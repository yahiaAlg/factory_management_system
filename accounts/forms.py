# accounts/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nom d\'utilisateur'
        }),
        label="Nom d'utilisateur"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        }),
        label="Mot de passe"
    )

class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(),
        label="Mot de passe"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(),
        label="Confirmer le mot de passe"
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Les mots de passe ne correspondent pas")
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

class UserProfileForm(forms.ModelForm):
    """
    Role & site-binding sub-form for user creation (S9), extended for the
    Multi-Site Architecture (functional spec §25.2, mirroring avicole's
    role-locked Branche pattern, §3.5.2).

    `site` queryset is limited to active ProductionSites. Its required-ness
    depends on the selected role (SITE_REQUIRED_ROLES / manager /
    qa_manager / qc_technician) — enforced in clean() since a plain
    ModelForm can't make a field conditionally required. The template
    shows/hides the site select via JS based on the chosen role.
    """

    class Meta:
        model = UserProfile
        fields = ['role', 'site', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import ProductionSite

        self.fields['site'].queryset = ProductionSite.objects.filter(
            is_active=True
        ).order_by('name')
        self.fields['site'].required = False
        self.fields['site'].empty_label = "🌐 Vue globale (toutes les sites)"

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        site = cleaned_data.get('site')

        if role in UserProfile.SITE_REQUIRED_ROLES and not site:
            self.add_error(
                'site',
                "Ce rôle nécessite un site de production obligatoire.",
            )
        if role == 'manager' and site:
            self.add_error(
                'site',
                "Le manager n'est pas lié à un site unique — laissez ce "
                "champ vide.",
            )
        if role in ('qa_manager', 'qc_technician') and site:
            self.add_error(
                'site',
                "Ce rôle reste transverse à tous les sites — laissez ce "
                "champ vide.",
            )
        return cleaned_data