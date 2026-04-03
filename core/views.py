# core/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.utils import role_required
from .models import CompanyInformation, SystemParameter
from .forms import CompanyInformationForm, SystemParameterForm


@login_required
def dashboard(request):
    return render(request, "core/dashboard.html", {"title": "Tableau de bord"})


@login_required
@role_required(["manager"])
def company_settings(request):
    """
    FIX: replaced inline `if not role in ['manager']` check with @role_required
    decorator, consistent with S9 / accounts/utils.py contract.
    """
    company, _ = CompanyInformation.objects.get_or_create(
        defaults={"raison_sociale": "Ma Société", "address": "", "wilaya": ""}
    )

    if request.method == "POST":
        form = CompanyInformationForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Informations société mises à jour avec succès")
            return redirect("company_settings")
    else:
        form = CompanyInformationForm(instance=company)

    return render(
        request,
        "core/company_settings.html",
        {
            "form": form,
            "title": "Paramètres société",
        },
    )


@login_required
@role_required(["manager"])
def system_parameters(request):
    """
    FIX: replaced inline role check with @role_required decorator.
    FIX: update_parameter AJAX endpoint merged here as a standard POST action
         (editing an existing parameter by id) to stay within the POST-Redirect-GET
         pattern.  The separate update_parameter view is removed (outside S5 AJAX list).
    """
    if request.method == "POST":
        param_id = request.POST.get("param_id")
        if param_id:
            # Edit existing parameter
            parameter = get_object_or_404(SystemParameter, id=param_id)
            new_value = request.POST.get("value", "")
            parameter.value = new_value
            parameter.save()
            messages.success(request, f"Paramètre « {parameter.key} » mis à jour")
        else:
            # Create new parameter
            form = SystemParameterForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Paramètre ajouté avec succès")
            else:
                parameters = SystemParameter.objects.all().order_by("category", "key")
                return render(
                    request,
                    "core/system_parameters.html",
                    {
                        "form": form,
                        "parameters": parameters,
                        "title": "Paramètres système",
                    },
                )
        return redirect("system_parameters")

    form = SystemParameterForm()
    parameters = SystemParameter.objects.all().order_by("category", "key")
    return render(
        request,
        "core/system_parameters.html",
        {
            "form": form,
            "parameters": parameters,
            "title": "Paramètres système",
        },
    )


# FIX: update_parameter (AJAX/JsonResponse) REMOVED.
# Inline parameter value editing was a JsonResponse endpoint outside the 4
# permitted AJAX cases (S5).  The functionality is now handled by the POST
# branch of system_parameters() above using POST-Redirect-GET.
