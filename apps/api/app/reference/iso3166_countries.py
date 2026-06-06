"""ISO 3166-1 alpha-2 country reference (static, no external dependency).

Used for DSI region fallback picker and channel geographic hints. Codes map to ``dim_region.code``.
"""

from __future__ import annotations

from functools import lru_cache

# (alpha2, english_short_name) — subset complete for UN member states + common territories.
ISO3166_ALPHA2: tuple[tuple[str, str], ...] = (
    ("AF", "Afghanistan"),
    ("AL", "Albania"),
    ("DZ", "Algeria"),
    ("AS", "American Samoa"),
    ("AD", "Andorra"),
    ("AO", "Angola"),
    ("AG", "Antigua and Barbuda"),
    ("AR", "Argentina"),
    ("AM", "Armenia"),
    ("AU", "Australia"),
    ("AT", "Austria"),
    ("AZ", "Azerbaijan"),
    ("BS", "Bahamas"),
    ("BH", "Bahrain"),
    ("BD", "Bangladesh"),
    ("BB", "Barbados"),
    ("BY", "Belarus"),
    ("BE", "Belgium"),
    ("BZ", "Belize"),
    ("BJ", "Benin"),
    ("BT", "Bhutan"),
    ("BO", "Bolivia"),
    ("BA", "Bosnia and Herzegovina"),
    ("BW", "Botswana"),
    ("BR", "Brazil"),
    ("BN", "Brunei Darussalam"),
    ("BG", "Bulgaria"),
    ("BF", "Burkina Faso"),
    ("BI", "Burundi"),
    ("KH", "Cambodia"),
    ("CM", "Cameroon"),
    ("CA", "Canada"),
    ("CV", "Cabo Verde"),
    ("CF", "Central African Republic"),
    ("TD", "Chad"),
    ("CL", "Chile"),
    ("CN", "China"),
    ("CO", "Colombia"),
    ("KM", "Comoros"),
    ("CG", "Congo"),
    ("CD", "Democratic Republic of the Congo"),
    ("CR", "Costa Rica"),
    ("CI", "Côte d'Ivoire"),
    ("HR", "Croatia"),
    ("CU", "Cuba"),
    ("CY", "Cyprus"),
    ("CZ", "Czechia"),
    ("DK", "Denmark"),
    ("DJ", "Djibouti"),
    ("DM", "Dominica"),
    ("DO", "Dominican Republic"),
    ("EC", "Ecuador"),
    ("EG", "Egypt"),
    ("SV", "El Salvador"),
    ("GQ", "Equatorial Guinea"),
    ("ER", "Eritrea"),
    ("EE", "Estonia"),
    ("SZ", "Eswatini"),
    ("ET", "Ethiopia"),
    ("FJ", "Fiji"),
    ("FI", "Finland"),
    ("FR", "France"),
    ("GA", "Gabon"),
    ("GM", "Gambia"),
    ("GE", "Georgia"),
    ("DE", "Germany"),
    ("GH", "Ghana"),
    ("GR", "Greece"),
    ("GD", "Grenada"),
    ("GT", "Guatemala"),
    ("GN", "Guinea"),
    ("GW", "Guinea-Bissau"),
    ("GY", "Guyana"),
    ("HT", "Haiti"),
    ("HN", "Honduras"),
    ("HK", "Hong Kong"),
    ("HU", "Hungary"),
    ("IS", "Iceland"),
    ("IN", "India"),
    ("ID", "Indonesia"),
    ("IR", "Iran"),
    ("IQ", "Iraq"),
    ("IE", "Ireland"),
    ("IL", "Israel"),
    ("IT", "Italy"),
    ("JM", "Jamaica"),
    ("JP", "Japan"),
    ("JO", "Jordan"),
    ("KZ", "Kazakhstan"),
    ("KE", "Kenya"),
    ("KI", "Kiribati"),
    ("KP", "North Korea"),
    ("KR", "South Korea"),
    ("KW", "Kuwait"),
    ("KG", "Kyrgyzstan"),
    ("LA", "Lao People's Democratic Republic"),
    ("LV", "Latvia"),
    ("LB", "Lebanon"),
    ("LS", "Lesotho"),
    ("LR", "Liberia"),
    ("LY", "Libya"),
    ("LI", "Liechtenstein"),
    ("LT", "Lithuania"),
    ("LU", "Luxembourg"),
    ("MO", "Macao"),
    ("MG", "Madagascar"),
    ("MW", "Malawi"),
    ("MY", "Malaysia"),
    ("MV", "Maldives"),
    ("ML", "Mali"),
    ("MT", "Malta"),
    ("MH", "Marshall Islands"),
    ("MR", "Mauritania"),
    ("MU", "Mauritius"),
    ("MX", "Mexico"),
    ("FM", "Micronesia"),
    ("MD", "Moldova"),
    ("MC", "Monaco"),
    ("MN", "Mongolia"),
    ("ME", "Montenegro"),
    ("MA", "Morocco"),
    ("MZ", "Mozambique"),
    ("MM", "Myanmar"),
    ("NA", "Namibia"),
    ("NR", "Nauru"),
    ("NP", "Nepal"),
    ("NL", "Netherlands"),
    ("NZ", "New Zealand"),
    ("NI", "Nicaragua"),
    ("NE", "Niger"),
    ("NG", "Nigeria"),
    ("MK", "North Macedonia"),
    ("NO", "Norway"),
    ("OM", "Oman"),
    ("PK", "Pakistan"),
    ("PW", "Palau"),
    ("PS", "Palestine"),
    ("PA", "Panama"),
    ("PG", "Papua New Guinea"),
    ("PY", "Paraguay"),
    ("PE", "Peru"),
    ("PH", "Philippines"),
    ("PL", "Poland"),
    ("PT", "Portugal"),
    ("PR", "Puerto Rico"),
    ("QA", "Qatar"),
    ("RO", "Romania"),
    ("RU", "Russian Federation"),
    ("RW", "Rwanda"),
    ("KN", "Saint Kitts and Nevis"),
    ("LC", "Saint Lucia"),
    ("VC", "Saint Vincent and the Grenadines"),
    ("WS", "Samoa"),
    ("SM", "San Marino"),
    ("ST", "Sao Tome and Principe"),
    ("SA", "Saudi Arabia"),
    ("SN", "Senegal"),
    ("RS", "Serbia"),
    ("SC", "Seychelles"),
    ("SL", "Sierra Leone"),
    ("SG", "Singapore"),
    ("SK", "Slovakia"),
    ("SI", "Slovenia"),
    ("SB", "Solomon Islands"),
    ("SO", "Somalia"),
    ("ZA", "South Africa"),
    ("SS", "South Sudan"),
    ("ES", "Spain"),
    ("LK", "Sri Lanka"),
    ("SD", "Sudan"),
    ("SR", "Suriname"),
    ("SE", "Sweden"),
    ("CH", "Switzerland"),
    ("SY", "Syrian Arab Republic"),
    ("TW", "Taiwan"),
    ("TJ", "Tajikistan"),
    ("TZ", "Tanzania"),
    ("TH", "Thailand"),
    ("TL", "Timor-Leste"),
    ("TG", "Togo"),
    ("TO", "Tonga"),
    ("TT", "Trinidad and Tobago"),
    ("TN", "Tunisia"),
    ("TR", "Türkiye"),
    ("TM", "Turkmenistan"),
    ("TV", "Tuvalu"),
    ("UG", "Uganda"),
    ("UA", "Ukraine"),
    ("AE", "United Arab Emirates"),
    ("GB", "United Kingdom"),
    ("US", "United States of America"),
    ("UY", "Uruguay"),
    ("UZ", "Uzbekistan"),
    ("VU", "Vanuatu"),
    ("VE", "Venezuela"),
    ("VN", "Viet Nam"),
    ("YE", "Yemen"),
    ("ZM", "Zambia"),
    ("ZW", "Zimbabwe"),
)


@lru_cache(maxsize=1)
def alpha2_name_index() -> dict[str, str]:
    return {code.upper(): name for code, name in ISO3166_ALPHA2}


@lru_cache(maxsize=1)
def name_to_alpha2_index() -> dict[str, str]:
    out: dict[str, str] = {}
    for code, name in ISO3166_ALPHA2:
        out[name.strip().lower()] = code.upper()
    # Common aliases
    for alias, code in (
        ("united states", "US"),
        ("usa", "US"),
        ("u.s.", "US"),
        ("u.s.a.", "US"),
        ("uk", "GB"),
        ("u.k.", "GB"),
        ("great britain", "GB"),
        ("england", "GB"),
        ("korea", "KR"),
        ("south korea", "KR"),
        ("north korea", "KP"),
        ("czech republic", "CZ"),
        ("ivory coast", "CI"),
        ("vietnam", "VN"),
        ("russia", "RU"),
        ("turkey", "TR"),
        ("tanzania", "TZ"),
        ("bolivia", "BO"),
        ("venezuela", "VE"),
        ("iran", "IR"),
        ("syria", "SY"),
        ("laos", "LA"),
        ("cape verde", "CV"),
        ("eswatini", "SZ"),
        ("swaziland", "SZ"),
        ("burma", "MM"),
        ("taiwan", "TW"),
        ("hong kong", "HK"),
        ("macau", "MO"),
        ("uae", "AE"),
    ):
        out[alias] = code
    return out


def list_countries_for_api() -> list[dict[str, str]]:
    """Countries for steward fallback picker (ISO only, not demo commercial regions)."""
    return [{"alpha2": code, "name": name} for code, name in ISO3166_ALPHA2]


def resolve_alpha2_from_token(raw: str) -> str | None:
    """Conservative geographic hint: exact alpha2/alpha3, full name, or trailing segment in compound labels."""

    def _single_token(token: str) -> str | None:
        if not token or not str(token).strip():
            return None
        t = str(token).strip()
        upper = t.upper()
        alpha2 = alpha2_name_index()
        if len(upper) == 2 and upper in alpha2:
            return upper
        if len(upper) == 3:
            hit_a3 = name_to_alpha2_index().get(t.lower())
            if hit_a3:
                return hit_a3
        hit = name_to_alpha2_index().get(t.lower())
        if hit:
            return hit
        return None

    if not raw or not str(raw).strip():
        return None
    t = str(raw).strip()

    hit = _single_token(t)
    if hit:
        return hit

    # Leading whitespace-delimited token (legacy behaviour).
    parts = t.replace(",", " ").replace("/", " ").split()
    if parts:
        hit_lead = _single_token(parts[0])
        if hit_lead:
            return hit_lead

    # Compound labels: prefer trailing segment (SADC_Botswana → Botswana → BW).
    if "_" in t:
        tail = t.rsplit("_", 1)[-1].strip()
        hit_tail = _single_token(tail)
        if hit_tail:
            return hit_tail
        after_first = t.split("_", 1)[-1].strip()
        if after_first != tail:
            hit_after = _single_token(after_first)
            if hit_after:
                return hit_after

    if "-" in t:
        tail = t.rsplit("-", 1)[-1].strip()
        hit_tail = _single_token(tail)
        if hit_tail:
            return hit_tail

    if len(parts) > 1:
        hit_trail = _single_token(parts[-1])
        if hit_trail:
            return hit_trail

    return None
