# core/context_processors.py
"""
Exposes the request's active ProductionSite to every template (functional
spec §25.2 + avicole-style role-locking) — so the topbar switcher badge
can show *which* site is active without every view having to inject it
manually into its context.
"""


def active_site(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from core.utils import get_active_site

    return {"active_site": get_active_site(request)}
