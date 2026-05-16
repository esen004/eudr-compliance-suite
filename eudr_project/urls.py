from django.contrib import admin
from django.urls import path, include

from core import api_views

api_v1_patterns = [
    path("products", api_views.list_products, name="api_list_products"),
    path("products/<int:product_id>", api_views.product_detail, name="api_product_detail"),
    path("plots", api_views.plots_collection, name="api_plots"),
    path("dds", api_views.dds_collection, name="api_dds"),
    path("dds/<int:dds_id>", api_views.dds_detail, name="api_dds_detail"),
    path("widget/publish", api_views.publish_widget, name="api_publish_widget"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("shopify_auth.urls")),
    path("webhooks/", include("shopify_auth.webhook_urls")),
    path("api/v1/", include((api_v1_patterns, "api_v1"))),
    path("", include("core.urls")),
]
