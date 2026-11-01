from django import template

from core.forms import format_minutes

register = template.Library()


@register.filter
def duration(minutes):
    """45 -> '45m', 105 -> '1h 45m', 120 -> '2h'."""
    try:
        return format_minutes(int(minutes))
    except (TypeError, ValueError):
        return ""
