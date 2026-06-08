"""
Domain model reconstructed from the decompiled MaxDone APK (greenDAO schema).
Entities, enums and key fields mirror the original; implementation is our own.
"""
import uuid
from django.conf import settings
from django.db import models


def _uuid():
    return uuid.uuid4().hex


class TimeStamped(models.Model):
    """Shared audit + sync fields present on every original entity."""
    id = models.CharField(primary_key=True, max_length=32, default=_uuid, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    local_change_date = models.DateTimeField(auto_now=True)
    archived = models.BooleanField(default=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Context(TimeStamped):
    """A lightweight tag/condition, e.g. @home, @5min."""
    title = models.CharField(max_length=120)

    def __str__(self):
        return self.title


class Goal(TimeStamped):
    class Type(models.TextChoices):
        PRIVATE = "PRIVATE", "Личная"
        CORPORATE = "CORPORATE", "Корпоративная"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    goal_type = models.CharField(max_length=12, choices=Type.choices, default=Type.PRIVATE)
    status = models.CharField(max_length=40, blank=True)
    start_period = models.DateField(null=True, blank=True)
    end_period = models.DateField(null=True, blank=True)
    shared = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Task(TimeStamped):
    class Horizon(models.IntegerChoices):
        UNDEFINED = 0, "Не задан"
        INBOX = 1, "Входящие"
        TODAY = 2, "Сегодня"
        WEEK = 3, "Неделя"
        LATER = 4, "Позже"

    class State(models.IntegerChoices):
        ACTIVE = 0, "Активна"
        HIDDEN = 1, "Скрыта"

    title = models.CharField(max_length=500)
    note = models.TextField(blank=True)
    task_type = models.IntegerField(choices=Horizon.choices, default=Horizon.INBOX)
    state = models.IntegerField(choices=State.choices, default=State.ACTIVE)
    priority = models.FloatField(default=0.0)  # fractional rank for drag-and-drop
    done = models.BooleanField(default=False)
    is_project = models.BooleanField(default=False)

    goal = models.ForeignKey(Goal, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    context = models.ForeignKey(Context, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    start_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    hide_until_date = models.DateTimeField(null=True, blank=True)

    # iCal RRULE string + series/exception tracking (as in original)
    recur_rule = models.CharField(max_length=255, blank=True)
    recur_parent_id = models.CharField(max_length=32, blank=True)
    recur_exclude_dates = models.TextField(blank=True)

    class Meta:
        ordering = ["priority", "-created"]

    def __str__(self):
        return self.title

    def visible_children(self):
        """BR-1/BR-7: child subtasks that pass the visibility filter."""
        from . import services
        return services.visible_qs(self.children.all())


class CheckListItem(models.Model):
    """Sub-item of a task. In the original these were JSON-serialized on Task."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="checklist")
    title = models.CharField(max_length=300)
    done = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.title
