from datetime import datetime
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods
from .models import Task, Goal, Context, CheckListItem, GoalTemplate
from .forms import TaskForm, GoalForm, ContextForm
from . import services


def signup(request):
    """Feature catalog #16: self-service registration (web equivalent of signUp)."""
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("board")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})

HORIZON_LABELS = {
    "TODAY": ("Сегодня", Task.Horizon.TODAY),
    "WEEK": ("Неделя", Task.Horizon.WEEK),
    "LATER": ("Позже", Task.Horizon.LATER),
    "INBOX": ("Входящие", Task.Horizon.INBOX),
}


def _visible_tasks(user):
    """BR-1: single source of the visibility filter (used by the BR arbiter tests)."""
    return services.visible_qs(Task.objects.filter(owner=user))


def _horizon_counts(user):
    """BR-2 + BR-11: visible root-level tasks per horizon (counted by due_date)."""
    tasks = _visible_tasks(user).filter(parent__isnull=True)
    return {key: services.horizon_filter(tasks, key).count() for key in HORIZON_LABELS}


def _board_tasks(request):
    """BR-7 + BR-12: root-level tasks for the board list, honoring the show_hidden setting."""
    qs = Task.objects.filter(owner=request.user, parent__isnull=True, archived=False, done=False)
    if not request.session.get("show_hidden"):
        now = timezone.now()
        qs = qs.exclude(state=Task.State.HIDDEN, hide_until_date__gt=now)
        qs = qs.exclude(goal__status=Goal.Status.PAUSED)  # BR-16: paused goal hides its tasks
    return qs


HORIZON_NAV = [(k, lbl) for k, (lbl, _) in HORIZON_LABELS.items()]


SORT_ORDERS = {
    "priority": ("priority", "-created"),   # default
    "due": ("due_date",),                   # nulls last on Postgres ASC
    "recent": ("-created",),
    "updated": ("-modified",),
}


def _grouped(tasks, group_by):
    """BR-17: group an ordered task list by goal/context for the grouped view."""
    if group_by not in ("goal", "context"):
        return None
    empty = "Без цели" if group_by == "goal" else "Без контекста"
    groups = {}
    for t in tasks:
        rel = t.goal if group_by == "goal" else t.context
        key = rel.title if rel else empty
        groups.setdefault(key, []).append(t)
    return list(groups.items())


def _collapse_recurrences(tasks):
    """spec/06 B: collapse >=2 overdue instances of one recurring series into a single
    group row (count, "mark all"). Returns (recur_groups, singles). Lone overdue
    instances stay normal rows. Visual only — no data change."""
    sod = services._today_sod()
    by_series, singles = {}, []
    for t in tasks:
        recurring = bool(t.recur_rule or t.recur_parent_id)
        overdue = t.due_date is not None and t.due_date < sod
        if recurring and overdue and not t.done:
            by_series.setdefault(t.recur_parent_id or t.id, []).append(t)
        else:
            singles.append(t)
    groups = []
    for sid, items in by_series.items():
        if len(items) >= 2:
            groups.append({"series_id": sid, "title": items[0].title, "count": len(items)})
        else:
            singles.extend(items)
    return groups, singles


def _board_context(request, horizon="TODAY"):
    label, _ = HORIZON_LABELS.get(horizon, HORIZON_LABELS["TODAY"])
    sort = request.session.get("sort", "priority")
    order = SORT_ORDERS.get(sort, SORT_ORDERS["priority"])
    group_by = request.session.get("group_by", "none")
    # BR-7/BR-8: the horizon list is built by filtering on due_date, not task_type.
    tasks = services.horizon_filter(_board_tasks(request), horizon).order_by(*order)
    groups = _grouped(tasks, group_by)
    recur_groups = None
    if group_by == "none":  # overdue-recurrence collapse only in the flat list
        recur_groups, tasks = _collapse_recurrences(list(tasks))
    return {
        "tasks": tasks,
        "groups": groups,
        "recur_groups": recur_groups,
        "group_by": group_by,
        "sort": sort,
        "horizon": horizon,
        "horizon_label": label,
        "horizon_nav": HORIZON_NAV,
        "counts": _horizon_counts(request.user),
        "goals": Goal.objects.filter(owner=request.user, archived=False),
        "contexts": Context.objects.filter(owner=request.user, archived=False),
        "show_hidden": bool(request.session.get("show_hidden")),
        "quick_add": bool(request.session.get("quick_add")),
        # BR-11: on HTMX swaps, refresh the sidebar counters out-of-band. Suppressed on
        # the full-page render (board.html embeds _task_list, where OOB spans would be inert clutter).
        "oob_counts": bool(request.headers.get("HX-Request")),
    }


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
    # BLOCKED_BY_GOAL_TEMPLATE: tasks created from a goal template are read-only.
    return render(request, "tasks/_task_editor.html",
                  {"task": task, "form": form, "locked": task.from_template})


@login_required
def task_new(request):
    # BR-20: a new task without a date lands in the box ACTIVE at creation (the viewed
    # horizon), not always INBOX. The form posts ?h=<horizon> so task_create knows the box.
    # BR-15: prefill from the last-used goal/context/is_project (task preferences).
    initial = {}
    if request.session.get("pref_goal"):
        initial["goal"] = request.session["pref_goal"]
    if request.session.get("pref_context"):
        initial["context"] = request.session["pref_context"]
    if request.session.get("pref_is_project"):
        initial["is_project"] = True
    form = TaskForm(user=request.user, initial=initial)
    horizon = request.GET.get("h", "TODAY")
    return render(request, "tasks/_task_editor.html",
                  {"task": None, "form": form, "horizon": horizon})


@login_required
@require_http_methods(["POST"])
def task_create(request):
    form = TaskForm(request.POST, user=request.user)
    if form.is_valid():
        task = form.save(commit=False)
        task.owner = request.user
        task.priority = services.next_priority(request.user)
        # BR-10: quick-add from a horizon column dates the task into that column,
        # unless the user already gave it a due_date.
        set_h = request.POST.get("set_horizon")
        if set_h and not task.due_date:
            task.due_date = services.due_for_horizon(set_h)
        # BR-24: setting a repeat on a task with no date anchors it to the nearest rule date.
        if task.recur_rule and not task.due_date:
            task.due_date = services.first_occurrence(task.recur_rule)
        # BR-20: a still-dateless task lands in the box active at creation (set_horizon for
        # quick-add, else the viewed horizon), NOT forced into INBOX.
        if not task.due_date:
            box = set_h or request.GET.get("h", "INBOX")
            task.task_type = services.HORIZON_BY_KEY.get(box, Task.Horizon.INBOX)
        services.apply_hidden_state(task)
        task.save()
        # BR-15: remember this task's goal/context/is_project for the next new task.
        request.session["pref_goal"] = str(task.goal_id or "")
        request.session["pref_context"] = str(task.context_id or "")
        request.session["pref_is_project"] = task.is_project
        ctx = _board_context(request, request.GET.get("h", "TODAY"))
        resp = render(request, "tasks/_task_list.html", ctx)
        resp["HX-Trigger"] = "taskSaved"
        return resp
    return render(request, "tasks/_task_editor.html", {"task": None, "form": form}, status=422)


@login_required
@require_http_methods(["POST"])
def task_update(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    if task.from_template:  # BLOCKED_BY_GOAL_TEMPLATE: template-derived tasks can't be edited
        return HttpResponse(status=403)
    form = TaskForm(request.POST, instance=task, user=request.user)
    if form.is_valid():
        task = form.save(commit=False)
        # BR-24: if a repeat is set but the date was cleared, re-anchor to the nearest rule
        # date. (Sending a recurring task to INBOX dateless is the separate to_inbox action.)
        if task.recur_rule and not task.due_date:
            task.due_date = services.first_occurrence(task.recur_rule)
        services.apply_hidden_state(task)
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
    services.exclude_occurrence(task)  # BR-5: skip this date in future catch-up if recurring
    task.delete()
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def toggle_done(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.set_done(task, not task.done)
    # BR-11: completing/uncompleting changes the horizon counters → refresh them OOB.
    return render(request, "tasks/_task_row_swap.html",
                  {"task": task, "counts": _horizon_counts(request.user)})


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
def subtask_add(request, task_id):
    """BR-7: add a child task; it inherits the parent's horizon (via due_date) and owner."""
    parent = get_object_or_404(Task, id=task_id, owner=request.user)
    title = (request.POST.get("title") or "").strip()
    if title:
        Task.objects.create(
            owner=request.user, title=title, parent=parent,
            due_date=parent.due_date, task_type=parent.task_type,  # BR-20: inherit the parent's box
            priority=services.next_priority(request.user),
        )
    return render(request, "tasks/_subtasks.html", {"task": parent})


@login_required
@require_http_methods(["POST"])
def subtask_toggle(request, task_id):
    """BR-23: clicking a subtask toggles its done state (NOT delete); the section re-renders."""
    child = get_object_or_404(Task, id=task_id, owner=request.user)
    services.set_done(child, not child.done)
    return render(request, "tasks/_subtasks.html", {"task": child.parent})


@login_required
@require_http_methods(["POST", "DELETE"])
def subtask_delete(request, task_id):
    """BR-23: deleting a subtask is a SEPARATE explicit action (the × control)."""
    child = get_object_or_404(Task, id=task_id, owner=request.user)
    parent = child.parent
    services.exclude_occurrence(child)  # BR-5: skip this date if recurring
    child.delete()
    return render(request, "tasks/_subtasks.html", {"task": parent})


@login_required
@require_http_methods(["POST"])
def task_copy(request, task_id):
    """Feature catalog #7: duplicate the task (with checklist)."""
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.copy_task(task)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    resp = render(request, "tasks/_task_list.html", ctx)
    resp["HX-Trigger"] = "taskSaved"
    return resp


@login_required
@require_http_methods(["POST"])
def task_reorder(request):
    """spec/06 next-step: reorder within a list by fractional priority (BR-4).

    Drag&drop sends the moved task id plus its new neighbours; only `priority`
    changes — the horizon stays derived from due_date (BR-7).
    """
    task = get_object_or_404(Task, id=request.POST.get("id", ""), owner=request.user)
    before = Task.objects.filter(id=request.POST.get("before") or "", owner=request.user).first()
    after = Task.objects.filter(id=request.POST.get("after") or "", owner=request.user).first()
    task.priority = services.priority_between(before, after)
    task.save(update_fields=["priority", "modified"])
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def recur_group_done(request):
    """spec/06 B: "mark all" — complete every overdue instance of a recurring series."""
    sid = request.POST.get("series", "")
    sod = services._today_sod()
    qs = (Task.objects.filter(owner=request.user, done=False, archived=False, due_date__lt=sod)
          .filter(Q(id=sid) | Q(recur_parent_id=sid)))
    for t in list(qs):
        services.set_done(t, True)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    resp = render(request, "tasks/_task_list.html", ctx)
    resp["HX-Trigger"] = "taskSaved"
    return resp


@login_required
@require_http_methods(["POST"])
def task_move(request, task_id, horizon):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.move_task(task, horizon)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def task_to_inbox(request, task_id):
    """BR-21: send the task to INBOX (clears due_date, sets the box to INBOX).
    BR-25: a recurring task keeps its rule — the repeat sleeps in INBOX without a date."""
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.to_inbox(task)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    resp = render(request, "tasks/_task_list.html", ctx)
    resp["HX-Trigger"] = "taskSaved"
    return resp


# ---- Archive (BR-9) ----

@login_required
@require_http_methods(["POST"])
def task_archive(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.set_archived(task, True)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def task_unarchive(request, task_id):
    task = get_object_or_404(Task, id=task_id, owner=request.user)
    services.set_archived(task, False)
    return render(request, "tasks/_archive_list.html", _archive_context(request.user))


@login_required
@require_http_methods(["POST"])
def goal_archive(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, owner=request.user)
    goal.archived = True
    goal.save(update_fields=["archived", "modified"])
    return render(request, "tasks/_goal_list.html",
                  {"goals": Goal.objects.filter(owner=request.user, archived=False)})


@login_required
@require_http_methods(["POST"])
def goal_unarchive(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, owner=request.user)
    goal.archived = False
    goal.save(update_fields=["archived", "modified"])
    return render(request, "tasks/_archive_list.html", _archive_context(request.user))


def _archive_context(user):
    return {
        "tasks": Task.objects.filter(owner=user, archived=True),
        "goals": Goal.objects.filter(owner=user, archived=True),
    }


@login_required
def archive_list(request):
    ctx = _archive_context(request.user)
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_archive_list.html", ctx)
    return render(request, "tasks/archive.html", ctx)


@login_required
@require_http_methods(["POST"])
def archive_clear(request):
    Task.objects.filter(owner=request.user, archived=True).delete()
    Goal.objects.filter(owner=request.user, archived=True).delete()
    return render(request, "tasks/_archive_list.html", _archive_context(request.user))


_TOGGLE_KEYS = {"show_hidden", "quick_add"}


@login_required
@require_http_methods(["POST"])
def toggle_setting(request, key):
    """BR-11/12/14: flip a boolean display setting stored in the session."""
    if key in _TOGGLE_KEYS:
        request.session[key] = not request.session.get(key)
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def set_sort(request):
    """BR-13: choose the task list sort order (stored in the session)."""
    sort = request.POST.get("sort", "priority")
    if sort in SORT_ORDERS:
        request.session["sort"] = sort
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
@require_http_methods(["POST"])
def set_group(request):
    """BR-17: choose how the task list is grouped (stored in the session)."""
    group_by = request.POST.get("group_by", "none")
    if group_by in ("none", "goal", "context"):
        request.session["group_by"] = group_by
    ctx = _board_context(request, request.GET.get("h", "TODAY"))
    return render(request, "tasks/_task_list.html", ctx)


@login_required
def completed_list(request):
    """BR-10: tasks marked done (not archived), newest completion first."""
    tasks = (Task.objects.filter(owner=request.user, archived=False, done=True)
             .order_by("-completion_date"))
    ctx = {"tasks": tasks}
    if request.headers.get("HX-Request"):
        return render(request, "tasks/_completed_list.html", ctx)
    return render(request, "tasks/completed.html", ctx)


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


# ---- Goal templates (BR-18) ----

@login_required
def template_list(request):
    """Catalog: published templates + the user's own drafts."""
    templates = (GoalTemplate.objects.filter(Q(published=True) | Q(owner=request.user))
                 .prefetch_related("milestones__key_results", "task_templates"))
    return render(request, "tasks/templates.html", {"templates": templates})


@login_required
@require_http_methods(["POST"])
def template_create_goal(request, template_id):
    template = get_object_or_404(
        GoalTemplate, Q(published=True) | Q(owner=request.user), id=template_id)
    d = parse_date(request.POST.get("start_date") or "")
    start_dt = timezone.make_aware(datetime(d.year, d.month, d.day)) if d else timezone.now()
    services.create_goal_from_template(template, request.user, start_dt)
    return redirect(reverse("goal_list"))


# ---- Goals ----

@login_required
def goal_list(request):
    # Feature catalog #10: "мои" vs "общие" goals (shared flag).
    scope = request.GET.get("scope", "mine")
    goals = Goal.objects.filter(owner=request.user, archived=False)
    if scope == "shared":
        goals = goals.filter(shared=True)
    ctx = {"goals": goals, "scope": scope}
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
