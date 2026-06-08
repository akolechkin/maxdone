from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Task, Goal, Context

HORIZON_LABELS = {
    "TODAY": ("Сегодня", Task.Horizon.TODAY),
    "WEEK": ("Неделя", Task.Horizon.WEEK),
    "LATER": ("Позже", Task.Horizon.LATER),
    "INBOX": ("Входящие", Task.Horizon.INBOX),
}


def _visible_tasks(user):
    """Active, non-archived tasks; hidden ones surface once hide_until_date passes."""
    now = timezone.now()
    qs = Task.objects.filter(owner=user, archived=False, done=False)
    return qs.exclude(state=Task.State.HIDDEN, hide_until_date__gt=now)


def _horizon_counts(user):
    tasks = _visible_tasks(user)
    return {
        key: tasks.filter(task_type=val).count()
        for key, (_, val) in HORIZON_LABELS.items()
    }


@login_required
def board(request):
    horizon = request.GET.get("h", "TODAY")
    label, value = HORIZON_LABELS.get(horizon, HORIZON_LABELS["TODAY"])
    tasks = _visible_tasks(request.user).filter(task_type=value)
    ctx = {
        "tasks": tasks,
        "horizon": horizon,
        "horizon_label": label,
        "counts": _horizon_counts(request.user),
        "goals": Goal.objects.filter(owner=request.user, archived=False),
        "contexts": Context.objects.filter(owner=request.user, archived=False),
    }
    # HTMX request -> return only the list fragment
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_task_list.html", ctx)
    return render(request, "tasks/board.html", ctx)


@login_required
@require_http_methods(["POST"])
def task_create(request):
    """spec/03_api_ui.md: 'Новая задача' создаёт задачу в горизонте `h`
    (по умолчанию INBOX), а не открывает существующую."""
    from .services import create_task
    horizon = request.POST.get("h", "INBOX")
    label, value = HORIZON_LABELS.get(horizon, HORIZON_LABELS["INBOX"])
    task = create_task(request.user, title="Новая задача", task_type=value)
    ctx = {
        "task": task,
        "tasks": _visible_tasks(request.user).filter(task_type=value),
        "horizon": horizon,
        "horizon_label": label,
        "counts": _horizon_counts(request.user),
        "goals": Goal.objects.filter(owner=request.user, archived=False),
        "contexts": Context.objects.filter(owner=request.user, archived=False),
        "horizons": Task.Horizon.choices,
    }
    return render(request, "tasks/_task_created.html", ctx)


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    ctx = {
        "task": task,
        "goals": Goal.objects.filter(owner=request.user, archived=False),
        "contexts": Context.objects.filter(owner=request.user, archived=False),
        "horizons": Task.Horizon.choices,
    }
    return render(request, "tasks/_task_editor.html", ctx)


@login_required
@require_http_methods(["POST"])
def toggle_done(request, task_id):
    from .services import set_done
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    set_done(task, not task.done)
    return render(request, "tasks/_task_row.html", {"task": task})


@login_required
@require_http_methods(["POST"])
def toggle_check_item(request, item_id):
    from .models import CheckListItem
    item = get_object_or_404(CheckListItem, id=item_id, task__owner=request.user)
    item.done = not item.done
    item.save(update_fields=["done"])
    return render(request, "tasks/_check_item.html", {"item": item})
