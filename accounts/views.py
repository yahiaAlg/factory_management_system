# accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from accounts.utils import role_required
from .models import UserProfile, AuditLog
from .forms import LoginForm, UserForm, UserProfileForm


def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)

            if user is not None:
                if hasattr(user, "userprofile") and user.userprofile.is_active:
                    login(request, user)
                    # FIX: do NOT manually call AuditLog here for successful login.
                    # accounts/models.py on_user_logged_in signal (user_logged_in)
                    # already logs it — calling it here would create a duplicate entry.
                    return redirect("dashboard")
                else:
                    messages.error(request, "Votre compte est désactivé")
                    # Failed login due to disabled account — signal won't fire for
                    # inactive profiles since authenticate() succeeds.  Log manually.
                    AuditLog.log_action(
                        user=user,
                        action_type="failed_login",
                        module="accounts",
                        instance=user,
                        details={"reason": "account_disabled"},
                        request=request,
                    )
            else:
                messages.error(request, "Nom d'utilisateur ou mot de passe incorrect")
                # on_user_login_failed signal handles audit for unknown/wrong-password
                # attempts, so no manual call is needed here.
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    """User logout view"""
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès")
    return redirect("login")


@login_required
@role_required(["manager"])
def user_management(request):
    """User management view — Manager only (S9)"""
    if request.method == "POST":
        user_form = UserForm(request.POST)
        profile_form = UserProfileForm(request.POST)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            # FIX: auto-created profile (via post_save signal) must be updated,
            # not saved as a new record, to avoid duplicate OneToOne violation.
            profile = user.userprofile
            profile.role = profile_form.cleaned_data["role"]
            profile.is_active = profile_form.cleaned_data["is_active"]
            profile.save()

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="accounts",
                instance=user,
                details={"role": profile.role},
                request=request,
            )

            messages.success(request, f"Utilisateur {user.username} créé avec succès")
            return redirect("user_management")
    else:
        user_form = UserForm()
        profile_form = UserProfileForm()

    users = User.objects.filter(userprofile__isnull=False).select_related("userprofile")

    return render(
        request,
        "accounts/user_management.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
            "users": users,
            "title": "Gestion des utilisateurs",
        },
    )


@login_required
@role_required(["manager"])
def toggle_user_status(request, user_id):
    """
    Toggle user active status.

    FIX: was a JsonResponse / AJAX endpoint — outside the 4 permitted AJAX
    cases (S5).  Converted to a standard POST-Redirect-GET view.
    """
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        user.userprofile.is_active = not user.userprofile.is_active
        user.userprofile.save()

        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="accounts",
            instance=user,
            details={"is_active": user.userprofile.is_active},
            request=request,
        )

        status_label = "activé" if user.userprofile.is_active else "désactivé"
        messages.success(request, f"Utilisateur {user.username} {status_label}")

    return redirect("user_management")


@login_required
@role_required(["manager"])
def audit_log(request):
    """Audit log view — Manager only (S9)"""
    # FIX: apply filters BEFORE slicing; original code sliced first then filtered,
    # which silently returned wrong (or empty) results.
    # FIX: removed 'content_type' from select_related — AuditLog has no such field.
    logs = AuditLog.objects.select_related("user").all()

    module_filter = request.GET.get("module")
    if module_filter:
        logs = logs.filter(module=module_filter)

    action_filter = request.GET.get("action")
    if action_filter:
        logs = logs.filter(action_type=action_filter)

    user_filter = request.GET.get("user")
    if user_filter:
        logs = logs.filter(user_id=user_filter)

    logs = logs[:1000]

    context = {
        "logs": logs,
        "modules": AuditLog.MODULES,
        "actions": AuditLog.ACTION_TYPES,
        "users": User.objects.filter(userprofile__isnull=False),
        "title": "Journal d'audit",
    }

    return render(request, "accounts/audit_log.html", context)
