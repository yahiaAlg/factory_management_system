from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('catalog/', include('catalog.urls')),
    path('suppliers/', include('suppliers.urls')),
    path('clients/', include('clients.urls')),
    path('supplier-ops/', include('supplier_ops.urls')),
    path('production/', include('production.urls')),
    path('stock/', include('stock.urls')),
    path('sales/', include('sales.urls')),
    path('expenses/', include('expenses.urls')),
    path('reporting/', include('reporting.urls')),
    path('settings/', include('core.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)