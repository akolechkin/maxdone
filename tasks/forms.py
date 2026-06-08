from django import forms
from .models import Task, Goal, Context
from .services import validate_rrule


class TaskForm(forms.ModelForm):
    """Create/edit task. Date fields use HTML5 datetime-local inputs."""

    class Meta:
        model = Task
        # gap #1: start_date dropped from the editing flow; due_date is the single
        # primary date (date picker), hide_until_date is a separate "hide until" control.
        fields = [
            "title", "note", "task_type", "goal", "context",
            "due_date", "hide_until_date", "recur_rule", "is_project",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full border border-line rounded-md px-3 py-2 text-sm",
                "placeholder": "Что нужно сделать?",
                "autofocus": "autofocus",
            }),
            "note": forms.Textarea(attrs={
                "class": "w-full border border-line rounded-md px-3 py-2 text-sm",
                "rows": 3, "placeholder": "Заметка…",
            }),
            "task_type": forms.Select(attrs={"class": "border border-line rounded-md px-2 py-1.5 text-sm"}),
            "goal": forms.Select(attrs={"class": "border border-line rounded-md px-2 py-1.5 text-sm"}),
            "context": forms.Select(attrs={"class": "border border-line rounded-md px-2 py-1.5 text-sm"}),
            # due_date / hide_until_date: native date picker (one date, no time-of-day)
            "due_date": forms.DateInput(attrs={
                "type": "date",
                "class": "border border-line rounded-md px-2 py-1.5 text-sm",
            }, format="%Y-%m-%d"),
            "hide_until_date": forms.DateInput(attrs={
                "type": "date",
                "class": "border border-line rounded-md px-2 py-1.5 text-sm",
            }, format="%Y-%m-%d"),
            "recur_rule": forms.TextInput(attrs={
                "class": "border border-line rounded-md px-2 py-1.5 text-sm",
                "placeholder": "FREQ=WEEKLY",
            }),
            "is_project": forms.CheckboxInput(attrs={"class": "rounded border-line"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # date picker submits YYYY-MM-DD; field is a DateTimeField (stored at midnight)
        for f in ("due_date", "hide_until_date"):
            self.fields[f].input_formats = ["%Y-%m-%d"]
            self.fields[f].required = False
        self.fields["note"].required = False
        self.fields["goal"].required = False
        self.fields["context"].required = False
        self.fields["recur_rule"].required = False
        # scope goal/context choices to the owner
        if user is not None:
            self.fields["goal"].queryset = Goal.objects.filter(owner=user, archived=False)
            self.fields["context"].queryset = Context.objects.filter(owner=user, archived=False)

    def clean_recur_rule(self):
        # BR-5: recur_rule is assembled by the picker; reject malformed RRULE strings.
        rule = (self.cleaned_data.get("recur_rule") or "").strip()
        if rule and not validate_rrule(rule):
            raise forms.ValidationError("Некорректное правило повтора.")
        return rule


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ["title", "description", "goal_type", "status", "start_period", "end_period"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full border border-line rounded-md px-3 py-2 text-sm",
                "placeholder": "Название цели", "autofocus": "autofocus",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full border border-line rounded-md px-3 py-2 text-sm",
                "rows": 3, "placeholder": "Описание…",
            }),
            "goal_type": forms.Select(attrs={"class": "border border-line rounded-md px-2 py-1.5 text-sm"}),
            "status": forms.Select(attrs={"class": "border border-line rounded-md px-2 py-1.5 text-sm"}),
            "start_period": forms.DateInput(attrs={"type": "date", "class": "border border-line rounded-md px-2 py-1.5 text-sm"}, format="%Y-%m-%d"),
            "end_period": forms.DateInput(attrs={"type": "date", "class": "border border-line rounded-md px-2 py-1.5 text-sm"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("description", "start_period", "end_period"):
            self.fields[f].required = False
        self.fields["start_period"].input_formats = ["%Y-%m-%d"]
        self.fields["end_period"].input_formats = ["%Y-%m-%d"]


class ContextForm(forms.ModelForm):
    class Meta:
        model = Context
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full border border-line rounded-md px-3 py-2 text-sm",
                "placeholder": "Название контекста (например, дома)", "autofocus": "autofocus",
            }),
        }
