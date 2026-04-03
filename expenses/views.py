# expenses/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Expense, SupportingDocument, ExpenseCategory
from .forms import ExpenseForm, SupportingDocumentForm


@login_required
def expenses_list(request):
    expenses = Expense.objects.select_related(
        "created_by", "validated_by", "category"
    ).all()

    search = request.GET.get("search")
    if search:
        expenses = expenses.filter(
            Q(reference__icontains=search)
            | Q(description__icontains=search)
            | Q(beneficiary__icontains=search)
        )

    category_filter = request.GET.get("category")
    if category_filter:
        # FIX: category is a FK to ExpenseCategory, not a char-choice field.
        expenses = expenses.filter(category_id=category_filter)

    status_filter = request.GET.get("status")
    if status_filter:
        expenses = expenses.filter(status=status_filter)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)

    if request.GET.get("pending_validation") == "true":
        expenses = expenses.filter(status="recorded")

    total_amount = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    validated_amount = expenses.filter(status__in=["validated", "paid"]).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    paid_amount = expenses.filter(status="paid").aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0.00")

    # FIX: Expense.CATEGORY_CHOICES does not exist — category is now a FK model.
    categories = ExpenseCategory.objects.filter(is_active=True).order_by(
        "order", "label"
    )

    return render(
        request,
        "expenses/expenses_list.html",
        {
            "expenses": expenses.order_by("-expense_date"),
            "categories": categories,
            "status_choices": Expense.STATUS_CHOICES,
            "total_amount": total_amount,
            "validated_amount": validated_amount,
            "paid_amount": paid_amount,
            "title": "Gestion des dépenses",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def expense_create(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="expenses",
                instance=expense,
                request=request,
            )
            messages.success(request, f"Dépense {expense.reference} créée avec succès")
            return redirect("expense_detail", expense_id=expense.id)
    else:
        form = ExpenseForm()

    return render(
        request,
        "expenses/expense_form.html",
        {"form": form, "title": "Nouvelle dépense"},
    )


@login_required
def expense_detail(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)
    supporting_docs = SupportingDocument.objects.filter(
        entity_type="expense", entity_id=expense.id
    )
    return render(
        request,
        "expenses/expense_detail.html",
        {
            "expense": expense,
            "supporting_docs": supporting_docs,
            "can_validate": (
                request.user.userprofile.role in ["manager", "accountant"]
                and expense.status == "recorded"
            ),
            "can_mark_paid": (
                request.user.userprofile.role in ["manager", "accountant"]
                and expense.status == "validated"
            ),
            "requires_manager": expense.requires_manager_approval(),
            "title": f"Dépense - {expense.reference}",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def expense_validate(request, expense_id):
    """
    Validate or reject an expense.

    FIX: original code only caught ValueError.  Expense.validate() raises
    PermissionError (BR-EXP-01 threshold exceeded, non-manager) and
    ValidationError (wrong status or missing SD-EXP).  Both are now caught.
    """
    expense = get_object_or_404(Expense, id=expense_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "validate":
            try:
                expense.validate(request.user)
                AuditLog.log_action(
                    user=request.user,
                    action_type="validate",
                    module="expenses",
                    instance=expense,
                    request=request,
                )
                messages.success(request, f"Dépense {expense.reference} validée")
            except PermissionError as e:
                # BR-EXP-01: amount above threshold, user is not Manager —
                # status stays 'recorded'; show informational message.
                messages.warning(request, str(e))
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))

        elif action == "reject":
            reason = request.POST.get("rejection_reason", "").strip()
            if not reason:
                messages.error(request, "Le motif de rejet est obligatoire")
                return redirect("expense_detail", expense_id=expense.id)
            try:
                expense.reject(request.user, reason)
                AuditLog.log_action(
                    user=request.user,
                    action_type="update",
                    module="expenses",
                    instance=expense,
                    details={"action": "reject", "reason": reason},
                    request=request,
                )
                messages.success(request, f"Dépense {expense.reference} rejetée")
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("expense_detail", expense_id=expense.id)


@login_required
@role_required(["manager", "accountant"])
def expense_mark_paid(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)

    if request.method == "POST":
        payment_date_str = request.POST.get("payment_date")
        payment_method = request.POST.get("payment_method")

        if not payment_date_str or not payment_method:
            messages.error(request, "Date et mode de paiement sont obligatoires")
            return redirect("expense_detail", expense_id=expense.id)

        try:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
            expense.mark_as_paid(request.user, payment_date, payment_method)
            AuditLog.log_action(
                user=request.user,
                action_type="pay",
                module="expenses",
                instance=expense,
                details={
                    "payment_date": str(payment_date),
                    "payment_method": payment_method,
                },
                request=request,
            )
            messages.success(
                request, f"Dépense {expense.reference} marquée comme payée"
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return redirect("expense_detail", expense_id=expense.id)


@login_required
@role_required(["manager", "accountant"])
def supporting_document_create(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)

    if request.method == "POST":
        form = SupportingDocumentForm(request.POST)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.entity_type = "expense"
            doc.entity_id = expense.id
            doc.registered_by = request.user
            doc.save()
            messages.success(request, "Document justificatif ajouté avec succès")
            return redirect("expense_detail", expense_id=expense.id)
    else:
        form = SupportingDocumentForm(initial={"doc_type": "SD-EXP"})

    return render(
        request,
        "expenses/supporting_document_form.html",
        {
            "form": form,
            "expense": expense,
            "title": f"Ajouter justificatif - {expense.reference}",
        },
    )


@login_required
def expenses_dashboard(request):
    current_month = timezone.now().replace(day=1)
    next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)

    monthly_recorded = Expense.objects.filter(
        expense_date__gte=current_month,
        expense_date__lt=next_month,
        status__in=["recorded", "validated", "paid"],
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    monthly_paid = Expense.objects.filter(
        expense_date__gte=current_month, expense_date__lt=next_month, status="paid"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    pending_validation = Expense.objects.filter(status="recorded")
    pending_amount = pending_validation.aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0.00")

    # FIX: Expense.CATEGORY_CHOICES does not exist.  Use ExpenseCategory FK objects.
    category_breakdown = {}
    for category in ExpenseCategory.objects.filter(is_active=True):
        amount = Expense.objects.filter(
            category=category,
            expense_date__gte=current_month,
            expense_date__lt=next_month,
            status__in=["validated", "paid"],
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        if amount > 0:
            category_breakdown[category.label] = amount

    overdue_validations = Expense.objects.filter(
        status="recorded",
        expense_date__lt=timezone.now().date() - timezone.timedelta(days=7),
    )

    return render(
        request,
        "expenses/expenses_dashboard.html",
        {
            "monthly_recorded": monthly_recorded,
            "monthly_paid": monthly_paid,
            "pending_amount": pending_amount,
            "pending_count": pending_validation.count(),
            "category_breakdown": category_breakdown,
            "recent_expenses": Expense.objects.select_related("created_by").order_by(
                "-created_at"
            )[:10],
            "overdue_validations": overdue_validations,
            "title": "Tableau de bord dépenses",
        },
    )


@login_required
def expenses_report(request):
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    expenses = Expense.objects.filter(status__in=["validated", "paid"])
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)

    # FIX: Expense.CATEGORY_CHOICES does not exist — query ExpenseCategory FK objects.
    category_totals = {}
    for category in ExpenseCategory.objects.filter(is_active=True):
        total = expenses.filter(category=category).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")
        if total > 0:
            category_totals[category.label] = total

    monthly_trend = []
    for i in range(12):
        month_date = timezone.now().replace(day=1) - timezone.timedelta(days=30 * i)
        next_month = (month_date + timezone.timedelta(days=32)).replace(day=1)
        monthly_total = Expense.objects.filter(
            expense_date__gte=month_date,
            expense_date__lt=next_month,
            status__in=["validated", "paid"],
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        monthly_trend.append(
            {"month": month_date.strftime("%Y-%m"), "total": monthly_total}
        )
    monthly_trend.reverse()

    top_beneficiaries = (
        expenses.values("beneficiary")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:10]
    )

    return render(
        request,
        "expenses/expenses_report.html",
        {
            "expenses": expenses.order_by("-expense_date")[:100],
            "category_totals": category_totals,
            "monthly_trend": monthly_trend,
            "top_beneficiaries": top_beneficiaries,
            "total_amount": sum(category_totals.values()),
            "title": "Rapport d'analyse des dépenses",
        },
    )
