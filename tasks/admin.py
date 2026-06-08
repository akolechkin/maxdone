from django.contrib import admin
from .models import Task, Goal, Context, CheckListItem


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "task_type", "state", "done", "due_date")
    list_filter = ("task_type", "state", "done", "archived")
    search_fields = ("title",)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "goal_type", "status")
    list_filter = ("goal_type",)


admin.site.register(Context)
admin.site.register(CheckListItem)
