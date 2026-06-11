"""
Сервисный слой бизнес-логики.
Реализует правила из spec/02_rules.md. Проверяется тестами в tasks/tests/.
Логика живёт здесь (не во вьюхах), чтобы быть тестируемой и единообразной.
"""
import re
from datetime import datetime, timedelta
from dateutil.rrule import rrulestr
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

def _today_sod():
    """Start of today in the user's server time (getTodaySOD-equivalent)."""
    local = timezone.localtime(timezone.now())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


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
    """BR-3: завершение задачи проставляет/снимает completion_date.

    BR-5: завершение повторяющейся задачи порождает следующий экземпляр серии.
    """
    task.done = done
    task.completion_date = timezone.now() if done else None
    task.save(update_fields=["done", "completion_date", "modified"])
    if done and task.recur_rule:
        spawn_next_occurrence(task)
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
        # milestone = container project task; horizon derives from its (relative) due date.
        # from_template locks it from free editing (BLOCKED_BY_GOAL_TEMPLATE).
        milestone_tasks[ms.id] = Task.objects.create(
            owner=owner, title=ms.title, is_project=True, goal=goal,
            from_template=True, priority=next_priority(owner),
        )
    for tt in template.task_templates.all():
        Task.objects.create(
            owner=owner, title=tt.title, goal=goal,
            parent=milestone_tasks.get(tt.milestone_id),
            due_date=start_date + timedelta(days=tt.offset_days),
            from_template=True, priority=next_priority(owner),
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


def _rrule_parts(rule_str: str) -> dict:
    """Parse an RRULE string into an uppercase-keyed dict (the picker emits this subset)."""
    parts = {}
    for chunk in rule_str.split(";"):
        key, _, value = chunk.partition("=")
        parts[key.strip().upper()] = value.strip()
    return parts


def _parse_until(value: str):
    """RRULE UNTIL → aware datetime (YYYYMMDD or YYYYMMDDThhmmssZ); None if unparsable."""
    value = value.strip().upper()
    fmt = "%Y%m%dT%H%M%SZ" if "T" in value else "%Y%m%d"
    try:
        dt = datetime.strptime(value, fmt)
    except ValueError:
        return None
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


# A recurring series is a chain of Task rows that share a "series id" — the id of
# the first occurrence. Children carry recur_parent_id = series id (the first row's
# recur_parent_id is blank). The series root row also holds the EXDATE set (skipped
# dates) in recur_exclude_dates, so catch-up never regenerates a deleted occurrence.

def _series_id(task: Task) -> str:
    return task.recur_parent_id or task.id


def _series_root(task: Task):
    return Task.objects.filter(id=_series_id(task)).first()


def _date_key(dt) -> str:
    return timezone.localtime(dt).strftime("%Y-%m-%d") if dt else ""


def _exclude_set(root) -> set:
    if not root or not root.recur_exclude_dates:
        return set()
    return {d for d in root.recur_exclude_dates.split(",") if d}


def exclude_occurrence(task: Task) -> None:
    """BR-5 (EXDATE): record a deleted/skipped recurring occurrence's date on the
    series root so catch-up materialization never regenerates it."""
    if not (task.recur_rule or task.recur_parent_id) or not task.due_date:
        return
    root = _series_root(task)
    if root is None or root.id == task.id:
        return  # deleting the root itself: no stable place to store; series ends here
    excl = _exclude_set(root)
    excl.add(_date_key(task.due_date))
    root.recur_exclude_dates = ",".join(sorted(excl))
    root.save(update_fields=["recur_exclude_dates", "modified"])


def spawn_next_occurrence(task: Task, now=None, only_past: bool = False) -> "Task | None":
    """BR-5: create the next occurrence of a recurring series.

    Returns the new Task, or None if the task isn't recurring, the series has ended
    (COUNT exhausted / next date past UNTIL), the next occurrence already exists
    (idempotent), or — when only_past=True (catch-up) — the next date is in the future.
    The spawned occurrence is a fresh active task dated to the next RRULE date (skipping
    EXDATE), linked to the series root via recur_parent_id. Used both on completion and
    by catch-up materialization.
    """
    rule_str = (task.recur_rule or "").strip()
    if not rule_str:
        return None
    parts = _rrule_parts(rule_str)

    # COUNT termination: COUNT counts the occurrences remaining including this one,
    # so COUNT<=1 means this was the last.
    count = parts.get("COUNT")
    if count is not None and count.isdigit() and int(count) <= 1:
        return None

    series_id = _series_id(task)
    exclude = _exclude_set(_series_root(task))
    anchor = task.due_date or task.completion_date or timezone.now()
    # COUNT/UNTIL handled here, so drop them from the rule used to find the date.
    raw = ";".join(f"{k}={v}" for k, v in parts.items() if k not in ("COUNT", "UNTIL"))
    try:
        rule = rrulestr("RRULE:" + raw, dtstart=anchor)
    except (ValueError, TypeError):
        return None
    next_due = rule.after(anchor, inc=False)
    guard = 0
    while next_due is not None and _date_key(next_due) in exclude and guard < 1000:
        next_due = rule.after(next_due, inc=False)
        guard += 1
    if next_due is None:
        return None

    until = parts.get("UNTIL")
    if until:
        until_dt = _parse_until(until)
        if until_dt and next_due > until_dt:
            return None

    if only_past and now is not None and next_due > now:
        return None

    # idempotent: don't duplicate an occurrence the series already has at this date
    if Task.objects.filter(recur_parent_id=series_id, due_date=next_due).exists():
        return None

    child_parts = dict(parts)
    if count is not None and count.isdigit():
        child_parts["COUNT"] = str(int(count) - 1)
    child_rule = ";".join(f"{k}={v}" for k, v in child_parts.items())

    child = Task.objects.create(
        owner=task.owner, title=task.title, note=task.note,
        priority=next_priority(task.owner), is_project=task.is_project,
        goal=task.goal, context=task.context, parent=task.parent,
        due_date=next_due, recur_rule=child_rule, recur_parent_id=series_id,
    )
    # the new occurrence gets a fresh (unchecked) copy of the checklist
    for item in task.checklist.all():
        child.checklist.create(title=item.title, sort_order=item.sort_order)
    return child


def materialize_due_recurrences(now=None) -> int:
    """BR-5 (catch-up): generate the overdue occurrences that piled up while the user
    was away. For each recurring series, walk its frontier (latest-dated occurrence)
    forward, creating every occurrence whose due_date is already past — but NOT the
    first future one (that appears on completion). Returns the number created.

    Meant to be run periodically (cron / Celery-beat) — this is record materialization,
    not a horizon view computation, so a scheduler is appropriate here (unlike BR-8).
    """
    now = now or timezone.now()
    # frontier per series = the occurrence with the greatest due_date
    frontiers = {}
    for t in Task.objects.filter(archived=False, due_date__isnull=False).exclude(recur_rule=""):
        sid = _series_id(t)
        cur = frontiers.get(sid)
        if cur is None or t.due_date > cur.due_date:
            frontiers[sid] = t

    created = 0
    for frontier in frontiers.values():
        cur = frontier
        while True:
            child = spawn_next_occurrence(cur, now=now, only_past=True)
            if child is None:
                break
            created += 1
            cur = child
    return created


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
