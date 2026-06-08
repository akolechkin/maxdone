from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Look up a dict value by variable key in templates."""
    if hasattr(d, "get"):
        return d.get(key, "")
    return ""
