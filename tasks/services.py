"""
Сервисный слой бизнес-логики.
Реализует правила из spec/02_rules.md. Проверяется тестами в tasks/tests/.
Логика живёт здесь (не во вьюхах), чтобы быть тестируемой и единообразной.
"""
import re
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone
from .models import Task, Goal


def visible_qs(qs):
    """BR-1: single source of the visibility filter (active, non-archived, not future-hidden)."""
    now = timezone.now()
    return qs.filter(archived=False, done=False).exclude(
        state=Task.State.HIDDEN, hide_until_date__gt=now)


# ---- Horizon as a function of due_date (Milestone 2: BR-7..BR-11) ----
# The planning horizon (INBOX/TODAY/WEEK/LATER) is NOT a stored choice; it is
# derived from `due_date` and "now", and lists are built by filtering on
# `due_date` at query time. This gives automatic midnight-correctness (a task
# dated "tomorrow" falls into TODAY on its own after midnight) with no cron.

def _today_eod():
    """End of today in the user's server time (getTodayEOD-equivalent)."""
    local = timezone.localtime(timezone.now())
    return local.replace(hour=23, minute=59, second=59, microsecond=999999)


def _week_eod():
    """End of the current week (Sunday EOD)."""
    local = timezone.localtime(timezone.now())
    days_until_sunday = 6 - local.weekday()  # Mon=0 .. Sun=6
    return (local + timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=59, microsecond=999999)


def horizon_for(due_date):
    """BR-7: map a due_date to its horizon (from APK calculateTaskType).

    None → INBOX; due today or overdue → TODAY; within this week → WEEK; later → LATER.
    """
    if due_date is None:
        return Task.Horizon.INBOX
    if due_date <= _today_eod():
        return Task.Horizon.TODAY
    if due_date <= _week_eod():
        return Task.Horizon.WEEK
    return Task.Horizon.LATER


def horizon_filter(qs, horizon_key):
    """BR-8: restrict a queryset to a horizon by filtering on due_date (no cron, no stored type)."""
    if horizon_key == "INBOX":
        return qs.filter(due_date__isnull=True)
    if horizon_key == "TODAY":
        return qs.filter(due_date__isnull=False, due_date__lte=_today_eod())
    if horizon_key == "WEEK":
        return qs.filter(due_date__gt=_today_eod(), due_date__lte=_week_eod())
    if horizon_key == "LATER":
        return qs.filter(due_date__gt=_week_eod())
    return qs


def due_for_horizon(horizon_key):
    """BR-10: a due_date that lands a task in the target horizon (used by move + quick-add).

    INBOX clears the date; the others pick a moment inside the horizon's range so
    that horizon_for() of the result equals horizon_key.
    """
    if horizon_key == "TODAY":
        return _today_eod()
    if horizon_key == "WEEK":
        return _week_eod()
    if horizon_key == "LATER":
        return _week_eod() + timedelta(days=1)
    return None  # INBOX


def set_done(task: Task, done: bool) -> Task:
    """BR-3: завершение задачи проставляет/снимает completion_date."""
    task.done = done
    task.completion_date = timezone.now() if done else None
    task.save(update_fields=["done", "completion_date", "modified"])
    return task


def next_priority(user) -> float:
    """BR-4: priority новой задачи = максимум среди задач владельца + 1.0."""
    current_max = Task.objects.filter(owner=user).aggregate(m=Max("priority"))["m"]
    return (current_max or 0.0) + 1.0


def priority_between(before: Task | None, after: Task | None, user=None) -> float:
    """
    BR-4: priority при вставке между соседями = среднее их priority.
    - между A и B → (A.priority + B.priority) / 2
    - в начало (before=None) → after.priority - 1.0
    - в конец (after=None) → before.priority + 1.0
    - пустой список → 1.0
    """
    if before and after:
        return (before.priority + after.priority) / 2
    if after and not before:
        return after.priority - 1.0
    if before and not after:
        return before.priority + 1.0
    return 1.0


def create_task(user, title: str, **kwargs) -> Task:
    """Создание задачи с авто-priority (BR-4)."""
    kwargs.setdefault("priority", next_priority(user))
    return Task.objects.create(owner=user, title=title, **kwargs)


def create_goal_from_template(template, owner, start_date):
    """BR-18: instantiate a real goal from a template, expanding relative dates.

    Milestones become container project-tasks (BR-8); a milestone's task
    templates become subtasks of it (BR-7). due_date = start_date + offset_days.
    """
    goal = Goal.objects.create(
        owner=owner, title=template.title, description=template.description,
        goal_type=template.goal_type, status=Goal.Status.ACTIVE, start_period=start_date,
    )
    milestone_tasks = {}
    for ms in template.milestones.all():
        # milestone = container project task; horizon derives from its (relative) due date
        milestone_tasks[ms.id] = Task.objects.create(
            owner=owner, title=ms.title, is_project=True, goal=goal,
            priority=next_priority(owner),
        )
    for tt in template.task_templates.all():
        Task.objects.create(
            owner=owner, title=tt.title, goal=goal,
            parent=milestone_tasks.get(tt.milestone_id),
            due_date=start_date + timedelta(days=tt.offset_days),
            priority=next_priority(owner),
        )
    return goal


HORIZON_BY_KEY = {
    "TODAY": Task.Horizon.TODAY,
    "WEEK": Task.Horizon.WEEK,
    "LATER": Task.Horizon.LATER,
    "INBOX": Task.Horizon.INBOX,
}


_FREQS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
_WEEKDAYS = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}
_BYDAY_RE = re.compile(r"^[+-]?\d*(MO|TU|WE|TH|FR|SA|SU)$")
_UNTIL_RE = re.compile(r"^\d{8}(T\d{6}Z)?$")


def validate_rrule(rule: str) -> bool:
    """BR-5: validate the accepted RRULE subset (the picker only emits this subset).

    Empty string is valid (recurrence off). Otherwise FREQ is required and every
    KEY=VALUE pair must be a known key with a valid value; anything else fails.
    """
    rule = (rule or "").strip()
    if not rule:
        return True
    parts = {}
    for chunk in rule.split(";"):
        if "=" not in chunk:
            return False
        key, _, value = chunk.partition("=")
        key = key.strip().upper()
        if key in parts:  # duplicate key
            return False
        parts[key] = value.strip()

    if parts.get("FREQ") not in _FREQS:
        return False

    for key, value in parts.items():
        if key == "FREQ":
            continue
        if key in ("INTERVAL", "COUNT"):
            if not (value.isdigit() and int(value) >= 1):
                return False
        elif key == "BYMONTHDAY":
            if not (value.lstrip("-").isdigit() and 1 <= abs(int(value)) <= 31):
                return False
        elif key == "BYDAY":
            days = value.split(",")
            if not days or not all(_BYDAY_RE.match(d) for d in days):
                return False
        elif key == "WKST":
            if value.upper() not in _WEEKDAYS:
                return False
        elif key == "UNTIL":
            if not _UNTIL_RE.match(value.upper()):
                return False
        else:
            return False  # unknown key
    return True


def move_task(task: Task, horizon_key: str) -> Task:
    """Feature catalog #1 + BR-10: move between horizons by setting due_date.

    The horizon is derived from due_date (BR-7), so moving means re-dating the task;
    the whole subtree is carried along to the same date.
    """
    if horizon_key in HORIZON_BY_KEY:
        _set_due_recursive(task, due_for_horizon(horizon_key))
    return task


def _set_due_recursive(task: Task, due) -> None:
    task.due_date = due
    task.save(update_fields=["due_date", "task_type", "modified"])  # save() re-derives task_type
    for child in task.children.all():
        _set_due_recursive(child, due)


def copy_task(task: Task) -> Task:
    """Feature catalog #7 (buildTaskCopy): duplicate a task with its checklist.

    The copy is fresh (not done), gets a new priority, and keeps goal/context/
    parent/dates/recurrence. Subtasks are NOT copied (only the checklist).
    """
    copy = Task.objects.create(
        owner=task.owner, title=f"{task.title} (копия)", note=task.note,
        task_type=task.task_type, state=task.state,
        priority=next_priority(task.owner), is_project=task.is_project,
        goal=task.goal, context=task.context, parent=task.parent,
        start_date=task.start_date, due_date=task.due_date,
        hide_until_date=task.hide_until_date, recur_rule=task.recur_rule,
    )
    for item in task.checklist.all():
        copy.checklist.create(title=item.title, done=item.done, sort_order=item.sort_order)
    return copy


def set_archived(task: Task, archived: bool) -> Task:
    """BR-9: archive/restore a task and its whole subtree."""
    task.archived = archived
    task.save(update_fields=["archived", "modified"])
    for child in task.children.all():
        set_archived(child, archived)
    return task


def apply_hidden_state(task: Task) -> None:
    """BR-1 + BR-7: a future hide_until_date implies HIDDEN, else ACTIVE.

    The caller saves `task` itself (it is mid-form-save); this mirrors the parent's
    hide state + date onto every descendant (CAN_HIDE_DESCENDANTS).
    """
    hidden = bool(task.hide_until_date and task.hide_until_date > timezone.now())
    task.state = Task.State.HIDDEN if hidden else Task.State.ACTIVE
    _propagate_hidden(task, task.state, task.hide_until_date if hidden else None)


def _propagate_hidden(task: Task, state: int, hide_until) -> None:
    for child in task.children.all():
        child.state = state
        child.hide_until_date = hide_until
        child.save(update_fields=["state", "hide_until_date", "modified"])
        _propagate_hidden(child, state, hide_until)
