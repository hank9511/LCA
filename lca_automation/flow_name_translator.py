"""Chinese flow name translator for ecoinvent database matching."""

import re
import json
import os
from typing import Optional, Dict, List, Tuple
from pathlib import Path

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_ALIAS_MAP_PATH = Path(__file__).parent / "flow_alias_mapping.json"


def _normalize_english_key(text: str) -> str:
    """Normalize an English flow name for case-insensitive alias lookup."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def _load_alias_map() -> Dict[str, Dict[str, str]]:
    """Load the alias→canonical map from disk."""
    try:
        if _ALIAS_MAP_PATH.exists():
            with open(_ALIAS_MAP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            aliases = data.get("aliases", {})
            if isinstance(aliases, dict):
                return aliases
    except Exception as e:
        print(f"⚠️ Failed to load flow alias map: {e}")
    return {}


_CHINESE_MODIFIERS = [
    "purchased",
    "self-produced",
    "by-product",
    "recycled",
    "waste",
    "inventory",
    "feedstock",
    "high-purity",
    "high-concentration",
    "concentrated",
    "dilute",
    "crude",
    "refined",
    "industrial-grade",
    "analytical-grade",
    "premium-grade",
    "first-grade",
    "qualified-grade",
    "plant",
    "workshop",
    "unit",
]

_SPEC_PREFIX_RE = re.compile(
    r"^[\-]?[\d]+[.]?[\d]*\s*(?:℃|°C|°c|MPa|Mpa|mpa|kPa|bar|atm)\s*"
)

_CIRCULATION_RE = re.compile(r"^(?:circulating|recycle[d]?)")

_LEVEL_PREFIX_RE = re.compile(r"^(?:primary|secondary|tertiary|[0-9]+(?:st|nd|rd|th)?)-?grade", re.IGNORECASE)


def _normalize_degree_symbols(text: str) -> str:
    """Normalize degree symbol variants for consistent cache keys."""
    if not text:
        return text
    return text.replace("°C", "℃").replace("°c", "℃")


_CORE_NOUN_DICT: Dict[str, str] = {
    "water": "tap water",
    "deionized water": "water, deionised",
    "process water": "tap water",
    "tap water": "tap water",
    "condensate": "tap water",
    "condensed water": "tap water",
    "cooling water": "tap water",
    "boiler feed water": "water, completely softened",
    "medium-pressure boiler feed water": "water, completely softened",
    "softened water": "water, completely softened",
    "distilled water": "water, deionised",
    "steam": "steam, in chemical industry",
    "air": "compressed air, 700 kPa gauge",
    "instrument air": "compressed air, 700 kPa gauge",
    "compressed air": "compressed air, 700 kPa gauge",
    "nitrogen": "nitrogen, liquid",
    "liquid nitrogen": "nitrogen, liquid",
    "oxygen": "oxygen, liquid",
    "liquid oxygen": "oxygen, liquid",
    "hydrogen": "hydrogen, liquid",
    "liquid hydrogen": "hydrogen, liquid",
    "argon": "argon, liquid",
    "carbon dioxide": "carbon dioxide, liquid",
    "electricity": "electricity, medium voltage",
    "electric power": "electricity, medium voltage",
    "photovoltaic power": "electricity, low voltage",
    "calcium carbide": "calcium carbide",
    "limestone": "limestone, crushed, washed",
    "lime": "quicklime, in packed",
    "hydrated lime": "hydrated lime",
    "methanol": "methanol",
    "ethanol": "ethanol, without water, in 99.7% solution state, from ethylene",
    "acetylene": "acetylene",
    "acetic acid": "acetic acid",
    "vinyl acetate": "vinyl acetate",
    "low-concentration vinyl acetate": "vinyl acetate, low concentration",
    "acetaldehyde": "acetaldehyde",
    "purified air": "compressed air, 700 kPa gauge",
    "non-purified air": "compressed air, 700 kPa gauge",
    "chilled water": "water, completely softened",
    "demineralized water": "water, deionised",
    "propionic acid": "propionic acid",
    "sulfuric acid": "sulfuric acid",
    "concentrated sulfuric acid": "sulfuric acid",
    "hydrochloric acid": "hydrochloric acid",
    "sodium hydroxide": "sodium hydroxide, without water, in 50% solution state",
    "caustic soda": "sodium hydroxide, without water, in 50% solution state",
    "sodium carbonate": "soda ash, light",
    "soda ash": "soda ash, light",
    "natural gas": "natural gas, high pressure",
    "coal": "hard coal",
    "feedstock coal": "hard coal",
    "coke": "coke",
    "carbon material": "coke",
    "coal tar": "coal tar",
    "electrode paste": "electrode paste",
    "limestone residue": "ite residue",
    "calcium carbide slag": "calcium carbide slag",
    "fusel oil": "fusel oil",
    "off-gas": "off-gas, from methanol synthesis",
    "ammonia": "ammonia, liquid",
    "liquid ammonia": "ammonia, liquid",
    "urea": "urea, as N",
    "chlorine": "chlorine, liquid",
    "sodium chloride": "sodium chloride, powder",
    "salt": "sodium chloride, powder",
    "phosphoric acid": "phosphoric acid, industrial grade, without water, in 85% solution state",
    "hydrogen peroxide": "hydrogen peroxide, without water, in 50% solution state",
    "butadiene": "butadiene",
    "propylene oxide": "propylene oxide, liquid",
    "ethylene oxide": "ethylene oxide",
    "polyethylene": "polyethylene, high density, granulate",
    "polypropylene": "polypropylene, granulate",
    "polyvinylchloride": "polyvinylchloride, bulk polymerised",
    "PVC": "polyvinylchloride, bulk polymerised",
    "ethylene": "ethylene",
    "propylene": "propylene",
    "styrene": "styrene",
    "benzene": "benzene",
    "toluene": "toluene",
    "xylene": "xylene",
    "methyl acetate": "methyl acetate",
    "iron": "pig iron",
    "steel": "steel, low-alloyed",
    "stainless steel": "steel, chromium steel 18/8",
    "aluminium": "aluminium, primary, ingot",
    "copper": "copper",
    "zinc": "zinc",
    "aniline": "aniline",
    "nitrobenzene": "nitrobenzene",
    "formaldehyde": "formaldehyde",
    "MDI": "methylene diphenyl diisocyanate",
    "TDI": "toluene diisocyanate",
    "diesel": "diesel",
    "gasoline": "petrol, unleaded",
    "heavy fuel oil": "heavy fuel oil",
    "liquefied petroleum gas": "liquefied petroleum gas",
    "LPG": "liquefied petroleum gas",
    "glass": "flat glass, uncoated",
    "cement": "cement, Portland",
    "concrete": "concrete, normal",
    "wood": "sawnwood, softwood, raw, air dried",
    "paper": "paper, woodfree, uncoated",
    "paperboard": "corrugated board box",
    "transport": "transport, freight, lorry",
    "road transport": "transport, freight, lorry 16-32 metric ton, EURO5",
    "rail transport": "transport, freight train",
    "waterway transport": "transport, freight, inland waterways, barge",
    "sea transport": "transport, freight, sea, container ship",
    "wastewater": "wastewater, average",
    "waste gas": "waste heat",
    "solid waste": "municipal solid waste",
}

ELEMENTARY_EMISSION_OVERRIDES: Dict[str, str] = {
    "carbon dioxide": "Carbon dioxide, fossil",
    "co2": "Carbon dioxide, fossil",
    "carbon monoxide": "Carbon monoxide, fossil",
    "methane": "Methane, fossil",
    "ch4": "Methane, fossil",
    "nitrous oxide": "Dinitrogen monoxide",
    "n2o": "Dinitrogen monoxide",
    "sulfur dioxide": "Sulfur dioxide",
    "so2": "Sulfur dioxide",
    "nitrogen oxides": "Nitrogen oxides",
    "nox": "Nitrogen oxides",
    "hydrogen sulfide": "Hydrogen sulfide",
    "h2s": "Hydrogen sulfide",
    "hydrogen chloride": "Hydrogen chloride",
    "hcl": "Hydrogen chloride",
    "hydrogen fluoride": "Hydrogen fluoride",
    "hf": "Hydrogen fluoride",
}

_ECOINVENT_SEARCH_VARIANTS: Dict[str, List[str]] = {
    "water": [
        "tap water",
        "water, deionised",
        "water, completely softened",
        "water, decarbonised",
    ],
    "compressed air": ["compressed air, 700 kPa gauge"],
    "nitrogen": ["nitrogen, liquid"],
    "oxygen": ["oxygen, liquid"],
    "hydrogen": ["hydrogen, liquid"],
    "steam": ["steam, in chemical industry"],
    "electricity": [
        "electricity, medium voltage",
        "electricity, high voltage",
        "electricity, low voltage",
    ],
    "sodium hydroxide": ["sodium hydroxide, without water, in 50% solution state"],
    "polyethylene": [
        "polyethylene, high density, granulate",
        "polyethylene, low density, granulate",
    ],
    "polypropylene": ["polypropylene, granulate"],
    "polyvinylchloride": ["polyvinylchloride, bulk polymerised"],
    "transport": [
        "transport, freight, lorry 16-32 metric ton, EURO5",
        "transport, freight train",
    ],
    "wastewater": ["wastewater, average", "wastewater, unpolluted"],
    "tar": ["coal tar"],
    "coal tar": ["coal tar"],
    "coke": ["coke"],
    "diesel": ["diesel"],
}

_PRESERVE_CHINESE_FLOW_KEYWORDS = (
    "brake disc",
    "manufacturing",
)


def contains_chinese(text: str) -> bool:
    """Check if text contains any Chinese characters."""
    if not text:
        return False
    return bool(_CJK_RE.search(text))


def normalize_chinese_flow_name(name: str) -> str:
    """Strip modifiers/adjectives from a Chinese flow name to extract the core noun."""
    if not name:
        return name

    result = name.strip()

    result = _normalize_degree_symbols(result)

    result = _SPEC_PREFIX_RE.sub("", result)

    result = _LEVEL_PREFIX_RE.sub("", result)

    result = _CIRCULATION_RE.sub("", result)

    for modifier in _CHINESE_MODIFIERS:
        if result.startswith(modifier) and len(result) > len(modifier):
            result = result[len(modifier) :]

    return result.strip() if result.strip() else name.strip()


def should_preserve_chinese_flow_name(name: str) -> bool:
    """Determine whether a Chinese flow name must be kept as-is."""
    if not name:
        return False
    if not contains_chinese(name):
        return False

    original = name.strip()
    normalized = normalize_chinese_flow_name(original)
    for keyword in _PRESERVE_CHINESE_FLOW_KEYWORDS:
        if keyword in original or keyword in normalized:
            return True
    return False


class FlowNameTranslator:
    """Translates Chinese flow names to English for ecoinvent database matching."""

    def __init__(
        self, cache_dir: Optional[str] = None, llm_clients: Optional[Dict] = None
    ):

        if cache_dir is None:
            cache_dir = str(Path(__file__).parent / ".cache")
        self._cache_path = os.path.join(cache_dir, "flow_name_mapping.json")
        self._cache: Dict[str, str] = {}
        self._llm_clients = llm_clients or {}

        self._unavailable_llms: set = set()

        self._alias_map: Dict[str, Dict[str, str]] = _load_alias_map()
        if self._alias_map:
            print(f"🔗 Loaded {len(self._alias_map)} flow alias→canonical mappings")
        self._load_cache()

    def _load_cache(self):
        """Load the persistent Chinese→English mapping cache."""
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                print(
                    f"📖 Loaded {len(self._cache)} Chinese→English flow name mappings from cache"
                )
        except Exception as e:
            print(f"⚠️ Failed to load flow name mapping cache: {e}")
            self._cache = {}
        self._reconcile_cache_with_dictionary()

    def _reconcile_cache_with_dictionary(self):
        """Ensure built-in dictionary entries override stale cache values."""
        updated = False
        for cn, en in _CORE_NOUN_DICT.items():
            if self._cache.get(cn) != en:
                self._cache[cn] = en
                updated = True
        if updated:
            self._save_cache()

        stale_keys = []
        for key, value in self._cache.items():
            if should_preserve_chinese_flow_name(key):
                stale_keys.append(key)
                continue
            if should_preserve_chinese_flow_name(value):
                stale_keys.append(key)
        if stale_keys:
            for key in stale_keys:
                self._cache.pop(key, None)
            self._save_cache()

    def _save_cache(self):
        """Persist the mapping cache to disk."""
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save flow name mapping cache: {e}")

    @staticmethod
    def _normalize_cache_key(name: str) -> str:
        """Normalize a name for consistent cache key lookup (degree symbols, whitespace)."""
        return _normalize_degree_symbols(name.strip())

    def translate(self, chinese_name: str) -> Optional[str]:
        """Translate a Chinese flow name to English using multi-tier strategy."""
        if not chinese_name or not contains_chinese(chinese_name):
            return None

        if should_preserve_chinese_flow_name(chinese_name):
            return None

        original = self._normalize_cache_key(chinese_name)

        if original in self._cache:
            cached = self._cache[original]
            if cached and cached != original:
                return cached

        normalized = normalize_chinese_flow_name(original)

        if normalized != original and normalized in self._cache:
            cached = self._cache[normalized]
            if cached and cached != normalized:
                self._cache[original] = cached
                self._save_cache()
                return cached

        en_name = _CORE_NOUN_DICT.get(original)
        if not en_name:
            en_name = _CORE_NOUN_DICT.get(normalized)

        if en_name:
            self._cache[original] = en_name
            if normalized != original:
                self._cache[normalized] = en_name
            self._save_cache()
            return en_name

        en_name = self._llm_translate(original, normalized)
        if en_name:
            self._cache[original] = en_name
            if normalized != original:
                self._cache[normalized] = en_name
            self._save_cache()
            return en_name

        return None

    def _llm_translate(self, original_name: str, normalized_name: str) -> Optional[str]:
        """Use LLM to translate a Chinese flow name to its ecoinvent English equivalent."""
        if not self._llm_clients:
            return None

        from .llm_utils import (
            call_llm_api,
            pick_available_llm,
            is_permanent_llm_failure,
        )

        prompt = f"""You are an LCA (Life Cycle Assessment) expert familiar with ecoinvent database flow names.

Translate the following Chinese flow name to its most likely corresponding English flow name in the ecoinvent database.

Chinese flow name (original): {original_name}
Chinese flow name (core noun): {normalized_name}

RULES:
1. Return ONLY the English flow name, nothing else.
2. Use ecoinvent naming conventions (lowercase, comma-separated qualifiers).
3. Common patterns: "electricity, medium voltage", "steam, in chemical industry", "water, deionised", "natural gas, high pressure", "transport, freight, lorry", etc.
4. If the Chinese name includes a pressure/temperature qualifier, include the appropriate ecoinvent qualifier (e.g., "steam, in chemical industry" for generic steam).
5. If you're unsure, give the most general ecoinvent flow name for that substance.

English flow name:"""

        attempted: set = set()
        last_err: Optional[BaseException] = None
        while True:
            chosen = pick_available_llm(
                self._llm_clients,
                exclude=self._unavailable_llms | attempted,
            )
            if chosen is None:
                break
            attempted.add(chosen)

            try:
                response = call_llm_api(
                    self._llm_clients, chosen, prompt, max_tokens=100
                )
            except Exception as e:
                last_err = e
                if is_permanent_llm_failure(e):
                    self._unavailable_llms.add(chosen)
                    print(
                        f"🚫 LLM '{chosen}' marked unavailable for this session "
                        f"(likely deprecated/404/401): {e}"
                    )
                else:
                    print(
                        f"⚠️ LLM translation transient failure on '{chosen}' for '{original_name}': {e}"
                    )
                continue

            if not response:
                continue
            en_name = response.strip().strip('"').strip("'").strip()

            if en_name and len(en_name) > 1 and not contains_chinese(en_name):
                print(f"🤖 [{chosen}] LLM translated '{original_name}' → '{en_name}'")
                return en_name

        if last_err is not None:
            print(
                f"⚠️ LLM translation failed for '{original_name}' after trying "
                f"{sorted(attempted) or ['<none>']}: {last_err}"
            )
        return None

    def get_translation_candidates(
        self, chinese_name: str, flow_type: str = ""
    ) -> List[str]:
        """Generate multiple English name candidates for database searching."""
        candidates = []
        if not chinese_name or not contains_chinese(chinese_name):
            return candidates
        if should_preserve_chinese_flow_name(chinese_name):
            return candidates

        original = self._normalize_cache_key(chinese_name)
        normalized = normalize_chinese_flow_name(original)

        def _add(name: str):
            """Deduplicated append."""
            if name and name not in candidates and not contains_chinese(name):
                candidates.append(name)

        if flow_type == "ELEMENTARY_FLOW":
            _add(ELEMENTARY_EMISSION_OVERRIDES.get(original, ""))
            if normalized != original:
                _add(ELEMENTARY_EMISSION_OVERRIDES.get(normalized, ""))

        if original in self._cache:
            _add(self._cache[original])

        if normalized != original and normalized in self._cache:
            _add(self._cache[normalized])

        _add(_CORE_NOUN_DICT.get(original, ""))
        if normalized != original:
            _add(_CORE_NOUN_DICT.get(normalized, ""))

        extra_variants = []
        for cand in candidates:
            base = cand.split(",")[0].strip().lower()
            for key, variants in _ECOINVENT_SEARCH_VARIANTS.items():
                if key == base or base == key:
                    for v in variants:
                        if v not in candidates and v not in extra_variants:
                            extra_variants.append(v)
        for v in extra_variants:
            _add(v)

        if not candidates:
            en_name = self._llm_translate(original, normalized)
            if en_name:
                _add(en_name)

                base = en_name.split(",")[0].strip().lower()
                for key, variants in _ECOINVENT_SEARCH_VARIANTS.items():
                    if key == base:
                        for v in variants:
                            _add(v)

        return candidates

    def add_mapping(self, chinese_name: str, english_name: str):
        """Manually add or update a mapping and persist to cache."""
        key = self._normalize_cache_key(chinese_name)
        english_name = english_name.strip()
        dict_override = _CORE_NOUN_DICT.get(key)
        if dict_override:
            english_name = dict_override
        self._cache[key] = english_name

        normalized = normalize_chinese_flow_name(key)
        if normalized != key and normalized not in self._cache:
            normalized_override = _CORE_NOUN_DICT.get(normalized)
            self._cache[normalized] = normalized_override or english_name
        self._save_cache()

    def resolve_canonical(self, name: str, flow_type: str = "") -> Optional[str]:
        """Resolve a fuzzed English or Chinese display name to its canonical"""
        if not name or not self._alias_map:
            return None

        entry = self._alias_map.get(name.strip())
        if entry is None:
            entry = self._alias_map.get(_normalize_english_key(name))
        if not entry:
            return None

        canonical = entry.get("canonical")
        entry_type = entry.get("flow_type", "")
        via = entry.get("via", "")
        if not canonical:
            return None

        if flow_type:
            normalized_type = self._normalize_flow_type_value(flow_type)
            if normalized_type and entry_type and normalized_type != entry_type:
                return None
            return canonical

        if via == "fuzzed_en":
            return canonical
        return None

    @staticmethod
    def _normalize_flow_type_value(value: str) -> str:
        """Normalize a flow-type string to the canonical FlowType token."""
        if not value:
            return ""
        v = value.strip().lower().replace(" ", "_")
        if "elementary" in v:
            return "ELEMENTARY_FLOW"
        if "waste" in v:
            return "WASTE_FLOW"
        if "product" in v:
            return "PRODUCT_FLOW"
        if v in ("elementary_flow", "product_flow", "waste_flow"):
            return v.upper()
        return (
            value.strip().upper()
            if value.strip().upper()
            in ("ELEMENTARY_FLOW", "PRODUCT_FLOW", "WASTE_FLOW")
            else ""
        )

    @property
    def cache_size(self) -> int:
        """Return the number of cached mappings."""
        return len(self._cache)
