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
def yesno(value, arg=None):
    """Enhanced yes/no filter for booleans (e.g. {{ active|yesno:'Active,Inactive' }}).

    Accepts 2 or 3 comma-separated values, same as Django's built-in
    `yesno` (yes,no[,maybe]) — this custom filter used to require
    exactly 3 and would crash on the common 2-value form used elsewhere
    in the app (e.g. `|yesno:'true,false'`), which is why it now mirrors
    the built-in's flexible arity instead of re-narrowing it.
    """
    parts = (arg or "yes,no,maybe").split(",")
    if len(parts) == 2:
        yes, no = parts
        maybe = no
    elif len(parts) >= 3:
        yes, no, maybe = parts[0], parts[1], parts[2]
    else:
        yes = no = maybe = parts[0]
    if value is None:
        return maybe
    return yes if value else no


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


@register.filter(name="getfield")
def getfield(form, field_name):
    """Return a BoundField by dynamic name — used in production_order_close.html."""
    try:
        return form[field_name]
    except KeyError:
        return None


@register.filter(name="contrast_text")
def contrast_text(hex_color):
    """Return '#0b1220' or '#ffffff' — whichever reads better on hex_color.

    Used for the row_color chip on Désignation cells (raw materials /
    finished products lists): a user-chosen color can be light or dark,
    so the label text needs to pick its own foreground rather than
    assuming one, or a light pick like a pale yellow renders unreadable
    pale-on-white text.
    """
    if not hex_color:
        return "#ffffff"
    h = str(hex_color).lstrip("#")
    if len(h) != 6:
        return "#ffffff"
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"
    # WCAG-style relative luminance (sRGB, simplified linearization).
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#0b1220" if luminance > 0.42 else "#ffffff"
