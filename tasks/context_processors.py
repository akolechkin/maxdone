from django.conf import settings


def feature_flags(request):
    """Expose presentation-layer feature flags to all templates.

    BR-33: `task_edit_draft` toggles the draft + edit-buffer editor (vs. the plain
    single-submit form). Default comes from settings.TASK_EDIT_DRAFT (env-driven).
    """
    return {"task_edit_draft": settings.TASK_EDIT_DRAFT}
