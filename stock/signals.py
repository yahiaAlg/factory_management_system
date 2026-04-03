# stock/signals.py
#
# NOTE (spec BR-RM-05): StockMovement records are NEVER deleted — they are
# the immutable audit trail for all stock changes.  The post_delete handler
# below is therefore removed: it contradicts the spec and was also broken
# (missing 'models' and 'Decimal' imports).
#
# The only permitted write paths for stock balances are:
#   - stock.signals.supplier_dn_validated  (via supplier_ops/signals.py)
#   - stock.signals.production_order_closed (via production/signals.py)
#   - stock.signals.client_dn_validated    (via sales/signals.py)
#   - StockAdjustment.approve()
#
# StockMovement.save() already calls update_stock_balance() directly, so no
# post_save signal is needed here either — it would double-update the balance.

# No signal registrations required for stock app.
# Balance updates are handled inside StockMovement.save() → update_stock_balance().
