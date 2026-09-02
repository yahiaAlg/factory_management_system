# core/utils.py
"""
Shared, request-level utilities for the Production Sites (Branches)
feature (functional spec §25.2).

Deliberately simple compared to avicole's role-locked Branche switcher:
no middleware, no session-wide "active site", no Vue Globale concept, no
new role. A create form just defaults to whichever site the user most
recently used (get_default_site / remember_site); list and report views
take a plain "?site=<id>" GET filter (site_filter_kwargs) — omitted or
"all" means All Sites.
"""

from __future__ import annotations

LAST_SITE_SESSION_KEY = "last_production_site_id"


def get_default_site(request):
    """
    Resolve the ProductionSite a create form should default to (§25.2.5):
    whichever site this user most recently used, stored in the session by
    `remember_site` below. Falls back to the first active site (e.g. the
    seeded "Site Principal") when the session holds no usable selection.
    Returns None only if no active ProductionSite exists at all.
    """
    from core.models import ProductionSite

    site_id = request.session.get(LAST_SITE_SESSION_KEY)
    if site_id:
        site = ProductionSite.objects.filter(pk=site_id, is_active=True).first()
        if site:
            return site
    return ProductionSite.objects.filter(is_active=True).order_by("name").first()


def remember_site(request, site):
    """Record *site* as this user's most-recently-used site (session-level),
    so their next create form defaults to it (§25.2.5)."""
    if site is not None:
        request.session[LAST_SITE_SESSION_KEY] = site.pk


def site_filter_kwargs(request, field_name="site"):
    """
    Convenience for list/report views: `{}` when the GET param `site` is
    absent or `"all"` (== All Sites, no filter), else `{field_name: site_id}`.
    """
    site_id = request.GET.get("site")
    if not site_id or site_id == "all":
        return {}
    return {field_name: site_id}


def get_seed_site(command=None):
    """
    Resolve the site seed/demo management commands should attach
    site-scoped documents to (functional spec §25.2) — no request/session
    available outside a view, so this is the non-request counterpart to
    get_default_site(). Prefers the seeded "Site Principal" (code MAIN),
    falling back to the first active site so a command still works if MAIN
    was renamed.

    Self-healing: creates "Site Principal" (MAIN) on the fly if none
    exists at all. This matters because `manage.py flush` (used by every
    seed script here to reset demo data) truncates ProductionSite too but,
    unlike `migrate`, does NOT re-run the core.0004_seed_main_site data
    migration — so relying on that migration alone would break every seed
    script immediately after a flush. `command` is an optional
    BaseCommand instance, used only to print a confirmation via
    self.stdout when a site is actually created.
    """
    from core.models import ProductionSite

    site = ProductionSite.objects.filter(code="MAIN").first()
    if site is None:
        site = ProductionSite.objects.filter(is_active=True).order_by("id").first()
    if site is None:
        site = ProductionSite.objects.create(name="Site Principal", code="MAIN")
        if command is not None:
            command.stdout.write(
                command.style.SUCCESS(
                    f"  ✔ ProductionSite '{site.name}' ({site.code}) créé (aucun site trouvé)"
                )
            )
    return site
