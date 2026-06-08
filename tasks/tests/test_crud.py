"""CRUD + horizon move + hide-state tests (working-app guarantees)."""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from tasks.models import Task, Goal, Context


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

    def test_move_horizon(self):  # feature catalog #1
        t = Task.objects.create(owner=self.user, title="m", task_type=Task.Horizon.TODAY)
        self.client.post(reverse("task_move", args=[t.id, "LATER"]))
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.LATER)

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
        parent = Task.objects.create(owner=self.user, title="P", task_type=Task.Horizon.LATER)
        r = self.client.post(reverse("subtask_add", args=[parent.id]), {"title": "child"})
        self.assertEqual(r.status_code, 200)
        child = Task.objects.get(title="child")
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(child.owner, self.user)
        self.assertEqual(child.task_type, Task.Horizon.LATER)
        self.assertGreater(child.priority, 0.0)

    def test_board_lists_root_only(self):
        parent = Task.objects.create(owner=self.user, title="ParentRoot", task_type=Task.Horizon.TODAY)
        Task.objects.create(owner=self.user, title="ChildHidden", parent=parent, task_type=Task.Horizon.TODAY)
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
        Task.objects.create(owner=self.user, title="ProjRow", task_type=Task.Horizon.TODAY, is_project=True)
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "проект")


class GoalContextCrud(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_goal_create_and_delete(self):
        self.client.post(reverse("goal_create"), {"title": "G", "goal_type": "PRIVATE"})
        g = Goal.objects.get(title="G")
        self.assertEqual(g.owner, self.user)
        self.client.post(reverse("goal_delete", args=[g.id]))
        self.assertFalse(Goal.objects.filter(id=g.id).exists())

    def test_context_create(self):
        self.client.post(reverse("context_create"), {"title": "дома"})
        self.assertTrue(Context.objects.filter(title="дома", owner=self.user).exists())


class Search(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_search_finds_task(self):
        Task.objects.create(owner=self.user, title="купить молоко", task_type=Task.Horizon.TODAY)
        r = self.client.get(reverse("search") + "?q=молоко")
        self.assertContains(r, "молоко")
