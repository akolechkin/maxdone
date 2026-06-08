from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Task, Goal, Context, CheckListItem
from .forms import TaskForm, GoalForm, ContextForm
from . import services

HORIZON_LABELS = {
    "TODAY": ("Сегодня", Task.Horizon.TODAY),
    "WEEK": ("Неделя", Task.Horizon.WEEK),
    "LATER": ("Позже", Task.Horizon.LATER),
    "INBOX": ("Входящие", Task.Horizon.INBOX),
}


def _visible_tasks(user):
    """BR-1: active, non-archived; hidden ones surface once hide_until_date passes."""
    now = timezone.now()
    qs = Task.objects.filter(owner=user, archived=False, done=False)
    return qs.exclude(state=Task.State.HIDDEN, hide_until_date__gt=now)


def _horizon_counts(user):
    tasks = _visible_tasks(user)
    return {key: tasks.filter(task_type=val).count() for key, (_, val) in HORIZON_LABELS.items()}


HORIZON_NAV = [(k, lbl) for k, (lbl, _) in HORIZON_LABELS.items()]


def _board_context(request, horizon="TODAY"):
    label, value = HORIZON_LABELS.get(horizon, HORIZON_LABELS["TODAY"])
    return {
        "tasks": _visible_tasks(request.user).filter(task_type=value),
        "horizon": horizon,
        "horizon_label": label,
        "horizon_nav": HORIZON_NAV,
        "counts": _horizon_counts(request.user),
        "goals": Goal.objects.filter(owner=request.user, archived=False),
        "contexts": Context.objects.filter(owner=request.user, archived=False),
    }


def _apply_hidden_state(task):
    """BR-1: a future hide_until_date implies HIDDEN; otherwise ACTIVE."""
    if task.hide_until_date and task.hide_until_date > timezone.now():
        task.state = Task.State.HIDDEN
    else:
        task.state = Task.State.ACTIVE


@login_required
def board(request):
    horizon = request.GET.get("h", "TODAY")
    ctx = _board_context(request, horizon)
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_task_list.html", ctx)
    return render(request, "tasks/board.html", ctx)


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    form = TaskForm(instance=task, user=request.user)
    return render(request, "tasks/_task_editor.html", {"task": task, "form": form})


@login_required
def task_new(request):
    form = TaskForm(user=request.user, initial={"task_type": Task.Horizon.TODAY})
    return render(request, "tasks/_task_editor.html", {"task": None, "form": form})


@login_required
@require_http_methods(["POST"])
def task_create(request):
    form = TaskForm(request.POST, user=request.user)
    if form.is_valid():
        task = form.save(commit=False)
        task.owner = request.user
        task.priority = services.next_priority(request.user)
        _apply_hidden_state(task)
        task.save()
        ctx = _board_context(request, request.GET.get("h", "TODAY"))
        resp = render(request, "tasks/_task_list.html", ctx)
        resp["HX-Trigger"] = "taskSaved"
        return resp
    return render(request, "tasks/_task_editor.html", {"task": None, "form": form}, status=422)


@login_required
@require_http_methods(["POST"])
def task_update(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    form = TaskForm(request.POST, instance=task, user=request.user)
    if form.is_valid():
        task = form.save(commit=False)
        _apply_hidden_state(task)
        task.save()
        ctx = _board_context(request, request.GET.get("h", "TODAY"))
        resp = render(request, "tasks/_task_list.html", ctx)
        resp["HX-Trigger"] = "taskSaved"
        return resp
    return render(request, "tasks/_task_editor.html", {"task": task, "form": form}, status=422)


@login_required
@require_http_methods(["POST", "DELETE"])
def task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    task.delete()
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def toggle_done(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.set_done(task, not task.done)
    return render(request, "tasks/_task_row.html", {"task": task})


@login_required
@require_http_methods(["POST"])
def check_item_add(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    title = (request.POST.get("title") or "").strip()
    if title:
        order = task.checklist.count()
        task.checklist.create(title=title, sort_order=order)
    return render(request, "tasks/_checklist.html", {"task": task})


@login_required
@require_http_methods(["POST"])
def toggle_check_item(request, item_id):
    item = get_object_or_404(CheckListItem, id=item_id, task__owner=request.user)
    item.done = not item.done
    item.save(update_fields=["done"])
    return render(request, "tasks/_check_item.html", {"item": item})


@login_required
@require_http_methods(["POST"])
def check_item_delete(request, item_id):
    item = get_object_or_404(CheckListItem, id=item_id, task__owner=request.user)
    task = item.task
    item.delete()
    return render(request, "tasks/_checklist.html", {"task": task})


@login_required
@require_http_methods(["POST"])
def task_move(request, task_id, horizon):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.move_task(task, horizon)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
def search(request):
    q = (request.GET.get("q") or "").strip()
    tasks = Task.objects.none()
    goals = Goal.objects.none()
    if q:
        tasks = Task.objects.filter(owner=request.user, archived=False, title__icontains=q)
        goals = Goal.objects.filter(owner=request.user, archived=False, title__icontains=q)
    ctx = {"q": q, "tasks": tasks, "goals": goals}
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_search_results.html", ctx)
    return render(request, "tasks/search.html", ctx)


# ---- Goals ----

@login_required
def goal_list(request):
    goals = Goal.objects.filter(owner=request.user, archived=False)
    ctx = {"goals": goals}
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_goal_list.html", ctx)
    return render(request, "tasks/goals.html", ctx)


@login_required
def goal_new(request):
    return render(request, "tasks/_goal_editor.html", {"goal": None, "form": GoalForm()})


@login_required
@require_http_methods(["POST"])
def goal_create(request):
    form = GoalForm(request.POST)
    if form.is_valid():
        goal = form.save(commit=False)
        goal.owner = request.user
        goal.save()
        return render(request, "tasks/_goal_list.html",
                      {"goals": Goal.objects.filter(owner=request.user, archived=False)})
    return render(request, "tasks/_goal_editor.html", {"goal": None, "form": form}, status=422)


@login_required
def goal_edit(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, owner=request.user)
    return render(request, "tasks/_goal_editor.html", {"goal": goal, "form": GoalForm(instance=goal)})


@login_required
@require_http_methods(["POST"])
def goal_update(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, owner=request.user)
    form = GoalForm(request.POST, instance=goal)
    if form.is_valid():
        form.save()
        return render(request, "tasks/_goal_list.html",
                      {"goals": Goal.objects.filter(owner=request.user, archived=False)})
    return render(request, "tasks/_goal_editor.html", {"goal": goal, "form": form}, status=422)


@login_required
@require_http_methods(["POST", "DELETE"])
def goal_delete(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, owner=request.user)
    goal.delete()
    return render(request, "tasks/_goal_list.html",
                  {"goals": Goal.objects.filter(owner=request.user, archived=False)})


# ---- Contexts ----

@login_required
def context_list(request):
    contexts = Context.objects.filter(owner=request.user, archived=False)
    ctx = {"contexts": contexts}
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_context_list.html", ctx)
    return render(request, "tasks/contexts.html", ctx)


@login_required
@require_http_methods(["POST"])
def context_create(request):
    form = ContextForm(request.POST)
    if form.is_valid():
        c = form.save(commit=False)
        c.owner = request.user
        c.save()
    return render(request, "tasks/_context_list.html",
                  {"contexts": Context.objects.filter(owner=request.user, archived=False)})


@login_required
@require_http_methods(["POST", "DELETE"])
def context_delete(request, context_id):
    c = get_object_or_404(Context, id=context_id, owner=request.user)
    c.delete()
    return render(request, "tasks/_context_list.html",
                  {"contexts": Context.objects.filter(owner=request.user, archived=False)})
