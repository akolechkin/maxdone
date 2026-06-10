"""
Тесты сервисного слоя, выведенные из spec/02_rules.md.
BR-3 (completion_date) и BR-4 (priority).
"""
from datetime import datetime, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from tasks.models import Task
from tasks import services


class CompletionRule(TestCase):
    """BR-3."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.task = services.create_task(self.user, "t", task_type=Task.Horizon.TODAY)

    def test_done_sets_completion_date(self):
        services.set_done(self.task, True)
        self.assertTrue(self.task.done)
        self.assertIsNotNone(self.task.completion_date)

    def test_undone_clears_completion_date(self):
        services.set_done(self.task, True)
        services.set_done(self.task, False)
        self.assertFalse(self.task.done)
        self.assertIsNone(self.task.completion_date)


class PriorityRule(TestCase):
    """BR-4."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def test_first_task_priority(self):
        self.assertEqual(services.next_priority(self.user), 1.0)

    def test_next_priority_increments_above_max(self):
        services.create_task(self.user, "a", priority=5.0)
        self.assertEqual(services.next_priority(self.user), 6.0)

    def test_between_two_neighbors_is_midpoint(self):
        a = services.create_task(self.user, "a", priority=2.0)
        b = services.create_task(self.user, "b", priority=4.0)
        self.assertEqual(services.priority_between(a, b), 3.0)

    def test_insert_at_start(self):
        b = services.create_task(self.user, "b", priority=4.0)
        self.assertEqual(services.priority_between(None, b), 3.0)

    def test_insert_at_end(self):
        a = services.create_task(self.user, "a", priority=4.0)
        self.assertEqual(services.priority_between(a, None), 5.0)

    def test_empty_list(self):
        self.assertEqual(services.priority_between(None, None), 1.0)

    def test_create_task_uses_auto_priority(self):
        t1 = services.create_task(self.user, "a")
        t2 = services.create_task(self.user, "b")
        self.assertEqual(t1.priority, 1.0)
        self.assertEqual(t2.priority, 2.0)


class SubtreeMove(TestCase):
    """BR-22: moving a task re-dates its whole subtree into the target horizon."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def test_move_propagates_to_descendants(self):
        now = timezone.now()
        root = Task.objects.create(owner=self.user, title="root", due_date=now)
        child = Task.objects.create(owner=self.user, title="child", parent=root, due_date=now)
        grand = Task.objects.create(owner=self.user, title="grand", parent=child, due_date=now)
        services.move_task(root, "LATER")
        for t in (root, child, grand):
            t.refresh_from_db()
            self.assertEqual(services.horizon_for(t.due_date), Task.Horizon.LATER, t.title)


class RecurrenceGeneration(TestCase):
    """BR-5: completing a recurring task spawns the next occurrence."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def _recurring(self, rule, due, **kw):
        return Task.objects.create(owner=self.user, title="R", due_date=due,
                                   recur_rule=rule, **kw)

    def test_daily_spawns_next_day(self):
        due = timezone.now().replace(microsecond=0)
        t = self._recurring("FREQ=DAILY", due)
        services.set_done(t, True)
        nxt = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertEqual(nxt.due_date, due + timedelta(days=1))
        self.assertFalse(nxt.done)
        self.assertEqual(nxt.recur_rule, "FREQ=DAILY")

    def test_interval_respected(self):
        due = timezone.now().replace(microsecond=0)
        t = self._recurring("FREQ=DAILY;INTERVAL=3", due)
        services.set_done(t, True)
        nxt = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertEqual(nxt.due_date, due + timedelta(days=3))

    def test_completed_task_stays_done(self):
        t = self._recurring("FREQ=DAILY", timezone.now())
        services.set_done(t, True)
        t.refresh_from_db()
        self.assertTrue(t.done)
        self.assertIsNotNone(t.completion_date)

    def test_weekly_byday_picks_next_listed_weekday(self):
        # Monday 2026-06-15; rule fires Mon & Wed → next is Wednesday 2026-06-17
        monday = timezone.make_aware(datetime(2026, 6, 15, 9, 0))
        t = self._recurring("FREQ=WEEKLY;BYDAY=MO,WE", monday)
        services.set_done(t, True)
        nxt = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertEqual((nxt.due_date.year, nxt.due_date.month, nxt.due_date.day), (2026, 6, 17))

    def test_count_decrements_and_terminates(self):
        due = timezone.now().replace(microsecond=0)
        t = self._recurring("FREQ=DAILY;COUNT=2", due)
        services.set_done(t, True)
        child = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertEqual(_count_in(child.recur_rule), 1)
        # completing the COUNT=1 occurrence ends the series — no further spawn
        services.set_done(child, True)
        self.assertEqual(Task.objects.filter(owner=self.user).count(), 2)

    def test_until_in_past_stops_series(self):
        due = timezone.now().replace(microsecond=0)
        t = self._recurring("FREQ=DAILY;UNTIL=20000101", due)
        services.set_done(t, True)
        self.assertEqual(Task.objects.filter(owner=self.user).count(), 1)

    def test_non_recurring_does_not_spawn(self):
        t = Task.objects.create(owner=self.user, title="once", due_date=timezone.now())
        services.set_done(t, True)
        self.assertEqual(Task.objects.filter(owner=self.user).count(), 1)

    def test_series_root_is_carried(self):
        due = timezone.now().replace(microsecond=0)
        root = self._recurring("FREQ=DAILY", due)
        services.set_done(root, True)
        child = Task.objects.exclude(id=root.id).get(owner=self.user)
        self.assertEqual(child.recur_parent_id, root.id)
        services.set_done(child, True)
        grand = Task.objects.exclude(id__in=[root.id, child.id]).get(owner=self.user)
        self.assertEqual(grand.recur_parent_id, root.id)  # points to the series root, not the child

    def test_checklist_copied_unchecked(self):
        t = self._recurring("FREQ=DAILY", timezone.now())
        t.checklist.create(title="step", done=True, sort_order=0)
        services.set_done(t, True)
        child = Task.objects.exclude(id=t.id).get(owner=self.user)
        self.assertEqual(child.checklist.count(), 1)
        self.assertFalse(child.checklist.first().done)


def _count_in(rule):
    for chunk in rule.split(";"):
        k, _, v = chunk.partition("=")
        if k.upper() == "COUNT":
            return int(v)
    return None
