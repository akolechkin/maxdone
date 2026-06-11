"""CRUD + horizon move + hide-state tests (working-app guarantees)."""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from tasks.models import (Task, Goal, Context, GoalTemplate, MilestoneTemplate,
                          TaskTemplate, KeyResult)


class TaskCrud(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_create_task(self):
        r = self.client.post(reverse("task_create") + "?h=TODAY",
                             {"title": "Новая", "task_type": Task.Horizon.TODAY})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Task.objects.filter(title="Новая", owner=self.user).exists())

    def test_create_sets_priority(self):  # BR-4 wired into create
        self.client.post(reverse("task_create"), {"title": "a", "task_type": Task.Horizon.TODAY})
        self.client.post(reverse("task_create"), {"title": "b", "task_type": Task.Horizon.TODAY})
        ps = sorted(Task.objects.values_list("priority", flat=True))
        self.assertEqual(ps, [1.0, 2.0])

    def test_hide_until_future_sets_hidden(self):  # BR-1 on save; hide_until is a date picker
        future = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        self.client.post(reverse("task_create"),
                        {"title": "h", "task_type": Task.Horizon.TODAY, "hide_until_date": future})
        t = Task.objects.get(title="h")
        self.assertEqual(t.state, Task.State.HIDDEN)

    def test_due_date_accepts_date_only(self):  # gap #1: single date picker (YYYY-MM-DD)
        r = self.client.post(reverse("task_create"),
                             {"title": "due", "task_type": Task.Horizon.TODAY, "due_date": "2026-06-20"})
        self.assertEqual(r.status_code, 200)
        t = Task.objects.get(title="due")
        self.assertIsNotNone(t.due_date)
        self.assertEqual((t.due_date.year, t.due_date.month, t.due_date.day), (2026, 6, 20))

    def test_due_date_can_be_cleared(self):  # gap #1: clear button submits empty -> None
        t = Task.objects.create(owner=self.user, title="c", task_type=Task.Horizon.TODAY,
                                due_date=timezone.now())
        r = self.client.post(reverse("task_update", args=[t.id]),
                             {"title": "c", "task_type": Task.Horizon.TODAY, "due_date": ""})
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertIsNone(t.due_date)

    def test_start_date_not_in_task_form(self):  # gap #1: start_date removed from editing flow
        from tasks.forms import TaskForm
        self.assertNotIn("start_date", TaskForm(user=self.user).fields)

    def test_move_horizon(self):  # feature catalog #1 / BR-10: move re-dates the task
        from tasks import services
        t = Task.objects.create(owner=self.user, title="m", due_date=timezone.now())
        self.client.post(reverse("task_move", args=[t.id, "LATER"]))
        t.refresh_from_db()
        self.assertEqual(services.horizon_for(t.due_date), Task.Horizon.LATER)

    def test_delete(self):
        t = Task.objects.create(owner=self.user, title="d", task_type=Task.Horizon.TODAY)
        self.client.post(reverse("task_delete", args=[t.id]))
        self.assertFalse(Task.objects.filter(id=t.id).exists())

    def test_cannot_touch_other_users_task(self):  # BR-6
        other = User.objects.create_user("o", password="p")
        t = Task.objects.create(owner=other, title="secret", task_type=Task.Horizon.TODAY)
        r = self.client.post(reverse("task_delete", args=[t.id]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Task.objects.filter(id=t.id).exists())


class Recurrence(TestCase):
    """BR-5: recur_rule is assembled by the picker; server validates RRULE syntax."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_valid_rrule_is_stored(self):
        r = self.client.post(reverse("task_create"),
                             {"title": "rec", "task_type": Task.Horizon.TODAY,
                              "recur_rule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE"})
        self.assertEqual(r.status_code, 200)
        t = Task.objects.get(title="rec")
        self.assertEqual(t.recur_rule, "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE")

    def test_empty_rrule_allowed(self):
        r = self.client.post(reverse("task_create"),
                             {"title": "norec", "task_type": Task.Horizon.TODAY, "recur_rule": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Task.objects.get(title="norec").recur_rule, "")

    def test_invalid_rrule_rejected(self):
        r = self.client.post(reverse("task_create"),
                             {"title": "bad", "task_type": Task.Horizon.TODAY,
                              "recur_rule": "totally invalid"})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(Task.objects.filter(title="bad").exists())

    def test_rrule_validator_subset(self):
        from tasks.services import validate_rrule
        for ok in ["", "FREQ=DAILY", "FREQ=MONTHLY;BYMONTHDAY=15",
                   "FREQ=MONTHLY;BYDAY=2MO", "FREQ=YEARLY;COUNT=5",
                   "FREQ=WEEKLY;UNTIL=20261231"]:
            self.assertTrue(validate_rrule(ok), ok)
        for bad in ["WEEKLY", "FREQ=HOURLY", "FREQ=WEEKLY;INTERVAL=0",
                    "FREQ=WEEKLY;BYDAY=XX", "FREQ=WEEKLY;FOO=1", "INTERVAL=2"]:
            self.assertFalse(validate_rrule(bad), bad)


class Subtasks(TestCase):
    """BR-7: subtask hierarchy + subtree hide/list behaviour (view layer)."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_add_subtask_inherits_parent(self):
        from tasks import services
        due = timezone.now() + timedelta(days=30)  # LATER
        parent = Task.objects.create(owner=self.user, title="P", due_date=due)
        r = self.client.post(reverse("subtask_add", args=[parent.id]), {"title": "child"})
        self.assertEqual(r.status_code, 200)
        child = Task.objects.get(title="child")
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(child.owner, self.user)
        self.assertEqual(child.due_date, parent.due_date)
        self.assertEqual(services.horizon_for(child.due_date), Task.Horizon.LATER)
        self.assertGreater(child.priority, 0.0)

    def test_board_lists_root_only(self):
        parent = Task.objects.create(owner=self.user, title="ParentRoot", due_date=timezone.now())
        Task.objects.create(owner=self.user, title="ChildHidden", parent=parent, due_date=timezone.now())
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "ParentRoot")
        self.assertNotContains(r, "ChildHidden")

    def test_hide_parent_hides_subtree(self):  # CAN_HIDE_DESCENDANTS
        parent = Task.objects.create(owner=self.user, title="HP", task_type=Task.Horizon.TODAY)
        child = Task.objects.create(owner=self.user, title="HC", parent=parent, task_type=Task.Horizon.TODAY)
        future = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        self.client.post(reverse("task_update", args=[parent.id]),
                         {"title": "HP", "task_type": Task.Horizon.TODAY, "hide_until_date": future})
        child.refresh_from_db()
        self.assertEqual(child.state, Task.State.HIDDEN)
        self.assertIsNotNone(child.hide_until_date)

    def test_unhide_parent_unhides_subtree(self):
        parent = Task.objects.create(owner=self.user, title="UP", task_type=Task.Horizon.TODAY,
                                     state=Task.State.HIDDEN, hide_until_date=timezone.now() + timedelta(days=3))
        child = Task.objects.create(owner=self.user, title="UC", parent=parent, task_type=Task.Horizon.TODAY,
                                    state=Task.State.HIDDEN, hide_until_date=timezone.now() + timedelta(days=3))
        self.client.post(reverse("task_update", args=[parent.id]),
                         {"title": "UP", "task_type": Task.Horizon.TODAY, "hide_until_date": ""})
        child.refresh_from_db()
        self.assertEqual(child.state, Task.State.ACTIVE)

    def test_delete_parent_cascades(self):
        parent = Task.objects.create(owner=self.user, title="DP", task_type=Task.Horizon.TODAY)
        child = Task.objects.create(owner=self.user, title="DC", parent=parent, task_type=Task.Horizon.TODAY)
        self.client.post(reverse("task_delete", args=[parent.id]))
        self.assertFalse(Task.objects.filter(id=child.id).exists())


class Projects(TestCase):
    """BR-8: is_project flag is editable and surfaced in the UI."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_create_as_project(self):
        self.client.post(reverse("task_create"),
                         {"title": "Proj", "task_type": Task.Horizon.TODAY, "is_project": "on"})
        self.assertTrue(Task.objects.get(title="Proj").is_project)

    def test_default_not_project(self):
        self.client.post(reverse("task_create"), {"title": "Plain", "task_type": Task.Horizon.TODAY})
        self.assertFalse(Task.objects.get(title="Plain").is_project)

    def test_update_clears_project_flag(self):
        t = Task.objects.create(owner=self.user, title="P2", task_type=Task.Horizon.TODAY, is_project=True)
        self.client.post(reverse("task_update", args=[t.id]),
                         {"title": "P2", "task_type": Task.Horizon.TODAY})  # checkbox unchecked -> absent
        t.refresh_from_db()
        self.assertFalse(t.is_project)

    def test_project_marked_in_list(self):
        Task.objects.create(owner=self.user, title="ProjRow", due_date=timezone.now(), is_project=True)
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "проект")


class GoalContextCrud(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_goal_create_and_delete(self):
        self.client.post(reverse("goal_create"),
                         {"title": "G", "goal_type": "PRIVATE", "status": "ACTIVE"})
        g = Goal.objects.get(title="G")
        self.assertEqual(g.owner, self.user)
        self.client.post(reverse("goal_delete", args=[g.id]))
        self.assertFalse(Goal.objects.filter(id=g.id).exists())

    def test_goal_status_is_a_choice(self):  # gap #5: status picked from a fixed set
        self.client.post(reverse("goal_create"),
                         {"title": "GS", "goal_type": "PRIVATE", "status": "PAUSED"})
        self.assertEqual(Goal.objects.get(title="GS").status, Goal.Status.PAUSED)

    def test_goal_invalid_status_rejected(self):
        r = self.client.post(reverse("goal_create"),
                             {"title": "GBad", "goal_type": "PRIVATE", "status": "whatever"})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(Goal.objects.filter(title="GBad").exists())

    def test_goal_status_change_via_update(self):  # CHANGE_GOAL_STATUS
        g = Goal.objects.create(owner=self.user, title="GC", goal_type="PRIVATE", status=Goal.Status.ACTIVE)
        self.client.post(reverse("goal_update", args=[g.id]),
                         {"title": "GC", "goal_type": "PRIVATE", "status": "ACHIEVED"})
        g.refresh_from_db()
        self.assertEqual(g.status, Goal.Status.ACHIEVED)

    def test_context_create(self):
        self.client.post(reverse("context_create"), {"title": "дома"})
        self.assertTrue(Context.objects.filter(title="дома", owner=self.user).exists())


class Archive(TestCase):
    """BR-9: archive is soft-hide; archive screen + restore + clear."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_archive_task_removes_from_board(self):
        t = Task.objects.create(owner=self.user, title="ArcMe", due_date=timezone.now())
        self.client.post(reverse("task_archive", args=[t.id]))
        t.refresh_from_db()
        self.assertTrue(t.archived)
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "ArcMe")

    def test_archive_propagates_to_subtree(self):
        p = Task.objects.create(owner=self.user, title="AP", task_type=Task.Horizon.TODAY)
        c = Task.objects.create(owner=self.user, title="AC", parent=p, task_type=Task.Horizon.TODAY)
        self.client.post(reverse("task_archive", args=[p.id]))
        c.refresh_from_db()
        self.assertTrue(c.archived)

    def test_unarchive_restores(self):
        t = Task.objects.create(owner=self.user, title="Un", task_type=Task.Horizon.TODAY, archived=True)
        self.client.post(reverse("task_unarchive", args=[t.id]))
        t.refresh_from_db()
        self.assertFalse(t.archived)

    def test_archive_screen_lists_archived(self):
        Task.objects.create(owner=self.user, title="ArcShown", task_type=Task.Horizon.TODAY, archived=True)
        Goal.objects.create(owner=self.user, title="GoalArc", goal_type="PRIVATE",
                            status=Goal.Status.ACTIVE, archived=True)
        r = self.client.get(reverse("archive_list"))
        self.assertContains(r, "ArcShown")
        self.assertContains(r, "GoalArc")

    def test_archive_clear_deletes_permanently(self):
        Task.objects.create(owner=self.user, title="Doomed", task_type=Task.Horizon.TODAY, archived=True)
        Goal.objects.create(owner=self.user, title="DoomedG", goal_type="PRIVATE",
                            status=Goal.Status.ACTIVE, archived=True)
        active = Task.objects.create(owner=self.user, title="Kept", task_type=Task.Horizon.TODAY)
        self.client.post(reverse("archive_clear"))
        self.assertFalse(Task.objects.filter(title="Doomed").exists())
        self.assertFalse(Goal.objects.filter(title="DoomedG").exists())
        self.assertTrue(Task.objects.filter(id=active.id).exists())

    def test_goal_archive_and_restore(self):
        g = Goal.objects.create(owner=self.user, title="GA", goal_type="PRIVATE", status=Goal.Status.ACTIVE)
        self.client.post(reverse("goal_archive", args=[g.id]))
        g.refresh_from_db(); self.assertTrue(g.archived)
        r = self.client.get(reverse("goal_list"))
        self.assertNotContains(r, "GA")
        self.client.post(reverse("goal_unarchive", args=[g.id]))
        g.refresh_from_db(); self.assertFalse(g.archived)


class TaskCopy(TestCase):
    """Feature catalog #7: duplicate task with checklist."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_copy_duplicates_with_checklist(self):
        from tasks import services
        due = timezone.now() + timedelta(days=30)  # LATER
        t = Task.objects.create(owner=self.user, title="Orig", due_date=due)
        t.checklist.create(title="step1", sort_order=0)
        t.checklist.create(title="step2", sort_order=1, done=True)
        self.client.post(reverse("task_copy", args=[t.id]))
        copy = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertTrue(copy.title.startswith("Orig"))
        self.assertEqual(copy.due_date, t.due_date)
        self.assertEqual(services.horizon_for(copy.due_date), Task.Horizon.LATER)
        self.assertEqual(copy.checklist.count(), 2)
        self.assertNotEqual(copy.id, t.id)

    def test_copy_is_not_done(self):
        t = Task.objects.create(owner=self.user, title="D", task_type=Task.Horizon.TODAY,
                                done=True, completion_date=timezone.now())
        self.client.post(reverse("task_copy", args=[t.id]))
        copy = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertFalse(copy.done)
        self.assertIsNone(copy.completion_date)


class Sorting(TestCase):
    """BR-13: task list sort orders."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_sort_by_due_orders_ascending(self):
        now = timezone.now()  # all far-future -> same horizon (LATER), distinct due dates
        Task.objects.create(owner=self.user, title="Late", due_date=now + timedelta(days=50))
        Task.objects.create(owner=self.user, title="Soon", due_date=now + timedelta(days=30))
        Task.objects.create(owner=self.user, title="Mid", due_date=now + timedelta(days=40))
        self.client.post(reverse("set_sort"), {"sort": "due"})
        html = self.client.get(reverse("board") + "?h=LATER").content.decode()
        self.assertLess(html.index("Soon"), html.index("Mid"))
        self.assertLess(html.index("Mid"), html.index("Late"))

    def test_invalid_sort_ignored(self):
        self.client.post(reverse("set_sort"), {"sort": "bogus"})
        self.assertNotEqual(self.client.session.get("sort"), "bogus")


class QuickAdd(TestCase):
    """BR-14: quick-add row toggle."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_quick_add_hidden_by_default(self):
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "Быстро добавить")

    def test_toggle_shows_quick_add_row(self):
        self.client.post(reverse("toggle_setting", args=["quick_add"]))
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "Быстро добавить")

    def test_quick_add_creates_task_in_current_horizon(self):
        from tasks import services
        # quick-add posts set_horizon; the task is dated into that column (BR-10)
        self.client.post(reverse("task_create") + "?h=LATER",
                         {"title": "Quick", "set_horizon": "LATER"})
        t = Task.objects.get(title="Quick")
        self.assertIsNotNone(t.due_date)
        self.assertEqual(services.horizon_for(t.due_date), Task.Horizon.LATER)


class TaskPreferences(TestCase):
    """BR-15: remember last goal/context/is_project for the next new task."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_new_task_prefills_last_goal_and_context(self):
        g = Goal.objects.create(owner=self.user, title="G", goal_type="PRIVATE", status=Goal.Status.ACTIVE)
        c = Context.objects.create(owner=self.user, title="ctx")
        self.client.post(reverse("task_create"),
                         {"title": "x", "task_type": Task.Horizon.TODAY, "goal": g.id, "context": c.id})
        r = self.client.get(reverse("task_new"))
        self.assertContains(r, f'{g.id}" selected')
        self.assertContains(r, f'{c.id}" selected')

    def test_new_task_prefills_is_project(self):
        self.client.post(reverse("task_create"),
                         {"title": "p", "task_type": Task.Horizon.TODAY, "is_project": "on"})
        r = self.client.get(reverse("task_new"))
        self.assertContains(r, "checked")


class GoalPause(TestCase):
    """BR-16: a paused goal hides its tasks from the board."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.goal = Goal.objects.create(owner=self.user, title="G", goal_type="PRIVATE",
                                        status=Goal.Status.ACTIVE)
        Task.objects.create(owner=self.user, title="GoalTask", due_date=timezone.now(), goal=self.goal)

    def test_active_goal_tasks_visible(self):
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "GoalTask")

    def test_paused_goal_hides_tasks(self):
        self.client.post(reverse("goal_update", args=[self.goal.id]),
                         {"title": "G", "goal_type": "PRIVATE", "status": "PAUSED"})
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "GoalTask")

    def test_show_hidden_reveals_paused_goal_tasks(self):
        self.goal.status = Goal.Status.PAUSED
        self.goal.save()
        self.client.post(reverse("toggle_setting", args=["show_hidden"]))
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "GoalTask")

    def test_unpause_restores_tasks(self):
        self.goal.status = Goal.Status.PAUSED
        self.goal.save()
        self.client.post(reverse("goal_update", args=[self.goal.id]),
                         {"title": "G", "goal_type": "PRIVATE", "status": "ACTIVE"})
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "GoalTask")


class Categories(TestCase):
    """BR-17: grouping view (categories) by goal/context."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_group_by_goal_renders_headers(self):
        g = Goal.objects.create(owner=self.user, title="MyGoal", goal_type="PRIVATE", status=Goal.Status.ACTIVE)
        Task.objects.create(owner=self.user, title="WithGoal", due_date=timezone.now(), goal=g)
        Task.objects.create(owner=self.user, title="NoGoal", due_date=timezone.now())
        self.client.post(reverse("set_group"), {"group_by": "goal"})
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "MyGoal")
        self.assertContains(r, "Без цели")
        self.assertContains(r, "WithGoal")
        self.assertContains(r, "NoGoal")

    def test_invalid_group_ignored(self):
        self.client.post(reverse("set_group"), {"group_by": "bogus"})
        self.assertNotEqual(self.client.session.get("group_by"), "bogus")


class HorizonCounters(TestCase):
    """BR-11: sidebar counters refresh out-of-band on mutating HTMX responses."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def _hx(self, method, url, data=None):
        return getattr(self.client, method)(url, data or {}, HTTP_HX_REQUEST="true")

    def test_create_emits_oob_count(self):
        r = self._hx("post", reverse("task_create") + "?h=TODAY",
                     {"title": "T", "set_horizon": "TODAY"})
        self.assertContains(r, 'id="count-TODAY"')
        self.assertContains(r, 'hx-swap-oob="true"')

    def test_full_page_has_no_oob_spans(self):
        # non-HX board render must NOT contain inert OOB spans inside the list
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, 'hx-swap-oob')

    def test_toggle_done_refreshes_counts(self):
        t = Task.objects.create(owner=self.user, title="D", due_date=timezone.now())
        r = self._hx("post", reverse("toggle_done", args=[t.id]))
        self.assertContains(r, 'id="count-TODAY"')
        self.assertContains(r, 'hx-swap-oob="true"')


class Completed(TestCase):
    """BR-10: completed tasks screen."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_completed_screen_lists_done_only(self):
        Task.objects.create(owner=self.user, title="WasDone", task_type=Task.Horizon.TODAY,
                            done=True, completion_date=timezone.now())
        Task.objects.create(owner=self.user, title="StillActive", task_type=Task.Horizon.TODAY)
        r = self.client.get(reverse("completed_list"))
        self.assertContains(r, "WasDone")
        self.assertNotContains(r, "StillActive")


class ShowHidden(TestCase):
    """BR-12: show-hidden toggle."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.hidden = Task.objects.create(
            owner=self.user, title="HiddenOne", due_date=timezone.now(),
            state=Task.State.HIDDEN, hide_until_date=timezone.now() + timedelta(days=3))

    def test_hidden_excluded_by_default(self):
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "HiddenOne")

    def test_toggle_reveals_hidden(self):
        self.client.post(reverse("toggle_setting", args=["show_hidden"]))
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "HiddenOne")

    def test_toggle_off_again_hides(self):
        self.client.post(reverse("toggle_setting", args=["show_hidden"]))
        self.client.post(reverse("toggle_setting", args=["show_hidden"]))
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "HiddenOne")


class GoalTemplates(TestCase):
    """BR-18: goal templates catalog + create-from-template (milestones, key results)."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.tpl = GoalTemplate.objects.create(owner=self.user, title="Launch", published=True)
        self.m = MilestoneTemplate.objects.create(template=self.tpl, title="Prep", sort_order=0)
        TaskTemplate.objects.create(template=self.tpl, milestone=self.m, title="Step A", offset_days=0)
        TaskTemplate.objects.create(template=self.tpl, milestone=self.m, title="Step B", offset_days=10)
        KeyResult.objects.create(milestone=self.m, title="KR1", kind=KeyResult.Kind.SUM_RESULT, planned=50)

    def test_catalog_lists_published_template(self):
        r = self.client.get(reverse("template_list"))
        self.assertContains(r, "Launch")
        self.assertContains(r, "Prep")
        self.assertContains(r, "KR1")

    def test_create_goal_from_template_expands(self):
        from datetime import date
        r = self.client.post(reverse("template_create_goal", args=[self.tpl.id]),
                             {"start_date": "2026-07-01"})
        self.assertEqual(r.status_code, 302)
        goal = Goal.objects.get(title="Launch", owner=self.user)
        self.assertEqual(goal.status, Goal.Status.ACTIVE)
        # milestone -> project task
        ms_task = Task.objects.get(title="Prep", owner=self.user)
        self.assertTrue(ms_task.is_project)
        self.assertEqual(ms_task.goal_id, goal.id)
        # task templates -> subtasks of the milestone with relative due dates
        a = Task.objects.get(title="Step A", owner=self.user)
        b = Task.objects.get(title="Step B", owner=self.user)
        self.assertEqual(a.parent_id, ms_task.id)
        self.assertEqual((a.due_date.year, a.due_date.month, a.due_date.day), (2026, 7, 1))
        self.assertEqual((b.due_date.year, b.due_date.month, b.due_date.day), (2026, 7, 11))

    def test_other_users_draft_not_listed(self):
        other = User.objects.create_user("o", password="p")
        GoalTemplate.objects.create(owner=other, title="SecretDraft", published=False)
        r = self.client.get(reverse("template_list"))
        self.assertNotContains(r, "SecretDraft")


class Registration(TestCase):
    """Feature catalog #16: self-service signup."""
    def test_signup_creates_and_logs_in(self):
        c = Client()
        r = c.post(reverse("signup"),
                   {"username": "newbie", "password1": "Str0ngPass!23", "password2": "Str0ngPass!23"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username="newbie").exists())
        self.assertEqual(c.get(reverse("board")).status_code, 200)  # logged in

    def test_signup_rejects_mismatch(self):
        c = Client()
        c.post(reverse("signup"), {"username": "x", "password1": "abc12345!", "password2": "different9!"})
        self.assertFalse(User.objects.filter(username="x").exists())


class GoalIconAndSharing(TestCase):
    """Feature catalog #10: goal icon + мои/общие (shared)."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_icon_and_shared_saved(self):
        self.client.post(reverse("goal_create"),
                         {"title": "G", "goal_type": "PRIVATE", "status": "ACTIVE",
                          "icon": "🎯", "shared": "on"})
        g = Goal.objects.get(title="G")
        self.assertEqual(g.icon, "🎯")
        self.assertTrue(g.shared)

    def test_shared_scope_filters(self):
        Goal.objects.create(owner=self.user, title="Mine", goal_type="PRIVATE", status=Goal.Status.ACTIVE)
        Goal.objects.create(owner=self.user, title="Common", goal_type="PRIVATE",
                            status=Goal.Status.ACTIVE, shared=True)
        r = self.client.get(reverse("goal_list") + "?scope=shared")
        self.assertContains(r, "Common")
        self.assertNotContains(r, "Mine")


class Search(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_search_finds_task(self):
        Task.objects.create(owner=self.user, title="купить молоко", task_type=Task.Horizon.TODAY)
        r = self.client.get(reverse("search") + "?q=молоко")
        self.assertContains(r, "молоко")


class Reorder(TestCase):
    """spec/06 next-step: drag&drop reorder sets fractional priority (BR-4)."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_reorder_between_neighbors(self):
        a = Task.objects.create(owner=self.user, title="a", priority=1.0, due_date=timezone.now())
        b = Task.objects.create(owner=self.user, title="b", priority=3.0, due_date=timezone.now())
        c = Task.objects.create(owner=self.user, title="c", priority=9.0, due_date=timezone.now())
        r = self.client.post(reverse("task_reorder"), {"id": c.id, "before": a.id, "after": b.id})
        self.assertEqual(r.status_code, 204)
        c.refresh_from_db()
        self.assertEqual(c.priority, 2.0)  # midpoint of 1.0 and 3.0

    def test_reorder_to_top(self):
        a = Task.objects.create(owner=self.user, title="a", priority=5.0, due_date=timezone.now())
        b = Task.objects.create(owner=self.user, title="b", priority=6.0, due_date=timezone.now())
        self.client.post(reverse("task_reorder"), {"id": b.id, "before": "", "after": a.id})
        b.refresh_from_db()
        self.assertEqual(b.priority, 4.0)  # after.priority - 1.0

    def test_reorder_owner_isolation(self):
        other = User.objects.create_user("o", password="p")
        t = Task.objects.create(owner=other, title="x", due_date=timezone.now())
        r = self.client.post(reverse("task_reorder"), {"id": t.id, "before": "", "after": ""})
        self.assertEqual(r.status_code, 404)


class RecurGroup(TestCase):
    """spec/06 B: collapse overdue recurring instances + mark-all."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        now = timezone.now()
        self.root = Task.objects.create(owner=self.user, title="Полить",
                                        due_date=now - timedelta(days=3), recur_rule="FREQ=DAILY")
        self.inst = Task.objects.create(owner=self.user, title="Полить",
                                        due_date=now - timedelta(days=2), recur_rule="FREQ=DAILY",
                                        recur_parent_id=self.root.id)

    def test_overdue_series_is_collapsed(self):
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "просрочено")
        self.assertContains(r, "отметить все")

    def test_mark_all_completes_the_group(self):
        self.client.post(reverse("recur_group_done") + "?h=TODAY", {"series": self.root.id})
        self.root.refresh_from_db(); self.inst.refresh_from_db()
        self.assertTrue(self.root.done)
        self.assertTrue(self.inst.done)

    def test_single_overdue_not_collapsed(self):
        self.inst.delete()  # leave just one overdue instance in the series
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertNotContains(r, "просрочено")


class TemplateLock(TestCase):
    """BLOCKED_BY_GOAL_TEMPLATE: tasks created from a goal template are read-only."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_create_from_template_marks_locked(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="T", published=True)
        m = MilestoneTemplate.objects.create(template=tpl, title="M", sort_order=0)
        TaskTemplate.objects.create(template=tpl, milestone=m, title="Step", offset_days=0)
        self.client.post(reverse("template_create_goal", args=[tpl.id]), {"start_date": "2026-07-01"})
        self.assertTrue(Task.objects.get(title="M", owner=self.user).from_template)
        self.assertTrue(Task.objects.get(title="Step", owner=self.user).from_template)

    def test_update_blocked(self):
        t = Task.objects.create(owner=self.user, title="L", from_template=True, due_date=timezone.now())
        r = self.client.post(reverse("task_update", args=[t.id]), {"title": "changed"})
        self.assertEqual(r.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.title, "L")

    def test_editor_shows_lock_and_hides_save(self):
        t = Task.objects.create(owner=self.user, title="L", from_template=True, due_date=timezone.now())
        r = self.client.get(reverse("task_detail", args=[t.id]))
        self.assertContains(r, "заблокировано")
        self.assertNotContains(r, "Сохранить")

    def test_normal_task_still_editable(self):
        t = Task.objects.create(owner=self.user, title="N", due_date=timezone.now())
        r = self.client.post(reverse("task_update", args=[t.id]), {"title": "renamed"})
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.title, "renamed")


class EditorActionIcons(TestCase):
    """Editor header shows duplicate/archive/delete/close as icon buttons (wired to the
    existing task_copy/task_archive/task_delete endpoints)."""
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_editor_renders_action_icons(self):
        t = Task.objects.create(owner=self.user, title="E", due_date=timezone.now())
        r = self.client.get(reverse("task_detail", args=[t.id]))
        for title in ("Дублировать", "В архив", "Удалить", "Закрыть"):
            self.assertContains(r, 'title="%s"' % title)
        self.assertContains(r, "<svg")
        self.assertContains(r, reverse("task_copy", args=[t.id]))
        self.assertContains(r, reverse("task_archive", args=[t.id]))
