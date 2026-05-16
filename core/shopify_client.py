"""Shopify GraphQL Admin API client for EUDR Compliance Suite.

Used for:
- Syncing products from the merchant's store into EUDRProduct records
- Writing EUDR compliance metafields back to Shopify products (consumed by
  the storefront widget that displays compliance info on product pages)
"""

import json

import requests
from django.conf import settings
from django.utils import timezone

from .models import Shop, EUDRProduct


# Metafield namespace + keys exposed on the storefront. Theme app extension
# reads from these via `{{ product.metafields.eudr.* }}` Liquid syntax.
METAFIELD_NAMESPACE = "eudr"
METAFIELD_KEYS = {
    "is_in_scope": "in_scope",
    "commodity": "commodity",
    "hs_code": "hs_code",
    "country_of_production": "country_of_production",
    "dds_reference": "dds_reference",
    "dds_verification": "dds_verification",
    "operator_name": "operator_name",
    "operator_address": "operator_address",
    "operator_country": "operator_country",
    "compliance_statement": "compliance_statement",
    # Plan-driven flags read by the storefront widget
    "multi_language_enabled": "multi_language_enabled",
}


class ShopifyClient:
    """Thin wrapper around Shopify GraphQL Admin API."""

    def __init__(self, shop: Shop):
        self.shop = shop
        self.base_url = (
            f"https://{shop.shopify_domain}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
        )
        self.headers = {
            "X-Shopify-Access-Token": shop.access_token,
            "Content-Type": "application/json",
        }

    def query(self, gql: str, variables: dict = None) -> dict:
        payload = {"query": gql}
        if variables:
            payload["variables"] = variables
        resp = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
        # Do not auto-deactivate the shop on 401/403. A single transient error
        # was killing the install record. Real uninstalls go through the
        # app-uninstalled webhook.
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    # --- Product sync ---

    def sync_products(self):
        """Sync products from Shopify into EUDRProduct records.

        Respects plan SKU limits.
        """
        plan = settings.EUDR_PLANS.get(self.shop.plan, settings.EUDR_PLANS["starter"])
        sku_limit = plan.get("sku_limit")

        cursor = None
        has_next = True
        count = 0

        while has_next:
            gql = """
            query($cursor: String) {
                products(first: 50, after: $cursor) {
                    pageInfo { hasNextPage endCursor }
                    edges {
                        node {
                            id
                            title
                            vendor
                            productType
                            status
                            featuredMedia {
                                preview { image { url } }
                            }
                        }
                    }
                }
            }
            """
            data = self.query(gql, {"cursor": cursor})
            products_data = data.get("products", {})
            page_info = products_data.get("pageInfo", {})

            for edge in products_data.get("edges", []):
                if sku_limit and count >= sku_limit:
                    has_next = False
                    break

                node = edge["node"]
                product_id = node["id"].split("/")[-1]

                image_url = ""
                if node.get("featuredMedia"):
                    preview = node["featuredMedia"].get("preview", {})
                    if preview and preview.get("image"):
                        image_url = preview["image"].get("url", "")

                EUDRProduct.objects.update_or_create(
                    shop=self.shop,
                    shopify_product_id=product_id,
                    defaults={
                        "title": node["title"],
                        "vendor": node.get("vendor", "") or "",
                        "product_type": node.get("productType", "") or "",
                        "image_url": image_url,
                    },
                )
                count += 1

            if has_next:
                has_next = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")

        self.shop.last_product_sync = timezone.now()
        self.shop.save(update_fields=["last_product_sync"])

    # --- Metafield writes (consumed by storefront widget) ---

    def write_product_metafields(self, eudr_product: EUDRProduct):
        """Write all EUDR compliance metafields to a single Shopify product."""
        latest_dds = eudr_product.due_diligence_statements.filter(
            status__in=["submitted", "verified"],
        ).order_by("-created_at").first()

        shop = self.shop
        statement = self._build_compliance_statement(eudr_product, latest_dds)
        plan = settings.EUDR_PLANS.get(shop.plan, settings.EUDR_PLANS["starter"])
        multi_lang = "multi_language" in plan.get("features", [])

        values = {
            METAFIELD_KEYS["is_in_scope"]: "true" if eudr_product.is_in_scope else "false",
            METAFIELD_KEYS["commodity"]: eudr_product.commodity or "",
            METAFIELD_KEYS["hs_code"]: eudr_product.hs_code or "",
            METAFIELD_KEYS["country_of_production"]: (
                latest_dds.country_of_production if latest_dds else ""
            ),
            METAFIELD_KEYS["dds_reference"]: (
                latest_dds.eu_reference_number if latest_dds else ""
            ),
            METAFIELD_KEYS["dds_verification"]: (
                latest_dds.eu_verification_number if latest_dds else ""
            ),
            METAFIELD_KEYS["operator_name"]: shop.operator_name or shop.store_name,
            METAFIELD_KEYS["operator_address"]: shop.operator_address or "",
            METAFIELD_KEYS["operator_country"]: shop.operator_country or "",
            METAFIELD_KEYS["compliance_statement"]: statement,
            METAFIELD_KEYS["multi_language_enabled"]: "true" if multi_lang else "false",
        }

        gql = """
        mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
            metafieldsSet(metafields: $metafields) {
                metafields { id key namespace }
                userErrors { field message }
            }
        }
        """
        owner_gid = f"gid://shopify/Product/{eudr_product.shopify_product_id}"
        metafields = [
            {
                "ownerId": owner_gid,
                "namespace": METAFIELD_NAMESPACE,
                "key": key,
                "type": "single_line_text_field" if key != METAFIELD_KEYS["compliance_statement"] else "multi_line_text_field",
                "value": value or "",
            }
            for key, value in values.items()
        ]
        data = self.query(gql, {"metafields": metafields})
        errors = data.get("metafieldsSet", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Metafield write failed: {errors}")
        return data

    def _build_compliance_statement(self, eudr_product, dds):
        if not eudr_product.is_in_scope:
            return ""
        parts = ["This product complies with EU Regulation 2023/1115 (EUDR)."]
        if dds and dds.eu_reference_number:
            parts.append(f"Due Diligence Statement reference: {dds.eu_reference_number}.")
        if eudr_product.commodity:
            display = dict(eudr_product._meta.get_field("commodity").choices).get(
                eudr_product.commodity, eudr_product.commodity,
            )
            parts.append(f"Commodity classification: {display}.")
        if dds:
            parts.append(f"Country of production: {dds.country_of_production}.")
        return " ".join(parts)

    def define_metafield_schema(self):
        """Create metafield definitions so they appear in Shopify Admin under
        Settings > Custom data > Products. Safe to call repeatedly — Shopify
        returns ALREADY_EXISTS for definitions that already exist.
        """
        gql = """
        mutation metafieldDefinitionCreate($definition: MetafieldDefinitionInput!) {
            metafieldDefinitionCreate(definition: $definition) {
                createdDefinition { id }
                userErrors { field message code }
            }
        }
        """
        for label, key in [
            ("EUDR — In scope", METAFIELD_KEYS["is_in_scope"]),
            ("EUDR — Commodity", METAFIELD_KEYS["commodity"]),
            ("EUDR — HS code", METAFIELD_KEYS["hs_code"]),
            ("EUDR — Country of production", METAFIELD_KEYS["country_of_production"]),
            ("EUDR — DDS reference number", METAFIELD_KEYS["dds_reference"]),
            ("EUDR — DDS verification number", METAFIELD_KEYS["dds_verification"]),
            ("EUDR — Operator name", METAFIELD_KEYS["operator_name"]),
            ("EUDR — Operator address", METAFIELD_KEYS["operator_address"]),
            ("EUDR — Operator country", METAFIELD_KEYS["operator_country"]),
            ("EUDR — Compliance statement", METAFIELD_KEYS["compliance_statement"]),
        ]:
            mtype = (
                "multi_line_text_field"
                if key == METAFIELD_KEYS["compliance_statement"]
                else "single_line_text_field"
            )
            variables = {
                "definition": {
                    "name": label,
                    "namespace": METAFIELD_NAMESPACE,
                    "key": key,
                    "type": mtype,
                    "ownerType": "PRODUCT",
                    "pin": False,
                    "visibleToStorefrontApi": True,
                }
            }
            try:
                self.query(gql, variables)
            except Exception:
                # Already exists or other non-fatal error — continue
                pass
