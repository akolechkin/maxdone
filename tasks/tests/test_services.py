"""
Тесты сервисного слоя, выведенные из spec/02_rules.md.
BR-1 (hidden state, запись), BR-3 (completion_date) и BR-4 (priority).
"""
from datetime import timedelta
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


class HiddenStateRule(TestCase):
    """BR-1 (запись): state выводится из hide_until_date."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def test_future_date_hides(self):
        task = services.create_task(self.user, "t")
        task.hide_until_date = timezone.now() + timedelta(days=3)
        services.apply_hidden_state(task)
        self.assertEqual(task.state, Task.State.HIDDEN)

    def test_no_date_active(self):
        task = services.create_task(self.user, "t")
        task.hide_until_date = None
        services.apply_hidden_state(task)
        self.assertEqual(task.state, Task.State.ACTIVE)

    def test_past_date_active(self):
        task = services.create_task(self.user, "t", state=Task.State.HIDDEN)
        task.hide_until_date = timezone.now() - timedelta(days=1)
        services.apply_hidden_state(task)
        self.assertEqual(task.state, Task.State.ACTIVE)


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
