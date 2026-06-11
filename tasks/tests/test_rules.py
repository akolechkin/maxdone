"""
Поведенческие тесты, выведенные из spec/02_rules.md.
Это арбитр spec-driven цикла. Каждый тест ссылается на BR-N из спеки.
"""
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from tasks.models import Task, Goal, Context


class VisibilityRules(TestCase):
    """BR-1, BR-2: видимость и счётчики горизонтов."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")

    def test_active_task_is_visible(self):  # BR-1
        Task.objects.create(owner=self.user, title="t", task_type=Task.Horizon.TODAY)
        from tasks.views import _visible_tasks
        self.assertEqual(_visible_tasks(self.user).count(), 1)

    def test_done_task_hidden(self):  # BR-1
        Task.objects.create(owner=self.user, title="t", done=True)
        from tasks.views import _visible_tasks
        self.assertEqual(_visible_tasks(self.user).count(), 0)

    def test_hidden_future_task_invisible(self):  # BR-1
        Task.objects.create(
            owner=self.user, title="t", state=Task.State.HIDDEN,
            hide_until_date=timezone.now() + timedelta(days=2),
        )
        from tasks.views import _visible_tasks
        self.assertEqual(_visible_tasks(self.user).count(), 0)

    def test_hidden_past_task_resurfaces(self):  # BR-1
        Task.objects.create(
            owner=self.user, title="t", state=Task.State.HIDDEN,
            hide_until_date=timezone.now() - timedelta(days=1),
        )
        from tasks.views import _visible_tasks
        self.assertEqual(_visible_tasks(self.user).count(), 1)

    def test_horizon_counts(self):  # BR-2 / BR-8: counts derive from due_date, not a stored type
        now = timezone.now()
        Task.objects.create(owner=self.user, title="a", due_date=now)                   # TODAY
        Task.objects.create(owner=self.user, title="b", due_date=now)                   # TODAY
        Task.objects.create(owner=self.user, title="c", due_date=now + timedelta(days=30))  # LATER
        Task.objects.create(owner=self.user, title="d")                                 # no due -> INBOX
        from tasks.views import _horizon_counts
        counts = _horizon_counts(self.user)
        self.assertEqual(counts["TODAY"], 2)
        self.assertEqual(counts["LATER"], 1)
        self.assertEqual(counts["INBOX"], 1)


class OwnerIsolation(TestCase):
    """BR-6: пользователь видит только свои объекты."""

    def test_isolation(self):
        a = User.objects.create_user("a", password="p")
        b = User.objects.create_user("b", password="p")
        Task.objects.create(owner=a, title="secret", task_type=Task.Horizon.TODAY)
        from tasks.views import _visible_tasks
        self.assertEqual(_visible_tasks(b).count(), 0)
        self.assertEqual(_visible_tasks(a).count(), 1)


class EnumContract(TestCase):
    """spec/01_domain.md: enum-значения фиксированы (из APK). Ломать нельзя."""

    def test_horizon_values(self):
        self.assertEqual(Task.Horizon.INBOX, 1)
        self.assertEqual(Task.Horizon.TODAY, 2)
        self.assertEqual(Task.Horizon.WEEK, 3)
        self.assertEqual(Task.Horizon.LATER, 4)

    def test_state_values(self):
        self.assertEqual(Task.State.ACTIVE, 0)
        self.assertEqual(Task.State.HIDDEN, 1)

    def test_goal_types(self):
        self.assertEqual(Goal.Type.PRIVATE, "PRIVATE")
        self.assertEqual(Goal.Type.CORPORATE, "CORPORATE")
