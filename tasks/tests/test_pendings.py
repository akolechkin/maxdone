"""Pending fixes finished together: BR-30, BR-31, BR-32, BR-28 reorder.

- BR-30: editor actions return to the box being viewed, not TODAY.
- BR-31: sidebar active item + counters follow an HTMX box switch (OOB).
- BR-32: drag&drop reorder of subtasks (priority) and checklist (sort_order).
- BR-28: drag&drop reorder of template milestones / task templates (sort_order).
"""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from tasks.models import (Task, CheckListItem, GoalTemplate, MilestoneTemplate, TaskTemplate)


class HorizonRetention(TestCase):  # BR-30
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_editor_carries_current_horizon(self):
        t = Task.objects.create(owner=self.user, title="W",
                                due_date=timezone.now() + timedelta(days=3))  # WEEK
        r = self.client.get(reverse("task_detail", args=[t.id]) + "?h=WEEK")
        # the editor's action buttons must post back with ?h=WEEK, not the TODAY default
        self.assertContains(r, "h=WEEK")

    def test_delete_returns_to_current_box(self):
        t = Task.objects.create(owner=self.user, title="W",
                                due_date=timezone.now() + timedelta(days=3))
        r = self.client.post(reverse("task_delete", args=[t.id]) + "?h=WEEK")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Неделя")  # WEEK list, not "Сегодня"


class SidebarOob(TestCase):  # BR-31
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_box_switch_oob_swaps_active_nav(self):
        r = self.client.get(reverse("board") + "?h=WEEK", HTTP_HX_REQUEST="true")
        self.assertContains(r, 'id="nav-WEEK"')
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, "nav-item-active")

    def test_full_page_nav_not_oob(self):
        r = self.client.get(reverse("board") + "?h=WEEK")  # no HX header
        self.assertContains(r, 'id="nav-WEEK"')
        self.assertNotContains(r, 'hx-swap-oob="true"')


class SubtaskReorder(TestCase):  # BR-32 (subtasks)
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.parent = Task.objects.create(owner=self.user, title="P", is_project=True)
        self.c1 = Task.objects.create(owner=self.user, title="c1", parent=self.parent, priority=1.0)
        self.c2 = Task.objects.create(owner=self.user, title="c2", parent=self.parent, priority=2.0)
        self.c3 = Task.objects.create(owner=self.user, title="c3", parent=self.parent, priority=3.0)

    def test_reorder_subtask_sets_fractional_priority(self):
        # move c3 between c1 and c2 → priority = 1.5
        r = self.client.post(reverse("task_reorder"),
                             {"id": self.c3.id, "before": self.c1.id, "after": self.c2.id})
        self.assertEqual(r.status_code, 204)
        self.c3.refresh_from_db()
        self.assertEqual(self.c3.priority, 1.5)

    def test_editor_renders_sortable_subtasks(self):
        r = self.client.get(reverse("task_detail", args=[self.parent.id]))
        self.assertContains(r, 'data-id-prefix="sub-"')
        self.assertContains(r, 'id="sub-{}"'.format(self.c1.id))


class ChecklistReorder(TestCase):  # BR-32 (checklist)
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.task = Task.objects.create(owner=self.user, title="T")
        self.a = self.task.checklist.create(title="A", sort_order=0)
        self.b = self.task.checklist.create(title="B", sort_order=1)
        self.c = self.task.checklist.create(title="C", sort_order=2)

    def _orders(self):
        return {i.title: i.sort_order for i in self.task.checklist.all()}

    def test_move_to_top(self):
        r = self.client.post(reverse("check_reorder"), {"id": self.c.id, "before": ""})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self._orders(), {"C": 0, "A": 1, "B": 2})

    def test_move_after_neighbour(self):
        # drop A right after B → order B, A, C
        self.client.post(reverse("check_reorder"), {"id": self.a.id, "before": self.b.id})
        self.assertEqual(self._orders(), {"B": 0, "A": 1, "C": 2})

    def test_other_users_item_404(self):
        other = User.objects.create_user("o", password="p")
        ot = Task.objects.create(owner=other, title="X")
        it = ot.checklist.create(title="Z", sort_order=0)
        r = self.client.post(reverse("check_reorder"), {"id": it.id, "before": ""})
        self.assertEqual(r.status_code, 404)


class TemplateReorder(TestCase):  # BR-28 reorder
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")
        self.tpl = GoalTemplate.objects.create(owner=self.user, title="T")
        self.m1 = MilestoneTemplate.objects.create(template=self.tpl, title="m1", sort_order=0)
        self.m2 = MilestoneTemplate.objects.create(template=self.tpl, title="m2", sort_order=1)
        self.m3 = MilestoneTemplate.objects.create(template=self.tpl, title="m3", sort_order=2)

    def test_reorder_milestones(self):
        r = self.client.post(reverse("milestone_reorder"), {"id": self.m3.id, "before": ""})
        self.assertEqual(r.status_code, 204)
        orders = {m.title: m.sort_order for m in self.tpl.milestones.all()}
        self.assertEqual(orders, {"m3": 0, "m1": 1, "m2": 2})

    def test_reorder_tasks_within_milestone(self):
        t1 = TaskTemplate.objects.create(template=self.tpl, milestone=self.m1, title="t1", sort_order=0)
        t2 = TaskTemplate.objects.create(template=self.tpl, milestone=self.m1, title="t2", sort_order=1)
        self.client.post(reverse("tasktmpl_reorder"), {"id": t2.id, "before": ""})
        orders = {t.title: t.sort_order for t in self.m1.task_templates.all()}
        self.assertEqual(orders, {"t2": 0, "t1": 1})

    def test_reorder_unsorted_tasks(self):
        u1 = TaskTemplate.objects.create(template=self.tpl, title="u1", sort_order=0)
        u2 = TaskTemplate.objects.create(template=self.tpl, title="u2", sort_order=1)
        self.client.post(reverse("tasktmpl_reorder"), {"id": u2.id, "before": ""})
        unsorted = self.tpl.task_templates.filter(milestone__isnull=True)
        orders = {t.title: t.sort_order for t in unsorted}
        self.assertEqual(orders, {"u2": 0, "u1": 1})

    def test_other_users_milestone_404(self):
        other = User.objects.create_user("o", password="p")
        otpl = GoalTemplate.objects.create(owner=other, title="O")
        om = MilestoneTemplate.objects.create(template=otpl, title="om", sort_order=0)
        r = self.client.post(reverse("milestone_reorder"), {"id": om.id, "before": ""})
        self.assertEqual(r.status_code, 404)
