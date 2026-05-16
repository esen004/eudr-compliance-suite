from django.contrib import admin

from .models import (
    Shop,
    GeolocationPlot,
    EUDRProduct,
    DueDiligenceStatement,
    ComplianceAudit,
    APIToken,
)


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ["name", "shop", "last_4", "is_active", "created_at", "last_used_at"]
    list_filter = ["is_active"]
    readonly_fields = ["token", "last_4", "created_at", "last_used_at"]


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ["shopify_domain", "store_name", "plan", "billing_status", "is_active"]
    list_filter = ["plan", "billing_status", "is_active"]
    search_fields = ["shopify_domain", "store_name", "store_email"]


@admin.register(GeolocationPlot)
class GeolocationPlotAdmin(admin.ModelAdmin):
    list_display = ["name", "shop", "country", "plot_type", "area_hectares", "country_risk"]
    list_filter = ["country", "plot_type", "country_risk"]
    search_fields = ["name", "country", "region", "supplier_name"]


@admin.register(EUDRProduct)
class EUDRProductAdmin(admin.ModelAdmin):
    list_display = ["title", "shop", "commodity", "hs_code", "is_in_scope", "is_compliant"]
    list_filter = ["is_in_scope", "is_compliant", "commodity"]
    search_fields = ["title", "vendor", "hs_code"]


@admin.register(DueDiligenceStatement)
class DDSAdmin(admin.ModelAdmin):
    list_display = ["__str__", "shop", "status", "country_of_production", "risk_level", "created_at"]
    list_filter = ["status", "risk_level", "country_of_production"]
    search_fields = ["eu_reference_number", "eu_verification_number"]


@admin.register(ComplianceAudit)
class ComplianceAuditAdmin(admin.ModelAdmin):
    list_display = ["action", "shop", "eudr_product", "dds", "actor", "created_at"]
    list_filter = ["action"]
    readonly_fields = ["shop", "eudr_product", "dds", "action", "details", "actor", "created_at"]
