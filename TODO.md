1 - fix the filter layout and inputs in suppliers ops and dn
2 - make the RAW materials categories create/edit form
3 - fix adjustements line items quantity prev and the deletion and its prepopulation

## How it currently works in your code

1. **Supplier DN created** (draft → pending → validated) → stock movements created automatically via signal
2. **Invoice created separately** → linked to one or more validated DNs → reconciliation runs (qty/price comparison BL vs invoice)
3. **Payment recorded** against a specific invoice → `balance_due` recomputed → invoice marked paid/partially paid

---

## Your described flow vs. what's built

Your flow is actually the standard one and **mostly matches** what's built, with one gap:

| Step                                             | my expectation   | Current code                                                  |
| ------------------------------------------------ | ---------------- | ------------------------------------------------------------- |
| DN validated → stock                             | ✅ Yes           | ✅ Done via signal                                            |
| Invoice covers multiple DNs                      | ✅ Yes           | ✅ `linked_dns` M2M field                                     |
| Pay invoice directly                             | ✅ Yes           | ✅ `SupplierPayment` linked to invoice                        |
| **Pay by total supplier debt** (not per invoice) | ✅ You want this | ❌ Not built — payments are always tied to a specific invoice |

---

## The "total debt" payment gap

What you're describing for the second payment mode is called **supplier account settlement**:

- You record a payment of amount X against the **supplier** (not a specific invoice)
- The system automatically clears invoices **oldest-first** (FIFO) until X is exhausted
- A partially consumed invoice gets its `balance_due` reduced proportionally

This is a common AP (Accounts Payable) pattern. To implement it you'd need:

1. A new `SupplierAccountPayment` model (linked to `Supplier`, not `SupplierInvoice`)
2. A settlement function that fetches unpaid invoices ordered by `due_date` / `invoice_date` ascending and applies the payment amount FIFO until exhausted
3. It creates `SupplierPayment` records (or equivalent) for each invoice touched, updating `balance_due` on each

---

## My recommendation

Keep the current per-invoice payment as-is (it's useful for direct payment on receipt). Add the FIFO settlement as a **separate action** — something like "Régler le compte fournisseur" on the supplier detail page where the manager enters an amount and the system clears invoices automatically. Want me to build that?
