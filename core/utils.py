# core/utils.py
"""
Shared, request-level utilities for the Production Sites (Sites) feature
(functional spec §25.2), extended to mirror the avicole project's
role-locked Branche switcher (§3.5.4):

  - stock_prod / sales (UserProfile.SITE_REQUIRED_ROLES): always their own
    profile.site — locked, no switcher (BR-BRA-02 equivalent).
  - accountant / viewer bound to a site: always that site.
  - manager, or accountant/viewer left unbound (profile.has_global_view):
    the site stored in session by `site_switch`, or None when the session
    holds no selection (default = global view across all sites,
    BR-BRA-04 equivalent).
  - qa_manager / qc_technician: unaffected — the quality module stays
    company-wide (functional spec §25.2 scope) and never resolves a site.

There is no per-site URL segment and no middleware: every app's views call
`get_active_site(request)` and filter accordingly; `None` always means
"toutes les sites" (all sites / global view).
"""

from __future__ import annotations

SITE_SESSION_KEY = "active_site_id"


def get_user_profile(user):
    """Return the UserProfile for *user*, or None if it doesn't exist."""
    from accounts.models import UserProfile

    try:
        return user.userprofile
    except UserProfile.DoesNotExist:
        return None
    except AttributeError:
        return None


def get_active_site(request):
    """
    Resolve the ProductionSite the current request is operating in
    (§25.2 + avicole §3.5.4 role-locking).

      - stock_prod / sales: always their own profile.site — locked, no
        switcher.
      - accountant / viewer bound to a site: always that site.
      - manager, or accountant/viewer left unbound
        (profile.has_global_view): the site stored in session by
        `site_switch`, or None when the session holds no selection
        (default = all sites / global view).
      - qa_manager / qc_technician: always None (module stays
        company-wide).

    Returns a ProductionSite instance, or None for "toutes les sites".
    """
    from core.models import ProductionSite

    profile = get_user_profile(request.user)
    if profile is None:
        return None
    if not profile.has_global_view:
        return profile.site

    site_id = request.session.get(SITE_SESSION_KEY)
    if not site_id:
        return None
    return ProductionSite.objects.filter(pk=site_id, is_active=True).first()


def is_global_view(request):
    """True when the request is currently in global view (all sites)."""
    return get_active_site(request) is None


def can_switch_site(request):
    """True when the user gets a site switcher in the UI (§25.2 + avicole §3.5.4)."""
    profile = get_user_profile(request.user)
    return bool(profile and profile.can_switch_site)


def require_site_context(view_func):
    """
    Decorator for create/edit views: global view is read-only, never used
    to create or own a new record (mirrors avicole's BR-BRA-04 /
    `require_branche_context`). Manager/accountant/viewer must select a
    concrete site via the switcher before reaching a creation form;
    stock_prod/sales are always pinned to one and never hit this guard.
    """
    from functools import wraps

    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if is_global_view(request):
            messages.error(
                request,
                "La vue globale (toutes les sites) est en lecture seule — "
                "veuillez sélectionner un site précis avant de créer ou "
                "modifier un enregistrement.",
            )
            return redirect(f"{reverse('core:site_switch')}?next={request.path}")
        return view_func(request, *args, **kwargs)

    return _wrapped


def site_object_or_404(request, model, **kwargs):
    """
    get_object_or_404, additionally enforcing that the object's `site`
    matches the request's active site when not in global view (mirrors
    avicole's `branche_object_or_404`): a stock_prod/sales account must
    never reach another site's record even by guessing its pk in the URL.
    In global view the object is returned regardless of which site it
    belongs to.
    """
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    obj = get_object_or_404(model, **kwargs)
    site = get_active_site(request)
    if site is not None and getattr(obj, "site_id", None) != site.id:
        raise Http404("Cet enregistrement appartient à un autre site.")
    return obj


def site_scope_kwargs(request, field_name="site"):
    """
    Convenience for simple `Model.objects.filter(**kwargs)` calls:
    `{}` in global view (no filter == every site), else
    `{field_name: active_site}`. Replaces the old GET-param-only
    `site_filter_kwargs` now that site can also come from a locked
    profile or a session-stored switcher choice.
    """
    site = get_active_site(request)
    if site is None:
        return {}
    return {field_name: site}


# ---------------------------------------------------------------------------
# Backward-compatible helpers (pre-role-locking, §25.2 original design) —
# kept for management commands / call sites that don't need role-locking
# and only want "whichever site was last used" or a plain GET filter.
# ---------------------------------------------------------------------------

LAST_SITE_SESSION_KEY = "last_production_site_id"


def get_default_site(request):
    """
    Resolve the ProductionSite a create form should default to.

    Role-locked roles (stock_prod/sales, or a bound accountant/viewer) get
    their own `get_active_site(request)` result directly — this matters
    because their create views pass the result straight to the form as a
    locked/hidden field. For manager / unbound accountant / viewer, this
    falls back to whichever site was most recently used in session
    (§25.2.5), then the first active site.
    """
    from core.models import ProductionSite

    profile = get_user_profile(request.user)
    if profile is not None and not profile.has_global_view:
        return profile.site

    active = get_active_site(request)
    if active is not None:
        return active

    site_id = request.session.get(LAST_SITE_SESSION_KEY)
    if site_id:
        site = ProductionSite.objects.filter(pk=site_id, is_active=True).first()
        if site:
            return site
    return ProductionSite.objects.filter(is_active=True).order_by("name").first()


def remember_site(request, site):
    """Record *site* as this user's most-recently-used site (session-level),
    so their next create form defaults to it (§25.2.5). Only meaningful for
    users with a switcher (manager / unbound accountant / viewer) — a
    role-locked user's site never changes, so this is a no-op in practice
    for them, but harmless to call unconditionally."""
    if site is not None:
        request.session[LAST_SITE_SESSION_KEY] = site.pk


def site_form_kwargs(request):
    """
    Build the right kwarg for a site-aware ModelForm (ProductionOrderForm,
    StockAdjustmentForm, ClientDNForm, SupplierDNForm — each accepts
    `site=` to lock+hide the field, or `initial_site=` to just default it):

      - Role-locked users (stock_prod/sales, or a site-bound
        accountant/viewer — `not profile.has_global_view`): `{"site": ...}`
        — the field is hidden and forced to their own site, mirroring
        avicole's BLFournisseurForm(branche=...) pattern.
      - Switcher-capable users (manager, or an unbound accountant/viewer):
        `{"initial_site": ...}` — the field stays visible/editable,
        defaulting to the active site (or last-used site).

    Returns `{}` if no site could be resolved (e.g. no ProductionSite
    exists yet) — the form's own `site` field then falls back to its
    normal (required, unfiltered-default) behaviour.
    """
    profile = get_user_profile(request.user)
    site = get_default_site(request)
    if site is None:
        return {}
    if profile is not None and not profile.has_global_view:
        return {"site": site}
    return {"initial_site": site}


def site_filter_kwargs(request, field_name="site"):
    """
    DEPRECATED — superseded by `site_scope_kwargs`, which additionally
    respects role-locking. Kept only for any leftover call site during
    migration; behaves the same as before (?site=<id> GET param only,
    ignores role-locking).
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
