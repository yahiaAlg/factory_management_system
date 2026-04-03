# accounts/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import UserProfile, AuditLog
from .forms import LoginForm, UserForm, UserProfileForm

def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                if user.userprofile.is_active:
                    login(request, user)
                    AuditLog.log_action(
                        user=user,
                        action_type='login',
                        module='accounts',
                        instance=user,
                        request=request
                    )
                    return redirect('dashboard')
                else:
                    messages.error(request, "Votre compte est désactivé")
                    AuditLog.log_action(
                        user=user,
                        action_type='failed_login',
                        module='accounts',
                        instance=user,
                        details={'reason': 'account_disabled'},
                        request=request
                    )
            else:
                messages.error(request, "Nom d'utilisateur ou mot de passe incorrect")
                # Try to find user for logging failed attempt
                try:
                    user = User.objects.get(username=username)
                    AuditLog.log_action(
                        user=user,
                        action_type='failed_login',
                        module='accounts',
                        instance=user,
                        details={'reason': 'invalid_credentials'},
                        request=request
                    )
                except User.DoesNotExist:
                    pass
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})

@login_required
def logout_view(request):
    """User logout view"""
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès")
    return redirect('login')

@login_required
def user_management(request):
    """User management view - Manager only"""
    if not request.user.userprofile.can_manage_settings():
        messages.error(request, "Accès non autorisé")
        return redirect('dashboard')
    
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        profile_form = UserProfileForm(request.POST)
        
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            profile.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='accounts',
                instance=user,
                details={'role': profile.role},
                request=request
            )
            
            messages.success(request, f"Utilisateur {user.username} créé avec succès")
            return redirect('user_management')
    else:
        user_form = UserForm()
        profile_form = UserProfileForm()
    
    users = User.objects.filter(userprofile__isnull=False).select_related('userprofile')
    
    return render(request, 'accounts/user_management.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'users': users,
        'title': 'Gestion des utilisateurs'
    })

@login_required
def toggle_user_status(request, user_id):
    """Toggle user active status via AJAX"""
    if not request.user.userprofile.can_manage_settings():
        return JsonResponse({'success': False, 'error': 'Accès non autorisé'})
    
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.userprofile.is_active = not user.userprofile.is_active
            user.userprofile.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='accounts',
                instance=user,
                details={'is_active': user.userprofile.is_active},
                request=request
            )
            
            return JsonResponse({
                'success': True, 
                'is_active': user.userprofile.is_active
            })
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Utilisateur non trouvé'})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

@login_required
def audit_log(request):
    """Audit log view - Manager only"""
    if not request.user.userprofile.can_manage_settings():
        messages.error(request, "Accès non autorisé")
        return redirect('dashboard')
    
    logs = AuditLog.objects.select_related('user', 'content_type').all()[:1000]
    
    # Filter by module if specified
    module_filter = request.GET.get('module')
    if module_filter:
        logs = logs.filter(module=module_filter)
    
    # Filter by action type if specified
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action_type=action_filter)
    
    # Filter by user if specified
    user_filter = request.GET.get('user')
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    
    context = {
        'logs': logs,
        'modules': AuditLog.MODULES,
        'actions': AuditLog.ACTION_TYPES,
        'users': User.objects.filter(userprofile__isnull=False),
        'title': 'Journal d\'audit'
    }
    
    return render(request, 'accounts/audit_log.html', context)