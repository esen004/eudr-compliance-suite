"""EUDR country risk classification reference.

The European Commission is required to classify producer countries (or
regions) as low / standard / high risk under EUDR Article 29. The official
list is being maintained by the Commission and will be updated periodically.

As a default until the EC publishes the full list:
- EU member states default to LOW (deforestation already controlled by
  separate forestry directives)
- Known high-deforestation jurisdictions default to HIGH
- Everything else defaults to STANDARD

Merchants can override per-plot. This is just a helper for the "auto-fill
risk when I enter a country code" UX on the plot form.
"""

# ISO 3166-1 alpha-2 country code → risk tier
COUNTRY_RISK = {
    # EU member states — low risk by default
    "AT": "low", "BE": "low", "BG": "low", "HR": "low", "CY": "low",
    "CZ": "low", "DK": "low", "EE": "low", "FI": "low", "FR": "low",
    "DE": "low", "GR": "low", "HU": "low", "IE": "low", "IT": "low",
    "LV": "low", "LT": "low", "LU": "low", "MT": "low", "NL": "low",
    "PL": "low", "PT": "low", "RO": "low", "SK": "low", "SI": "low",
    "ES": "low", "SE": "low",

    # EEA / candidates — low
    "NO": "low", "IS": "low", "CH": "low", "GB": "low",

    # Producer countries with strong forest governance — low
    "CR": "low", "PA": "low", "CL": "low", "NZ": "low", "AU": "low",
    "CA": "low", "US": "low",

    # Known high-deforestation hotspots (subject to EC final classification)
    "BR": "high",   # Brazilian Amazon
    "ID": "high",   # Indonesia palm oil/soy
    "MY": "high",   # Malaysia palm
    "PG": "high",   # Papua New Guinea
    "MM": "high",   # Myanmar wood
    "CI": "high",   # Cote d'Ivoire cocoa
    "GH": "high",   # Ghana cocoa
    "PY": "high",   # Paraguay soy/cattle
    "BO": "high",   # Bolivia soy/cattle
    "PE": "high",   # Peru wood/cocoa
    "CM": "high",   # Cameroon cocoa/wood
    "LR": "high",   # Liberia palm
    "SB": "high",   # Solomon Islands wood

    # Producer countries — standard until EC publishes
    "CO": "standard", "EC": "standard", "MX": "standard", "GT": "standard",
    "HN": "standard", "NI": "standard", "SV": "standard", "VE": "standard",
    "ET": "standard", "KE": "standard", "UG": "standard", "TZ": "standard",
    "RW": "standard", "BI": "standard", "MG": "standard", "MZ": "standard",
    "AO": "standard", "CD": "standard", "GA": "standard", "CG": "standard",
    "NG": "standard", "TG": "standard", "BJ": "standard", "SL": "standard",
    "VN": "standard", "TH": "standard", "PH": "standard", "LK": "standard",
    "IN": "standard", "BD": "standard", "KH": "standard", "LA": "standard",
}


def risk_for_country(country_code: str) -> str:
    """Return 'low' / 'standard' / 'high' for ISO 3166-1 alpha-2 code."""
    if not country_code:
        return "standard"
    return COUNTRY_RISK.get(country_code.upper(), "standard")


def is_high_risk(country_code: str) -> bool:
    return risk_for_country(country_code) == "high"
