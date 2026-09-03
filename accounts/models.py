# accounts/models.py
from django.contrib.auth.models import User
from django.db import models
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_login_failed
import json


class UserProfile(models.Model):
    """User profile with role-based permissions.

    Site binding (functional spec §25.2 — Multi-Site Architecture, extended
    to mirror the avicole project's Branche role-locking, §3.5.2):
      - manager                     : `site` always None. Not bound to a
                                       single site — switches the *active*
                                       site context per session (see
                                       core.utils.get_active_site) or works
                                       in "Toutes les sites" (global view).
      - stock_prod / sales          : `site` is REQUIRED — locked to
                                       exactly one site; every
                                       production/stock/BL record they
                                       create or see is implicitly filtered
                                       to it, with no switcher.
      - accountant / viewer         : `site` is OPTIONAL — set for
                                       site-only visibility, left None for
                                       company-wide (global) visibility.
      - qa_manager / qc_technician  : `site` unused (the quality module
                                       stays company-wide, functional spec
                                       §25.2 scope) — never bound, never
                                       shown a switcher.
    """

    ROLES = [
        ("manager", "Manager / Administrateur"),
        ("stock_prod", "Responsable Stock/Production"),
        ("accountant", "Comptable"),
        ("sales", "Commercial"),
        ("viewer", "Consultation seule"),
        ("qa_manager", "Responsable QA (Assurance Qualité)"),
        ("qc_technician", "Technicien QC (Contrôle Qualité)"),
    ]

    #: Roles that MUST be bound to exactly one site (mirrors avicole's
    #: ROLES_LIES_A_UNE_BRANCHE) — the field/site-operational roles that
    #: create the site-scoped documents (SupplierDN, ClientDN,
    #: ProductionOrder, StockAdjustment).
    SITE_REQUIRED_ROLES = ("stock_prod", "sales")

    #: Roles that MAY optionally be bound to one site — left blank means
    #: company-wide (global) visibility, mirrors avicole's comptable.
    SITE_OPTIONAL_ROLES = ("accountant", "viewer")

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="userprofile"
    )
    role = models.CharField(max_length=20, choices=ROLES, verbose_name="Rôle")
    # on_delete=CASCADE mirrors avicole's UserProfile.branche tradeoff:
    # deleting a ProductionSite from the admin is a deliberate wipe, and a
    # stock_prod/sales profile locked to only that site goes with it (the
    # underlying User row survives, profile-less) — reassign or recreate
    # the affected account's profile manually afterwards.
    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="userprofiles",
        verbose_name="Site de production",
        help_text=(
            "Obligatoire pour Responsable Stock/Production et Commercial. "
            "Optionnel pour Comptable et Consultation (vide = vue globale, "
            "toutes les sites). Toujours vide pour Manager."
        ),
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role in self.SITE_REQUIRED_ROLES and not self.site_id:
            raise ValidationError(
                {
                    "site": (
                        "Ce rôle nécessite un site de production obligatoire."
                    )
                }
            )
        if self.role == "manager" and self.site_id:
            raise ValidationError(
                {
                    "site": (
                        "Le manager n'est pas lié à un site unique — "
                        "laissez ce champ vide (le site actif se change "
                        "via le sélecteur de site en session)."
                    )
                }
            )
        if (
            self.role in ("qa_manager", "qc_technician")
            and self.site_id
        ):
            raise ValidationError(
                {
                    "site": (
                        "Ce rôle reste transverse à tous les sites "
                        "(module Qualité) — laissez ce champ vide."
                    )
                }
            )

    @property
    def has_global_view(self):
        """
        True when this user can see/aggregate site-scoped data across ALL
        sites (manager always; accountant/viewer only when left unbound) —
        mirrors avicole's `a_vue_globale` (BR-BRA-04).
        """
        return self.role == "manager" or (
            self.role in self.SITE_OPTIONAL_ROLES and self.site_id is None
        )

    @property
    def can_switch_site(self):
        """True for roles that get the active-site switcher in the UI."""
        return self.has_global_view

    # --- permission helpers ---

    def can_validate_supplier_dn(self):
        return self.role in ["manager", "stock_prod"]

    def can_create_supplier_invoice(self):
        return self.role in ["manager", "accountant"]

    def can_validate_production_order(self):
        return self.role in ["manager", "stock_prod"]

    def can_create_client_dn(self):
        return self.role in ["manager", "sales"]

    def can_validate_expense_above_threshold(self):
        return self.role == "manager"

    def can_access_financial_reports(self):
        return self.role in ["manager", "accountant", "viewer"]

    def can_manage_settings(self):
        return self.role == "manager"

    def can_manage_catalog(self):
        return self.role == "manager"

    def can_resolve_dispute(self):
        return self.role == "manager"

    # --- QA/QC Laboratory module (Section 2.3 permission matrix) ---

    def can_manage_quality_standards(self):
        """Define/edit Property Catalogue, Quality Specifications, Sampling Plans."""
        return self.role in ["qa_manager", "manager"]

    def can_perform_qc(self):
        """Draw a sample / record a test result."""
        return self.role in ["qa_manager", "qc_technician", "manager"]

    def can_override_qc_result(self):
        """BR-QA-08: only QA (or Manager override) may flip an automatic Fail."""
        return self.role in ["qa_manager", "manager"]

    def can_release_gate_a(self):
        """Release/disposition a DN line held for QC."""
        return self.role in ["qa_manager", "manager"]

    def can_release_gate_c(self):
        """Release finished goods to sellable stock after Gate C."""
        return self.role in ["qa_manager", "manager"]

    def can_place_production_hold(self):
        """Gate B: place a hold (QC places; QA/Manager can too)."""
        return self.role in ["qa_manager", "qc_technician", "manager"]

    def can_lift_production_hold(self):
        """Gate B: lift/acknowledge a hold — Production Manager (stock_prod) or QA."""
        return self.role in ["stock_prod", "qa_manager", "manager"]

    def can_open_ncr(self):
        return self.role in ["qa_manager", "qc_technician", "stock_prod", "manager"]

    def can_close_ncr(self):
        """BR-QA-09: only QA Manager (or Manager/Admin) may close an NCR."""
        return self.role in ["qa_manager", "manager"]

    def can_view_quality_dashboard(self):
        return self.role in ["qa_manager", "qc_technician", "stock_prod", "manager"]


# Auto-create profile when User is created
@receiver(models.signals.post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance, role="viewer")


@receiver(models.signals.post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "userprofile"):
        instance.userprofile.save()


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditLog(models.Model):
    """Immutable audit trail for all system actions.

    SPEC S2/BR-AUD-02:
      - Written by system only — no user-facing create/edit views.
      - action_type choices: create / update / validate / pay / cancel /
        login / failed_login  (no 'delete' — records are never deleted).
      - Implemented via AuditableMixin on tracked models, not inline in views.
    """

    ACTION_TYPES = [
        ("create", "Création"),
        ("update", "Modification"),
        ("validate", "Validation"),
        ("pay", "Paiement"),
        ("cancel", "Annulation"),
        ("login", "Connexion"),
        ("failed_login", "Échec connexion"),
        # NOTE: 'delete' is intentionally absent — the spec forbids deletion;
        # records are deactivated (is_active=False) instead.
    ]

    MODULES = [
        ("suppliers", "Fournisseurs"),
        ("clients", "Clients"),
        ("catalog", "Catalogue"),
        ("supplier_ops", "Opérations fournisseurs"),
        ("production", "Production"),
        ("stock", "Stock"),
        ("sales", "Ventes"),
        ("expenses", "Dépenses"),
        ("accounts", "Comptes"),
        ("settings_app", "Paramètres"),
        ("quality", "Qualité / Laboratoire"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Utilisateur")
    action_type = models.CharField(
        max_length=20, choices=ACTION_TYPES, verbose_name="Type d'action"
    )
    module = models.CharField(max_length=20, choices=MODULES, verbose_name="Module")

    # Plain char fields per spec — simpler than GenericForeignKey,
    # avoids ContentType dependency, matches spec field names exactly.
    entity_type = models.CharField(max_length=100, verbose_name="Type d'entité")
    entity_id = models.PositiveIntegerField(verbose_name="ID entité")
    entity_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence entité"
    )

    detail_json = models.TextField(verbose_name="Détails JSON")  # before/after snapshot
    ip_address = models.GenericIPAddressField(
        blank=True, null=True, verbose_name="Adresse IP"
    )

    class Meta:
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journaux d'audit"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp", "user"]),
            models.Index(fields=["module", "action_type"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return (
            f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} — "
            f"{self.user.username} — {self.get_action_type_display()}"
        )

    def get_details(self):
        try:
            return json.loads(self.detail_json)
        except Exception:
            return {}

    @classmethod
    def log_action(
        cls, user, action_type, module, instance, details=None, request=None
    ):
        """Central entry point for logging any system action."""
        if details is None:
            details = {}

        ip_address = None
        if request:
            x_fwd = request.META.get("HTTP_X_FORWARDED_FOR")
            ip_address = (
                x_fwd.split(",")[0] if x_fwd else request.META.get("REMOTE_ADDR")
            )

        entity_reference = ""
        if hasattr(instance, "reference"):
            entity_reference = str(instance.reference)
        elif hasattr(instance, "pk") and instance.pk:
            entity_reference = str(instance.pk)

        return cls.objects.create(
            user=user,
            action_type=action_type,
            module=module,
            entity_type=instance.__class__.__name__,
            entity_id=instance.pk,
            entity_reference=entity_reference,
            detail_json=json.dumps(details, default=str, ensure_ascii=False),
            ip_address=ip_address,
        )


# ---------------------------------------------------------------------------
# AuditableMixin
# ---------------------------------------------------------------------------


class AuditableMixin:
    """
    Mixin for tracked models.  Override `_audit_module` on the model class.

    Usage:
        class SupplierDN(AuditableMixin, models.Model):
            _audit_module = 'supplier_ops'
            ...

    Then in views, after a state-changing save:
        AuditLog.log_action(request.user, 'validate', 'supplier_ops',
                            instance, details={'status': 'validated'}, request=request)

    The mixin itself does NOT auto-write logs on every save (that would
    produce noise and prevent clean before/after snapshots).  Views are
    responsible for calling AuditLog.log_action() at the right moment.
    """

    _audit_module = "accounts"


# ---------------------------------------------------------------------------
# Auth signals → login / failed_login audit entries
# ---------------------------------------------------------------------------


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    AuditLog.log_action(
        user=user,
        action_type="login",
        module="accounts",
        instance=user,
        details={"username": user.username},
        request=request,
    )


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request, **kwargs):
    # No real User object — create a minimal stub for the log entry.
    # We use the system's first superuser as the log actor, or skip if none.
    try:
        system_user = User.objects.filter(is_superuser=True).first()
        if system_user:
            AuditLog.log_action(
                user=system_user,
                action_type="failed_login",
                module="accounts",
                instance=system_user,
                details={"username": credentials.get("username", "")},
                request=request,
            )
    except Exception:
        pass  # Never let audit failures crash authentication
