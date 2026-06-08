"""
Сервисный слой бизнес-логики.
Реализует правила из spec/02_rules.md. Проверяется тестами в tasks/tests/.
Логика живёт здесь (не во вьюхах), чтобы быть тестируемой и единообразной.
"""
from django.db.models import Max
from django.utils import timezone
from .models import Task


def set_done(task: Task, done: bool) -> Task:
    """BR-3: завершение задачи проставляет/снимает completion_date."""
    task.done = done
    task.completion_date = timezone.now() if done else None
    task.save(update_fields=["done", "completion_date", "modified"])
    return task


def apply_hidden_state(task: Task) -> Task:
    """BR-1 (запись): state выводится из hide_until_date.
    Будущая дата → HIDDEN, иначе ACTIVE. Не сохраняет — это делает вызывающий.
    (Из APK: checkIfTaskIsHidden / checkIfShouldUnsetHidden.)"""
    now = timezone.now()
    if task.hide_until_date and task.hide_until_date > now:
        task.state = Task.State.HIDDEN
    else:
        task.state = Task.State.ACTIVE
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
