"""
Формы редактирования. TaskEditForm — поля редактора из spec/03_api_ui.md
(TaskEditFragment, провенанс §134). goal/context ограничены владельцем (BR-6).
"""
from django import forms
from .models import Task, Goal, Context

_DT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]


class TaskEditForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title", "note", "task_type", "goal", "context",
            "due_date", "hide_until_date", "recur_rule",
        ]

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["goal"].queryset = Goal.objects.filter(owner=owner, archived=False)
            self.fields["context"].queryset = Context.objects.filter(owner=owner, archived=False)
        for name in ("note", "goal", "context", "due_date", "hide_until_date", "recur_rule"):
            self.fields[name].required = False
        for name in ("due_date", "hide_until_date"):
            self.fields[name].input_formats = _DT_FORMATS
