"""EUDR Compliance Suite — REST API (Enterprise tier).

Bearer-token authenticated JSON API for merchants who want to integrate EUDR
compliance into their own ERP / PIM systems.

Auth: every request must include `Authorization: Bearer <api_token>`.
Tokens are created from the API tokens admin page.

Plan gate: only Enterprise plans can call the API. Other plans get 403.
"""

import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (
    APIToken,
    DueDiligenceStatement,
    EUDRProduct,
    GeolocationPlot,
    ComplianceAudit,
)


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def api_auth(view_func):
    """Decorator: extract Bearer token, attach shop to request, enforce Enterprise plan."""
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _err("missing or malformed Authorization header", 401)
        token_value = auth_header[7:].strip()
        if not token_value:
            return _err("empty bearer token", 401)
        try:
            token = APIToken.objects.select_related("shop").get(
                token=token_value, is_active=True,
            )
        except APIToken.DoesNotExist:
            return _err("invalid token", 401)

        shop = token.shop
        plan = settings.EUDR_PLANS.get(shop.plan, {})
        if "api_access" not in plan.get("features", []):
            return _err(
                "API access requires an Enterprise plan. Upgrade at /billing/select",
                status=403,
            )

        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])

        request.shop = shop
        request.api_token = token
        return view_func(request, *args, **kwargs)
    return wrapper


def _product_dict(p: EUDRProduct):
    return {
        "id": p.id,
        "shopify_product_id": p.shopify_product_id,
        "title": p.title,
        "vendor": p.vendor,
        "product_type": p.product_type,
        "is_in_scope": p.is_in_scope,
        "commodity": p.commodity,
        "hs_code": p.hs_code,
        "is_compliant": p.is_compliant,
        "has_geolocation": p.has_geolocation,
        "has_dds": p.has_dds,
        "plot_ids": list(p.plots.values_list("id", flat=True)),
    }


def _plot_dict(p: GeolocationPlot):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "country": p.country,
        "region": p.region,
        "plot_type": p.plot_type,
        "area_hectares": float(p.area_hectares) if p.area_hectares else None,
        "coordinates": p.coordinates,
        "country_risk": p.country_risk,
        "supplier_name": p.supplier_name,
        "supplier_country": p.supplier_country,
    }


def _dds_dict(d: DueDiligenceStatement):
    return {
        "id": d.id,
        "eudr_product_id": d.eudr_product_id,
        "status": d.status,
        "consignment_quantity": float(d.consignment_quantity),
        "quantity_unit": d.quantity_unit,
        "country_of_production": d.country_of_production,
        "risk_level": d.risk_level,
        "risk_notes": d.risk_notes,
        "mitigation_measures": d.mitigation_measures,
        "eu_reference_number": d.eu_reference_number,
        "eu_verification_number": d.eu_verification_number,
        "plot_ids": list(d.plots.values_list("id", flat=True)),
        "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None,
        "verified_at": d.verified_at.isoformat() if d.verified_at else None,
        "created_at": d.created_at.isoformat(),
    }


@require_GET
@api_auth
def list_products(request):
    qs = EUDRProduct.objects.filter(shop=request.shop)
    scope = request.GET.get("scope")
    if scope == "in":
        qs = qs.filter(is_in_scope=True)
    elif scope == "out":
        qs = qs.filter(is_in_scope=False)
    compliant = request.GET.get("compliant")
    if compliant == "true":
        qs = qs.filter(is_compliant=True)
    elif compliant == "false":
        qs = qs.filter(is_in_scope=True, is_compliant=False)
    try:
        limit = min(int(request.GET.get("limit", "100")), 500)
    except ValueError:
        limit = 100
    return JsonResponse({
        "count": qs.count(),
        "products": [_product_dict(p) for p in qs[:limit]],
    })


@require_http_methods(["GET", "PATCH"])
@api_auth
def product_detail(request, product_id):
    try:
        product = EUDRProduct.objects.get(id=product_id, shop=request.shop)
    except EUDRProduct.DoesNotExist:
        return _err("product not found", 404)

    if request.method == "GET":
        return JsonResponse(_product_dict(product))

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return _err("invalid JSON body")

    for field in ["is_in_scope", "commodity", "hs_code"]:
        if field in body:
            setattr(product, field, body[field])

    if "plot_ids" in body:
        plot_ids = body["plot_ids"] or []
        plots = GeolocationPlot.objects.filter(shop=request.shop, id__in=plot_ids)
        product.plots.set(plots)

    product.save()
    product.recalculate_compliance()
    ComplianceAudit.objects.create(
        shop=request.shop, eudr_product=product,
        action="api_product_update", actor=request.api_token.name,
        details=body,
    )
    return JsonResponse(_product_dict(product))


@require_http_methods(["GET", "POST"])
@api_auth
def plots_collection(request):
    if request.method == "GET":
        qs = GeolocationPlot.objects.filter(shop=request.shop)
        country = request.GET.get("country")
        if country:
            qs = qs.filter(country=country.upper())
        return JsonResponse({
            "count": qs.count(),
            "plots": [_plot_dict(p) for p in qs[:500]],
        })

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return _err("invalid JSON body")

    required = ["name", "country", "plot_type", "coordinates"]
    for r in required:
        if r not in body:
            return _err(f"missing required field: {r}")

    try:
        area = Decimal(str(body["area_hectares"])) if body.get("area_hectares") else None
    except InvalidOperation:
        return _err("area_hectares must be numeric")

    plot = GeolocationPlot.objects.create(
        shop=request.shop,
        name=body["name"],
        description=body.get("description", ""),
        country=body["country"].upper(),
        region=body.get("region", ""),
        plot_type=body["plot_type"],
        area_hectares=area,
        coordinates=body["coordinates"],
        country_risk=body.get("country_risk", "standard"),
        supplier_name=body.get("supplier_name", ""),
        supplier_country=(body.get("supplier_country") or "").upper(),
    )
    ComplianceAudit.objects.create(
        shop=request.shop, action="api_plot_create",
        actor=request.api_token.name, details={"plot_id": plot.id},
    )
    return JsonResponse(_plot_dict(plot), status=201)


@require_http_methods(["GET", "POST"])
@api_auth
def dds_collection(request):
    if request.method == "GET":
        qs = DueDiligenceStatement.objects.filter(shop=request.shop)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "count": qs.count(),
            "dds": [_dds_dict(d) for d in qs[:200]],
        })

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return _err("invalid JSON body")

    required = ["eudr_product_id", "consignment_quantity", "country_of_production"]
    for r in required:
        if r not in body:
            return _err(f"missing required field: {r}")

    try:
        product = EUDRProduct.objects.get(
            id=body["eudr_product_id"], shop=request.shop,
        )
    except EUDRProduct.DoesNotExist:
        return _err("eudr_product_id not found", 404)

    try:
        qty = Decimal(str(body["consignment_quantity"]))
    except InvalidOperation:
        return _err("consignment_quantity must be numeric")

    dds = DueDiligenceStatement.objects.create(
        shop=request.shop, eudr_product=product,
        consignment_quantity=qty,
        quantity_unit=body.get("quantity_unit", "kg"),
        country_of_production=body["country_of_production"].upper(),
        risk_level=body.get("risk_level", "standard"),
        risk_notes=body.get("risk_notes", ""),
        mitigation_measures=body.get("mitigation_measures", ""),
        eu_reference_number=body.get("eu_reference_number", ""),
        eu_verification_number=body.get("eu_verification_number", ""),
        status=body.get("status", "draft"),
    )
    if body.get("plot_ids"):
        plots = GeolocationPlot.objects.filter(
            shop=request.shop, id__in=body["plot_ids"],
        )
        dds.plots.set(plots)
    if dds.status in ("submitted", "verified"):
        dds.submitted_at = timezone.now()
        dds.save(update_fields=["submitted_at"])
    product.recalculate_compliance()
    ComplianceAudit.objects.create(
        shop=request.shop, eudr_product=product, dds=dds,
        action="api_dds_create", actor=request.api_token.name,
    )
    return JsonResponse(_dds_dict(dds), status=201)


@require_GET
@api_auth
def dds_detail(request, dds_id):
    try:
        dds = DueDiligenceStatement.objects.get(id=dds_id, shop=request.shop)
    except DueDiligenceStatement.DoesNotExist:
        return _err("DDS not found", 404)
    return JsonResponse(_dds_dict(dds))


@require_POST
@api_auth
def publish_widget(request):
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
    ComplianceAudit.objects.create(
        shop=request.shop, action="api_widget_publish",
        actor=request.api_token.name,
        details={"written": written, "failed": failed},
    )
    return JsonResponse({"written": written, "failed": failed})
