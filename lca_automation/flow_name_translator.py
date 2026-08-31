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
    "外购",
    "自产",
    "副产",
    "回收",
    "废弃",
    "库存",
    "原料",
    "高纯",
    "高浓度",
    "浓",
    "稀",
    "粗",
    "精",
    "工业级",
    "分析纯",
    "优级品",
    "一等品",
    "合格品",
    "工厂",
    "车间",
    "装置",
]

_SPEC_PREFIX_RE = re.compile(
    r"^[\-]?[\d]+[.]?[\d]*\s*(?:℃|°C|°c|MPa|Mpa|mpa|kPa|bar|atm)\s*"
)

_CIRCULATION_RE = re.compile(r"^循环")

_LEVEL_PREFIX_RE = re.compile(r"^[一二三四五六七八九十]+级")


def _normalize_degree_symbols(text: str) -> str:
    """Normalize degree symbol variants for consistent cache keys."""
    if not text:
        return text
    return text.replace("°C", "℃").replace("°c", "℃")


_CORE_NOUN_DICT: Dict[str, str] = {
    "水": "tap water",
    "脱盐水": "water, deionised",
    "生产水": "tap water",
    "自来水": "tap water",
    "冷凝液": "tap water",
    "冷凝水": "tap water",
    "冷却水": "tap water",
    "锅炉给水": "water, completely softened",
    "中压锅炉给水": "water, completely softened",
    "软化水": "water, completely softened",
    "蒸馏水": "water, deionised",
    "去离子水": "water, deionised",
    "蒸汽": "steam, in chemical industry",
    "空气": "compressed air, 700 kPa gauge",
    "仪表空气": "compressed air, 700 kPa gauge",
    "压缩空气": "compressed air, 700 kPa gauge",
    "氮气": "nitrogen, liquid",
    "液氮": "nitrogen, liquid",
    "氧气": "oxygen, liquid",
    "液氧": "oxygen, liquid",
    "氢气": "hydrogen, liquid",
    "液氢": "hydrogen, liquid",
    "氩气": "argon, liquid",
    "二氧化碳": "carbon dioxide, liquid",
    "电": "electricity, medium voltage",
    "电力": "electricity, medium voltage",
    "电能": "electricity, medium voltage",
    "光伏发电": "electricity, low voltage",
    "电石": "calcium carbide",
    "石灰石": "limestone, crushed, washed",
    "石灰": "quicklime, in packed",
    "白灰": "hydrated lime",
    "甲醇": "methanol",
    "乙醇": "ethanol, without water, in 99.7% solution state, from ethylene",
    "乙炔": "acetylene",
    "醋酸": "acetic acid",
    "醋酸乙烯": "vinyl acetate",
    "低浓度醋酸乙烯": "vinyl acetate, low concentration",
    "乙醛": "acetaldehyde",
    "净化风": "compressed air, 700 kPa gauge",
    "非净化风": "compressed air, 700 kPa gauge",
    "冷冻水": "water, completely softened",
    "除盐水": "water, deionised",
    "丙酸": "propionic acid",
    "硫酸": "sulfuric acid",
    "浓硫酸": "sulfuric acid",
    "盐酸": "hydrochloric acid",
    "氢氧化钠": "sodium hydroxide, without water, in 50% solution state",
    "烧碱": "sodium hydroxide, without water, in 50% solution state",
    "碳酸钠": "soda ash, light",
    "纯碱": "soda ash, light",
    "天然气": "natural gas, high pressure",
    "煤": "hard coal",
    "原料煤": "hard coal",
    "焦炭": "coke",
    "碳材": "coke",
    "焦油": "coal tar",
    "电极糊": "electrode paste",
    "石灰石渣": "ite residue",
    "电石渣": "calcium carbide slag",
    "杂醇油": "fusel oil",
    "解析气": "off-gas, from methanol synthesis",
    "氨": "ammonia, liquid",
    "液氨": "ammonia, liquid",
    "尿素": "urea, as N",
    "氯气": "chlorine, liquid",
    "氯化钠": "sodium chloride, powder",
    "食盐": "sodium chloride, powder",
    "磷酸": "phosphoric acid, industrial grade, without water, in 85% solution state",
    "双氧水": "hydrogen peroxide, without water, in 50% solution state",
    "过氧化氢": "hydrogen peroxide, without water, in 50% solution state",
    "丁二烯": "butadiene",
    "环氧丙烷": "propylene oxide, liquid",
    "环氧乙烷": "ethylene oxide",
    "聚乙烯": "polyethylene, high density, granulate",
    "聚丙烯": "polypropylene, granulate",
    "聚氯乙烯": "polyvinylchloride, bulk polymerised",
    "PVC": "polyvinylchloride, bulk polymerised",
    "乙烯": "ethylene",
    "丙烯": "propylene",
    "苯乙烯": "styrene",
    "苯": "benzene",
    "甲苯": "toluene",
    "二甲苯": "xylene",
    "醋酸甲酯": "methyl acetate",
    "铁": "pig iron",
    "钢": "steel, low-alloyed",
    "不锈钢": "steel, chromium steel 18/8",
    "铝": "aluminium, primary, ingot",
    "铜": "copper",
    "锌": "zinc",
    "苯胺": "aniline",
    "硝基苯": "nitrobenzene",
    "甲醛": "formaldehyde",
    "MDI": "methylene diphenyl diisocyanate",
    "TDI": "toluene diisocyanate",
    "柴油": "diesel",
    "汽油": "petrol, unleaded",
    "重油": "heavy fuel oil",
    "液化石油气": "liquefied petroleum gas",
    "LPG": "liquefied petroleum gas",
    "玻璃": "flat glass, uncoated",
    "水泥": "cement, Portland",
    "混凝土": "concrete, normal",
    "木材": "sawnwood, softwood, raw, air dried",
    "纸": "paper, woodfree, uncoated",
    "纸板": "corrugated board box",
    "运输": "transport, freight, lorry",
    "公路运输": "transport, freight, lorry 16-32 metric ton, EURO5",
    "铁路运输": "transport, freight train",
    "水路运输": "transport, freight, inland waterways, barge",
    "海运": "transport, freight, sea, container ship",
    "废水": "wastewater, average",
    "废气": "waste heat",
    "固废": "municipal solid waste",
}

ELEMENTARY_EMISSION_OVERRIDES: Dict[str, str] = {
    "二氧化碳": "Carbon dioxide, fossil",
    "一氧化碳": "Carbon monoxide, fossil",
    "甲烷": "Methane, fossil",
    "氧化亚氮": "Dinitrogen monoxide",
    "二氧化硫": "Sulfur dioxide",
    "氮氧化物": "Nitrogen oxides",
    "硫化氢": "Hydrogen sulfide",
    "氯化氢": "Hydrogen chloride",
    "氟化氢": "Hydrogen fluoride",
    "粉尘": "Particulates, > 2.5 um, and < 10um",
    "颗粒物": "Particulates, > 2.5 um, and < 10um",
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
    "刹车盘",
    "生产制造",
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
                        f"🚫 LLM '{chosen}' 在本会话内被标记为不可用 "
                        f"(疑似 deprecated/404/401)：{e}"
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
