from django import template
from django.template.defaultfilters import stringfilter, floatformat
from django.utils.safestring import mark_safe
import locale

register = template.Library()


@register.filter
def abs(value):
    try:
        return (
            __builtins__["abs"](value)
            if isinstance(__builtins__, dict)
            else __import__("builtins").abs(value)
        )
    except (TypeError, ValueError):
        return value


@register.filter
@stringfilter
def currency(value, arg="USD"):
    """
    Format a value as currency (e.g. {{ amount|currency:'USD' }} -> $1,234.56).
    Supports 'USD', 'EUR'. Uses locale for formatting.
    """
    try:
        locale.setlocale(locale.LC_ALL, "")
        float_val = float(value.replace(",", ""))
        if arg.upper() == "EUR":
            prefix = "€"
        else:
            prefix = "$"
        return mark_safe(f"{prefix}{locale.currency(float_val, grouping=True)}")
    except (ValueError, TypeError):
        return value


@register.filter
def status_badge(value):
    """
    Return HTML badge for status (e.g. 'In Production' -> green badge).
    Common statuses: 'Draft', 'In Production', 'Completed', 'Cancelled'.
    """
    badges = {
        "draft": ("badge-warning", "Draft"),
        "in production": ("badge-info", "In Production"),
        "completed": ("badge-success", "Completed"),
        "cancelled": ("badge-danger", "Cancelled"),
        "pending": ("badge-secondary", "Pending"),
    }
    status = value.lower() if value else ""
    badge_class, text = badges.get(status, ("badge-secondary", value or "Unknown"))
    return mark_safe(f'<span class="badge {badge_class}">{text}</span>')


@register.filter
def quantity(value, unit="kg"):
    """
    Format quantity with unit (e.g. {{ qty|quantity:'pcs' }} -> 100.00 pcs).
    """
    try:
        formatted = floatformat(value, 2)
        return mark_safe(f"{formatted} {unit}")
    except (ValueError, TypeError):
        return f"{value} {unit}"


@register.filter
def yesno(value, arg="yes,no,maybe"):
    """
    Enhanced yes/no filter for booleans (e.g. {{ active|yesno:'Active,Inactive' }}).
    """
    yes, no, maybe = arg.split(",")
    if value:
        return yes
    else:
        return no


@register.filter
def safe_floatformat(value, arg=2):
    """
    Safe float formatting (handles None/empty).
    """
    if value is None or value == "":
        return "0.00"
    return floatformat(float(value), arg)


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0
