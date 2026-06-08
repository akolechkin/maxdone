"""
Сервисный слой бизнес-логики.
Реализует правила из spec/02_rules.md. Проверяется тестами в tasks/tests/.
Логика живёт здесь (не во вьюхах), чтобы быть тестируемой и единообразной.
"""
import re
from django.db.models import Max
from django.utils import timezone
from .models import Task


def visible_qs(qs):
    """BR-1: single source of the visibility filter (active, non-archived, not future-hidden)."""
    now = timezone.now()
    return qs.filter(archived=False, done=False).exclude(
        state=Task.State.HIDDEN, hide_until_date__gt=now)


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
    """Feature catalog #1 + BR-7: move between horizons, carrying the whole subtree."""
    if horizon_key in HORIZON_BY_KEY:
        _set_type_recursive(task, HORIZON_BY_KEY[horizon_key])
    return task


def _set_type_recursive(task: Task, target: int) -> None:
    task.task_type = target
    task.save(update_fields=["task_type", "modified"])
    for child in task.children.all():
        _set_type_recursive(child, target)


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
