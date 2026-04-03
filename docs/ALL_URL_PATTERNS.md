# Factory Management System - Complete URL Patterns

Generated automatically from all urls.py files. Prefixes based on main factory_management/urls.py includes.

## Main Project URLs (factory_management/urls.py)

| Pattern         | View              | Name |
| --------------- | ----------------- | ---- |
| `admin/`        | Django Admin      | -    |
| `accounts/`     | accounts.urls     | -    |
| `catalog/`      | catalog.urls      | -    |
| `suppliers/`    | suppliers.urls    | -    |
| `clients/`      | clients.urls      | -    |
| `supplier-ops/` | supplier_ops.urls | -    |
| `production/`   | production.urls   | -    |
| `stock/`        | stock.urls        | -    |
| `sales/`        | sales.urls        | -    |
| `expenses/`     | expenses.urls     | -    |
| `reporting/`    | reporting.urls    | -    |
| `settings/`     | core.urls         | -    |
| `` (root)       | core.urls         | -    |

## accounts/ (Prefix: /accounts/)

| Full Path                             | View                     | Name               |
| ------------------------------------- | ------------------------ | ------------------ |
| /accounts/login/                      | views.login_view         | login              |
| /accounts/logout/                     | views.logout_view        | logout             |
| /accounts/users/                      | views.user_management    | user_management    |
| /accounts/users/<int:user_id>/toggle/ | views.toggle_user_status | toggle_user_status |
| /accounts/audit-log/                  | views.audit_log          | audit_log          |

## catalog/ (Prefix: /catalog/)

| Full Path                                      | View                           | Name                     |
| ---------------------------------------------- | ------------------------------ | ------------------------ |
| /catalog/raw-materials/                        | views.raw_materials_list       | raw_materials_list       |
| /catalog/raw-materials/create/                 | views.raw_material_create      | raw_material_create      |
| /catalog/raw-materials/<int:material_id>/      | views.raw_material_detail      | raw_material_detail      |
| /catalog/raw-materials/<int:material_id>/edit/ | views.raw_material_edit        | raw_material_edit        |
| /catalog/finished-products/                    | views.finished_products_list   | finished_products_list   |
| /catalog/finished-products/create/             | views.finished_product_create  | finished_product_create  |
| /catalog/finished-products/<int:product_id>/   | views.finished_product_detail  | finished_product_detail  |
| /catalog/check-stock-availability/             | views.check_stock_availability | check_stock_availability |

## clients/ (Prefix: /clients/)

| Full Path                                      | View                              | Name                        |
| ---------------------------------------------- | --------------------------------- | --------------------------- |
| /clients/                                      | views.clients_list                | clients_list                |
| /clients/create/                               | views.client_create               | client_create               |
| /clients/<int:client_id>/                      | views.client_detail               | client_detail               |
| /clients/<int:client_id>/edit/                 | views.client_edit                 | client_edit                 |
| /clients/<int:client_id>/toggle-active/        | views.client_toggle_active        | client_toggle_active        |
| /clients/<int:client_id>/update-credit-status/ | views.client_update_credit_status | client_update_credit_status |
| /clients/search/                               | views.client_search_ajax          | client_search_ajax          |

## core/ (Prefix: /, /settings/)

| Full Path                             | View                    | Name              |
| ------------------------------------- | ----------------------- | ----------------- |
| /dashboard                            | views.dashboard         | dashboard         |
| /company-settings/                    | views.company_settings  | company_settings  |
| /system-parameters/                   | views.system_parameters | system_parameters |
| /update-parameter/<int:parameter_id>/ | views.update_parameter  | update_parameter  |

## expenses/ (Prefix: /expenses/)

| Full Path                                | View                             | Name                       |
| ---------------------------------------- | -------------------------------- | -------------------------- |
| /expenses/dashboard/                     | views.expenses_dashboard         | expenses_dashboard         |
| /expenses/                               | views.expenses_list              | expenses_list              |
| /expenses/create/                        | views.expense_create             | expense_create             |
| /expenses/<int:expense_id>/              | views.expense_detail             | expense_detail             |
| /expenses/<int:expense_id>/validate/     | views.expense_validate           | expense_validate           |
| /expenses/<int:expense_id>/mark-paid/    | views.expense_mark_paid          | expense_mark_paid          |
| /expenses/<int:expense_id>/add-document/ | views.supporting_document_create | supporting_document_create |
| /expenses/report/                        | views.expenses_report            | expenses_report            |

## production/ (Prefix: /production/)

| Full Path                                            | View                           | Name                     |
| ---------------------------------------------------- | ------------------------------ | ------------------------ |
| /production/formulations/                            | views.formulations_list        | formulations_list        |
| /production/formulations/create/                     | views.formulation_create       | formulation_create       |
| /production/formulations/<int:formulation_id>/       | views.formulation_detail       | formulation_detail       |
| /production/formulations/<int:formulation_id>/edit/  | views.formulation_edit         | formulation_edit         |
| /production/production-orders/                       | views.production_orders_list   | production_orders_list   |
| /production/production-orders/create/                | views.production_order_create  | production_order_create  |
| /production/production-orders/<int:order_id>/        | views.production_order_detail  | production_order_detail  |
| /production/production-orders/<int:order_id>/launch/ | views.production_order_launch  | production_order_launch  |
| /production/production-orders/<int:order_id>/close/  | views.production_order_close   | production_order_close   |
| /production/yield-report/                            | views.production_yield_report  | production_yield_report  |
| /production/formulation-scaling/                     | views.formulation_scaling_ajax | formulation_scaling_ajax |

## reporting/ (Prefix: /reporting/)

| Full Path                                | View                           | Name                     |
| ---------------------------------------- | ------------------------------ | ------------------------ |
| /reporting/                              | views.reporting_dashboard      | reporting_dashboard      |
| /reporting/financial-result/             | views.financial_result_report  | financial_result_report  |
| /reporting/receivables-aging/            | views.receivables_aging_report | receivables_aging_report |
| /reporting/payables-aging/               | views.payables_aging_report    | payables_aging_report    |
| /reporting/production-yield/             | views.production_yield_report  | production_yield_report  |
| /reporting/expense-breakdown/            | views.expense_breakdown_report | expense_breakdown_report |
| /reporting/stock-valuation/              | views.stock_valuation_report   | stock_valuation_report   |
| /reporting/export/<str:report_type>/csv/ | views.export_report_csv        | export_report_csv        |
| /reporting/kpi-dashboard/                | views.kpi_dashboard_ajax       | kpi_dashboard_ajax       |

## sales/ (Prefix: /sales/)

| Full Path                                        | View                               | Name                         |
| ------------------------------------------------ | ---------------------------------- | ---------------------------- |
| /sales/dashboard/                                | views.sales_dashboard              | sales_dashboard              |
| /sales/client-dns/                               | views.client_dns_list              | client_dns_list              |
| /sales/client-dns/create/                        | views.client_dn_create             | client_dn_create             |
| /sales/client-dns/<int:dn_id>/                   | views.client_dn_detail             | client_dn_detail             |
| /sales/client-dns/<int:dn_id>/validate/          | views.client_dn_validate           | client_dn_validate           |
| /sales/client-dns/<int:dn_id>/print/             | views.client_dn_print              | client_dn_print              |
| /sales/client-invoices/                          | views.client_invoices_list         | client_invoices_list         |
| /sales/client-invoices/create/                   | views.client_invoice_create        | client_invoice_create        |
| /sales/client-invoices/<int:invoice_id>/         | views.client_invoice_detail        | client_invoice_detail        |
| /sales/client-invoices/<int:invoice_id>/print/   | views.client_invoice_print         | client_invoice_print         |
| /sales/client-invoices/<int:invoice_id>/collect/ | views.client_payment_create        | client_payment_create        |
| /sales/client-payments/<int:payment_id>/receipt/ | views.client_payment_receipt_print | client_payment_receipt_print |

## stock/ (Prefix: /stock/)

| Full Path                                       | View                                | Name                          |
| ----------------------------------------------- | ----------------------------------- | ----------------------------- |
| /stock/raw-materials/                           | views.raw_materials_stock_list      | raw_materials_stock_list      |
| /stock/finished-products/                       | views.finished_products_stock_list  | finished_products_stock_list  |
| /stock/movements/                               | views.stock_movements_list          | stock_movements_list          |
| /stock/raw-materials/<int:material_id>/         | views.raw_material_stock_detail     | raw_material_stock_detail     |
| /stock/finished-products/<int:product_id>/      | views.finished_product_stock_detail | finished_product_stock_detail |
| /stock/adjustments/                             | views.stock_adjustments_list        | stock_adjustments_list        |
| /stock/adjustments/create/                      | views.stock_adjustment_create       | stock_adjustment_create       |
| /stock/adjustments/<int:adjustment_id>/         | views.stock_adjustment_detail       | stock_adjustment_detail       |
| /stock/adjustments/<int:adjustment_id>/approve/ | views.stock_adjustment_approve      | stock_adjustment_approve      |
| /stock/alerts/                                  | views.stock_alerts_dashboard        | stock_alerts_dashboard        |
| /stock/availability-check/                      | views.stock_availability_ajax       | stock_availability_ajax       |

## suppliers/ (Prefix: /suppliers/)

| Full Path                                   | View                         | Name                   |
| ------------------------------------------- | ---------------------------- | ---------------------- |
| /suppliers/                                 | views.suppliers_list         | suppliers_list         |
| /suppliers/create/                          | views.supplier_create        | supplier_create        |
| /suppliers/<int:supplier_id>/               | views.supplier_detail        | supplier_detail        |
| /suppliers/<int:supplier_id>/edit/          | views.supplier_edit          | supplier_edit          |
| /suppliers/<int:supplier_id>/toggle-active/ | views.supplier_toggle_active | supplier_toggle_active |
| /suppliers/search/                          | views.supplier_search_ajax   | supplier_search_ajax   |

## supplier_ops/ (Prefix: /supplier-ops/)

| Full Path                                               | View                          | Name                    |
| ------------------------------------------------------- | ----------------------------- | ----------------------- |
| /supplier-ops/supplier-dns/                             | views.supplier_dns_list       | supplier_dns_list       |
| /supplier-ops/supplier-dns/create/                      | views.supplier_dn_create      | supplier_dn_create      |
| /supplier-ops/supplier-dns/<int:dn_id>/                 | views.supplier_dn_detail      | supplier_dn_detail      |
| /supplier-ops/supplier-dns/<int:dn_id>/validate/        | views.supplier_dn_validate    | supplier_dn_validate    |
| /supplier-ops/supplier-dns/<int:dn_id>/print/           | views.supplier_dn_print       | supplier_dn_print       |
| /supplier-ops/supplier-invoices/                        | views.supplier_invoices_list  | supplier_invoices_list  |
| /supplier-ops/supplier-invoices/create/                 | views.supplier_invoice_create | supplier_invoice_create |
| /supplier-ops/supplier-invoices/<int:invoice_id>/       | views.supplier_invoice_detail | supplier_invoice_detail |
| /supplier-ops/supplier-invoices/<int:invoice_id>/print/ | views.supplier_invoice_print  | supplier_invoice_print  |
| /supplier-ops/supplier-invoices/<int:invoice_id>/pay/   | views.supplier_payment_create | supplier_payment_create |
| /supplier-ops/reconciliation/<int:invoice_id>/          | views.reconciliation_ajax     | reconciliation_ajax     |

_Total: 89 URL patterns. Last updated: Current time._
