# core/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import CompanyInformation, SystemParameter
from .forms import CompanyInformationForm, SystemParameterForm

@login_required
def dashboard(request):
    """Main dashboard view"""
    # This would collect KPIs from various apps
    context = {
        'title': 'Tableau de bord'
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def company_settings(request):
    """Company information settings"""
    if not request.user.userprofile.role in ['manager']:
        messages.error(request, "Accès non autorisé")
        return redirect('dashboard')
    
    company, created = CompanyInformation.objects.get_or_create(
        defaults={'raison_sociale': 'Ma Société'}
    )
    
    if request.method == 'POST':
        form = CompanyInformationForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Informations société mises à jour avec succès")
            return redirect('company_settings')
    else:
        form = CompanyInformationForm(instance=company)
    
    return render(request, 'core/company_settings.html', {
        'form': form,
        'title': 'Paramètres société'
    })

@login_required
def system_parameters(request):
    """System parameters management"""
    if not request.user.userprofile.role in ['manager']:
        messages.error(request, "Accès non autorisé")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = SystemParameterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Paramètre ajouté avec succès")
            return redirect('system_parameters')
    else:
        form = SystemParameterForm()
    
    parameters = SystemParameter.objects.all().order_by('category', 'key')
    
    return render(request, 'core/system_parameters.html', {
        'form': form,
        'parameters': parameters,
        'title': 'Paramètres système'
    })

@login_required
def update_parameter(request, parameter_id):
    """Update system parameter via AJAX"""
    if not request.user.userprofile.role in ['manager']:
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'})
    
    if request.method == 'POST':
        try:
            parameter = SystemParameter.objects.get(id=parameter_id)
            parameter.value = request.POST.get('value', '')
            parameter.save()
            return JsonResponse({'success': True})
        except SystemParameter.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Paramètre non trouvé'})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})