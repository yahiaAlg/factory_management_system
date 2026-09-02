# Factory Management System — Functional Specification

> **Version:** 1.0 — Generated 2026-05-07  
> **Stack:** Django (Python) · PostgreSQL · DZD currency  
> **Locale:** Algeria (wilaya, NIF/NIS/RC/AI fiscal identifiers, TVA 19%)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Module Map](#2-architecture--module-map)
3. [User Roles & Permissions](#3-user-roles--permissions)
4. [Core Infrastructure](#4-core-infrastructure)
   - 4.1 [Company Information (Singleton)](#41-company-information-singleton)
   - 4.2 [System Parameters](#42-system-parameters)
   - 4.3 [Document Sequences](#43-document-sequences)
   - 4.4 [Audit Log](#44-audit-log)
5. [Module: Catalog](#5-module-catalog)
   - 5.1 [Units of Measure](#51-units-of-measure)
   - 5.2 [Raw Materials](#52-raw-materials)
   - 5.3 [Finished Products](#53-finished-products)
6. [Module: Suppliers](#6-module-suppliers)
7. [Module: Clients](#7-module-clients)
8. [Module: Supplier Operations](#8-module-supplier-operations)
   - 8.1 [Supplier Delivery Notes (BL-F)](#81-supplier-delivery-notes-bl-f)
   - 8.2 [Supplier Invoices](#82-supplier-invoices)
   - 8.3 [Supplier Payments & FIFO Settlement](#83-supplier-payments--fifo-settlement)
9. [Module: Production](#9-module-production)
   - 9.1 [Formulations](#91-formulations)
   - 9.2 [Production Orders (OP)](#92-production-orders-op)
10. [Module: Stock](#10-module-stock)
    - 10.1 [Stock Balances](#101-stock-balances)
    - 10.2 [Stock Movements](#102-stock-movements)
    - 10.3 [Stock Adjustments](#103-stock-adjustments)
11. [Module: Sales](#11-module-sales)
    - 11.1 [Client Delivery Notes (BL-C)](#111-client-delivery-notes-bl-c)
    - 11.2 [Client Invoices](#112-client-invoices)
    - 11.3 [Client Payments](#113-client-payments)
12. [Module: Expenses](#12-module-expenses)
13. [Module: Reporting](#13-module-reporting)
14. [Signal Architecture & Stock Update Flows](#14-signal-architecture--stock-update-flows)
15. [Business Rules Reference](#15-business-rules-reference)
16. [Document Reference Numbering](#16-document-reference-numbering)
17. [URL Map Summary](#17-url-map-summary)
18. [Known Fixes & Technical Debt](#18-known-fixes--technical-debt)

---

## 1. Project Overview

This is a **full-stack ERP-style factory management application** built with Django, designed for an Algerian manufacturing company. It manages the complete operational and financial lifecycle of a factory: raw material procurement → production → finished goods inventory → client sales → invoicing → reporting.

**Core design principles:**

- **Immutability of records:** Nothing is ever deleted. Records are deactivated (`is_active=False`) or cancelled (`status='cancelled'`). Stock movements are a permanently immutable audit trail.
- **Signal-driven stock accounting:** Stock balances are never written from forms or views directly. All balance updates flow through `StockMovement.save()` which calls `update_stock_balance()` atomically.
- **Role-based access control:** Five user roles enforce who can validate documents, access financial data, or manage settings.
- **Algerian fiscal context:** All identifiers (NIF, NIS, RC, AI, wilaya), document references, and TVA calculations follow Algerian business conventions.

---

## 2. Architecture & Module Map

```
config/          ← Django project root
│
├── accounts/                ← Authentication, user profiles, audit log
├── catalog/                 ← Master data: raw materials, finished products, UoM
├── suppliers/               ← Supplier directory
├── clients/                 ← Client directory & credit management
├── supplier_ops/            ← Supplier DNs, invoices, payments, FIFO settlement
├── production/              ← Formulations, production orders
├── stock/                   ← Stock balances, movements, adjustments
├── sales/                   ← Client DNs, invoices, payments
├── expenses/                ← Operational expense management
├── reporting/               ← Financial periods, report templates, KPIs
└── core/                    ← Company info, system parameters, document sequences
```

**URL mounting** (from `config_urls.py`):

| Prefix               | App          |
| -------------------- | ------------ |
| `/admin/`            | Django admin |
| `/accounts/`         | accounts     |
| `/catalog/`          | catalog      |
| `/suppliers/`        | suppliers    |
| `/clients/`          | clients      |
| `/supplier-ops/`     | supplier_ops |
| `/production/`       | production   |
| `/stock/`            | stock        |
| `/sales/`            | sales        |
| `/expenses/`         | expenses     |
| `/reporting/`        | reporting    |
| `/settings/` and `/` | core         |

---

## 3. User Roles & Permissions

Every user gets a `UserProfile` (auto-created via `post_save` signal) with one of five roles:

| Role               | Code         | Key Capabilities                                                                                    |
| ------------------ | ------------ | --------------------------------------------------------------------------------------------------- |
| Manager / Admin    | `manager`    | All permissions including settings, catalog, dispute resolution, above-threshold expense validation |
| Stock & Production | `stock_prod` | Validate supplier DNs, validate production orders                                                   |
| Accountant         | `accountant` | Create supplier invoices, access financial reports                                                  |
| Sales              | `sales`      | Create client delivery notes                                                                        |
| View only          | `viewer`     | Read-only access to financial reports                                                               |

**Permission helpers on `UserProfile`:**

- `can_validate_supplier_dn()` → manager, stock_prod
- `can_create_supplier_invoice()` → manager, accountant
- `can_validate_production_order()` → manager, stock_prod
- `can_create_client_dn()` → manager, sales
- `can_validate_expense_above_threshold()` → manager only
- `can_access_financial_reports()` → manager, accountant, viewer
- `can_manage_settings()` → manager only
- `can_manage_catalog()` → manager only
- `can_resolve_dispute()` → manager only

New users default to the `viewer` role.

---

## 4. Core Infrastructure

### 4.1 Company Information (Singleton)

`CompanyInformation` holds the company's legal identity used on all printed documents: raison sociale, forme juridique, NIF, NIS, RC, AI, address, wilaya, phone, email, bank details, logo, and the active VAT rate (`vat_rate`, default 19%).

Only one record is permitted. Attempting to create a second raises `ValueError`.

### 4.2 System Parameters

`SystemParameter` is a key-value store for runtime configuration, organized by category (financial, stock, production, alert, document).

**Required seed values (spec S2):**

| Key                                | Type    | Default       | Purpose                                 |
| ---------------------------------- | ------- | ------------- | --------------------------------------- |
| `reconciliation_tolerance_epsilon` | Decimal | 500.00 DZD    | Invoice-DN reconciliation tolerance     |
| `reconciliation_dispute_delta`     | Decimal | 5 000.00 DZD  | Threshold for auto-dispute              |
| `expense_delegation_threshold`     | Decimal | 50 000.00 DZD | Manager approval required above this    |
| `yield_warning_threshold`          | Decimal | 90.00 %       | Production yield warning level          |
| `yield_critical_threshold`         | Decimal | 80.00 %       | Production yield critical level         |
| `payment_due_alert_days`           | int     | 7             | Days before due date for payment alerts |
| `default_vat_rate`                 | Decimal | 0.19          | TVA rate                                |
| `current_year`                     | int     | current year  | Fiscal year for sequences               |

Access helpers: `get_value()`, `get_decimal_value()`, `get_int_value()`.

### 4.3 Document Sequences

`DocumentSequence` provides thread-safe, sequential reference number generation using `select_for_update()` inside `transaction.atomic()` to prevent duplicate references under concurrent requests.

**Reference formats:**

| Prefix  | Pattern              | Example           | Used for                         |
| ------- | -------------------- | ----------------- | -------------------------------- |
| `RM`    | `RM-NNN` (year-less) | `RM-042`          | Raw materials                    |
| `PF`    | `PF-NNN` (year-less) | `PF-007`          | Finished products (Produit Fini) |
| `F`     | `F-NNN` (year-less)  | `F-015`           | Formulations                     |
| `BL-F`  | `BL-F-YYYY-NNNN`     | `BL-F-2026-0031`  | Supplier delivery notes          |
| `BL-C`  | `BL-C-YYYY-NNNN`     | `BL-C-2026-0012`  | Client delivery notes            |
| `FC`    | `FC-YYYY-NNNN`       | `FC-2026-0008`    | Client invoices (Facture Client) |
| `OP`    | `OP-YYYY-NNNN`       | `OP-2026-0005`    | Production orders                |
| `DEP`   | `DEP-YYYY-NNNN`      | `DEP-2026-0019`   | Expenses (Dépense)               |
| `ADJ`   | `ADJ-YYYY-NNNN`      | `ADJ-2026-0003`   | Stock adjustments                |
| `PAY-C` | `PAY-C-YYYY-NNNN`    | `PAY-C-2026-0006` | Client payments                  |
| `RGL-F` | `RGL-F-YYYY-NNNN`    | `RGL-F-2026-0004` | Supplier account settlements     |

Year-less sequences use `current_year=0` as a sentinel. All references are **immutable** after creation — model `save()` raises `ValidationError` if mutation is attempted.

### 4.4 Audit Log

`AuditLog` is the system's immutable event trail (spec S2 / BR-AUD-02). Written by the system only — no user-facing create or edit views.

**Recorded action types:** create, update, validate, pay, cancel, login, failed_login.  
(`delete` is intentionally absent — records are never deleted.)

**Tracked modules:** suppliers, clients, catalog, supplier_ops, production, stock, sales, expenses, accounts, settings_app.

Each log entry captures: timestamp, user, action_type, module, entity_type, entity_id, entity_reference, a before/after JSON snapshot (`detail_json`), and the requester's IP address.

**Usage pattern:** Models inherit `AuditableMixin` (which sets `_audit_module`). Views call `AuditLog.log_action()` explicitly after state-changing operations.

Login and failed login events are captured automatically via Django auth signals.

---

## 5. Module: Catalog

### 5.1 Units of Measure

`UnitOfMeasure`: code, name, symbol (e.g. `kg`, kilogramme, kg). Soft-deactivatable.

### 5.2 Raw Materials

`RawMaterial` is the master record for all input materials.

**Key rules:**

- Reference (`RM-NNN`) is auto-generated and **immutable** after creation (`editable=False`; `save()` blocks mutation).
- `unit_of_measure` is **immutable** once any `SupplierDNLine` or `FormulationLine` references this material (`clean()` enforces this).
- `alert_threshold` must be **strictly greater** than `stockout_threshold` (`clean()` enforces this).
- `reference_price` is used for valuation in production cost calculations.
- Deactivation only — never deleted.

**Stock status** is derived by comparing the material's current stock balance against its thresholds: `ok`, `alert`, or `stockout`.

### 5.3 Finished Products

`FinishedProduct` is the master record for products manufactured and sold.

**Key fields:** reference (`PF-NNN`), designation, category, sales_unit, production_unit, selling_price_ht, alert_threshold, stockout_threshold.

The same immutability rules as raw materials apply to the reference. Finished products are soft-deactivatable via dedicated `/activate/` and `/deactivate/` endpoints.

An AJAX endpoint (`/catalog/finished-products/quick-create/`) supports inline creation from production and sales forms.

---

## 6. Module: Suppliers

`Supplier` is the master directory for all suppliers.

**Key fields:** code (unique), raison_sociale, forme_juridique, NIF/NIS/RC/AI, address, wilaya, phone/fax/email, contact_person, `payment_terms` (days, default 30), `currency` (DZD/EUR/USD), bank details (bank_name, bank_account, RIB), `is_active`.

**Computed methods:**

- `get_outstanding_balance()` — sum of `balance_due` on open invoices (verified/unpaid/partially_paid)
- `get_total_purchases_amount(year=None)` — total TTC of supplier invoices
- `has_fiscal_identifier()` — True if any of NIF/NIS/RC/AI is populated

Deactivation only via `/suppliers/<id>/toggle-active/`.

---

## 7. Module: Clients

`Client` mirrors the `Supplier` structure but adds **credit management**.

**Additional fields:** `payment_terms`, `credit_limit`, `credit_status`.

**Credit statuses:**

- `active` — normal trading
- `suspended` — can still place orders but under watch
- `blocked` — validation of new delivery notes is blocked (enforced in BR-CDN-01)

**Computed methods:**

- `get_outstanding_balance()` — sum of `balance_due` on issued/partially_paid invoices
- `can_place_order()` — True if credit_status in (active, suspended) and is_active

Credit status can be updated via `/clients/<id>/update-credit-status/`.

---

## 8. Module: Supplier Operations

### 8.1 Supplier Delivery Notes (BL-F)

`SupplierDN` records the physical receipt of raw materials from a supplier.

**Reference format:** `BL-F-YYYY-NNNN` (auto-generated, immutable).

**Status lifecycle and valid transitions:**

```
draft → pending → validated
              ↓         ↓
          cancelled  in_dispute → pending
draft → cancelled
```

**Key business rules:**

- `total_amount_ht` is a cached computed field (sum of lines × agreed unit prices), updated in `save()` and by `SupplierDNLine.save()` via a direct `filter().update()` call. It is `editable=False` and never accepted from POST data.
- Stock movements for raw materials are created **only on validation**, via the `supplier_ops/signals.py` `post_save` handler — not in `validate()` directly (keeping the model free of stock-layer imports).
- The signal has an idempotency guard: duplicate movements are blocked by checking for an existing `StockMovement` with the same `source_document_type`, `source_document_id`, and `source_line_id`.

**`SupplierDNLine` fields:** raw_material, quantity_received, agreed_unit_price, remarks. `line_total_ht` is a computed property.

### 8.2 Supplier Invoices

`SupplierInvoice` records the financial obligation created by receiving supplier goods.

**Key fields:** reference, supplier, invoice_date, due_date (auto-calculated from `supplier.payment_terms`), total_ht, vat_amount, total_ttc, balance_due, status.

**Statuses:** draft → verified → unpaid → partially_paid → paid / in_dispute / cancelled.

`balance_due` is recomputed by `recompute_balance_due()` after every payment. Status transitions automatically: fully paid → `paid`, partially paid → `partially_paid`.

Cancellation blocked if any payments exist (`clean()` enforces this).

### 8.3 Supplier Payments & FIFO Settlement

Two payment paths exist:

**Direct payment (`SupplierPayment`):** Records a single payment against a specific invoice. A `post_save` signal (`supplier_payment_post_save`) calls `invoice.recompute_balance_due()` after each save.

**Account settlement (`SupplierAccountSettlement` + `settle_fifo()`):** A lump-sum payment applied to the supplier's oldest open invoices first (FIFO). Ordered by `due_date ASC`, then `invoice_date ASC`. Uses `select_for_update()` for concurrency safety. Creates one `SupplierPayment` per invoice touched and calls `recompute_balance_due()` on each. Returns a list of `{"invoice": ..., "applied": ...}` dicts for confirmation display.

URL: `POST /supplier-ops/suppliers/<supplier_id>/settle/`.

---

## 9. Module: Production

### 9.1 Formulations

`Formulation` defines the recipe for making a finished product.

**Key fields:** reference (`F-NNN`), name, finished_product, reference_batch_qty (the quantity produced by one "batch"), is_active, version.

**`FormulationLine`** (related name `lines`): raw_material, qty_per_batch, tolerance_pct (default 5%).

A formulation must have at least one line. Lines are the basis for scaling when a Production Order is created.

AJAX endpoint for batch scaling previews: `GET /production/formulation-scaling/`.

### 9.2 Production Orders (OP)

`ProductionOrder` records the intent and execution of a production run.

**Reference format:** `OP-YYYY-NNNN`.

**Status lifecycle:**

```
draft → launched → completed
      ↓
   cancelled
```

**Statuses:** draft, launched, completed, cancelled.

**Creation (`create()`):** Scales formulation lines to `target_qty` and creates `ProductionOrderLine` records (one per raw material). `qty_theoretical` on each line is computed from `formulation_line.qty_per_batch × (target_qty / reference_batch_qty)` and is `editable=False`.

**Launch (`launch()`):** Checks stock availability for all theoretical quantities. If any raw material is insufficient, launch is blocked and a detailed shortage report is returned. On success, status → `launched`.

**Closure (`close()`):**

1. `actual_qty_produced` is set.
2. The PO's `closure_date` and `closed_by` are recorded.
3. `self.save()` is called — this fires **Signal A** (finished-goods stock credit).
4. Each `ProductionOrderLine.qty_actual` is set and `line.save()` is called — this fires **Signal B** (raw-material consumption deduction) once per line.

**Cost calculation:**

- `calculate_batch_cost()` — `Σ (qty_actual × reference_price)` per line.
- `get_unit_cost()` — `batch_cost / actual_qty_produced`.

**`ProductionOrderLine`** computed properties (never stored per spec S3):

- `delta_qty` = `qty_actual - qty_theoretical`
- `financial_impact` = `delta_qty × reference_price`
- `is_within_tolerance()` — True if `|delta_qty| ≤ qty_theoretical × tolerance_pct / 100`
- `get_variance_percentage()`

---

## 10. Module: Stock

### 10.1 Stock Balances

Two balance tables maintain the current live stock quantity:

**`RawMaterialStockBalance`** (one row per raw material):

- `quantity` — editable=False; updated only via `StockMovement.save() → update_stock_balance()`
- `last_movement_date`

**`FinishedProductStockBalance`** (one row per finished product):

- `quantity` — same constraint
- `weighted_average_cost` (WAC) — recomputed from all production-type movements after each new movement via `update_weighted_average_cost()`

Both records are auto-created by `get_or_create()` inside `update_stock_balance()` on first movement.

### 10.2 Stock Movements

`StockMovement` is the **immutable audit trail** for all stock changes (spec BR-RM-05). Records are never deleted.

**Movement types:** receipt, consumption, production, delivery, adjustment, opening, return, loss.

**Source document types:** supplier_dn, production_order, client_dn, adjustment, opening.

Each movement stores: raw_material OR finished_product (exactly one must be set — enforced in `save()`), movement_type, quantity (positive = inflow, negative = outflow), unit_price or unit_cost, source_document_type, source_document_id, source_line_id, movement_date, created_by, remarks.

`StockMovement.save()` calls `update_stock_balance()` directly, which recalculates the balance from the sum of all movements for that item. This means balances are always consistent with movement history.

**Permitted creation paths only (BR-RM-05):**

1. Supplier DN validation → `supplier_ops/signals.py`
2. Production Order closure → `production/signals.py` (two signals: FG credit + RM deductions)
3. Client DN validation → `sales/signals.py`
4. `StockAdjustment.approve()`

### 10.3 Stock Adjustments

`StockAdjustment` allows inventory corrections with manager approval.

**Adjustment types:** inventory, correction, loss, damage, return.

**Reference format:** `ADJ-YYYY-NNNN`.

`approve(user)` creates one `StockMovement` per `StockAdjustmentLine`, using `quantity_after - quantity_before` as the adjustment quantity (computed property, never stored).

Stock alerts dashboard available at `/stock/alerts/`.

---

## 11. Module: Sales

### 11.1 Client Delivery Notes (BL-C)

`ClientDN` records the physical delivery of finished products to a client.

**Reference format:** `BL-C-YYYY-NNNN`.

**Status lifecycle:**

```
draft → validated → delivered → invoiced
  ↓          ↓           ↓
cancelled  cancelled  cancelled
```

**Key business rules:**

- **BR-CDN-01:** Validation blocked if `client.credit_status == 'blocked'`.
- **BR-CDN-02:** Validation blocked if any line quantity exceeds the current finished product stock balance (checked atomically).
- Finished goods stock deductions happen **only on validation**, via the `sales/signals.py` `post_save` handler. The signal has an idempotency guard.

`total_ht` is cached and recalculated on each save from `Σ(line.line_amount) × (1 - discount_pct/100)`.

**`ClientDNLine`:** finished_product, quantity_delivered, selling_unit_price_ht. `line_amount` is a computed property.

### 11.2 Client Invoices

`ClientInvoice` is the financial document consolidating one or more delivered `ClientDN`s.

**Reference format:** `FC-YYYY-NNNN`.

**Statuses:** issued, partially_paid, paid, in_dispute, cancelled.

`due_date` is auto-calculated as `invoice_date + client.payment_terms` days if not explicitly provided.

**Totals computation (`_recompute_totals()`):**

- `total_ht` = sum of linked DNs' `total_ht`
- `net_ht` = `total_ht × (1 - discount_pct/100)` (property, not stored)
- `vat_amount` = `net_ht × vat_rate` (from CompanyInformation)
- `total_ttc` = `net_ht + vat_amount`
- `balance_due` = `total_ttc - Σ(payments.amount)`

`balance_due` is **editable=False** and **never form-editable**. It is recomputed by `recompute_balance_due()` after each `ClientPayment` save.

Cancellation blocked if any payments exist.

### 11.3 Client Payments

`ClientPayment` records a payment received from a client against a specific invoice.

**Reference format:** `PAY-C-YYYY-NNNN`.

**Payment methods:** cash, transfer, cheque, bill (effet de commerce), card.

After save, a `post_save` signal calls `invoice.recompute_balance_due()`, which updates `balance_due` and transitions status to `paid` (if balance ≤ 0) or `partially_paid` (if partially collected), using a direct `filter().update()` to avoid signal re-entrancy.

`is_overdue()` and `days_overdue()` helpers support aging reports and alerts.

---

## 12. Module: Expenses

`Expense` manages all operational expenses outside of supplier invoices.

**Reference format:** `DEP-YYYY-NNNN`.

**Statuses:** recorded → validated → paid / rejected.

**Key business rules (spec BR-EXP-01):**

- If `amount > expense_delegation_threshold` (default 50 000 DZD) **and** the validating user is not Manager: status stays `recorded`, a `PermissionError` is raised for the view to display a message. Status is NOT changed.
- If Manager is validating an above-threshold expense: a supporting document of type `SD-EXP` must be attached first (hard gate per spec S2). Raises `ValidationError` if missing.
- Below-threshold expenses can be validated by any authorized user.

**Actions on `Expense`:**

- `validate(user)` — transitions to `validated`
- `reject(user, reason)` — transitions to `rejected` (from recorded or validated)
- `mark_as_paid(user, payment_date, payment_method)` — transitions to `paid` (from validated only)

`SupportingDocument` (type `SD-EXP`) is attached to an expense before Manager validation of above-threshold amounts.

An expense can optionally be linked to a `SupplierInvoice` (`linked_supplier_invoice`).

`ExpenseCategory` (code, label, order) is managed via admin or seed data. Active categories only are available in forms.

---

## 13. Module: Reporting

### Financial Periods

`FinancialPeriod` (monthly, quarterly, annual, or custom) groups reporting data by date range. Periods can be closed (`is_closed=True`) to freeze data.

`get_financial_summary()` computes for a period:

- Invoiced vs. collected revenue (from `ClientInvoice` / `ClientPayment`)
- Committed vs. paid supplier charges (from `SupplierInvoice` / `SupplierPayment`)
- Committed vs. paid operational expenses (from `Expense`)
- Theoretical result = invoiced revenue − total committed charges
- Actual cash result = collected revenue − total paid charges
- Collection rate and settlement rate percentages

### Report Types

`ReportTemplate` stores reusable parameterized report configurations. `ReportExecution` tracks execution history with status (running / completed / failed) and stores result data as JSON.

**Available report types:** financial_result, receivables_aging, payables_aging, production_yield, expense_breakdown, stock_valuation, sales_analysis, supplier_analysis.

**Reporting routes:**

| URL                                    | Report                        |
| -------------------------------------- | ----------------------------- |
| `/reporting/financial-result/`         | P&L summary                   |
| `/reporting/receivables-aging/`        | Client aging schedule         |
| `/reporting/payables-aging/`           | Supplier aging schedule       |
| `/reporting/production-yield/`         | Yield analysis                |
| `/reporting/expense-breakdown/`        | Expense breakdown by category |
| `/reporting/stock-valuation/`          | Stock valuation (RM + FG)     |
| `/reporting/export/<report_type>/csv/` | CSV export                    |
| `/reporting/kpi-dashboard/`            | AJAX KPI dashboard            |

---

## 14. Signal Architecture & Stock Update Flows

The signal layer is the **single authorized path** for all stock balance changes. No view or form may write to `RawMaterialStockBalance`, `FinishedProductStockBalance`, or `StockMovement` directly.

### Flow 1 — Supplier Receipt (RM inflow)

```
SupplierDN.validate()
  └─ self.save()  [status → 'validated']
       └─ post_save(SupplierDN) → update_stock_on_dn_validation()
            └─ for each line: StockMovement.create(type='receipt', qty=+line.quantity_received)
                 └─ StockMovement.save() → update_stock_balance()
                      └─ RawMaterialStockBalance.quantity updated
```

### Flow 2 — Production Closure (RM outflow + FG inflow)

```
ProductionOrder.close()
  ├─ self.save()  [status → 'completed', actual_qty_produced set]
  │    └─ Signal A: post_save(ProductionOrder) → create_fg_movement_on_po_completion()
  │         └─ StockMovement.create(type='production', qty=+actual_qty_produced, unit_cost=get_unit_cost())
  │              └─ FinishedProductStockBalance.quantity updated + WAC recomputed
  │
  └─ for each line: line.qty_actual = x; line.save()
       └─ Signal B: post_save(ProductionOrderLine) → create_rm_consumption_on_line_save()
            └─ StockMovement.create(type='consumption', qty=-line.qty_actual)
                 └─ RawMaterialStockBalance.quantity updated
```

> **Note on the timing fix:** The original design had a single `post_save` on `ProductionOrder` that tried to read `qty_actual` from lines — but lines were saved _after_ the PO, so `qty_actual` was always `None`. The fix splits into Signal A (PO post_save → FG movement) and Signal B (Line post_save → RM movement).

### Flow 3 — Client Delivery (FG outflow)

```
ClientDN.validate()
  └─ self.save()  [status → 'validated']
       └─ post_save(ClientDN) → update_stock_on_client_dn_validation()
            └─ for each line: StockMovement.create(type='delivery', qty=-line.quantity_delivered)
                 └─ FinishedProductStockBalance.quantity updated
```

### Flow 4 — Stock Adjustment

```
StockAdjustment.approve(user)
  └─ for each line: StockMovement.create(type='adjustment', qty=qty_after - qty_before)
       └─ RawMaterialStockBalance or FinishedProductStockBalance updated
```

**All signal handlers include idempotency guards** — they query for an existing `StockMovement` with matching `source_document_type + source_document_id + source_line_id` before creating, preventing duplicates on re-save.

---

## 15. Business Rules Reference

| Code       | Module       | Rule                                                                                     |
| ---------- | ------------ | ---------------------------------------------------------------------------------------- |
| BR-AUD-02  | Accounts     | AuditLog is immutable; no delete action type                                             |
| BR-CDN-01  | Sales        | ClientDN validation blocked if client.credit_status == 'blocked'                         |
| BR-CDN-02  | Sales        | ClientDN validation blocked if any line qty > FG stock (atomic check)                    |
| BR-EXP-01  | Expenses     | Amounts > delegation_threshold require Manager; SD-EXP required for Manager validation   |
| BR-PROD-05 | Production   | RM stock deductions use qty_actual (not qty_theoretical)                                 |
| BR-RM-05   | Stock        | StockMovement records are never deleted; only signal-authorized paths may write balances |
| S2         | Catalog      | RawMaterial: alert_threshold > stockout_threshold; UoM immutable once referenced         |
| S2         | Catalog      | Finished products: deactivation only — never deleted                                     |
| S3         | Production   | delta_qty and financial_impact are computed properties — never stored                    |
| S3         | Sales        | balance_due is signal-updated — never form-editable                                      |
| S6         | Supplier Ops | SupplierDN status transitions are strictly enforced via VALID_TRANSITIONS dict           |
| S7         | Supplier Ops | SupplierPayment.save() triggers invoice.recompute_balance_due() via signal               |
| S7         | Sales        | ClientPayment.save() triggers invoice.recompute_balance_due() via signal                 |
| S8         | All          | Document references are auto-generated by DocumentSequence and immutable after creation  |

---

## 16. Document Reference Numbering

All reference numbers are generated atomically by `DocumentSequence.get_next_reference(prefix, year)`, using `select_for_update()` inside `transaction.atomic()`. This prevents duplicates under concurrent requests.

- **Year-based** (reset each year): BL-F, BL-C, FC, OP, DEP, ADJ, PAY-C, RGL-F
- **Year-less** (never reset): RM, PF, F

The `save()` method of each document model auto-generates the reference only if `not self.reference` (i.e., on creation). A guard in `save()` raises `ValidationError` if any code attempts to mutate an existing reference.

---

## 17. URL Map Summary

### Accounts (`/accounts/`)

| Endpoint             | Purpose                  |
| -------------------- | ------------------------ |
| `login/`             | Login                    |
| `logout/`            | Logout                   |
| `users/`             | User management          |
| `users/<id>/toggle/` | Activate/deactivate user |
| `audit-log/`         | Audit log viewer         |

### Catalog (`/catalog/`)

Raw materials and finished products: list, create, detail, edit. Plus quick-create AJAX endpoints and unit lookup.

### Production (`/production/`)

Formulations (list, create, detail, edit) and Production Orders (list, create, detail, launch, close). Yield report and AJAX scaling endpoint.

### Stock (`/stock/`)

RM and FG stock lists, detail views per item, movement history, adjustment management (list, create, detail, approve), alerts dashboard, and AJAX availability check.

### Supplier Operations (`/supplier-ops/`)

Supplier DNs and invoices (full CRUD + validate + print), supplier payments, FIFO settlement, and AJAX DN lookup by supplier.

### Sales (`/sales/`)

Client DNs and invoices (full CRUD + validate + print), client payments and receipt printing.

### Expenses (`/expenses/`)

Expense list, create, detail, validate, mark-paid, supporting document upload, and expense report.

### Reporting (`/reporting/`)

Dashboard + 5 financial/operational reports + CSV export + AJAX KPI endpoint.

---

## 18. Known Fixes & Technical Debt

The codebase contains documented fixes for several bugs found during development:

**1. Production signal timing bug (FIXED)**
The original single `post_save` on `ProductionOrder` fired when `ProductionOrderLine.qty_actual` was still `None`, preventing RM consumption movements from ever being created. Fixed by splitting into two independent signals (Signal A on PO, Signal B on Line).

**2. Duplicate stock movements from SupplierDNLine save (FIXED)**
The original `update_dn_total_on_line_change` signal called `supplier_dn.save()` on every line save, which re-fired the DN's `post_save` signal and would have created duplicate `StockMovement` records. Removed; total is now maintained by `SupplierDNLine.save()`'s direct `filter().update()`.

**3. Direct supplier payment not updating invoice status (FIXED)**
`SupplierPayment.save()` referenced a signal that was never implemented, so direct payments left `balance_due` and `status` stale on the invoice. The `supplier_payment_post_save` signal was implemented to close this gap. (Account `settle_fifo` was unaffected because it called `recompute_balance_due()` directly.)

**4. `balance_due` not initialized on new invoices (FIXED)**
Both `ClientInvoice._recompute_totals()` and `SupplierInvoice` had a bug where `balance_due` was not initialized at creation time. Fixed to compute `balance_due = total_ttc − Σ(payments)` on every save.

**5. Duplicate URL patterns in catalog (MINOR — pending cleanup)**
`catalog_urls.py` has duplicated entries for `finished-products/` list and `finished-products/create/`. These are harmless (Django uses the first match) but should be removed.

**6. Catalog URL: missing `finished_product_detail` edit registration**
`finished_product_detail` view is registered but no `finished-products/<id>/edit/` redirect exists from detail — it is registered separately. Low risk.

---

_End of Functional Specification — Factory Management System v1.0_
