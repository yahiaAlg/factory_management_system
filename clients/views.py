# clients/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Client
from .forms import ClientForm


@login_required
def clients_list(request):
    clients = Client.objects.all()

    search = request.GET.get("search")
    if search:
        clients = clients.filter(
            Q(code__icontains=search)
            | Q(raison_sociale__icontains=search)
            | Q(nif__icontains=search)
            | Q(nis__icontains=search)
        )

    credit_status_filter = request.GET.get("credit_status")
    if credit_status_filter:
        clients = clients.filter(credit_status=credit_status_filter)

    wilaya_filter = request.GET.get("wilaya")
    if wilaya_filter:
        clients = clients.filter(wilaya=wilaya_filter)

    if request.GET.get("active") == "false":
        clients = clients.filter(is_active=False)
    elif request.GET.get("active") != "all":
        clients = clients.filter(is_active=True)

    wilayas = (
        Client.objects.values_list("wilaya", flat=True).distinct().exclude(wilaya="")
    )

    return render(
        request,
        "clients/clients_list.html",
        {
            "clients": clients.order_by("raison_sociale"),
            "wilayas": sorted(wilayas),
            "credit_statuses": Client.CREDIT_STATUS_CHOICES,
            "title": "Répertoire clients",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="clients",
                instance=client,
                request=request,
            )
            messages.success(request, f"Client {client.code} créé avec succès")
            return redirect("clients_list")
    else:
        form = ClientForm()

    return render(
        request, "clients/client_form.html", {"form": form, "title": "Nouveau client"}
    )


@login_required
def client_detail(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    current_year = timezone.now().year
    return render(
        request,
        "clients/client_detail.html",
        {
            "client": client,
            "recent_deliveries": client.get_recent_deliveries(10),
            "recent_invoices": client.get_recent_invoices(10),
            "total_sales_current_year": client.get_total_sales_amount(current_year),
            "total_sales_previous_year": client.get_total_sales_amount(
                current_year - 1
            ),
            "outstanding_balance": client.get_outstanding_balance(),
            "title": f"Client - {client.code}",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_edit(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            old_values = {
                "raison_sociale": client.raison_sociale,
                "address": client.address,
                "payment_terms": client.payment_terms,
                "credit_status": client.credit_status,
            }
            client = form.save()
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="clients",
                instance=client,
                details={
                    "before": old_values,
                    "after": {
                        "raison_sociale": client.raison_sociale,
                        "address": client.address,
                        "payment_terms": client.payment_terms,
                        "credit_status": client.credit_status,
                    },
                },
                request=request,
            )
            messages.success(request, f"Client {client.code} modifié avec succès")
            return redirect("client_detail", client_id=client.id)
    else:
        form = ClientForm(instance=client)

    return render(
        request,
        "clients/client_form.html",
        {
            "form": form,
            "client": client,
            "title": f"Modifier - {client.code}",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_toggle_active(request, client_id):
    """
    Toggle client active status.

    FIX: was a JsonResponse/AJAX endpoint — outside the 4 permitted AJAX cases (S5).
    Converted to a standard POST-Redirect-GET view.
    """
    if request.method == "POST":
        client = get_object_or_404(Client, id=client_id)
        old_status = client.is_active
        client.is_active = not client.is_active
        client.save()
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="clients",
            instance=client,
            details={
                "field_changed": "is_active",
                "before": old_status,
                "after": client.is_active,
            },
            request=request,
        )
        status_label = "activé" if client.is_active else "désactivé"
        messages.success(request, f"Client {client.code} {status_label}")

    return redirect("client_detail", client_id=client_id)


@login_required
@role_required(["manager"])
def client_update_credit_status(request, client_id):
    """
    Update client credit status.

    FIX: was a JsonResponse/AJAX endpoint — outside the 4 permitted AJAX cases (S5).
    Converted to a standard POST-Redirect-GET view.
    """
    if request.method == "POST":
        client = get_object_or_404(Client, id=client_id)
        new_status = request.POST.get("credit_status")

        if new_status not in dict(Client.CREDIT_STATUS_CHOICES):
            messages.error(request, "Statut de crédit invalide")
            return redirect("client_detail", client_id=client_id)

        old_status = client.credit_status
        client.credit_status = new_status
        client.save()
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="clients",
            instance=client,
            details={
                "field_changed": "credit_status",
                "before": old_status,
                "after": new_status,
            },
            request=request,
        )
        messages.success(request, "Statut crédit mis à jour")

    return redirect("client_detail", client_id=client_id)


# FIX: client_search_ajax REMOVED.
# A generic search/autocomplete JSON endpoint is not among the 4 permitted AJAX
# cases (S5).  Client dropdowns in forms are populated server-side via the
# queryset in ClientDNForm.__init__().
