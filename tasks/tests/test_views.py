"""
Маршрутные тесты (spec/03_api_ui.md — источник истины для маршрутов и HTMX-флоу).
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from tasks.models import Task
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
