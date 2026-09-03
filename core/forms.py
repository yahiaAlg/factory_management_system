# core/forms.py
from django import forms
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from .models import CompanyInformation, SystemParameter, PieceJointe


class SiteLockedFormMixin:
    """
    Mixin for the four site-scoped create forms (ProductionOrderForm,
    StockAdjustmentForm, ClientDNForm, SupplierDNForm).

    Each of those forms already pops a `site=<ProductionSite>` kwarg in
    its own `__init__` to hide the field (`forms.HiddenInput()`) and must
    store it as `self._locked_site` before calling `super().__init__()`.
    This mixin's `clean()` then forces `cleaned_data["site"]` back to
    `self._locked_site` regardless of whatever value actually arrived in
    POST — a role-locked user (stock_prod/sales, or a site-bound
    accountant/viewer) must never be able to write into another site's
    records by tampering with the hidden input client-side. Mirrors
    avicole's BLFournisseurForm(branche=…) intent, but closes the gap
    where avicole trusts the hidden field's submitted value as-is.
    """

    _locked_site = None

    def clean(self):
        cleaned_data = super().clean()
        if self._locked_site is not None:
            cleaned_data["site"] = self._locked_site
        return cleaned_data


class CompanyInformationForm(forms.ModelForm):
    class Meta:
        model = CompanyInformation
        fields = [
            'raison_sociale', 'forme_juridique', 'nif', 'nis', 'rc', 'ai',
            'address', 'wilaya', 'phone', 'email',
            'bank_name', 'bank_account', 'rib', 'logo',
            'vat_rate', 'fiscal_regime'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'vat_rate': forms.NumberInput(attrs={'step': '0.0001', 'min': '0', 'max': '1'}),
            'logo': forms.FileInput(attrs={'accept': 'image/*'}),
        }

class SystemParameterForm(forms.ModelForm):
    class Meta:
        model = SystemParameter
        fields = ['category', 'key', 'value', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'value': forms.Textarea(attrs={'rows': 2}),
        }


# ---------------------------------------------------------------------------
# Site switcher (functional spec §25.2, extended to mirror avicole's
# BrancheSwitchForm, §3.5.4)
# ---------------------------------------------------------------------------


class SiteSwitchForm(forms.Form):
    """
    Non-model form backing the manager/unbound-accountant/unbound-viewer
    site switcher. Leaving `site` blank selects **toutes les sites** — the
    aggregate, read-only global view. Only roles with
    `profile.can_switch_site` (manager, or accountant/viewer left unbound)
    should ever be shown this form; stock_prod/sales are locked to their
    own site and never see a switcher.
    """

    site = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="🌐 Toutes les sites (vue globale)",
        label="Site actif",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import ProductionSite

        self.fields['site'].queryset = ProductionSite.objects.filter(
            is_active=True
        ).order_by('name')

# ---------------------------------------------------------------------------
# PieceJointe (generic document-proof model, core.models) — mirrors the
# avicole project's mechanism. Single source of truth for attachment
# validation and formset wiring, reused by every app that carries proof
# documents (SupplierDN, SupplierInvoice, SupplierPayment, ClientDN,
# ClientInvoice, ClientPayment, Expense, ...).
# ---------------------------------------------------------------------------

ALLOWED_ATTACHMENT_TYPES = ["application/pdf", "image/jpeg", "image/png"]
MAX_ATTACHMENT_SIZE_MB = 5


class PieceJointeForm(forms.ModelForm):
    """
    Single-file form for one PieceJointe row. Used standalone (quick "add a
    proof" action) or as the `form=` of the generic formset below (multi-
    file attach/replace on a document's create/edit page).
    """

    class Meta:
        model = PieceJointe
        fields = ["fichier", "type_document", "description"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Description courte"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type_document"].required = False
        self.fields["description"].required = False

    def clean_fichier(self):
        file = self.cleaned_data.get("fichier")
        if file and hasattr(file, "content_type"):
            if file.content_type not in ALLOWED_ATTACHMENT_TYPES:
                raise forms.ValidationError(
                    "Seuls les fichiers PDF, JPG et PNG sont acceptés."
                )
            if file.size > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f"La taille du fichier ne doit pas dépasser {MAX_ATTACHMENT_SIZE_MB} Mo."
                )
        return file


def make_piece_jointe_formset(extra: int = 1, max_num=10):
    """
    Build a generic-relation formset bound to PieceJointe for any parent
    model (SupplierDN, SupplierInvoice, Expense, ...).

    Usage in a view, mirroring a normal inline formset:
        FormSet = make_piece_jointe_formset(extra=2)
        formset = FormSet(request.POST or None, request.FILES or None, instance=dn)
        ...
        if header_form.is_valid() and formset.is_valid():
            dn = header_form.save()
            formset.instance = dn
            formset.save()
    """
    return generic_inlineformset_factory(
        PieceJointe,
        form=PieceJointeForm,
        ct_field="content_type",
        fk_field="object_id",
        extra=extra,
        can_delete=True,
        max_num=max_num,
        validate_max=bool(max_num),
    )


#: Default ready-to-use formset (extra=1) — fine for most single-proof cases.
PieceJointeFormSet = make_piece_jointe_formset()
