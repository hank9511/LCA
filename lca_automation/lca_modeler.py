"""Main LCA modeler class for the LCA analysis system"""

import uuid
import re
import json
import math
import statistics
from typing import Dict, List, Optional, Any, Tuple, Set
import Levenshtein
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.ioff()
import numpy as np
from datetime import datetime
import olca_ipc as ipc
import olca_schema as o

from .data_structures import (
    FlowSpec,
    ProcessSpec,
    ProductSystemSpec,
    SimpleExchange,
    Flow,
    Process,
    ProductSystem,
    LCACase,
)
from .config import (
    PREFERRED_LCIA_METHOD,
    UNCERTAINTY_ANALYSIS_ENABLED,
    MONTE_CARLO_ITERATIONS,
    LLM_PROVIDER_SELECTION_MAX_CANDIDATES,
    UPSTREAM_TRACING_MAX_DEPTH,
    PREFER_EXCEL_PROVIDERS,
    ENABLE_UNLIMITED_EXCEL_LINKING,
    DISABLE_BACKGROUND_UPSTREAM_TRACING,
    ENABLE_WASTE_FLOW_LINKING,
    WASTE_FLOW_MAX_DEPTH,
    DIAGNOSTIC_SHOW_SCALING_FACTORS,
    SKIP_DUMMY_PROVIDERS,
    DUMMY_PROCESS_NAME_PATTERN,
    PREFER_MARKET_PROCESSES,
    MARKET_PROCESSES_AS_CUTOFF,
    MARKET_PROCESS_PATTERN,
    VERBOSE_OUTPUT,
    ENABLE_CHINESE_FLOW_TRANSLATION,
    CHINESE_FLOW_SIMILARITY_THRESHOLD,
    CHINESE_FLOW_LLM_EVALUATION,
    MC_SAFE_LINK_SANITIZE,
    PROVIDER_SELECTION_MODE,
    CANDIDATE_CONSTRAINT_MODE,
    ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
)
from .llm_utils import call_llm_api
from .uncertainty import create_uncertainty_from_cv
from .project_context import ProjectContext
from .flow_name_translator import (
    FlowNameTranslator,
    contains_chinese,
    normalize_chinese_flow_name,
    ELEMENTARY_EMISSION_OVERRIDES,
)

PHOTOVOLTAIC_EXCEL_FLOW_NAME = "光伏发电"
PHOTOVOLTAIC_TARGET_FLOW_NAME = "electricity, low voltage"
PHOTOVOLTAIC_PROVIDER_NAME = (
    "electricity production, photovoltaic, 3kWp facade installation, "
    "multi-Si, laminated, integrated | electricity, low voltage | Cutoff, U"
)


class UniversalLCAModeler:
    """Universal LCA Modeler"""

    def __init__(
        self,
        ipc_client: ipc.Client,
        llm_clients: Dict[str, Any] = None,
        project_context: Optional[ProjectContext] = None,
        runtime_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize LCA Modeler"""
        self.client = ipc_client
        self.llm_clients = llm_clients or {}
        self.project_context = (
            project_context if project_context is not None else ProjectContext.default()
        )
        self.runtime_config = runtime_config or {}
        self.created_flows = {}
        self.created_processes = {}
        self.excel_flow_providers = {}
        self.excel_explicit_providers = {}
        self.excel_explicit_providers_by_key = {}

        self.excel_waste_consumers = {}
        self.pending_output_provider_links = []
        self.provider_cv_results = {}
        self.flow_provider_cache = {}
        self._provider_candidates_cache = {}

        self._consumer_flow_provider_usage: Dict[Tuple[str, str], Set[str]] = {}
        self.uncertainty_enabled = UNCERTAINTY_ANALYSIS_ENABLED
        self.preferred_lcia_method = self.project_context.lcia_method_keyword
        self.flow_name_translator = FlowNameTranslator(llm_clients=self.llm_clients)
        self._all_flow_descriptors_cache = None
        self._stage_geography_cache = None
        self.provider_selection_mode = (
            str(
                self.runtime_config.get(
                    "PROVIDER_SELECTION_MODE",
                    self.runtime_config.get(
                        "provider_selection_mode", PROVIDER_SELECTION_MODE
                    ),
                )
            )
            .strip()
            .lower()
        )
        if self.provider_selection_mode == "full":
            print(
                "ℹ️ Public snapshot: provider quality-scoring is not included; "
                "using semantic matching."
            )
            self.provider_selection_mode = "semantic_only"
        self.candidate_constraint_mode = (
            str(
                self.runtime_config.get(
                    "CANDIDATE_CONSTRAINT_MODE",
                    self.runtime_config.get(
                        "candidate_mode", CANDIDATE_CONSTRAINT_MODE
                    ),
                )
            )
            .strip()
            .lower()
        )
        self.enable_lifecycle_stage_classification = bool(
            self.runtime_config.get(
                "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION",
                self.runtime_config.get(
                    "stage_classification",
                    ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
                ),
            )
        )

        self.excel_process_names: Set[str] = set()
        print(
            "🧪 Provider选择模式: "
            f"provider_mode={self.provider_selection_mode}, "
            f"candidate_mode={self.candidate_constraint_mode}, "
            f"stage_classification={self.enable_lifecycle_stage_classification}"
        )

        self._excel_unit_label_map = {
            "t": "t",
            "ton": "t",
            "tons": "t",
            "tonne": "t",
            "tonnes": "t",
            "kg": "kg",
            "g": "g",
            "mg": "mg",
            "kwh": "kWh",
            "mwh": "MWh",
            "wh": "Wh",
            "mj": "MJ",
            "gj": "GJ",
            "m3": "m3",
            "m³": "m3",
            "l": "l",
            "ml": "ml",
        }

        self._transport_unit_aliases = frozenset(
            {
                "t*km",
                "tkm",
                "t·km",
                "t km",
                "ton*km",
                "tonkm",
                "ton·km",
                "ton km",
                "kg*km",
                "kgkm",
                "kg·km",
                "kg km",
                "tonne*km",
                "tonnekm",
                "tonne·km",
                "tonne km",
            }
        )
        self._count_unit_aliases = frozenset(
            {
                "item(s)",
                "items",
                "item",
                "p",
                "piece",
                "pieces",
                "unit",
                "units",
                "pc",
                "pcs",
                "number",
            }
        )
        self._flow_property_candidates = {
            "count": ["Number", "number", "Number of items"],
            "transport": [
                "Mass transport",
                "Goods transport (mass*distance)",
                "Transport",
                "Mass*length",
            ],
            "mass": ["Mass"],
            "energy": ["Energy"],
            "volume": ["Volume"],
            "area": ["Area"],
            "length": ["Length"],
        }

    def set_preferred_impact_method(self, method_keyword: str):
        """Set preferred impact assessment method for both deterministic and uncertainty analysis"""
        self.preferred_lcia_method = method_keyword
        print(f"✅ Preferred impact assessment method set to: '{method_keyword}'")
        print(f"   This will be used for both deterministic and uncertainty analysis")

    def _select_provider_by_semantic_similarity(
        self,
        providers: List[Any],
        flow_name: str,
        excel_flow_name: str = "",
    ) -> Tuple[Optional[o.Ref], Dict[str, Any]]:

        if not providers:
            return None, {}

        from .uncertainty import _is_market_activity

        target_names = [flow_name]
        if excel_flow_name and excel_flow_name != flow_name:
            target_names.append(excel_flow_name)

        candidate_refs: List[o.Ref] = []
        for provider_obj in providers:
            provider_ref = getattr(provider_obj, "provider", None)
            if provider_ref is None and hasattr(provider_obj, "id"):
                provider_ref = provider_obj
            if provider_ref and getattr(provider_ref, "name", ""):
                candidate_refs.append(provider_ref)

        if not candidate_refs:
            return None, {}

        if self.candidate_constraint_mode != "expanded_or_unconstrained":
            market_refs = [
                ref for ref in candidate_refs if _is_market_activity(ref.name or "")
            ]
            if market_refs:
                candidate_refs = market_refs

            max_candidates = int(
                self.runtime_config.get(
                    "SEMANTIC_SELECTION_MAX_CANDIDATES",
                    LLM_PROVIDER_SELECTION_MAX_CANDIDATES,
                )
                or 0
            )
            if max_candidates > 0:
                candidate_refs = candidate_refs[:max_candidates]

        scored: List[Tuple[float, o.Ref]] = []
        for candidate in candidate_refs:
            cand_name = (candidate.name or "").lower()
            if not cand_name:
                continue
            best_similarity = max(
                Levenshtein.ratio((target or "").lower(), cand_name)
                for target in target_names
            )
            scored.append((best_similarity, candidate))

        if not scored:
            return candidate_refs[0], {
                "selection_mode": "semantic_only",
                "candidate_count": len(candidate_refs),
            }

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_provider = scored[0]
        print(
            f"🧪 [semantic_only] 选择provider: {best_provider.name} "
            f"(semantic_score={best_score:.3f}, candidates={len(candidate_refs)})"
        )
        return best_provider, {
            "selection_mode": "semantic_only",
            "semantic_score": best_score,
            "candidate_count": len(candidate_refs),
        }

    def _normalize_flow_type(self, value: Any) -> str:
        """Normalize flow type representations to uppercase string constants."""
        if not value:
            return ""

        if isinstance(value, str):
            return value.upper().strip()

        try:
            name = getattr(value, "name", None)
            if name:
                return name.upper().strip()
        except Exception:
            pass

        value_str = str(value)
        if "." in value_str:
            value_str = value_str.split(".")[-1]
        return value_str.upper().strip()

    def _find_excel_waste_treater(
        self, flow_name: str, exclude_process_id: str = ""
    ) -> Optional[Any]:
        """Look up the Excel-defined treater (waste consumer) for a waste flow."""
        if not flow_name:
            return None
        consumers = self.excel_waste_consumers.get(flow_name) or []
        for treater_name in consumers:
            treater_ref = self.created_processes.get(treater_name)
            if treater_ref is None:
                continue
            if (
                exclude_process_id
                and getattr(treater_ref, "id", None) == exclude_process_id
            ):
                continue
            return treater_ref
        return None

    def _determine_flow_type(self, flow_obj: Any) -> str:
        """Determine the flow type string for a given flow object or reference."""
        if not flow_obj:
            return ""

        try:

            if isinstance(flow_obj, o.Ref):
                flow_obj = self.client.get(o.Flow, flow_obj.id)
        except Exception as error:
            print(
                f"⚠️ Unable to resolve flow reference when determining flow type: {error}"
            )
            return ""

        flow_type_value = getattr(flow_obj, "flow_type", None)
        flow_type = self._normalize_flow_type(flow_type_value)

        if flow_type in {"PRODUCT_FLOW", "ELEMENTARY_FLOW", "WASTE_FLOW"}:
            return flow_type

        return ""

    def _ensure_flow_type(self, flow_ref: o.Ref, flow_spec: FlowSpec) -> o.Ref:
        """Ensure an existing flow matches the desired flow type and category."""
        if not flow_ref:
            return flow_ref

        desired_type = self._normalize_flow_type(getattr(flow_spec, "flow_type", ""))

        try:
            flow_obj = self.client.get(o.Flow, flow_ref.id)
        except Exception as error:
            print(
                f"⚠️ Unable to load flow '{flow_ref.name}' for type validation: {error}"
            )
            return flow_ref

        current_type = self._determine_flow_type(flow_obj)

        if desired_type and desired_type not in {
            "PRODUCT_FLOW",
            "ELEMENTARY_FLOW",
            "WASTE_FLOW",
        }:
            print(
                f"⚠️ Desired flow type '{desired_type}' for '{flow_ref.name}' is invalid; skipping update"
            )
            desired_type = ""

        if desired_type and current_type and desired_type != current_type:
            try:
                flow_obj.flow_type = getattr(o.FlowType, desired_type)
                self.client.put(flow_obj)
                print(
                    f"🔁 Updated flow type for '{flow_obj.name}' from {current_type or 'UNKNOWN'} to {desired_type}"
                )
                current_type = desired_type
            except Exception as error:
                print(f"⚠️ Failed to update flow type for '{flow_obj.name}': {error}")

        elif desired_type and not current_type:
            try:
                flow_obj.flow_type = getattr(o.FlowType, desired_type)
                self.client.put(flow_obj)
                print(f"🔁 Assigned flow type '{desired_type}' to '{flow_obj.name}'")
                current_type = desired_type
            except Exception as error:
                print(f"⚠️ Failed to assign flow type for '{flow_obj.name}': {error}")

        if getattr(flow_spec, "category", None):
            desired_category = flow_spec.category
            try:
                if desired_category and flow_obj.category != desired_category:
                    flow_obj.category = desired_category
                    self.client.put(flow_obj)
                    print(
                        f"📁 Updated category for '{flow_obj.name}' to '{desired_category}'"
                    )
            except Exception as error:
                print(f"⚠️ Failed to update category for '{flow_obj.name}': {error}")

        return flow_ref

    def _ensure_flow_property(self, flow_ref: o.Ref, flow_spec: FlowSpec) -> o.Ref:
        """Ensure an existing flow has the correct FlowProperty based on its unit."""
        if not flow_ref:
            return flow_ref

        if not hasattr(flow_spec, "unit"):
            return flow_ref

        try:
            flow_obj = self.client.get(o.Flow, flow_ref.id)
        except Exception as error:
            print(
                f"⚠️ Unable to load flow '{flow_ref.name}' for FlowProperty validation: {error}"
            )
            return flow_ref

        standardized_unit, _ = self.standardize_unit(flow_spec.unit, 1.0)

        expected_prop_ref = self.get_flow_property_for_unit(standardized_unit)
        if not expected_prop_ref:
            print(
                f"⚠️ Cannot determine expected FlowProperty for unit '{standardized_unit}'"
            )
            return flow_ref

        if not flow_obj.flow_properties or len(flow_obj.flow_properties) == 0:
            print(f"⚠️ Flow '{flow_obj.name}' has no flow properties!")
            return flow_ref

        current_ref_prop = next(
            (fp for fp in flow_obj.flow_properties if fp.is_ref_flow_property), None
        )

        if not current_ref_prop or not current_ref_prop.flow_property:
            print(f"⚠️ Flow '{flow_obj.name}' has no reference flow property!")
            return flow_ref

        current_prop_id = current_ref_prop.flow_property.id
        expected_prop_id = expected_prop_ref.id

        if current_prop_id != expected_prop_id:

            print(f"🔧 Flow '{flow_obj.name}' has wrong FlowProperty!")
            print(
                f"   Current: {current_ref_prop.flow_property.name if hasattr(current_ref_prop.flow_property, 'name') else 'unknown'}"
            )
            print(
                f"   Expected: {expected_prop_ref.name} (for unit: {standardized_unit})"
            )

            try:

                flow_obj.reference_flow_property = expected_prop_ref

                for fp in flow_obj.flow_properties:
                    if fp.is_ref_flow_property:
                        fp.flow_property = expected_prop_ref
                        break

                self.client.put(flow_obj)
                print(
                    f"✅ Updated FlowProperty for '{flow_obj.name}' to '{expected_prop_ref.name}'"
                )

            except Exception as error:
                print(f"⚠️ Failed to update FlowProperty for '{flow_obj.name}': {error}")
        else:

            pass

        return flow_ref

    def _is_compound_or_transport_unit(self, unit: str) -> bool:
        """Return True for mass*distance and other compound transport units."""
        if not unit:
            return False
        unit_lower = unit.lower().strip()
        if unit_lower in self._transport_unit_aliases:
            return True
        return any(sep in unit_lower for sep in ("*", "·", "×", "/"))

    def _is_count_unit(self, unit: str) -> bool:
        """Return True for piece/item count units (must use Number flow property)."""
        if not unit:
            return False
        return unit.lower().strip() in self._count_unit_aliases

    def _is_excel_lifecycle_flow(self, flow_name: str) -> bool:
        """Return True when a flow name matches an Excel foreground process name."""
        if not flow_name or not self.excel_process_names:
            return False
        return flow_name.strip() in self.excel_process_names

    def _resolve_lifecycle_process_flow(
        self,
        flow_spec: FlowSpec,
        create_if_missing: bool,
    ) -> Optional[o.Ref]:
        """Get or create a foreground flow for lifecycle process hand-off."""
        flow_name = flow_spec.name.strip()
        desired_type = self._normalize_flow_type(flow_spec.flow_type or "")

        cached_entry = self.created_flows.get(flow_name)
        if cached_entry:
            cached_ref = (
                cached_entry["ref"] if isinstance(cached_entry, dict) else cached_entry
            )
            cached_name = (getattr(cached_ref, "name", "") or "").strip()
            if cached_name == flow_name:
                return self._ensure_flow_property(cached_ref, flow_spec)

            del self.created_flows[flow_name]

        existing = self._find_exact_flow_by_name_and_type(flow_name, desired_type)
        if existing:
            print(
                f"✅ Reusing lifecycle hand-off flow '{flow_name}' (matches Excel process name)"
            )
            return self._validate_and_cache_flow(flow_name, existing, flow_spec)

        if create_if_missing:
            print(
                f"🔨 Creating lifecycle hand-off flow '{flow_name}' "
                f"(Excel process name; skip ecoinvent translation)"
            )
            new_flow_ref = self.create_new_flow(flow_spec)
            if new_flow_ref:
                self.created_flows[flow_name] = {
                    "ref": new_flow_ref,
                    "flow_type": flow_spec.flow_type or "UNKNOWN",
                }
            return new_flow_ref
        return None

    def _try_link_excel_lifecycle_process_provider(
        self,
        excel_lookup_name: str,
        flow_ref: o.Ref,
        cache_key: Tuple,
        process_context: str,
    ) -> Optional[Tuple[Optional[o.Ref], Dict]]:
        """Link consumer input to the Excel process whose name equals the flow name."""
        if not self._is_excel_lifecycle_flow(excel_lookup_name):
            return None

        supplier_ref = self.created_processes.get(excel_lookup_name.strip())
        if not supplier_ref:
            return None

        if self._cache_flow_provider(cache_key, supplier_ref, flow_ref):
            print(
                f"🔗 Excel lifecycle hand-off: '{process_context}' input "
                f"'{excel_lookup_name}' → '{supplier_ref.name}'"
            )
            self._apply_provider_metadata(supplier_ref, flow_ref)
            return supplier_ref, {}

        output_amount = self._check_provider_output_amount(supplier_ref, flow_ref)
        if output_amount > 0 or self._provider_supports_flow(supplier_ref, flow_ref):
            self.flow_provider_cache[cache_key] = (supplier_ref, {})
            print(
                f"🔗 Excel lifecycle hand-off (direct): '{process_context}' input "
                f"'{excel_lookup_name}' → '{supplier_ref.name}'"
            )
            self._apply_provider_metadata(supplier_ref, flow_ref)
            return supplier_ref, {}

        print(
            f"⚠️ Excel lifecycle process '{excel_lookup_name}' exists but does not "
            f"output flow '{flow_ref.name}' — check Excel outputs for this stage"
        )
        return None

    def _find_flow_property_by_candidates(
        self, candidates: List[str]
    ) -> Optional[o.Ref]:
        """Resolve FlowProperty by trying multiple database name variants."""
        for name in candidates:
            prop_ref = self.client.find(o.FlowProperty, name)
            if prop_ref:
                return prop_ref
        try:
            wanted = {name.lower() for name in candidates}
            for descriptor in self.client.get_descriptors(o.FlowProperty):
                if descriptor.name.lower() in wanted:
                    return descriptor
        except Exception as error:
            print(f"⚠️ FlowProperty descriptor scan failed: {error}")
        return None

    def _unit_name_aliases_for_matching(self, unit: str) -> List[str]:
        """Build ordered alias list when matching a unit inside a UnitGroup."""
        if not unit:
            return []
        original = unit.strip()
        unit_lower = original.lower()
        aliases: List[str] = [original]

        if self._is_count_unit(unit):
            aliases.extend(
                [
                    "Item(s)",
                    "item(s)",
                    "items",
                    "item",
                    "p",
                    "unit",
                    "units",
                    "piece",
                    "pieces",
                    "pc",
                    "pcs",
                ]
            )
        elif self._is_compound_or_transport_unit(unit):
            aliases.extend(
                [
                    original.replace(" ", "*"),
                    original.replace("·", "*"),
                    unit_lower.replace(" ", "*"),
                    unit_lower.replace("·", "*"),
                    "t*km",
                    "tkm",
                    "kg*km",
                    "kgkm",
                ]
            )
        elif unit_lower in ("t", "ton", "tons", "tonne", "tonnes"):
            aliases.extend(["t", "tonne", "ton", "metric ton", "Mg"])
        elif unit_lower in ("kwh",):
            aliases.extend(["kWh", "kwh", "Kwh", "KWh"])

        seen = set()
        unique_aliases: List[str] = []
        for alias in aliases:
            key = alias.lower()
            if key not in seen:
                seen.add(key)
                unique_aliases.append(alias)
        return unique_aliases

    def _find_matching_unit_in_group(self, unit_group_obj, target_unit: str):
        """Find a Unit in a UnitGroup for Excel/openLCA unit strings."""
        if not unit_group_obj or not unit_group_obj.units:
            return None

        alias_candidates = self._unit_name_aliases_for_matching(target_unit)
        alias_lower = [alias.lower().strip() for alias in alias_candidates]

        for alias in alias_candidates:
            for unit_obj in unit_group_obj.units:
                if unit_obj.name.strip() == alias:
                    return unit_obj

        for alias_lower_name in alias_lower:
            for unit_obj in unit_group_obj.units:
                if unit_obj.name.lower().strip() == alias_lower_name:
                    return unit_obj

        is_compound = self._is_compound_or_transport_unit(target_unit)
        if not is_compound:
            target_lower = target_unit.lower().strip()
            for unit_obj in unit_group_obj.units:
                unit_name_lower = unit_obj.name.lower().strip()
                if (
                    target_lower == unit_name_lower
                    or target_lower in unit_name_lower.split()
                    or unit_name_lower in target_lower.split()
                ):
                    return unit_obj
        return None

    def _convert_amount_in_unit_group(
        self,
        amount: float,
        from_unit_name: str,
        to_unit_obj,
        unit_group_obj,
    ) -> float:
        """Convert an amount between units in the same openLCA UnitGroup."""
        if not unit_group_obj or not unit_group_obj.units or not to_unit_obj:
            return amount
        from_unit_obj = self._find_matching_unit_in_group(
            unit_group_obj, from_unit_name
        )
        if not from_unit_obj:
            return amount
        from_factor = float(getattr(from_unit_obj, "conversion_factor", 1.0) or 1.0)
        to_factor = float(getattr(to_unit_obj, "conversion_factor", 1.0) or 1.0)
        if from_factor == 0 or to_factor == 0:
            return amount
        amount_in_ref = float(amount) * from_factor
        return amount_in_ref / to_factor

    def _normalize_excel_unit_label(self, unit: str) -> str:
        """Normalize Excel unit strings for openLCA matching without changing amounts."""
        if not unit or str(unit).lower() == "nan":
            return "kg"
        stripped = str(unit).strip()
        return self._excel_unit_label_map.get(stripped.lower(), stripped)

    def standardize_unit(self, unit: str, amount: float) -> Tuple[str, float]:
        """Normalize unit label only; preserve Excel amount."""
        normalized_unit = self._normalize_excel_unit_label(unit)
        try:
            normalized_amount = float(amount)
        except (TypeError, ValueError):
            normalized_amount = amount
        return normalized_unit, normalized_amount

    def get_available_impact_methods(self) -> List[str]:
        """Get list of all available impact assessment methods in the database"""
        try:
            all_methods = self.client.get_descriptors(o.ImpactMethod)
            method_names = [method.name for method in all_methods]

            print(f"📊 Available Impact Assessment Methods ({len(method_names)}):")
            for i, name in enumerate(method_names, 1):
                print(f"  {i}. {name}")

            return method_names
        except Exception as e:
            print(f"❌ Error retrieving impact methods: {e}")
            return []

    def find_similar_flows(
        self, target_name: str, category: str = "", similarity_threshold: float = 0.7
    ) -> List[Tuple[o.Ref, float]]:
        """Find similar flows in the background database using cached descriptors."""
        try:
            all_flows = self._get_all_flow_descriptors()
            similar_flows = []

            for flow_ref in all_flows:
                similarity = Levenshtein.ratio(
                    target_name.lower(), flow_ref.name.lower()
                )

                if category:
                    try:
                        flow_obj = self.client.get(o.Flow, flow_ref.id)
                        if (
                            flow_obj.category
                            and category.lower() not in flow_obj.category.lower()
                        ):
                            similarity *= 0.8
                    except:
                        pass

                if similarity >= similarity_threshold:
                    similar_flows.append((flow_ref, similarity))

            similar_flows.sort(key=lambda x: x[1], reverse=True)
            return similar_flows

        except Exception as e:
            print(f"❌ Error finding similar flows: {e}")
            return []

    def llm_evaluate_flow_match_strict(
        self, target_spec: FlowSpec, candidate_flows: List[o.Ref]
    ) -> Optional[o.Ref]:
        """Use LLM to evaluate flow matching quality with strict criteria for complete name preservation,"""
        if not candidate_flows or not self.llm_clients:
            return None

        available_llm = "deepseek"
        if available_llm not in self.llm_clients or not self.llm_clients[available_llm]:
            print("⚠️ No available LLM for strict flow matching evaluation")
            return None

        try:

            candidate_info = []
            for i, flow_ref in enumerate(candidate_flows):
                try:
                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                    candidate_info.append(
                        f"{i+1}. {flow_ref.name} (Category: {flow_obj.category or 'Not specified'})"
                    )
                except:
                    candidate_info.append(f"{i+1}. {flow_ref.name}")

            candidate_info_str = "\n".join(candidate_info)

            prompt = f"""
You are an LCA expert evaluating flow matching for universal cases, considering synonyms, units, and semantic equivalence.

Target flow:
- Name: {target_spec.name}
- Category: {target_spec.category}
- Type: {target_spec.flow_type}
- Unit: {target_spec.unit}

Candidate flows:
{candidate_info_str}

CRITERIA:
1. Consider synonyms and name variations (e.g., 'power' = 'electricity', 'gas' = 'natural gas', 'caustic' = 'sodium hydroxide').
2. Match units or convertible units (e.g., 'tons' ~ 'kg' with conversion, 'kW' ~ 'kWh').
3. Allow semantic matches if functionally identical (e.g., '50% Caustic' matches 'Sodium hydroxide solution').
4. Prioritize functional equivalence over exact naming.
5. Return number of best match, or '0' if none suitable for all cases.

EXAMPLES:
- Target 'power' (kW) matches 'electricity' (kWh) if energy context.
- Target 'caustic' (tons) matches 'sodium hydroxide' (kg) with unit conversion.
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=50
            )

            match = re.search(r"\b([0-{}])\b".format(len(candidate_info)), response)
            if match:
                choice = int(match.group(1))
                if 1 <= choice <= len(candidate_flows):
                    selected_flow = candidate_flows[choice - 1]
                    print(f"🤖 LLM approved strict match: {selected_flow.name}")
                    return selected_flow
                elif choice == 0:
                    print(
                        "🤖 LLM found no exact functional match - will create new flow"
                    )
                    return None

            print(
                "⚠️ LLM response could not be parsed, being conservative - will create new flow"
            )
            return None

        except Exception as e:
            print(f"❌ LLM strict flow matching evaluation failed: {e}")
            return None

    def llm_evaluate_flow_match(
        self, target_spec: FlowSpec, candidate_flows: List[o.Ref]
    ) -> Optional[o.Ref]:
        """Use LLM to evaluate flow matching quality"""
        if not candidate_flows or not self.llm_clients:
            return None

        available_llm = "deepseek"
        if available_llm not in self.llm_clients or not self.llm_clients[available_llm]:
            print("⚠️ No available LLM for flow matching evaluation")
            return candidate_flows[0] if candidate_flows else None

        try:

            candidate_info = []
            for i, flow_ref in enumerate(candidate_flows[:5]):
                try:
                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                    candidate_info.append(
                        f"{i+1}. {flow_ref.name} (Category: {flow_obj.category or 'Not specified'})"
                    )
                except:
                    candidate_info.append(f"{i+1}. {flow_ref.name}")

            candidate_info_str = "\n".join(candidate_info)

            prompt = f"""
You are a Life Cycle Assessment (LCA) expert. Please help me evaluate the matching quality of the following flows:

Target flow specification:
- Name: {target_spec.name}
- Category: {target_spec.category}
- Type: {target_spec.flow_type}

Candidate flows:
{candidate_info_str}

Please analyze the matching degree of each candidate flow with the target flow, considering:
1. Name semantic similarity
2. Category matching
3. Usage consistency

Please only return the number of the best match (1-{len(candidate_info)}), or return "0" if there is no suitable match.
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=50
            )

            match = re.search(r"\b([0-{}])\b".format(len(candidate_info)), response)
            if match:
                choice = int(match.group(1))
                if 1 <= choice <= len(candidate_flows):
                    selected_flow = candidate_flows[choice - 1]
                    print(f"🤖 LLM selected flow: {selected_flow.name}")
                    return selected_flow
                elif choice == 0:
                    print("🤖 LLM found no suitable match")
                    return None

            print("⚠️ LLM response could not be parsed, using first candidate flow")
            return candidate_flows[0]

        except Exception as e:
            print(f"❌ LLM flow matching evaluation failed: {e}")
            return candidate_flows[0] if candidate_flows else None

    def _validate_and_cache_flow(
        self, flow_name: str, flow_ref: o.Ref, flow_spec: FlowSpec
    ) -> o.Ref:
        """Validate flow type/property and cache the result."""
        validated = self._ensure_flow_type(flow_ref, flow_spec)
        validated = self._ensure_flow_property(validated, flow_spec)
        resolved_type = self._determine_flow_type(validated)
        stored_type = resolved_type or flow_spec.flow_type or "UNKNOWN"
        self.created_flows[flow_name] = {"ref": validated, "flow_type": stored_type}
        return validated

    def _find_exact_flow_by_name_and_type(
        self, flow_name: str, desired_type: str = ""
    ) -> Optional[o.Ref]:
        """Find an exact-name flow, preferring a flow whose type matches desired_type."""
        normalized_name = (flow_name or "").strip().lower()
        if not normalized_name:
            return None

        candidates = []
        for ref in self._get_all_flow_descriptors():
            ref_name = (getattr(ref, "name", "") or "").strip().lower()
            if ref_name == normalized_name:
                candidates.append(ref)

        if not candidates:
            return None

        desired = self._normalize_flow_type(desired_type)
        if not desired:
            return candidates[0]

        matched = []
        mismatch_summaries = []
        for ref in candidates:
            flow_type = self._determine_flow_type(ref)
            mismatch_summaries.append(
                f"{getattr(ref, 'name', 'unknown')}:{flow_type or 'UNKNOWN'}"
            )
            if flow_type == desired:
                matched.append(ref)

        if matched:
            return matched[0]

        print(
            f"⚠️ Exact-name flow '{flow_name}' exists but type mismatch "
            f"(required: {desired}; candidates: {', '.join(mismatch_summaries[:5])})"
        )
        return None

    def _get_all_flow_descriptors(self) -> list:
        """Get all flow descriptors from the database with lazy caching."""
        if self._all_flow_descriptors_cache is None:
            try:
                self._all_flow_descriptors_cache = list(
                    self.client.get_descriptors(o.Flow)
                )
                if VERBOSE_OUTPUT:
                    print(
                        f"📋 Cached {len(self._all_flow_descriptors_cache)} flow descriptors for matching"
                    )
            except Exception as e:
                print(f"⚠️ Failed to cache flow descriptors: {e}")
                self._all_flow_descriptors_cache = []
        return self._all_flow_descriptors_cache

    def _find_flows_by_name_prefix(
        self, prefix: str, max_results: int = 15
    ) -> List[o.Ref]:
        """Find flows whose names start with the given prefix (case-insensitive)."""
        try:
            all_flows = self._get_all_flow_descriptors()
            prefix_lower = prefix.lower().strip()
            if not prefix_lower:
                return []

            matches = []
            for flow_ref in all_flows:
                name_lower = flow_ref.name.lower()
                if name_lower == prefix_lower:
                    continue
                if name_lower.startswith(prefix_lower + ",") or name_lower.startswith(
                    prefix_lower + " "
                ):
                    matches.append(flow_ref)

            return matches[:max_results]
        except Exception as e:
            print(f"⚠️ Prefix search failed for '{prefix}': {e}")
            return []

    def _try_match_english_name(
        self, english_name: str, flow_spec: FlowSpec, original_chinese_name: str
    ) -> Optional[o.Ref]:
        """Attempt to match an English name candidate against the ecoinvent database."""

        if original_chinese_name == "解析气" or "off-gas" in english_name:

            exact_match = self._find_exact_flow_by_name_and_type(
                english_name,
                self._normalize_flow_type(getattr(flow_spec, "flow_type", "")),
            )
            if exact_match:
                return self._validate_and_cache_flow(
                    original_chinese_name, exact_match, flow_spec
                )
            return None

        desired_type = self._normalize_flow_type(getattr(flow_spec, "flow_type", ""))

        exact_match = self._find_exact_flow_by_name_and_type(english_name, desired_type)
        if exact_match:
            print(
                f"✅ Chinese flow '{original_chinese_name}' → exact match '{english_name}' in database"
            )
            return self._validate_and_cache_flow(
                original_chinese_name, exact_match, flow_spec
            )

        prefix_matches = self._find_flows_by_name_prefix(english_name)
        if prefix_matches:
            if len(prefix_matches) == 1:
                best = prefix_matches[0]
                print(
                    f"✅ Chinese flow '{original_chinese_name}' → prefix match '{best.name}'"
                )
                self.flow_name_translator.add_mapping(original_chinese_name, best.name)
                return self._validate_and_cache_flow(
                    original_chinese_name, best, flow_spec
                )
            else:
                if CHINESE_FLOW_LLM_EVALUATION:
                    best = self._llm_evaluate_chinese_flow_match(
                        original_chinese_name,
                        english_name,
                        flow_spec,
                        prefix_matches[:10],
                    )
                    if best:
                        print(
                            f"🤖 Chinese flow '{original_chinese_name}' → LLM prefix match '{best.name}'"
                        )
                        self.flow_name_translator.add_mapping(
                            original_chinese_name, best.name
                        )
                        return self._validate_and_cache_flow(
                            original_chinese_name, best, flow_spec
                        )

                shortest = min(prefix_matches, key=lambda r: len(r.name))
                print(
                    f"✅ Chinese flow '{original_chinese_name}' → best prefix match '{shortest.name}'"
                )
                self.flow_name_translator.add_mapping(
                    original_chinese_name, shortest.name
                )
                return self._validate_and_cache_flow(
                    original_chinese_name, shortest, flow_spec
                )

        if "," in english_name:
            base_name = english_name.split(",")[0].strip()
            base_prefix_matches = self._find_flows_by_name_prefix(base_name)
            if base_prefix_matches:
                if CHINESE_FLOW_LLM_EVALUATION:
                    best = self._llm_evaluate_chinese_flow_match(
                        original_chinese_name,
                        english_name,
                        flow_spec,
                        base_prefix_matches[:10],
                    )
                    if best:
                        print(
                            f"🤖 Chinese flow '{original_chinese_name}' → LLM base-prefix match '{best.name}'"
                        )
                        self.flow_name_translator.add_mapping(
                            original_chinese_name, best.name
                        )
                        return self._validate_and_cache_flow(
                            original_chinese_name, best, flow_spec
                        )

        similar = self.find_similar_flows(
            english_name,
            flow_spec.category,
            similarity_threshold=CHINESE_FLOW_SIMILARITY_THRESHOLD,
        )
        if similar:
            candidate_refs = [ref for ref, _ in similar[:8]]

            if CHINESE_FLOW_LLM_EVALUATION:
                best = self._llm_evaluate_chinese_flow_match(
                    original_chinese_name, english_name, flow_spec, candidate_refs
                )
                if best:
                    print(
                        f"🤖 Chinese flow '{original_chinese_name}' → LLM matched '{best.name}'"
                    )
                    self.flow_name_translator.add_mapping(
                        original_chinese_name, best.name
                    )
                    return self._validate_and_cache_flow(
                        original_chinese_name, best, flow_spec
                    )

            high_sim = [(ref, sim) for ref, sim in similar if sim >= 0.90]
            if high_sim:
                best_ref, best_sim = high_sim[0]
                print(
                    f"✅ Chinese flow '{original_chinese_name}' → high similarity ({best_sim:.0%}) '{best_ref.name}'"
                )
                self.flow_name_translator.add_mapping(
                    original_chinese_name, best_ref.name
                )
                return self._validate_and_cache_flow(
                    original_chinese_name, best_ref, flow_spec
                )

        return None

    def _llm_evaluate_chinese_flow_match(
        self,
        chinese_name: str,
        english_name: str,
        flow_spec: FlowSpec,
        candidate_flows: List[o.Ref],
    ) -> Optional[o.Ref]:
        """Use LLM to evaluate candidate flows considering Chinese-to-English context."""
        if not candidate_flows or not self.llm_clients:
            return None

        available_llm = "deepseek"
        if available_llm not in self.llm_clients or not self.llm_clients[available_llm]:
            return None

        try:
            candidate_info = []
            for i, flow_ref in enumerate(candidate_flows):
                try:
                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                    candidate_info.append(
                        f"{i+1}. {flow_ref.name} (Category: {flow_obj.category or 'N/A'})"
                    )
                except Exception:
                    candidate_info.append(f"{i+1}. {flow_ref.name}")

            candidate_info_str = "\n".join(candidate_info)
            normalized = normalize_chinese_flow_name(chinese_name)

            prompt = f"""You are an LCA expert matching Chinese industrial flow names to ecoinvent database flows.

Chinese flow name (original): {chinese_name}
Chinese flow name (core noun, modifiers stripped): {normalized}
Translated English name: {english_name}
Flow type: {flow_spec.flow_type}
Unit: {getattr(flow_spec, 'unit', 'unknown')}

Candidate flows from ecoinvent database:
{candidate_info_str}

RULES:
1. Match the SUBSTANCE/MATERIAL, ignoring Chinese adjectives like procurement source, temperature, pressure, grade.
2. "外购电石" means purchased calcium carbide → match "calcium carbide".
3. "5℃水" means water at 5°C → match "water" or "water, cooling".
4. "1.0MPa蒸汽" means steam at 1.0MPa → match "steam, in chemical industry".
5. "工厂空气" means factory air → match "compressed air" or "air".
6. "循环水" means circulating/cooling water → match "water, cooling" or "tap water".
7. Prioritize functional/substance equivalence over exact naming.
8. Return the NUMBER of the best match, or 0 if none are suitable.

Answer (number only):"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=50
            )
            if response:
                match = re.search(r"\b([0-9]+)\b", response)
                if match:
                    choice = int(match.group(1))
                    if 1 <= choice <= len(candidate_flows):
                        return candidate_flows[choice - 1]
                    elif choice == 0:
                        return None

        except Exception as e:
            print(f"⚠️ LLM Chinese flow match evaluation failed: {e}")

        return None

    def get_or_create_flow(
        self, flow_spec: FlowSpec, create_if_missing: bool = True
    ) -> Optional[o.Ref]:
        """Get or create flow with unit standardization and enhanced name matching."""
        flow_name = flow_spec.name

        if not flow_name or len(flow_name.strip()) == 0:
            print(f"❌ Cannot process flow with empty name")
            return None

        canonical_name = self.flow_name_translator.resolve_canonical(
            flow_name, flow_spec.flow_type or ""
        )
        if canonical_name and canonical_name != flow_name:
            print(
                f"🔗 Alias resolved: '{flow_name}' → '{canonical_name}' "
                f"(linking to existing ecoinvent flow)"
            )
            flow_spec.name = canonical_name
            flow_name = canonical_name

        if hasattr(flow_spec, "unit"):
            standardized_unit, _ = self.standardize_unit(flow_spec.unit, 1.0)
        else:
            standardized_unit = "kg"

        desired_type = self._normalize_flow_type(flow_spec.flow_type or "")
        flow_meta = getattr(self, "parsed_flow_metadata", {}).get(flow_name, {})
        force_foreground_flow = bool(
            flow_meta.get("force_foreground_flow")
            or flow_meta.get("has_emission_factor_provider")
        )

        if self._is_excel_lifecycle_flow(flow_name):
            return self._resolve_lifecycle_process_flow(flow_spec, create_if_missing)

        if force_foreground_flow:
            if VERBOSE_OUTPUT:
                print(
                    f"🧷 Flow '{flow_name}' is EF-bound; "
                    f"forcing foreground flow mode (skip translation/database matching)"
                )

            cached_entry = self.created_flows.get(flow_name)
            if cached_entry:
                cached_ref = (
                    cached_entry["ref"]
                    if isinstance(cached_entry, dict)
                    else cached_entry
                )
                return self._ensure_flow_property(cached_ref, flow_spec)

            local_exact = self._find_exact_flow_by_name_and_type(
                flow_name, desired_type
            )
            if local_exact:
                return self._validate_and_cache_flow(flow_name, local_exact, flow_spec)

            if create_if_missing:
                new_flow_ref = self.create_new_flow(flow_spec)
                if new_flow_ref:
                    self.created_flows[flow_name] = {
                        "ref": new_flow_ref,
                        "flow_type": flow_spec.flow_type or "UNKNOWN",
                    }
                return new_flow_ref
            return None

        is_chinese = contains_chinese(flow_name)

        if is_chinese and ENABLE_CHINESE_FLOW_TRANSLATION:

            cached_entry = self.created_flows.get(flow_name)
            if cached_entry:
                cached_ref = (
                    cached_entry["ref"]
                    if isinstance(cached_entry, dict)
                    else cached_entry
                )
                cached_name = getattr(cached_ref, "name", "") or ""
                if not contains_chinese(cached_name):
                    if VERBOSE_OUTPUT:
                        print(
                            f"💾 Using cached English flow for '{flow_name}': '{cached_name}'"
                        )
                    return self._ensure_flow_property(cached_ref, flow_spec)
                else:

                    del self.created_flows[flow_name]
                    print(
                        f"🗑️ Evicted stale Chinese-named cache entry for '{flow_name}' (was '{cached_name}')"
                    )

            normalized_cn = normalize_chinese_flow_name(flow_name)

            if normalized_cn == "解析气":
                existing_cn = self._find_exact_flow_by_name_and_type(
                    flow_name, self._normalize_flow_type(flow_spec.flow_type or "")
                )
                if existing_cn:
                    print(
                        f"✅ Reusing custom Chinese flow for process-specific stream '{flow_name}'"
                    )
                    return self._validate_and_cache_flow(
                        flow_name, existing_cn, flow_spec
                    )
                if create_if_missing:
                    print(
                        f"🔨 Creating custom Chinese flow for '{flow_name}' "
                        f"(forced foreground stream; skip ecoinvent translation/matching)"
                    )
                    new_flow_ref = self.create_new_flow(flow_spec)
                    if new_flow_ref:
                        self.created_flows[flow_name] = {
                            "ref": new_flow_ref,
                            "flow_type": flow_spec.flow_type or "UNKNOWN",
                        }
                    return new_flow_ref
                return None

            print(
                f"🇨🇳 Detected Chinese flow name: '{flow_name}', translating for ecoinvent matching..."
            )

            en_candidates = self.flow_name_translator.get_translation_candidates(
                flow_name, flow_type=flow_spec.flow_type or ""
            )

            if not en_candidates:

                en_single = self.flow_name_translator.translate(flow_name)
                if en_single:
                    en_candidates = [en_single]

            if en_candidates:
                print(f"🔤 Translation candidates for '{flow_name}': {en_candidates}")
                for en_name in en_candidates:
                    result = self._try_match_english_name(en_name, flow_spec, flow_name)
                    if result:
                        return result

                first_en = en_candidates[0]
                cache_key = self.flow_name_translator._normalize_cache_key(flow_name)
                cached_mapping = self.flow_name_translator._cache.get(cache_key)
                existing_first_en = self._find_exact_flow_by_name_and_type(
                    first_en, self._normalize_flow_type(flow_spec.flow_type or "")
                )
                if (
                    normalized_cn != "解析气"
                    and cached_mapping
                    and cached_mapping == first_en
                    and not existing_first_en
                    and create_if_missing
                ):
                    print(
                        f"🔨 Creating custom flow '{first_en}' for '{flow_name}' "
                        f"(cached mapping, no ecoinvent match)"
                    )
                    custom_spec = FlowSpec(
                        name=first_en,
                        flow_type=flow_spec.flow_type or "PRODUCT_FLOW",
                        category=flow_spec.category or "",
                    )
                    new_flow_ref = self.create_new_flow(custom_spec)
                    if new_flow_ref:
                        self.created_flows[flow_name] = {
                            "ref": new_flow_ref,
                            "flow_type": flow_spec.flow_type or "UNKNOWN",
                        }
                    return new_flow_ref

                if normalized_cn == "解析气":
                    existing_cn = self._find_exact_flow_by_name_and_type(
                        flow_name, self._normalize_flow_type(flow_spec.flow_type or "")
                    )
                    if existing_cn:
                        print(
                            f"✅ Reusing custom Chinese flow for process-specific stream '{flow_name}'"
                        )
                        return self._validate_and_cache_flow(
                            flow_name, existing_cn, flow_spec
                        )
                    if create_if_missing:
                        print(
                            f"🔨 Creating custom Chinese flow for '{flow_name}' "
                            f"(no reliable ecoinvent candidate; skip fuzzy fallback)"
                        )
                        new_flow_ref = self.create_new_flow(flow_spec)
                        if new_flow_ref:
                            self.created_flows[flow_name] = {
                                "ref": new_flow_ref,
                                "flow_type": flow_spec.flow_type or "UNKNOWN",
                            }
                        return new_flow_ref

            if CHINESE_FLOW_LLM_EVALUATION:
                broader_matches = self.find_similar_flows(
                    en_candidates[0] if en_candidates else flow_name,
                    flow_spec.category,
                    similarity_threshold=0.4,
                )
                if broader_matches:
                    candidate_refs = [ref for ref, _ in broader_matches[:10]]
                    best = self._llm_evaluate_chinese_flow_match(
                        flow_name,
                        en_candidates[0] if en_candidates else flow_name,
                        flow_spec,
                        candidate_refs,
                    )
                    if best:
                        print(
                            f"🤖 Broader search matched Chinese flow '{flow_name}' → '{best.name}'"
                        )
                        self.flow_name_translator.add_mapping(flow_name, best.name)
                        return self._validate_and_cache_flow(flow_name, best, flow_spec)

            fallback_match = self._find_exact_flow_by_name_and_type(
                flow_name, self._normalize_flow_type(flow_spec.flow_type or "")
            )
            if fallback_match:
                print(
                    f"⚠️ Translation failed for '{flow_name}'; reusing existing Chinese-named flow in database"
                )
                return self._validate_and_cache_flow(
                    flow_name, fallback_match, flow_spec
                )

            if create_if_missing:
                print(
                    f"🔨 Creating new flow with Chinese name (no ecoinvent match): '{flow_name}'"
                )
                new_flow_ref = self.create_new_flow(flow_spec)
                if new_flow_ref:
                    self.created_flows[flow_name] = {
                        "ref": new_flow_ref,
                        "flow_type": flow_spec.flow_type or "UNKNOWN",
                    }
                return new_flow_ref
            else:
                print(
                    f"⚠️ Flow not found '{flow_name}' and creation of new flows is not allowed"
                )
                return None

        cached_entry = self.created_flows.get(flow_name)
        if cached_entry:
            cached_ref = (
                cached_entry["ref"] if isinstance(cached_entry, dict) else cached_entry
            )
            cached_flow_type = (
                cached_entry.get("flow_type")
                if isinstance(cached_entry, dict)
                else None
            )

            if (
                cached_flow_type
                and flow_spec.flow_type
                and cached_flow_type != flow_spec.flow_type
            ):
                print(
                    f"⚠️ Cached flow '{flow_name}' has type {cached_flow_type}, expected {flow_spec.flow_type} - verifying in database"
                )
                updated_ref = self._ensure_flow_type(cached_ref, flow_spec)
                updated_ref = self._ensure_flow_property(updated_ref, flow_spec)
                stored_type = (
                    self._determine_flow_type(updated_ref)
                    or flow_spec.flow_type
                    or "UNKNOWN"
                )
                self.created_flows[flow_name] = {
                    "ref": updated_ref,
                    "flow_type": stored_type,
                }
                if desired_type and stored_type and stored_type != desired_type:
                    print(
                        f"⚠️ Cached flow '{flow_name}' still type-mismatched after validation "
                        f"(actual: {stored_type}, desired: {desired_type}); ignoring cache"
                    )
                    del self.created_flows[flow_name]
                else:
                    return updated_ref

            if VERBOSE_OUTPUT:
                print(f"💾 Using cached flow: '{flow_name}' - checking FlowProperty...")
            validated_ref = self._ensure_flow_property(cached_ref, flow_spec)
            return validated_ref

        if flow_spec.flow_type == "ELEMENTARY_FLOW":
            override_name = ELEMENTARY_EMISSION_OVERRIDES.get(flow_name.lower().strip())
            if override_name:
                override_match = self.client.find(o.Flow, override_name)
                if override_match:
                    print(
                        f"✅ Emission override: '{flow_name}' → '{override_name}' (elementary flow)"
                    )
                    return self._validate_and_cache_flow(
                        flow_name, override_match, flow_spec
                    )

        exact_match = self._find_exact_flow_by_name_and_type(flow_name, desired_type)
        if exact_match:
            print(f"✅ Found exact matching flow in database: '{flow_name}'")
            return self._validate_and_cache_flow(flow_name, exact_match, flow_spec)

        if VERBOSE_OUTPUT:
            print(f"🔍 Checking for semantic matches and synonyms: '{flow_name}'")
        semantic_matches = self.find_similar_flows(
            flow_name, flow_spec.category, similarity_threshold=0.8
        )
        if desired_type:
            filtered_matches = []
            for ref, sim in semantic_matches:
                if self._determine_flow_type(ref) == desired_type:
                    filtered_matches.append((ref, sim))
            if filtered_matches:
                semantic_matches = filtered_matches
            elif semantic_matches:
                print(
                    f"⚠️ Semantic candidates found for '{flow_name}', but none match "
                    f"required flow type {desired_type}; will create new flow if needed"
                )
                semantic_matches = []

        if semantic_matches:
            if VERBOSE_OUTPUT:
                print(f"📋 Found {len(semantic_matches)} potential semantic matches")
            candidate_refs = [ref for ref, sim in semantic_matches[:5]]

            best_match = self.llm_evaluate_flow_match_strict(flow_spec, candidate_refs)
            if best_match:
                print(
                    f"🤖 LLM identified semantic match: '{best_match.name}' for target: '{flow_name}'"
                )
                return self._validate_and_cache_flow(flow_name, best_match, flow_spec)

            high_similarity_flows = [
                (ref, sim) for ref, sim in semantic_matches if sim >= 0.95
            ]
            if high_similarity_flows:
                best_ref, best_sim = high_similarity_flows[0]
                print(
                    f"✅ Using highly similar flow ({best_sim:.1%}): '{best_ref.name}' for target: '{flow_name}'"
                )
                return self._validate_and_cache_flow(flow_name, best_ref, flow_spec)

        if create_if_missing:
            print(f"🔨 Creating new flow: '{flow_name}' (no match found in database)")
            new_flow_ref = self.create_new_flow(flow_spec)
            if new_flow_ref:
                print(f"✅ Created new flow: '{new_flow_ref.name}'")
                if new_flow_ref.name != flow_name:
                    print(
                        f"⚠️ WARNING: Created flow name mismatch! Expected: '{flow_name}', Got: '{new_flow_ref.name}'"
                    )
                self.created_flows[flow_name] = {
                    "ref": new_flow_ref,
                    "flow_type": flow_spec.flow_type or "UNKNOWN",
                }
            return new_flow_ref
        else:
            print(
                f"⚠️ Flow not found '{flow_name}' and creation of new flows is not allowed"
            )
            return None

    def get_flow_property_for_unit(self, unit: str) -> Optional[o.Ref]:

        unit_lower = unit.lower().strip()

        if self._is_count_unit(unit):
            prop_ref = self._find_flow_property_by_candidates(
                self._flow_property_candidates["count"]
            )
            if not prop_ref:
                print(
                    f"❌ Cannot find count FlowProperty for unit '{unit}' "
                    f"(tried: {self._flow_property_candidates['count']})"
                )
            return prop_ref

        if self._is_compound_or_transport_unit(unit):
            prop_ref = self._find_flow_property_by_candidates(
                self._flow_property_candidates["transport"]
            )
            if not prop_ref:
                print(
                    f"❌ Cannot find transport FlowProperty for unit '{unit}' "
                    f"(tried: {self._flow_property_candidates['transport']})"
                )
            return prop_ref

        unit_property_map = {
            "kg": "mass",
            "g": "mass",
            "mg": "mass",
            "t": "mass",
            "ton": "mass",
            "tons": "mass",
            "tonne": "mass",
            "tonnes": "mass",
            "lb": "mass",
            "mj": "energy",
            "kj": "energy",
            "gj": "energy",
            "j": "energy",
            "kwh": "energy",
            "wh": "energy",
            "m3": "volume",
            "m³": "volume",
            "l": "volume",
            "ml": "volume",
            "dm3": "volume",
            "cm3": "volume",
            "m2": "area",
            "m²": "area",
            "ha": "area",
            "km2": "area",
            "km²": "area",
            "m": "length",
            "km": "length",
            "cm": "length",
            "mm": "length",
        }

        property_category = unit_property_map.get(unit_lower)
        if property_category:
            return self._find_flow_property_by_candidates(
                self._flow_property_candidates[property_category]
            )

        print(
            f"⚠️ Unknown unit '{unit}', cannot determine FlowProperty (no Mass fallback)"
        )
        return None

    def create_new_flow(self, flow_spec: FlowSpec) -> o.Ref:
        """Create new flow with unit standardization for all cases"""
        try:
            if not flow_spec.name or len(flow_spec.name.strip()) == 0:
                raise ValueError("Cannot create flow with empty name")

            print(f"🔨 Creating new flow: '{flow_spec.name}'")

            if hasattr(flow_spec, "unit"):
                standardized_unit, _ = self.standardize_unit(flow_spec.unit, 1.0)
                print(f"📏 Using standardized unit: {standardized_unit}")
            else:
                standardized_unit = "kg"
                print(f"📏 Using default unit: {standardized_unit}")

            prop_ref = self.get_flow_property_for_unit(standardized_unit)
            if not prop_ref:
                raise ValueError(
                    f"Cannot find appropriate flow property for unit '{standardized_unit}'"
                )

            flow = o.Flow()
            flow.id = str(uuid.uuid4())
            flow.name = flow_spec.name
            flow.category = flow_spec.category
            flow.description = (
                flow_spec.description or f"Auto-generated flow: {flow_spec.name}"
            )

            if flow_spec.cas:
                flow.cas = flow_spec.cas
            if flow_spec.formula:
                flow.formula = flow_spec.formula
            if flow_spec.synonyms:
                flow.synonyms = flow_spec.synonyms
            flow.is_infrastructure_flow = flow_spec.is_infrastructure_flow

            resolved_flow_type = flow_spec.flow_type
            if not resolved_flow_type or resolved_flow_type not in {
                "PRODUCT_FLOW",
                "ELEMENTARY_FLOW",
                "WASTE_FLOW",
            }:
                print(
                    f"Warning: Invalid or missing flow type '{flow_spec.flow_type}' for '{flow_spec.name}', defaulting to PRODUCT_FLOW"
                )
                resolved_flow_type = "PRODUCT_FLOW"

            flow.flow_type = getattr(o.FlowType, resolved_flow_type)
            print(f"Setting flow type for '{flow_spec.name}': {resolved_flow_type}")

            flow.reference_flow_property = prop_ref

            factor = o.FlowPropertyFactor()
            factor.conversion_factor = 1.0
            factor.is_ref_flow_property = True
            factor.flow_property = prop_ref
            flow.flow_properties = [factor]

            self.client.put(flow)

            flow_ref = o.Ref()
            flow_ref.id = flow.id
            flow_ref.name = flow.name

            self.created_flows[flow_spec.name] = flow_ref

            print(
                f"✅ Successfully created flow with complete name: '{flow_spec.name}'"
            )
            return flow_ref

        except Exception as e:
            print(f"❌ Failed to create flow '{flow_spec.name}': {e}")
            raise

    def get_unit_ref(self, unit_group_name: str, unit_name: str) -> Optional[o.Ref]:

        try:
            unit_groups = self.client.get_all(o.UnitGroup)
            for group in unit_groups:
                if group.name == unit_group_name:
                    if group.units:
                        for unit in group.units:
                            if unit.name == unit_name:
                                ref = o.Ref()
                                ref.id = unit.id
                                ref.name = unit.name
                                return ref
            return None
        except Exception as e:
            print(f"❌ Failed to get unit reference: {e}")
            return None

    def get_available_units_for_flow(
        self, flow_ref: o.Ref
    ) -> Dict[str, List[Dict[str, str]]]:

        try:
            flow_obj = self.client.get(o.Flow, flow_ref.id)
            if not flow_obj or not flow_obj.flow_properties:
                return {}

            result = {}
            for fp in flow_obj.flow_properties:
                prop_obj = self.client.get(o.FlowProperty, fp.flow_property.id)
                if prop_obj and prop_obj.unit_group:
                    unit_group_obj = self.client.get(
                        o.UnitGroup, prop_obj.unit_group.id
                    )
                    if unit_group_obj and unit_group_obj.units:
                        unit_list = []
                        for unit in unit_group_obj.units:
                            unit_list.append(
                                {
                                    "id": str(unit.id) if hasattr(unit, "id") else "",
                                    "name": unit.name,
                                    "conversion_factor": (
                                        unit.conversion_factor
                                        if hasattr(unit, "conversion_factor")
                                        else 1.0
                                    ),
                                    "is_ref_unit": (
                                        unit.is_ref_unit
                                        if hasattr(unit, "is_ref_unit")
                                        else False
                                    ),
                                }
                            )
                        result[unit_group_obj.name] = unit_list

            return result
        except Exception as e:
            print(f"❌ Error getting available units for flow: {e}")
            return {}

    def list_all_unit_groups(self) -> Dict[str, List[Dict[str, Any]]]:

        try:
            all_unit_groups = {}
            unit_groups = self.client.get_all(o.UnitGroup)

            for group in unit_groups:
                units_in_group = []
                if group.units:
                    for unit in group.units:
                        units_in_group.append(
                            {
                                "id": str(unit.id) if hasattr(unit, "id") else "",
                                "name": unit.name,
                                "conversion_factor": (
                                    unit.conversion_factor
                                    if hasattr(unit, "conversion_factor")
                                    else 1.0
                                ),
                                "is_ref_unit": (
                                    unit.is_ref_unit
                                    if hasattr(unit, "is_ref_unit")
                                    else False
                                ),
                                "synonyms": (
                                    unit.synonyms if hasattr(unit, "synonyms") else ""
                                ),
                            }
                        )
                all_unit_groups[group.name] = units_in_group

            print(f"📊 Found {len(all_unit_groups)} unit groups")
            return all_unit_groups
        except Exception as e:
            print(f"❌ Error listing unit groups: {e}")
            return {}

    def create_process(
        self, process_spec: ProcessSpec, flows_created: Dict[str, o.Ref]
    ) -> o.Ref:
        """Created processes"""
        try:

            import datetime

            actual_process_name = process_spec.name
            existing_process = self.client.find(o.Process, process_spec.name)
            if existing_process:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                actual_process_name = f"{process_spec.name}_{timestamp}"
                print(
                    f"⚠️ Process '{process_spec.name}' already exists (keeping it intact for previous product systems)"
                )
                print(
                    f"📝 Creating new process with unique name: {actual_process_name}"
                )

            process = o.Process()
            process.id = str(uuid.uuid4())
            process.name = actual_process_name
            process.category = process_spec.category
            process.description = process_spec.description

            if process_spec.process_type == "LCI_RESULT":
                process.process_type = o.ProcessType.LCI_RESULT
            else:
                process.process_type = o.ProcessType.UNIT_PROCESS

            if hasattr(process_spec, "location") and process_spec.location:

                pass

            if hasattr(process_spec, "last_internal_id"):
                process.last_internal_id = process_spec.last_internal_id
            else:
                process.last_internal_id = 0

            simple_exchanges = []
            if hasattr(process_spec, "_simple_exchanges"):
                simple_exchanges = process_spec._simple_exchanges
            elif hasattr(process_spec, "exchanges") and process_spec.exchanges:

                for ex in process_spec.exchanges:
                    if hasattr(ex, "flow_name"):
                        simple_exchanges.append(ex)
                    else:
                        simple_ex = SimpleExchange(
                            flow_name=ex.flow.name if ex.flow else "",
                            amount=ex.amount,
                            is_input=ex.is_input,
                            is_quantitative_reference=ex.is_quantitative_reference,
                            unit="kg",
                        )
                        simple_exchanges.append(simple_ex)

            _process_inferred_location = ""
            if self.project_context and self.project_context.system_boundary:
                _sys_desc_for_loc = (
                    self.project_context.system_boundary.description or ""
                )
                if _sys_desc_for_loc:
                    if self.enable_lifecycle_stage_classification:
                        from .uncertainty import (
                            llm_extract_stage_geography_mapping,
                            resolve_process_geography,
                            _extract_process_specific_geography,
                        )

                        if self._stage_geography_cache is None:
                            print(
                                f"🌍 LLM地理映射尚未初始化，在create_process中补充调用..."
                            )
                            self._stage_geography_cache = (
                                llm_extract_stage_geography_mapping(
                                    _sys_desc_for_loc,
                                    self.llm_clients,
                                    [process_spec.name],
                                )
                                or {}
                            )

                        if self._stage_geography_cache:
                            _process_inferred_location = resolve_process_geography(
                                process_spec.name, self._stage_geography_cache
                            )

                        if not _process_inferred_location:
                            _process_inferred_location = (
                                _extract_process_specific_geography(
                                    _sys_desc_for_loc, process_spec.name
                                )
                                or ""
                            )
                    else:
                        from .uncertainty import _get_expected_location_codes

                        global_codes = _get_expected_location_codes(
                            _sys_desc_for_loc, ""
                        )
                        if global_codes:
                            _process_inferred_location = global_codes[0]
                        print(
                            f"🧪 [no_stage_classification] 过程 '{process_spec.name}' "
                            f"使用全局地理推断: {_process_inferred_location or 'GLO'}"
                        )

                    if _process_inferred_location:
                        print(
                            f"📍 过程 '{process_spec.name}' 推断地理位置: {_process_inferred_location}"
                        )

            if not _process_inferred_location:
                _process_inferred_location = "CN"
                print(
                    f"📍 过程 '{process_spec.name}' 未识别到具体地区信息，默认使用中国地区: CN"
                )

            exchange_internal_id = 1
            for exchange_spec in simple_exchanges:
                flow_name = exchange_spec.flow_name
                flow_ref = flows_created.get(flow_name)

                if not flow_ref:
                    print(
                        f"❌ In process '{process_spec.name}' cannot find flow '{flow_name}'"
                    )
                    continue

                exchange_unit, exchange_amount = self.standardize_unit(
                    exchange_spec.unit, exchange_spec.amount
                )
                print(
                    f"📏 Exchange {flow_name}: {exchange_amount} {exchange_unit} "
                    f"(from Excel: {exchange_spec.amount} {exchange_spec.unit})"
                )

                is_avoided_check = (
                    hasattr(exchange_spec, "is_avoided_product")
                    and exchange_spec.is_avoided_product
                )
                print(f"🔍 DEBUG create_process: Flow '{flow_name}':")
                print(f"   - exchange_spec.is_input: {exchange_spec.is_input}")
                print(f"   - exchange_spec.is_avoided_product: {is_avoided_check}")

                if exchange_spec.is_input:
                    exchange = o.new_input(process, flow_ref, exchange_amount)
                    if is_avoided_check:
                        print(
                            f"   ✅ Created as INPUT (avoided product - UI will show as OUTPUT)"
                        )
                    else:
                        print(f"   ✅ Created as INPUT")

                    if not is_avoided_check:
                        _in_ftype = ""
                        _in_cached = self.created_flows.get(exchange_spec.flow_name)
                        if isinstance(_in_cached, dict):
                            _in_ftype = (_in_cached.get("flow_type") or "").upper()
                            if not _in_ftype:
                                _in_ref = _in_cached.get("ref")
                                if _in_ref is not None:
                                    _in_ftype = self._determine_flow_type(_in_ref) or ""
                        elif _in_cached is not None:
                            _in_ftype = self._determine_flow_type(_in_cached) or ""

                        if _in_ftype == "WASTE_FLOW":
                            _consumers = self.excel_waste_consumers.setdefault(
                                exchange_spec.flow_name, []
                            )
                            if process_spec.name not in _consumers:
                                _consumers.append(process_spec.name)
                                print(
                                    f"   ♻️  Registered '{process_spec.name}' as Excel-defined "
                                    f"treater (waste consumer) for '{flow_name}'"
                                )
                else:
                    exchange = o.new_output(process, flow_ref, exchange_amount)
                    print(f"   ✅ Created as OUTPUT")

                    _resolved_ftype = ""
                    _cached_flow = self.created_flows.get(exchange_spec.flow_name)
                    if isinstance(_cached_flow, dict):
                        _resolved_ftype = (_cached_flow.get("flow_type") or "").upper()
                        if not _resolved_ftype:
                            _ref_obj = _cached_flow.get("ref")
                            if _ref_obj is not None:
                                _resolved_ftype = (
                                    self._determine_flow_type(_ref_obj) or ""
                                )
                    elif _cached_flow is not None:
                        _resolved_ftype = self._determine_flow_type(_cached_flow) or ""

                    if _resolved_ftype != "WASTE_FLOW":
                        self.excel_flow_providers[exchange_spec.flow_name] = {
                            "provider_name": process_spec.name,
                            "explicit": False,
                        }
                        print(f"   📝 Registered as output provider for '{flow_name}'")
                    else:
                        print(
                            f"   ⏭️  Skipped output-provider registration for WASTE flow '{flow_name}' "
                            f"(treater will be assigned via waste_flow_linking)"
                        )

                print(f"   - exchange.is_input after creation: {exchange.is_input}")

                exchange.internal_id = exchange_internal_id
                exchange_internal_id += 1

                try:
                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                    if flow_obj and flow_obj.flow_properties:

                        correct_prop_ref = self.get_flow_property_for_unit(
                            exchange_unit
                        )

                        target_prop_factor = None
                        if correct_prop_ref:
                            for fp in flow_obj.flow_properties:
                                if fp.flow_property.id == correct_prop_ref.id:
                                    target_prop_factor = fp
                                    print(
                                        f"🎯 Using correct FlowProperty '{correct_prop_ref.name}' for unit '{exchange_unit}'"
                                    )
                                    break

                        if not target_prop_factor and correct_prop_ref:
                            if self._is_count_unit(
                                exchange_unit
                            ) or self._is_compound_or_transport_unit(exchange_unit):
                                new_factor = o.FlowPropertyFactor()
                                new_factor.conversion_factor = 1.0
                                new_factor.is_ref_flow_property = False
                                new_factor.flow_property = correct_prop_ref
                                flow_obj.flow_properties.append(new_factor)
                                self.client.put(flow_obj)
                                target_prop_factor = new_factor
                                print(
                                    f"➕ Added FlowProperty '{correct_prop_ref.name}' to flow "
                                    f"'{flow_obj.name}' for unit '{exchange_unit}'"
                                )
                            else:
                                target_prop_factor = next(
                                    (
                                        fp
                                        for fp in flow_obj.flow_properties
                                        if fp.is_ref_flow_property
                                    ),
                                    None,
                                )
                                if target_prop_factor:
                                    print(
                                        f"⚠️ Unit '{exchange_unit}' - using default ref property "
                                        f"'{target_prop_factor.flow_property.name}' as fallback"
                                    )
                        elif not target_prop_factor:
                            target_prop_factor = next(
                                (
                                    fp
                                    for fp in flow_obj.flow_properties
                                    if fp.is_ref_flow_property
                                ),
                                None,
                            )
                            if target_prop_factor:
                                print(
                                    f"⚠️ Unit '{exchange_unit}' - using default ref property "
                                    f"'{target_prop_factor.flow_property.name}' as fallback"
                                )

                        if target_prop_factor:
                            exchange.flow_property = target_prop_factor.flow_property

                            prop_obj = self.client.get(
                                o.FlowProperty, target_prop_factor.flow_property.id
                            )
                            if prop_obj and prop_obj.unit_group:
                                unit_group_obj = self.client.get(
                                    o.UnitGroup, prop_obj.unit_group.id
                                )
                                if unit_group_obj and unit_group_obj.units:
                                    unit_for_matching = exchange_unit
                                    matching_unit = self._find_matching_unit_in_group(
                                        unit_group_obj,
                                        unit_for_matching,
                                    )
                                    if matching_unit:
                                        exchange.unit = matching_unit
                                        print(
                                            f"📏 Set exchange unit to: '{matching_unit.name}' "
                                            f"(from Excel: '{exchange_spec.unit}')"
                                        )
                                    elif self._is_count_unit(
                                        unit_for_matching
                                    ) or self._is_compound_or_transport_unit(
                                        unit_for_matching
                                    ):
                                        print(
                                            f"❌ Could not resolve unit '{unit_for_matching}' in "
                                            f"'{prop_obj.name}' unit group; refusing kg/Mass fallback"
                                        )
                                    else:
                                        ref_unit = next(
                                            (
                                                u
                                                for u in unit_group_obj.units
                                                if u.is_ref_unit
                                            ),
                                            None,
                                        )
                                        if ref_unit:
                                            if (
                                                unit_for_matching
                                                and unit_for_matching.lower()
                                                != ref_unit.name.lower().strip()
                                            ):
                                                exchange.amount = (
                                                    self._convert_amount_in_unit_group(
                                                        exchange_amount,
                                                        unit_for_matching,
                                                        ref_unit,
                                                        unit_group_obj,
                                                    )
                                                )
                                                print(
                                                    f"🔄 Converted exchange amount for unit fallback: "
                                                    f"{exchange_amount} {unit_for_matching} -> "
                                                    f"{exchange.amount} {ref_unit.name}"
                                                )
                                            exchange.unit = ref_unit
                                            print(
                                                f"⚠️ Could not find unit '{unit_for_matching}' in unit "
                                                f"group, using reference unit: '{ref_unit.name}'"
                                            )
                except Exception as e:
                    print(f"⚠️ Error setting exchange properties: {e}")

                if exchange_spec.is_quantitative_reference:
                    exchange.is_quantitative_reference = True
                    process.quantitative_reference = exchange

                if (
                    hasattr(exchange_spec, "is_avoided_product")
                    and exchange_spec.is_avoided_product
                ):
                    exchange.is_avoided_product = True
                    print(
                        f"🔄 Set '{flow_name}' as avoided product (system expansion enabled)"
                    )
                    print(
                        f"   Data model: is_input={exchange.is_input}, is_avoided_product={exchange.is_avoided_product}"
                    )
                    print(
                        f"   UI display: Will show in OUTPUTS section with 'Avoided product' checked"
                    )

                if (not exchange_spec.is_input) and (
                    not (
                        hasattr(exchange_spec, "is_avoided_product")
                        and exchange_spec.is_avoided_product
                    )
                ):
                    explicit_output_info = self._get_registered_explicit_provider_info(
                        process_context=process_spec.name,
                        flow_name=exchange_spec.flow_name,
                        direction="explicit_output",
                    )
                    explicit_output_provider_name = (
                        exchange_spec.provider_name or ""
                    ).strip()
                    if explicit_output_info and explicit_output_info.get(
                        "provider_name"
                    ):
                        explicit_output_provider_name = explicit_output_info[
                            "provider_name"
                        ]

                    if explicit_output_provider_name:
                        explicit_output_provider = self.created_processes.get(
                            explicit_output_provider_name
                        )
                        if explicit_output_provider:
                            exchange.default_provider = explicit_output_provider
                            print(
                                f"   ↪️ Linked explicit output '{flow_name}' "
                                f"to consumer provider: {explicit_output_provider.name}"
                            )
                        else:
                            self.pending_output_provider_links.append(
                                {
                                    "producer_name": process_spec.name,
                                    "provider_name": explicit_output_provider_name,
                                    "flow_name": exchange_spec.flow_name,
                                    "exchange_internal_id": exchange.internal_id,
                                }
                            )
                            print(
                                f"   🕓 Deferred explicit output link '{flow_name}' -> "
                                f"'{explicit_output_provider_name}' (provider not created yet)"
                            )

                needs_provider = exchange_spec.is_input or (
                    hasattr(exchange_spec, "is_avoided_product")
                    and exchange_spec.is_avoided_product
                )

                if needs_provider:
                    exchange_location = getattr(exchange_spec, "location", "") or ""
                    if not exchange_location and _process_inferred_location:
                        exchange_location = _process_inferred_location
                    provider, cv_results = self.find_provider_for_flow(
                        flow_ref,
                        process_spec.name,
                        exchange_spec.provider_name,
                        desired_location=exchange_location,
                        excel_flow_name=exchange_spec.flow_name,
                        requested_amount=exchange_amount,
                    )
                    if provider:
                        exchange.default_provider = provider

                        if exchange_spec.is_input:
                            print(
                                f"   ↪️ Linked input '{flow_name}' to provider: {provider.name}"
                            )
                        elif (
                            hasattr(exchange_spec, "is_avoided_product")
                            and exchange_spec.is_avoided_product
                        ):
                            print(
                                f"   ↪️ Linked avoided product '{flow_name}' to substituted provider: {provider.name}"
                            )

                        try:
                            from .config import APPLY_CUSTOM_UNCERTAINTY_TO_EXCHANGES

                            apply_custom_unc = APPLY_CUSTOM_UNCERTAINTY_TO_EXCHANGES
                        except ImportError:
                            apply_custom_unc = True

                        if (
                            self.uncertainty_enabled
                            and cv_results
                            and "selected_provider" in cv_results
                            and apply_custom_unc
                        ):
                            cv_value = cv_results["selected_provider"]["total_cv"]
                            if cv_value > 0:
                                try:
                                    from .config import UNCERTAINTY_DISTRIBUTION_TYPE

                                    dist_type = UNCERTAINTY_DISTRIBUTION_TYPE
                                except ImportError:
                                    dist_type = "LOG_NORMAL"
                                uncertainty = create_uncertainty_from_cv(
                                    cv_value, exchange.amount, dist_type
                                )
                                exchange.uncertainty = uncertainty

                                from .config import DISPLAY_UNCERTAINTY_DETAILS

                                if DISPLAY_UNCERTAINTY_DETAILS:

                                    if (
                                        uncertainty.distribution_type
                                        == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
                                    ):
                                        print(
                                            f"    🎲 Applied LOG_NORMAL uncertainty to {exchange_spec.flow_name}: CV={cv_value*100:.1f}%, geom_mean={uncertainty.geom_mean:.3f}, geom_sd={uncertainty.geom_sd:.3f}"
                                        )
                                    else:
                                        print(
                                            f"    🎲 Applied NORMAL uncertainty to {exchange_spec.flow_name}: CV={cv_value*100:.1f}%, mean={uncertainty.mean:.3f}, sd={uncertainty.sd:.3f}"
                                        )

                                exchange_key = (
                                    f"{process_spec.name}_{exchange_spec.flow_name}"
                                )
                                self.provider_cv_results[exchange_key] = cv_results
                        elif (
                            not apply_custom_unc
                            and cv_results
                            and "selected_provider" in cv_results
                        ):
                            print(
                                f"    ⚠️ Custom uncertainty DISABLED for '{flow_name}' (APPLY_CUSTOM_UNCERTAINTY_TO_EXCHANGES=False)"
                            )

            self._apply_allocation_to_process(process, simple_exchanges)

            print(
                f"\n📋 Final check before saving process '{process_spec.name}' to openLCA:"
            )
            uncertainty_count = 0
            for ex in process.exchanges:
                flow_name = ex.flow.name if ex.flow else "Unknown"
                is_avoided = getattr(ex, "is_avoided_product", False)
                has_uncertainty = ex.uncertainty is not None
                if has_uncertainty:
                    uncertainty_count += 1
                print(f"  • {flow_name}:")
                print(f"    - is_input: {ex.is_input}")
                print(f"    - is_avoided_product: {is_avoided}")
                print(f"    - amount: {ex.amount}")
                if has_uncertainty:
                    unc = ex.uncertainty
                    if (
                        unc.distribution_type
                        == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
                    ):
                        print(
                            f"    - uncertainty: LOG_NORMAL(geom_mean={unc.geom_mean}, geom_sd={unc.geom_sd})"
                        )
                    elif unc.distribution_type == o.UncertaintyType.NORMAL_DISTRIBUTION:
                        print(
                            f"    - uncertainty: NORMAL(mean={unc.mean}, sd={unc.sd})"
                        )
                    else:
                        print(f"    - uncertainty: {unc.distribution_type}")
            print(
                f"  📊 Total exchanges with uncertainty: {uncertainty_count}/{len(process.exchanges)}"
            )

            self.client.put(process)
            print(f"💾 Process saved to openLCA")

            try:
                in_memory_factors = len(
                    getattr(process, "allocation_factors", None) or []
                )
                if in_memory_factors > 0:
                    saved_alloc_proc = self.client.get(o.Process, process.id)
                    saved_factors = (
                        getattr(saved_alloc_proc, "allocation_factors", None) or []
                    )
                    saved_method = getattr(
                        saved_alloc_proc, "default_allocation_method", None
                    )
                    method_label = (
                        str(saved_method).split(".")[-1] if saved_method else "NONE"
                    )
                    print(
                        f"🔍 Allocation persistence check: in-memory={in_memory_factors}, "
                        f"persisted={len(saved_factors)}, default_method={method_label}"
                    )
                    if len(saved_factors) != in_memory_factors:
                        print(
                            f"⚠️  Allocation factor count mismatch after save — "
                            f"openLCA UI may still show empty allocation table."
                        )
            except Exception as _alloc_check_err:
                print(
                    f"⚠️  Could not verify allocation factors after save: {_alloc_check_err}"
                )

            if uncertainty_count > 0:
                try:
                    saved_process = self.client.get(o.Process, process.id)
                    if saved_process and saved_process.exchanges:
                        print(f"🔍 Verifying saved uncertainty parameters:")
                        verified_count = 0
                        for ex in saved_process.exchanges:
                            if ex.uncertainty:
                                verified_count += 1
                                flow_name = ex.flow.name if ex.flow else "Unknown"
                                unc = ex.uncertainty
                                if (
                                    unc.distribution_type
                                    == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
                                ):
                                    print(
                                        f"   ✅ {flow_name}: LOG_NORMAL(geom_mean={unc.geom_mean}, geom_sd={unc.geom_sd})"
                                    )
                                elif (
                                    unc.distribution_type
                                    == o.UncertaintyType.NORMAL_DISTRIBUTION
                                ):
                                    print(
                                        f"   ✅ {flow_name}: NORMAL(mean={unc.mean}, sd={unc.sd})"
                                    )
                        if verified_count != uncertainty_count:
                            print(
                                f"   ⚠️ WARNING: Only {verified_count}/{uncertainty_count} exchanges have uncertainty after save!"
                            )
                        else:
                            print(
                                f"   ✅ All {verified_count} uncertainty parameters verified"
                            )
                except Exception as e:
                    print(f"   ⚠️ Could not verify saved uncertainty: {e}")

            process_ref = o.Ref()
            process_ref.id = process.id
            process_ref.name = process.name

            self.created_processes[process_spec.name] = process_ref

            print(f"✅ Successfully created process: {process_spec.name}")
            return process_ref

        except Exception as e:
            print(f"❌ Failed to create process '{process_spec.name}': {e}")
            raise

    def _resolve_allocation_method_from_context(self, config_method: str) -> str:
        """Resolve allocation method using project context text hints."""
        try:
            basis = (
                (getattr(self.project_context, "allocation_basis", "") or "")
                .strip()
                .lower()
            )
            procedure = (
                (getattr(self.project_context, "allocation_procedure", "") or "")
                .strip()
                .lower()
            )
            text = f"{basis} {procedure}".strip()
            if not text:

                if config_method == "NONE":
                    return "PHYSICAL"
                return config_method

            no_alloc_keywords = [
                "none",
                "no allocation",
                "不分配",
                "无分配",
                "系统扩展",
                "system expansion",
                "substitution",
                "替代法",
            ]
            economic_keywords = [
                "economic",
                "price",
                "market",
                "revenue",
                "货币",
                "经济",
                "价格",
                "收益",
                "value",
                "价值",
            ]
            causal_keywords = [
                "causal",
                "cause",
                "因果",
                "归因",
            ]
            physical_keywords = [
                "physical",
                "mass",
                "energy",
                "weight",
                "volume",
                "物理",
                "质量",
                "能量",
                "重量",
                "体积",
            ]

            if any(k in text for k in no_alloc_keywords):
                return "NONE"
            if any(k in text for k in economic_keywords):
                return "ECONOMIC"
            if any(k in text for k in causal_keywords):
                return "CAUSAL"
            if any(k in text for k in physical_keywords):
                return "PHYSICAL"
            return config_method
        except Exception:
            return config_method

    def _apply_allocation_to_process(self, process: o.Process, simple_exchanges: List):
        """Replicate openLCA's "Calculate factors" button programmatically."""
        try:

            def _resolved_flow_type(flow_name: str) -> str:
                cached = self.created_flows.get(flow_name)
                if isinstance(cached, dict):
                    ftype = (cached.get("flow_type") or "").upper()
                    if ftype:
                        return ftype
                    ref = cached.get("ref")
                else:
                    ref = cached
                if ref and getattr(ref, "id", None):
                    try:
                        flow_obj = self.client.get(o.Flow, ref.id)
                        return self._normalize_flow_type(
                            getattr(flow_obj, "flow_type", "")
                        )
                    except Exception:
                        return ""
                return ""

            def _is_coproduct(sex) -> bool:
                if sex.is_input:
                    return False
                if getattr(sex, "is_avoided_product", False):
                    return False
                ftype = _resolved_flow_type(sex.flow_name)

                return ftype in ("", "PRODUCT_FLOW")

            output_products = [ex for ex in simple_exchanges if _is_coproduct(ex)]
            coproduct_flow_ids: set = set()
            for sex in output_products:
                ref = self.created_flows.get(sex.flow_name)
                if isinstance(ref, dict):
                    ref = ref.get("ref")
                if ref is not None and getattr(ref, "id", None):
                    coproduct_flow_ids.add(ref.id)

            elementary_outputs = [
                ex
                for ex in simple_exchanges
                if not ex.is_input
                and not getattr(ex, "is_avoided_product", False)
                and ex not in output_products
            ]
            avoided_products = [
                ex
                for ex in simple_exchanges
                if not ex.is_input and getattr(ex, "is_avoided_product", False)
            ]

            if elementary_outputs:
                _names = [getattr(s, "flow_name", "?") for s in elementary_outputs]
                print(
                    f"ℹ️ Allocation: excluding {len(elementary_outputs)} elementary/emission output(s) "
                    f"from co-product denominator: {_names}"
                )

            if avoided_products:
                print(
                    f"🔄 System expansion: {len(avoided_products)} avoided product(s) detected — "
                    f"setting default_allocation_method=NO_ALLOCATION (no factors needed)"
                )
                process.default_allocation_method = o.AllocationType.NO_ALLOCATION
                process.allocation_factors = []
                return

            if len(output_products) < 2:
                return

            print(
                f"📊 Multi-output process '{process.name}': {len(output_products)} co-products → "
                f"calculating Physical + Economic + Causal factors (Calculate-factors equivalent)"
            )

            from .config import DEFAULT_ALLOCATION_METHOD

            config_method = (DEFAULT_ALLOCATION_METHOD or "PHYSICAL").upper()
            resolved_method = self._resolve_allocation_method_from_context(
                config_method
            )
            if resolved_method != config_method:
                print(
                    f"🧭 Allocation default overridden by project context: {config_method} -> {resolved_method}"
                )

            method_to_enum = {
                "PHYSICAL": o.AllocationType.PHYSICAL_ALLOCATION,
                "ECONOMIC": o.AllocationType.ECONOMIC_ALLOCATION,
                "CAUSAL": o.AllocationType.CAUSAL_ALLOCATION,
                "NONE": o.AllocationType.NO_ALLOCATION,
                "USE_DEFAULT": o.AllocationType.USE_DEFAULT_ALLOCATION,
            }

            flow_id_to_simple: Dict[str, Any] = {}
            for sex in output_products:
                flow_ref = self.created_flows.get(getattr(sex, "flow_name", ""))
                if isinstance(flow_ref, dict):
                    flow_ref = flow_ref.get("ref")
                if flow_ref and getattr(flow_ref, "id", None):
                    flow_id_to_simple[flow_ref.id] = sex

            output_exchanges: List[Tuple[Any, Any]] = []
            other_exchanges: List[Any] = []
            for ex in process.exchanges or []:
                if ex.flow is None:
                    continue
                is_avoided = getattr(ex, "is_avoided_product", False)
                if (
                    not ex.is_input
                    and not is_avoided
                    and (not coproduct_flow_ids or ex.flow.id in coproduct_flow_ids)
                ):
                    sex = flow_id_to_simple.get(ex.flow.id)
                    if sex is None:

                        for cand in output_products:
                            if cand.flow_name == ex.flow.name:
                                sex = cand
                                break
                    output_exchanges.append((ex, sex))
                else:
                    other_exchanges.append(ex)

            if len(output_exchanges) < 2:

                return

            has_explicit_causal = all(
                sex is not None and (getattr(sex, "allocation_value", 0) or 0) > 0
                for _, sex in output_exchanges
            )
            has_costs = all(
                sex is not None and (getattr(sex, "cost_value", 0) or 0) > 0
                for _, sex in output_exchanges
            )
            if has_explicit_causal:
                default_enum = o.AllocationType.CAUSAL_ALLOCATION
            elif has_costs:
                default_enum = o.AllocationType.ECONOMIC_ALLOCATION
            else:
                default_enum = method_to_enum.get(
                    resolved_method, o.AllocationType.PHYSICAL_ALLOCATION
                )
                if (
                    default_enum == o.AllocationType.ECONOMIC_ALLOCATION
                    and not has_costs
                ):
                    print(
                        "⚠️  ECONOMIC requested but no cost_value provided — falling back to PHYSICAL as default method"
                    )
                    default_enum = o.AllocationType.PHYSICAL_ALLOCATION
                elif default_enum == o.AllocationType.NO_ALLOCATION:
                    print(
                        "⚙️  NO_ALLOCATION resolved but multi-output detected — promoting default to PHYSICAL so factors are visible"
                    )
                    default_enum = o.AllocationType.PHYSICAL_ALLOCATION

            total_amount = sum((ex.amount or 0.0) for ex, _ in output_exchanges)
            physical_factors: Dict[str, float] = {
                ex.flow.id: ((ex.amount or 0.0) / total_amount) if total_amount else 0.0
                for ex, _ in output_exchanges
            }

            if has_costs:
                total_value = sum(
                    (ex.amount or 0.0) * (getattr(sex, "cost_value", 0) or 0)
                    for ex, sex in output_exchanges
                )
                economic_factors: Dict[str, float] = {
                    ex.flow.id: (
                        (
                            (ex.amount or 0.0)
                            * (getattr(sex, "cost_value", 0) or 0)
                            / total_value
                        )
                        if total_value
                        else 0.0
                    )
                    for ex, sex in output_exchanges
                }
            else:

                economic_factors = dict(physical_factors)

            if has_explicit_causal:
                total_alloc = sum(
                    (getattr(sex, "allocation_value", 0) or 0)
                    for _, sex in output_exchanges
                )
                causal_share: Dict[str, float] = {
                    ex.flow.id: (
                        ((getattr(sex, "allocation_value", 0) or 0) / total_alloc)
                        if total_alloc
                        else 0.0
                    )
                    for ex, sex in output_exchanges
                }
            else:

                causal_share = dict(physical_factors)

            process.allocation_factors = []

            for ex, _sex in output_exchanges:
                product_ref = o.Ref(
                    id=ex.flow.id,
                    name=getattr(ex.flow, "name", None),
                    ref_type=o.RefType.Flow,
                )

                process.allocation_factors.append(
                    o.AllocationFactor(
                        allocation_type=o.AllocationType.PHYSICAL_ALLOCATION,
                        product=product_ref,
                        value=physical_factors.get(ex.flow.id, 0.0),
                    )
                )

                process.allocation_factors.append(
                    o.AllocationFactor(
                        allocation_type=o.AllocationType.ECONOMIC_ALLOCATION,
                        product=product_ref,
                        value=economic_factors.get(ex.flow.id, 0.0),
                    )
                )

                share = causal_share.get(ex.flow.id, 0.0)
                for other_ex in other_exchanges:
                    internal_id = getattr(other_ex, "internal_id", 0) or 0
                    if internal_id <= 0:
                        continue
                    process.allocation_factors.append(
                        o.AllocationFactor(
                            allocation_type=o.AllocationType.CAUSAL_ALLOCATION,
                            product=product_ref,
                            value=share,
                            exchange=o.ExchangeRef(internal_id=internal_id),
                        )
                    )

            process.default_allocation_method = default_enum

            method_name = str(default_enum).split(".")[-1]
            print(
                f"✅ Calculated allocation factors for '{process.name}': default={method_name}, "
                f"factors written = {len(process.allocation_factors)} "
                f"({len(output_exchanges)} products × physical+economic, plus causal "
                f"{len(output_exchanges)}×{len(other_exchanges)})"
            )
            for ex, _sex in output_exchanges:
                print(
                    f"  • {getattr(ex.flow, 'name', ex.flow.id)}: "
                    f"physical={physical_factors.get(ex.flow.id, 0):.4f}, "
                    f"economic={economic_factors.get(ex.flow.id, 0):.4f}, "
                    f"causal={causal_share.get(ex.flow.id, 0):.4f}"
                )

        except Exception as e:
            print(
                f"⚠️ Error applying allocation to process '{getattr(process, 'name', '?')}': {e}"
            )
            import traceback

            traceback.print_exc()

    def find_provider_for_flow(
        self,
        flow_ref: o.Ref,
        process_context: str = "Unknown Process",
        explicit_provider: str = "",
        desired_location: str = "",
        excel_flow_name: Optional[str] = None,
        requested_amount: Optional[float] = None,
    ) -> Tuple[Optional[o.Ref], Dict]:
        """Provider search with location-aware caching and geographic matching"""
        if not flow_ref:
            return None, {}

        try:
            flow_name = flow_ref.name

            excel_lookup_name = (excel_flow_name or "").strip() or flow_name

            normalized_excel_flow = (
                normalize_chinese_flow_name(excel_lookup_name)
                if contains_chinese(excel_lookup_name)
                else ""
            )
            excel_lookup_lower = (excel_lookup_name or "").strip().lower()
            is_process_specific_offgas = (
                normalized_excel_flow == "解析气" or "off-gas" in excel_lookup_lower
            )

            cache_lookup = (
                excel_lookup_name
                if is_process_specific_offgas
                else (getattr(flow_ref, "id", "") or flow_name)
            )
            cache_scope = (process_context or "") if is_process_specific_offgas else ""
            amount_key = ""
            if normalized_excel_flow == "解析气" and requested_amount is not None:
                try:
                    amount_key = f"{float(requested_amount):.12g}"
                except Exception:
                    amount_key = str(requested_amount)
            cache_key = (cache_scope, cache_lookup, desired_location or "", amount_key)

            photovoltaic_provider = self._get_photovoltaic_provider_override(
                flow_ref=flow_ref,
                excel_flow_name=excel_lookup_name,
            )
            if photovoltaic_provider:
                if self._cache_flow_provider(
                    cache_key, photovoltaic_provider, flow_ref
                ):
                    print(
                        f"🌞 光伏发电规则命中：'{excel_lookup_name}' → "
                        f"'{PHOTOVOLTAIC_TARGET_FLOW_NAME}' provider "
                        f"'{photovoltaic_provider.name}'"
                    )
                    self._apply_provider_metadata(photovoltaic_provider, flow_ref)
                    return photovoltaic_provider, {}
                print(
                    f"⚠️ 光伏规则找到提供者但流校验未通过: "
                    f"{photovoltaic_provider.name}"
                )

            if explicit_provider:
                print(
                    f"🎯 Searching for explicit provider '{explicit_provider}' for flow '{flow_name}' (Excel: '{excel_lookup_name}')"
                )

                explicit_provider_ref = self.created_processes.get(explicit_provider)
                if explicit_provider_ref:
                    output_amount = self._check_provider_output_amount(
                        explicit_provider_ref, flow_ref
                    )
                    print(f"✅ 使用Excel显式指定的提供者: {explicit_provider}")
                    self._apply_provider_metadata(explicit_provider_ref, flow_ref)
                    return explicit_provider_ref, {}

                explicit_provider_ref = self.client.find(o.Process, explicit_provider)
                if explicit_provider_ref:
                    output_amount = self._check_provider_output_amount(
                        explicit_provider_ref, flow_ref
                    )
                    print(f"✅ 在背景数据库中找到显式指定的提供者: {explicit_provider}")
                    return explicit_provider_ref, {}

                print(
                    f"⚠️ Explicit provider '{explicit_provider}' not found, falling back to automatic search"
                )

            lifecycle_link = self._try_link_excel_lifecycle_process_provider(
                excel_lookup_name=excel_lookup_name,
                flow_ref=flow_ref,
                cache_key=cache_key,
                process_context=process_context,
            )
            if lifecycle_link:
                return lifecycle_link

            excel_explicit_info = self._get_registered_explicit_provider_info(
                process_context=process_context,
                flow_name=excel_lookup_name,
                direction="input_or_avoided",
            )
            if excel_explicit_info:
                excel_explicit_name = excel_explicit_info["provider_name"]

                print(
                    f"🎯 Found pre-registered Excel explicit provider for '{excel_lookup_name}': {excel_explicit_name}"
                )

                explicit_provider_ref = self.created_processes.get(excel_explicit_name)
                if explicit_provider_ref:
                    output_amount = self._check_provider_output_amount(
                        explicit_provider_ref, flow_ref
                    )
                    print(f"✅ 使用预注册的Excel提供者: {excel_explicit_name}")
                    self.flow_provider_cache[cache_key] = (explicit_provider_ref, {})
                    return explicit_provider_ref, {}

                if not PREFER_EXCEL_PROVIDERS:
                    explicit_provider_ref = self.client.find(
                        o.Process, excel_explicit_name
                    )
                    if explicit_provider_ref:
                        output_amount = self._check_provider_output_amount(
                            explicit_provider_ref, flow_ref
                        )
                        print(
                            f"✅ 在背景数据库中找到预注册的提供者: {excel_explicit_name}"
                        )
                        if self._cache_flow_provider(
                            cache_key, explicit_provider_ref, flow_ref
                        ):
                            return explicit_provider_ref, {}
                        self.flow_provider_cache[cache_key] = (
                            explicit_provider_ref,
                            {},
                        )
                        return explicit_provider_ref, {}
                print(
                    f"⚠️ Pre-registered provider '{excel_explicit_name}' not available yet"
                )

            if is_process_specific_offgas:
                providers = self.client.get_providers(flow_ref)
                if providers:
                    created_ids = {
                        ref.id
                        for ref in self.created_processes.values()
                        if ref and getattr(ref, "id", None)
                    }
                    foreground_candidates = []
                    for provider_obj in providers:
                        provider_ref = getattr(provider_obj, "provider", None)
                        if not provider_ref or provider_ref.id not in created_ids:
                            continue
                        output_amount = self._check_provider_output_amount(
                            provider_ref, flow_ref
                        )
                        if output_amount <= 0:
                            continue
                        foreground_candidates.append((provider_ref, output_amount))

                    if foreground_candidates:
                        usage_key = (process_context or "", excel_lookup_name)
                        used_provider_ids = (
                            self._consumer_flow_provider_usage.setdefault(
                                usage_key, set()
                            )
                        )
                        consumer_ctx = process_context or ""

                        preferred_supplier_tokens = []
                        if "电石装置" in consumer_ctx:
                            preferred_supplier_tokens = ["甲醇装置", "醋酸装置"]

                        preferred_available = []
                        for token in preferred_supplier_tokens:
                            for pref, out_amt in foreground_candidates:
                                if token in (pref.name or ""):
                                    preferred_available.append((token, pref, out_amt))
                                    break

                        for _token, pref, out_amt in preferred_available:
                            if pref.id in used_provider_ids:
                                continue
                            used_provider_ids.add(pref.id)
                            if self._cache_flow_provider(cache_key, pref, flow_ref):
                                print(
                                    f"🎯 Preferred foreground provider selected for '{excel_lookup_name}' "
                                    f"in '{process_context}': {pref.name} "
                                    f"(output={out_amt}, input={requested_amount})"
                                )
                                self._apply_provider_metadata(pref, flow_ref)
                                return pref, {}

                        def _candidate_score(item):
                            pref, out_amt = item
                            reused = 1 if pref.id in used_provider_ids else 0
                            if requested_amount is None:
                                amount_diff = 0.0
                            else:
                                try:
                                    amount_diff = abs(
                                        float(out_amt) - float(requested_amount)
                                    )
                                except Exception:
                                    amount_diff = 0.0

                            return (reused, amount_diff, -float(out_amt))

                        best_provider_ref, best_out_amt = sorted(
                            foreground_candidates, key=_candidate_score
                        )[0]
                        used_provider_ids.add(best_provider_ref.id)
                        if self._cache_flow_provider(
                            cache_key, best_provider_ref, flow_ref
                        ):
                            print(
                                f"🎯 Foreground custom-flow provider selected for '{excel_lookup_name}' "
                                f"in '{process_context}': {best_provider_ref.name} "
                                f"(output={best_out_amt}, input={requested_amount})"
                            )
                            self._apply_provider_metadata(best_provider_ref, flow_ref)
                            return best_provider_ref, {}

            if cache_key in self.flow_provider_cache:
                cached_provider, cached_cv_results = self.flow_provider_cache[cache_key]

                if not is_process_specific_offgas:
                    print(
                        f"💾 Using cached provider for '{flow_name}' (loc:{desired_location or 'auto'}): {cached_provider.name}"
                    )
                    return cached_provider, cached_cv_results
                if self._provider_supports_flow(cached_provider, flow_ref):
                    print(
                        f"💾 Using cached provider for '{flow_name}' (loc:{desired_location or 'auto'}): {cached_provider.name}"
                    )
                    return cached_provider, cached_cv_results
                print(
                    f"⚠️ Cached provider '{cached_provider.name}' does not output '{flow_name}' - removing from cache"
                )
                del self.flow_provider_cache[cache_key]

            excel_provider_found = False
            if excel_lookup_name in self.excel_flow_providers:
                provider_info = self.excel_flow_providers[excel_lookup_name]
                if isinstance(provider_info, dict):
                    excel_provider_name = provider_info["provider_name"]
                else:
                    excel_provider_name = provider_info

                excel_provider_ref = self.created_processes.get(excel_provider_name)
                if excel_provider_ref:
                    if self._cache_flow_provider(
                        cache_key, excel_provider_ref, flow_ref
                    ):
                        print(
                            f"🎯 Using Excel-defined output provider for '{excel_lookup_name}': {excel_provider_name}"
                        )
                        return excel_provider_ref, {}
                    print(
                        f"⚠️ Excel-defined output provider '{excel_provider_name}' does not supply '{excel_lookup_name}' - ignoring"
                    )
                else:
                    excel_provider_found = True

            is_chinese_custom = contains_chinese(excel_lookup_name) or (
                "off-gas" in excel_lookup_lower
            )
            if (
                PREFER_EXCEL_PROVIDERS
                and excel_provider_found
                and not is_chinese_custom
            ):
                print(
                    f"⚠️ Excel provider specified for '{excel_lookup_name}' but not found"
                )
                return None, {}

            system_desc = ""
            if self.project_context and self.project_context.system_boundary:
                system_desc = self.project_context.system_boundary.description or ""
                geo_scope = (
                    getattr(
                        self.project_context.system_boundary, "geographic_scope", ""
                    )
                    or ""
                )
                if geo_scope and geo_scope.lower() not in (
                    system_desc.lower() if system_desc else ""
                ):
                    system_desc = (
                        f"{system_desc}\nDefault geographic scope: {geo_scope}"
                        if system_desc
                        else f"Default geographic scope: {geo_scope}"
                    )

            providers = None
            flow_id = getattr(flow_ref, "id", "") if flow_ref else ""

            if (
                (not is_process_specific_offgas)
                and flow_id
                and flow_id in self._provider_candidates_cache
            ):
                providers = self._provider_candidates_cache[flow_id]
            if providers is None:
                providers = self.client.get_providers(flow_ref)
                if (not is_process_specific_offgas) and flow_id and providers:
                    self._provider_candidates_cache[flow_id] = providers
            if providers:
                if VERBOSE_OUTPUT:
                    print(
                        f"🔍 Found {len(providers)} candidate providers for '{flow_name}'"
                    )
                process_context_for_selection = (
                    process_context
                    if self.enable_lifecycle_stage_classification
                    else "General process (stage classification disabled)"
                )

                provider_ref = None
                cv_results = {}

                if self.provider_selection_mode == "semantic_only":
                    provider_ref, cv_results = (
                        self._select_provider_by_semantic_similarity(
                            providers=providers,
                            flow_name=flow_name,
                            excel_flow_name=excel_lookup_name,
                        )
                    )

                if not provider_ref:
                    from .uncertainty import (
                        _is_market_activity,
                        _get_expected_location_codes,
                        _calculate_geographic_match_score,
                        _extract_location_from_provider_name,
                        _calculate_geographic_match_score_by_code,
                        _check_provider_output_and_location,
                        _EU_COUNTRY_CODES,
                        _EFTA_CODES,
                    )

                    if desired_location:
                        loc_upper = desired_location.upper()
                        expected_codes = [loc_upper]
                        if loc_upper in _EU_COUNTRY_CODES or loc_upper in _EFTA_CODES:
                            expected_codes.append("RER")
                        elif loc_upper not in ("GLO", "RER", "RoW", "ROW"):
                            expected_codes.append("RoW")
                        if "GLO" not in expected_codes:
                            expected_codes.append("GLO")
                        print(
                            f"📍 Excel指定地区 '{desired_location}' → 优先级: {' → '.join(expected_codes)}"
                        )
                    else:
                        expected_codes = _get_expected_location_codes(
                            system_desc, process_context_for_selection
                        )
                        if expected_codes == ["GLO"]:
                            print(
                                f"🌍 过程 '{process_context_for_selection}' 无法推断地区，回退到 GLO"
                            )
                        else:
                            print(
                                f"🌍 过程 '{process_context_for_selection}' 推断地区优先级: {' → '.join(expected_codes)}"
                            )

                    all_scored = []
                    for prov in providers:
                        tier = 0
                        pname = prov.provider.name
                        is_market = _is_market_activity(pname)
                        if is_market:
                            tier += 10000
                        geo_score = _calculate_geographic_match_score(
                            pname, expected_codes
                        )
                        if geo_score >= 1.0:
                            tier += 5000
                        elif geo_score >= 0.7:
                            tier += 3000
                        elif geo_score >= 0.4:
                            tier += 1000
                        all_scored.append((prov.provider, tier, is_market, geo_score))

                    market_scored = [s for s in all_scored if s[2]]
                    pool = market_scored if market_scored else all_scored

                    needs_db_location = (
                        expected_codes
                        and expected_codes[0] not in ("GLO", "RER", "RoW", "ROW")
                        and pool
                        and all(s[3] == 0.0 for s in pool)
                    )
                    if needs_db_location:
                        print(
                            f"🔍 所有候选名称无地区信息，对 {min(len(pool), 50)} 个候选执行数据库地区查询..."
                        )
                        rescored_pool = []
                        for prov_ref, tier_val, is_mkt, _ in pool[:50]:
                            _, actual_loc = _check_provider_output_and_location(
                                prov_ref, flow_ref, self.client
                            )
                            new_geo = _calculate_geographic_match_score_by_code(
                                actual_loc, expected_codes
                            )
                            new_tier = 10000 if is_mkt else 0
                            if new_geo >= 1.0:
                                new_tier += 5000
                            elif new_geo >= 0.7:
                                new_tier += 3000
                            elif new_geo >= 0.4:
                                new_tier += 1000
                            rescored_pool.append(
                                (prov_ref, new_tier, is_mkt, new_geo, actual_loc)
                            )
                        rescored_pool.sort(key=lambda s: s[1], reverse=True)
                        best_prov = rescored_pool[0][0]
                        best_tier = rescored_pool[0][1]
                        best_loc = rescored_pool[0][4]
                        geo_matched = sum(1 for s in rescored_pool if s[3] >= 0.4)
                        print(f"✅ 数据库地区查询完成：{geo_matched} 个地区匹配")
                        if best_prov:
                            provider_ref = best_prov
                            is_mkt_flag = "🏪" if rescored_pool[0][2] else ""
                            print(
                                f"{is_mkt_flag}🔗 选择提供者 for '{flow_name}': {provider_ref.name} (db_loc:{best_loc}, expected:{expected_codes[0]}, tier:{best_tier})"
                            )
                    else:
                        pool.sort(key=lambda s: s[1], reverse=True)
                        best_prov, best_tier = pool[0][0], pool[0][1]

                        if best_prov:
                            provider_ref = best_prov
                            loc = _extract_location_from_provider_name(
                                provider_ref.name
                            )
                            is_mkt = (
                                "🏪" if _is_market_activity(provider_ref.name) else ""
                            )
                            src = "market" if market_scored else "all"
                            print(
                                f"{is_mkt}🔗 选择提供者 for '{flow_name}': {provider_ref.name} (loc:{loc}, expected:{expected_codes[0]}, tier:{best_tier}, from:{src})"
                            )

                    if not provider_ref:
                        provider_ref = providers[0].provider
                        print(
                            f"🔗 Using first available provider for '{flow_name}': {provider_ref.name}"
                        )

                self.flow_provider_cache[cache_key] = (provider_ref, cv_results)
                return provider_ref, cv_results

            print(f"⚠️ No providers found for flow '{flow_name}'")
            return None, {}

        except Exception as e:
            print(f"❌ Error finding provider for flow '{flow_ref.name}': {e}")
            return None, {}

    def _normalize_lookup_label(self, value: str) -> str:
        """Normalize labels for robust flow/provider string comparison."""
        normalized = (value or "").strip().lower()
        if not normalized:
            return ""
        normalized = re.sub(r"\s*,\s*", ", ", normalized)
        normalized = re.sub(r"\s*\|\s*", " | ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _is_photovoltaic_excel_flow(self, excel_flow_name: str) -> bool:
        """Check whether the original Excel flow name indicates photovoltaic electricity."""
        raw_name = (excel_flow_name or "").strip()
        if not raw_name:
            return False
        if raw_name == PHOTOVOLTAIC_EXCEL_FLOW_NAME:
            return True
        if contains_chinese(raw_name):
            return normalize_chinese_flow_name(raw_name) == PHOTOVOLTAIC_EXCEL_FLOW_NAME
        return False

    def _get_photovoltaic_provider_override(
        self, flow_ref: o.Ref, excel_flow_name: str
    ) -> Optional[o.Ref]:

        if not flow_ref or not self._is_photovoltaic_excel_flow(excel_flow_name):
            return None

        if self._normalize_lookup_label(flow_ref.name) != self._normalize_lookup_label(
            PHOTOVOLTAIC_TARGET_FLOW_NAME
        ):
            return None

        provider_ref = self.client.find(o.Process, PHOTOVOLTAIC_PROVIDER_NAME)
        if provider_ref:
            return provider_ref

        target_norm = self._normalize_lookup_label(PHOTOVOLTAIC_PROVIDER_NAME)
        required_tokens = (
            "electricity production, photovoltaic",
            "3kwp facade installation",
            "multi-si",
            "laminated",
            "integrated",
            "| electricity, low voltage | cutoff, u",
        )

        try:
            for process_ref in self.client.get_descriptors(o.Process):
                process_name = getattr(process_ref, "name", "") or ""
                if not process_name:
                    continue
                process_norm = self._normalize_lookup_label(process_name)
                if process_norm == target_norm:
                    return process_ref
                if all(token in process_norm for token in required_tokens):
                    return process_ref
        except Exception as error:
            print(f"⚠️ 光伏provider检索失败: {error}")

        return None

    def _check_provider_output_amount(
        self, provider_ref: o.Ref, flow_ref: o.Ref
    ) -> float:
        """Simplified provider output check for stability"""
        try:
            provider_process = self.client.get(o.Process, provider_ref.id)
            if not provider_process or not provider_process.exchanges:
                return 0.0

            for exchange in provider_process.exchanges:
                if exchange.is_input or not exchange.flow:
                    continue
                if exchange.flow.id == flow_ref.id:
                    return exchange.amount

            return 0.0

        except Exception as e:

            return 0.0

    def _provider_supports_flow(
        self, provider_ref: Optional[o.Ref], flow_ref: o.Ref
    ) -> bool:
        """Return True when provider_ref has an output exchange for flow_ref."""
        if not provider_ref or not flow_ref:
            return False

        output_amount = self._check_provider_output_amount(provider_ref, flow_ref)
        if output_amount > 0:
            return True

        try:
            provider_process = self.client.get(o.Process, provider_ref.id)
            if not provider_process or not provider_process.exchanges:
                return False

            for exchange in provider_process.exchanges:
                if (
                    not exchange.is_input
                    and exchange.flow
                    and exchange.flow.name == flow_ref.name
                ):

                    if exchange.flow.id != flow_ref.id:
                        flow_ref.id = exchange.flow.id
                    return True
        except Exception as error:
            print(
                f"⚠️ Error verifying provider support for '{provider_ref.name}': {error}"
            )

        return False

    def _cache_flow_provider(
        self, cache_key, provider_ref: o.Ref, flow_ref: o.Ref
    ) -> bool:
        """Cache provider when it produces the given flow"""
        if not provider_ref or not flow_ref:
            return False

        if self._provider_supports_flow(provider_ref, flow_ref):
            self.flow_provider_cache[cache_key] = (provider_ref, {})
            return True

        return False

    def _filter_providers_with_nonzero_output(
        self, providers: List, flow_ref: o.Ref
    ) -> List:
        """Filter providers to only include those that produce a non-zero amount of the specified flow"""
        valid_providers = []

        try:
            for provider_obj in providers:
                if not hasattr(provider_obj, "provider") or not provider_obj.provider:
                    continue

                provider_ref = provider_obj.provider
                output_amount = self._check_provider_output_amount(
                    provider_ref, flow_ref
                )

                if output_amount > 0:
                    valid_providers.append(provider_obj)

        except Exception as e:
            print(f"❌ Error filtering providers by output amount: {e}")

            return providers

        return valid_providers

    def _enhanced_provider_search(
        self, target_flow_name: str, flow_ref: o.Ref, process_context: str = ""
    ) -> Optional[o.Ref]:
        """DEPRECATED: This method is no longer used to prevent timeout issues"""

        print(f"⚠️ Enhanced provider search disabled for stability")
        return None

    def _comprehensive_provider_search(
        self, target_flow_name: str, flow_ref: o.Ref, process_context: str = ""
    ) -> Optional[o.Ref]:
        """DEPRECATED: This method is no longer used to prevent timeout issues"""

        print(f"⚠️ Comprehensive provider search disabled for stability")
        return None

    def _find_flows_by_partial_name(
        self, target_flow_name: str
    ) -> List[Tuple[o.Ref, float]]:
        """Find flows that have partial name matches with the target flow."""
        try:

            all_flows = self.client.get_descriptors(o.Flow)
            similar_flows = []

            target_lower = target_flow_name.lower()

            for flow_ref in all_flows:
                flow_name_lower = flow_ref.name.lower()

                similarity = 0

                if target_lower in flow_name_lower or flow_name_lower in target_lower:

                    similarity = 0.9 if len(target_lower) > 0 else 0.5

                elif self._calculate_partial_similarity(target_lower, flow_name_lower):
                    similarity = 0.8

                if similarity > 0:
                    similar_flows.append((flow_ref, similarity))

            similar_flows.sort(key=lambda x: x[1], reverse=True)
            return similar_flows

        except Exception as e:
            print(f"❌ Error in partial name search: {e}")
            return []

    def _calculate_partial_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names based on shared words after removing common words."""
        try:

            common_words = {
                "the",
                "of",
                "and",
                "or",
                "a",
                "an",
                "in",
                "on",
                "at",
                "to",
                "for",
                "with",
                "by",
                "from",
                "up",
                "about",
                "into",
                "through",
                "during",
                "before",
                "after",
                "above",
                "below",
                "between",
                "among",
                "as",
                "if",
                "is",
                "was",
                "are",
                "were",
                "be",
                "been",
                "being",
                "have",
                "has",
                "had",
                "do",
                "does",
                "did",
                "will",
                "would",
                "should",
                "can",
                "could",
                "consumption",
                "mix",
                "at",
                "power",
                "plant",
                "from",
                "underground",
                "open",
                "pit",
                "mining",
                "production",
                "sintered",
                "bricks",
                "raw",
            }

            words1 = [w for w in name1.split() if w not in common_words]
            words2 = [w for w in name2.split() if w not in common_words]

            if not words1 or not words2:
                return False

            set1 = set(words1)
            set2 = set(words2)
            intersection = set1.intersection(set2)

            if len(intersection) > 0:
                min_len = min(len(set1), len(set2))
                if len(intersection) >= max(1, min_len * 0.5):
                    return True

            return False
        except:
            return False

    def _find_provider_by_category(
        self, target_flow_name: str, flow_ref: o.Ref
    ) -> Optional[o.Ref]:
        """Try to find providers by looking for flows in related categories."""
        try:

            category_indicators = {
                "energy": ["power", "electricity", "energy", "kwh", "mj", "joule"],
                "fuel": ["coal", "gas", "oil", "petrol", "diesel", "fuel", "gasoline"],
                "minerals": [
                    "ore",
                    "mineral",
                    "metal",
                    "iron",
                    "copper",
                    "aluminum",
                    "gold",
                    "silver",
                ],
                "chemicals": [
                    "acid",
                    "base",
                    "chemical",
                    "caustic",
                    "sodium",
                    "chlorine",
                ],
                "emissions": [
                    "co2",
                    "co",
                    "ch4",
                    "no",
                    "no2",
                    "nox",
                    "so2",
                    "sox",
                    "pm",
                    "particles",
                ],
                "water": ["water", "fresh water", "ground water", "surface water"],
            }

            target_lower = target_flow_name.lower()
            likely_category = None

            for category, indicators in category_indicators.items():
                if any(indicator in target_lower for indicator in indicators):
                    likely_category = category
                    break

            if not likely_category:
                return None

            print(
                f"🔍 Searching in category '{likely_category}' for flows similar to '{target_flow_name}'"
            )

            all_processes = self.client.get_descriptors(o.Process)

            for process_desc in all_processes[:200]:
                try:
                    process_obj = self.client.get(o.Process, process_desc.id)
                    if not process_obj or not process_obj.exchanges:
                        continue

                    for exchange in process_obj.exchanges:
                        if exchange.is_input or not exchange.flow:
                            continue

                        output_flow = exchange.flow
                        if not output_flow.name:
                            continue

                        output_flow_lower = output_flow.name.lower()

                        if (
                            target_lower in output_flow_lower
                            or output_flow_lower in target_lower
                            or any(
                                indicator in output_flow_lower
                                for indicator in category_indicators.get(
                                    likely_category, []
                                )
                            )
                        ):

                            print(
                                f"🔍 Found matching output flow '{output_flow.name}' in process '{process_obj.name}'"
                            )

                            if (
                                output_flow.id == flow_ref.id
                                or output_flow.name == flow_ref.name
                            ):

                                process_ref = o.Ref()
                                process_ref.id = process_obj.id
                                process_ref.name = process_obj.name
                                return process_ref
                            else:

                                flow_similarity = self._calculate_partial_similarity(
                                    target_flow_name.lower(), output_flow.name.lower()
                                )
                                if flow_similarity:

                                    temp_flow_ref = o.Ref()
                                    temp_flow_ref.id = output_flow.id
                                    temp_flow_ref.name = output_flow.name

                                    providers = self.client.get_providers(temp_flow_ref)
                                    if providers:
                                        valid_providers = (
                                            self._filter_providers_with_nonzero_output(
                                                providers, temp_flow_ref
                                            )
                                        )
                                        if valid_providers:
                                            return valid_providers[0].provider
                except Exception as e:
                    continue

            return None
        except Exception as e:
            print(f"❌ Error in category-based provider search: {e}")
            return None

    def _llm_semantic_search(
        self, target_flow_name: str, flow_ref: o.Ref, process_context: str = ""
    ) -> Optional[o.Ref]:
        """Use LLM to perform semantic search for providers of flows that might not have"""
        if not self.llm_clients:
            return None

        try:

            available_llm = "deepseek"
            if (
                available_llm not in self.llm_clients
                or not self.llm_clients[available_llm]
            ):
                print("⚠️ No available LLM for semantic provider search")
                return None

            all_processes = self.client.get_descriptors(o.Process)

            process_samples = []
            for i, proc_desc in enumerate(all_processes[:50]):
                try:
                    proc_obj = self.client.get(o.Process, proc_desc.id)
                    if proc_obj and proc_obj.exchanges:

                        output_flow_names = []
                        for ex in proc_obj.exchanges:
                            if not ex.is_input and ex.flow and ex.flow.name:
                                output_flow_names.append(ex.flow.name)

                        if output_flow_names:
                            process_samples.append(
                                {
                                    "name": proc_obj.name,
                                    "outputs": output_flow_names[:3],
                                }
                            )
                except:
                    continue

            if not process_samples:
                return None

            processes_str = "\\n".join(
                [
                    f"{i+1}. Process: {proc['name']}, Outputs: {', '.join(proc['outputs'])}"
                    for i, proc in enumerate(process_samples)
                ]
            )

            prompt = f"""
You are an LCA expert helping to match a flow to its provider process.

Target Flow: "{target_flow_name}"
Process Context: {process_context}

The flow might be an elementary flow or a product flow. Based on the flow name,
please identify which of the following processes is most likely to provide this flow.
Consider that elementary flows like "hard coal, consumption mix, at power plant, from underground and open pit mining"
are often provided by processes like "Coke production ; coke ; coking" that output similar flows.

Available Processes:
{processes_str}

Please return the number of the most likely process (1-{len(process_samples)}), or return "0" if none are suitable.
If multiple processes could provide this flow, return the most specific or common one.
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=100
            )

            import re

            match = re.search(r"\\b([0-{}])\\b".format(len(process_samples)), response)
            if match:
                choice = int(match.group(1))
                if 1 <= choice <= len(process_samples):
                    selected_process = process_samples[choice - 1]
                    print(f"🤖 LLM selected process: {selected_process['name']}")

                    process_ref_result = self.client.find(
                        o.Process, selected_process["name"]
                    )
                    if process_ref_result:

                        try:
                            process_obj = self.client.get(
                                o.Process, process_ref_result.id
                            )
                            if process_obj and process_obj.exchanges:
                                for exchange in process_obj.exchanges:
                                    if (
                                        not exchange.is_input
                                        and exchange.flow
                                        and exchange.flow.name
                                    ):

                                        if (
                                            exchange.flow.name.lower()
                                            == target_flow_name.lower()
                                            or target_flow_name.lower()
                                            in exchange.flow.name.lower()
                                            or self._calculate_partial_similarity(
                                                target_flow_name.lower(),
                                                exchange.flow.name.lower(),
                                            )
                                        ):

                                            temp_flow_ref = o.Ref()
                                            temp_flow_ref.id = exchange.flow.id
                                            temp_flow_ref.name = exchange.flow.name

                                            return process_ref_result
                        except:
                            pass

                    return process_ref_result

            print(
                f"❌ LLM semantic search could not identify provider for '{target_flow_name}'"
            )
            return None

        except Exception as e:
            print(f"❌ Error in LLM semantic search for '{target_flow_name}': {e}")
            return None

    def _llm_synonym_provider_search(self, target_flow_name: str) -> Optional[o.Ref]:
        """Use LLM to identify synonyms and search for providers of synonym flows"""
        if not self.llm_clients:
            return None

        try:
            print(f"🤖 LLM synonym provider search for: '{target_flow_name}'")

            available_llm = "deepseek"
            if (
                available_llm not in self.llm_clients
                or not self.llm_clients[available_llm]
            ):
                print("⚠️ No available LLM for synonym provider search")
                return None

            prompt = f"""
You are an LCA expert identifying industrial flow synonyms to help find providers.

Target flow: "{target_flow_name}"

Task: Identify the most likely industrial synonyms for this flow that would have the same providers.

Common industrial synonym patterns:
- Power = Electricity, Electric power, Electric energy
- Natural gas = Naturalgas, Gas, NG
- Caustic = Sodium hydroxide, NaOH, Caustic soda
- Steam = Water vapor, Vapor
- Diesel = Diesel fuel, Gas oil
- Petrol = Gasoline, Fuel

Respond with ONLY the top 3 most likely synonyms, one per line, no numbering or explanation.
If no clear synonyms exist, respond with "NONE".

Example:
Input: "Power"
Output:
Electricity
Electric power
Electric energy
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=100
            )

            if not response or "NONE" in response.upper():
                print(f"🤖 LLM found no synonyms for '{target_flow_name}'")
                return None

            synonym_candidates = []
            for line in response.strip().split("\n"):
                synonym = line.strip()
                if (
                    synonym
                    and len(synonym) > 0
                    and synonym.lower() != target_flow_name.lower()
                ):
                    synonym_candidates.append(synonym)

            if not synonym_candidates:
                print(f"🤖 No valid synonyms extracted for '{target_flow_name}'")
                return None

            print(
                f"🔍 Searching providers for synonyms of '{target_flow_name}': {synonym_candidates[:3]}"
            )

            all_flows = self.client.get_descriptors(o.Flow)

            for synonym in synonym_candidates[:3]:
                synonym_lower = synonym.lower()

                for flow_desc in all_flows:
                    if not flow_desc.name:
                        continue

                    flow_name_lower = flow_desc.name.lower()

                    if (
                        synonym_lower == flow_name_lower
                        or synonym_lower in flow_name_lower
                        or flow_name_lower in synonym_lower
                    ):

                        try:
                            temp_ref = o.Ref()
                            temp_ref.id = flow_desc.id
                            temp_ref.name = flow_desc.name

                            if temp_ref.name in self.flow_provider_cache:
                                cached_provider, _ = self.flow_provider_cache[
                                    temp_ref.name
                                ]
                                print(
                                    f"💾 Using cached provider (synonym) for '{temp_ref.name}': {cached_provider.name}"
                                )
                                return cached_provider

                            providers = self.client.get_providers(temp_ref)
                            if providers:
                                provider = providers[0].provider
                                print(
                                    f"✅ Found provider via synonym match: '{target_flow_name}' -> '{temp_ref.name}' -> {provider.name}"
                                )

                                self.flow_provider_cache[temp_ref.name] = (provider, {})
                                return provider

                        except Exception as e:
                            print(
                                f"⚠️ Error checking providers for synonym flow '{flow_desc.name}': {e}"
                            )
                            continue

            print(f"❌ No providers found via synonym search for '{target_flow_name}'")
            return None

        except Exception as e:
            print(
                f"❌ Error in LLM synonym provider search for '{target_flow_name}': {e}"
            )
            return None

    def select_impact_method(
        self,
        product_system_name: str,
        calculation_purpose: str = "LCA calculation",
        impact_method_name: str = None,
    ) -> Optional[o.Ref]:
        """Unified impact assessment method selection for both deterministic and uncertainty analysis"""

        if impact_method_name:
            impact_method = self.client.find(o.ImpactMethod, impact_method_name)
            if impact_method:
                print(
                    f"📋 Using specified impact assessment method: {impact_method.name}"
                )
                return impact_method

        if VERBOSE_OUTPUT:
            print("🔍 Finding available impact assessment methods...")
        all_methods = self.client.get_descriptors(o.ImpactMethod)
        if not all_methods:
            print("❌ No available impact assessment methods")
            return None

        if VERBOSE_OUTPUT:
            print(f"📊 Found {len(all_methods)} available impact assessment methods")

        if self.preferred_lcia_method:
            print(
                f"🔍 Priority search for preferred method: {self.preferred_lcia_method}"
            )

            preferred_method = None

            user_wants_no_lt = "no lt" in self.preferred_lcia_method.lower()
            print(f"   User wants 'no LT' version: {user_wants_no_lt}")

            preferred_methods = [
                m
                for m in all_methods
                if self.preferred_lcia_method.lower() in m.name.lower()
                and "incl" not in m.name.lower()
                and "uptake" not in m.name.lower()
            ]

            print(f"   Initial substring matches: {len(preferred_methods)} methods")
            for m in preferred_methods[:5]:
                print(f"      - {m.name}")

            if not user_wants_no_lt:
                before_filter = len(preferred_methods)
                preferred_methods = [
                    m for m in preferred_methods if "no lt" not in m.name.lower()
                ]
                after_filter = len(preferred_methods)
                print(
                    f"   After excluding 'no LT': {after_filter} methods (removed {before_filter - after_filter})"
                )
                for m in preferred_methods[:5]:
                    print(f"      - {m.name}")

            if preferred_methods:
                preferred_method = preferred_methods[0]
                print(f"✅ Found via substring match: {preferred_method.name}")
                print(f"   🎯 Selected method ID: {preferred_method.id}")

            if not preferred_method and "ipcc" in self.preferred_lcia_method.lower():
                ipcc_methods = []
                for m in all_methods:
                    name_lower = m.name.lower()

                    if (
                        "ipcc" in name_lower
                        or "climate" in name_lower
                        or "global warming" in name_lower
                    ):
                        if "incl" not in name_lower and "uptake" not in name_lower:

                            if user_wants_no_lt or "no lt" not in name_lower:
                                ipcc_methods.append(m)

                if ipcc_methods:

                    for m in ipcc_methods:
                        name_lower = m.name.lower()
                        if (
                            "ipcc" in name_lower
                            and "gwp" in name_lower
                            and "100" in name_lower
                        ):
                            if "2013" in name_lower or "2021" in name_lower:
                                preferred_method = m
                                print(
                                    f"✅ Found IPCC GWP 100a method (with year, without uptake): {m.name}"
                                )
                                break

                    if not preferred_method:
                        for m in ipcc_methods:
                            name_lower = m.name.lower()
                            if (
                                "ipcc" in name_lower
                                and ("gwp" in name_lower or "warming" in name_lower)
                                and "100" in name_lower
                            ):
                                preferred_method = m
                                print(f"✅ Found IPCC GWP 100 method: {m.name}")
                                break

                    if not preferred_method:
                        for m in ipcc_methods:
                            name_lower = m.name.lower()
                            if "ipcc" in name_lower:
                                preferred_method = m
                                print(f"✅ Found IPCC method: {m.name}")
                                break

                    if not preferred_method:
                        preferred_method = ipcc_methods[0]
                        print(
                            f"✅ Found climate-related method: {preferred_method.name}"
                        )

            if not preferred_method:
                keywords = self.preferred_lcia_method.lower().split()
                for m in all_methods:
                    name_lower = m.name.lower()
                    if all(kw in name_lower for kw in keywords):
                        preferred_method = m
                        print(f"✅ Found via keyword match: {m.name}")
                        break

            if preferred_method:
                print(f"🎯 [Preferred Method] ✅ {preferred_method.name}")
                return preferred_method
            else:
                print(f"⚠️ No methods found matching '{self.preferred_lcia_method}'")
                print(f"⚠️ Available methods: {[m.name for m in all_methods[:5]]}")
                print(f"⚠️ Falling back to AI selection")

        if len(all_methods) > 1 and self.llm_clients:
            print(
                "🤖 Using AI to select the most appropriate impact assessment method..."
            )
            selected_method = self.llm_select_impact_method_llm(
                all_methods, product_system_name, calculation_purpose
            )
            if selected_method:
                return selected_method
            else:
                print(
                    f"🔄 Fallback: Using first available method: {all_methods[0].name}"
                )
                return all_methods[0]

        impact_method = all_methods[0]
        print(
            f"📋 Using first available impact assessment method: {impact_method.name}"
        )
        return impact_method

    def llm_select_impact_method_llm(
        self,
        available_methods: List[o.Ref],
        product_system_name: str = "",
        calculation_purpose: str = "",
    ) -> Optional[o.Ref]:
        """Use LLM to select the most appropriate impact assessment method"""
        if not available_methods or not self.llm_clients:
            return None

        available_llm = None
        for llm_name in ["deepseek"]:
            if llm_name in self.llm_clients and self.llm_clients[llm_name]:
                available_llm = llm_name
                break

        if not available_llm:
            print("⚠️ No available LLM for impact method selection")
            return None

        try:

            method_info = []
            for i, method_ref in enumerate(available_methods[:10]):
                try:

                    full_method = self.client.get(o.ImpactMethod, method_ref.id)
                    impact_categories = []
                    if full_method and full_method.impact_categories:
                        impact_categories = [
                            cat.name for cat in full_method.impact_categories[:5]
                        ]

                    method_name_line = f"{i+1}. Method Name: {method_ref.name}\n"
                    category_line = (
                        f"   Category: {method_ref.category or 'Uncategorized'}\n"
                    )
                    desc_line = f"   Description: {full_method.description[:100] if full_method and full_method.description else 'No description'}\n"
                    categories_line = f"   Impact Categories: {', '.join(impact_categories) if impact_categories else 'Not specified'}"
                    method_info.append(
                        method_name_line + category_line + desc_line + categories_line
                    )
                except Exception as e:
                    method_name_line = f"{i+1}. Method Name: {method_ref.name}\n"
                    category_line = (
                        f"   Category: {method_ref.category or 'Uncategorized'}\n"
                    )
                    desc_line = (
                        "   Description: Unable to retrieve detailed information"
                    )
                    method_info.append(method_name_line + category_line + desc_line)

            method_info_str = "\n".join(method_info)

            prompt = f"""
You are a Life Cycle Assessment (LCA) expert. I need you to select the most appropriate impact assessment method for the following product system.

Product System Information:
- System Name: {product_system_name}
- Calculation Purpose: {calculation_purpose or 'General environmental impact assessment'}

Available Impact Assessment Methods:
{method_info_str}

Please analyze and select the most suitable method based on the following criteria:
1. Comprehensiveness and authority of the method
2. Applicability to the given product system type
3. Coverage of impact categories
4. Widespread application and recognition
5. Data quality and scientific basis

Please only return the number of the best method (1-{len(method_info)}), or return "0" if no suitable method is found.
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=100
            )

            import re

            match = re.search(r"\b([0-{}])\b".format(len(method_info)), response)
            if match:
                choice = int(match.group(1))
                if 1 <= choice <= len(available_methods):
                    selected_method = available_methods[choice - 1]
                    print(
                        f"🤖 AI selected impact assessment method: {selected_method.name}"
                    )
                    return selected_method
                elif choice == 0:
                    print("🤖 AI found no suitable impact assessment method")
                    return None

            print(
                "⚠️ AI response could not be parsed, using first available impact assessment method"
            )
            return available_methods[0]

        except Exception as e:
            print(f"❌ AI impact assessment method selection failed: {e}")

            if available_methods:
                return available_methods[0]
            return None

    def llm_evaluate_provider_match(
        self,
        target_flow_ref: o.Ref,
        candidate_providers: List[Dict],
        process_context: str = "",
    ) -> Optional[o.Ref]:
        """Use LLM to evaluate which provider best matches the target flow requirements"""
        if not candidate_providers or not self.llm_clients:
            return None

        available_llm = "deepseek"
        if available_llm not in self.llm_clients or not self.llm_clients[available_llm]:
            print("⚠️ No available LLM for provider evaluation")
            return None

        try:

            candidate_info = []
            for i, candidate in enumerate(candidate_providers[:5]):
                provider_name = candidate["provider"].name
                source_flow_name = candidate["source_flow"].name
                similarity = candidate["similarity"]

                output_flow_name = "Unknown"
                if "output_flow" in candidate and candidate["output_flow"]:
                    output_flow_name = getattr(
                        candidate["output_flow"], "name", "Unknown"
                    )

                provider_line = f"{i+1}. Provider: {provider_name}\n"
                source_line = f"   Source Flow: {source_flow_name} (Similarity: {similarity:.2f})\n"
                output_line = f"   Output: {output_flow_name}"
                candidate_info.append(provider_line + source_line + output_line)

            target_flow_obj = None
            try:
                target_flow_obj = self.client.get(o.Flow, target_flow_ref.id)
            except:
                pass

            candidate_info_str = "\n".join(candidate_info)

            prompt = f"""
You are a Life Cycle Assessment (LCA) expert. I need help selecting the best provider for a specific flow.

Target Flow Information:
- Name: {target_flow_ref.name}
- Process Context: {process_context}
- Flow Type: {getattr(target_flow_obj, 'flow_type', 'Unknown') if target_flow_obj else 'Unknown'}

Candidate Providers:
{candidate_info_str}

Please analyze which provider would be most appropriate for the target flow considering:
1. Semantic similarity of the output flow to the target flow
2. Relevance to the process context
3. Typical usage in LCA studies
4. Quality and reliability of the provider

Please return only the number (1-{len(candidate_info)}) of the best provider, or "0" if none are suitable.
"""

            response = call_llm_api(
                self.llm_clients, available_llm, prompt, max_tokens=50
            )

            import re

            match = re.search(r"\b([0-{}])\b".format(len(candidate_info)), response)
            if match:
                choice = int(match.group(1))
                if 1 <= choice <= len(candidate_providers):
                    selected_provider = candidate_providers[choice - 1]["provider"]
                    print(f"🤖 AI selected provider: {selected_provider.name}")
                    return selected_provider
                elif choice == 0:
                    print("🤖 AI found no suitable provider")
                    return None

            print(
                "⚠️ AI response could not be parsed, using provider with highest similarity"
            )
            if candidate_providers:
                best_candidate = max(candidate_providers, key=lambda x: x["similarity"])
                return best_candidate["provider"]

            return None

        except Exception as e:
            print(f"❌ AI provider evaluation failed: {e}")

            if candidate_providers:
                best_candidate = max(candidate_providers, key=lambda x: x["similarity"])
                return best_candidate["provider"]
            return None

    def create_product_system(
        self, system_spec: ProductSystem, processes_created: Dict[str, o.Ref]
    ) -> o.Ref:
        """Create product system with limited upstream process tracing to prevent model over-expansion"""
        try:

            import datetime

            original_name = system_spec.name
            existing_system = self.client.find(o.ProductSystem, original_name)
            if existing_system:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                system_spec.name = f"{original_name}_{timestamp}"
                print(f"⚠️ Product system '{original_name}' already exists")
                print(f"📝 Creating new system with timestamp: {system_spec.name}")

            ref_process_name = ""
            if (
                hasattr(system_spec, "reference_process")
                and system_spec.reference_process
            ):
                ref_process_name = system_spec.reference_process
            elif system_spec.ref_process and system_spec.ref_process.name:
                ref_process_name = system_spec.ref_process.name

            ref_process = processes_created.get(ref_process_name)
            if not ref_process:
                ref_process = self.client.find(o.Process, ref_process_name)
                if not ref_process:
                    raise ValueError(
                        f"Cannot find reference process: {ref_process_name}"
                    )

            print(
                f"🔧 Creating empty product system (no auto-linking): '{system_spec.name}' ..."
            )
            print(f"🔗 Strategy: Manual construction only")
            print(f"🎯 Depth limit: {UPSTREAM_TRACING_MAX_DEPTH} (strict control)")

            full_system = o.ProductSystem()
            full_system.name = system_spec.name
            full_system.ref_process = ref_process
            full_system.category = system_spec.category
            full_system.description = system_spec.description
            full_system.processes = []
            full_system.process_links = []

            ref_process_full = self.client.get(o.Process, ref_process.id)
            if ref_process_full and ref_process_full.exchanges:

                quant_ref_exchange = None
                first_output_exchange = None
                for exchange in ref_process_full.exchanges:
                    if not exchange.is_input:
                        if first_output_exchange is None:
                            first_output_exchange = exchange
                        if getattr(exchange, "is_quantitative_reference", False):
                            quant_ref_exchange = exchange
                            break

                target_exchange = quant_ref_exchange or first_output_exchange
                if target_exchange:
                    ref_exchange_ref = o.ExchangeRef()
                    ref_exchange_ref.internal_id = target_exchange.internal_id
                    full_system.ref_exchange = ref_exchange_ref
                    is_quant_ref = getattr(
                        target_exchange, "is_quantitative_reference", False
                    )
                    print(
                        f"🎯 Set reference exchange: {target_exchange.flow.name if target_exchange.flow else 'Unknown'} (internal_id: {target_exchange.internal_id}, is_quantitative_reference: {is_quant_ref})"
                    )

            system_ref = self.client.put(full_system)

            if system_ref:

                full_system = self.client.get(o.ProductSystem, system_ref.id)
                print(f"✅ Created empty product system with ID: {system_ref.id}")
                print(
                    f"📊 Initial process count: {len(full_system.processes) if full_system.processes else 0}"
                )

                full_system.target_amount = 1.0

                target_flow_prop_name = "Mass"
                if (
                    hasattr(system_spec, "target_flow_property")
                    and system_spec.target_flow_property
                ):
                    if isinstance(system_spec.target_flow_property, str):
                        target_flow_prop_name = system_spec.target_flow_property
                    elif hasattr(system_spec.target_flow_property, "name"):
                        target_flow_prop_name = system_spec.target_flow_property.name

                target_flow_prop = self.client.find(
                    o.FlowProperty, target_flow_prop_name
                )
                if target_flow_prop:
                    full_system.target_flow_property = target_flow_prop

                target_unit_name = "kg"
                if hasattr(system_spec, "target_unit") and system_spec.target_unit:
                    if isinstance(system_spec.target_unit, str):
                        target_unit_name = system_spec.target_unit
                    elif hasattr(system_spec.target_unit, "name"):
                        target_unit_name = system_spec.target_unit.name

                target_unit_ref = self.get_unit_ref("Units of mass", target_unit_name)
                if target_unit_ref:
                    full_system.target_unit = target_unit_ref

                if system_spec.ref_exchange:
                    ref_exchange_ref = o.ExchangeRef()
                    ref_exchange_ref.internal_id = (
                        system_spec.ref_exchange.get("internal_id", 1)
                        if isinstance(system_spec.ref_exchange, dict)
                        else getattr(system_spec.ref_exchange, "internal_id", 1)
                    )
                    full_system.ref_exchange = ref_exchange_ref

                self._report_product_system_processes(full_system)

                if SKIP_DUMMY_PROVIDERS:
                    try:
                        original_count = len(
                            getattr(full_system, "processes", []) or []
                        )
                        pruned = []
                        kept = []
                        for p in getattr(full_system, "processes", []) or []:
                            name = getattr(p, "name", "") or ""
                            try:
                                if re.search(DUMMY_PROCESS_NAME_PATTERN, name):
                                    pruned.append(p)
                                else:
                                    kept.append(p)
                            except Exception:
                                kept.append(p)
                        if pruned:
                            full_system.processes = kept
                            print(
                                f"🧹 Pruned {len(pruned)} dummy-like processes before provider inclusion (from {original_count} to {len(kept)})"
                            )
                    except Exception as e:
                        print(
                            f"⚠️ Failed to prune dummy-like processes pre-inclusion: {e}"
                        )

                print(f"\n🧹 Cleaning auto-linked background processes...")
                excel_process_ids = {ref.id for ref in processes_created.values()}

                if full_system.processes:
                    original_count = len(full_system.processes)

                    full_system.processes = [
                        p for p in full_system.processes if p.id in excel_process_ids
                    ]
                    removed_count = original_count - len(full_system.processes)
                    print(
                        f"🗑️  Removed {removed_count} auto-linked background processes"
                    )
                    print(
                        f"✅ Starting with {len(full_system.processes)} Excel processes only"
                    )

                    self.client.put(full_system)
                    print(f"💾 Saved cleaned system to openLCA")

                self._limit_provider_inclusion(full_system, processes_created)

                self.client.put(full_system)
                print(f"💾 Saved system with providers to openLCA")

                try:
                    links_created = self._rebuild_process_links(
                        full_system, processes_created
                    )
                    print(f"🔗 Rebuilt process links: {links_created} links")
                except Exception as e:
                    print(f"⚠️ Failed to rebuild process links: {e}")

                if SKIP_DUMMY_PROVIDERS:
                    try:
                        pruned_links = []
                        kept_links = []
                        for pl in getattr(full_system, "process_links", []) or []:
                            try:
                                prov = getattr(pl, "provider", None)
                                pname = getattr(prov, "name", "") or ""
                                if pname and re.search(
                                    DUMMY_PROCESS_NAME_PATTERN, pname
                                ):
                                    pruned_links.append(pl)
                                else:
                                    kept_links.append(pl)
                            except Exception:
                                kept_links.append(pl)
                        if pruned_links:
                            full_system.process_links = kept_links
                            print(
                                f"🧹 Pruned {len(pruned_links)} links to dummy-like providers"
                            )
                    except Exception as e:
                        print(f"⚠️ Failed to prune links to dummy-like providers: {e}")

                print(f"\n💾 Saving ProcessLinks to database...")
                print(
                    f"   Total ProcessLinks: {len(full_system.process_links) if full_system.process_links else 0}"
                )
                if full_system.process_links:
                    for idx, link in enumerate(full_system.process_links[:3]):
                        proc_name = getattr(
                            getattr(link, "process", None), "name", "unknown"
                        )
                        prov_name = getattr(
                            getattr(link, "provider", None), "name", "unknown"
                        )
                        flow_name = getattr(
                            getattr(link, "flow", None), "name", "unknown"
                        )
                        print(
                            f"   Link {idx+1}: {proc_name} → {flow_name} → {prov_name}"
                        )
                try:
                    self.client.put(full_system)
                    print(f"✅ ProcessLinks saved successfully")
                except Exception as e:
                    print(f"⚠️ Failed to save ProcessLinks: {e}")

                print(f"\nℹ️ 保留过程中的 default_provider 引用（不修改数据库）")

                print(f"\n💾 Final save to openLCA...")
                process_count_before_save = (
                    len(full_system.processes) if full_system.processes else 0
                )
                print(f"   - Process count before save: {process_count_before_save}")
                links_before_save = (
                    len(full_system.process_links) if full_system.process_links else 0
                )
                print(f"   - ProcessLinks before save: {links_before_save}")

                self.client.put(full_system)

                saved_system = self.client.get(o.ProductSystem, full_system.id)
                saved_count = (
                    len(saved_system.processes)
                    if saved_system and saved_system.processes
                    else 0
                )
                saved_links_count = (
                    len(saved_system.process_links)
                    if saved_system and saved_system.process_links
                    else 0
                )
                print(f"   - Process count after save: {saved_count}")
                print(f"   - ProcessLinks after save: {saved_links_count}")

                if links_before_save > 0 and saved_links_count != links_before_save:
                    print(
                        f"   ⚠️  WARNING: ProcessLinks count mismatch! ({links_before_save} → {saved_links_count})"
                    )
                    print(f"   🔧 Re-saving ProcessLinks...")
                    self.client.put(full_system)
                    saved_system = self.client.get(o.ProductSystem, full_system.id)
                    saved_links_count = (
                        len(saved_system.process_links)
                        if saved_system and saved_system.process_links
                        else 0
                    )
                    print(f"   ✅ ProcessLinks after re-save: {saved_links_count}")

                if saved_count != process_count_before_save:
                    print(
                        f"   ⚠️  WARNING: Process count mismatch! ({process_count_before_save} → {saved_count})"
                    )
                    extra_processes = saved_count - process_count_before_save
                    print(f"   ℹ️  openLCA auto-linked {extra_processes} processes!")
                    print(
                        f"   ℹ️  These auto-linked processes are treatment providers needed for waste flows"
                    )
                    print(
                        f"   ✅ KEEPING all {saved_count} processes to preserve ProcessLinks and model graph display"
                    )
                    print(
                        f"   💡 Waste flow connections will now be visible in OpenLCA Model Graph!"
                    )

                    final_system = self.client.get(o.ProductSystem, full_system.id)
                    final_links_count = (
                        len(final_system.process_links)
                        if final_system and final_system.process_links
                        else 0
                    )
                    print(f"   - Final ProcessLinks count: {final_links_count}")

                    if final_links_count >= links_before_save:
                        print(
                            f"   ✅ All ProcessLinks preserved! Waste flows should now display in Model Graph."
                        )
                    else:
                        print(
                            f"   ⚠️  ProcessLinks count decreased! Some waste flow connections may be lost."
                        )
                else:
                    print(f"   ✅ Save verified successfully!")

                print(
                    f"✅ Successfully created focused product system: {system_spec.name}"
                )
                return system_ref
            else:
                raise ValueError(f"Failed to create product system: {system_spec.name}")

        except Exception as e:
            print(f"❌ Failed to create product system '{system_spec.name}': {e}")
            raise

    def _register_excel_explicit_providers(self, process_specs: List[Process]):
        """Pre-register explicit provider relationships from Excel"""
        print("📋 Registering Excel explicit provider relationships...")

        for process_spec in process_specs:
            if hasattr(process_spec, "_simple_exchanges"):
                for exchange in process_spec._simple_exchanges:
                    is_avoided = (
                        hasattr(exchange, "is_avoided_product")
                        and exchange.is_avoided_product
                    )
                    is_explicit_output_route = (not exchange.is_input) and (
                        not is_avoided
                    )
                    needs_provider = (
                        exchange.is_input or is_avoided or is_explicit_output_route
                    )

                    if needs_provider and exchange.provider_name:
                        flow_name = exchange.flow_name
                        provider_name = exchange.provider_name
                        direction = (
                            "input_or_avoided"
                            if (exchange.is_input or is_avoided)
                            else "explicit_output"
                        )
                        key = (process_spec.name, flow_name, direction)

                        relationship = {
                            "provider_name": provider_name,
                            "flow_name": flow_name,
                            "requesting_process": process_spec.name,
                            "is_avoided_product": is_avoided,
                            "direction": direction,
                        }

                        self.excel_explicit_providers_by_key[key] = relationship

                        if flow_name not in self.excel_explicit_providers:
                            self.excel_explicit_providers[flow_name] = relationship

                        if direction == "explicit_output":
                            print(
                                f"📝 Registered explicit output route: '{process_spec.name}' output '{flow_name}' -> '{provider_name}'"
                            )
                        elif is_avoided:
                            print(
                                f"📝 Registered avoided product provider: '{flow_name}' -> '{provider_name}'"
                            )
                        else:
                            print(
                                f"📝 Registered explicit provider: '{flow_name}' -> '{provider_name}'"
                            )

        print(
            f"✅ Registered {len(self.excel_explicit_providers_by_key)} explicit provider relationships "
            f"({len(self.excel_explicit_providers)} flow-name fallbacks)"
        )

    def _get_registered_explicit_provider_info(
        self,
        process_context: str,
        flow_name: str,
        direction: str = "input_or_avoided",
    ) -> Optional[Dict[str, Any]]:
        """Get pre-registered explicit provider relationship with process-scoped priority."""
        key = (process_context, flow_name, direction)
        info = self.excel_explicit_providers_by_key.get(key)
        if info:
            return info

        return self.excel_explicit_providers.get(flow_name)

    def _resolve_pending_output_provider_links(
        self, processes_created: Dict[str, o.Ref]
    ):
        """Resolve deferred explicit output-provider routes after all processes are created."""
        if not self.pending_output_provider_links:
            return

        print(
            f"\n🔄 Resolving deferred explicit output-provider routes ({len(self.pending_output_provider_links)})..."
        )
        unresolved = []
        resolved_count = 0

        for item in self.pending_output_provider_links:
            producer_name = item.get("producer_name", "")
            provider_name = item.get("provider_name", "")
            flow_name = item.get("flow_name", "")
            exchange_internal_id = item.get("exchange_internal_id")

            producer_ref = processes_created.get(producer_name)
            provider_ref = self.created_processes.get(
                provider_name
            ) or processes_created.get(provider_name)
            if not producer_ref or not provider_ref or exchange_internal_id is None:
                unresolved.append(item)
                continue

            try:
                producer_obj = self.client.get(o.Process, producer_ref.id)
                if not producer_obj or not getattr(producer_obj, "exchanges", None):
                    unresolved.append(item)
                    continue

                target_exchange = next(
                    (
                        ex
                        for ex in producer_obj.exchanges
                        if getattr(ex, "internal_id", None) == exchange_internal_id
                    ),
                    None,
                )
                if not target_exchange:
                    unresolved.append(item)
                    continue

                target_exchange.default_provider = provider_ref
                self.client.put(producer_obj)
                resolved_count += 1
                print(
                    f"✅ Resolved explicit output route: "
                    f"'{producer_name}' output '{flow_name}' -> '{provider_name}'"
                )
            except Exception as e:
                print(
                    f"⚠️ Failed to resolve output route "
                    f"'{producer_name}'/'{flow_name}' -> '{provider_name}': {e}"
                )
                unresolved.append(item)

        self.pending_output_provider_links = unresolved
        if unresolved:
            print(f"⚠️ Unresolved explicit output routes remaining: {len(unresolved)}")
        else:
            print(f"✅ Deferred explicit output routes resolved: {resolved_count}")

    def _resolve_pending_input_provider_links(
        self,
        process_specs: List[Process],
        processes_created: Dict[str, o.Ref],
    ):
        """Re-link unresolved input providers after all processes exist."""
        print(
            "\n🔄 Re-linking unresolved input/avoided exchanges after process creation..."
        )
        relinked_count = 0
        unresolved_count = 0
        updated_process_count = 0

        for process_spec in process_specs:
            process_ref = processes_created.get(process_spec.name)
            if not process_ref:
                continue

            process_obj = self.client.get(o.Process, process_ref.id)
            if not process_obj or not getattr(process_obj, "exchanges", None):
                continue

            simple_exchanges = []
            if hasattr(process_spec, "_simple_exchanges"):
                simple_exchanges = process_spec._simple_exchanges
            elif hasattr(process_spec, "exchanges") and process_spec.exchanges:
                for ex in process_spec.exchanges:
                    if isinstance(ex, SimpleExchange):
                        simple_exchanges.append(ex)
                    else:
                        simple_exchanges.append(
                            SimpleExchange(
                                flow_name=ex.flow.name if ex.flow else "",
                                amount=ex.amount,
                                unit=ex.unit.name if ex.unit else "kg",
                                is_input=ex.is_input,
                                is_quantitative_reference=False,
                            )
                        )

            if not simple_exchanges:
                continue

            exchange_by_internal_id = {
                getattr(ex, "internal_id", None): ex
                for ex in process_obj.exchanges
                if getattr(ex, "internal_id", None) is not None
            }
            process_updated = False

            for idx, exchange_spec in enumerate(simple_exchanges, start=1):
                is_avoided = (
                    hasattr(exchange_spec, "is_avoided_product")
                    and exchange_spec.is_avoided_product
                )
                needs_provider = exchange_spec.is_input or is_avoided
                if not needs_provider:
                    continue

                target_exchange = exchange_by_internal_id.get(idx)
                if not target_exchange:
                    continue

                excel_flow_name = (
                    getattr(exchange_spec, "flow_name", "") or ""
                ).strip()
                current_provider = getattr(target_exchange, "default_provider", None)

                if excel_flow_name and self._is_excel_lifecycle_flow(excel_flow_name):
                    supplier_ref = processes_created.get(
                        excel_flow_name
                    ) or self.created_processes.get(excel_flow_name)
                    if supplier_ref:
                        current_id = (
                            getattr(current_provider, "id", None)
                            if current_provider
                            else None
                        )
                        if current_id != supplier_ref.id:
                            target_exchange.default_provider = supplier_ref
                            relinked_count += 1
                            process_updated = True
                            print(
                                f"   ↪️ Lifecycle re-link '{process_spec.name}' "
                                f"exchange#{idx} '{excel_flow_name}' → {supplier_ref.name}"
                            )
                        continue

                if current_provider:
                    continue

                exchange_location = (
                    getattr(exchange_spec, "location", "")
                    or getattr(process_obj, "location", "")
                    or ""
                )
                provider_ref, _cv_results = self.find_provider_for_flow(
                    target_exchange.flow,
                    process_spec.name,
                    getattr(exchange_spec, "provider_name", ""),
                    desired_location=exchange_location,
                    excel_flow_name=getattr(exchange_spec, "flow_name", "")
                    or target_exchange.flow.name,
                    requested_amount=getattr(target_exchange, "amount", None),
                )

                if provider_ref:
                    target_exchange.default_provider = provider_ref
                    relinked_count += 1
                    process_updated = True
                    print(
                        f"   ↪️ Re-linked '{process_spec.name}' "
                        f"exchange#{idx} '{getattr(exchange_spec, 'flow_name', target_exchange.flow.name)}' "
                        f"-> {provider_ref.name}"
                    )
                else:
                    unresolved_count += 1

            if process_updated:
                self.client.put(process_obj)
                updated_process_count += 1

        print(
            f"✅ Input provider re-link pass finished: relinked={relinked_count}, "
            f"still_unresolved={unresolved_count}, processes_updated={updated_process_count}"
        )

    def _report_product_system_processes(self, product_system: o.ProductSystem):
        """Report processes included in the product system"""
        if not product_system.processes:
            print("⚠️ No processes found in product system")
            return

        print(f"📋 Product system includes {len(product_system.processes)} processes:")
        for i, process_ref in enumerate(product_system.processes, 1):
            print(f"  {i}. {process_ref.name}")

    def _ensure_all_providers_included(
        self, product_system: o.ProductSystem, processes_created: Dict[str, o.Ref]
    ):
        """Ensure upstream provider processes are included with STRICT depth control"""
        try:
            print(
                f"🔍 Checking upstream providers with STRICT control (UPSTREAM_TRACING_MAX_DEPTH: {UPSTREAM_TRACING_MAX_DEPTH})..."
            )
            print(f"📋 NEW RULES:")
            print(f"   1. Excel processes: Add direct providers only (depth 1)")
            if DISABLE_BACKGROUND_UPSTREAM_TRACING:
                print(
                    f"   2. Background providers: NEVER trace upstream (DISABLE_BACKGROUND_UPSTREAM_TRACING=True)"
                )
            else:
                print(
                    f"   2. Background providers: STOP immediately (no further expansion)"
                )
            print(f"   3. Market processes: Preferred and treated as cutoff points")
            print(
                f"   4. Max depth setting: {UPSTREAM_TRACING_MAX_DEPTH} (for explicit providers only)"
            )

            current_process_ids = (
                {p.id for p in product_system.processes}
                if product_system.processes
                else set()
            )
            excel_process_names = set(processes_created.keys())

            excel_process_ids = {
                processes_created[name].id for name in excel_process_names
            }

            non_explicit_background_providers = set()

            added_any = True
            depth_level = 0

            max_depth = max(1, UPSTREAM_TRACING_MAX_DEPTH)

            while added_any and depth_level < max_depth:
                depth_level += 1
                added_any = False
                missing_providers = []

                print(f"📊 Processing depth level {depth_level}...")

                current_processes = (
                    list(product_system.processes) if product_system.processes else []
                )

                for process_name, process_ref in processes_created.items():
                    if process_ref.id not in current_process_ids:
                        current_processes.append(process_ref)

                for process_ref in current_processes:
                    try:
                        process_obj = self.client.get(o.Process, process_ref.id)
                        if not process_obj or not process_obj.exchanges:
                            continue

                        is_excel_process = process_ref.id in excel_process_ids

                        if not is_excel_process:

                            if DISABLE_BACKGROUND_UPSTREAM_TRACING:

                                continue

                            elif (
                                depth_level >= UPSTREAM_TRACING_MAX_DEPTH
                                and UPSTREAM_TRACING_MAX_DEPTH > 0
                            ):
                                continue

                        for exchange in process_obj.exchanges:
                            is_explicit_output_route = (
                                (not exchange.is_input)
                                and (not getattr(exchange, "is_avoided_product", False))
                                and bool(getattr(exchange, "default_provider", None))
                                and getattr(
                                    getattr(exchange, "default_provider", None),
                                    "id",
                                    None,
                                )
                                in excel_process_ids
                            )
                            needs_provider = (
                                exchange.is_input
                                or getattr(exchange, "is_avoided_product", False)
                                or is_explicit_output_route
                            )

                            flow_ref = getattr(exchange, "flow", None)
                            flow_name = (
                                getattr(flow_ref, "name", "") if flow_ref else ""
                            )

                            is_quantitative_ref = getattr(
                                exchange, "is_quantitative_reference", False
                            )

                            if (
                                ENABLE_WASTE_FLOW_LINKING
                                and is_excel_process
                                and flow_ref
                                and not exchange.is_input
                                and not getattr(exchange, "is_avoided_product", False)
                                and not is_quantitative_ref
                                and not exchange.default_provider
                                and depth_level <= max(1, WASTE_FLOW_MAX_DEPTH)
                            ):
                                flow_obj = None
                                try:
                                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                                except Exception:
                                    flow_obj = None
                                flow_display_name = (
                                    getattr(flow_obj, "name", "") or flow_name
                                )
                                flow_type = self._determine_flow_type(flow_obj)
                                flow_name_lower = (flow_display_name or "").lower()
                                waste_keywords = [
                                    "waste",
                                    "wastewater",
                                    "sludge",
                                    "residue",
                                    "ash",
                                    "scrap",
                                    "disposed",
                                    "disposal",
                                    "treatment",
                                    "landfill",
                                    "municipal solid",
                                    "worn out",
                                ]
                                is_waste_flow = flow_type.endswith("WASTE_FLOW") or any(
                                    k in flow_name_lower for k in waste_keywords
                                )

                                if is_waste_flow:

                                    excel_treater_ref = self._find_excel_waste_treater(
                                        flow_display_name,
                                        exclude_process_id=process_ref.id,
                                    )
                                    if excel_treater_ref is not None:
                                        exchange.default_provider = excel_treater_ref
                                        try:
                                            self.client.put(process_obj)
                                            print(
                                                f"♻️  Found Excel-defined treater for waste "
                                                f"'{flow_display_name}': {excel_treater_ref.name}"
                                            )
                                            print(
                                                f"✅ Linked waste output '{flow_display_name}' to "
                                                f"Excel treater"
                                            )
                                        except Exception as e:
                                            print(
                                                f"⚠️ Failed to persist Excel waste treater for "
                                                f"'{flow_display_name}': {e}"
                                            )
                                        needs_provider = True
                                        flow_name = flow_name or flow_display_name
                                    else:

                                        try:
                                            providers = self.client.get_providers(
                                                flow_ref
                                            )
                                            if providers:

                                                provider_ref = None

                                                treatment_pattern = re.compile(
                                                    r"(?i)(treatment|disposal|recycling|landfill|incineration)"
                                                )
                                                for prov in providers:
                                                    if treatment_pattern.search(
                                                        prov.provider.name
                                                    ):
                                                        provider_ref = prov.provider
                                                        print(
                                                            f"🗑️ Found treatment provider for waste '{flow_display_name}': {provider_ref.name}"
                                                        )
                                                        break

                                                if (
                                                    not provider_ref
                                                    and PREFER_MARKET_PROCESSES
                                                ):
                                                    market_pattern = re.compile(
                                                        MARKET_PROCESS_PATTERN
                                                    )
                                                    for prov in providers:
                                                        if market_pattern.search(
                                                            prov.provider.name
                                                        ):
                                                            provider_ref = prov.provider
                                                            print(
                                                                f"🏪 Found market provider for waste '{flow_display_name}': {provider_ref.name}"
                                                            )
                                                            break

                                                if not provider_ref:
                                                    provider_ref = providers[0].provider
                                                    print(
                                                        f"🗑️ Found waste provider for '{flow_display_name}': {provider_ref.name}"
                                                    )

                                                if (
                                                    provider_ref
                                                    and getattr(
                                                        provider_ref, "id", None
                                                    )
                                                    == process_ref.id
                                                ):
                                                    print(
                                                        f"⏭️ Skip self waste provider for '{flow_display_name}': "
                                                        f"{getattr(process_ref, 'name', '?')} -> {getattr(provider_ref, 'name', '?')}"
                                                    )
                                                    provider_ref = None

                                                if provider_ref:
                                                    exchange.default_provider = (
                                                        provider_ref
                                                    )
                                                    try:
                                                        self.client.put(process_obj)
                                                        print(
                                                            f"✅ Linked waste output '{flow_display_name}' to treatment provider"
                                                        )
                                                    except Exception as e:
                                                        print(
                                                            f"⚠️ Failed to persist waste provider for '{flow_display_name}': {e}"
                                                        )
                                                    needs_provider = True
                                                    flow_name = (
                                                        flow_name or flow_display_name
                                                    )
                                            else:
                                                print(
                                                    f"⚠️ No treatment provider found for waste flow '{flow_display_name}'"
                                                )
                                        except Exception as e:
                                            print(
                                                f"⚠️ Error finding waste treatment provider for '{flow_display_name}': {e}"
                                            )

                            if needs_provider and exchange.default_provider:
                                provider_id = exchange.default_provider.id
                                provider_name = (
                                    getattr(exchange.default_provider, "name", "") or ""
                                )
                                is_provider_excel = provider_id in excel_process_ids

                                is_waste_provider = False
                                if not exchange.is_input and not getattr(
                                    exchange, "is_avoided_product", False
                                ):
                                    flow_ref_local = getattr(exchange, "flow", None)
                                    if flow_ref_local:
                                        try:
                                            flow_obj_local = self.client.get(
                                                o.Flow, flow_ref_local.id
                                            )
                                            if flow_obj_local:
                                                flow_type_local = (
                                                    self._determine_flow_type(
                                                        flow_obj_local
                                                    )
                                                )
                                                flow_name_lower_local = (
                                                    getattr(flow_obj_local, "name", "")
                                                    or ""
                                                ).lower()
                                                waste_keywords_local = [
                                                    "waste",
                                                    "wastewater",
                                                    "sludge",
                                                    "residue",
                                                    "ash",
                                                    "scrap",
                                                    "disposed",
                                                    "disposal",
                                                    "treatment",
                                                    "landfill",
                                                    "municipal solid",
                                                    "worn out",
                                                ]
                                                is_waste_provider = (
                                                    flow_type_local.endswith(
                                                        "WASTE_FLOW"
                                                    )
                                                    or any(
                                                        k in flow_name_lower_local
                                                        for k in waste_keywords_local
                                                    )
                                                )
                                        except Exception:
                                            pass

                                if SKIP_DUMMY_PROVIDERS:
                                    try:
                                        if re.search(
                                            DUMMY_PROCESS_NAME_PATTERN,
                                            provider_name or "",
                                        ):

                                            continue
                                    except Exception:

                                        pass

                                if provider_id not in current_process_ids:

                                    if (
                                        is_provider_excel
                                        and ENABLE_UNLIMITED_EXCEL_LINKING
                                    ):
                                        missing_providers.append(
                                            exchange.default_provider
                                        )
                                        current_process_ids.add(provider_id)
                                        added_any = True
                                        if getattr(
                                            exchange, "is_avoided_product", False
                                        ):
                                            print(
                                                f"🔄 Added avoided product provider: {exchange.default_provider.name}"
                                            )
                                        elif is_explicit_output_route:
                                            print(
                                                f"🔗 Added explicit output-route provider: {exchange.default_provider.name}"
                                            )
                                        else:
                                            print(
                                                f"✅ Added Excel provider: {exchange.default_provider.name}"
                                            )

                                    elif (
                                        is_waste_provider and ENABLE_WASTE_FLOW_LINKING
                                    ):
                                        missing_providers.append(
                                            exchange.default_provider
                                        )
                                        current_process_ids.add(provider_id)
                                        added_any = True
                                        non_explicit_background_providers.add(
                                            provider_id
                                        )
                                        print(
                                            f"🗑️ Added waste treatment provider: {exchange.default_provider.name}"
                                        )
                                        print(
                                            f"   For waste flow: {flow_name or 'unknown'} (output from {process_name})"
                                        )

                                    elif (
                                        not is_provider_excel
                                        and is_excel_process
                                        and depth_level == 1
                                    ):
                                        missing_providers.append(
                                            exchange.default_provider
                                        )
                                        current_process_ids.add(provider_id)
                                        added_any = True

                                        non_explicit_background_providers.add(
                                            provider_id
                                        )

                                        if getattr(
                                            exchange, "is_avoided_product", False
                                        ):
                                            print(
                                                f"🔄 Added avoided product provider (STOP HERE - no upstream): {exchange.default_provider.name}"
                                            )
                                        else:
                                            import re

                                            market_pattern = re.compile(
                                                MARKET_PROCESS_PATTERN
                                            )
                                            if market_pattern.search(provider_name):
                                                print(
                                                    f"🏪 Added market provider (STOP HERE - no upstream): {exchange.default_provider.name}"
                                                )
                                            else:
                                                print(
                                                    f"🔗 Added background provider (STOP HERE - no upstream): {exchange.default_provider.name}"
                                                )
                                    elif not is_provider_excel and not is_excel_process:

                                        if DISABLE_BACKGROUND_UPSTREAM_TRACING:
                                            if getattr(
                                                exchange, "is_avoided_product", False
                                            ):
                                                print(
                                                    f"⏹️ Skipped avoided product provider (background-to-background disabled): {exchange.default_provider.name}"
                                                )
                                            else:
                                                print(
                                                    f"⏹️ Skipped background provider (background-to-background disabled): {exchange.default_provider.name}"
                                                )
                                        else:

                                            if (
                                                depth_level > 1
                                                and UPSTREAM_TRACING_MAX_DEPTH > 0
                                            ):
                                                missing_providers.append(
                                                    exchange.default_provider
                                                )
                                                current_process_ids.add(provider_id)
                                                added_any = True
                                                print(
                                                    f"🔗 Added background-to-background provider: {exchange.default_provider.name}"
                                                )
                                            else:
                                                if getattr(
                                                    exchange,
                                                    "is_avoided_product",
                                                    False,
                                                ):
                                                    print(
                                                        f"⏹️ Skipped avoided product provider (depth limit): {exchange.default_provider.name}"
                                                    )
                                                else:
                                                    print(
                                                        f"⏹️ Skipped background provider (depth limit): {exchange.default_provider.name}"
                                                    )

                    except Exception as e:
                        continue

                if missing_providers:
                    if not product_system.processes:
                        product_system.processes = []

                    for provider in missing_providers:
                        product_system.processes.append(provider)

            total_processes = (
                len(product_system.processes) if product_system.processes else 0
            )
            excel_count = sum(
                1 for p in product_system.processes if p.id in excel_process_ids
            )
            background_count = total_processes - excel_count
            stopped_count = len(non_explicit_background_providers)

            print(f"✅ STRICT upstream tracing completed!")
            print(
                f"📊 System contains {total_processes} processes ({excel_count} Excel, {background_count} background)"
            )
            print(
                f"🛑 Stopped expansion at {stopped_count} non-explicit background providers"
            )

        except Exception as e:
            print(f"❌ Error in provider inclusion: {e}")

    def _rebuild_process_links(
        self,
        product_system: o.ProductSystem,
        processes_created: Dict[str, o.Ref] = None,
    ) -> int:
        """Rebuild process links in the given product system by connecting each"""
        if product_system is None:
            return 0

        if (
            not hasattr(product_system, "process_links")
            or product_system.process_links is None
        ):
            product_system.process_links = []

        links_before = len(product_system.process_links)

        excel_process_ids = set()
        if processes_created:
            excel_process_ids = {proc_ref.id for proc_ref in processes_created.values()}

        existing_keys = set()
        for pl in product_system.process_links:
            try:

                exchange_ref = getattr(pl, "exchange", None)
                internal_id = (
                    getattr(exchange_ref, "internal_id", None) if exchange_ref else None
                )

                key = (
                    getattr(getattr(pl, "process", None), "id", None),
                    getattr(getattr(pl, "provider", None), "id", None),
                    internal_id,
                )
                existing_keys.add(key)
            except Exception:
                continue

        processes = getattr(product_system, "processes", []) or []

        for proc_ref in processes:
            try:
                proc_obj = self.client.get(o.Process, proc_ref.id)
                if not proc_obj or not getattr(proc_obj, "exchanges", None):
                    continue

                is_excel_process = proc_ref.id in excel_process_ids

                if DISABLE_BACKGROUND_UPSTREAM_TRACING and not is_excel_process:

                    continue

                for exch in proc_obj.exchanges:

                    is_input = getattr(exch, "is_input", False)
                    is_avoided = getattr(exch, "is_avoided_product", False)

                    is_waste_output = False
                    is_quantitative_ref = getattr(
                        exch, "is_quantitative_reference", False
                    )

                    if (
                        not is_input
                        and not is_quantitative_ref
                        and getattr(exch, "default_provider", None)
                    ):
                        flow_ref = getattr(exch, "flow", None)
                        if flow_ref:
                            try:
                                flow_obj = self.client.get(o.Flow, flow_ref.id)
                                if flow_obj:
                                    flow_type = self._determine_flow_type(flow_obj)
                                    flow_name_lower = (
                                        getattr(flow_obj, "name", "") or ""
                                    ).lower()
                                    waste_keywords = [
                                        "waste",
                                        "wastewater",
                                        "sludge",
                                        "residue",
                                        "ash",
                                        "scrap",
                                        "disposed",
                                        "disposal",
                                        "treatment",
                                        "landfill",
                                        "municipal solid",
                                        "worn out",
                                    ]
                                    is_waste_output = flow_type.endswith(
                                        "WASTE_FLOW"
                                    ) or any(
                                        k in flow_name_lower for k in waste_keywords
                                    )
                            except Exception:
                                pass

                    provider_ref = getattr(exch, "default_provider", None)
                    provider_id = (
                        getattr(provider_ref, "id", None) if provider_ref else None
                    )
                    is_explicit_output_route = (
                        (not is_input)
                        and (not is_avoided)
                        and (not is_quantitative_ref)
                        and bool(provider_ref)
                        and (provider_id in excel_process_ids)
                    )
                    needs_provider = (
                        is_input
                        or is_avoided
                        or is_waste_output
                        or is_explicit_output_route
                    )

                    if not needs_provider:
                        continue
                    if not getattr(exch, "default_provider", None):
                        continue

                    provider_ref = exch.default_provider

                    if SKIP_DUMMY_PROVIDERS:
                        try:
                            prov_name = getattr(provider_ref, "name", "") or ""
                            if re.search(DUMMY_PROCESS_NAME_PATTERN, prov_name):

                                continue
                        except Exception:
                            pass
                    flow_ref = getattr(exch, "flow", None)
                    internal_id = getattr(exch, "internal_id", None)

                    if not provider_ref or not internal_id:
                        continue

                    if provider_ref.id == proc_ref.id:
                        print(
                            f"⏭️ Skip self ProcessLink: {getattr(proc_ref, 'name', '?')} "
                            f"→ {getattr(flow_ref, 'name', 'unknown') if flow_ref else 'unknown'} "
                            f"→ {getattr(provider_ref, 'name', '?')}"
                        )
                        continue

                    key = (proc_ref.id, provider_ref.id, internal_id)
                    if key in existing_keys:
                        continue

                    link = o.ProcessLink()

                    process_link_ref = o.Ref()
                    process_link_ref.id = proc_ref.id
                    process_link_ref.name = getattr(proc_ref, "name", "")
                    link.process = process_link_ref

                    provider_link_ref = o.Ref()
                    provider_link_ref.id = provider_ref.id
                    provider_link_ref.name = getattr(provider_ref, "name", "")
                    link.provider = provider_link_ref

                    if flow_ref is not None:
                        flow_link_ref = o.Ref()
                        flow_link_ref.id = getattr(flow_ref, "id", "")
                        flow_link_ref.name = getattr(flow_ref, "name", "")
                        link.flow = flow_link_ref

                    ex_ref = o.ExchangeRef()
                    ex_ref.internal_id = internal_id
                    link.exchange = ex_ref

                    product_system.process_links.append(link)
                    existing_keys.add(key)

                    if is_waste_output:
                        flow_name = (
                            getattr(flow_ref, "name", "unknown")
                            if flow_ref
                            else "unknown"
                        )
                        print(
                            f"   ✅ Waste flow ProcessLink created: {getattr(proc_ref, 'name', '?')} → {flow_name} → {getattr(provider_ref, 'name', '?')}"
                        )
                    elif is_explicit_output_route:
                        flow_name = (
                            getattr(flow_ref, "name", "unknown")
                            if flow_ref
                            else "unknown"
                        )
                        print(
                            f"   ✅ Explicit output ProcessLink created: {getattr(proc_ref, 'name', '?')} → {flow_name} → {getattr(provider_ref, 'name', '?')}"
                        )

            except Exception as e:

                print(
                    f"⚠️ Error while building links for process '{getattr(proc_ref, 'name', 'Unknown')}': {e}"
                )
                continue

        return len(product_system.process_links) - links_before

    def _limit_provider_inclusion(
        self, product_system: o.ProductSystem, processes_created: Dict[str, o.Ref]
    ):
        """Add provider processes to the product system with STRICT depth control."""
        try:
            print(
                f"🔍 Adding provider processes with STRICT control (UPSTREAM_TRACING_MAX_DEPTH: {UPSTREAM_TRACING_MAX_DEPTH})..."
            )
            print(f"📋 STRICT RULES:")
            print(f"   1. Excel processes: Add direct providers only (depth 1)")
            print(
                f"   2. Background providers: STOP immediately (no further expansion)"
            )
            print(f"   3. Market processes: Preferred and treated as cutoff points")

            if not product_system.processes:
                product_system.processes = []

            current_process_ids = {p.id for p in product_system.processes}
            excel_process_names = set(processes_created.keys())
            excel_process_ids = {
                processes_created[name].id for name in excel_process_names
            }

            added_any = True
            depth_level = 0

            max_depth = max(1, UPSTREAM_TRACING_MAX_DEPTH)

            while added_any and depth_level < max_depth:
                depth_level += 1
                added_any = False
                new_providers = []

                print(f"📊 Processing provider depth level {depth_level}...")

                current_processes = list(product_system.processes)

                for process_name, process_ref in processes_created.items():
                    if process_ref.id not in current_process_ids:
                        current_processes.append(process_ref)
                        current_process_ids.add(process_ref.id)
                        new_providers.append(process_ref)
                        added_any = True
                        print(f"✅ Added Excel process to system: {process_name}")

                for process_ref in current_processes:
                    try:
                        process_obj = self.client.get(o.Process, process_ref.id)
                        if not process_obj or not process_obj.exchanges:
                            continue

                        is_excel_process = process_ref.id in excel_process_ids

                        if not is_excel_process:

                            continue

                        for exchange in process_obj.exchanges:
                            is_explicit_output_route = (
                                (not exchange.is_input)
                                and (not getattr(exchange, "is_avoided_product", False))
                                and bool(getattr(exchange, "default_provider", None))
                                and getattr(
                                    getattr(exchange, "default_provider", None),
                                    "id",
                                    None,
                                )
                                in excel_process_ids
                            )
                            needs_provider = (
                                exchange.is_input
                                or getattr(exchange, "is_avoided_product", False)
                                or is_explicit_output_route
                            )

                            flow_ref = getattr(exchange, "flow", None)
                            flow_name = (
                                getattr(flow_ref, "name", "") if flow_ref else ""
                            )

                            is_quantitative_ref = getattr(
                                exchange, "is_quantitative_reference", False
                            )

                            if (
                                ENABLE_WASTE_FLOW_LINKING
                                and is_excel_process
                                and flow_ref
                                and not exchange.is_input
                                and not getattr(exchange, "is_avoided_product", False)
                                and not is_quantitative_ref
                                and not exchange.default_provider
                                and depth_level <= max(1, WASTE_FLOW_MAX_DEPTH)
                            ):
                                flow_obj = None
                                try:
                                    flow_obj = self.client.get(o.Flow, flow_ref.id)
                                except Exception:
                                    flow_obj = None
                                flow_display_name = (
                                    getattr(flow_obj, "name", "") or flow_name
                                )
                                flow_type = self._determine_flow_type(flow_obj)
                                flow_name_lower = (flow_display_name or "").lower()
                                waste_keywords = [
                                    "waste",
                                    "wastewater",
                                    "sludge",
                                    "residue",
                                    "ash",
                                    "scrap",
                                    "disposed",
                                    "disposal",
                                    "treatment",
                                    "landfill",
                                    "municipal solid",
                                    "worn out",
                                ]
                                is_waste_flow = flow_type.endswith("WASTE_FLOW") or any(
                                    k in flow_name_lower for k in waste_keywords
                                )

                                if is_waste_flow:

                                    excel_treater_ref = self._find_excel_waste_treater(
                                        flow_display_name,
                                        exclude_process_id=process_ref.id,
                                    )
                                    if excel_treater_ref is not None:
                                        exchange.default_provider = excel_treater_ref
                                        try:
                                            self.client.put(process_obj)
                                            print(
                                                f"♻️  Found Excel-defined treater for waste "
                                                f"'{flow_display_name}': {excel_treater_ref.name}"
                                            )
                                            print(
                                                f"✅ Linked waste output '{flow_display_name}' to "
                                                f"Excel treater"
                                            )
                                        except Exception as e:
                                            print(
                                                f"⚠️ Failed to persist Excel waste treater for "
                                                f"'{flow_display_name}': {e}"
                                            )
                                        needs_provider = True
                                        flow_name = flow_name or flow_display_name
                                    else:

                                        try:
                                            providers = self.client.get_providers(
                                                flow_ref
                                            )
                                            if providers:

                                                provider_ref = None

                                                treatment_pattern = re.compile(
                                                    r"(?i)(treatment|disposal|recycling|landfill|incineration)"
                                                )
                                                for prov in providers:
                                                    if treatment_pattern.search(
                                                        prov.provider.name
                                                    ):
                                                        provider_ref = prov.provider
                                                        print(
                                                            f"🗑️ Found treatment provider for waste '{flow_display_name}': {provider_ref.name}"
                                                        )
                                                        break

                                                if (
                                                    not provider_ref
                                                    and PREFER_MARKET_PROCESSES
                                                ):
                                                    market_pattern = re.compile(
                                                        MARKET_PROCESS_PATTERN
                                                    )
                                                    for prov in providers:
                                                        if market_pattern.search(
                                                            prov.provider.name
                                                        ):
                                                            provider_ref = prov.provider
                                                            print(
                                                                f"🏪 Found market provider for waste '{flow_display_name}': {provider_ref.name}"
                                                            )
                                                            break

                                                if not provider_ref:
                                                    provider_ref = providers[0].provider
                                                    print(
                                                        f"🗑️ Found waste provider for '{flow_display_name}': {provider_ref.name}"
                                                    )

                                                if provider_ref:
                                                    exchange.default_provider = (
                                                        provider_ref
                                                    )
                                                    try:
                                                        self.client.put(process_obj)
                                                        print(
                                                            f"✅ Linked waste output '{flow_display_name}' to treatment provider"
                                                        )
                                                    except Exception as e:
                                                        print(
                                                            f"⚠️ Failed to persist waste provider for '{flow_display_name}': {e}"
                                                        )
                                                    needs_provider = True
                                                    flow_name = (
                                                        flow_name or flow_display_name
                                                    )
                                            else:
                                                print(
                                                    f"⚠️ No treatment provider found for waste flow '{flow_display_name}'"
                                                )
                                        except Exception as e:
                                            print(
                                                f"⚠️ Error finding waste treatment provider for '{flow_display_name}': {e}"
                                            )

                            if needs_provider and exchange.default_provider:
                                provider_id = exchange.default_provider.id
                                provider_name = (
                                    getattr(exchange.default_provider, "name", "") or ""
                                )
                                is_provider_excel = provider_id in excel_process_ids

                                if SKIP_DUMMY_PROVIDERS:
                                    try:
                                        if re.search(
                                            DUMMY_PROCESS_NAME_PATTERN,
                                            provider_name or "",
                                        ):
                                            continue
                                    except Exception:
                                        pass

                                if provider_id not in current_process_ids:

                                    if (
                                        is_provider_excel
                                        and ENABLE_UNLIMITED_EXCEL_LINKING
                                    ):
                                        new_providers.append(exchange.default_provider)
                                        current_process_ids.add(provider_id)
                                        added_any = True
                                        if getattr(
                                            exchange, "is_avoided_product", False
                                        ):
                                            print(
                                                f"🔄 Added avoided product provider: {exchange.default_provider.name}"
                                            )
                                        elif is_explicit_output_route:
                                            print(
                                                f"🔗 Added explicit output-route provider: {exchange.default_provider.name}"
                                            )
                                        else:
                                            print(
                                                f"✅ Added Excel provider: {exchange.default_provider.name}"
                                            )

                                    elif not is_provider_excel and depth_level == 1:
                                        new_providers.append(exchange.default_provider)
                                        current_process_ids.add(provider_id)
                                        added_any = True
                                        if getattr(
                                            exchange, "is_avoided_product", False
                                        ):
                                            print(
                                                f"🔄 Added avoided product provider (STOP HERE): {exchange.default_provider.name}"
                                            )
                                        else:

                                            import re

                                            market_pattern = re.compile(
                                                MARKET_PROCESS_PATTERN
                                            )
                                            if market_pattern.search(provider_name):
                                                print(
                                                    f"🏪 Added market provider (STOP HERE): {exchange.default_provider.name}"
                                                )
                                            else:
                                                print(
                                                    f"🔗 Added background provider (STOP HERE): {exchange.default_provider.name}"
                                                )

                    except Exception as e:
                        print(
                            f"⚠️ Error processing providers for process '{getattr(process_ref, 'name', 'Unknown')}': {e}"
                        )
                        continue

                for provider in new_providers:
                    if provider not in product_system.processes:
                        product_system.processes.append(provider)

            total_processes = len(product_system.processes)
            excel_count = sum(
                1 for p in product_system.processes if p.id in excel_process_ids
            )
            background_count = total_processes - excel_count

            print(f"✅ Provider inclusion completed with depth control!")
            print(
                f"📊 System contains {total_processes} processes ({excel_count} Excel, {background_count} background)"
            )

        except Exception as e:
            print(f"❌ Error in provider inclusion: {e}")

    def _expand_system_with_background_processes(self, product_system: o.ProductSystem):
        """No-op method to prevent over-expansion of background processes"""
        print("⏭️ Skipping background process expansion to maintain focused model")
        print(
            "💡 To enable background process expansion, uncomment relevant code in create_product_system"
        )

    def _display_impact_method_info(self, impact_method_ref: o.Ref):
        """Display detailed information about the selected impact assessment method"""
        try:
            print(f"\n📊 Impact Assessment Method Details:")
            print(f"📋 Name: {impact_method_ref.name}")
            print(f"📁 Category: {impact_method_ref.category or 'Uncategorized'}")

            try:
                full_method = self.client.get(o.ImpactMethod, impact_method_ref.id)
                if full_method:
                    if full_method.description:
                        print(
                            f"📝 Description: {full_method.description[:200]}{'...' if len(full_method.description) > 200 else ''}"
                        )

                    if full_method.impact_categories:
                        print(
                            f"🎯 Impact Categories: {len(full_method.impact_categories)}"
                        )
                        for i, cat_ref in enumerate(
                            full_method.impact_categories[:5], 1
                        ):
                            unit_info = (
                                f" ({cat_ref.ref_unit})"
                                if hasattr(cat_ref, "ref_unit") and cat_ref.ref_unit
                                else ""
                            )
                            print(f"   {i}. {cat_ref.name}{unit_info}")
                        if len(full_method.impact_categories) > 5:
                            print(
                                f"   ... and {len(full_method.impact_categories) - 5} more categories"
                            )

            except Exception as e:
                print(f"⚠️ Cannot get detailed information: {e}")

            print("-" * 50)

        except Exception as e:
            print(f"❌ Error displaying impact method info: {e}")

    def build_lca_case(self, lca_case: LCACase) -> Dict[str, Any]:
        """Build complete LCA case"""
        print(f"\n🚀 Starting to build LCA case: {lca_case.case_name}")
        print(f"📝 Description: {lca_case.description}")
        print("=" * 60)

        print(f"\n📋 Step 5.0: Pre-register Excel explicit providers...")
        self._register_excel_explicit_providers(lca_case.processes)
        self.excel_process_names = {
            p.name.strip()
            for p in lca_case.processes
            if getattr(p, "name", None) and str(p.name).strip()
        }
        if self.excel_process_names:
            print(
                f"📋 Registered {len(self.excel_process_names)} Excel process names "
                f"for lifecycle foreground hand-off"
            )
        self.parsed_flow_metadata = getattr(lca_case, "flow_metadata", {})
        self.process_provider_metadata = getattr(
            lca_case, "process_provider_metadata", {}
        )

        results = {"flows": {}, "processes": {}, "product_systems": {}}

        try:

            print(f"\n📋 Step 5.1: Identify all required flows...")
            all_required_flows = set()

            for flow_spec in lca_case.flows:
                all_required_flows.add(flow_spec.name)

            for process_spec in lca_case.processes:
                if hasattr(process_spec, "_simple_exchanges"):
                    for exchange in process_spec._simple_exchanges:
                        all_required_flows.add(exchange.flow_name)
                elif hasattr(process_spec, "exchanges") and process_spec.exchanges:
                    for exchange in process_spec.exchanges:
                        if hasattr(exchange, "flow_name"):
                            all_required_flows.add(exchange.flow_name)
                        elif hasattr(exchange, "flow") and exchange.flow:
                            all_required_flows.add(exchange.flow.name)

            print(f"🔍 Identified {len(all_required_flows)} unique flow requirements")

            flow_specs_dict = {fs.name: fs for fs in lca_case.flows}
            for flow_name in all_required_flows:
                if flow_name not in flow_specs_dict:
                    flow_specs_dict[flow_name] = Flow(
                        name=flow_name,
                        category=lca_case.category,
                        description=f"Auto-generated flow specification for: {flow_name}",
                    )

            for flow_name, flow_spec in flow_specs_dict.items():
                if not flow_name or len(flow_name.strip()) == 0:
                    continue

                flow_ref = self.get_or_create_flow(flow_spec, create_if_missing=True)
                if flow_ref:
                    results["flows"][flow_name] = flow_ref

            if (
                self._stage_geography_cache is None
                and self.enable_lifecycle_stage_classification
                and self.project_context
                and self.project_context.system_boundary
                and self.project_context.system_boundary.description
                and self.llm_clients
            ):
                from .uncertainty import llm_extract_stage_geography_mapping

                _all_proc_names = [p.name for p in lca_case.processes]
                print(f"🌍 预提取地理映射：使用LLM分析系统边界中各阶段的地理位置...")
                self._stage_geography_cache = llm_extract_stage_geography_mapping(
                    self.project_context.system_boundary.description,
                    self.llm_clients,
                    _all_proc_names,
                )
                if not self._stage_geography_cache:
                    self._stage_geography_cache = {}

            for process_spec in lca_case.processes:
                process_ref = self.create_process(process_spec, results["flows"])
                if process_ref:
                    results["processes"][process_spec.name] = process_ref

            self._resolve_pending_output_provider_links(results["processes"])

            self._resolve_pending_input_provider_links(
                lca_case.processes, results["processes"]
            )

            for system_spec in lca_case.product_systems:
                system_ref = self.create_product_system(
                    system_spec, results["processes"]
                )
                if system_ref:
                    results["product_systems"][system_spec.name] = system_ref

            print(
                f"\n✅ LCA case construction completed with {len(results['flows'])} flows, {len(results['processes'])} processes, {len(results['product_systems'])} systems"
            )

            return results

        except Exception as e:
            print(f"❌ Error building LCA case: {e}")
            import traceback

            traceback.print_exc()
            raise

    def calculate_results(
        self, product_system_name: str, impact_method_name: str = None
    ) -> Dict[str, Any]:
        """Calculate LCA results"""
        try:
            print(
                f"\n📊 Preparing to calculate product system results: {product_system_name}"
            )

            system_ref = self.client.find(o.ProductSystem, product_system_name)
            if not system_ref:
                print(f"❌ Cannot find product system: {product_system_name}")
                return None

            impact_method = self.select_impact_method(
                product_system_name,
                "Life cycle impact assessment calculation",
                impact_method_name,
            )

            if not impact_method:
                print("❌ No available impact assessment methods")
                return None

            self._display_impact_method_info(impact_method)

            print(f"\n🧮 Calculating product system: {product_system_name}")

            setup = o.CalculationSetup(target=system_ref, impact_method=impact_method)

            setup.allocation = o.AllocationType.USE_DEFAULT_ALLOCATION

            result = self.client.calculate(setup)
            result.wait_until_ready()

            impacts = result.get_total_impacts()

            total_impacts = []
            for impact in impacts:
                if impact.impact_category:
                    total_impacts.append(
                        {
                            "category": impact.impact_category.name,
                            "value": impact.amount,
                            "unit": impact.impact_category.ref_unit,
                        }
                    )

            results_dict = {
                "product_system": product_system_name,
                "impact_method": impact_method.name,
                "total_impacts": total_impacts,
            }

            print(f"\n" + "=" * 80)
            print(f" {product_system_name} - LCA Results Report")
            print(f" Impact Assessment Method: {impact_method.name}")
            print("=" * 80)
            print(f"{'Impact Category':<45}{'Value':<20}{'Unit':<15}")
            print("-" * 80)

            for impact_data in total_impacts:
                category_name = impact_data["category"]
                value = impact_data["value"]
                unit = impact_data["unit"]

                if len(category_name) > 43:
                    category_name = category_name[:40] + "..."

                print(f"{category_name:<45}{value:<20.4e}{unit:<15}")

            print("=" * 80)

            if DIAGNOSTIC_SHOW_SCALING_FACTORS:
                try:
                    print(f"\n🔍 DIAGNOSTIC: DETERMINISTIC Process Scaling Factors")
                    print("=" * 80)
                    scaling_factors = result.get_scaling_factors()
                    if scaling_factors:
                        print(f"📊 Total processes: {len(scaling_factors)}")

                        sf_list = []
                        for tech_flow in scaling_factors:
                            if hasattr(tech_flow, "provider") and tech_flow.provider:
                                process_name = getattr(
                                    tech_flow.provider, "name", "Unknown"
                                )[:55]
                                scaling_value = tech_flow.amount
                                sf_list.append((process_name, scaling_value))

                        sf_sorted = sorted(
                            sf_list, key=lambda x: abs(x[1]), reverse=True
                        )

                        print(f"\n📊 TOP 15 LARGEST SCALING FACTORS (Deterministic):")
                        for i, (name, val) in enumerate(sf_sorted[:15], 1):
                            flag = "🚨" if abs(val) > 100 else ""
                            print(f"   {i}. {name}: {val:.6e} {flag}")

                        abnormal = [(n, v) for n, v in sf_list if abs(v) > 1000]
                        if abnormal:
                            print(
                                f"\n🚨 ABNORMAL VALUES (>1000): {len(abnormal)} found"
                            )
                            for name, val in abnormal[:10]:
                                print(f"   • {name}: {val:.6e}")
                        print("=" * 80)
                except Exception as e:
                    print(f"⚠️ Could not get scaling factors: {e}")

            result.dispose()

            print("✅ Calculation completed!")

            return results_dict

        except Exception as e:
            print(f"❌ Error calculating results: {e}")
            import traceback

            traceback.print_exc()
            return None

    def run_monte_carlo_analysis(
        self,
        product_system_name: str,
        impact_method_name: str = None,
        iterations: int = None,
    ) -> Dict[str, Any]:
        """Run Monte Carlo uncertainty analysis using openLCA's native simulation functionality"""
        if not self.uncertainty_enabled:
            print("⚠️ Uncertainty analysis is disabled")
            return {}

        if iterations is None:
            iterations = MONTE_CARLO_ITERATIONS

        try:
            print(f"\n" + "=" * 80)
            print(f"🎲 Monte Carlo Uncertainty Analysis")
            print(f"📊 Product System: {product_system_name}")
            print(f"🔢 Iterations: {iterations}")
            print("=" * 80)

            system_ref = self.client.find(o.ProductSystem, product_system_name)
            if not system_ref:
                print(f"❌ Cannot find product system: {product_system_name}")
                return {}
            system_obj = self.client.get(o.ProductSystem, system_ref.id)
            if MC_SAFE_LINK_SANITIZE:
                system_obj = self._sanitize_product_system_links_for_mc(system_obj)
            self._diagnose_product_system_for_mc(system_obj)

            impact_method = self.select_impact_method(
                product_system_name,
                "Monte Carlo uncertainty analysis",
                impact_method_name,
            )

            if not impact_method:
                print("❌ No available impact assessment methods")
                return {}

            setup = o.CalculationSetup(target=system_ref, impact_method=impact_method)

            setup.allocation = o.AllocationType.USE_DEFAULT_ALLOCATION

            if hasattr(setup, "amount"):
                setup.amount = 1.0
                print(f"✅ 设置蒙特卡洛模拟参考数量: 1.0 kg (固定功能单位)")
            else:
                print(f"⚠️ CalculationSetup不支持amount属性，可能使用系统默认值")

            print(f"\n🎯 Starting Monte Carlo simulation...")
            print(
                f"   (First iteration may take longer as openLCA builds calculation graph)"
            )

            result = self.client.simulate(setup)
            result.wait_until_ready()

            impact_categories = result.get_impact_categories()
            if not impact_categories:
                print("❌ No impact categories found")
                result.dispose()
                return {}

            print(f"📋 Found {len(impact_categories)} impact categories in method")

            from .config import MONTE_CARLO_SELECTED_CATEGORIES

            selected_categories = (
                MONTE_CARLO_SELECTED_CATEGORIES
                if "MONTE_CARLO_SELECTED_CATEGORIES" in dir()
                else []
            )

            if selected_categories:
                filtered_categories = []
                for category in impact_categories:
                    for selected in selected_categories:
                        if selected.lower() in category.name.lower():
                            filtered_categories.append(category)
                            break

                if filtered_categories:
                    impact_categories = filtered_categories
                    print(
                        f"✅ 只计算 {len(impact_categories)} 个选定的影响类别（配置：MONTE_CARLO_SELECTED_CATEGORIES）"
                    )
                    for cat in impact_categories:
                        print(f"   - {cat.name}")
                else:
                    print(
                        f"⚠️ 未找到配置的影响类别，将计算所有 {len(impact_categories)} 个类别"
                    )
            else:
                print(f"📊 将计算所有 {len(impact_categories)} 个影响类别")

            monte_carlo_results = {}
            category_refs = {}
            for category in impact_categories:
                monte_carlo_results[category.name] = {
                    "values": [],
                    "category_id": category.id,
                    "category_name": category.name,
                    "unit": getattr(category, "ref_unit", "Unknown"),
                }
                category_refs[category.name] = category

            try:
                print(f"\n🔬 DIAGNOSTIC: First MC iteration scaling factors:")
                first_scaling = result.get_scaling_factors()
                if first_scaling:
                    sf_list = []
                    for tf in first_scaling:
                        try:
                            name = (
                                getattr(tf.provider, "name", "Unknown")[:50]
                                if tf.provider
                                else "Unknown"
                            )
                            val = tf.amount if hasattr(tf, "amount") else 0.0
                            sf_list.append((name, val))
                        except:
                            pass

                    sf_sorted = sorted(sf_list, key=lambda x: abs(x[1]), reverse=True)
                    for name, val in sf_sorted[:5]:
                        flag = "🚨 ABNORMAL!" if abs(val) > 100 else ""
                        print(f"   • {name}: {val:.6e} {flag}")
            except Exception as e:
                print(f"   ⚠️ Could not get scaling factors: {e}")

            print(f"\n✅ Iteration 1/{iterations} completed")

            print(f"\n🔬 DIAGNOSTIC: First MC iteration IMPACT values:")
            for category_name, category_data in monte_carlo_results.items():
                try:
                    category_ref = category_refs[category_name]
                    impact_value = result.get_total_impact_value_of(category_ref)
                    category_data["values"].append(impact_value.amount)

                    print(f"   • {category_name[:50]}: {impact_value.amount:.6e}")
                except Exception as e:
                    print(f"⚠️ Error getting impact value for {category_name}: {e}")
                    category_data["values"].append(0.0)
            print(
                f"\n   💡 比较上面的值与确定性结果：如果第一次迭代就有巨大偏差，问题在 simulate() 采样"
            )

            for i in range(1, iterations):
                if (i + 1) % 50 == 0:
                    print(f"🔄 Iteration {i+1}/{iterations}...")

                try:
                    result.simulate_next()
                    result.wait_until_ready()

                    for category_name, category_data in monte_carlo_results.items():
                        try:
                            category_ref = category_refs[category_name]
                            impact_value = result.get_total_impact_value_of(
                                category_ref
                            )
                            category_data["values"].append(impact_value.amount)
                        except Exception as e:
                            category_data["values"].append(0.0)

                except Exception as e:
                    print(f"❌ Error in iteration {i+1}: {e}")
                    break

            try:
                print(
                    f"\n🔍 DIAGNOSTIC: Checking MC scaling factors (after last iteration)..."
                )
                scaling_factors = result.get_scaling_factors()
                if scaling_factors and DIAGNOSTIC_SHOW_SCALING_FACTORS:
                    print(f"📊 Found {len(scaling_factors)} scaling factors")

                    sf_list = []
                    for tech_flow in scaling_factors:
                        try:
                            if hasattr(tech_flow, "provider") and tech_flow.provider:
                                process_name = getattr(
                                    tech_flow.provider, "name", "Unknown"
                                )[:60]
                            else:
                                process_name = "Unknown"
                            scaling_value = (
                                tech_flow.amount
                                if hasattr(tech_flow, "amount")
                                else 0.0
                            )
                            sf_list.append((process_name, scaling_value))
                        except:
                            pass

                    sf_sorted = sorted(sf_list, key=lambda x: abs(x[1]), reverse=True)
                    print(
                        f"\n⚠️ TOP 10 LARGEST SCALING FACTORS (potential problem sources):"
                    )
                    for i, (name, value) in enumerate(sf_sorted[:10], 1):
                        flag = "🚨" if abs(value) > 100 else ""
                        print(f"   {i}. {name}: {value:.6e} {flag}")

                    abnormal = [(n, v) for n, v in sf_list if abs(v) > 1000]
                    if abnormal:
                        print(
                            f"\n🚨 ABNORMAL SCALING FACTORS (>1000) - {len(abnormal)} found:"
                        )
                        for name, value in abnormal[:20]:
                            print(f"   • {name}: {value:.6e}")
            except Exception as e:
                print(f"⚠️ Could not get scaling factors: {e}")

            result.dispose()

            print(f"\n📊 Calculating uncertainty statistics...")
            statistics_results = self._calculate_monte_carlo_statistics(
                monte_carlo_results
            )

            self._display_monte_carlo_results(
                statistics_results,
                product_system_name,
                impact_method.name,
                monte_carlo_results,
            )

            return {
                "product_system": product_system_name,
                "impact_method": impact_method.name,
                "iterations": iterations,
                "raw_results": monte_carlo_results,
                "statistics": statistics_results,
                "provider_cv_data": self.provider_cv_results,
            }

        except Exception as e:
            print(f"❌ Error in Monte Carlo analysis: {e}")
            import traceback

            traceback.print_exc()
            return {}

    def _diagnose_product_system_for_mc(self, system: o.ProductSystem) -> None:
        """Diagnose product-system integrity before Monte Carlo simulation."""
        if not system:
            print("⚠️ MC诊断: 产品系统对象为空，跳过结构检查")
            return

        processes = list(getattr(system, "processes", None) or [])
        links = list(getattr(system, "process_links", None) or [])
        process_ids = {
            getattr(p, "id", None) for p in processes if getattr(p, "id", None)
        }
        process_name_by_id = {
            getattr(p, "id", None): (getattr(p, "name", None) or "")
            for p in processes
            if getattr(p, "id", None)
        }

        orphan_process_links = 0
        orphan_provider_links = 0
        self_loop_links = 0
        missing_exchange_id_links = 0
        duplicate_keys = set()
        seen_keys = set()

        self_loop_examples = []
        for link in links:
            process_id = getattr(getattr(link, "process", None), "id", None)
            provider_id = getattr(getattr(link, "provider", None), "id", None)
            exchange_id = getattr(getattr(link, "exchange", None), "internal_id", None)
            flow_id = getattr(getattr(link, "flow", None), "id", None)
            flow_name = getattr(getattr(link, "flow", None), "name", None)

            if process_id and process_id not in process_ids:
                orphan_process_links += 1
            if provider_id and provider_id not in process_ids:
                orphan_provider_links += 1
            if process_id and provider_id and process_id == provider_id:
                self_loop_links += 1
                if len(self_loop_examples) < 5:
                    pname = process_name_by_id.get(process_id) or "?"
                    self_loop_examples.append(
                        f"{pname} (process={process_id}, exchange={exchange_id}, flow={flow_name or flow_id})"
                    )
            if exchange_id is None:
                missing_exchange_id_links += 1

            key = (str(process_id), str(provider_id), str(exchange_id), str(flow_id))
            if key in seen_keys:
                duplicate_keys.add(key)
            else:
                seen_keys.add(key)

        print(
            f"🔎 MC前系统诊断: processes={len(processes)}, links={len(links)}, "
            f"orphan_process_links={orphan_process_links}, orphan_provider_links={orphan_provider_links}, "
            f"self_loops={self_loop_links}, missing_exchange_id={missing_exchange_id_links}, "
            f"duplicate_links={len(duplicate_keys)}"
        )
        if self_loop_examples:
            print("⚠️ MC前诊断发现自环链接示例:")
            for item in self_loop_examples:
                print(f"   - {item}")

    def _sanitize_product_system_links_for_mc(
        self, system: o.ProductSystem
    ) -> o.ProductSystem:
        """Sanitize ProductSystem links before Monte Carlo simulation."""
        if not system:
            return system

        links = list(getattr(system, "process_links", None) or [])
        if not links:
            return system

        sanitized_links = []
        seen_keys = set()
        removed_self_loops = 0
        removed_duplicates = 0

        for link in links:
            process_id = getattr(getattr(link, "process", None), "id", None)
            provider_id = getattr(getattr(link, "provider", None), "id", None)
            exchange_id = getattr(getattr(link, "exchange", None), "internal_id", None)
            flow_id = getattr(getattr(link, "flow", None), "id", None)

            if process_id and provider_id and process_id == provider_id:
                removed_self_loops += 1
                continue

            key = (str(process_id), str(provider_id), str(exchange_id), str(flow_id))
            if key in seen_keys:
                removed_duplicates += 1
                continue

            seen_keys.add(key)
            sanitized_links.append(link)

        if removed_self_loops == 0 and removed_duplicates == 0:
            return system

        system.process_links = sanitized_links
        self.client.put(system)
        refreshed = self.client.get(o.ProductSystem, system.id)
        print(
            "🧹 MC_SAFE_LINK_SANITIZE: "
            f"removed_self_loops={removed_self_loops}, "
            f"removed_duplicates={removed_duplicates}, "
            f"links={len(links)}→{len(sanitized_links)}"
        )
        return refreshed or system

    def _calculate_monte_carlo_statistics(self, monte_carlo_results: Dict) -> Dict:
        """Calculate statistical measures for Monte Carlo results"""
        statistics_results = {}

        for category_name, category_data in monte_carlo_results.items():
            values = category_data["values"]

            if len(values) == 0:
                continue

            try:

                valid_values = [
                    float(v) for v in values if v is not None and not math.isnan(v)
                ]

                if len(valid_values) == 0:
                    continue

                mean_val = statistics.mean(valid_values)
                std_val = (
                    statistics.stdev(valid_values) if len(valid_values) > 1 else 0.0
                )
                cv_val = std_val / mean_val if mean_val != 0 else 0

                sorted_values = np.array(valid_values)
                p2_5 = np.percentile(sorted_values, 2.5)
                p5 = np.percentile(sorted_values, 5)
                p25 = np.percentile(sorted_values, 25)
                p50 = np.percentile(sorted_values, 50)
                p75 = np.percentile(sorted_values, 75)
                p95 = np.percentile(sorted_values, 95)
                p97_5 = np.percentile(sorted_values, 97.5)

                statistics_results[category_name] = {
                    "mean": mean_val,
                    "std": std_val,
                    "cv": cv_val,
                    "min": min(valid_values),
                    "max": max(valid_values),
                    "median": p50,
                    "p2_5": p2_5,
                    "p5": p5,
                    "p25": p25,
                    "p75": p75,
                    "p95": p95,
                    "p97_5": p97_5,
                    "unit": category_data["unit"],
                    "sample_size": len(valid_values),
                }

            except Exception as e:
                print(f"⚠️ Error calculating statistics for {category_name}: {e}")

        return statistics_results

    def _display_monte_carlo_results(
        self,
        statistics: Dict,
        system_name: str,
        method_name: str,
        raw_results: Dict = None,
    ):
        """Display Monte Carlo uncertainty analysis results"""
        print(f"\n" + "=" * 140)
        print(f" Monte Carlo Uncertainty Analysis Results")
        print(f" Product System: {system_name}")
        print(f" Impact Method: {method_name}")
        print("=" * 140)

        iterations = list(statistics.values())[0]["sample_size"] if statistics else 0

        header = f"{'Impact Category':<45}{'Iterations':<12}{'Mean':<15}{'Std Dev':<15}{'5% percentile':<15}{'95% percentile':<15}{'Median':<15}{'Unit':<10}"
        print(header)
        print("-" * 140)

        for category_name, stat_data in statistics.items():
            if len(category_name) > 43:
                display_name = category_name[:40] + "..."
            else:
                display_name = category_name

            iterations_str = f"{stat_data['sample_size']}"
            mean_str = f"{stat_data['mean']:.3f}"
            std_str = f"{stat_data['std']:.3f}"
            p5_str = f"{stat_data['p5']:.3f}"
            p95_str = f"{stat_data['p95']:.3f}"
            median_str = f"{stat_data['median']:.3f}"
            unit_str = stat_data["unit"][:8] if stat_data["unit"] else "Unknown"

            row = f"{display_name:<45}{iterations_str:<12}{mean_str:<15}{std_str:<15}{p5_str:<15}{p95_str:<15}{median_str:<15}{unit_str:<10}"
            print(row)

        print("=" * 140)
        print(f"Results: {iterations} iterations")
        print("95% Confidence Interval: 2.5th percentile to 97.5th percentile")

        if self.provider_cv_results:
            print(f"\n📊 Provider CV Summary:")
            for exchange_key, cv_data in self.provider_cv_results.items():
                if "selected_provider" in cv_data:
                    provider_info = cv_data["selected_provider"]
                    print(
                        f"  • {exchange_key}: CV={provider_info['total_cv']*100:.1f}% ({provider_info['name']})"
                    )

        from .config import DISPLAY_UNCERTAINTY_DETAILS

        if DISPLAY_UNCERTAINTY_DETAILS:
            self._display_uncertainty_parameters(system_name)
        else:
            print(
                "💡 Detailed uncertainty parameters display is disabled (DISPLAY_UNCERTAINTY_DETAILS=False)"
            )

        self._plot_uncertainty_distributions(statistics, system_name, raw_results)

        if raw_results:
            print(f"\n📊 Generating selected distribution plots...")

            climate_change_keys = [
                key
                for key in statistics.keys()
                if "climate" in key.lower() and "change" in key.lower()
            ]

            if climate_change_keys:

                midpoint_keys = [
                    key for key in climate_change_keys if "midpoint" in key.lower()
                ]
                if midpoint_keys:
                    climate_key = midpoint_keys[0]
                else:

                    non_endpoint_keys = [
                        key
                        for key in climate_change_keys
                        if "endpoint" not in key.lower()
                    ]
                    if non_endpoint_keys:
                        climate_key = non_endpoint_keys[0]
                    else:
                        climate_key = climate_change_keys[0]
                if climate_key in raw_results:
                    values = raw_results[climate_key]["values"]
                    stat_data = statistics[climate_key]
                    print(f"📈 Generating Climate Change distribution plot...")
                    self.plot_single_impact_distribution(
                        climate_key, values, stat_data, system_name
                    )
            else:
                print("⚠️ Climate change impact category not found")

                print("📋 Available impact categories:")
                for i, key in enumerate(statistics.keys(), 1):
                    print(f"  {i}. {key}")
                    if i >= 5:
                        print(f"  ... and {len(statistics)-5} more")
                        break

        print("✅ Monte Carlo uncertainty analysis completed!")

    def _display_uncertainty_parameters(self, system_name: str):
        """Display all uncertainty parameters applied to exchanges in the product system"""
        try:
            print(f"\n" + "=" * 100)
            print(f"🎲 Uncertainty Parameters Applied to Exchanges")
            print(f"📊 Product System: {system_name}")
            print("=" * 100)

            system_ref = self.client.find(o.ProductSystem, system_name)
            if not system_ref:
                print(f"❌ Cannot find product system: {system_name}")
                return

            full_system = self.client.get(o.ProductSystem, system_ref.id)
            if not full_system or not full_system.processes:
                print("⚠️ No processes found in product system")
                return

            print(
                f"{'Process':<35}{'Flow':<35}{'Exchange Type':<15}{'Distribution':<15}{'Geom Mean':<12}{'Geom SD':<12}{'CV (%)':<10}"
            )
            print("-" * 100)

            total_uncertain_exchanges = 0

            for process_ref in full_system.processes:
                try:
                    process_obj = self.client.get(o.Process, process_ref.id)
                    if not process_obj or not process_obj.exchanges:
                        continue

                    process_name = (
                        process_obj.name[:33] + "..."
                        if len(process_obj.name) > 33
                        else process_obj.name
                    )

                    for exchange in process_obj.exchanges:
                        if exchange.uncertainty:
                            uncertainty = exchange.uncertainty
                            flow_name = (
                                exchange.flow.name[:33] + "..."
                                if exchange.flow and len(exchange.flow.name) > 33
                                else (
                                    exchange.flow.name if exchange.flow else "Unknown"
                                )
                            )
                            exchange_type = "Input" if exchange.is_input else "Output"

                            dist_type = "Unknown"
                            geom_mean = "N/A"
                            geom_sd = "N/A"
                            cv_percent = "N/A"

                            if (
                                uncertainty.distribution_type
                                == o.UncertaintyType.LOG_NORMAL_DISTRIBUTION
                            ):
                                dist_type = "Log-Normal"
                                if uncertainty.geom_mean:
                                    geom_mean = f"{uncertainty.geom_mean:.4f}"
                                if uncertainty.geom_sd:
                                    geom_sd = f"{uncertainty.geom_sd:.4f}"

                                    if uncertainty.geom_sd > 1:
                                        sigma = math.log(uncertainty.geom_sd)
                                        cv = math.sqrt(math.exp(sigma**2) - 1)
                                        cv_percent = f"{cv*100:.1f}"
                            elif (
                                uncertainty.distribution_type
                                == o.UncertaintyType.NORMAL_DISTRIBUTION
                            ):
                                dist_type = "Normal"
                                if uncertainty.mean:
                                    geom_mean = f"{uncertainty.mean:.4f}"
                                if uncertainty.sd:
                                    geom_sd = f"{uncertainty.sd:.4f}"
                                    if uncertainty.mean and uncertainty.mean != 0:
                                        cv_percent = f"{(uncertainty.sd/uncertainty.mean)*100:.1f}"

                            print(
                                f"{process_name:<35}{flow_name:<35}{exchange_type:<15}{dist_type:<15}{geom_mean:<12}{geom_sd:<12}{cv_percent:<10}"
                            )
                            total_uncertain_exchanges += 1

                except Exception as e:
                    print(f"⚠️ Error processing process {process_ref.name}: {e}")
                    continue

            print("=" * 100)
            print(f"📊 Total exchanges with uncertainty: {total_uncertain_exchanges}")

            if total_uncertain_exchanges == 0:
                print("⚠️ No uncertainty parameters found in the system")
                print(
                    "💡 This explains why Monte Carlo results may appear deterministic"
                )

        except Exception as e:
            print(f"❌ Error displaying uncertainty parameters: {e}")
            import traceback

            traceback.print_exc()

    def _plot_uncertainty_distributions(
        self, statistics: Dict, system_name: str, raw_results: Dict = None
    ):
        """Plot uncertainty distributions for each impact category"""
        if not statistics:
            return

        try:
            print(f"\n📊 Generating uncertainty distribution plots...")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            plt.style.use("default")

            n_categories = len(statistics)
            if n_categories == 0:
                return

            if n_categories <= 4:
                n_cols = 2
                n_rows = (n_categories + 1) // 2
            elif n_categories <= 9:
                n_cols = 3
                n_rows = (n_categories + 2) // 3
            else:
                n_cols = 4
                n_rows = (n_categories + 3) // 4

            fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3 * n_rows))
            fig.suptitle(
                f"Monte Carlo Uncertainty Analysis\nProduct System: {system_name}",
                fontsize=14,
                fontweight="bold",
            )

            if n_categories == 1:
                axes = [axes]
            elif n_rows == 1:
                axes = axes.reshape(-1)
            else:
                axes = axes.flatten()

            for i, (category_name, stat_data) in enumerate(statistics.items()):
                if i >= len(axes):
                    break

                ax = axes[i]

                if raw_results and category_name in raw_results:
                    sample_data = np.array(raw_results[category_name]["values"])
                else:

                    mean_val = stat_data["mean"]
                    std_val = stat_data["std"]
                    n_samples = stat_data["sample_size"]
                    sample_data = np.random.normal(mean_val, std_val, n_samples)

                n_bins = 50
                counts, bins, patches = ax.hist(
                    sample_data,
                    bins=n_bins,
                    alpha=0.7,
                    color="lightblue",
                    edgecolor="black",
                    linewidth=0.5,
                )

                mean_val = stat_data["mean"]
                std_val = stat_data["std"]
                median_val = stat_data["median"]
                p5_val = stat_data["p5"]
                p95_val = stat_data["p95"]

                ax.axvline(
                    mean_val,
                    color="red",
                    linestyle="-",
                    linewidth=2,
                    label=f"Mean: {mean_val:.3f}",
                )
                ax.axvline(
                    median_val,
                    color="green",
                    linestyle="--",
                    linewidth=2,
                    label=f"Median: {median_val:.3f}",
                )
                ax.axvline(
                    p5_val,
                    color="orange",
                    linestyle=":",
                    linewidth=1.5,
                    label=f"5% percentile: {p5_val:.3f}",
                )
                ax.axvline(
                    p95_val,
                    color="orange",
                    linestyle=":",
                    linewidth=1.5,
                    label=f"95% percentile: {p95_val:.3f}",
                )

                category_short = (
                    category_name[:30] + "..."
                    if len(category_name) > 30
                    else category_name
                )
                ax.set_title(f"{category_short}", fontsize=10, fontweight="bold")
                ax.set_xlabel(f'Impact Value ({stat_data["unit"]})', fontsize=8)
                ax.set_ylabel("Frequency", fontsize=8)

                iterations = stat_data["sample_size"]
                stats_text = f"Results: {iterations}\nMean: {mean_val:.3f}\nStandard deviation: {std_val:.3f}\n5% percentile: {p5_val:.3f}\n95% percentile: {p95_val:.3f}\nMedian: {median_val:.3f}"
                ax.text(
                    0.02,
                    0.98,
                    stats_text,
                    transform=ax.transAxes,
                    fontsize=8,
                    verticalalignment="top",
                    bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
                )

                ax.tick_params(axis="both", which="major", labelsize=8)

                ax.grid(True, alpha=0.3)

            for i in range(n_categories, len(axes)):
                axes[i].set_visible(False)

            plt.tight_layout(rect=[0, 0.03, 1, 0.95])

            plt.close()

        except Exception as e:
            print(f"⚠️ Error generating uncertainty plots: {e}")
            import traceback

            traceback.print_exc()

    def _validate_upstream_connections(self, product_system: o.ProductSystem):
        """Validate that all input flows in the product system have upstream connections"""
        try:
            print(f"\n🔍 Validating upstream connections for all flows...")

            unconnected_flows = []
            total_inputs = 0
            connected_inputs = 0

            if not product_system.processes:
                print(f"⚠️ No processes in product system to validate")
                return

            for process_ref in product_system.processes:
                try:
                    process_obj = self.client.get(o.Process, process_ref.id)
                    if not process_obj or not process_obj.exchanges:
                        continue

                    for exchange in process_obj.exchanges:
                        if exchange.is_input and exchange.flow:
                            total_inputs += 1

                            if exchange.default_provider:
                                connected_inputs += 1
                            else:
                                unconnected_flows.append(
                                    {
                                        "process": process_obj.name,
                                        "flow": exchange.flow.name,
                                        "amount": exchange.amount,
                                    }
                                )

                except Exception as e:
                    print(f"⚠️ Error validating process {process_ref.name}: {e}")
                    continue

            print(f"\n📈 Upstream Connection Validation Results:")
            print(f"  - Total input flows: {total_inputs}")
            print(f"  - Connected inputs: {connected_inputs}")
            print(f"  - Unconnected inputs: {len(unconnected_flows)}")
            print(
                f"  - Connection rate: {(connected_inputs/total_inputs*100):.1f}%"
                if total_inputs > 0
                else "  - Connection rate: N/A"
            )

            if unconnected_flows:
                print(f"\n⚠️ Unconnected flows (no upstream tracing):")
                for i, flow_info in enumerate(unconnected_flows[:5], 1):
                    print(
                        f"  {i}. {flow_info['process']} <- '{flow_info['flow']}' ({flow_info['amount']})"
                    )
                if len(unconnected_flows) > 5:
                    print(f"  ... and {len(unconnected_flows) - 5} more")
                print(
                    f"\n💡 Consider adding these flows to background database or Excel processes"
                )
            else:
                print(f"\n✅ All input flows have upstream connections!")

        except Exception as e:
            print(f"❌ Error validating upstream connections: {e}")

    def plot_single_impact_distribution(
        self, category_name: str, values: List[float], stats: Dict, system_name: str
    ):
        """Plot a single impact category distribution in the format shown in the image"""
        try:

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            fig, ax = plt.subplots(figsize=(12, 8))

            iterations = len(values)
            mean_val = stats["mean"]
            std_val = stats["std"]
            p5_val = stats["p5"]
            p95_val = stats["p95"]
            median_val = stats["median"]

            n_bins = 100
            counts, bins, patches = ax.hist(
                values,
                bins=n_bins,
                alpha=0.7,
                color="lightgray",
                edgecolor="black",
                linewidth=0.5,
            )

            ax.axvline(
                mean_val,
                color="red",
                linestyle="-",
                linewidth=3,
                label=f"Mean: {mean_val:.3f}",
            )
            ax.axvline(
                median_val,
                color="blue",
                linestyle="-",
                linewidth=3,
                label=f"Median: {median_val:.3f}",
            )
            ax.axvline(
                p5_val,
                color="red",
                linestyle="-",
                linewidth=2,
                label=f"5% percentile: {p5_val:.3f}",
            )
            ax.axvline(
                p95_val,
                color="red",
                linestyle="-",
                linewidth=2,
                label=f"95% percentile: {p95_val:.3f}",
            )

            ax.set_title(f"{category_name}", fontsize=14, fontweight="bold", pad=20)
            ax.set_xlabel("Impact Value", fontsize=12)
            ax.set_ylabel("Frequency", fontsize=12)

            stats_text = f"Results: {iterations}  Mean: {mean_val:.3f}  Standard deviation: {std_val:.3f}  5% percentile: {p5_val:.3f}  95% percentile: {p95_val:.3f}  Median: {median_val:.3f}"
            ax.text(
                0.5,
                1.02,
                stats_text,
                transform=ax.transAxes,
                fontsize=11,
                horizontalalignment="center",
                color="blue",
                fontweight="bold",
            )

            ax.grid(True, alpha=0.3)
            ax.set_facecolor("white")

            x_min, x_max = ax.get_xlim()
            y_min, y_max = ax.get_ylim()
            ax.set_ylim(0, y_max * 1.1)

            plt.tight_layout()

            plt.close()

        except Exception as e:
            print(f"⚠️ Error generating single distribution plot: {e}")
            import traceback

            traceback.print_exc()

    def get_comprehensive_lca_results(
        self, system_name: str, system_uuid: str = None
    ) -> Dict[str, Any]:
        """Get comprehensive LCA results similar to openLCA interface"""
        try:
            print(f"\n📊 Generating comprehensive LCA results for {system_name}...")

            target_system = None

            if system_uuid:
                try:
                    print(f"   🔍 Trying to get system by UUID: {system_uuid}")
                    target_system = self.client.get(o.ProductSystem, system_uuid)
                    if target_system and target_system.name == system_name:
                        print(f"   ✅ Found system by UUID: {target_system.name}")
                    else:
                        print(f"   ⚠️ UUID found but name mismatch, will try get_all...")
                        target_system = None
                except Exception as e:
                    print(
                        f"   ⚠️ Failed to get system by UUID: {e}, will try get_all..."
                    )
                    target_system = None

            if not target_system:
                try:
                    print(
                        f"   🔍 Searching for product system '{system_name}' using get_all..."
                    )
                    systems = self.client.get_all(o.ProductSystem)

                    if systems is None:
                        raise Exception(
                            "get_all returned None - database may be too large or IPC server error"
                        )

                    for system in systems:
                        if system.name == system_name:
                            target_system = system
                            break
                except Exception as e:
                    print(f"   ⚠️ get_all failed: {e}")

                    if system_uuid:
                        try:
                            print(f"   🔄 Retrying with UUID as fallback...")
                            target_system = self.client.get(
                                o.ProductSystem, system_uuid
                            )
                            if target_system:
                                print(
                                    f"   ✅ Successfully retrieved system by UUID: {target_system.name}"
                                )
                        except Exception as e2:
                            print(f"   ❌ UUID fallback also failed: {e2}")
                            return {
                                "error": f'Failed to retrieve product system "{system_name}": {e}. UUID fallback also failed: {e2}'
                            }
                    else:
                        return {
                            "error": f'Failed to retrieve product system "{system_name}": {e}. Consider providing system_uuid parameter.'
                        }

            if not target_system:
                return {"error": f'Product system "{system_name}" not found'}

            results = {
                "system_info": {
                    "name": system_name,
                    "id": target_system.id,
                    "description": target_system.description or "",
                },
                "inventory_results": self._get_inventory_results(target_system),
                "impact_analysis": self._get_impact_analysis_results(target_system),
                "process_results": self._get_process_results(target_system),
                "contribution_analysis": self._get_contribution_analysis(target_system),
                "grouping": self._get_grouping_results(target_system),
                "locations": self._get_location_analysis(target_system),
                "sankey_diagram": self._get_sankey_diagram_data(target_system),
                "lcia_checks": self._get_lcia_checks(target_system),
                "uncertainty_analysis": None,
                "generated_plots": [],
            }

            if self.uncertainty_enabled:
                print("🎲 Including uncertainty analysis...")
                uncertainty_results = self.run_monte_carlo_analysis(system_name)
                if uncertainty_results:
                    results["uncertainty_analysis"] = uncertainty_results

            print(f"✅ Comprehensive results generated for {system_name}")
            return results

        except Exception as e:
            print(f"❌ Error generating comprehensive results: {e}")
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    def _get_inventory_results(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get inventory analysis results (flows in/out)"""
        try:
            print("📋 Calculating inventory results...")

            setup = o.CalculationSetup()
            setup.target = o.Ref(id=system.id)
            setup.impact_method = None

            setup.allocation = o.AllocationType.USE_DEFAULT_ALLOCATION

            result = self.client.calculate(setup)

            if not result:
                return {"error": "Inventory calculation failed"}

            try:
                result.wait_until_ready()
                print("✅ Inventory calculation completed")
            except Exception as e:
                print(f"⚠️ Error waiting for inventory calculation: {e}")
                return {"error": f"Inventory calculation timed out or failed: {str(e)}"}

            print(f"🔍 Detailed inventory result inspection:")
            print(f"   - Result type: {type(result)}")
            print(f"   - Has flow_results: {hasattr(result, 'flow_results')}")
            print(f"   - Has get_total_flows: {hasattr(result, 'get_total_flows')}")
            print(
                f"   - Has total_requirements: {hasattr(result, 'total_requirements')}"
            )
            print(
                f"   - Has get_total_requirements: {hasattr(result, 'get_total_requirements')}"
            )
            print(f"   - Has get_flow_results: {hasattr(result, 'get_flow_results')}")
            print(
                f"   - Result dir: {[attr for attr in dir(result) if not attr.startswith('_')]}"
            )

            flow_results = []
            input_flows = []
            output_flows = []

            if hasattr(result, "flow_results") and result.flow_results:
                print(
                    f"📊 Using flow_results attribute, found {len(result.flow_results)} flows"
                )
                for flow_result in result.flow_results[:100]:
                    flow_info = {
                        "flow_name": (
                            flow_result.flow.name if flow_result.flow else "Unknown"
                        ),
                        "flow_id": flow_result.flow.id if flow_result.flow else None,
                        "flow_type": (
                            str(flow_result.flow.flow_type)
                            if hasattr(flow_result.flow, "flow_type")
                            else "Unknown"
                        ),
                        "value": (
                            flow_result.value if hasattr(flow_result, "value") else 0
                        ),
                        "unit": flow_result.unit.name if flow_result.unit else "",
                        "is_input": (
                            flow_result.is_input
                            if hasattr(flow_result, "is_input")
                            else False
                        ),
                        "category": (
                            getattr(flow_result.flow.category, "name", "")
                            if hasattr(flow_result.flow, "category")
                            and flow_result.flow.category
                            else ""
                        ),
                    }
                    flow_results.append(flow_info)

                    if flow_info["is_input"]:
                        input_flows.append(flow_info)
                    else:
                        output_flows.append(flow_info)

            elif hasattr(result, "get_total_flows"):
                try:
                    total_flows = result.get_total_flows()
                    print(f"📊 Using get_total_flows(), found {len(total_flows)} flows")
                    for flow_result in total_flows[:100]:
                        flow_info = {
                            "flow_name": (
                                flow_result.flow.name
                                if hasattr(flow_result, "flow") and flow_result.flow
                                else "Unknown"
                            ),
                            "flow_id": (
                                flow_result.flow.id
                                if hasattr(flow_result, "flow") and flow_result.flow
                                else None
                            ),
                            "flow_type": (
                                str(flow_result.flow.flow_type)
                                if hasattr(flow_result, "flow")
                                and hasattr(flow_result.flow, "flow_type")
                                else "Unknown"
                            ),
                            "value": (
                                flow_result.value
                                if hasattr(flow_result, "value")
                                else 0
                            ),
                            "unit": (
                                flow_result.unit.name
                                if hasattr(flow_result, "unit") and flow_result.unit
                                else ""
                            ),
                            "is_input": (
                                flow_result.is_input
                                if hasattr(flow_result, "is_input")
                                else False
                            ),
                            "category": (
                                getattr(flow_result.flow.category, "name", "")
                                if hasattr(flow_result, "flow")
                                and hasattr(flow_result.flow, "category")
                                and flow_result.flow.category
                                else ""
                            ),
                        }
                        flow_results.append(flow_info)

                        if flow_info["is_input"]:
                            input_flows.append(flow_info)
                        else:
                            output_flows.append(flow_info)
                except Exception as e:
                    print(f"⚠️ Could not use get_total_flows(): {e}")

            elif hasattr(result, "get_total_requirements"):
                try:
                    total_reqs = result.get_total_requirements()
                    print(
                        f"📊 Using get_total_requirements(), found {len(total_reqs)} elementary flows"
                    )
                    for flow_result in total_reqs[:100]:
                        flow_info = {
                            "flow_name": (
                                flow_result.flow.name
                                if hasattr(flow_result, "flow") and flow_result.flow
                                else "Unknown"
                            ),
                            "flow_id": (
                                flow_result.flow.id
                                if hasattr(flow_result, "flow") and flow_result.flow
                                else None
                            ),
                            "flow_type": "ELEMENTARY_FLOW",
                            "value": (
                                flow_result.value
                                if hasattr(flow_result, "value")
                                else 0
                            ),
                            "unit": (
                                flow_result.unit.name
                                if hasattr(flow_result, "unit") and flow_result.unit
                                else ""
                            ),
                            "is_input": (
                                flow_result.is_input
                                if hasattr(flow_result, "is_input")
                                else False
                            ),
                            "category": (
                                getattr(flow_result.flow.category, "name", "")
                                if hasattr(flow_result, "flow")
                                and hasattr(flow_result.flow, "category")
                                and flow_result.flow.category
                                else ""
                            ),
                        }
                        flow_results.append(flow_info)

                        if flow_info["is_input"]:
                            input_flows.append(flow_info)
                        else:
                            output_flows.append(flow_info)
                except Exception as e:
                    print(f"⚠️ Could not use get_total_requirements(): {e}")

            if len(flow_results) == 0:
                print(f"⚠️ WARNING: No inventory flows were obtained!")
                print(
                    f"   - This may indicate the product system needs to be calculated in OpenLCA first"
                )
            else:
                print(f"✅ Successfully obtained {len(flow_results)} flow results")

            try:
                if hasattr(self.client, "dispose"):
                    self.client.dispose(result)
            except Exception as e:
                print(f"⚠️ Could not dispose result: {e}")

            return {
                "total_flows": len(flow_results),
                "flow_results": flow_results,
                "inputs": input_flows,
                "outputs": output_flows,
                "input_count": len(input_flows),
                "output_count": len(output_flows),
            }

        except Exception as e:
            print(f"❌ Error in inventory analysis: {e}")
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    def _get_impact_analysis_results(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get impact assessment results"""
        try:
            print("🎯 Calculating impact analysis results...")

            all_methods = self.client.get_all(o.ImpactMethod)
            target_method = None

            if self.preferred_lcia_method:
                print(f"🔍 Looking for configured method: {self.preferred_lcia_method}")

                user_wants_no_lt = "no lt" in self.preferred_lcia_method.lower()
                print(f"   User wants 'no LT' version: {user_wants_no_lt}")

                preferred_methods = [
                    m
                    for m in all_methods
                    if self.preferred_lcia_method.lower() in m.name.lower()
                    and "incl" not in m.name.lower()
                    and "uptake" not in m.name.lower()
                ]

                print(f"   Initial matches: {len(preferred_methods)} methods")

                if not user_wants_no_lt:
                    before_filter = len(preferred_methods)
                    preferred_methods = [
                        m for m in preferred_methods if "no lt" not in m.name.lower()
                    ]
                    after_filter = len(preferred_methods)
                    print(
                        f"   After excluding 'no LT': {after_filter} methods (removed {before_filter - after_filter})"
                    )

                if preferred_methods:
                    target_method = preferred_methods[0]
                    print(f"✅ Found configured method: {target_method.name}")
                    print(f"   Method ID: {target_method.id}")

            if not target_method:
                for method in all_methods:
                    method_name_lower = method.name.lower()
                    if (
                        "ipcc 2013" in method_name_lower
                        and "gwp" in method_name_lower
                        and "100a" in method_name_lower
                        and "incl" not in method_name_lower
                        and "uptake" not in method_name_lower
                    ):
                        target_method = method
                        print(
                            f"✅ Found fallback method (without CO2 uptake): {method.name}"
                        )
                        break

            if not target_method:
                for method in all_methods:
                    method_name_lower = method.name.lower()
                    if "ipcc" in method_name_lower and "gwp" in method_name_lower:
                        target_method = method
                        print(f"✅ Found IPCC GWP method: {method.name}")
                        break

            if not target_method:
                for method in all_methods:
                    if "ILCD".lower() in method.name.lower():
                        target_method = method
                        print(f"✅ Found ILCD method: {method.name}")
                        break

            if not target_method:

                print("⚠️ Available impact methods:")
                for method in all_methods[:10]:
                    print(f"   - {method.name}")
                return {
                    "error": "No suitable impact method found. Please ensure a compatible method is available in OpenLCA."
                }

            print(f"🔍 Product system details:")
            print(f"   - System ID: {system.id}")
            print(f"   - System name: {system.name}")

            try:
                full_system = self.client.get(o.ProductSystem, system.id)
                if (
                    hasattr(full_system, "reference_exchange")
                    and full_system.reference_exchange
                ):
                    print(f"   - Reference exchange: {full_system.reference_exchange}")
                    if hasattr(full_system.reference_exchange, "amount"):
                        print(
                            f"   - Reference amount: {full_system.reference_exchange.amount}"
                        )
                if (
                    hasattr(full_system, "reference_process")
                    and full_system.reference_process
                ):
                    print(
                        f"   - Reference process: {full_system.reference_process.name}"
                    )
                if hasattr(full_system, "target_amount"):
                    print(f"   - Target amount: {full_system.target_amount}")
            except Exception as e:
                print(f"⚠️ Could not get full system details: {e}")

            setup = o.CalculationSetup()
            setup.target = o.Ref(id=system.id)
            setup.impact_method = o.Ref(id=target_method.id)

            setup.allocation = o.AllocationType.USE_DEFAULT_ALLOCATION
            print(
                "✅ Set allocation to USE_DEFAULT_ALLOCATION (= GUI 'As defined in processes')"
            )

            try:

                if hasattr(setup, "calculation_type"):
                    setup.calculation_type = "CONTRIBUTION_ANALYSIS"
                    print("✅ Set calculation type to CONTRIBUTION_ANALYSIS")

                if hasattr(setup, "amount"):
                    setup.amount = 1.0
                    print("✅ Set target amount to 1.0 kg (fixed functional unit)")

                if hasattr(setup, "with_costs"):
                    setup.with_costs = False
                if hasattr(setup, "with_regionalization"):
                    setup.with_regionalization = False

                print(f"📋 Calculation setup configured:")
                print(f"   - Target: {setup.target.id}")
                print(f"   - Impact method: {target_method.name}")
            except Exception as e:
                print(f"⚠️ Some setup properties could not be set: {e}")

            print("🔄 Running calculation via IPC...")
            result = self.client.calculate(setup)

            if not result:
                return {
                    "error": "Impact calculation failed - client.calculate() returned None"
                }

            try:
                result.wait_until_ready()
                print("✅ Impact calculation completed")
            except Exception as e:
                print(f"⚠️ Error waiting for impact calculation: {e}")
                return {"error": f"Impact calculation timed out or failed: {str(e)}"}

            impact_results = []
            midpoint_results = []
            endpoint_results = []

            print(f"🔍 Detailed result object inspection:")
            print(f"   - Result type: {type(result)}")
            print(f"   - Result attributes: {dir(result)}")
            print(f"   - Has impact_results: {hasattr(result, 'impact_results')}")
            print(f"   - Has get_total_impacts: {hasattr(result, 'get_total_impacts')}")
            print(f"   - Has total_impacts: {hasattr(result, 'total_impacts')}")
            print(
                f"   - Has get_total_impact_results: {hasattr(result, 'get_total_impact_results')}"
            )
            print(
                f"   - Has total_impact_results: {hasattr(result, 'total_impact_results')}"
            )

            if hasattr(result, "impact_results"):
                ir = result.impact_results
                print(f"   - impact_results: {ir}")
                if ir is not None and hasattr(ir, "__len__"):
                    print(f"   - impact_results length: {len(ir)}")
                    if len(ir) > 0:
                        print(f"   - First impact result: {ir[0]}")
                        if hasattr(ir[0], "__dict__"):
                            print(f"   - First impact result dict: {ir[0].__dict__}")

            if hasattr(result, "impact_results"):
                ir = result.impact_results
                print(f"🔍 impact_results type: {type(ir)}")
                print(f"🔍 impact_results is None: {ir is None}")
                if ir is not None:
                    print(
                        f"🔍 impact_results length: {len(ir) if hasattr(ir, '__len__') else 'N/A'}"
                    )

            extraction_successful = False

            if hasattr(result, "get_total_impacts") and not extraction_successful:
                try:
                    total_impacts = result.get_total_impacts()
                    print(
                        f"📊 Method 0 (Standard API): get_total_impacts() returned {len(total_impacts) if total_impacts else 0} results"
                    )
                    if total_impacts and len(total_impacts) > 0:
                        for impact in total_impacts:

                            value = impact.amount if hasattr(impact, "amount") else 0

                            if (
                                hasattr(impact, "impact_category")
                                and impact.impact_category
                            ):
                                category_name = impact.impact_category.name
                                unit = (
                                    impact.impact_category.ref_unit
                                    if hasattr(impact.impact_category, "ref_unit")
                                    else ""
                                )
                                description = getattr(
                                    impact.impact_category, "description", ""
                                )
                            else:
                                category_name = "Unknown"
                                unit = ""
                                description = ""

                            if abs(value) > 1e-15:
                                impact_info = {
                                    "category": category_name,
                                    "value": value,
                                    "unit": unit,
                                    "description": description,
                                }
                                impact_results.append(impact_info)

                                category_name_lower = category_name.lower()
                                if any(
                                    word in category_name_lower
                                    for word in [
                                        "climate change",
                                        "climate",
                                        "gwp",
                                        "global warming",
                                        "acidification",
                                        "eutrophication",
                                        "ozone",
                                        "particulate",
                                        "ionising",
                                        "photochemical",
                                        "ecotoxicity",
                                        "toxicity",
                                        "land use",
                                        "water use",
                                        "mineral",
                                        "fossil",
                                    ]
                                ):
                                    midpoint_results.append(impact_info)
                                elif any(
                                    word in category_name_lower
                                    for word in [
                                        "human health",
                                        "ecosystem",
                                        "resource",
                                    ]
                                ):
                                    endpoint_results.append(impact_info)

                                print(f"   - {category_name}: {value} {unit}")

                        if len(impact_results) > 0:
                            extraction_successful = True
                            print(
                                f"✅ Method 0 succeeded: extracted {len(impact_results)} non-zero impact categories"
                            )
                        else:
                            print(f"⚠️ Method 0 returned only zero values")
                except Exception as e:
                    print(f"⚠️ Method 0 failed: {e}")
                    import traceback

                    traceback.print_exc()

            if (
                hasattr(result, "impact_results")
                and result.impact_results
                and not extraction_successful
            ):
                try:
                    print(
                        f"📊 Method 1: Using impact_results attribute with {len(result.impact_results)} items"
                    )
                    for impact_result in result.impact_results:
                        value = (
                            impact_result.value
                            if hasattr(impact_result, "value")
                            else 0
                        )

                        if abs(value) > 1e-15:
                            impact_info = {
                                "category": (
                                    impact_result.impact_category.name
                                    if impact_result.impact_category
                                    else "Unknown"
                                ),
                                "value": value,
                                "unit": (
                                    impact_result.unit.name
                                    if impact_result.unit
                                    else ""
                                ),
                                "description": (
                                    getattr(
                                        impact_result.impact_category, "description", ""
                                    )
                                    if impact_result.impact_category
                                    else ""
                                ),
                            }
                            impact_results.append(impact_info)

                            category_name = impact_info["category"].lower()
                            if any(
                                word in category_name
                                for word in [
                                    "climate change",
                                    "climate",
                                    "gwp",
                                    "acidification",
                                    "eutrophication",
                                    "ozone",
                                    "particulate",
                                ]
                            ):
                                midpoint_results.append(impact_info)
                            elif any(
                                word in category_name
                                for word in ["human health", "ecosystem", "resource"]
                            ):
                                endpoint_results.append(impact_info)

                    if len(impact_results) > 0:
                        extraction_successful = True
                        print(
                            f"✅ Method 1 succeeded: extracted {len(impact_results)} non-zero impact categories"
                        )
                    else:
                        print(f"⚠️ Method 1 returned only zero values")
                except Exception as e:
                    print(f"⚠️ Method 1 failed: {e}")

            if hasattr(result, "total_impacts") and not extraction_successful:
                try:
                    total_impacts_attr = result.total_impacts
                    print(f"📊 Method 2: Using total_impacts attribute")
                    if total_impacts_attr:
                        for impact in total_impacts_attr:
                            value = impact.value if hasattr(impact, "value") else 0
                            if abs(value) > 1e-15:
                                impact_info = {
                                    "category": (
                                        impact.impact_category.name
                                        if hasattr(impact, "impact_category")
                                        and impact.impact_category
                                        else "Unknown"
                                    ),
                                    "value": value,
                                    "unit": (
                                        impact.unit.name
                                        if hasattr(impact, "unit") and impact.unit
                                        else ""
                                    ),
                                    "description": "",
                                }
                                impact_results.append(impact_info)

                                category_name = impact_info["category"].lower()
                                if any(
                                    word in category_name
                                    for word in [
                                        "climate",
                                        "gwp",
                                        "acidification",
                                        "eutrophication",
                                    ]
                                ):
                                    midpoint_results.append(impact_info)
                                elif any(
                                    word in category_name
                                    for word in [
                                        "human health",
                                        "ecosystem",
                                        "resource",
                                    ]
                                ):
                                    endpoint_results.append(impact_info)

                        if len(impact_results) > 0:
                            extraction_successful = True
                            print(
                                f"✅ Method 2 succeeded: extracted {len(impact_results)} non-zero impact categories"
                            )
                except Exception as e:
                    print(f"⚠️ Method 2 failed: {e}")

            try:
                if hasattr(self.client, "dispose"):
                    self.client.dispose(result)
            except Exception as e:
                print(f"⚠️ Could not dispose result: {e}")

            if len(impact_results) == 0:
                print(f"❌ CRITICAL: No non-zero impact results were obtained!")
                print(f"   - Method used: {target_method.name}")
                print(f"   - System ID: {system.id}")
                print(f"   - System name: {system.name}")
                print(f"   - Possible causes:")
                print(
                    f"     1. ⚠️ Product system was not calculated properly in OpenLCA"
                )
                print(
                    f"     2. ⚠️ Impact method has no characterization factors for the elementary flows"
                )
                print(f"     3. ⚠️ System contains only zero-valued exchanges")
                print(f"     4. ⚠️ Reference flow amount is set to 0")
                print(f"   - SOLUTION:")
                print(f"     → Open the product system '{system.name}' in OpenLCA")
                print(f"     → Right-click and select 'Calculate'")
                print(f"     → Choose impact method: {target_method.name}")
                print(f"     → Ensure calculation completes successfully")
                print(f"     → Then re-run analysis in this platform")
            else:
                print(
                    f"✅ Successfully obtained {len(impact_results)} non-zero impact categories"
                )

            return {
                "method_name": target_method.name,
                "total_categories": len(impact_results),
                "impact_results": impact_results,
                "midpoint_results": midpoint_results,
                "endpoint_results": endpoint_results,
                "midpoint_count": len(midpoint_results),
                "endpoint_count": len(endpoint_results),
            }

        except Exception as e:
            print(f"❌ Error in impact analysis: {e}")
            return {"error": str(e)}

    def _get_process_results(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get process-level results"""
        try:
            print("⚙️ Analyzing process results...")

            processes = []
            process_categories = {}

            if hasattr(system, "processes") and system.processes:
                for process_link in system.processes:
                    if hasattr(process_link, "process") and process_link.process:
                        process_obj = process_link.process
                        process_info = {
                            "name": getattr(process_obj, "name", "Unknown"),
                            "id": getattr(process_obj, "id", ""),
                            "category": getattr(
                                getattr(process_obj, "category", None),
                                "name",
                                "Uncategorized",
                            ),
                            "location": getattr(
                                getattr(process_obj, "location", None), "name", ""
                            ),
                            "process_type": str(
                                getattr(process_obj, "process_type", "Unknown")
                            ),
                            "exchanges": [],
                        }
                        if hasattr(process_obj, "exchanges") and process_obj.exchanges:
                            for exchange in process_obj.exchanges[:20]:
                                if exchange.flow:
                                    exchange_info = {
                                        "flow_name": exchange.flow.name,
                                        "flow_type": (
                                            str(exchange.flow.flow_type)
                                            if hasattr(exchange.flow, "flow_type")
                                            else "Unknown"
                                        ),
                                        "amount": exchange.amount,
                                        "unit": (
                                            exchange.unit.name if exchange.unit else ""
                                        ),
                                        "is_input": exchange.is_input,
                                        "provider": (
                                            exchange.default_provider.name
                                            if hasattr(exchange, "default_provider")
                                            and exchange.default_provider
                                            else "N/A"
                                        ),
                                    }
                                    process_info["exchanges"].append(exchange_info)
                        processes.append(process_info)

                        category = process_info["category"]
                        if category not in process_categories:
                            process_categories[category] = []
                        process_categories[category].append(process_info)

            return {
                "total_processes": len(processes),
                "process_list": processes,
                "categories": process_categories,
                "category_count": len(process_categories),
            }

        except Exception as e:
            print(f"❌ Error analyzing processes: {e}")
            return {"error": str(e)}

    def _get_contribution_analysis(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get contribution analysis with process-level impact contributions"""
        try:
            print("🌳 Generating contribution analysis...")

            target_method = self.select_impact_method(
                system.name if hasattr(system, "name") else "unknown",
                "Contribution analysis",
            )

            if not target_method:
                print("⚠️ No impact method found for contribution analysis")
                return {
                    "error": "No impact method available",
                    "system_structure": {
                        "reference_process": "Unknown",
                        "total_processes": len(getattr(system, "processes", [])),
                    },
                }

            print(f"✅ Using method for contribution: {target_method.name}")

            setup = o.CalculationSetup()
            setup.target = o.Ref(id=system.id)
            setup.impact_method = o.Ref(id=target_method.id)

            setup.allocation = o.AllocationType.USE_DEFAULT_ALLOCATION

            setup.amount = 1.0
            print(f"📊 Calculation amount set to: 1.0 kg (fixed functional unit)")

            result = self.client.calculate(setup)
            if not result:
                return {"error": "Calculation failed"}

            result.wait_until_ready()
            print("✅ Contribution calculation completed")

            process_contributions = []
            selected_category_name = None
            selected_category_unit = None
            all_category_contributions = {}

            try:

                if hasattr(result, "get_total_impacts"):
                    total_impacts = result.get_total_impacts()
                    print(
                        f"📊 Found {len(total_impacts) if total_impacts else 0} impact categories"
                    )

                    if total_impacts and len(total_impacts) > 0:

                        climate_impacts = []
                        other_impact = None

                        for impact in total_impacts:
                            if hasattr(impact, "amount") and abs(impact.amount) > 1e-15:
                                if (
                                    hasattr(impact, "impact_category")
                                    and impact.impact_category
                                ):
                                    category_name = (
                                        impact.impact_category.name
                                        if hasattr(impact.impact_category, "name")
                                        else "Unknown"
                                    )

                                    if any(
                                        keyword in category_name.lower()
                                        for keyword in [
                                            "climate",
                                            "gwp",
                                            "warming",
                                            "gtp",
                                        ]
                                    ):
                                        climate_impacts.append(impact)
                                        print(
                                            f"  ✓ 发现Climate Change类别: {category_name}"
                                        )
                                    elif other_impact is None:
                                        other_impact = impact

                        if not climate_impacts and other_impact:
                            climate_impacts = [other_impact]
                            print(f"⚠️ 未找到Climate Change类别，使用第一个非零类别")

                        print(f"📊 将为 {len(climate_impacts)} 个影响类别计算贡献")

                        for idx, selected_impact in enumerate(climate_impacts):
                            if not (
                                selected_impact
                                and hasattr(selected_impact, "impact_category")
                            ):
                                continue

                            total_amount = selected_impact.amount
                            impact_category_ref = selected_impact.impact_category
                            category_name = (
                                impact_category_ref.name
                                if hasattr(impact_category_ref, "name")
                                else "Unknown"
                            )
                            unit = (
                                impact_category_ref.ref_unit
                                if hasattr(impact_category_ref, "ref_unit")
                                else "kg CO2 eq"
                            )

                            if idx == 0:
                                selected_category_name = category_name
                                selected_category_unit = unit

                            print(
                                f"\n📊 [{idx+1}/{len(climate_impacts)}] Analyzing contributions for: {category_name}"
                            )
                            print(f"📊 Total impact: {total_amount} {unit}")

                            category_contributions = []

                            if hasattr(result, "get_impact_contributions_of"):
                                try:
                                    print("📊 Using get_impact_contributions_of API...")
                                    contributions = result.get_impact_contributions_of(
                                        impact_category_ref
                                    )
                                    print(
                                        f"📊 Found {len(contributions) if contributions else 0} contribution entries"
                                    )

                                    if contributions:
                                        for contrib in contributions:
                                            try:

                                                if (
                                                    hasattr(contrib, "tech_flow")
                                                    and contrib.tech_flow
                                                ):
                                                    tech_flow = contrib.tech_flow
                                                    amount = getattr(
                                                        contrib, "amount", 0
                                                    )

                                                    if (
                                                        hasattr(tech_flow, "provider")
                                                        and tech_flow.provider
                                                    ):
                                                        process_name = (
                                                            tech_flow.provider.name
                                                            if hasattr(
                                                                tech_flow.provider,
                                                                "name",
                                                            )
                                                            else "Unknown"
                                                        )
                                                        process_id = (
                                                            tech_flow.provider.id
                                                            if hasattr(
                                                                tech_flow.provider, "id"
                                                            )
                                                            else ""
                                                        )

                                                        if abs(amount) > 1e-15:
                                                            contribution_percent = (
                                                                (
                                                                    abs(amount)
                                                                    / abs(total_amount)
                                                                    * 100
                                                                )
                                                                if total_amount != 0
                                                                else 0
                                                            )

                                                            contrib_data = {
                                                                "process_name": process_name,
                                                                "process_id": process_id,
                                                                "impact_value": abs(
                                                                    amount
                                                                ),
                                                                "contribution_percent": contribution_percent,
                                                                "unit": unit,
                                                            }
                                                            category_contributions.append(
                                                                contrib_data
                                                            )

                                                            if idx == 0:
                                                                process_contributions.append(
                                                                    contrib_data.copy()
                                                                )

                                                            if (
                                                                len(
                                                                    category_contributions
                                                                )
                                                                <= 5
                                                            ):
                                                                print(
                                                                    f"  ✓ {process_name}: {abs(amount):.6e} ({contribution_percent:.2f}%)"
                                                                )
                                            except Exception as e:
                                                print(
                                                    f"⚠️ Error processing contribution: {e}"
                                                )
                                                continue

                                        if len(category_contributions) > 5:
                                            print(
                                                f"  ... 以及其他 {len(category_contributions) - 5} 个过程"
                                            )
                                        print(
                                            f"✅ Collected {len(category_contributions)} process contributions for {category_name}"
                                        )
                                except Exception as e:
                                    print(
                                        f"⚠️ Error using get_impact_contributions_of: {e}"
                                    )
                                    import traceback

                                    traceback.print_exc()

                            if category_contributions:
                                all_category_contributions[category_name] = (
                                    category_contributions
                                )
                                print(
                                    f"✅ 已保存 {category_name} 的 {len(category_contributions)} 个过程贡献"
                                )

                            if (
                                idx == 0
                                and not process_contributions
                                and hasattr(result, "get_tech_flows")
                                and hasattr(result, "get_direct_impacts_of")
                            ):
                                try:
                                    print(
                                        "📊 Trying alternative: get_tech_flows + get_direct_impacts_of..."
                                    )
                                    tech_flows = result.get_tech_flows()
                                    print(
                                        f"📊 Found {len(tech_flows) if tech_flows else 0} tech flows"
                                    )

                                    if tech_flows:
                                        for tech_flow in tech_flows:
                                            try:

                                                impacts = result.get_direct_impacts_of(
                                                    tech_flow
                                                )

                                                if impacts:

                                                    for impact in impacts:
                                                        if (
                                                            hasattr(
                                                                impact,
                                                                "impact_category",
                                                            )
                                                            and impact.impact_category
                                                        ):
                                                            if (
                                                                impact.impact_category.id
                                                                == impact_category_ref.id
                                                            ):
                                                                amount = getattr(
                                                                    impact, "amount", 0
                                                                )

                                                                if (
                                                                    abs(amount) > 1e-15
                                                                    and hasattr(
                                                                        tech_flow,
                                                                        "provider",
                                                                    )
                                                                    and tech_flow.provider
                                                                ):
                                                                    process_name = (
                                                                        tech_flow.provider.name
                                                                        if hasattr(
                                                                            tech_flow.provider,
                                                                            "name",
                                                                        )
                                                                        else "Unknown"
                                                                    )
                                                                    process_id = (
                                                                        tech_flow.provider.id
                                                                        if hasattr(
                                                                            tech_flow.provider,
                                                                            "id",
                                                                        )
                                                                        else ""
                                                                    )
                                                                    contribution_percent = (
                                                                        (
                                                                            abs(amount)
                                                                            / abs(
                                                                                total_amount
                                                                            )
                                                                            * 100
                                                                        )
                                                                        if total_amount
                                                                        != 0
                                                                        else 0
                                                                    )

                                                                    process_contributions.append(
                                                                        {
                                                                            "process_name": process_name,
                                                                            "process_id": process_id,
                                                                            "impact_value": abs(
                                                                                amount
                                                                            ),
                                                                            "contribution_percent": contribution_percent,
                                                                            "unit": unit,
                                                                        }
                                                                    )

                                                                    print(
                                                                        f"  ✓ {process_name}: {abs(amount):.6e} ({contribution_percent:.2f}%)"
                                                                    )
                                                                break
                                            except Exception as e:
                                                print(
                                                    f"⚠️ Error processing tech flow: {e}"
                                                )
                                                continue

                                        print(
                                            f"✅ Collected {len(process_contributions)} process contributions via alternative method"
                                        )
                                except Exception as e:
                                    print(f"⚠️ Alternative method failed: {e}")
                                    import traceback

                                    traceback.print_exc()

                            if (
                                not process_contributions
                                and hasattr(system, "processes")
                                and system.processes
                            ):
                                print(
                                    "⚠️ Using fallback method: iterating system processes"
                                )
                                print(
                                    f"📊 Analyzing {len(system.processes)} processes..."
                                )

                                process_count = min(len(system.processes), 20)

                                for i, process_link in enumerate(
                                    system.processes[:process_count]
                                ):
                                    try:
                                        if (
                                            hasattr(process_link, "process")
                                            and process_link.process
                                        ):
                                            process_ref = process_link.process
                                            process_name = getattr(
                                                process_ref, "name", f"Process {i+1}"
                                            )

                                            estimated_value = (
                                                total_amount / process_count
                                                if process_count > 0
                                                else 0
                                            )
                                            estimated_percent = (
                                                100.0 / process_count
                                                if process_count > 0
                                                else 0
                                            )

                                            process_contributions.append(
                                                {
                                                    "process_name": process_name,
                                                    "process_id": getattr(
                                                        process_ref, "id", ""
                                                    ),
                                                    "impact_value": abs(
                                                        estimated_value
                                                    ),
                                                    "contribution_percent": estimated_percent,
                                                    "unit": unit,
                                                }
                                            )
                                    except Exception as e:
                                        print(f"⚠️ Error processing process {i}: {e}")
                                        continue

                                print(
                                    f"✅ Collected {len(process_contributions)} processes (estimated contributions)"
                                )

                if not process_contributions:
                    print("⚠️ Could not get detailed contribution data")
                    print(
                        "💡 This may be due to API limitations or calculation settings"
                    )

            except Exception as e:
                print(f"⚠️ Error extracting process contributions: {e}")
                import traceback

                traceback.print_exc()

            try:
                result.dispose()
            except:
                pass

            contribution_info = {
                "system_structure": {
                    "reference_process": (
                        getattr(system.reference_process, "name", "Unknown")
                        if hasattr(system, "reference_process")
                        and system.reference_process
                        else "Unknown"
                    ),
                    "total_processes": len(getattr(system, "processes", [])),
                    "reference_exchange": str(
                        getattr(system, "reference_exchange", "Not specified")
                    ),
                },
                "process_contributions": process_contributions,
                "contribution_tree_available": len(process_contributions) > 0,
                "note": "Detailed process-level contributions require OpenLCA GUI calculation or contribution-specific API",
                "selected_impact_category": selected_category_name,
                "selected_impact_unit": selected_category_unit,
                "all_category_contributions": all_category_contributions,
                "available_categories": list(all_category_contributions.keys()),
            }

            print(f"\n📊 贡献分析完成:")
            print(f"  - 默认类别: {selected_category_name}")
            print(f"  - 总共分析了 {len(all_category_contributions)} 个影响类别")
            print(
                f"  - 可用类别: {', '.join(list(all_category_contributions.keys())[:3])}..."
            )

            return contribution_info

        except Exception as e:
            print(f"❌ Error in contribution analysis: {e}")
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    def _get_grouping_results(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get grouping analysis results"""
        try:
            print("📊 Analyzing grouping results...")

            try:
                if hasattr(o, "Category"):
                    categories = self.client.get_all(o.Category)
                    flow_categories = [
                        cat
                        for cat in categories
                        if hasattr(cat, "model_type") and cat.model_type == "FLOW"
                    ]
                    process_categories = [
                        cat
                        for cat in categories
                        if hasattr(cat, "model_type") and cat.model_type == "PROCESS"
                    ]
                else:
                    flow_categories = []
                    process_categories = []
                    print("⚠️ Category class not available in olca_schema")
            except Exception as e:
                print(f"⚠️ Could not get categories: {e}")
                flow_categories = []
                process_categories = []

            grouping_info = {
                "flow_grouping": {
                    "total_categories": len(flow_categories),
                    "categories": [
                        {"name": cat.name, "id": cat.id} for cat in flow_categories[:20]
                    ],
                },
                "process_grouping": {
                    "total_categories": len(process_categories),
                    "categories": [
                        {"name": cat.name, "id": cat.id}
                        for cat in process_categories[:20]
                    ],
                },
            }

            return grouping_info

        except Exception as e:
            print(f"❌ Error in grouping analysis: {e}")
            return {"error": str(e)}

    def _get_location_analysis(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get location analysis results"""
        try:
            print("🌍 Analyzing location data...")

            locations = self.client.get_all(o.Location)
            used_locations = set()

            if hasattr(system, "processes") and system.processes:
                for process_link in system.processes:
                    if hasattr(process_link, "process") and process_link.process:
                        if (
                            hasattr(process_link.process, "location")
                            and process_link.process.location
                        ):
                            used_locations.add(process_link.process.location.name)

            location_info = {
                "total_locations": len(locations),
                "used_locations": list(used_locations),
                "used_count": len(used_locations),
                "location_distribution": {loc: 1 for loc in used_locations},
            }

            return location_info

        except Exception as e:
            print(f"❌ Error in location analysis: {e}")
            return {"error": str(e)}

    def _get_sankey_diagram_data(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get data for Sankey diagram generation"""
        try:
            print("📈 Preparing Sankey diagram data...")

            nodes = []
            links = []

            reference_process = getattr(system, "reference_process", None)
            if reference_process:
                nodes.append(
                    {
                        "id": getattr(reference_process, "id", "unknown"),
                        "name": getattr(reference_process, "name", "Unknown Process"),
                        "type": "reference",
                    }
                )

            processes = getattr(system, "processes", [])
            if processes:
                for i, process_link in enumerate(processes[:20]):
                    process = getattr(process_link, "process", None)
                    if process:
                        nodes.append(
                            {
                                "id": getattr(process, "id", f"process_{i}"),
                                "name": getattr(process, "name", f"Process {i}"),
                                "type": "process",
                            }
                        )

                        if i > 0:
                            prev_process = getattr(processes[i - 1], "process", None)
                            links.append(
                                {
                                    "source": (
                                        getattr(prev_process, "id", f"process_{i-1}")
                                        if prev_process
                                        else ""
                                    ),
                                    "target": getattr(process, "id", f"process_{i}"),
                                    "value": 1,
                                }
                            )

            sankey_data = {
                "nodes": nodes,
                "links": links,
                "note": "Simplified Sankey diagram data - full implementation requires flow calculations",
            }

            return sankey_data

        except Exception as e:
            print(f"❌ Error preparing Sankey data: {e}")
            return {"error": str(e)}

    def _get_lcia_checks(self, system: o.ProductSystem) -> Dict[str, Any]:
        """Get LCIA checks and validation results"""
        try:
            from .config import ENABLE_DETAILED_LCIA_CHECKS

            print("✅ Performing LCIA checks...")

            checks = {
                "system_completeness": {
                    "has_reference_process": bool(
                        getattr(system, "reference_process", None)
                    ),
                    "has_processes": bool(
                        getattr(system, "processes", [])
                        and len(getattr(system, "processes", [])) > 0
                    ),
                    "has_reference_exchange": hasattr(system, "reference_exchange"),
                },
                "method_availability": {
                    "impact_methods_count": "N/A (detailed checks disabled)",
                    "preferred_method_available": False,
                },
                "data_quality": {
                    "total_flows": "N/A (detailed checks disabled)",
                    "total_processes": "N/A (detailed checks disabled)",
                    "total_product_systems": "N/A (detailed checks disabled)",
                },
            }

            if ENABLE_DETAILED_LCIA_CHECKS:
                print(
                    "⚠️ Detailed LCIA checks enabled - this may take several minutes on large databases..."
                )
                checks["method_availability"]["impact_methods_count"] = len(
                    self.client.get_all(o.ImpactMethod)
                )
                checks["data_quality"]["total_flows"] = len(self.client.get_all(o.Flow))
                checks["data_quality"]["total_processes"] = len(
                    self.client.get_all(o.Process)
                )
                checks["data_quality"]["total_product_systems"] = len(
                    self.client.get_all(o.ProductSystem)
                )

                methods = self.client.get_all(o.ImpactMethod)
                for method in methods:
                    if "ILCD".lower() in method.name.lower():
                        checks["method_availability"][
                            "preferred_method_available"
                        ] = True
                        checks["method_availability"][
                            "preferred_method_name"
                        ] = method.name
                        break
            else:
                print(
                    "💡 Detailed LCIA checks skipped (ENABLE_DETAILED_LCIA_CHECKS=False)"
                )

            return checks

        except Exception as e:
            print(f"❌ Error in LCIA checks: {e}")
            return {"error": str(e)}

    def _apply_provider_metadata(self, provider_ref: o.Ref, flow_ref: o.Ref):
        if not provider_ref or not flow_ref:
            return

        metadata = {}
        provider_info = self.excel_flow_providers.get(flow_ref.name)
        if isinstance(provider_info, dict):
            metadata = provider_info.get("metadata", {})

        if not metadata:

            flow_info = getattr(self, "parsed_flow_metadata", {}).get(flow_ref.name, {})
            metadata = flow_info.get("provider_flow_meta", {})

        if not metadata:
            return

        try:
            provider_process = self.client.get(o.Process, provider_ref.id)
            if not provider_process:
                return

            updated = False
            for exchange in provider_process.exchanges:
                if exchange.is_input:
                    continue
                if not exchange.flow:
                    continue
                if exchange.flow.name != flow_ref.name:
                    continue

                if metadata.get("unit"):
                    exchange.unit = metadata["unit"]
                if metadata.get("flow_type") and hasattr(exchange.flow, "flow_type"):
                    exchange.flow.flow_type = getattr(
                        o.FlowType, metadata["flow_type"], exchange.flow.flow_type
                    )
                if metadata.get("category") and not exchange.flow.category:
                    exchange.flow.category = metadata["category"]
                updated = True

            if updated:
                self.client.put(provider_process)
        except Exception as error:
            print(
                f"⚠️ Failed to apply provider metadata for '{provider_ref.name}': {error}"
            )
