"""EUDR Compliance Suite — views.

Auth + billing scaffold inherited from StockPilot pattern. EUDR-specific
views handle: product classification, geolocation plot management, DDS
workflow, metafield publishing to storefront widget, compliance reporting.
"""

import json
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    COMMODITY_CHOICES,
    COUNTRY_RISK_CHOICES,
    PLOT_TYPE_CHOICES,
    ComplianceAudit,
    DueDiligenceStatement,
    EUDRProduct,
    GeolocationPlot,
    Shop,
)


# =============================================================
# AUTH HELPERS (inherited from StockPilot)
# =============================================================

def _get_shop(request):
    shop_domain = getattr(request, "shopify_shop_domain", None)
    if shop_domain:
        cache_key = f"shop:{shop_domain}"
        shop_obj = cache.get(cache_key)
        if not shop_obj:
            try:
                shop_obj = Shop.objects.get(shopify_domain=shop_domain)
                cache.set(cache_key, shop_obj, 300)
            except Shop.DoesNotExist:
                shop_obj = None
        if shop_obj:
            request.session["shop_id"] = shop_obj.id
            return shop_obj

    shop_id = request.session.get("shop_id")
    if shop_id:
        cache_key = f"shop_id:{shop_id}"
        shop_obj = cache.get(cache_key)
        if not shop_obj:
            try:
                shop_obj = Shop.objects.get(id=shop_id)
                cache.set(cache_key, shop_obj, 300)
            except Shop.DoesNotExist:
                shop_obj = None
        if shop_obj:
            return shop_obj

    shop_domain = request.GET.get("shop", "").strip()
    if shop_domain:
        cache_key = f"shop:{shop_domain}"
        shop_obj = cache.get(cache_key)
        if not shop_obj:
            try:
                shop_obj = Shop.objects.get(shopify_domain=shop_domain)
                cache.set(cache_key, shop_obj, 300)
            except Shop.DoesNotExist:
                shop_obj = None
        if shop_obj:
            request.session["shop_id"] = shop_obj.id
            return shop_obj

    return None


def _is_valid_shop(s):
    return bool(s) and s.endswith(".myshopify.com") and "/" not in s and " " not in s


def _resolve_shop_domain(request):
    """Try every signal Shopify sends to identify the shop domain.

    Order: explicit ?shop= param, JWT iss claim (via middleware), then
    base64-decoded ?host= param (admin.shopify.com/store/{handle}).
    """
    import base64 as _b64
    s = (request.GET.get("shop", "") or "").strip()
    if s:
        return s
    s = getattr(request, "shopify_shop_domain", None)
    if s:
        return s
    host = (request.GET.get("host", "") or "").strip()
    if host:
        try:
            padded = host + "=" * (4 - len(host) % 4)
            decoded = _b64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
            # decoded format: admin.shopify.com/store/{handle}
            if "/store/" in decoded:
                handle = decoded.rsplit("/store/", 1)[-1].split("/", 1)[0]
                if handle:
                    return f"{handle}.myshopify.com"
        except Exception:
            pass
    return ""


def _require_shop(view_func):
    def wrapper(request, *args, **kwargs):
        # Bounce page pattern — embedded auth requirement
        has_auth_header = request.headers.get("Authorization", "").startswith("Bearer ")
        has_id_token = bool(request.GET.get("id_token", ""))
        is_document_request = (
            request.method == "GET"
            and not has_auth_header
            and not has_id_token
            and not request.session.get("shop_id")
            and request.GET.get("shop", "")
            and not request.path.startswith("/auth/")
            and not request.path.startswith("/webhooks/")
            and not request.path.startswith("/session-token-bounce")
        )

        if is_document_request:
            from urllib.parse import urlencode
            params = dict(request.GET.items())
            shopify_reload = f"{request.path}?{urlencode(params)}" if params else request.path
            params["shopify-reload"] = shopify_reload
            return redirect(f"/session-token-bounce?{urlencode(params)}")

        shop = _get_shop(request)
        if not shop:
            shop_domain = request.GET.get("shop", "").strip()
            if _is_valid_shop(shop_domain):
                return render(request, "exit_iframe.html", {
                    "redirect_url": f"/auth/install?shop={shop_domain}",
                })
            return render(request, "core/install_prompt.html")
        request.shop = shop
        return view_func(request, *args, **kwargs)
    return wrapper


def session_token_bounce(request):
    """Bounce page initializing App Bridge to get a session token."""
    api_key = settings.SHOPIFY_API_KEY
    return HttpResponse(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="shopify-api-key" content="{api_key}" />
    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
    <title>Loading...</title>
</head>
<body>
<script>
(async function() {{
    if (!window.shopify) {{
        const params = new URLSearchParams(window.location.search);
        const reload = params.get('shopify-reload');
        if (reload) window.location.replace(reload);
        return;
    }}
    try {{
        const token = await shopify.idToken();
        const params = new URLSearchParams(window.location.search);
        const reload = params.get('shopify-reload') || '/';
        params.delete('shopify-reload');
        params.set('id_token', token);
        const base = reload.split('?')[0];
        window.location.replace(base + '?' + params.toString());
    }} catch (e) {{
        console.error('Bounce failed:', e);
    }}
}})();
</script>
</body>
</html>""", content_type="text/html")


# =============================================================
# LEGAL
# =============================================================

def privacy_policy(request):
    return HttpResponse("""
    <html><head><title>EUDR Compliance Suite Privacy Policy</title>
    <style>body{font-family:-apple-system,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333;}h1{font-size:24px;}h2{font-size:18px;margin-top:24px;}</style>
    </head><body>
    <h1>EUDR Compliance Suite — Privacy Policy</h1>
    <p>Last updated: May 16, 2026</p>

    <h2>What data we collect</h2>
    <p>EUDR Compliance Suite accesses your Shopify store data to help you comply with EU Regulation 2023/1115 (EU Deforestation Regulation). We read product information (titles, vendors, product types, HS codes) and write EUDR compliance metafields back to your products so they display correctly on your storefront.</p>

    <p>We also store the EUDR-specific data you enter inside the app: production plot geolocations, Due Diligence Statements, risk assessments, supplier and operator details.</p>

    <h2>How we use your data</h2>
    <p>Your data is used solely to: (1) help you classify products as in/out of EUDR scope, (2) generate and store Due Diligence Statements, (3) write compliance information to your storefront via Shopify metafields, (4) maintain an audit log of your compliance actions for legal traceability.</p>

    <h2>Data storage</h2>
    <p>Your data is stored in a PostgreSQL database hosted by Neon (neon.tech) with encryption in transit. Access tokens are stored encrypted and used only to communicate with Shopify on your behalf.</p>

    <h2>Customer data</h2>
    <p>EUDR Compliance Suite does NOT access, collect, or store any customer personal information. We only access product and shop-level data.</p>

    <h2>Data deletion</h2>
    <p>When you uninstall the app, we receive a notification from Shopify and mark your account as inactive. Within 48 hours, your data is permanently deleted from our systems.</p>

    <h2>Third-party services</h2>
    <p>This app uses: Shopify API (to sync product data and write metafields), Neon PostgreSQL (database hosting), and Render (application hosting). No other third parties have access to your data.</p>

    <h2>Contact</h2>
    <p>For privacy questions, contact: esengad004@gmail.com</p>
    </body></html>
    """)


# =============================================================
# PLAN HELPERS
# =============================================================

def _get_plan_limits(shop):
    return settings.EUDR_PLANS.get(shop.plan, settings.EUDR_PLANS["starter"])


def _check_limit(shop, limit_key, current_count):
    plan = _get_plan_limits(shop)
    limit = plan.get(limit_key)
    if limit is None:
        return True
    return current_count < limit


def _has_feature(shop, feature):
    plan = _get_plan_limits(shop)
    return feature in plan.get("features", [])


def _audit(shop, action, **details):
    """Helper to write to ComplianceAudit log."""
    ComplianceAudit.objects.create(
        shop=shop,
        action=action,
        details=details or {},
        actor=details.get("actor", ""),
        eudr_product=details.get("eudr_product") if isinstance(details.get("eudr_product"), EUDRProduct) else None,
        dds=details.get("dds") if isinstance(details.get("dds"), DueDiligenceStatement) else None,
    )


# =============================================================
# DASHBOARD
# =============================================================

def dashboard(request):
    """Dashboard — 200 response with App Bridge tags for Shopify's checker."""
    shop = _get_shop(request)
    if not shop:
        # No Shop record found. Try every signal Shopify might send (?shop=,
        # JWT iss, base64 host) to identify which store wants to install.
        # If we can name a valid shop, kick off OAuth — even if Shopify thinks
        # the app is "installed" on their side, our callback creates the DB row.
        shop_domain = _resolve_shop_domain(request)
        if _is_valid_shop(shop_domain):
            return render(request, "exit_iframe.html", {
                "redirect_url": f"/auth/install?shop={shop_domain}",
            })
        return render(request, "core/install_prompt.html")

    cache_key = f"dashboard:{shop.id}"
    ctx = cache.get(cache_key)
    if not ctx:
        in_scope = EUDRProduct.objects.filter(shop=shop, is_in_scope=True).count()
        compliant = EUDRProduct.objects.filter(shop=shop, is_compliant=True).count()
        total = EUDRProduct.objects.filter(shop=shop).count()
        ctx = {
            "total_products": total,
            "in_scope": in_scope,
            "compliant": compliant,
            "non_compliant": in_scope - compliant,
            "compliance_pct": int((compliant / in_scope) * 100) if in_scope else 0,
            "total_plots": GeolocationPlot.objects.filter(shop=shop).count(),
            "dds_drafts": DueDiligenceStatement.objects.filter(shop=shop, status="draft").count(),
            "dds_submitted": DueDiligenceStatement.objects.filter(
                shop=shop, status__in=["submitted", "verified"],
            ).count(),
            "operator_configured": bool(
                shop.operator_name and shop.operator_country and shop.operator_address
            ),
        }
        cache.set(cache_key, ctx, 60)
    ctx["shop"] = shop
    ctx["active_tab"] = "dashboard"
    return render(request, "core/dashboard.html", ctx)


def sync_from_shopify(request):
    """Sync products from Shopify."""
    import requests as _requests
    shop = _get_shop(request)
    if not shop:
        shop_domain = request.GET.get("shop", "").strip()
        if _is_valid_shop(shop_domain):
            return render(request, "exit_iframe.html", {
                "redirect_url": f"/auth/install?shop={shop_domain}",
            })
        return render(request, "core/install_prompt.html")

    try:
        from .shopify_client import ShopifyClient
        client = ShopifyClient(shop)
        client.sync_products()
        client.define_metafield_schema()
    except _requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            return render(request, "exit_iframe.html", {
                "redirect_url": f"/auth/install?shop={shop.shopify_domain}",
            })
        raise
    cache.delete(f"dashboard:{shop.id}")
    return redirect(f"/?shop={shop.shopify_domain}")


# =============================================================
# OPERATOR SETTINGS
# =============================================================

@_require_shop
def operator_settings(request):
    """Merchant configures themselves as EUDR operator (required for DDS)."""
    if request.method == "POST":
        request.shop.operator_name = request.POST.get("operator_name", "").strip()
        request.shop.operator_address = request.POST.get("operator_address", "").strip()
        request.shop.operator_country = request.POST.get("operator_country", "").strip().upper()
        request.shop.operator_eori = request.POST.get("operator_eori", "").strip()
        request.shop.operator_email = request.POST.get("operator_email", "").strip()
        request.shop.save()
        _audit(request.shop, "operator_settings_updated")
        cache.delete(f"dashboard:{request.shop.id}")
        return redirect("operator_settings")

    return render(request, "core/operator_settings.html", {
        "shop": request.shop,
        "active_tab": "settings",
    })


# =============================================================
# PRODUCTS — EUDR CLASSIFICATION
# =============================================================

@_require_shop
def product_list(request):
    search = request.GET.get("q", "").strip()
    scope_filter = request.GET.get("scope", "")
    compliance_filter = request.GET.get("compliance", "")

    products = EUDRProduct.objects.filter(shop=request.shop)
    if search:
        products = products.filter(title__icontains=search)
    if scope_filter == "in":
        products = products.filter(is_in_scope=True)
    elif scope_filter == "out":
        products = products.filter(is_in_scope=False)
    if compliance_filter == "compliant":
        products = products.filter(is_compliant=True)
    elif compliance_filter == "non_compliant":
        products = products.filter(is_in_scope=True, is_compliant=False)

    return render(request, "core/product_list.html", {
        "shop": request.shop,
        "products": products[:500],
        "search": search,
        "scope_filter": scope_filter,
        "compliance_filter": compliance_filter,
        "commodity_choices": COMMODITY_CHOICES,
        "active_tab": "products",
    })


@_require_shop
def product_detail(request, product_id):
    product = get_object_or_404(EUDRProduct, id=product_id, shop=request.shop)
    plots = product.plots.all()
    dds = product.due_diligence_statements.all()

    return render(request, "core/product_detail.html", {
        "shop": request.shop,
        "product": product,
        "plots": plots,
        "dds": dds,
        "commodity_choices": COMMODITY_CHOICES,
        "active_tab": "products",
    })


@_require_shop
@require_POST
def product_classify(request, product_id):
    """Set in-scope flag, commodity, HS code on a product."""
    product = get_object_or_404(EUDRProduct, id=product_id, shop=request.shop)
    product.is_in_scope = request.POST.get("is_in_scope", "") == "on"
    product.commodity = request.POST.get("commodity", "").strip()
    product.hs_code = request.POST.get("hs_code", "").strip()

    plot_ids = request.POST.getlist("plots")
    if plot_ids:
        product.plots.set(
            GeolocationPlot.objects.filter(shop=request.shop, id__in=plot_ids)
        )

    product.save()
    product.recalculate_compliance()
    _audit(request.shop, "product_classified", eudr_product=product,
           commodity=product.commodity, hs_code=product.hs_code)
    cache.delete(f"dashboard:{request.shop.id}")
    return redirect("product_detail", product_id=product.id)


@_require_shop
def bulk_classify(request):
    """Bulk in-scope classification by product type or vendor."""
    if request.method == "POST":
        product_type = request.POST.get("product_type", "").strip()
        vendor = request.POST.get("vendor", "").strip()
        commodity = request.POST.get("commodity", "").strip()
        hs_code = request.POST.get("hs_code", "").strip()

        qs = EUDRProduct.objects.filter(shop=request.shop)
        if product_type:
            qs = qs.filter(product_type__iexact=product_type)
        if vendor:
            qs = qs.filter(vendor__iexact=vendor)

        updated = qs.update(
            is_in_scope=True,
            commodity=commodity,
            hs_code=hs_code,
        )
        for p in qs:
            p.recalculate_compliance()
        _audit(request.shop, "bulk_classified", count=updated,
               product_type=product_type, vendor=vendor, commodity=commodity)
        cache.delete(f"dashboard:{request.shop.id}")
        return redirect("product_list")

    product_types = (
        EUDRProduct.objects.filter(shop=request.shop)
        .exclude(product_type="")
        .values_list("product_type", flat=True)
        .distinct()
        .order_by("product_type")
    )
    vendors = (
        EUDRProduct.objects.filter(shop=request.shop)
        .exclude(vendor="")
        .values_list("vendor", flat=True)
        .distinct()
        .order_by("vendor")
    )
    return render(request, "core/bulk_classify.html", {
        "shop": request.shop,
        "product_types": product_types,
        "vendors": vendors,
        "commodity_choices": COMMODITY_CHOICES,
        "active_tab": "products",
    })


# =============================================================
# GEOLOCATION PLOTS
# =============================================================

@_require_shop
def plot_list(request):
    plots = GeolocationPlot.objects.filter(shop=request.shop)
    return render(request, "core/plot_list.html", {
        "shop": request.shop,
        "plots": plots,
        "active_tab": "plots",
    })


@_require_shop
def plot_create(request):
    current_count = GeolocationPlot.objects.filter(shop=request.shop).count()
    if not _check_limit(request.shop, "plot_limit", current_count):
        plan = _get_plan_limits(request.shop)
        return render(request, "core/plan_limit.html", {
            "shop": request.shop,
            "limit_type": "geolocation plots",
            "current": current_count,
            "limit": plan["plot_limit"],
            "plan_name": plan["name"],
        })

    if request.method == "POST":
        plot = _save_plot_from_post(GeolocationPlot(shop=request.shop), request.POST)
        if plot.plot_type == "polygon" and not _has_feature(request.shop, "geolocation_polygons"):
            plot.delete()
            return render(request, "core/plan_limit.html", {
                "shop": request.shop,
                "limit_type": "polygon plots (Pro feature)",
                "current": 0, "limit": 0,
                "plan_name": _get_plan_limits(request.shop)["name"],
            })
        _audit(request.shop, "plot_created", plot_id=plot.id, country=plot.country)
        return redirect("plot_detail", plot_id=plot.id)

    return render(request, "core/plot_form.html", {
        "shop": request.shop,
        "plot_type_choices": PLOT_TYPE_CHOICES,
        "country_risk_choices": COUNTRY_RISK_CHOICES,
        "active_tab": "plots",
        "editing": False,
    })


@_require_shop
def plot_detail(request, plot_id):
    plot = get_object_or_404(GeolocationPlot, id=plot_id, shop=request.shop)
    return render(request, "core/plot_detail.html", {
        "shop": request.shop,
        "plot": plot,
        "products": plot.products.all(),
        "dds_entries": plot.dds_entries.all(),
        "active_tab": "plots",
    })


@_require_shop
def plot_edit(request, plot_id):
    plot = get_object_or_404(GeolocationPlot, id=plot_id, shop=request.shop)
    if request.method == "POST":
        _save_plot_from_post(plot, request.POST)
        _audit(request.shop, "plot_updated", plot_id=plot.id)
        return redirect("plot_detail", plot_id=plot.id)

    return render(request, "core/plot_form.html", {
        "shop": request.shop,
        "plot": plot,
        "plot_type_choices": PLOT_TYPE_CHOICES,
        "country_risk_choices": COUNTRY_RISK_CHOICES,
        "active_tab": "plots",
        "editing": True,
    })


@_require_shop
@require_POST
def plot_delete(request, plot_id):
    plot = get_object_or_404(GeolocationPlot, id=plot_id, shop=request.shop)
    if not plot.dds_entries.exists():
        plot.delete()
        _audit(request.shop, "plot_deleted", plot_id=plot_id)
    return redirect("plot_list")


def _save_plot_from_post(plot, post):
    plot.name = post.get("name", "").strip()
    plot.description = post.get("description", "").strip()
    plot.country = post.get("country", "").strip().upper()
    plot.region = post.get("region", "").strip()
    plot.plot_type = post.get("plot_type", "point")
    area = post.get("area_hectares", "").strip()
    plot.area_hectares = Decimal(area) if area else None
    plot.country_risk = post.get("country_risk", "standard")
    plot.supplier_name = post.get("supplier_name", "").strip()
    plot.supplier_country = post.get("supplier_country", "").strip().upper()

    coords_raw = post.get("coordinates", "").strip()
    try:
        plot.coordinates = json.loads(coords_raw) if coords_raw else {}
    except json.JSONDecodeError:
        # Fallback: parse "lat,lng" for point plots
        if plot.plot_type == "point" and "," in coords_raw:
            lat, lng = coords_raw.split(",", 1)
            plot.coordinates = {"lat": float(lat.strip()), "lng": float(lng.strip())}
        else:
            plot.coordinates = {}

    plot.save()
    return plot


# =============================================================
# DUE DILIGENCE STATEMENTS (DDS)
# =============================================================

@_require_shop
def dds_list(request):
    dds = DueDiligenceStatement.objects.filter(shop=request.shop).select_related("eudr_product")
    status_filter = request.GET.get("status", "")
    if status_filter:
        dds = dds.filter(status=status_filter)

    return render(request, "core/dds_list.html", {
        "shop": request.shop,
        "dds": dds,
        "status_filter": status_filter,
        "active_tab": "dds",
    })


@_require_shop
def dds_create(request):
    from datetime import datetime
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_count = DueDiligenceStatement.objects.filter(
        shop=request.shop, created_at__gte=month_start,
    ).count()
    if not _check_limit(request.shop, "dds_limit_monthly", monthly_count):
        plan = _get_plan_limits(request.shop)
        return render(request, "core/plan_limit.html", {
            "shop": request.shop,
            "limit_type": "DDS this month",
            "current": monthly_count,
            "limit": plan["dds_limit_monthly"],
            "plan_name": plan["name"],
        })

    if request.method == "POST":
        product = get_object_or_404(
            EUDRProduct, id=request.POST.get("eudr_product"), shop=request.shop,
        )
        dds = DueDiligenceStatement.objects.create(
            shop=request.shop,
            eudr_product=product,
            consignment_quantity=Decimal(request.POST.get("consignment_quantity", "0") or "0"),
            quantity_unit=request.POST.get("quantity_unit", "kg"),
            country_of_production=request.POST.get("country_of_production", "").strip().upper(),
            risk_level=request.POST.get("risk_level", "standard"),
            risk_notes=request.POST.get("risk_notes", "").strip(),
            mitigation_measures=request.POST.get("mitigation_measures", "").strip(),
        )
        plot_ids = request.POST.getlist("plots")
        if plot_ids:
            dds.plots.set(
                GeolocationPlot.objects.filter(shop=request.shop, id__in=plot_ids)
            )
        _audit(request.shop, "dds_created", dds=dds, eudr_product=product)
        return redirect("dds_detail", dds_id=dds.id)

    products = EUDRProduct.objects.filter(shop=request.shop, is_in_scope=True)
    plots = GeolocationPlot.objects.filter(shop=request.shop)
    return render(request, "core/dds_form.html", {
        "shop": request.shop,
        "products": products,
        "plots": plots,
        "country_risk_choices": COUNTRY_RISK_CHOICES,
        "active_tab": "dds",
    })


@_require_shop
def dds_detail(request, dds_id):
    dds = get_object_or_404(DueDiligenceStatement, id=dds_id, shop=request.shop)
    return render(request, "core/dds_detail.html", {
        "shop": request.shop,
        "dds": dds,
        "active_tab": "dds",
    })


@_require_shop
@require_POST
def dds_submit(request, dds_id):
    """Mark DDS as submitted to EU Info System. v1 = manual entry of reference."""
    dds = get_object_or_404(DueDiligenceStatement, id=dds_id, shop=request.shop)
    dds.eu_reference_number = request.POST.get("eu_reference_number", "").strip()
    dds.eu_verification_number = request.POST.get("eu_verification_number", "").strip()
    dds.status = "submitted"
    dds.submitted_at = timezone.now()
    dds.save()
    dds.eudr_product.recalculate_compliance()
    _audit(request.shop, "dds_submitted", dds=dds, ref=dds.eu_reference_number)
    cache.delete(f"dashboard:{request.shop.id}")
    return redirect("dds_detail", dds_id=dds.id)


@_require_shop
@require_POST
def dds_withdraw(request, dds_id):
    dds = get_object_or_404(DueDiligenceStatement, id=dds_id, shop=request.shop)
    dds.status = "withdrawn"
    dds.save()
    dds.eudr_product.recalculate_compliance()
    _audit(request.shop, "dds_withdrawn", dds=dds)
    cache.delete(f"dashboard:{request.shop.id}")
    return redirect("dds_detail", dds_id=dds.id)


@_require_shop
def dds_pdf(request, dds_id):
    """Generate DDS as PDF for record-keeping or supplier submission."""
    if not _has_feature(request.shop, "pdf_export"):
        plan = _get_plan_limits(request.shop)
        return render(request, "core/plan_limit.html", {
            "shop": request.shop,
            "limit_type": "PDF export (Pro feature)",
            "current": 0, "limit": 0,
            "plan_name": plan["name"],
        })
    dds = get_object_or_404(DueDiligenceStatement, id=dds_id, shop=request.shop)
    html = render(request, "core/dds_pdf.html", {
        "dds": dds,
        "shop": request.shop,
    }).content.decode()
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        ref = dds.eu_reference_number or f"draft-{dds.id}"
        response["Content-Disposition"] = f'attachment; filename="DDS-{ref}.pdf"'
        return response
    except Exception as e:
        return HttpResponse(f"PDF generation error: {e}", status=500)


# =============================================================
# STOREFRONT WIDGET PUBLISHING
# =============================================================

@_require_shop
@require_POST
def publish_widget_metafields(request):
    """Write EUDR metafields to all compliant products so the storefront
    theme app extension can render the compliance widget on product pages."""
    from .shopify_client import ShopifyClient
    client = ShopifyClient(request.shop)
    client.define_metafield_schema()

    products = EUDRProduct.objects.filter(shop=request.shop, is_in_scope=True)
    written, failed = 0, 0
    for product in products:
        try:
            client.write_product_metafields(product)
            written += 1
        except Exception:
            failed += 1
    _audit(request.shop, "widget_published", written=written, failed=failed)
    return JsonResponse({"written": written, "failed": failed})


# =============================================================
# COMPLIANCE REPORT + AUDIT LOG
# =============================================================

@_require_shop
def compliance_report(request):
    in_scope = EUDRProduct.objects.filter(shop=request.shop, is_in_scope=True)
    non_compliant = in_scope.filter(is_compliant=False)
    missing_classification = in_scope.filter(commodity="")
    missing_geolocation = in_scope.filter(has_geolocation=False)
    missing_dds = in_scope.filter(has_dds=False)

    return render(request, "core/compliance_report.html", {
        "shop": request.shop,
        "in_scope_count": in_scope.count(),
        "compliant_count": in_scope.filter(is_compliant=True).count(),
        "non_compliant": non_compliant[:50],
        "missing_classification": missing_classification[:50],
        "missing_geolocation": missing_geolocation[:50],
        "missing_dds": missing_dds[:50],
        "active_tab": "compliance",
    })


@_require_shop
def audit_log(request):
    log = ComplianceAudit.objects.filter(shop=request.shop).select_related(
        "eudr_product", "dds",
    )[:200]
    return render(request, "core/audit_log.html", {
        "shop": request.shop,
        "log": log,
        "active_tab": "compliance",
    })


# =============================================================
# BILLING
# =============================================================

@_require_shop
def billing_select(request):
    if request.method == "POST":
        plan_key = request.POST.get("plan", "starter")
        from .billing import create_subscription
        try:
            confirmation_url = create_subscription(request.shop, plan_key)
            if confirmation_url:
                return redirect(confirmation_url)
        except Exception:
            return render(request, "core/billing_select.html", {
                "shop": request.shop,
                "plans": settings.EUDR_PLANS,
                "current_plan": request.shop.plan,
                "error": "We couldn't start your subscription. Please try again or contact support.",
            })
        return redirect(f"/?shop={request.shop.shopify_domain}")

    return render(request, "core/billing_select.html", {
        "shop": request.shop,
        "plans": settings.EUDR_PLANS,
        "current_plan": request.shop.plan,
        "active_tab": "settings",
    })


@_require_shop
def billing_callback(request):
    charge_id = request.GET.get("charge_id", "")
    plan_key = request.GET.get("plan", "starter")

    if charge_id:
        request.shop.shopify_charge_id = charge_id
        request.shop.plan = plan_key
        request.shop.billing_status = "active"
        request.shop.save(update_fields=["shopify_charge_id", "plan", "billing_status"])
        _audit(request.shop, "plan_activated", plan=plan_key)

    return redirect("dashboard")


# =============================================================
# CSV IMPORT (products + plots)
# =============================================================

import csv as _csv
from io import StringIO as _StringIO

from .models import APIToken
from .country_risk import risk_for_country


@_require_shop
def csv_import_products(request):
    """Bulk-classify products from a CSV upload."""
    result = None
    if request.method == "POST" and request.FILES.get("csv_file"):
        result = {"updated": 0, "skipped": 0, "errors": []}
        try:
            content = request.FILES["csv_file"].read().decode("utf-8-sig")
            reader = _csv.DictReader(_StringIO(content))
            for i, row in enumerate(reader, start=2):
                spid = (row.get("shopify_product_id") or "").strip()
                if not spid:
                    result["skipped"] += 1
                    continue
                try:
                    product = EUDRProduct.objects.get(
                        shop=request.shop, shopify_product_id=spid,
                    )
                except EUDRProduct.DoesNotExist:
                    result["errors"].append(f"Row {i}: product {spid} not synced yet")
                    continue

                in_scope_raw = (row.get("is_in_scope") or "").strip().lower()
                product.is_in_scope = in_scope_raw in ("true", "1", "yes", "y")
                product.commodity = (row.get("commodity") or "").strip()
                product.hs_code = (row.get("hs_code") or "").strip()

                plot_ids_raw = (row.get("plot_ids") or "").strip()
                if plot_ids_raw:
                    ids = [p.strip() for p in plot_ids_raw.split("|") if p.strip().isdigit()]
                    product.plots.set(
                        GeolocationPlot.objects.filter(shop=request.shop, id__in=ids)
                    )

                product.save()
                product.recalculate_compliance()
                result["updated"] += 1
        except UnicodeDecodeError:
            result["errors"].append("File must be UTF-8 encoded CSV")
        except Exception as e:
            result["errors"].append(f"Parse error: {e}")

        _audit(request.shop, "csv_import_products",
               updated=result["updated"], errors=len(result["errors"]))
        cache.delete(f"dashboard:{request.shop.id}")

    return render(request, "core/csv_import_products.html", {
        "shop": request.shop,
        "result": result,
        "active_tab": "products",
    })


@_require_shop
def csv_import_plots(request):
    """Bulk-create geolocation plots from a CSV upload."""
    current_count = GeolocationPlot.objects.filter(shop=request.shop).count()
    plan_limit = _get_plan_limits(request.shop).get("plot_limit")

    result = None
    if request.method == "POST" and request.FILES.get("csv_file"):
        result = {"created": 0, "skipped": 0, "errors": []}
        try:
            content = request.FILES["csv_file"].read().decode("utf-8-sig")
            reader = _csv.DictReader(_StringIO(content))
            for i, row in enumerate(reader, start=2):
                if plan_limit and (current_count + result["created"]) >= plan_limit:
                    result["errors"].append(
                        f"Row {i}: plan plot limit ({plan_limit}) reached, stopping import"
                    )
                    break
                name = (row.get("name") or "").strip()
                country = (row.get("country") or "").strip().upper()
                plot_type = (row.get("plot_type") or "").strip().lower()
                coords_raw = (row.get("coordinates") or "").strip()
                if not (name and country and plot_type and coords_raw):
                    result["errors"].append(f"Row {i}: missing required field")
                    continue
                try:
                    coords = json.loads(coords_raw)
                except json.JSONDecodeError:
                    result["errors"].append(f"Row {i}: invalid coordinates JSON")
                    continue
                if plot_type == "polygon" and not _has_feature(request.shop, "geolocation_polygons"):
                    result["errors"].append(
                        f"Row {i}: polygon plots require Pro plan"
                    )
                    continue

                area_raw = (row.get("area_hectares") or "").strip()
                try:
                    area = Decimal(area_raw) if area_raw else None
                except Exception:
                    area = None

                country_risk = (row.get("country_risk") or "").strip().lower()
                if not country_risk:
                    country_risk = risk_for_country(country)

                GeolocationPlot.objects.create(
                    shop=request.shop,
                    name=name,
                    description=(row.get("description") or "").strip(),
                    country=country,
                    region=(row.get("region") or "").strip(),
                    plot_type=plot_type,
                    area_hectares=area,
                    coordinates=coords,
                    country_risk=country_risk,
                    supplier_name=(row.get("supplier_name") or "").strip(),
                    supplier_country=(row.get("supplier_country") or "").strip().upper(),
                )
                result["created"] += 1
        except UnicodeDecodeError:
            result["errors"].append("File must be UTF-8 encoded CSV")
        except Exception as e:
            result["errors"].append(f"Parse error: {e}")

        _audit(request.shop, "csv_import_plots",
               created=result["created"], errors=len(result["errors"]))

    return render(request, "core/csv_import_plots.html", {
        "shop": request.shop,
        "result": result,
        "active_tab": "plots",
    })


# =============================================================
# BULK DDS GENERATION (Pro+)
# =============================================================

@_require_shop
def dds_bulk(request):
    """Generate draft DDS for many in-scope products at once."""
    if not _has_feature(request.shop, "bulk_dds"):
        plan = _get_plan_limits(request.shop)
        return render(request, "core/plan_limit.html", {
            "shop": request.shop,
            "limit_type": "bulk DDS generation (Pro feature)",
            "current": 0, "limit": 0,
            "plan_name": plan["name"],
        })

    result = None
    if request.method == "POST":
        product_ids = request.POST.getlist("product_ids")
        if product_ids:
            products = EUDRProduct.objects.filter(
                shop=request.shop, id__in=product_ids, is_in_scope=True,
            )
            shared_plots = GeolocationPlot.objects.filter(
                shop=request.shop, id__in=request.POST.getlist("plot_ids"),
            )

            try:
                qty = Decimal(request.POST.get("consignment_quantity", "0") or "0")
            except Exception:
                qty = Decimal("0")

            created = 0
            for product in products:
                dds = DueDiligenceStatement.objects.create(
                    shop=request.shop,
                    eudr_product=product,
                    consignment_quantity=qty,
                    quantity_unit=request.POST.get("quantity_unit", "kg"),
                    country_of_production=request.POST.get("country_of_production", "").strip().upper(),
                    risk_level=request.POST.get("risk_level", "standard"),
                    risk_notes=request.POST.get("risk_notes", "").strip(),
                    mitigation_measures=request.POST.get("mitigation_measures", "").strip(),
                )
                if shared_plots.exists():
                    dds.plots.set(shared_plots)
                _audit(request.shop, "dds_bulk_created", dds=dds, eudr_product=product)
                created += 1
            result = {"created": created}

    products = EUDRProduct.objects.filter(shop=request.shop, is_in_scope=True)
    plots = GeolocationPlot.objects.filter(shop=request.shop)
    return render(request, "core/dds_bulk.html", {
        "shop": request.shop,
        "products": products,
        "plots": plots,
        "country_risk_choices": COUNTRY_RISK_CHOICES,
        "result": result,
        "active_tab": "dds",
    })


# =============================================================
# COUNTRY RISK AUTO-LOOKUP (JSON helper for plot form)
# =============================================================

@_require_shop
def country_risk_lookup(request):
    """JSON helper called from the plot form to pre-fill risk tier."""
    code = request.GET.get("country", "").strip().upper()
    return JsonResponse({"country": code, "risk": risk_for_country(code)})


# =============================================================
# API TOKEN MANAGEMENT (Enterprise)
# =============================================================

@_require_shop
def api_tokens(request):
    """Create / revoke REST API tokens. Enterprise only."""
    if not _has_feature(request.shop, "api_access"):
        plan = _get_plan_limits(request.shop)
        return render(request, "core/plan_limit.html", {
            "shop": request.shop,
            "limit_type": "REST API access (Enterprise feature)",
            "current": 0, "limit": 0,
            "plan_name": plan["name"],
        })

    new_token = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip() or "Unnamed token"
            _instance, new_token = APIToken.generate(request.shop, name)
            _audit(request.shop, "api_token_created", name=name)
        elif action == "revoke":
            tid = request.POST.get("token_id")
            if tid:
                APIToken.objects.filter(
                    shop=request.shop, id=tid,
                ).update(is_active=False)
                _audit(request.shop, "api_token_revoked", token_id=tid)

    tokens = APIToken.objects.filter(shop=request.shop, is_active=True)
    return render(request, "core/api_tokens.html", {
        "shop": request.shop,
        "tokens": tokens,
        "new_token": new_token,
        "base_url": settings.SHOPIFY_APP_URL,
        "active_tab": "api",
    })
