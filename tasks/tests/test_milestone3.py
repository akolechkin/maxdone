"""
Поведенческие тесты Milestone 3 (spec/07_milestone3_status.md), BR-20..BR-25.
Гибридная модель горизонта, "в инбокс", подсветка просрочки, toggle подзадач,
якорение повтора без даты, "спящий" повтор в инбоксе.
"""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from tasks.models import Task
from tasks import services
from tasks.templatetags.mx import is_overdue


class HybridHorizon(TestCase):
    """BR-38: the box (task_type) is STORED — due_date neither derives nor overrides it."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_save_preserves_dateless_box(self):
        # a dateless task is NOT flattened to INBOX — it keeps the box it was given
        t = Task.objects.create(owner=self.user, title="t", task_type=Task.Horizon.LATER)
        t.refresh_from_db()
        self.assertIsNone(t.due_date)
        self.assertEqual(t.task_type, Task.Horizon.LATER)
        self.assertEqual(t.horizon, Task.Horizon.LATER)

    def test_dateless_task_appears_in_its_box_not_inbox(self):
        Task.objects.create(owner=self.user, title="WeekBox", task_type=Task.Horizon.WEEK)
        qs = Task.objects.filter(owner=self.user)
        self.assertEqual(services.horizon_filter(qs, "WEEK").count(), 1)
        self.assertEqual(services.horizon_filter(qs, "INBOX").count(), 0)

    def test_dated_task_keeps_stored_box(self):  # BR-38: stored box wins; date never overrides
        # task_type says LATER and the due_date is today — under BR-38 the box stays LATER
        t = Task.objects.create(owner=self.user, title="d", task_type=Task.Horizon.LATER,
                                due_date=timezone.now())
        t.refresh_from_db()
        self.assertEqual(t.task_type, Task.Horizon.LATER)  # NOT re-derived from due_date
        qs = Task.objects.filter(owner=self.user)
        self.assertEqual(services.horizon_filter(qs, "LATER").count(), 1)
        self.assertEqual(services.horizon_filter(qs, "TODAY").count(), 0)

    def test_new_dateless_task_lands_in_active_box(self):
        # BR-20 replaces BR-9: a new dateless task takes the VIEWED box, not always INBOX
        self.client.post(reverse("task_create") + "?h=WEEK", {"title": "InWeek"})
        t = Task.objects.get(title="InWeek")
        self.assertIsNone(t.due_date)
        self.assertEqual(t.task_type, Task.Horizon.WEEK)
        r = self.client.get(reverse("board") + "?h=WEEK")
        self.assertContains(r, "InWeek")
        r2 = self.client.get(reverse("board") + "?h=INBOX")
        self.assertNotContains(r2, "InWeek")


class ToInbox(TestCase):
    """BR-21: 'в инбокс' clears the date and sets the box to INBOX (carries subtree)."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_to_inbox_clears_date_and_sets_box(self):
        t = Task.objects.create(owner=self.user, title="T", due_date=timezone.now())
        r = self.client.post(reverse("task_to_inbox", args=[t.id]) + "?h=TODAY")
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertIsNone(t.due_date)
        self.assertEqual(t.task_type, Task.Horizon.INBOX)
        self.assertEqual(t.horizon, Task.Horizon.INBOX)

    def test_to_inbox_carries_subtree(self):
        p = Task.objects.create(owner=self.user, title="P", due_date=timezone.now())
        c = Task.objects.create(owner=self.user, title="C", parent=p, due_date=timezone.now())
        self.client.post(reverse("task_to_inbox", args=[p.id]))
        c.refresh_from_db()
        self.assertIsNone(c.due_date)
        self.assertEqual(c.task_type, Task.Horizon.INBOX)

    def test_to_inbox_editor_has_button(self):
        t = Task.objects.create(owner=self.user, title="E", due_date=timezone.now())
        r = self.client.get(reverse("task_detail", args=[t.id]))
        self.assertContains(r, 'title="В инбокс"')
        self.assertContains(r, reverse("task_to_inbox", args=[t.id]))


class OverdueHighlight(TestCase):
    """BR-22: an overdue (past, not done) due_date is painted red with 🔥."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_is_overdue_filter(self):
        now = timezone.now()
        self.assertTrue(is_overdue(now - timedelta(days=1)))
        self.assertFalse(is_overdue(now + timedelta(days=1)))
        self.assertFalse(is_overdue(None))

    def test_overdue_row_shows_fire(self):
        # an overdue task in the TODAY box: past due_date renders the 🔥 overdue chip
        Task.objects.create(owner=self.user, title="Late", task_type=Task.Horizon.TODAY,
                            due_date=timezone.now() - timedelta(days=2))
        r = self.client.get(reverse("board") + "?h=TODAY")
        self.assertContains(r, "🔥")

    def test_future_row_has_no_fire(self):
        Task.objects.create(owner=self.user, title="Soon", task_type=Task.Horizon.LATER,
                            due_date=timezone.now() + timedelta(days=40))
        r = self.client.get(reverse("board") + "?h=LATER")
        self.assertNotContains(r, "🔥")


class SubtaskToggle(TestCase):
    """BR-23: clicking a subtask toggles done (not delete); delete is a separate action."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.parent = Task.objects.create(owner=self.user, title="P", due_date=timezone.now())
        self.child = Task.objects.create(owner=self.user, title="C", parent=self.parent,
                                         due_date=timezone.now())

    def test_toggle_marks_done_and_keeps_row(self):
        r = self.client.post(reverse("subtask_toggle", args=[self.child.id]))
        self.assertEqual(r.status_code, 200)
        self.child.refresh_from_db()
        self.assertTrue(self.child.done)
        self.assertTrue(Task.objects.filter(id=self.child.id).exists())  # NOT deleted

    def test_toggle_again_undones(self):
        self.client.post(reverse("subtask_toggle", args=[self.child.id]))
        self.client.post(reverse("subtask_toggle", args=[self.child.id]))
        self.child.refresh_from_db()
        self.assertFalse(self.child.done)

    def test_done_subtask_still_listed_struck_through(self):
        services.set_done(self.child, True)
        r = self.client.get(reverse("task_detail", args=[self.parent.id]))
        self.assertContains(r, "line-through")
        self.assertContains(r, "C")  # still rendered, not hidden

    def test_explicit_delete_removes_subtask(self):
        r = self.client.post(reverse("subtask_delete", args=[self.child.id]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Task.objects.filter(id=self.child.id).exists())

    def test_subtask_inherits_parent_box(self):
        # BR-20: a dateless parent's subtask inherits the box, not INBOX
        p = Task.objects.create(owner=self.user, title="DatelessParent", task_type=Task.Horizon.WEEK)
        self.client.post(reverse("subtask_add", args=[p.id]), {"title": "kid"})
        kid = Task.objects.get(title="kid")
        self.assertEqual(kid.task_type, Task.Horizon.WEEK)


class RecurrenceAnchor(TestCase):
    """BR-24: setting a repeat on a dateless task anchors it to the nearest rule date."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_first_occurrence_daily_is_today(self):
        d = services.first_occurrence("FREQ=DAILY")
        today = timezone.localtime(timezone.now()).date()
        self.assertEqual(d.date(), today)

    def test_first_occurrence_weekly_is_a_listed_weekday(self):
        d = services.first_occurrence("FREQ=WEEKLY;BYDAY=TU")
        self.assertEqual(d.weekday(), 1)  # Tuesday
        self.assertGreaterEqual(d.date(), timezone.localtime(timezone.now()).date())

    def test_create_with_recur_no_date_gets_anchored(self):
        self.client.post(reverse("task_create"),
                         {"title": "Rec", "recur_rule": "FREQ=DAILY"})
        t = Task.objects.get(title="Rec")
        self.assertIsNotNone(t.due_date)  # anchored, not left dateless
        self.assertEqual(t.due_date.date(), timezone.localtime(timezone.now()).date())

    def test_update_clearing_date_on_recurring_reanchors(self):
        t = Task.objects.create(owner=self.user, title="R", recur_rule="FREQ=DAILY",
                                due_date=timezone.now() + timedelta(days=5))
        self.client.post(reverse("task_update", args=[t.id]),
                         {"title": "R", "recur_rule": "FREQ=DAILY", "due_date": ""})
        t.refresh_from_db()
        self.assertIsNotNone(t.due_date)  # re-anchored rather than going dateless


class RecurrenceSleepsInInbox(TestCase):
    """BR-25: a recurring task can sleep dateless in INBOX; completing it dates the next one."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_to_inbox_keeps_recur_rule(self):
        t = Task.objects.create(owner=self.user, title="R", recur_rule="FREQ=WEEKLY;BYDAY=MO",
                                due_date=timezone.now())
        self.client.post(reverse("task_to_inbox", args=[t.id]))
        t.refresh_from_db()
        self.assertIsNone(t.due_date)
        self.assertEqual(t.task_type, Task.Horizon.INBOX)
        self.assertEqual(t.recur_rule, "FREQ=WEEKLY;BYDAY=MO")  # repeat preserved, just sleeping

    def test_completing_dateless_recurring_spawns_a_dated_occurrence(self):
        t = Task.objects.create(owner=self.user, title="R", recur_rule="FREQ=DAILY",
                                task_type=Task.Horizon.INBOX)  # sleeping, no date
        services.set_done(t, True)
        nxt = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertIsNotNone(nxt.due_date)  # the awakened occurrence is dated
        self.assertFalse(nxt.done)
        self.assertEqual(nxt.recur_rule, "FREQ=DAILY")
