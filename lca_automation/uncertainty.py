"""Uncertainty helpers for the public LCA modeling pipeline."""

import math
import re
from typing import Dict, List, Optional, Tuple, Any
from openai import OpenAI
import olca_schema as o
import olca_ipc as ipc
from .config import MARKET_PROCESS_PATTERN
from .llm_utils import call_llm_api, pick_available_llm


def _check_provider_output_amount(
    provider_ref: o.Ref, flow_ref: o.Ref, client: ipc.Client
) -> float:
    """Check the output amount of a specific flow from a provider process"""
    try:

        provider_process = client.get(o.Process, provider_ref.id)
        if not provider_process or not provider_process.exchanges:
            return 0.0

        for exchange in provider_process.exchanges:
            if (
                not exchange.is_input
                and exchange.flow
                and exchange.flow.id == flow_ref.id
            ):
                return exchange.amount

        return 0.0

    except Exception as e:
        print(
            f"⚠️ Error checking provider output amount for '{provider_ref.name}' -> '{flow_ref.name}': {e}"
        )
        return 0.0


def _check_provider_output_and_location(
    provider_ref: o.Ref, flow_ref: o.Ref, client: ipc.Client
) -> Tuple[float, str]:

    try:
        provider_process = client.get(o.Process, provider_ref.id)
        if not provider_process:
            return 0.0, ""

        location_code = ""
        if provider_process.location:
            loc_ref = provider_process.location
            if loc_ref.name:
                location_code = _normalize_location_code(loc_ref.name)

            if not location_code or len(location_code) > 3:
                try:
                    location_obj = client.get(o.Location, loc_ref.id)
                    if location_obj:
                        raw = location_obj.code or location_obj.name or ""
                        location_code = (
                            _normalize_location_code(raw) if raw else location_code
                        )
                except Exception:
                    pass

        output_amount = 0.0
        if provider_process.exchanges:
            for exchange in provider_process.exchanges:
                if (
                    not exchange.is_input
                    and exchange.flow
                    and exchange.flow.id == flow_ref.id
                ):
                    output_amount = exchange.amount
                    break

        return output_amount, location_code
    except Exception:
        return 0.0, ""


def _calculate_name_similarity(flow_name: str, provider_name: str) -> float:
    """Calculate similarity between flow name and provider name to prioritize relevant providers"""
    try:

        flow_name_lower = flow_name.lower()
        provider_name_lower = provider_name.lower()

        flow_words = set(flow_name_lower.replace(",", " ").replace(";", " ").split())
        provider_words = set(
            provider_name_lower.replace(",", " ").replace(";", " ").split()
        )

        if len(flow_words) == 0 and len(provider_words) == 0:
            return 1.0
        elif len(flow_words) == 0 or len(provider_words) == 0:
            return 0.0

        intersection = len(flow_words.intersection(provider_words))
        union = len(flow_words.union(provider_words))

        jaccard_score = intersection / union if union > 0 else 0

        containment_score = 1.0 if flow_name_lower in provider_name_lower else 0.0

        combined_score = 0.7 * jaccard_score + 0.3 * containment_score

        return combined_score

    except Exception as e:
        print(f"⚠️ Error calculating name similarity: {e}")
        return 0.0


def _is_market_activity(provider_name: str) -> bool:

    return bool(re.search(MARKET_PROCESS_PATTERN, provider_name))


_REGION_TO_COUNTRY_CODE = {
    "india": "IN",
    "indian": "IN",
    "china": "CN",
    "chinese": "CN",
    "shanghai": "CN",
    "beijing": "CN",
    "germany": "DE",
    "german": "DE",
    "berlin": "DE",
    "munich": "DE",
    "france": "FR",
    "french": "FR",
    "paris": "FR",
    "italy": "IT",
    "italian": "IT",
    "spain": "ES",
    "spanish": "ES",
    "united kingdom": "GB",
    "uk": "GB",
    "britain": "GB",
    "british": "GB",
    "london": "GB",
    "usa": "US",
    "united states": "US",
    "american": "US",
    "japan": "JP",
    "japanese": "JP",
    "korea": "KR",
    "korean": "KR",
    "south korea": "KR",
    "brazil": "BR",
    "brazilian": "BR",
    "australia": "AU",
    "australian": "AU",
    "canada": "CA",
    "canadian": "CA",
    "russia": "RU",
    "russian": "RU",
    "south africa": "ZA",
    "mexico": "MX",
    "mexican": "MX",
    "indonesia": "ID",
    "indonesian": "ID",
    "thailand": "TH",
    "thai": "TH",
    "vietnam": "VN",
    "vietnamese": "VN",
    "pakistan": "PK",
    "pakistani": "PK",
    "bangladesh": "BD",
    "turkey": "TR",
    "turkish": "TR",
    "poland": "PL",
    "polish": "PL",
    "netherlands": "NL",
    "dutch": "NL",
    "belgium": "BE",
    "belgian": "BE",
    "sweden": "SE",
    "swedish": "SE",
    "switzerland": "CH",
    "swiss": "CH",
    "austria": "AT",
    "austrian": "AT",
    "norway": "NO",
    "norwegian": "NO",
    "denmark": "DK",
    "danish": "DK",
    "finland": "FI",
    "finnish": "FI",
    "portugal": "PT",
    "portuguese": "PT",
    "greece": "GR",
    "greek": "GR",
    "ireland": "IE",
    "irish": "IE",
    "czech republic": "CZ",
    "czech": "CZ",
    "romania": "RO",
    "romanian": "RO",
    "hungary": "HU",
    "hungarian": "HU",
    "taiwan": "TW",
    "singapore": "SG",
    "malaysia": "MY",
    "philippines": "PH",
    "chile": "CL",
    "colombia": "CO",
    "argentina": "AR",
    "peru": "PE",
    "egypt": "EG",
    "nigeria": "NG",
    "kenya": "KE",
    "ethiopia": "ET",
    "iran": "IR",
    "saudi arabia": "SA",
    "uae": "AE",
    "united arab emirates": "AE",
}

_COUNTRY_NAME_TO_CODE = {name: code for name, code in _REGION_TO_COUNTRY_CODE.items()}

_KNOWN_SHORT_CODES = {
    "GLO",
    "RER",
    "RoW",
    "ROW",
    "RNA",
    "RLA",
    "RAF",
    "RAS",
    "RME",
    "UN-AMERICAS",
    "UN-EUROPE",
    "UN-AFRICA",
    "UN-ASIA",
    "UN-OCEANIA",
    "ENTSO-E",
    "NORDEL",
    "UCTE",
    "WECC",
    "RFC",
    "ASCC",
    "FRCC",
    "HICC",
    "MRO",
    "NPCC",
    "SERC",
    "SPP",
    "TRE",
    "IAI Area",
}


def _normalize_location_code(raw_location: str) -> str:

    if not raw_location:
        return ""

    stripped = raw_location.strip()
    if not stripped:
        return ""

    if len(stripped) <= 3:
        return stripped

    if stripped in _KNOWN_SHORT_CODES:
        return stripped

    lower = stripped.lower()
    if lower in _COUNTRY_NAME_TO_CODE:
        return _COUNTRY_NAME_TO_CODE[lower]

    return stripped


_EU_COUNTRY_CODES = {
    "DE",
    "FR",
    "IT",
    "ES",
    "NL",
    "BE",
    "AT",
    "PL",
    "SE",
    "DK",
    "FI",
    "IE",
    "PT",
    "GR",
    "CZ",
    "RO",
    "HU",
    "SK",
    "BG",
    "HR",
    "LT",
    "LV",
    "EE",
    "SI",
    "CY",
    "LU",
    "MT",
}

_EFTA_CODES = {"CH", "NO", "IS", "LI"}

_STAGE_KEYWORDS = {
    "raw_material": [
        "raw material",
        "extraction",
        "mining",
        "harvest",
        "cultivation",
        "pre-process",
    ],
    "manufacturing": [
        "manufactur",
        "production",
        "assembly",
        "fabricat",
        "processing",
        "making",
        "sewing",
        "knitting",
        "weaving",
        "dyeing",
        "printing",
    ],
    "distribution": [
        "distribut",
        "transport",
        "export",
        "import",
        "shipping",
        "logistics",
        "freight",
    ],
    "use": [
        "use phase",
        "use stage",
        "use ",
        " use",
        "used",
        "consumption",
        "consumer",
        "operation",
        "worn",
        "wash",
        "wearing",
        "laundry",
        "cleaning",
        "maintenance",
    ],
    "end_of_life": [
        "disposal",
        "disposed",
        "end of life",
        "end-of-life",
        "recycl",
        "waste",
        "incinerat",
        "landfill",
        "discard",
    ],
}


def _extract_location_from_provider_name(provider_name: str) -> str:

    patterns = [
        r"\s*-\s*([A-Z]{2}-[A-Za-z0-9-]+)\s*$",
        r"Cutoff,\s*[A-Z]\s*-\s*([A-Z]{2}-[A-Za-z0-9-]+)",
        r"\s*-\s*([A-Z][A-Za-z]{1,2})\s*$",
        r"\|\s*([A-Z][A-Za-z]{1,2})\s*$",
        r"Cutoff,\s*[A-Z]\s*-\s*([A-Z][A-Za-z]{1,2})",
        r",\s*([A-Z]{2,3})\s*$",
        r"\|\s*(RER)\b",
        r"\|\s*(RoW)\b",
        r"\|\s*(GLO)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, provider_name)
        if match:
            return match.group(1).strip()

    return ""


def _determine_process_stage(process_context: str) -> str:

    proc_lower = process_context.lower()
    for stage, keywords in _STAGE_KEYWORDS.items():
        for kw in keywords:
            if kw in proc_lower:
                return stage
    return "unknown"


def _extract_process_specific_geography(
    system_description: str, process_context: str
) -> Optional[str]:

    if not system_description:
        return None

    stage = _determine_process_stage(process_context)
    if stage == "unknown":
        return None

    desc_lower = system_description.lower()

    sentence_fragments = re.split(r"[.;!\n]", desc_lower)
    clause_fragments = re.split(r"[.;!\n,]", desc_lower)

    stage_kws = _STAGE_KEYWORDS.get(stage, [])

    for fragment in sentence_fragments:
        fragment = fragment.strip()
        if not fragment:
            continue
        stage_mentioned = any(kw in fragment for kw in stage_kws)
        if stage_mentioned:
            for geo_kw, code in _REGION_TO_COUNTRY_CODE.items():
                if geo_kw in fragment:
                    return code

    for fragment in clause_fragments:
        fragment = fragment.strip()
        if not fragment:
            continue
        stage_mentioned = any(kw in fragment for kw in stage_kws)
        if stage_mentioned:
            for geo_kw, code in _REGION_TO_COUNTRY_CODE.items():
                if geo_kw in fragment:
                    return code

    _proximity_patterns = {
        "manufacturing": [
            rf"(?:manufactur|produc|process|assembl|fabricat|made|take\s+place)\w*"
            rf".{{0,60}}?(?:in|at)\s+\w{{0,15}}?\s*({_geo_alternation()})",
        ],
        "raw_material": [
            rf"(?:raw\s+material|extract|min(?:e|ing)|harvest|cultivat)\w*"
            rf".{{0,60}}?(?:in|at|from)\s+\w{{0,15}}?\s*({_geo_alternation()})",
        ],
        "use": [
            rf"(?:use[ds]?|consum|worn|wash|wear|laundry|clean|maintenanc)\w*"
            rf".{{0,60}}?(?:in|at)\s+\w{{0,15}}?\s*({_geo_alternation()})",
            rf"(?:(?:export|ship|deliver|sold?|sell)\w*\s+to)\s+\w{{0,15}}?\s*({_geo_alternation()})",
        ],
        "end_of_life": [
            rf"(?:dispos|end.of.life|recycl|waste|incinerat|landfill|discard)\w*"
            rf".{{0,60}}?(?:in|at)\s+\w{{0,15}}?\s*({_geo_alternation()})",
            rf"(?:(?:export|ship|deliver|sold?|sell)\w*\s+to)\s+\w{{0,15}}?\s*({_geo_alternation()})",
        ],
        "distribution": [
            rf"(?:distribut|transport|ship|export|import|freight|logistic)\w*"
            rf".{{0,60}}?(?:to|from|in|between)\s+\w{{0,15}}?\s*({_geo_alternation()})",
        ],
    }

    patterns = _proximity_patterns.get(stage, [])
    for pat in patterns:
        m = re.search(pat, desc_lower)
        if m:
            matched_geo = m.group(1).strip().lower()
            if matched_geo in _REGION_TO_COUNTRY_CODE:
                return _REGION_TO_COUNTRY_CODE[matched_geo]

    if stage == "end_of_life":
        use_geo = _extract_process_specific_geography(system_description, "use phase")
        if use_geo:
            return use_geo

    return None


def _geo_alternation() -> str:

    sorted_keys = sorted(_REGION_TO_COUNTRY_CODE.keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in sorted_keys)


def llm_extract_stage_geography_mapping(
    system_description: str,
    llm_clients: Dict[str, OpenAI],
    process_names: List[str] = None,
) -> Dict[str, str]:

    if not system_description or not llm_clients:
        return {}

    available_llm = pick_available_llm(llm_clients)

    if not available_llm:
        return {}

    process_list_str = ""
    if process_names:
        process_list_str = "\n".join(f"- {name}" for name in process_names)

    prompt = f"""You are an LCA (Life Cycle Assessment) expert. Given the system boundary description below, determine the geographic location (country) where each lifecycle stage takes place.

System boundary description:
"{system_description}"

{f"Process names in this LCA study:{chr(10)}{process_list_str}" if process_list_str else ""}

For EACH process or lifecycle stage mentioned, identify the country or region where it takes place.
Use ISO 3166-1 alpha-2 country codes (e.g., IN=India, DE=Germany, CN=China, US=USA, PK=Pakistan).
Use "RER" for generic European processes, "RoW" for Rest of World, "GLO" for truly global/unknown.

Rules:
- If manufacturing/production happens in one country but use/consumption in another, they must have DIFFERENT codes
- Distribution/transport between countries should use GLO unless explicitly regional
- End-of-life/disposal typically occurs in the SAME country as the use phase
- If a stage's location is not explicitly mentioned, infer from context (e.g., if product is "used in Germany", disposal also likely in Germany)
- Be precise: do NOT assign the manufacturing country to the use phase or vice versa

Return ONLY a JSON object mapping process/stage names to country codes. Example:
{{"manufacturing": "IN", "distribution": "GLO", "use": "DE", "end_of_life": "DE"}}

{f"Also map these specific process names:{chr(10)}" + chr(10).join(f'"{name}": "<code>"' for name in process_names) if process_names else ""}

Return ONLY the JSON object, no other text."""

    try:
        response = call_llm_api(
            llm_clients, available_llm, prompt, max_tokens=500, temperature=0.0
        )
        if not response:
            return {}

        import json

        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```\w*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
            clean = clean.strip()

        mapping = json.loads(clean)
        if not isinstance(mapping, dict):
            return {}

        result = {}
        valid_codes = set()
        valid_codes.update(_REGION_TO_COUNTRY_CODE.values())
        valid_codes.update(_EU_COUNTRY_CODES)
        valid_codes.update(_EFTA_CODES)
        valid_codes.update({"GLO", "RER", "RoW", "ROW"})

        for key, code in mapping.items():
            if isinstance(code, str) and code.upper() in {
                c.upper() for c in valid_codes
            }:
                result[key.lower()] = code.upper()
                if code.upper() == "ROW":
                    result[key.lower()] = "RoW"

        print(f"🌍 LLM地理映射提取结果: {result}")
        return result

    except Exception as e:
        print(f"⚠️ LLM地理映射提取失败: {e}")
        return {}


def resolve_process_geography(
    process_name: str, stage_geography_mapping: Dict[str, str]
) -> str:

    if not stage_geography_mapping:
        return ""

    proc_lower = process_name.lower()

    for key, code in stage_geography_mapping.items():
        key_lower = key.lower()
        if key_lower in proc_lower or proc_lower in key_lower:
            return code

    stage = _determine_process_stage(process_name)
    if stage != "unknown" and stage in stage_geography_mapping:
        return stage_geography_mapping[stage]

    for key, code in stage_geography_mapping.items():
        key_stage = _determine_process_stage(key)
        if key_stage != "unknown" and key_stage == stage:
            return code

    return ""


def _get_expected_location_codes(
    system_description: str, process_context: str
) -> List[str]:

    if not system_description:
        return ["GLO"]

    country_code = _extract_process_specific_geography(
        system_description, process_context
    )

    if country_code:
        result = [country_code]

        if country_code in _EU_COUNTRY_CODES or country_code in _EFTA_CODES:
            result.append("RER")
        else:
            result.append("RoW")
        result.append("GLO")
        print(f"🌍 过程 '{process_context}' 的地理匹配优先级: {' → '.join(result)}")
        return result

    stage = _determine_process_stage(process_context)

    if stage != "unknown":

        desc_lower = system_description.lower()
        default_codes = []
        for geo_kw, code in _REGION_TO_COUNTRY_CODE.items():
            if geo_kw in desc_lower and code not in default_codes:
                default_codes.append(code)

        if len(default_codes) == 1:
            result = [default_codes[0]]
            if default_codes[0] in _EU_COUNTRY_CODES or default_codes[0] in _EFTA_CODES:
                result.append("RER")
            else:
                result.append("RoW")
            result.append("GLO")
            print(
                f"🌍 过程 '{process_context}' 阶段={stage}，使用系统边界默认地区: {' → '.join(result)}"
            )
            return result

        print(
            f"🌍 过程 '{process_context}' 阶段={stage} 但无法从描述中提取对应地区，回退到 GLO"
        )
        return ["GLO"]

    desc_lower = system_description.lower()
    all_codes = []
    for geo_kw, code in _REGION_TO_COUNTRY_CODE.items():
        if geo_kw in desc_lower and code not in all_codes:
            all_codes.append(code)

    if all_codes:
        has_eu = any(c in _EU_COUNTRY_CODES or c in _EFTA_CODES for c in all_codes)
        has_non_eu = any(
            c not in _EU_COUNTRY_CODES and c not in _EFTA_CODES for c in all_codes
        )
        result = all_codes[:]
        if has_eu and "RER" not in result:
            result.append("RER")
        if has_non_eu and "RoW" not in result:
            result.append("RoW")
        result.append("GLO")
        return result

    return ["GLO"]


def _calculate_geographic_match_score(
    provider_name: str, expected_codes: List[str]
) -> float:

    provider_location = _extract_location_from_provider_name(provider_name)
    if not provider_location:
        return 0.0

    prov_upper = provider_location.upper()

    for code in expected_codes:
        code_upper = code.upper()
        if prov_upper == code_upper:
            if code_upper == "GLO":
                return 0.4
            elif code_upper in ("RER", "ROW"):
                return 0.7
            else:
                return 1.0

        if (
            len(code) == 2
            and code_upper not in ("GLO", "RER", "ROW")
            and prov_upper.startswith(code_upper + "-")
        ):
            return 1.0

    return 0.0


def _calculate_geographic_match_score_by_code(
    location_code: str, expected_codes: List[str]
) -> float:

    if not location_code:
        return 0.0

    normalized = _normalize_location_code(location_code)
    prov_upper = normalized.upper() if normalized else location_code.upper()

    for code in expected_codes:
        code_upper = code.upper()

        if prov_upper == code_upper:
            if code_upper == "GLO":
                return 0.4
            elif code_upper in ("RER", "ROW"):
                return 0.7
            else:
                return 1.0

        if (
            len(code) == 2
            and code_upper not in ("GLO", "RER", "ROW")
            and prov_upper.startswith(code_upper + "-")
        ):
            return 1.0

    return 0.0


def create_uncertainty_from_cv(
    cv_value: float, mean_value: float, distribution_type: str = "NORMAL"
) -> o.Uncertainty:
    """Create uncertainty distribution from CV value"""
    uncertainty = o.Uncertainty()

    if distribution_type == "LOG_NORMAL":
        uncertainty.distribution_type = o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
        uncertainty.geom_mean = mean_value

        uncertainty.geom_sd = math.exp(math.sqrt(math.log(cv_value**2 + 1)))

        try:
            from .config import DISPLAY_UNCERTAINTY_DETAILS

            if DISPLAY_UNCERTAINTY_DETAILS:
                print(
                    f"    📊 Applied log-normal uncertainty: mean={mean_value:.4f}, geom_sd={uncertainty.geom_sd:.4f}, CV={cv_value:.3f}"
                )
        except:
            pass

    elif distribution_type == "NORMAL":
        uncertainty.distribution_type = o.UncertaintyType.NORMAL_DISTRIBUTION
        uncertainty.mean = mean_value
        uncertainty.sd = mean_value * cv_value

        try:
            from .config import DISPLAY_UNCERTAINTY_DETAILS

            if DISPLAY_UNCERTAINTY_DETAILS:
                print(
                    f"    📊 Applied normal uncertainty: mean={mean_value:.4f}, sd={uncertainty.sd:.4f}, CV={cv_value:.3f}"
                )
        except:
            pass

    else:

        uncertainty.distribution_type = o.UncertaintyType.NORMAL_DISTRIBUTION
        uncertainty.mean = mean_value
        uncertainty.sd = mean_value * cv_value

        try:
            from .config import DISPLAY_UNCERTAINTY_DETAILS

            if DISPLAY_UNCERTAINTY_DETAILS:
                print(
                    f"    📊 Applied default normal uncertainty: mean={mean_value:.4f}, sd={uncertainty.sd:.4f}, CV={cv_value:.3f}"
                )
        except:
            pass

    return uncertainty
