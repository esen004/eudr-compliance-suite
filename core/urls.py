from django.urls import path
from . import views

urlpatterns = [
    # Shopify session token bounce page (REQUIRED for embedded auth)
    path("session-token-bounce", views.session_token_bounce, name="session_token_bounce"),

    # Legal
    path("privacy", views.privacy_policy, name="privacy"),

    # Dashboard
    path("", views.dashboard, name="dashboard"),
    path("sync", views.sync_from_shopify, name="sync"),

    # Operator (merchant company info, required for DDS)
    path("settings", views.operator_settings, name="operator_settings"),

    # Products (EUDR classification + compliance status)
    path("products", views.product_list, name="product_list"),
    path("products/<int:product_id>", views.product_detail, name="product_detail"),
    path("products/<int:product_id>/classify", views.product_classify, name="product_classify"),
    path("products/bulk-classify", views.bulk_classify, name="bulk_classify"),
    path("products/csv-import", views.csv_import_products, name="csv_import_products"),

    # Geolocation Plots
    path("plots", views.plot_list, name="plot_list"),
    path("plots/new", views.plot_create, name="plot_create"),
    path("plots/<int:plot_id>", views.plot_detail, name="plot_detail"),
    path("plots/<int:plot_id>/edit", views.plot_edit, name="plot_edit"),
    path("plots/<int:plot_id>/delete", views.plot_delete, name="plot_delete"),
    path("plots/csv-import", views.csv_import_plots, name="csv_import_plots"),
    path("plots/country-risk", views.country_risk_lookup, name="country_risk_lookup"),

    # Due Diligence Statements
    path("dds", views.dds_list, name="dds_list"),
    path("dds/new", views.dds_create, name="dds_create"),
    path("dds/bulk", views.dds_bulk, name="dds_bulk"),
    path("dds/<int:dds_id>", views.dds_detail, name="dds_detail"),
    path("dds/<int:dds_id>/submit", views.dds_submit, name="dds_submit"),
    path("dds/<int:dds_id>/pdf", views.dds_pdf, name="dds_pdf"),
    path("dds/<int:dds_id>/withdraw", views.dds_withdraw, name="dds_withdraw"),

    # API tokens (Enterprise feature)
    path("api-tokens", views.api_tokens, name="api_tokens"),

    # Storefront widget (write EUDR metafields to Shopify products)
    path("widget/publish", views.publish_widget_metafields, name="publish_widget"),

    # Compliance overview
    path("compliance", views.compliance_report, name="compliance_report"),
    path("compliance/audit", views.audit_log, name="audit_log"),

    # Billing
    path("billing/select", views.billing_select, name="billing_select"),
    path("billing/callback", views.billing_callback, name="billing_callback"),
]
