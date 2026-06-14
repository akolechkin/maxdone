"""BR-38 — final box/date model: the box (task_type) is stored and manual; date and box are
independent; the ONLY automation is the narrow one-way "pull forward" for LATER/WEEK tasks.
"""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from tasks.models import Task
from tasks import services


class PullForward(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def _mk(self, box, due):
        return Task.objects.create(owner=self.user, title="t", task_type=box, due_date=due)

    def test_later_with_today_date_pulled_to_today(self):
        t = self._mk(Task.Horizon.LATER, timezone.now())
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.TODAY)

    def test_later_with_week_date_pulled_forward(self):
        # due end-of-this-week → pulled out of LATER (to WEEK, or TODAY if today is Sunday)
        t = self._mk(Task.Horizon.LATER, services._week_eod())
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertIn(t.task_type, (Task.Horizon.WEEK, Task.Horizon.TODAY))
        self.assertNotEqual(t.task_type, Task.Horizon.LATER)

    def test_far_future_not_moved(self):  # never backward / no move when date still says LATER
        t = self._mk(Task.Horizon.WEEK, timezone.now() + timedelta(days=40))
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.WEEK)

    def test_today_box_never_auto_moved(self):
        t = self._mk(Task.Horizon.TODAY, timezone.now() + timedelta(days=40))
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.TODAY)

    def test_past_due_left_in_place(self):
        t = self._mk(Task.Horizon.LATER, timezone.now() - timedelta(days=2))
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.LATER)

    def test_dateless_untouched(self):
        t = Task.objects.create(owner=self.user, title="t", task_type=Task.Horizon.LATER)
        services.pull_forward(self.user)
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.LATER)

    def test_board_load_triggers_pull_forward(self):
        c = Client(); c.login(username="u", password="p")
        t = self._mk(Task.Horizon.LATER, timezone.now())
        c.get(reverse("board"))
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.TODAY)


class ManualPlacement(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client(); self.client.login(username="u", password="p")

    def test_create_in_tab_without_date_stays_dateless_in_box(self):  # BR-36
        self.client.post(reverse("task_create") + "?h=WEEK",
                         {"title": "W", "set_horizon": "WEEK"})
        t = Task.objects.get(title="W")
        self.assertIsNone(t.due_date)
        self.assertEqual(t.task_type, Task.Horizon.WEEK)

    def test_create_with_date_takes_box_from_date(self):  # BR-38
        self.client.post(reverse("task_create") + "?h=INBOX",
                         {"title": "D", "due_date": "2099-01-01"})
        t = Task.objects.get(title="D")
        self.assertEqual(t.task_type, Task.Horizon.LATER)  # far date → LATER, ignoring the tab

    def test_move_to_week_sets_box_keeps_date(self):  # BR-37 / BR-38
        t = Task.objects.create(owner=self.user, title="m", task_type=Task.Horizon.TODAY,
                                due_date=timezone.now() + timedelta(days=40))
        due_before = t.due_date
        self.client.post(reverse("task_move", args=[t.id, "WEEK"]))
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.WEEK)
        self.assertEqual(t.due_date, due_before)

    def test_move_to_inbox_clears_date(self):  # BR-38 INBOX special case
        t = Task.objects.create(owner=self.user, title="i", task_type=Task.Horizon.TODAY,
                                due_date=timezone.now())
        self.client.post(reverse("task_to_inbox", args=[t.id]))
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.INBOX)
        self.assertIsNone(t.due_date)
