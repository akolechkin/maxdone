"""BR-33 (task editor draft + edit buffer, feature-flagged) and BR-34 (network indicators).

Presentation-layer rules. The Django test client can't exercise the Alpine/htmx behavior, so
these assert the server-side contract: flag-gated markup, the additive draft-create branch,
and that the indicator markup is present.
"""
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from tasks.models import Task


class EditDraftFlag(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    # ---- BR-33: flag gating ----

    def test_flag_on_shows_cancel_and_draft_wiring(self):  # default ON
        r = self.client.get(reverse("task_new"))
        self.assertContains(r, "Отмена")
        self.assertContains(r, "flag: true")
        self.assertContains(r, "taskEditor(")

    @override_settings(TASK_EDIT_DRAFT=False)
    def test_flag_off_is_plain_form(self):
        r = self.client.get(reverse("task_new"))
        self.assertNotContains(r, "Отмена")
        self.assertContains(r, "flag: false")
        self.assertContains(r, "Создать")  # plain submit still there

    def test_editor_of_existing_task_has_detail_url_for_cancel(self):
        t = Task.objects.create(owner=self.user, title="E")
        r = self.client.get(reverse("task_detail", args=[t.id]))
        self.assertContains(r, "Отмена")
        self.assertContains(r, reverse("task_detail", args=[t.id]))  # detailUrl for revert

    # ---- BR-33: draft-on-blur create branch ----

    def test_draft_create_persists_and_keeps_editing(self):
        r = self.client.post(reverse("task_create") + "?h=TODAY&draft=1", {"title": "Draft me"})
        self.assertEqual(r.status_code, 200)
        task = Task.objects.get(title="Draft me", owner=self.user)
        # editor comes back in EDIT mode (posts to task_update), not the list
        self.assertContains(r, reverse("task_update", args=[task.id]))
        # list refreshed out-of-band so the new task shows
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, "Draft me")
        # editor stays open: no taskSaved trigger
        self.assertIsNone(r.get("HX-Trigger"))

    def test_empty_draft_creates_nothing(self):
        before = Task.objects.count()
        r = self.client.post(reverse("task_create") + "?h=TODAY&draft=1", {"title": ""})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(Task.objects.count(), before)

    def test_normal_create_still_closes_editor(self):  # non-draft path unchanged
        r = self.client.post(reverse("task_create") + "?h=TODAY", {"title": "Normal"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get("HX-Trigger"), "taskSaved")
        self.assertTrue(Task.objects.filter(title="Normal", owner=self.user).exists())


class NetworkIndicators(TestCase):  # BR-34
    def setUp(self):
        self.user = User.objects.create_user("u", password="p")
        self.client = Client()
        self.client.login(username="u", password="p")

    def test_board_has_indicator_markup(self):
        r = self.client.get(reverse("board"))
        self.assertContains(r, 'id="net-bar"')
        self.assertContains(r, 'id="net-error"')
        self.assertContains(r, "htmx:beforeRequest")
