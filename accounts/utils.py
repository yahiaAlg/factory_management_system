from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def role_required(allowed_roles):
    """Decorator to check user role permissions"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not hasattr(request.user, 'userprofile'):
                messages.error(request, "Profil utilisateur non configuré")
                return redirect('dashboard')
            
            if request.user.userprofile.role not in allowed_roles:
                messages.error(request, "Accès non autorisé pour votre rôle")
                return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def log_model_change(sender, instance, created, **kwargs):
    """Signal handler to log model changes"""
    from .models import AuditLog
    from django.contrib.auth import get_user
    
    # This would need to be connected to specific model signals
    # and have access to the request to get the current user
    pass