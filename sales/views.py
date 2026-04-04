# sales/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import ClientDN, ClientDNLine, ClientInvoice, ClientPayment
from .forms import (
    ClientDNForm,
    ClientDNLineFormSet,
    ClientInvoiceForm,
    ClientPaymentForm,
)


@login_required
def client_dns_list(request):
    dns = ClientDN.objects.select_related("client", "validated_by").all()
    search = request.GET.get("search")
    if search:
        dns = dns.filter(
            Q(reference__icontains=search) | Q(client__raison_sociale__icontains=search)
        )
    status_filter = request.GET.get("status")
    if status_filter:
        dns = dns.filter(status=status_filter)
    client_filter = request.GET.get("client")
    if client_filter:
        dns = dns.filter(client_id=client_filter)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        dns = dns.filter(delivery_date__gte=date_from)
    if date_to:
        dns = dns.filter(delivery_date__lte=date_to)
    return render(
        request,
        "sales/client_dns_list.html",
        {
            "dns": dns.order_by("-delivery_date"),
            "status_choices": ClientDN.STATUS_CHOICES,
            "title": "Bons de livraison clients",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_dn_create(request):
    if request.method == "POST":
        form = ClientDNForm(request.POST)
        formset = ClientDNLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            formset.instance = dn
            formset.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="sales",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL Client {dn.reference} créé avec succès")
            return redirect("sales:client_dn_detail", dn_id=dn.id)
    else:
        form = ClientDNForm()
        formset = ClientDNLineFormSet()
    return render(
        request,
        "sales/client_dn_form.html",
        {"form": form, "formset": formset, "title": "Nouveau BL Client"},
    )


@login_required
def client_dn_detail(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    role = request.user.userprofile.role
    return render(
        request,
        "sales/client_dn_detail.html",
        {
            "dn": dn,
            "lines": dn.lines.select_related(
                "finished_product", "unit_of_measure"
            ).all(),
            "can_validate": role in ["manager", "sales"] and dn.status == "draft",
            "can_invoice": role in ["manager", "sales", "accountant"]
            and dn.can_be_invoiced(),
            "title": f"BL Client - {dn.reference}",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_dn_validate(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    if request.method == "POST":
        try:
            dn.validate(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="validate",
                module="sales",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL {dn.reference} validé avec succès")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
    return redirect("sales:client_dn_detail", dn_id=dn.id)


@login_required
def client_invoices_list(request):
    invoices = ClientInvoice.objects.select_related("client").all()
    search = request.GET.get("search")
    if search:
        invoices = invoices.filter(
            Q(reference__icontains=search) | Q(client__raison_sociale__icontains=search)
        )
    status_filter = request.GET.get("status")
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    if request.GET.get("overdue") == "true":
        invoices = invoices.filter(
            due_date__lt=timezone.now().date(), balance_due__gt=0
        )
    client_filter = request.GET.get("client")
    if client_filter:
        invoices = invoices.filter(client_id=client_filter)
    return render(
        request,
        "sales/client_invoices_list.html",
        {
            "invoices": invoices.order_by("-invoice_date"),
            "status_choices": ClientInvoice.STATUS_CHOICES,
            "title": "Factures clients",
        },
    )


@login_required
@role_required(["manager", "sales", "accountant"])
def client_invoice_create(request):
    if request.method == "POST":
        form = ClientInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            linked_dn_ids = request.POST.getlist("linked_dns")
            for dn_id in linked_dn_ids:
                try:
                    dn = ClientDN.objects.get(
                        id=dn_id, status="validated", linked_invoice__isnull=True
                    )
                    invoice.linked_dns.add(dn)
                    dn.linked_invoice = invoice
                    dn.status = "invoiced"
                    dn.save()
                except ClientDN.DoesNotExist:
                    pass
            if linked_dn_ids:
                invoice.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="sales",
                instance=invoice,
                request=request,
            )
            messages.success(request, f"Facture {invoice.reference} créée avec succès")
            return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    else:
        form = ClientInvoiceForm()
    return render(
        request,
        "sales/client_invoice_form.html",
        {"form": form, "title": "Nouvelle facture client"},
    )


@login_required
def client_invoice_detail(request, invoice_id):
    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    role = request.user.userprofile.role
    return render(
        request,
        "sales/client_invoice_detail.html",
        {
            "invoice": invoice,
            "linked_dns": invoice.linked_dns.all(),
            "payments": invoice.payments.all(),
            "can_collect": (
                role in ["manager", "accountant"]
                and invoice.balance_due > 0
                and invoice.status not in ["cancelled", "in_dispute"]
            ),
            "title": f"Facture Client - {invoice.reference}",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def client_payment_create(request, invoice_id):
    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    if invoice.balance_due <= 0:
        messages.error(request, "Cette facture est déjà entièrement payée")
        return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    if request.method == "POST":
        form = ClientPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.client_invoice = invoice
            payment.client = invoice.client
            payment.recorded_by = request.user
            if payment.amount > invoice.balance_due:
                messages.error(request, "Le montant ne peut pas dépasser le solde dû")
                return render(
                    request,
                    "sales/client_payment_form.html",
                    {
                        "form": form,
                        "invoice": invoice,
                        "title": f"Encaissement - {invoice.reference}",
                    },
                )
            payment.save()
            AuditLog.log_action(
                user=request.user,
                action_type="pay",
                module="sales",
                instance=payment,
                details={"invoice": invoice.reference, "amount": str(payment.amount)},
                request=request,
            )
            messages.success(request, f"Encaissement {payment.reference} enregistré")
            return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    else:
        form = ClientPaymentForm(initial={"amount": invoice.balance_due})
    return render(
        request,
        "sales/client_payment_form.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Encaissement - {invoice.reference}",
        },
    )


@login_required
def client_dn_print(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    return render(
        request,
        "sales/client_dn_print.html",
        {
            "dn": dn,
            "lines": dn.lines.select_related(
                "finished_product", "unit_of_measure"
            ).all(),
        },
    )


@login_required
def client_invoice_print(request, invoice_id):
    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    return render(
        request,
        "sales/client_invoice_print.html",
        {"invoice": invoice, "linked_dns": invoice.linked_dns.all()},
    )


@login_required
def client_payment_receipt_print(request, payment_id):
    payment = get_object_or_404(ClientPayment, id=payment_id)
    return render(
        request, "sales/client_payment_receipt_print.html", {"payment": payment}
    )


@login_required
def sales_dashboard(request):
    current_month = timezone.now().replace(day=1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)
    monthly_invoiced = ClientInvoice.objects.filter(
        invoice_date__gte=current_month, invoice_date__lt=next_month
    ).aggregate(total=Sum("total_ttc"))["total"] or Decimal("0.00")
    monthly_collected = ClientPayment.objects.filter(
        payment_date__gte=current_month, payment_date__lt=next_month
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    outstanding_receivables = ClientInvoice.objects.filter(balance_due__gt=0).aggregate(
        total=Sum("balance_due")
    )["total"] or Decimal("0.00")
    overdue_invoices = ClientInvoice.objects.filter(
        due_date__lt=timezone.now().date(), balance_due__gt=0
    )
    return render(
        request,
        "sales/sales_dashboard.html",
        {
            "monthly_invoiced": monthly_invoiced,
            "monthly_collected": monthly_collected,
            "outstanding_receivables": outstanding_receivables,
            "overdue_amount": overdue_invoices.aggregate(total=Sum("balance_due"))[
                "total"
            ]
            or Decimal("0.00"),
            "overdue_count": overdue_invoices.count(),
            "recent_dns": ClientDN.objects.select_related("client").order_by(
                "-created_at"
            )[:10],
            "recent_invoices": ClientInvoice.objects.select_related("client").order_by(
                "-created_at"
            )[:10],
            "recent_payments": ClientPayment.objects.select_related("client").order_by(
                "-created_at"
            )[:10],
            "title": "Tableau de bord commercial",
        },
    )
