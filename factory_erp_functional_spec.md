# Factory ERP System
## Functional Specification Mini Book

> **Document Type:** Functional Specification  
> **Scope:** Small Factory ERP — End-to-End Operations  
> **Version:** 1.2  
> **Audience:** Founders, Managers, Business Analysts, Product Teams  
> **Amendment Notes (v1.1):** Added Supplier Account Settlement — FIFO payment mode (Section 16); Document Proof and Evidence Attachments policy across all critical operations (Section 17); Audit Logs and Administrator Monitoring dashboard (Section 18); updated rules, statuses, and relevant existing sections accordingly.  
> **Amendment Notes (v1.2):** Added Receipt Generation — Purchase and Sales Directions (Section 19), covering supplier payment receipts (per-invoice and FIFO settlement) and client payment receipts, both linked to their originating invoices and delivery notes; updated rules, statuses, and relevant existing sections accordingly.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Business Actors and User Roles](#2-business-actors-and-user-roles)
3. [Supplier Management](#3-supplier-management)
4. [Supplier Delivery Notes](#4-supplier-delivery-notes)
5. [Raw Material Stock Management](#5-raw-material-stock-management)
6. [Production Management with Formulas](#6-production-management-with-formulas)
7. [Final Products Stock Management](#7-final-products-stock-management)
8. [Client Management](#8-client-management)
9. [Client Delivery Notes](#9-client-delivery-notes)
10. [Invoice Generation on Delivery Notes](#10-invoice-generation-on-delivery-notes)
11. [Expenses Management](#11-expenses-management)
12. [Reports and Statistics](#12-reports-and-statistics)
13. [End-to-End Workflow Narrative](#13-end-to-end-workflow-narrative)
14. [Functional Rules and Validations](#14-functional-rules-and-validations)
15. [Document Statuses Reference](#15-document-statuses-reference)
16. [Supplier Account Settlement — FIFO Payment Mode](#16-supplier-account-settlement--fifo-payment-mode)
17. [Document Proof and Evidence Attachments](#17-document-proof-and-evidence-attachments)
18. [Audit Logs and Administrator Monitoring](#18-audit-logs-and-administrator-monitoring)
19. [Receipt Generation — Purchase and Sales Directions](#19-receipt-generation--purchase-and-sales-directions)

---

## 1. Introduction

### 1.1 Purpose of This Document

This document defines the complete functional specification for a small factory Enterprise Resource Planning (ERP) system. It describes what the system must do — not how it is technically built — so that founders, managers, analysts, and development teams share a single, clear understanding of the business requirements.

The specification covers every major operational area of a small manufacturing business: receiving raw materials from suppliers, producing finished goods, delivering products to clients, issuing invoices, recording expenses, and monitoring performance through reports.

### 1.2 The Business Problems This ERP Solves

Small factories frequently operate with disconnected tools — paper delivery notes, manual spreadsheets, phone-based orders, and informal tracking. This leads to recurring operational problems:

- **Raw material shortages** during production because stock levels are not accurately tracked in real time.
- **Overproduction or underproduction** because there is no reliable way to match client demand with available materials.
- **Lost or unissued invoices** because deliveries and billing are managed separately.
- **Difficulty tracing costs** because expenses are scattered and not linked to production or sales.
- **Slow decision-making** because managers lack consolidated reports and must collect data manually.
- **Supplier and client disputes** because delivery records are incomplete or inconsistent.

This ERP eliminates these problems by creating a single, connected workflow where every action — from receiving a supplier shipment to issuing a client invoice — flows through the same system and updates the same records in real time.

### 1.3 Scope of the System

This ERP is designed for a small factory with the following operational characteristics:

- One or more production lines producing finished goods from raw materials.
- A small team of staff performing purchasing, production, warehousing, sales, and accounting functions, sometimes with staff wearing multiple hats.
- Regular purchasing from a defined set of suppliers.
- Regular sales to a defined set of clients, typically on a delivery-and-invoice basis.
- A need to track raw material consumption against production output and to understand costs and margins.

The system is intentionally scoped to cover the core operational cycle without unnecessary complexity. It does not aim to cover advanced financial accounting, payroll, or e-commerce. It is designed to be practical, learnable, and immediately useful for a team of five to thirty people.

### 1.4 The Main Workflow at a Glance

The system follows a natural factory cycle:

```
Supplier → Delivery Note → Raw Material Stock
                                   ↓
                          Production Order (using Formula/BOM)
                                   ↓
                         Finished Goods Stock
                                   ↓
                    Client Order → Client Delivery Note
                                   ↓
                              Invoice → Payment
                                   ↓
                         Expenses + Reports
```

Every step feeds the next. No information is entered twice. Every document created in the system has a clear status, a clear owner, and a clear effect on inventory and financials.

---

## 2. Business Actors and User Roles

### 2.1 Overview

The ERP assigns permissions and responsibilities according to user roles. Each role defines what screens a person can access, what actions they can take, and what approvals they can grant or require. A small factory may have one person covering multiple roles, and the system must allow this flexibility.

### 2.2 Role Definitions

#### Administrator

The Administrator has full access to every module in the system. This role is typically assigned to the business owner or a trusted senior manager. The Administrator can create and manage user accounts, assign roles, configure system-wide settings such as units of measure and expense categories, and override or correct records in any module. The Administrator is also the final authority for resolving data inconsistencies.

#### Storekeeper

The Storekeeper is responsible for physical stock in the factory. On the inbound side, the Storekeeper receives raw materials from suppliers, creates or validates supplier delivery notes, and confirms that physical quantities match what was ordered. On the outbound side, the Storekeeper releases raw materials to the production floor based on approved production orders and records the actual quantities issued. The Storekeeper may also conduct physical stock counts and trigger stock adjustments.

#### Production Manager

The Production Manager oversees all manufacturing activity. This role creates production orders, selects or confirms the formula to be used, initiates production runs, records output quantities, and closes production orders upon completion. The Production Manager is responsible for recording yield, waste, and any deviations from the standard formula. They also flag quality issues such as rejects or damaged batches.

#### Sales Staff

Sales Staff manage client relationships and outbound deliveries. This role creates client delivery notes, records what products are dispatched to which clients, and confirms that deliveries have been fulfilled. Sales Staff can view client records and stock availability but cannot modify prices, issue invoices, or access financial summaries.

#### Accountant

The Accountant handles all financial transactions in the system. This includes generating invoices from validated delivery notes, recording payments received against invoices, entering business expenses, and reviewing financial reports. The Accountant can view all sales and purchasing activity but cannot modify stock records or approve production orders.

#### Manager / Business Owner

The Manager has read access to all modules and full access to all reports and dashboards. This role does not typically create transactional records but uses the system to monitor business performance, review open orders and unpaid invoices, check stock health, and make operational decisions. The Manager can also approve expense entries above a defined threshold.

---

## 3. Supplier Management

### 3.1 Purpose

The supplier module is the foundation of the purchasing cycle. It stores all information about the companies or individuals who provide raw materials to the factory. Every purchasing transaction in the system — every delivery note, every stock receipt — is linked back to a supplier record.

### 3.2 Creating a Supplier Record

A supplier record is created by the Administrator or Storekeeper when the factory begins working with a new vendor. Before any purchasing activity can take place, the supplier must exist in the system.

The following information is captured for each supplier:

| Field | Description |
|---|---|
| Supplier Name | The legal or trading name of the supplier |
| Supplier Code | A unique short code used to reference the supplier quickly (e.g., SUP-001) |
| Contact Person | The name of the primary contact at the supplier |
| Phone Number | Main contact number |
| Email Address | For correspondence and document exchange |
| Address | Physical or mailing address |
| Tax Registration Number | Official tax or business registration number if applicable |
| Payment Terms | Standard number of days allowed for payment (e.g., 30 days, 60 days, cash on delivery) |
| Currency | The currency used in transactions with this supplier |
| Notes | Free-text field for any additional relevant information |
| Status | Active or Inactive |

### 3.3 Managing Supplier Records

Supplier records can be edited at any time by the Administrator or Storekeeper. Fields such as contact details, payment terms, and address can be updated without affecting historical records. If a supplier is no longer used, their status is set to Inactive. Inactive suppliers are hidden from selection in new purchasing transactions but remain accessible in historical reports and documents for audit purposes.

### 3.4 Supplier Use Across the System

Every supplier delivery note created in the system is linked to a supplier record. This linkage enables the system to:

- Show a complete purchase history for any supplier, including all delivery notes and the quantities and materials received over any date range.
- Identify which raw materials come from which suppliers.
- Track outstanding balances if payment tracking is enabled.
- Compare supplier performance over time (delivery frequency, volumes, discrepancies).

### 3.5 Supplier Purchase History

The system maintains an automatic record of all supplier delivery notes associated with each supplier. From the supplier's profile, an authorised user can view:

- A list of all delivery notes, each with its date, status, and total value.
- The total quantity of each raw material received from this supplier over a selected period.
- Any delivery notes that were flagged for discrepancies, damaged goods, or partial delivery.

This history cannot be manually edited. It is built automatically from the delivery note records.

### 3.6 Supplier Payment Modes

The system supports two distinct and complementary modes for paying suppliers. Both modes are available at all times, and the Accountant or Administrator selects the appropriate one depending on the commercial context.

**Mode 1 — Per-Invoice Direct Payment**  
The Accountant opens a specific supplier invoice and records a payment directly against it. This is appropriate when the factory is settling a single, clearly identified invoice — for example, paying an invoice on receipt of goods or responding to a supplier's payment reminder for a specific document. Upon recording the payment, the system makes a **supplier payment receipt** available for that transaction, listing the invoice paid and all delivery notes it covered. This mode is described in full in the invoicing sections, and receipt content is specified in Section 19.

**Mode 2 — Supplier Account Settlement (FIFO)**  
The Accountant navigates to the supplier's account and enters a total payment amount without specifying which invoice it covers. The system automatically distributes the payment across the supplier's unpaid invoices in chronological order — oldest first — until the payment amount is fully consumed. This mode is described in full in Section 16.

Both modes generate a traceable payment record. Both update outstanding invoice balances and the supplier's total account balance. Neither mode allows a payment to exceed the supplier's total outstanding debt.

---

## 4. Supplier Delivery Notes

### 4.1 Purpose

A supplier delivery note is the official record of raw materials arriving at the factory from a supplier. It bridges the purchasing activity and the raw material inventory. When a delivery note is validated, the quantities on it are added directly to the raw material stock. This module is one of the most critical in the system because it controls the accuracy of all downstream stock and production data.

### 4.2 The Receiving Workflow

The workflow for receiving goods from a supplier follows these steps:

**Step 1 — Goods Arrive**  
A supplier vehicle arrives at the factory with raw materials and a physical delivery document. The Storekeeper is responsible for receiving the shipment.

**Step 2 — Create the Delivery Note in the System**  
The Storekeeper opens the system and creates a new supplier delivery note. The note begins in **Draft** status. The Storekeeper selects the supplier from the supplier list and enters the delivery date.

**Step 3 — Add Line Items**  
For each raw material in the shipment, the Storekeeper adds a line to the delivery note. Each line includes:

| Field | Description |
|---|---|
| Raw Material | Selected from the raw material catalogue |
| Description | Optional additional description of the item |
| Quantity Received | The actual quantity physically counted at receiving |
| Unit of Measure | Kilogram, litre, bag, roll, piece, etc. |
| Unit Price | The price per unit agreed with the supplier |
| Total Line Value | Calculated automatically (Quantity × Unit Price) |
| Batch Number | Optional — used when batch tracking is required |
| Expiry Date | Optional — used for perishable raw materials |
| Notes | Free-text for any remarks about this line item |

**Step 4 — Attach Proof Documents**  
Before or during validation, the Storekeeper must attach at least one supporting document to the delivery note. Accepted formats are PDF, JPEG, or PNG. Typical attachments include the supplier's physical delivery slip, a signed receiving sheet, a weighbridge certificate, or a photo of the goods received. If no document is attached, the system displays a warning. Validation is still permitted but the absence of a proof document is flagged in the audit log and highlighted to the Administrator. For operations classified as high-value (above a configurable threshold), a proof document is mandatory and the system blocks validation until one is uploaded.

**Step 5 — Review and Validate**  
Once all lines are entered and the proof document is attached, the Storekeeper reviews the delivery note. If everything matches the physical shipment, the Storekeeper changes the status from Draft to **Validated**. Validation is the action that triggers stock entry. No stock is updated until a delivery note is validated.

**Step 6 — Stock is Updated**  
Upon validation, the system adds the quantities from each line of the delivery note to the corresponding raw material stock records. The stock update is immediate and timestamped. An audit log entry is created recording the user, the timestamp, the delivery note number, and a reference to any attached proof document.

### 4.3 Handling Partial Deliveries

If a supplier sends only part of an expected order — for example, 500 kg of flour when 1,000 kg was ordered — the delivery note records only what was physically received (500 kg). The note is validated for that quantity only. When the remaining 500 kg arrives later, a new delivery note is created for that shipment. The system does not automatically link the two deliveries unless a purchase order module is active, but both delivery notes reference the same supplier and the same raw material, making it easy to reconcile.

### 4.4 Handling Discrepancies

If the quantity on the supplier's physical document does not match what was actually counted at receiving, the Storekeeper records the actual received quantity in the system and adds a note to the affected line item explaining the discrepancy. The system records what was received, not what was expected. Disputes with the supplier are handled outside the system, but the delivery note serves as the official record of what entered the factory.

### 4.5 Handling Damaged Goods

If some goods arrive damaged and are not accepted into stock, the Storekeeper enters only the accepted, usable quantity on the delivery note. A note is added to the relevant line item indicating the damaged quantity and the reason for rejection. The Storekeeper is required to attach photographic evidence or a written damage report as a proof document to the delivery note before validation. This evidence protects the factory in any subsequent dispute with the supplier. Damaged goods that are still received provisionally can be marked with a "damaged" flag on the line, and the Storekeeper or Administrator can create a stock adjustment later if those goods are ultimately discarded.

### 4.6 Corrections and Cancellations

A delivery note in Draft status can be freely edited or deleted. Once validated, a delivery note cannot be directly edited because it has already updated stock. To correct a validated delivery note, the Administrator creates a stock adjustment (see Section 5.4) to correct the stock figures, and the original delivery note is annotated with a correction reference. A validated delivery note can be cancelled only by the Administrator, and cancellation automatically reverses the stock entries that were created when it was validated.

### 4.7 Delivery Note Status Flow

```
Draft → Validated → (Cancelled if needed, by Admin only)
```

### 4.8 Delivery Note Document

Each delivery note can be printed or exported as a formatted document including the supplier name, delivery date, list of items with quantities and prices, total value, and the name of the person who validated it. This document serves as an internal receiving record and can be used for supplier payment reconciliation.

---

## 5. Raw Material Stock Management

### 5.1 Purpose

The raw material stock module tracks the quantity of every material available in the factory at any given moment. It is the single source of truth for what the factory has on hand. It is updated by supplier delivery notes on the inbound side and by production orders on the outbound side, with manual adjustments available for corrections and physical counts.

### 5.2 The Raw Material Catalogue

Before any stock can be tracked, each raw material must be defined in the system's raw material catalogue. The catalogue contains:

| Field | Description |
|---|---|
| Material Name | Full descriptive name (e.g., White Wheat Flour) |
| Material Code | A unique code for quick reference (e.g., RM-001) |
| Category | Grouping for filtering and reporting (e.g., Flour, Chemicals, Packaging) |
| Unit of Measure | The standard unit used for this material (kg, litre, piece, roll, etc.) |
| Minimum Stock Level | The quantity below which a low-stock alert is triggered |
| Current Stock | The live quantity currently available (updated automatically) |
| Notes | Any handling instructions or storage requirements |
| Status | Active or Inactive |

The catalogue is managed by the Administrator or Storekeeper. Once a material is defined, it becomes available for selection in supplier delivery notes, production formulas, and stock adjustments.

### 5.3 How Stock Increases — Inbound Movements

Raw material stock increases only when a supplier delivery note is validated. At that moment, for each line item on the delivery note, the system adds the received quantity to the current stock of the corresponding raw material. The system records:

- The date and time of the stock increase.
- The quantity added.
- The supplier delivery note number that caused the increase.
- The supplier who provided the material.
- The unit price, enabling cost tracking.

This creates a complete inbound movement history for every raw material.

### 5.4 How Stock Decreases — Outbound Movements

Raw material stock decreases in two ways:

**Production Consumption:** When a production order is completed (or when raw materials are formally issued to production), the system deducts the quantities specified in the production formula from the relevant raw material stocks. This is the primary way stock is consumed.

**Manual Adjustment:** Authorised users (Storekeeper or Administrator) can create a stock adjustment to reduce stock for reasons such as material spoilage, physical count corrections, or material discarded due to contamination. Every adjustment must include a reason.

### 5.5 Stock Adjustments

A stock adjustment is a controlled mechanism to correct the system's stock figures when they diverge from physical reality. This can happen due to counting errors, unrecorded waste, or spillage.

To create a stock adjustment, the Storekeeper selects the raw material, specifies whether stock is being increased or decreased, enters the adjustment quantity, and provides a mandatory reason (e.g., "physical count correction," "waste disposal," "damaged goods write-off").

**Proof Document Requirement:** Every stock adjustment must include an attached supporting document before it can be submitted for approval or validated. For increases in stock, acceptable documents include a physical count sheet signed by the Storekeeper and a witness, or a delivery note correction. For decreases, acceptable documents include a waste disposal record, a signed write-off form, a photograph of damaged goods, or a lab or quality rejection report. The system blocks submission of an adjustment if no document is attached.

The adjustment is recorded with the user's name, timestamp, stated reason, and a reference to the attached document. Adjustments that increase stock significantly or that exceed a configurable threshold require Administrator approval before taking effect. Every adjustment — whether approved or rejected — generates a permanent audit log entry visible to the Administrator.

### 5.6 Minimum Stock Alerts

For each raw material, the Administrator or Storekeeper can define a minimum stock level. When the current stock falls at or below this threshold, the system displays a visual alert on the raw material record and on the main dashboard. This alert does not block any operation — it is informational only — but it prompts the Storekeeper to initiate a new purchase.

### 5.7 Stock History and Traceability

Every change to raw material stock — whether from a delivery note, a production order, or an adjustment — is recorded in a movement log for that material. The log shows:

- Date and time of each movement.
- Type of movement (delivery receipt, production consumption, adjustment).
- Quantity moved (positive for inbound, negative for outbound).
- Reference document number (delivery note number or production order number).
- The stock balance after the movement.

This log cannot be edited or deleted. It provides a complete and auditable history of every unit of material that has passed through the factory.

### 5.8 Unit of Measure Handling

Each raw material has one defined unit of measure. All quantities for that material — in delivery notes, production formulas, and stock records — must use that unit. If a supplier delivers in a different unit (e.g., tonnes instead of kilograms), the Storekeeper converts the quantity before entering the delivery note. The system does not perform automatic unit conversion.

---

## 6. Production Management with Formulas

### 6.1 Purpose

The production management module governs how the factory converts raw materials into finished products. It uses predefined formulas (also called Bills of Materials or BOMs) to define what raw materials are needed and in what quantities to produce a given output. This module connects raw material stock to finished goods stock, and it is where the transformation at the heart of the factory's business is recorded.

### 6.2 Formulas (Bills of Materials)

#### 6.2.1 What Is a Formula?

A formula defines the recipe for producing one unit (or a standard batch) of a finished product. It lists the raw materials required and the quantity of each. Formulas are created and maintained by the Administrator or Production Manager.

A formula record contains:

| Field | Description |
|---|---|
| Formula Name | A descriptive name for the formula (e.g., Standard Tomato Sauce 1 kg) |
| Formula Code | A unique reference code |
| Finished Product | The finished product that this formula produces |
| Output Quantity | How much finished product is produced by one execution of this formula (e.g., 100 kg) |
| Output Unit | The unit of measure of the finished product |
| Status | Active or Archived |
| Notes | Notes on the production process or quality requirements |

Each formula contains one or more **ingredient lines**, each specifying:

| Field | Description |
|---|---|
| Raw Material | Selected from the raw material catalogue |
| Quantity Required | The quantity of this material needed to produce the formula's output quantity |
| Unit of Measure | Must match the raw material's defined unit |
| Notes | Any special handling instruction for this ingredient |

#### 6.2.2 Formula Versions

When a formula is significantly changed — for example, when a supplier changes an ingredient or when the production process is improved — the old formula is archived and a new version is created rather than overwriting the original. This ensures that historical production orders accurately reflect what was actually used to produce goods in the past.

#### 6.2.3 Example Formula

> **Formula:** Olive Jam Jar 250g — Batch of 1,000 jars  
> **Output:** 1,000 units of "Olive Jam 250g Jar"  
> **Ingredients:**
> - Olives: 280 kg
> - Sugar: 90 kg
> - Citric Acid: 2 kg
> - Glass Jars 250g: 1,000 pieces
> - Metal Lids: 1,000 pieces
> - Labels: 1,000 pieces

### 6.3 Production Orders

#### 6.3.1 Creating a Production Order

A production order is a formal instruction to the production team to manufacture a specified quantity of a finished product. The Production Manager creates the production order, which contains:

| Field | Description |
|---|---|
| Production Order Number | Auto-generated unique reference |
| Product | The finished product to be produced |
| Formula | The formula to be used (selected from active formulas for this product) |
| Planned Quantity | The number of output units planned (e.g., 3,000 jars) |
| Planned Start Date | When production is scheduled to begin |
| Planned End Date | Expected completion date |
| Priority | Low, Normal, High |
| Notes | Any additional instructions for the production team |
| Status | Draft |

#### 6.3.2 Material Requirements Calculation

When the Production Manager selects the formula and enters the planned quantity, the system automatically calculates the required quantity of each raw material by scaling the formula proportionally.

**Example:**  
If the formula produces 1,000 jars and requires 280 kg of olives, and the production order is for 3,000 jars, the system calculates:

- Olives required: 280 × 3 = **840 kg**
- Sugar required: 90 × 3 = **270 kg**
- And so on for each ingredient.

The system then checks the current stock of each required raw material against the calculated requirement and displays a material availability summary:

| Material | Required | Available | Status |
|---|---|---|---|
| Olives | 840 kg | 1,200 kg | ✓ Sufficient |
| Sugar | 270 kg | 200 kg | ✗ Insufficient |
| Glass Jars 250g | 3,000 pcs | 3,500 pcs | ✓ Sufficient |

If any material is insufficient, the system displays a warning. The Production Manager cannot launch the production order until the material situation is resolved — either by waiting for a new supplier delivery or by reducing the planned quantity.

#### 6.3.3 Production Order Statuses

Production orders move through the following statuses:

```
Draft → Confirmed → In Progress → Completed → (Cancelled if needed)
```

- **Draft:** The order has been created but not yet reviewed or approved. Materials are not yet reserved.
- **Confirmed:** The Production Manager has reviewed the order and confirmed it is ready to execute. At this point, the system optionally reserves the required raw material quantities, making them unavailable for other orders.
- **In Progress:** Production has physically started. The order is locked from editing.
- **Completed:** Production has finished. Actual quantities produced and consumed are recorded and stock is updated.
- **Cancelled:** The order is cancelled before completion. If materials were reserved, the reservation is released. If partial production occurred, the system records the partial output.

#### 6.3.4 Raw Material Reservation

When a production order is confirmed, the system can optionally reserve the required raw material quantities. A reserved quantity is still counted in total stock but is marked as committed, so the available-for-use quantity is reduced accordingly. This prevents two production orders from both being confirmed against the same stock when there is only enough material for one.

If the factory chooses not to use reservations, the system instead issues a warning at the time of confirmation if stock appears insufficient.

#### 6.3.5 Launching and Executing Production

When the production team is ready to begin, the Production Manager changes the order status to **In Progress**. Physical raw materials are issued to the production floor by the Storekeeper based on the quantities listed on the confirmed production order.

During production, the following may be recorded:

- **Actual Raw Material Consumed:** If the production process consumed slightly more or less of a material than the formula specified (due to waste, evaporation, or process variation), the Storekeeper or Production Manager records the actual quantities consumed rather than the planned quantities.
- **Yield:** The actual quantity of finished product produced.
- **Waste / Rejects:** Any finished product units that failed quality checks and cannot be sold.

#### 6.3.6 Completing a Production Order

When production finishes, the Production Manager marks the order as **Completed** and enters the final figures:

| Field | Description |
|---|---|
| Actual Quantity Produced | The total units of finished product that passed quality |
| Rejected Quantity | Units produced but rejected for quality reasons |
| Actual Raw Material Consumed (per ingredient) | The real amounts used, which may differ from the formula |
| Completion Date | The actual date production finished |
| Notes | Any remarks on the production run |

**Production Incident and Proof Document Requirements:** If the actual production run deviated from the expected outcome in any of the following ways, the Production Manager must attach a supporting document before the order can be closed:

- **Over-consumption of raw materials:** If any ingredient was consumed more than 10% above the formula quantity, a written explanation or incident report must be attached. Example: equipment malfunction causing spillage, formula recalibration, or batch rework.
- **Significant under-yield:** If the actual good output is more than 10% below the planned quantity (excluding known rejects), a production incident note must be attached.
- **Rejects above threshold:** If rejected units exceed a configurable percentage of planned output (e.g., more than 5%), a quality rejection report with the identified cause must be attached.
- **Formula deviation:** If a substitute raw material was used in place of a formula ingredient (e.g., a different supplier's ingredient), the Production Manager must document this substitution with a signed approval from the Administrator.

These attachments can be PDF documents, scanned paper forms, or photographs. They are permanently linked to the production order record and are visible in the audit trail.

Upon completion, two things happen simultaneously:

1. **Raw material stock is reduced** by the actual quantities consumed.
2. **Finished product stock is increased** by the actual quantity of acceptable output produced.

An audit log entry is created for the completion event, recording the user, timestamp, planned vs. actual figures, and whether any incident documents were attached.

Rejected units are recorded but are not added to sellable finished goods stock. They may be tracked separately for waste analysis.

#### 6.3.7 Partial Production

If the factory produces part of a planned order and then pauses, the Production Manager can record a **partial completion** — logging the quantity produced so far and the materials consumed to that point — without closing the order. The order remains In Progress. When the remaining production is done, a second completion entry is made. The production order is fully closed only when the total actual output has been recorded and the Production Manager marks it as Completed.

---

## 7. Final Products Stock Management

### 7.1 Purpose

The finished products stock module tracks the quantity of every sellable product available in the factory's warehouse. It is updated by completed production orders on the inbound side and by client delivery notes on the outbound side. Like the raw material stock module, it maintains a complete movement history for every product.

### 7.2 The Finished Products Catalogue

Each finished product must be defined in the product catalogue before it can be tracked in stock. The catalogue contains:

| Field | Description |
|---|---|
| Product Name | Full name of the product (e.g., Olive Jam 250g Jar) |
| Product Code | Unique reference code (e.g., FP-001) |
| Category | Product grouping (e.g., Preserves, Sauces, Dry Goods) |
| Unit of Measure | The unit in which the product is sold (jar, box, kg, litre, etc.) |
| Sales Price | Default selling price per unit |
| Minimum Stock Level | Quantity below which a low-stock alert is triggered |
| Current Stock | Live quantity available for delivery (updated automatically) |
| Notes | Any storage or handling instructions |
| Status | Active or Discontinued |

### 7.3 How Stock Increases — Production Output

Finished product stock increases only when a production order is completed. The actual quantity of good output (excluding rejects) is added to the corresponding finished product's stock balance. The movement log records the production order number, the date, and the quantity added.

### 7.4 How Stock Decreases — Client Deliveries

Finished product stock decreases when a client delivery note is validated and confirmed as dispatched. The quantities on the delivery note are deducted from the corresponding product stocks at the moment the delivery is confirmed (see Section 9 for the full delivery workflow).

### 7.5 Stock Adjustments for Finished Products

As with raw materials, the Administrator or Storekeeper can create manual stock adjustments for finished products. Common reasons include: breakage in the warehouse, physical count corrections, promotional samples, or write-offs of expired goods. Every adjustment requires a stated reason and is logged with a timestamp and the user who created it.

### 7.6 Minimum Stock Alerts

Finished product minimum stock alerts work the same way as for raw materials. When a product's stock falls to or below its defined minimum, a visual alert appears on the product record and the dashboard. This prompts the Production Manager to consider scheduling a new production order.

### 7.7 Product Stock History

Every movement in and out of finished product stock is logged in a movement history including date, type of movement (production receipt or delivery dispatch), quantity, document reference, and running balance. This log is read-only and cannot be manually altered.

### 7.8 Batch and Lot Tracking (Optional)

If the factory requires traceability — for example, to meet food safety requirements — each production order can generate a batch or lot number that is assigned to all finished product units produced in that run. When those units are later delivered to clients, the delivery note records which batch was dispatched. This allows the factory to trace, in the event of a quality issue, exactly which clients received products from a specific production batch and which raw material deliveries were used.

---

## 8. Client Management

### 8.1 Purpose

The client module stores all information about the businesses or individuals who purchase finished products from the factory. Just as the supplier module is the foundation of purchasing, the client module is the foundation of sales. Every client delivery note, invoice, and payment record is linked to a client.

### 8.2 Creating a Client Record

A client record is created by the Administrator or Sales Staff when the factory establishes a new customer relationship. The record contains:

| Field | Description |
|---|---|
| Client Name | The legal or trading name of the client |
| Client Code | A unique short reference code (e.g., CLI-001) |
| Contact Person | The primary purchasing contact at the client |
| Phone Number | Main contact number |
| Email Address | For sending invoices and correspondence |
| Delivery Address | The address where goods are delivered |
| Billing Address | The address for invoice purposes (may differ from delivery address) |
| Tax Registration Number | The client's official tax or business registration number |
| Payment Terms | Agreed number of days to pay invoices (e.g., 30 days, immediate) |
| Credit Limit | Maximum value of outstanding unpaid invoices allowed (optional) |
| Currency | The currency used in transactions with this client |
| Notes | Any special commercial or handling notes |
| Status | Active or Inactive |

### 8.3 Managing Client Records

Client records can be edited at any time by the Administrator or Sales Staff. Inactive clients are hidden from selection in new transactions but remain accessible in historical reports. Inactivating a client does not affect any existing delivery notes, invoices, or payment records.

### 8.4 Client Payment Terms and Credit Status

Each client has agreed payment terms defined on their record. The system uses these terms to calculate the due date on each invoice automatically (invoice date plus the agreed number of days).

If a credit limit is defined, the system monitors the total value of outstanding unpaid invoices for that client. If a new delivery note would cause the outstanding balance to exceed the credit limit, the system displays a warning to Sales Staff. Sales Staff can still proceed, but the Accountant or Administrator is notified, and the Manager can review the situation.

### 8.5 Client Sales History

From any client's profile, an authorised user can view:

- A list of all delivery notes, with dates, statuses, and values.
- A list of all invoices, with due dates, paid/unpaid status, and outstanding amounts.
- Total sales volume and value over any selected period.
- Payment behaviour history (on-time, late, or outstanding payments).

---

## 9. Client Delivery Notes

### 9.1 Purpose

A client delivery note is the official record of finished products leaving the factory and being delivered to a client. It is the document that triggers a reduction in finished product stock and is the direct basis for generating a client invoice. No invoice can be created without a corresponding validated delivery note.

### 9.2 The Delivery Workflow

The delivery workflow follows these steps:

**Step 1 — Determine What to Deliver**  
Sales Staff determine what products need to be delivered to which client, either based on a client's order, a standing agreement, or a management decision. (If a formal sales order module is present, the delivery note can be created from the sales order. In the basic version of this ERP, delivery notes can be created directly.)

**Step 2 — Create the Delivery Note**  
Sales Staff create a new client delivery note in the system. The note begins in **Draft** status. They select the client, enter the delivery date, and optionally add a reference to a client purchase order number if the client provided one.

**Step 3 — Add Line Items**  
For each product to be delivered, Sales Staff add a line to the delivery note:

| Field | Description |
|---|---|
| Product | Selected from the finished products catalogue |
| Description | Optional additional description |
| Quantity to Deliver | The number of units to be sent |
| Unit of Measure | Must match the product's defined unit |
| Unit Price | The agreed price per unit for this client |
| Discount | Any line-level or order-level discount (percentage or amount) |
| Total Line Value | Calculated automatically |
| Batch Number | If batch tracking is active, the batch being dispatched |
| Notes | Any delivery-specific instructions |

The system checks the current available stock for each product. If the quantity requested exceeds available stock, a warning is displayed. Sales Staff cannot dispatch more than what is in stock.

**Step 4 — Review and Confirm**  
Before the goods physically leave the factory, the Storekeeper (or a designated person) reviews the delivery note and verifies that the goods have been physically prepared and loaded. The delivery note is then moved to **Confirmed** status.

**Step 5 — Dispatch and Validate**  
When the delivery is dispatched — whether by the factory's own transport or a third-party carrier — the delivery note is marked as **Dispatched**. At this point, the finished product stock is reduced by the quantities on the note.

**Step 6 — Delivery Acknowledgement (Optional)**  
If the factory collects a signed acknowledgement from the client confirming receipt, the delivery note can be updated to **Delivered** status. This is optional but useful for records and dispute resolution.

### 9.3 Delivery Note Status Flow

```
Draft → Confirmed → Dispatched → Delivered
                       ↓
                  (Invoiced — once invoice is created)
```

### 9.4 Partial Delivery

If the factory can only supply part of what a client has ordered — for example, 200 boxes when 500 were requested — the delivery note is created for 200 boxes only. The remaining 300 boxes can be delivered later with a new delivery note. The system does not automatically create a backorder, but the Sales Staff can add a note to the delivery record indicating the outstanding quantity.

### 9.5 Delivery Returns

If a client returns goods — because of quality issues, incorrect items, or overdelivery — a return delivery note is created. A return delivery note is the same as a standard delivery note but with a negative quantity or a return-type flag. When validated, a return delivery note increases finished product stock by the returned quantity and creates a credit note or offsets the next invoice. Returns can only be processed by the Administrator or Accountant.

### 9.6 Effect on Stock

Stock is reduced at the Dispatched step, not at Draft or Confirmed. This design ensures that stock is only committed to a delivery when the goods are actually leaving the factory, giving the factory maximum flexibility to adjust delivery notes while still in preparation.

### 9.7 Delivery Note Document

Each client delivery note can be printed or exported as a formatted document showing the client name, delivery address, date, list of products with quantities and prices, total value, and signature line for client acknowledgement. This document travels with the goods.

---

## 10. Invoice Generation on Delivery Notes

### 10.1 Purpose

The invoice module enables the factory to bill clients for goods that have been delivered. Invoicing is strictly tied to delivery: an invoice can only be generated for a delivery note that has reached **Dispatched** or **Delivered** status. This rule ensures that clients are never billed for goods that have not left the factory.

### 10.2 The Invoicing Rule

The fundamental rule of this module is:

> **An invoice can only be created for goods that have been dispatched. The invoice cannot exceed the value of the goods on the associated delivery note.**

This rule is enforced by the system and cannot be overridden by normal users.

### 10.3 Creating an Invoice from a Delivery Note

The Accountant navigates to a dispatched delivery note and selects the option to generate an invoice. The system pre-fills the invoice with all the information from the delivery note:

| Field | Description |
|---|---|
| Invoice Number | Auto-generated unique reference number |
| Invoice Date | Defaults to today's date; can be adjusted |
| Client | Carried from the delivery note |
| Delivery Note Reference | Linked to the source delivery note |
| Line Items | Products, quantities, unit prices, and discounts from the delivery note |
| Subtotal | Sum of all line items before tax |
| Tax | Applied according to the applicable tax rate (configurable per product or per client) |
| Total Amount Due | Subtotal plus tax, minus any applicable invoice-level discount |
| Payment Due Date | Calculated automatically from invoice date plus client payment terms |
| Payment Instructions | Bank account details or payment method |
| Notes | Optional free-text note to appear on the invoice |

The Accountant reviews the pre-filled invoice, makes any necessary adjustments to notes or tax lines, and then finalises it. A finalised invoice is in **Issued** status.

### 10.4 Invoice Statuses

```
Draft → Issued → Partially Paid → Paid → (Cancelled if needed)
```

- **Draft:** The invoice is being prepared but has not been sent to the client.
- **Issued:** The invoice has been finalised and sent (or is ready to be sent) to the client.
- **Partially Paid:** The client has made a payment that covers only part of the invoice total.
- **Paid:** The full invoice amount has been received. The invoice is closed.
- **Cancelled:** The invoice has been voided. This may happen if a delivery is reversed. Cancelled invoices cannot be deleted; they remain in the records with cancelled status for audit purposes.

### 10.5 Partial Invoicing

In some commercial arrangements, a factory may invoice for only part of a delivery — for example, if part of the delivery is disputed or if the client has requested staged invoicing. The system supports this by allowing the Accountant to reduce the invoiced quantities for any line item below the delivered quantities. The system tracks which portions of a delivery note have been invoiced and which remain uninvoiced, and prevents the same quantity from being invoiced twice.

### 10.6 Recording Payments

When a client makes a payment, the Accountant records it against the relevant invoice. A payment record includes:

| Field | Description |
|---|---|
| Payment Date | The date the payment was received |
| Amount Paid | The amount received (may be partial) |
| Payment Method | Bank transfer, cheque, cash, or other |
| Reference | The client's payment reference or bank transaction number |
| Notes | Any relevant remarks |

If the payment covers the full invoice amount, the invoice moves to **Paid** status. If partial, it moves to **Partially Paid** and shows the outstanding balance. Multiple payment entries can be recorded against a single invoice until it is fully paid.

**Receipt Generation on Payment:** Each time a payment is recorded against a client invoice — whether full or partial — the system makes a **client payment receipt** available for that payment event. The receipt is a formal, printable document confirming the amount received, the invoice it applies to, and all delivery notes covered by that invoice. Receipts serve as official proof of payment from the client's perspective and can be handed to the client or stored as an internal record. The full specification of receipt content, layout, and rules is in Section 19.

### 10.7 Taxes and Discounts

The system supports a single configurable tax rate (or multiple rates if the factory operates in a jurisdiction with product-level tax distinctions). Tax rates are set by the Administrator. Discounts can be applied at the line-item level on the delivery note (and thus carry through to the invoice) or at the invoice total level as a global discount. Both are recorded and visible on the printed invoice.

### 10.8 The Relationship Between Delivery Notes and Invoices

Each delivery note can generate one invoice (or multiple partial invoices if partial invoicing is used). Each invoice is always traceable back to its source delivery note. From a delivery note record, the user can see whether an invoice has been created, its status, and the outstanding amount. From an invoice record, the user can see the delivery note it covers.

This linkage ensures that the sales cycle is always auditable from product leaving the warehouse to payment being received in the bank.

---

## 11. Expenses Management

### 11.1 Purpose

The expenses module records all business costs that the factory incurs in operating, beyond the direct cost of raw materials and production. These expenses are essential for understanding the true profitability of the business. Without tracking them, the factory may believe it is profitable based on sales alone, while fixed and operating costs erode or eliminate its margins.

### 11.2 Expense Categories

Expenses are organised into categories to enable meaningful analysis. The standard categories are:

| Category | Examples |
|---|---|
| Utilities | Electricity, water, gas, internet, telephone |
| Transport and Logistics | Fuel, vehicle maintenance, delivery contractor fees |
| Labour and Salaries | Wages, bonuses, social security contributions |
| Maintenance and Repairs | Equipment servicing, factory repairs, cleaning |
| Packaging and Consumables | Boxes, tape, labels, shrink wrap, safety gloves |
| Rent and Premises | Factory rent, storage rental, lease payments |
| Administrative Costs | Office supplies, printing, postage |
| Professional Services | Accountant fees, legal fees, certification costs |
| Marketing and Sales | Promotional materials, trade show costs |
| Other | Miscellaneous expenses that do not fit other categories |

The Administrator can create, rename, or deactivate categories to match the specific needs of the factory.

### 11.3 Recording an Expense

Any authorised user (depending on the factory's policy, this may be limited to the Accountant, Administrator, or any staff member) can record an expense. To do so, they enter:

| Field | Description |
|---|---|
| Expense Date | The date the cost was incurred or paid |
| Category | Selected from the expense categories list |
| Description | A clear description of what the expense was for |
| Amount | The total amount of the expense |
| Currency | Defaults to the factory's operating currency |
| Supplier / Payee | Optional — who was paid (can be a system supplier or free text) |
| Payment Method | Cash, bank transfer, card, or other |
| Reference Number | Invoice or receipt number from the payee |
| Attachment | Supporting document — see proof document requirements below |
| Notes | Any additional remarks |
| Status | Draft or Validated |

**Proof Document Requirement for Expenses:** A scanned or photographed copy of the supplier's invoice, receipt, or official payment confirmation must be attached to every expense entry. For expenses above the approval threshold, a proof document is mandatory — the system blocks validation without it. For small petty-cash expenses below a configurable minimum value, the proof document is recommended but not required; however, the absence of a document is flagged in the audit log. Accepted file formats are PDF, JPEG, and PNG. Each attachment is stored permanently and linked to the expense record for audit and review purposes.

### 11.4 Expense Approval Workflow

The factory can configure a simple approval threshold. Expenses below the threshold are recorded directly in **Validated** status by the entering user. Expenses above the threshold are created in **Draft** status and require approval by the Administrator or Manager before they are validated and counted in reports.

The approving user reviews the expense, and if satisfied, changes the status to Validated. If rejected, the expense is marked as Rejected with a note explaining the reason, and the entering user is notified.

### 11.5 Expense Reporting and Profitability

Validated expenses feed directly into the financial reports and profitability analysis. The reports module (Section 12) aggregates expenses by category, by period, and optionally by production line or cost centre, and compares them against sales revenue to provide a gross and net margin view of the business.

The system does not perform full double-entry bookkeeping, but the combination of sales invoices and validated expenses gives the factory manager a reliable picture of income versus costs for any given period.

---

## 12. Reports and Statistics

### 12.1 Purpose

The reports module is where all the data captured across every other module comes together to give management the information they need to make good decisions. Reports are not just summaries — they are the business intelligence layer that transforms transactions into insights.

All reports support filtering by date range at minimum, and most support additional filters by supplier, client, product, production order, or expense category.

### 12.2 Dashboard — Management Overview

The main dashboard provides the Manager with a live summary of the factory's operational health. It displays:

- **Total raw materials below minimum stock** — with a list of affected materials and current quantities.
- **Total finished products below minimum stock** — with a list of affected products.
- **Production orders in progress** — count and list.
- **Pending supplier delivery notes** — delivery notes awaiting validation.
- **Outstanding client invoices** — total amount due, with breakdown by overdue and not-yet-due.
- **Total sales this month** (sum of dispatched delivery notes) vs. last month.
- **Total expenses this month** vs. last month.
- **Quick access shortcuts** to the most commonly used functions.
- **Audit activity feed** — a live summary of the most recent sensitive operations: stock adjustments, cancelled documents, production incident reports, and unproven validations (documents validated without a proof attachment). This feed is visible only to the Administrator and is described in full in Section 18.

The dashboard is read-only. It refreshes automatically as transactions are recorded.

### 12.3 Stock Reports

#### Raw Material Stock Report
Shows the current quantity of every raw material, its minimum stock level, whether it is below minimum, and its average unit cost. Can be filtered by category.

#### Finished Products Stock Report
Shows the current quantity of every finished product, its minimum level, and its default sales price. Can be filtered by category.

#### Stock Movement Report
For any selected material or product over a selected date range, shows every movement (in and out), the document that caused it, and the running stock balance after each movement. Useful for auditing and reconciling physical counts.

#### Low Stock Alert Report
A focused report listing only materials or products that are currently at or below their minimum stock level, sorted by urgency.

### 12.4 Purchasing and Supplier Reports

#### Supplier Delivery Summary
For a selected date range, shows all validated supplier delivery notes — total quantity and value per supplier, per material, or both.

#### Raw Material Received Report
For a selected material and date range, shows every delivery note that brought that material into stock, including the supplier, quantity, unit price, and total value.

#### Supplier Performance Report
Compares suppliers who supply the same material: frequency of delivery, volumes delivered, average unit price, and any delivery notes flagged for discrepancies or damaged goods.

### 12.5 Production Reports

#### Production Order Summary
A list of all production orders over a selected period, showing the product, planned quantity, actual quantity produced, formula used, and status.

#### Production Efficiency Report
Compares planned vs. actual raw material consumption for completed production orders. Highlights over-consumption or under-consumption by ingredient, helping the Production Manager identify waste or formula inaccuracies.

#### Waste and Rejects Report
Shows the quantities rejected in each production order and the reasons recorded. Helps management identify quality trends or equipment problems.

#### Raw Material Consumption Report
For any selected period, shows the total quantity of each raw material consumed by production, derived from completed production orders. This is a critical input for cost-of-production calculations.

### 12.6 Sales and Client Reports

#### Sales by Client Report
For a selected period, shows the total quantity and value of goods delivered to each client, ranked by value. Can be filtered to a single client.

#### Sales by Product Report
For a selected period, shows the total quantity and value of each product dispatched. Useful for identifying top-selling products.

#### Delivery Note Status Report
A list of all client delivery notes with their current status (Draft, Confirmed, Dispatched, Delivered, Invoiced). Highlights notes that have been dispatched but not yet invoiced — a critical gap to track.

### 12.7 Invoice and Financial Reports

#### Invoice Ageing Report
The single most important financial report. Lists all issued invoices grouped by their age (current, 1–30 days overdue, 31–60 days overdue, 60+ days overdue). Shows the outstanding amount for each invoice and the total exposure by age band. This enables the Accountant to prioritise collections.

#### Invoice Summary Report
For a selected period, shows all issued invoices, their total amounts, amounts paid, and outstanding balances. Can be filtered by client or status.

#### Revenue Report
Shows total sales revenue by month, by product, or by client over a selected period. Can be compared across periods to identify trends.

#### Payment Received Report
Shows all payments recorded in the system over a selected period, by client, with invoice references.

### 12.8 Expense Reports

#### Expense Summary by Category
For a selected period, shows the total expenditure in each expense category. This is the primary view for understanding cost structure.

#### Expense Detail Report
A line-by-line list of all validated expenses over a selected period, with full detail including payee, description, amount, and reference.

#### Monthly Expense Trend
Shows total expenses by month across a selected year, with category breakdown, to identify cost trends and seasonal patterns.

### 12.9 Profitability Overview

The profitability report is a high-level summary that the Manager uses to assess whether the business is generating a surplus. It is not a formal financial statement but a management view:

| Line | Description |
|---|---|
| Total Revenue | Sum of all invoiced sales for the period |
| Cost of Raw Materials | Total value of raw materials consumed in production (from production orders) |
| Gross Profit | Revenue minus raw material costs |
| Total Operating Expenses | Sum of all validated expenses for the period |
| Net Operating Result | Gross profit minus operating expenses |

This view is available monthly and can be compared across months. It gives the manager a quick sense of whether the factory is covering its costs and generating a surplus.

### 12.10 Custom Filters Available Across All Reports

All reports support the following standard filters:

- Date range (from / to)
- Supplier (for purchasing reports)
- Client (for sales and invoice reports)
- Product (for stock and sales reports)
- Raw material (for stock and consumption reports)
- Expense category (for expense reports)
- Status (for document reports — e.g., show only unvalidated or only unpaid)
- Production order (for production and consumption reports)

Reports can be printed, exported as PDF, or exported as a spreadsheet file.

---

## 13. End-to-End Workflow Narrative

This section tells the complete story of the ERP in action, following a single business cycle from raw material arrival to client payment.

---

### Step 1 — The Supplier Delivers Raw Materials

On a Monday morning, a supplier truck arrives at the factory gate with a shipment of olives, sugar, and glass jars. The Storekeeper meets the driver, inspects the goods, and counts the quantities. The physical delivery matches the expected quantities except for the glass jars — only 4,800 were delivered instead of the 5,000 ordered.

The Storekeeper opens the ERP system and creates a new **Supplier Delivery Note**. They select the supplier, enter today's date, and add three line items: olives (450 kg at 2.80 per kg), sugar (150 kg at 0.95 per kg), and glass jars (4,800 pieces at 0.12 each). On the glass jars line, they add a note: "200 units short — supplier advised remainder will arrive Thursday."

The Storekeeper reviews the note and clicks **Validate**. The system confirms the validation and immediately adds 450 kg to the olives stock, 150 kg to the sugar stock, and 4,800 units to the glass jars stock. The delivery note status changes to **Validated**.

---

### Step 2 — Raw Materials Are Available in Stock

The Storekeeper checks the raw material stock summary. Olives now show 1,650 kg available. Sugar shows 340 kg. Glass jars show 6,300 pieces. All materials are above their minimum stock levels. No alerts are active.

---

### Step 3 — The Production Manager Plans Production

The Production Manager looks at the finished goods stock. Olive jam jars are running low — only 800 units remain and the factory has pending client orders totalling 3,500 units. The Production Manager decides to produce 4,000 units to fulfil existing orders and maintain a safety buffer.

They open the Production module and create a new **Production Order**: Product is "Olive Jam 250g Jar," Formula is "Olive Jam Jar 250g — Batch of 1,000," planned quantity is 4,000 units, planned start date is tomorrow.

The system scales the formula and calculates requirements:
- Olives: 1,120 kg — Available: 1,650 kg ✓
- Sugar: 360 kg — Available: 340 kg ✗ (short by 20 kg)
- Citric Acid: 8 kg — Available: 15 kg ✓
- Glass Jars 250g: 4,000 pcs — Available: 6,300 pcs ✓
- Metal Lids: 4,000 pcs — Available: 4,500 pcs ✓
- Labels: 4,000 pcs — Available: 5,000 pcs ✓

The system shows a warning: sugar is insufficient by 20 kg. The Production Manager contacts the purchasing department, who immediately creates a new supplier delivery note for an urgent sugar order from a local supplier. When the sugar arrives the next morning and the delivery note is validated, the sugar stock rises above the required level.

The Production Manager returns to the production order, re-checks availability — all materials are now sufficient — and changes the status to **Confirmed**. The system reserves the raw materials against this order.

---

### Step 4 — Production Runs

Production begins on Tuesday. The Storekeeper physically issues the raw materials to the production floor in the quantities specified on the production order. By end of day Wednesday, the production team has produced 3,960 usable units. Forty jars were rejected due to seal defects detected during quality inspection.

The Production Manager records the completion:
- Actual quantity produced (good): 3,960 units
- Rejected: 40 units
- Actual raw materials consumed: matches formula closely, with olives 2 kg over formula due to normal processing variation.

The Production Manager clicks **Complete**. The system immediately:
- Reduces raw material stock by the actual consumed quantities (including the 2 kg extra olives).
- Adds 3,960 units to the Olive Jam 250g Jar finished product stock.
- Records the 40 rejected units in the waste log.

The production order status changes to **Completed**.

---

### Step 5 — Finished Goods Are Ready

The Storekeeper checks the finished products stock. Olive Jam 250g Jar now shows 4,760 units (800 existing + 3,960 new). The low-stock alert is no longer active.

---

### Step 6 — Client Orders Are Fulfilled

Sales Staff receive a formal order from a key client for 2,000 jars. They create a new **Client Delivery Note**: select the client, enter tomorrow as the delivery date, and add one line item — Olive Jam 250g Jar, quantity 2,000 at the agreed price of 1.85 per jar.

The system confirms that 4,760 units are in stock and the quantity of 2,000 is available. No warning is triggered. The delivery note is saved in **Draft** status.

The next morning, the Storekeeper prepares the 2,000 jars on pallets, checks the delivery note in the system, and marks it as **Confirmed**. When the delivery vehicle leaves the factory, the Storekeeper or Sales Staff marks the note as **Dispatched**. The system reduces finished product stock by 2,000 units. Olive Jam 250g Jar stock is now 2,760 units.

The client signs the delivery note upon receiving the goods. The delivery note is updated to **Delivered** status.

---

### Step 7 — Invoice Is Generated

The Accountant reviews the list of dispatched delivery notes waiting for invoicing. The delivery note for 2,000 jars appears in the list. The Accountant opens it and selects **Generate Invoice**.

The system creates a pre-filled invoice:
- Client: the purchasing client
- Delivery note reference: linked
- Line item: Olive Jam 250g Jar × 2,000 @ 1.85 = 3,700.00
- Tax (19%): 703.00
- **Total Due: 4,403.00**
- Payment due date: 30 days from today (per client's payment terms)

The Accountant reviews, makes no changes, and finalises the invoice. The invoice status is **Issued**. The delivery note status updates to **Invoiced**.

---

### Step 8 — Payment Is Received

Twenty-two days later, the client transfers the full payment. The Accountant records the payment:
- Date: today
- Amount: 4,403.00
- Method: bank transfer
- Reference: the client's bank transfer reference number

The invoice status changes to **Paid**. The outstanding amount on the client's account returns to zero.

---

### Step 9 — Expenses Are Recorded

Throughout the week, the factory incurs several expenses. The Accountant records each one:

- Electricity bill: 380.00 — Category: Utilities
- Fuel for delivery vehicle: 95.00 — Category: Transport
- Packaging tape and boxes purchased: 210.00 — Category: Packaging and Consumables

All three are validated immediately as they are below the approval threshold. They are now visible in the expense reports.

---

### Step 10 — Management Reviews Performance

At the end of the month, the Manager opens the Reports module and reviews:

- The **Profitability Overview**: revenue of 38,400 from the month's invoices, raw material costs of 14,200, gross profit of 24,200, total operating expenses of 9,800, net result of 14,400.
- The **Invoice Ageing Report**: two invoices totalling 7,200 are overdue by 15 days. The Manager asks the Accountant to follow up.
- The **Stock Report**: sugar is close to minimum stock again. The Manager tells the Storekeeper to order more before the next production run.
- The **Production Efficiency Report**: one production order last week consumed 4% more citric acid than the formula specified. The Production Manager is asked to investigate.

All of this information comes from the same system, connected and consistent, without manual assembly.

---

## 14. Functional Rules and Validations

This section defines the core business rules that the system must enforce at all times. These rules protect data integrity and ensure that the ERP reflects reality accurately.

### 14.1 Stock and Quantity Rules

**Rule 1 — No negative stock for finished products.**  
A client delivery note cannot be dispatched if the quantity requested exceeds the available finished product stock. The system blocks the dispatch action and displays the available quantity. The Sales Staff must reduce the quantity or wait for a new production run.

**Rule 2 — Production order material check.**  
A production order cannot be moved to Confirmed status if any required raw material has insufficient stock (below the required quantity). The system displays which materials are short and by how much. The Production Manager must either reduce the planned quantity or wait for new stock.

**Rule 3 — Stock adjustments require a reason.**  
Every manual stock adjustment — whether for raw materials or finished products — must include a written reason. The system does not accept a blank reason field.

**Rule 4 — Stock adjustments above a threshold require approval.**  
Stock adjustments that increase or decrease stock by more than a configurable quantity threshold require Administrator approval before they take effect.

### 14.2 Delivery Note Rules

**Rule 5 — Supplier delivery notes must reference a supplier.**  
A supplier delivery note cannot be validated without a valid, active supplier selected.

**Rule 6 — Supplier delivery notes must have at least one line item.**  
A delivery note with no line items cannot be validated.

**Rule 7 — Validated supplier delivery notes cannot be edited.**  
Once a supplier delivery note is validated, it is locked. Corrections are made via stock adjustments and the note is annotated. Only the Administrator can cancel a validated delivery note, and cancellation reverses all stock changes.

**Rule 8 — Client delivery notes must reference an active client.**  
A delivery note cannot be dispatched to an inactive client.

**Rule 9 — Client delivery notes cannot be dispatched with zero-quantity lines.**  
All line items on a client delivery note must have a quantity greater than zero.

### 14.3 Invoicing Rules

**Rule 10 — Invoices can only be created from dispatched delivery notes.**  
An invoice cannot be created for a delivery note that is still in Draft, Confirmed, or cancelled status. The delivery note must be in Dispatched or Delivered status.

**Rule 11 — Invoice quantities cannot exceed delivered quantities.**  
When creating an invoice, the quantity on any invoice line cannot exceed the quantity on the corresponding delivery note line. The system enforces this at the time of invoice creation.

**Rule 12 — A quantity cannot be invoiced twice.**  
If a partial invoice has already been created for part of a delivery note, subsequent invoices for the same delivery note can only cover the remaining uninvoiced quantity.

**Rule 13 — Paid invoices cannot be cancelled.**  
Once an invoice is fully paid, it cannot be cancelled or edited. To correct it, a credit note must be issued by the Administrator.

**Rule 14 — Invoice due dates are calculated automatically.**  
The payment due date on an invoice is always calculated as: invoice date plus the payment terms defined on the client record. The Accountant can override this date, but the override is logged.

### 14.4 Production Rules

**Rule 15 — Production orders must reference an active formula.**  
A production order cannot be confirmed without a valid, active formula selected.

**Rule 16 — Completed production orders cannot be reopened without Administrator action.**  
Once a production order is marked as Completed, only an Administrator can reopen it for correction.

**Rule 17 — Actual consumption must be recorded before order completion.**  
The Production Manager must confirm the actual quantities of raw materials consumed before the system accepts a production order as Completed.

**Rule 18 — Rejected production quantities are not added to sellable stock.**  
The actual good quantity produced (total produced minus rejected) is the only quantity added to finished product stock. Rejected units are logged but not stocked.

### 14.5 Expense Rules

**Rule 19 — Expenses must have a category and an amount.**  
An expense cannot be saved without a category selected and an amount greater than zero.

**Rule 20 — Expenses above the approval threshold require explicit approval.**  
Expenses above the configurable threshold remain in Draft status and cannot appear in reports until approved by the Administrator or Manager.

### 14.6 User and Access Rules

**Rule 21 — Only Administrators can cancel validated documents.**  
Validated supplier delivery notes, confirmed production orders, and issued invoices can only be cancelled by users with Administrator role. All cancellations are logged with a timestamp and the cancelling user's identity.

**Rule 22 — All actions are timestamped and attributed.**  
Every create, edit, validate, approve, or cancel action in the system records the date, time, and user who performed it. This log is read-only and cannot be altered.

### 14.7 Document Proof Rules

**Rule 23 — High-value supplier delivery notes require a proof document.**  
A supplier delivery note whose total value exceeds the configurable high-value threshold cannot be validated without at least one proof document attached. Below the threshold, proof is strongly recommended and its absence is flagged in the audit log.

**Rule 24 — All stock adjustments require a proof document.**  
No stock adjustment — for either raw materials or finished products — can be submitted (for approval or direct validation) without an attached supporting document. The system blocks submission if the attachment field is empty.

**Rule 25 — Production deviations above tolerance require an incident report.**  
If a production order is completed with raw material over-consumption above 10%, output under-yield above 10%, or a reject rate above the configured threshold, the system requires an attached incident or quality report before the order can be closed. The Production Manager cannot mark the order as Completed without this document.

**Rule 26 — Expenses above the threshold require a proof document.**  
An expense entry above the approval threshold cannot be validated — even by the Administrator — without an attached receipt, invoice, or payment confirmation document. Expenses below the threshold may be validated without a document but the absence is flagged in the audit log.

**Rule 27 — Proof documents are permanent.**  
Once a document is attached to any record (delivery note, adjustment, expense, or production order), it cannot be deleted by any user other than the Administrator. The Administrator's deletion of an attached document is itself logged as an audit event.

### 14.8 Supplier Account Settlement Rules

**Rule 28 — A supplier account settlement cannot exceed the supplier's total outstanding debt.**  
When using the FIFO settlement mode, the payment amount entered by the Accountant cannot be greater than the total unpaid balance across all outstanding invoices for that supplier. The system displays the current total debt before the Accountant enters the amount and blocks entry of an amount that exceeds it.

**Rule 29 — FIFO settlement applies payments to the oldest invoices first.**  
The system always allocates a supplier account payment to invoices in ascending order of invoice date (oldest first). The Accountant cannot manually reorder the allocation. If the last invoice touched is only partially covered, it receives a partial payment and its balance is reduced accordingly.

**Rule 30 — Each FIFO settlement creates individual payment records per invoice touched.**  
The system generates a distinct payment record for each invoice that received an allocation from the settlement. Each record references the originating supplier account payment, enabling full traceability of how the total amount was distributed.

### 14.9 Receipt Rules

**Rule 31 — Receipts are generated only for confirmed payment events.**  
A receipt cannot be issued before a payment has been recorded and confirmed. Draft or pending payment entries do not generate a receipt.

**Rule 32 — A receipt is generated per payment event, not per invoice.**  
For a per-invoice payment, one receipt is generated per payment record. For a FIFO supplier account settlement, one consolidated receipt is generated covering all invoices touched by that single settlement action.

**Rule 33 — Receipts are read-only and immutable once issued.**  
Once generated, a receipt cannot be edited. If a payment is reversed or cancelled, the original receipt is marked as Voided. A new receipt is not automatically created — it is generated only when a new valid payment is recorded.

**Rule 34 — Receipts must display all linked delivery notes.**  
Every receipt — whether purchase-side or sales-side — must list every delivery note associated with each invoice it covers. This chain (receipt → invoice(s) → delivery notes) must be fully visible on the printed or exported document.

**Rule 35 — A receipt number is unique and auto-generated.**  
The system assigns a unique, sequential receipt number to every receipt at the moment it is generated. Receipt numbers follow separate sequences for purchase receipts and sales receipts to avoid confusion (e.g., PR-0041 for purchase, SR-0087 for sales).

**Rule 36 — Partial payment receipts show the outstanding balance.**  
When a client pays only part of an invoice, the receipt for that partial payment must clearly display the amount paid in this transaction, the total invoice amount, and the remaining balance still outstanding.

---

## 15. Document Statuses Reference

This section summarises the status lifecycle for each major document type in the system.

### Supplier Delivery Note

| Status | Meaning | Stock Effect |
|---|---|---|
| Draft | Being entered; not yet validated | None |
| Validated | Accepted and stock updated | Raw material stock increases |
| Cancelled | Voided by Administrator | Raw material stock reversal |

### Production Order

| Status | Meaning | Stock Effect |
|---|---|---|
| Draft | Created but not reviewed | None |
| Confirmed | Approved and materials reserved | Optional reservation of raw materials |
| In Progress | Production physically underway | None yet |
| Completed | Production finished; actuals recorded | Raw materials decrease; finished goods increase |
| Cancelled | Order voided | Reservations released; no stock change if not started |

### Client Delivery Note

| Status | Meaning | Stock Effect |
|---|---|---|
| Draft | Being prepared | None |
| Confirmed | Goods verified and ready | None (no stock change yet) |
| Dispatched | Goods have left the factory | Finished goods stock decreases |
| Delivered | Client confirmed receipt | No further stock change |
| Invoiced | An invoice has been generated | None |
| Cancelled | Order voided before dispatch | No stock change if cancelled before Dispatched |

### Client Invoice

| Status | Meaning | Financial Effect |
|---|---|---|
| Draft | Being prepared | None |
| Issued | Sent to client; awaiting payment | Outstanding balance increases |
| Partially Paid | Part of the invoice has been received | Outstanding balance reduces by amount received |
| Paid | Full amount received | Invoice closed; outstanding balance zero |
| Cancelled | Invoice voided | Outstanding balance reversed |

### Expense

| Status | Meaning | Reporting Effect |
|---|---|---|
| Draft | Entered but awaiting approval | Not included in expense reports |
| Validated | Approved and confirmed | Included in all expense reports and profitability |
| Rejected | Declined by approver | Excluded from reports; visible for review |

### Supplier Account Payment (FIFO Settlement)

| Status | Meaning | Financial Effect |
|---|---|---|
| Draft | Being prepared by Accountant | None |
| Applied | Confirmed and distributed across invoices | Outstanding invoice balances reduced; supplier debt reduced |
| Cancelled | Voided by Administrator | All affected invoice balances restored to pre-settlement values |

### Stock Adjustment

| Status | Meaning | Stock Effect |
|---|---|---|
| Draft | Submitted, awaiting approval | None |
| Approved | Approved by Administrator; stock updated | Stock increases or decreases |
| Rejected | Declined by Administrator | No stock change |
| Auto-Validated | Below threshold; validated immediately | Stock updated immediately |

### Purchase Receipt (Supplier Payment Receipt)

| Status | Meaning |
|---|---|
| Issued | Generated upon confirmation of a supplier payment; available for print/export |
| Voided | The originating payment was reversed or cancelled; receipt is invalidated |

### Sales Receipt (Client Payment Receipt)

| Status | Meaning |
|---|---|
| Issued | Generated upon recording a client payment (full or partial); available for print/export |
| Voided | The originating payment was reversed or cancelled; receipt is invalidated |

---

## 16. Supplier Account Settlement — FIFO Payment Mode

### 16.1 Purpose and Context

In standard AP (Accounts Payable) operations, a supplier may send a monthly statement listing several unpaid invoices. Rather than paying each invoice individually, the factory transfers a lump sum to the supplier — for example, 15,000 DZD — and expects the system to distribute that payment intelligently across whatever invoices are outstanding.

This is what the Supplier Account Settlement function provides. It is the second and complementary payment mode in the system (the first being per-invoice direct payment, described in earlier sections). The two modes coexist and can both be used with the same supplier.

### 16.2 When to Use This Mode

The Supplier Account Settlement mode is appropriate when:

- The factory pays a supplier periodically (weekly, monthly) in a round-sum amount rather than invoice-by-invoice.
- The Accountant wants to clear as many invoices as possible with a single payment entry.
- A supplier calls to say "we transferred X amount" and the Accountant needs to apply it without knowing which specific invoices the supplier intended it to cover.
- Multiple small invoices from a supplier have accumulated and the factory wishes to settle them all at once.

### 16.3 Where This Feature Lives

The Supplier Account Settlement action is accessible from the **Supplier Detail Page**. A clearly labelled button — **"Régler le compte fournisseur"** (Settle Supplier Account) — is available to the Accountant and Administrator when the supplier has one or more outstanding unpaid invoices.

### 16.4 The Settlement Workflow

**Step 1 — Open the Supplier Account**  
The Accountant navigates to the supplier's profile. The system displays:

- A summary of all outstanding invoices, listed oldest-first, with their individual balances.
- The **Total Outstanding Debt** for this supplier — the sum of all unpaid balances across all invoices.

| Invoice No. | Invoice Date | Due Date | Original Amount | Amount Paid | Balance Due |
|---|---|---|---|---|---|
| INV-0041 | 2026-01-10 | 2026-02-10 | 8,400.00 | 0.00 | 8,400.00 |
| INV-0055 | 2026-02-03 | 2026-03-05 | 3,200.00 | 1,000.00 | 2,200.00 |
| INV-0062 | 2026-03-15 | 2026-04-15 | 5,100.00 | 0.00 | 5,100.00 |
| **Total** | | | | | **15,700.00** |

**Step 2 — Enter the Payment Amount**  
The Accountant clicks the **"Régler le compte fournisseur"** button. A settlement form opens showing the total outstanding balance. The Accountant enters:

| Field | Description |
|---|---|
| Payment Date | The date the payment was made or received by the supplier |
| Payment Amount | The total amount being settled (must be ≤ total outstanding debt) |
| Payment Method | Bank transfer, cheque, cash, or other |
| Bank Reference | The bank transfer reference or cheque number |
| Notes | Any remarks (e.g., "Monthly wire transfer for February invoices") |
| Proof Document | Attachment of bank transfer confirmation or payment receipt |

**Step 3 — System Calculates FIFO Allocation**  
Before the Accountant confirms, the system displays a **preview** of how the payment amount will be distributed:

| Invoice No. | Invoice Date | Balance Due | Amount Applied | Remaining Balance |
|---|---|---|---|---|
| INV-0041 | 2026-01-10 | 8,400.00 | 8,400.00 | 0.00 ✓ Cleared |
| INV-0055 | 2026-02-03 | 2,200.00 | 2,200.00 | 0.00 ✓ Cleared |
| INV-0062 | 2026-03-15 | 5,100.00 | 4,400.00 | 700.00 (partial) |
| **Total Applied** | | **15,700.00** | **15,000.00** | **700.00 remains** |

The Accountant reviews this preview. If the allocation is acceptable, they confirm. If they wish to pay a different amount, they return to Step 2 and adjust.

**Step 4 — Confirm and Apply**  
The Accountant clicks **Confirm Settlement**. The system simultaneously:

1. Creates a **Supplier Account Payment** record linked to the supplier with the total amount and all metadata.
2. Creates individual payment allocation records for each invoice that was touched, each showing the amount applied and the resulting balance.
3. Updates each touched invoice's balance and status:
   - Invoices fully cleared move to **Paid** status.
   - Invoices partially cleared move to **Partially Paid** status with the updated remaining balance.
4. Records an audit log entry describing the settlement event, the user, the timestamp, the total amount, and the list of invoices affected.
5. Makes a **supplier payment receipt** available for the entire settlement. This receipt lists the total amount paid, the payment method and reference, and for each invoice touched: the invoice number, the invoice date, the amount allocated, the resulting balance, and all supplier delivery notes that were covered by that invoice. This receipt is the factory's official record of having settled its debt with the supplier. The full specification is in Section 19.

### 16.5 FIFO Ordering Logic

The system always processes invoices in **ascending order of invoice date** — the oldest invoice is always paid first. If two invoices share the same date, the one with the lower invoice number is processed first.

The Accountant cannot override this ordering. This rule ensures consistency, prevents preferential treatment of newer invoices, and aligns with standard accounts payable practice.

### 16.6 Proof Document Requirement

A proof document (bank transfer confirmation, payment receipt, or cheque copy) must be attached to the settlement before it can be confirmed. The system blocks confirmation without an attachment. This document is stored permanently with the settlement record and is viewable from both the settlement record and from each individual invoice that was affected.

### 16.7 Cancelling a Settlement

If a settlement was applied in error (e.g., the wrong amount was entered, or the bank transfer was reversed), the Administrator can cancel the settlement. Cancellation reverses all allocations: every invoice that was fully or partially paid by the settlement is restored to its pre-settlement balance and status. The cancellation itself is recorded as an audit event. A settlement that has been cancelled cannot be reactivated — a new settlement must be created if needed.

### 16.8 Viewing Settlement History

From the supplier's profile, the Accountant or Administrator can view the full history of all settlement payments made to that supplier, including:

- Date and amount of each settlement.
- Which invoices were touched by each settlement and how much was allocated to each.
- The current balance of every invoice.
- The total amount paid to this supplier over any selected period.

---

## 17. Document Proof and Evidence Attachments

### 17.1 Purpose

This section defines the system-wide policy for attaching supporting documents to critical operations. Proof attachments serve three purposes: they create an evidence trail that protects the factory in commercial disputes, they discourage informal or undocumented adjustments by requiring accountability, and they give the Administrator a complete documentary record for internal audits and any external inspections.

### 17.2 Operations That Require or Recommend Proof Documents

The following table summarises the proof document requirements across all modules:

| Operation | Module | Proof Required? | Consequence if Missing |
|---|---|---|---|
| Supplier delivery note validation — high-value | Purchasing | **Mandatory** | System blocks validation |
| Supplier delivery note validation — standard | Purchasing | Recommended | Warning shown; flagged in audit log |
| Damaged goods receipt | Purchasing | **Mandatory** | System blocks validation |
| Raw material stock adjustment — increase | Stock | **Mandatory** | System blocks submission |
| Raw material stock adjustment — decrease | Stock | **Mandatory** | System blocks submission |
| Finished product stock adjustment | Stock | **Mandatory** | System blocks submission |
| Production order completion — with deviation | Production | **Mandatory** | System blocks order closure |
| Production order completion — normal | Production | Recommended | Warning shown; flagged if missing |
| Expense entry — above approval threshold | Expenses | **Mandatory** | System blocks validation |
| Expense entry — below threshold | Expenses | Recommended | Flagged in audit log if missing |
| Supplier account settlement | Purchasing | **Mandatory** | System blocks settlement confirmation |
| Client delivery note dispatch | Sales | Optional | No restriction; available for record-keeping |

### 17.3 Accepted File Types and Size Limits

The system accepts the following file types for all proof documents:

- **PDF** — preferred for printed documents, forms, and multi-page reports
- **JPEG / JPG** — acceptable for photographs of goods, receipts, or labels
- **PNG** — acceptable for screenshots, scanned documents, and quality reports

Each attachment has a maximum file size of 10 MB per file. Multiple documents can be attached to a single record (for example, both a supplier invoice and a photograph of received goods on the same delivery note). There is no limit on the number of attachments per record.

### 17.4 How Attachments Work

When a user is creating or editing a record that supports attachments, an **Attach Document** section appears at the bottom of the form. The user clicks the attachment area, selects or drags the file, and the system uploads and stores it. The attachment appears immediately with its filename, file size, upload date, and the name of the user who uploaded it.

Once a record is validated or confirmed, attachments can no longer be deleted by regular users. Only the Administrator can delete an attachment from a validated record, and any such deletion is permanently recorded in the audit log.

### 17.5 Viewing Attachments

Any authorised user who can view a record can also view and download its attachments. Attachments are displayed as a list below the record's main details, each showing the filename, upload date, and uploader name. Clicking an attachment opens it in a preview panel (for images and PDFs) or downloads it.

### 17.6 Proof Documents in Reports

The Administrator's audit reports (Section 18) include visibility into which operations were performed with and without proof documents. A dedicated **Missing Proof Report** lists all records where a proof document was recommended or required but was not provided at the time of validation. This report is sorted by date and can be filtered by module, allowing the Administrator to identify habitual gaps in documentation discipline.

---

## 18. Audit Logs and Administrator Monitoring

### 18.1 Purpose

The audit log system is the factory's internal oversight mechanism. It records every sensitive operation that takes place in the ERP — who did what, when, and what the outcome was — and makes this information accessible to the Administrator in a dedicated audit dashboard. The goal is not to micromanage staff but to give the Administrator the tools to detect errors, identify patterns of irregular behaviour, and maintain the integrity of all financial and operational records.

### 18.2 What Is Logged

The following event types are captured in the audit log:

**Document Events**
- Creating, editing, validating, confirming, dispatching, or cancelling any document (delivery note, invoice, production order, expense)
- Reopening a completed or validated document
- Attaching a proof document to any record
- Deleting an attachment from a validated record

**Stock Events**
- Creating a stock adjustment (raw material or finished product)
- Approving or rejecting a stock adjustment
- Validating a production order completion with deviations above tolerance
- Manual overrides of reserved stock quantities

**Financial Events**
- Issuing, paying, or cancelling a supplier or client invoice
- Recording a per-invoice payment
- Creating, confirming, or cancelling a supplier account settlement (FIFO)
- Recording a client payment
- Creating, validating, or rejecting an expense entry

**User and Access Events**
- User login and logout
- Failed login attempts
- Changes to user roles or permissions
- Password reset actions by Administrator

**Administrator Override Events**
- Any action taken by an Administrator that reverses, corrects, or overrides a previously validated record
- Deletion of a proof document attachment
- Cancellation of a validated delivery note, issued invoice, or confirmed production order

### 18.3 What Each Log Entry Contains

Every audit log entry records the following:

| Field | Description |
|---|---|
| Timestamp | Exact date and time of the event (to the second) |
| User | The name and role of the user who performed the action |
| Event Type | Category of the event (see 18.2) |
| Module | Which module the event occurred in |
| Record Reference | The document number or record identifier affected |
| Action Taken | A plain-language description of what was done (e.g., "Stock adjustment approved — Olives +50 kg") |
| Previous Value | The value or status before the change (where applicable) |
| New Value | The value or status after the change |
| Proof Document | Whether a proof document was present — Yes / No / Not Required |
| IP Address | The network address from which the action was performed |

Audit log entries are created by the system automatically. No user — including the Administrator — can edit, delete, or suppress an audit log entry. The log is append-only.

### 18.4 The Administrator Audit Dashboard

The Administrator has access to a dedicated **Audit & Oversight Dashboard** in addition to the main management dashboard. This dashboard is not visible to other roles. It contains the following panels:

#### Recent Activity Feed
A live, reverse-chronological list of all audit events across all modules from the last 48 hours. Each entry shows the event type, user, affected record, and a brief description. The feed updates automatically. The Administrator can click any entry to open the full detail of the related record.

#### Sensitive Operations Summary
A set of counters showing, for the current day and current month:
- Number of stock adjustments submitted and their approval status (pending / approved / rejected)
- Number of documents validated without a proof attachment
- Number of Administrator overrides performed
- Number of cancelled validated documents
- Number of production orders closed with deviations

These counters are clickable and expand into a filtered list of the relevant events.

#### Pending Approval Queue
A consolidated list of all items currently awaiting Administrator action:
- Stock adjustments awaiting approval (with submitter, material, quantity, and reason)
- Expenses above threshold awaiting approval (with submitter, category, amount, and attached document status)
- Any other operations flagged for Administrator review

The Administrator can approve or reject items directly from this panel without navigating to each module separately.

#### Unproven Validations Alert
A highlighted panel listing all records that were validated in the last 30 days without a required proof document. For each entry, the Administrator sees the record type, reference number, validating user, date, and a button to open the record and add a retroactive proof document. This panel remains visible until all flagged records either have a document attached or are acknowledged by the Administrator as exempt.

#### Administrator Override Log
A dedicated log showing only the actions that were taken by Administrator accounts, specifically those that modified or reversed a previously validated record. This log serves as a self-accountability mechanism and is useful if the factory is ever subject to an external audit.

### 18.5 Audit Log Reports

The following reports are available in the Reports module (Section 12) under the Audit category, accessible only to the Administrator:

**Full Audit Log Report**  
A searchable, exportable list of all audit events, filterable by date range, user, module, event type, and record reference. Can be exported as a spreadsheet for external review.

**Missing Proof Documents Report**  
All records (delivery notes, adjustments, expenses, production completions) where a proof document was recommended or required but not present at validation time, over any selected date range. Sortable by module, user, and date.

**Stock Adjustment History Report**  
All stock adjustments over a selected period — approved, rejected, and pending — with submitter, material, quantity, reason, proof document status, and approval outcome. Useful for periodic stock integrity reviews.

**User Activity Report**  
For any selected user and date range, a summary of all actions they performed in the system — records created, validated, modified, or cancelled. Useful for reviewing the activity of a staff member who is leaving or has changed roles.

**Override and Correction Report**  
A focused report on all Administrator overrides, reversals, and corrections, with before/after values. This is the primary document used in any internal or external audit of the ERP's records.

### 18.6 Data Retention

Audit logs are retained for a minimum of three years. The Administrator cannot delete audit log entries. If the factory requires longer retention for compliance purposes, the Administrator can export the log to an external file at any time. Archived exports are stored outside the ERP but can be referenced in the audit dashboard.

---

---

## 19. Receipt Generation — Purchase and Sales Directions

### 19.1 Purpose and Distinction from Invoices

A receipt is fundamentally different from an invoice. An **invoice** is a demand for payment — it tells the other party what they owe and by when. A **receipt** is a confirmation that a payment actually occurred — it tells the other party what was paid, when, through what method, and against which obligations.

The ERP generates receipts in two directions, reflecting the two financial flows of the factory:

- **Purchase-side receipts (Supplier Payment Receipts):** The factory is the paying party. It has received goods from a supplier, been invoiced, and has now settled its debt. The receipt confirms what the factory paid to whom, against which invoice(s), and which delivery notes those invoices covered.

- **Sales-side receipts (Client Payment Receipts):** The factory is the receiving party. It has delivered goods to a client, issued an invoice, and has now received payment. The receipt confirms what the client paid, against which invoice, and which delivery notes that invoice covered.

In both cases, the receipt is the closing document of a financial transaction. It is the proof that money moved, and it must carry with it the full chain of commercial documents that justified the payment.

### 19.2 The Document Chain Principle

Receipts in this system are not standalone summaries — they are the final link in a traceable document chain:

```
PURCHASE DIRECTION
─────────────────────────────────────────────────────────
Supplier Delivery Note(s)  ──►  Supplier Invoice  ──►  Payment  ──►  Purchase Receipt
      (goods received)           (amount owed)         (money sent)     (proof of settlement)

SALES DIRECTION
─────────────────────────────────────────────────────────
Client Delivery Note(s)  ──►  Client Invoice  ──►  Payment  ──►  Sales Receipt
     (goods dispatched)         (amount billed)     (money received)  (proof of receipt)
```

Every receipt must display this full chain. A receipt that does not reference its originating invoice and delivery notes is incomplete and cannot be issued by the system.

---

### 19.3 Purchase-Side Receipts — Supplier Payment Receipts

#### 19.3.1 When a Purchase Receipt Is Generated

A purchase receipt is generated in two scenarios:

**Scenario A — Per-Invoice Payment Receipt**  
The Accountant has paid a specific supplier invoice directly (Mode 1 payment, as described in Section 3.6). Upon confirming the payment, the system automatically generates a purchase receipt for that payment event. The receipt covers one invoice and lists all supplier delivery notes linked to that invoice.

**Scenario B — FIFO Settlement Receipt**  
The Accountant has performed a supplier account settlement (Section 16), paying a lump sum that cleared or partially cleared multiple invoices. Upon confirming the settlement, the system generates a single consolidated purchase receipt covering the entire settlement. This receipt references all invoices that were touched and, for each invoice, lists the delivery notes it covered.

#### 19.3.2 Content of a Purchase Receipt

Every purchase receipt contains the following sections and fields:

**Header Block — Factory Identity**

| Field | Value |
|---|---|
| Receipt Title | "Payment Receipt" / "Reçu de Paiement" |
| Receipt Number | Unique auto-generated reference (format: PR-YYYY-NNNN, e.g., PR-2026-0041) |
| Receipt Date | The date the payment was confirmed in the system |
| Issued By | The factory's name, address, and tax registration number |

**Payment Details Block**

| Field | Value |
|---|---|
| Paid To (Supplier) | Supplier name, address, tax number |
| Total Amount Paid | The total monetary amount of this payment |
| Payment Date | The date the transfer or payment was made |
| Payment Method | Bank transfer, cheque, cash, or other |
| Bank / Payment Reference | The transaction reference, cheque number, or transfer ID |
| Notes | Any remarks recorded at the time of payment |

**Invoices Covered Block**  
For each supplier invoice covered by this payment:

| Field | Value |
|---|---|
| Invoice Number | The supplier invoice reference |
| Invoice Date | The date the invoice was issued |
| Invoice Total | The original full amount of the invoice |
| Previously Paid | Any amounts paid against this invoice before this receipt |
| Amount Applied (this payment) | How much of this payment was allocated to this invoice |
| Remaining Balance | The invoice balance after this payment |
| Invoice Status | Paid in Full / Partially Paid |

**Delivery Notes Covered Block**  
For each invoice listed above, the system lists every supplier delivery note that was linked to that invoice:

| Field | Value |
|---|---|
| Delivery Note Number | The supplier delivery note reference |
| Delivery Date | The date the goods were received |
| Raw Materials Received | A summary line listing each material and quantity (e.g., Olives 450 kg, Sugar 150 kg) |
| Delivery Note Total Value | The total value of goods on that delivery note |

**Summary Footer**

| Field | Value |
|---|---|
| Total Amount Paid | Repeated for clarity |
| Total Invoices Cleared | Count of invoices fully settled |
| Total Invoices Partially Paid | Count of invoices with remaining balance |
| Outstanding Balance with Supplier | The remaining total debt after this payment |
| Authorised Signature | Space for the Accountant or Administrator signature |

#### 19.3.3 Example — Consolidated FIFO Purchase Receipt

> **Receipt No.:** PR-2026-0041  
> **Date:** 25 April 2026  
> **Paid To:** Société Agricole Berbère — 12 Rue des Oliviers, Béjaïa  
> **Total Paid:** 15,000.00 DZD — Bank Transfer — Ref: CCP-29042026-BEJ  
>
> **Invoices Covered:**
>
> | Invoice | Date | Total | Applied | Balance |
> |---|---|---|---|---|
> | INV-0041 | 10 Jan 2026 | 8,400.00 | 8,400.00 | 0.00 ✓ Paid |
> | INV-0055 | 03 Feb 2026 | 3,200.00 | 2,200.00 | 0.00 ✓ Paid |
> | INV-0062 | 15 Mar 2026 | 5,100.00 | 4,400.00 | 700.00 Partial |
>
> **Delivery Notes for INV-0041:**  
> — DN-2026-018 · 10 Jan 2026 · Olives 450 kg, Sugar 150 kg · 8,400.00 DZD
>
> **Delivery Notes for INV-0055:**  
> — DN-2026-024 · 02 Feb 2026 · Citric Acid 20 kg, Glass Jars 5,000 pcs · 3,200.00 DZD
>
> **Delivery Notes for INV-0062:**  
> — DN-2026-031 · 14 Mar 2026 · Olives 800 kg · 5,100.00 DZD
>
> **Remaining balance with supplier after this payment: 700.00 DZD**

---

### 19.4 Sales-Side Receipts — Client Payment Receipts

#### 19.4.1 When a Sales Receipt Is Generated

A sales receipt is generated every time the Accountant records a payment from a client against a client invoice. This happens regardless of whether the payment is full or partial. Every distinct payment event generates its own receipt.

If a client makes three separate partial payments against a single invoice — for example, paying 30% on week one, 40% on week three, and the final 30% on week five — the system generates three separate sales receipts, one for each payment event. Each receipt clearly shows the portion paid in that transaction and the outstanding balance remaining.

#### 19.4.2 Content of a Sales Receipt

Every sales receipt contains the following sections and fields:

**Header Block — Factory Identity**

| Field | Value |
|---|---|
| Receipt Title | "Receipt of Payment" / "Reçu de Règlement" |
| Receipt Number | Unique auto-generated reference (format: SR-YYYY-NNNN, e.g., SR-2026-0087) |
| Receipt Date | The date the payment was recorded |
| Issued By | The factory's name, address, and tax registration number |

**Client Block**

| Field | Value |
|---|---|
| Received From (Client) | Client name, billing address, tax registration number |
| Client Code | The client's internal reference code |

**Payment Details Block**

| Field | Value |
|---|---|
| Total Amount Received | The monetary amount of this payment |
| Payment Date | The date the payment was received |
| Payment Method | Bank transfer, cheque, cash, or other |
| Payment Reference | The client's transfer reference, cheque number, or receipt ID |
| Notes | Any remarks recorded at the time of payment |

**Invoice Covered Block**  
The invoice against which this payment was applied:

| Field | Value |
|---|---|
| Invoice Number | The client invoice reference |
| Invoice Date | The date the invoice was issued |
| Invoice Total | The full original invoice amount |
| Previously Received | Amounts received before this payment event |
| Amount Received (this payment) | The amount covered by this receipt |
| Remaining Balance | Invoice balance after this payment |
| Invoice Status | Paid in Full / Partially Paid — Balance Due: X |

**Delivery Notes Covered Block**  
All client delivery notes that were linked to the invoice on this receipt:

| Field | Value |
|---|---|
| Delivery Note Number | The client delivery note reference |
| Delivery Date | The date the goods were dispatched or delivered |
| Products Delivered | A summary of each product and quantity (e.g., Olive Jam 250g Jar × 2,000) |
| Delivery Note Value | The total value of goods on that delivery note |
| Delivery Status | Dispatched / Delivered |

**Summary Footer**

| Field | Value |
|---|---|
| Total Received (this payment) | The amount on this receipt |
| Total Received to Date | All payments received against this invoice, including this one |
| Outstanding Balance | Remaining amount due on the invoice after this payment |
| Thank-You Note | Optional configurable message (e.g., "Thank you for your payment.") |
| Authorised Signature | Space for Accountant or Administrator signature |

#### 19.4.3 Example — Partial Payment Sales Receipt

> **Receipt No.:** SR-2026-0087  
> **Date:** 25 April 2026  
> **Received From:** Entreprise Djaout & Fils — Zone Industrielle, Sétif  
> **Amount Received:** 1,500.00 DZD — Bank Transfer — Ref: CCP-24042026-SETIF  
>
> **Invoice Covered:**  
> INV-CLI-0112 · Issued 02 April 2026 · Total: 4,403.00 DZD  
> Previously received: 0.00 DZD  
> Received this payment: **1,500.00 DZD**  
> **Remaining balance: 2,903.00 DZD**  
>
> **Delivery Notes on this Invoice:**  
> — DN-CLI-2026-044 · 01 Apr 2026 · Olive Jam 250g Jar × 2,000 · 3,700.00 DZD · Delivered ✓  
> — DN-CLI-2026-047 · 01 Apr 2026 · Tomato Paste 500g × 300 · 703.00 DZD · Delivered ✓  
>
> *Balance of 2,903.00 DZD remains outstanding. Payment due by 02 May 2026.*

---

### 19.5 Multi-Delivery-Note Invoices

An invoice in this system can cover multiple delivery notes — for example, when all deliveries made to a client during a given week are consolidated onto a single end-of-week invoice. In this case, the receipt for a payment against that invoice lists every delivery note that contributed to the invoice, giving the client (or the supplier, on the purchase side) full visibility into exactly what goods were paid for.

This is a critical traceability feature. Without it, a receipt would merely confirm that money moved — it would say nothing about what was received or delivered in exchange. By embedding the full delivery note list, the receipt functions simultaneously as:

- A payment confirmation.
- A goods-received acknowledgement (on the purchase side).
- A delivery acknowledgement (on the sales side).
- A component of the audit trail.

### 19.6 Where Receipts Are Accessed

Receipts are accessible from three places in the system:

**From the Payment Record:**  
Every payment record (whether a per-invoice payment or a settlement allocation) has a **View Receipt** or **Print Receipt** button that opens the receipt immediately.

**From the Invoice Record:**  
Each invoice record shows a list of all payment events and, for each, a link to the corresponding receipt.

**From the Supplier or Client Profile:**  
The transaction history on a supplier or client profile lists all receipts issued, each showing the receipt number, date, amount, and a link to the full document.

### 19.7 Printing and Exporting Receipts

Every receipt can be:

- **Printed** directly from the system, formatted for A4 paper with the factory's standard document header.
- **Exported as a PDF** for digital sharing by email.
- **Downloaded** as an attached document to be filed alongside the related payment proof.

Receipts are not editable after generation. If a receipt must be regenerated (for example, after a correction by the Administrator), the original is voided and a new receipt with a new number is created for the corrected payment.

### 19.8 Receipt Numbering

The system maintains two separate, sequential receipt number series:

- **Purchase Receipts:** PR-YYYY-NNNN (e.g., PR-2026-0001, PR-2026-0002, …)
- **Sales Receipts:** SR-YYYY-NNNN (e.g., SR-2026-0001, SR-2026-0002, …)

Numbers reset annually (at the start of each calendar year) but always include the year prefix so that receipts from different years are never confused. Receipt numbers are assigned at the moment of generation and cannot be changed or reused.

### 19.9 Voided Receipts

If the payment that generated a receipt is subsequently reversed or cancelled by the Administrator, the receipt is marked **Voided**. A voided receipt remains visible in the system for audit purposes — it is not deleted — but it is clearly watermarked as void and cannot be presented as a valid payment confirmation. The associated invoice is restored to its pre-payment status, and a new receipt will be generated when and if a new payment is recorded.

---

---

| Item | Detail |
|---|---|
| Title | Factory ERP System — Functional Specification |
| Version | 1.1 |
| Scope | Small Factory — Full Operations Cycle |
| Modules Covered | Supplier Management, Purchasing, Raw Material Stock, Production, Finished Goods, Client Management, Sales & Delivery, Invoicing, Expenses, Reports, Supplier Account Settlement, Document Proofs, Audit Logs |
| Document Type | Functional Specification (Business Requirements) |
| Not Covered | Technical architecture, database design, API specifications, UI/UX designs, integrations |
