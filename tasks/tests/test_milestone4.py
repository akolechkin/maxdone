"""Milestone 4 — user-authored goal templates (spec/08, BR-26..BR-29).

CRUD of a template and its content, owner-scoping, cascade delete, and that the
existing "create goal from template" (BR-29) works on a user-built template.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from tasks.models import (Goal, Task, GoalTemplate, MilestoneTemplate, TaskTemplate)


class TemplateCrud(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    # ---- BR-27: template CRUD ----

    def test_create_template_owned_by_user(self):  # BR-26 + BR-27 Create
        r = self.client.post(reverse("template_create"), {"title": "Мой шаблон"})
        self.assertEqual(r.status_code, 302)  # redirects into the editor
        tpl = GoalTemplate.objects.get(title="Мой шаблон")
        self.assertEqual(tpl.owner, self.user)
        self.assertEqual(tpl.milestones.count(), 0)  # starts empty

    def test_detail_renders_editor(self):  # BR-27 Read one
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        r = self.client.get(reverse("template_detail", args=[tpl.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "template-editor")

    def test_update_title_and_description(self):  # BR-27 Update
        tpl = GoalTemplate.objects.create(owner=self.user, title="Old")
        self.client.post(reverse("template_update", args=[tpl.id]),
                         {"title": "New", "description": "desc"})
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "New")
        self.assertEqual(tpl.description, "desc")

    def test_delete_template_cascades(self):  # BR-27 Delete + cascade
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        ms = MilestoneTemplate.objects.create(template=tpl, title="M")
        TaskTemplate.objects.create(template=tpl, milestone=ms, title="X")
        self.client.post(reverse("template_delete", args=[tpl.id]))
        self.assertFalse(GoalTemplate.objects.filter(id=tpl.id).exists())
        self.assertEqual(MilestoneTemplate.objects.count(), 0)
        self.assertEqual(TaskTemplate.objects.count(), 0)

    # ---- BR-26: owner-scoping ----

    def test_other_users_template_hidden_from_list(self):  # BR-26
        other = User.objects.create_user("o", password="p")
        GoalTemplate.objects.create(owner=other, title="Чужой")
        r = self.client.get(reverse("template_list"))
        self.assertNotContains(r, "Чужой")

    def test_cannot_open_other_users_template(self):  # BR-26
        other = User.objects.create_user("o", password="p")
        tpl = GoalTemplate.objects.create(owner=other, title="Чужой")
        r = self.client.get(reverse("template_detail", args=[tpl.id]))
        self.assertEqual(r.status_code, 404)

    def test_cannot_edit_other_users_template(self):  # BR-26
        other = User.objects.create_user("o", password="p")
        tpl = GoalTemplate.objects.create(owner=other, title="Чужой")
        r = self.client.post(reverse("template_update", args=[tpl.id]), {"title": "hax"})
        self.assertEqual(r.status_code, 404)
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "Чужой")

    # ---- BR-28: milestone CRUD ----

    def test_add_rename_delete_milestone(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        self.client.post(reverse("milestone_add", args=[tpl.id]), {"title": "Этап 1"})
        ms = MilestoneTemplate.objects.get(template=tpl, title="Этап 1")
        self.client.post(reverse("milestone_update", args=[ms.id]), {"title": "Этап A"})
        ms.refresh_from_db()
        self.assertEqual(ms.title, "Этап A")
        self.client.post(reverse("milestone_delete", args=[ms.id]))
        self.assertFalse(MilestoneTemplate.objects.filter(id=ms.id).exists())

    def test_milestone_add_assigns_sort_order(self):  # BR-28 ordering
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        self.client.post(reverse("milestone_add", args=[tpl.id]), {"title": "A"})
        self.client.post(reverse("milestone_add", args=[tpl.id]), {"title": "B"})
        orders = sorted(tpl.milestones.values_list("sort_order", flat=True))
        self.assertEqual(orders, [1, 2])

    def test_cannot_touch_other_users_milestone(self):  # BR-26
        other = User.objects.create_user("o", password="p")
        tpl = GoalTemplate.objects.create(owner=other, title="Чужой")
        ms = MilestoneTemplate.objects.create(template=tpl, title="M")
        r = self.client.post(reverse("milestone_update", args=[ms.id]), {"title": "hax"})
        self.assertEqual(r.status_code, 404)

    # ---- BR-28: task-template CRUD ----

    def test_add_task_to_milestone(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        ms = MilestoneTemplate.objects.create(template=tpl, title="M")
        self.client.post(reverse("tasktmpl_add", args=[tpl.id]),
                         {"title": "Шаг", "milestone": ms.id})
        tt = TaskTemplate.objects.get(template=tpl, title="Шаг")
        self.assertEqual(tt.milestone_id, ms.id)

    def test_add_task_without_milestone(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        self.client.post(reverse("tasktmpl_add", args=[tpl.id]), {"title": "Свободная"})
        tt = TaskTemplate.objects.get(template=tpl, title="Свободная")
        self.assertIsNone(tt.milestone_id)

    def test_rename_and_delete_task(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        tt = TaskTemplate.objects.create(template=tpl, title="X")
        self.client.post(reverse("tasktmpl_update", args=[tt.id]), {"title": "Y"})
        tt.refresh_from_db()
        self.assertEqual(tt.title, "Y")
        self.client.post(reverse("tasktmpl_delete", args=[tt.id]))
        self.assertFalse(TaskTemplate.objects.filter(id=tt.id).exists())

    # ---- BR-29: applying a user-built template ----

    def test_create_goal_from_user_template(self):
        tpl = GoalTemplate.objects.create(owner=self.user, title="Запуск")
        ms = MilestoneTemplate.objects.create(template=tpl, title="Подготовка")
        TaskTemplate.objects.create(template=tpl, milestone=ms, title="Шаг 1", offset_days=0)
        r = self.client.post(reverse("template_create_goal", args=[tpl.id]),
                             {"start_date": "2026-07-01"})
        self.assertEqual(r.status_code, 302)
        goal = Goal.objects.get(title="Запуск", owner=self.user)
        ms_task = Task.objects.get(title="Подготовка", owner=self.user)
        self.assertTrue(ms_task.is_project)
        self.assertTrue(ms_task.from_template)  # BR-T1: passive origin marker (no longer a lock)
        step = Task.objects.get(title="Шаг 1", owner=self.user)
        self.assertEqual(step.parent_id, ms_task.id)

    def test_cannot_apply_other_users_template(self):  # BR-26 + BR-29
        other = User.objects.create_user("o", password="p")
        tpl = GoalTemplate.objects.create(owner=other, title="Чужой")
        r = self.client.post(reverse("template_create_goal", args=[tpl.id]),
                             {"start_date": "2026-07-01"})
        self.assertEqual(r.status_code, 404)
