from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def dict_get(d, key):
    """Look up a dict value by variable key in templates."""
    if hasattr(d, "get"):
        return d.get(key, "")
    return ""


@register.filter
def is_overdue(due_date):
    """BR-22: True if due_date is before the start of today (i.e. genuinely overdue, not
    merely due later today). Used to paint overdue dates red. Done-state is checked separately."""
    if not due_date:
        return False
    local = timezone.localtime(timezone.now())
    start_of_today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return due_date < start_of_today
