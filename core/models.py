"""EUDR Compliance Suite — data models.

EUDR = EU Deforestation Regulation (effective Dec 30, 2026 for large/medium,
June 30, 2027 for SMEs). Requires merchants to prove products containing
cattle, cocoa, coffee, palm oil, rubber, soya, or wood are not sourced from
land deforested after Dec 31, 2020.

Per-consignment Due Diligence Statements (DDS) must be submitted to the EU
Information System with geolocation of production plots.
"""

from django.db import models


COMMODITY_CHOICES = [
    ("cattle", "Cattle"),
    ("cocoa", "Cocoa"),
    ("coffee", "Coffee"),
    ("palm_oil", "Palm oil"),
    ("rubber", "Rubber"),
    ("soya", "Soya"),
    ("wood", "Wood"),
]

COUNTRY_RISK_CHOICES = [
    ("low", "Low risk"),
    ("standard", "Standard risk"),
    ("high", "High risk"),
]

DDS_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("submitted", "Submitted to EU"),
    ("verified", "Verified"),
    ("rejected", "Rejected"),
    ("withdrawn", "Withdrawn"),
]

PLOT_TYPE_CHOICES = [
    ("point", "Point (<=4 hectares)"),
    ("polygon", "Polygon (>4 hectares)"),
]


class Shop(models.Model):
    """Installed Shopify store — top-level tenant."""

    shopify_domain = models.CharField(max_length=255, unique=True)
    access_token = models.CharField(max_length=512)
    plan = models.CharField(max_length=20, default="starter")
    installed_at = models.DateTimeField(auto_now_add=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    store_name = models.CharField(max_length=255, blank=True)
    store_email = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=10, default="EUR")
    country_code = models.CharField(max_length=2, blank=True)

    shopify_charge_id = models.CharField(max_length=100, blank=True)
    billing_status = models.CharField(
        max_length=20,
        choices=[
            ("trial", "Trial"),
            ("active", "Active"),
            ("frozen", "Frozen"),
            ("cancelled", "Cancelled"),
        ],
        default="trial",
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # Operator details (the merchant as EUDR operator)
    operator_name = models.CharField(max_length=255, blank=True)
    operator_address = models.TextField(blank=True)
    operator_country = models.CharField(max_length=2, blank=True)
    operator_eori = models.CharField(max_length=20, blank=True, help_text="EU EORI number")
    operator_email = models.EmailField(blank=True)

    last_product_sync = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.shopify_domain

    class Meta:
        ordering = ["-installed_at"]


class GeolocationPlot(models.Model):
    """Production plot — point (<=4 ha) or polygon (>4 ha)."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="plots")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    country = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2")
    region = models.CharField(max_length=255, blank=True)

    plot_type = models.CharField(max_length=10, choices=PLOT_TYPE_CHOICES)
    area_hectares = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    coordinates = models.JSONField()

    country_risk = models.CharField(
        max_length=10, choices=COUNTRY_RISK_CHOICES, default="standard",
    )
    production_date = models.DateField(null=True, blank=True)

    supplier_name = models.CharField(max_length=255, blank=True)
    supplier_country = models.CharField(max_length=2, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.country})"


class EUDRProduct(models.Model):
    """Shopify product enriched with EUDR commodity classification."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="eudr_products")
    shopify_product_id = models.CharField(max_length=50)
    title = models.CharField(max_length=500)
    vendor = models.CharField(max_length=255, blank=True)
    product_type = models.CharField(max_length=255, blank=True)
    image_url = models.URLField(max_length=1000, blank=True)

    is_in_scope = models.BooleanField(
        default=False, help_text="True if product contains EUDR-covered commodities",
    )
    commodity = models.CharField(
        max_length=20, choices=COMMODITY_CHOICES, blank=True,
    )
    hs_code = models.CharField(max_length=20, blank=True, help_text="Harmonized System code")

    has_geolocation = models.BooleanField(default=False)
    has_dds = models.BooleanField(default=False)
    is_compliant = models.BooleanField(default=False)

    plots = models.ManyToManyField(
        GeolocationPlot, blank=True, related_name="products",
    )

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("shop", "shopify_product_id")
        indexes = [
            models.Index(fields=["shop", "is_in_scope"]),
            models.Index(fields=["shop", "is_compliant"]),
        ]

    def __str__(self):
        return self.title

    def recalculate_compliance(self):
        """Recompute compliance flags based on related data."""
        self.has_geolocation = self.plots.exists()
        self.has_dds = self.due_diligence_statements.filter(
            status__in=["submitted", "verified"],
        ).exists()
        self.is_compliant = (
            self.is_in_scope
            and bool(self.commodity)
            and bool(self.hs_code)
            and self.has_geolocation
            and self.has_dds
        )
        self.save(update_fields=["has_geolocation", "has_dds", "is_compliant"])


class DueDiligenceStatement(models.Model):
    """Per-consignment Due Diligence Statement (DDS) required by EUDR Article 4."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="dds")
    eudr_product = models.ForeignKey(
        EUDRProduct, on_delete=models.CASCADE, related_name="due_diligence_statements",
    )

    consignment_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_unit = models.CharField(
        max_length=20,
        choices=[("kg", "kg"), ("m3", "m3"), ("units", "units"), ("liters", "litres")],
        default="kg",
    )
    country_of_production = models.CharField(max_length=2)
    plots = models.ManyToManyField(GeolocationPlot, related_name="dds_entries")

    risk_level = models.CharField(
        max_length=10, choices=COUNTRY_RISK_CHOICES, default="standard",
    )
    risk_notes = models.TextField(blank=True)
    mitigation_measures = models.TextField(blank=True)

    eu_reference_number = models.CharField(
        max_length=100, blank=True, help_text="Assigned by EU Info System after submission",
    )
    eu_verification_number = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=DDS_STATUS_CHOICES, default="draft")

    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop", "status"]),
        ]

    def __str__(self):
        ref = self.eu_reference_number or f"draft {self.pk}"
        return f"DDS {ref} - {self.eudr_product.title}"


class ComplianceAudit(models.Model):
    """Audit log of compliance state changes — for legal trail."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="audit_log")
    eudr_product = models.ForeignKey(
        EUDRProduct, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_log",
    )
    dds = models.ForeignKey(
        DueDiligenceStatement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_log",
    )
    action = models.CharField(max_length=50)
    details = models.JSONField(default=dict, blank=True)
    actor = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class APIToken(models.Model):
    """API access token for Enterprise-tier merchants using the REST API."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=255, help_text="Human-readable label (e.g. 'ERP integration')")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    last_4 = models.CharField(max_length=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (...{self.last_4})"

    @classmethod
    def generate(cls, shop, name):
        """Create a new token, return (instance, raw_token_value)."""
        import secrets
        raw = "eudr_" + secrets.token_urlsafe(32)
        instance = cls.objects.create(
            shop=shop, name=name, token=raw, last_4=raw[-4:],
        )
        return instance, raw
