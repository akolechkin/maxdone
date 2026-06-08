"""
Маршрутные тесты (spec/03_api_ui.md — источник истины для маршрутов и HTMX-флоу).
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from tasks.models import Task, Goal, Context
from tasks import services


class NewTaskCreation(TestCase):
    """spec/03_api_ui.md: кнопка 'Новая задача' должна СОЗДАВАТЬ задачу,
    а не открывать существующую.

    Регресс: в board.html кнопка вела hx-get на task_detail(tasks.first),
    т.е. открывала редактор первой существующей задачи — отдельного
    маршрута создания не было вовсе.
    """

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client.force_login(self.user)

    def test_new_task_endpoint_creates_new_task(self):
        existing = services.create_task(
            self.user, "existing", task_type=Task.Horizon.TODAY
        )
        before = Task.objects.filter(owner=self.user).count()

        resp = self.client.post(reverse("task_create"), {"h": "TODAY"})

        self.assertIn(resp.status_code, (200, 201))
        self.assertEqual(Task.objects.filter(owner=self.user).count(), before + 1)
        newest = Task.objects.filter(owner=self.user).latest("created")
        self.assertNotEqual(newest.id, existing.id)

    def test_new_task_lands_in_requested_horizon(self):
        resp = self.client.post(reverse("task_create"), {"h": "WEEK"})
        self.assertEqual(resp.status_code, 200)
        newest = Task.objects.filter(owner=self.user).latest("created")
        self.assertEqual(newest.task_type, Task.Horizon.WEEK)

    def test_new_task_defaults_to_inbox(self):
        # spec/03: горизонт по умолчанию INBOX, когда `h` не передан/невалиден.
        self.client.post(reverse("task_create"))
        newest = Task.objects.filter(owner=self.user).latest("created")
        self.assertEqual(newest.task_type, Task.Horizon.INBOX)


class TaskSave(TestCase):
    """spec/03_api_ui.md: редактор сохраняет поля задачи; BR-6 на запись."""

    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client.force_login(self.user)
        self.task = services.create_task(
            self.user, "old", task_type=Task.Horizon.INBOX
        )

    def test_save_updates_fields(self):
        goal = Goal.objects.create(owner=self.user, title="G")
        ctx = Context.objects.create(owner=self.user, title="C")
        resp = self.client.post(
            reverse("task_save", args=[self.task.id]),
            {
                "title": "new title",
                "note": "a note",
                "task_type": Task.Horizon.WEEK,
                "goal": goal.id,
                "context": ctx.id,
                "recur_rule": "FREQ=DAILY",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "new title")
        self.assertEqual(self.task.note, "a note")
        self.assertEqual(self.task.task_type, Task.Horizon.WEEK)
        self.assertEqual(self.task.goal_id, goal.id)
        self.assertEqual(self.task.context_id, ctx.id)

    def test_save_accepts_date_only_due_date(self):
        # Регресс Phase B: due_date вводится как дата (без времени).
        resp = self.client.post(
            reverse("task_save", args=[self.task.id]),
            {"title": "t", "task_type": Task.Horizon.INBOX, "due_date": "2026-06-10"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.due_date)
        self.assertEqual(self.task.due_date.date().isoformat(), "2026-06-10")

    def test_hide_until_future_hides_task(self):  # BR-1 write side
        from tasks.views import _visible_tasks
        resp = self.client.post(
            reverse("task_save", args=[self.task.id]),
            {"title": "t", "task_type": Task.Horizon.INBOX, "hide_until_date": "2026-12-31"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, Task.State.HIDDEN)
        self.assertNotIn(self.task, _visible_tasks(self.user))

    def test_clearing_hide_until_keeps_active(self):  # BR-1 write side
        from tasks.views import _visible_tasks
        self.client.post(
            reverse("task_save", args=[self.task.id]),
            {"title": "t", "task_type": Task.Horizon.INBOX, "hide_until_date": "2026-12-31"},
        )
        self.client.post(
            reverse("task_save", args=[self.task.id]),
            {"title": "t", "task_type": Task.Horizon.INBOX, "hide_until_date": ""},
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, Task.State.ACTIVE)
        self.assertIn(self.task, _visible_tasks(self.user))

    def test_cannot_save_other_users_task(self):  # BR-6
        other = User.objects.create_user("o", password="p")
        victim = services.create_task(other, "secret")
        resp = self.client.post(
            reverse("task_save", args=[victim.id]), {"title": "hacked"}
        )
        self.assertEqual(resp.status_code, 404)
        victim.refresh_from_db()
        self.assertEqual(victim.title, "secret")

    def test_cannot_assign_other_users_goal(self):  # BR-6 на запись
        other = User.objects.create_user("o", password="p")
        foreign_goal = Goal.objects.create(owner=other, title="theirs")
        resp = self.client.post(
            reverse("task_save", args=[self.task.id]),
            {"title": "t", "task_type": Task.Horizon.INBOX, "goal": foreign_goal.id},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.goal_id)
