from typing import Dict, List, Optional, Tuple, Any

import Levenshtein
import olca_ipc as ipc
import olca_schema as o
from .data_structures import LCACase
from .uncertainty import _is_market_activity
from .config import (
    USE_LLM_FOR_PROVIDER_SELECTION,
    LLM_PROVIDER_SELECTION_MAX_CANDIDATES,
    CANDIDATE_CONSTRAINT_MODE,
)


class ProviderSelector:

    def __init__(
        self, client: ipc.Client, llm_clients: dict = None, config: dict = None
    ):

        self.client = client
        self.llm_clients = llm_clients or {}
        self.config = config or {}
        self.use_llm = self.config.get(
            "USE_LLM_FOR_PROVIDER_SELECTION", USE_LLM_FOR_PROVIDER_SELECTION
        )
        self.provider_cv_results = {}

    def select_provider(
        self,
        flow_ref: o.Ref,
        flow_name: str,
        process_context: str = "Unknown Process",
        excel_provider: str = None,
        candidates: List[o.Ref] = None,
    ) -> Tuple[Optional[o.Ref], float]:

        if excel_provider:
            provider_ref = self._find_excel_provider(excel_provider)
            if provider_ref:
                print(f"    🎯 使用Excel指定的Provider: {excel_provider}")
                return provider_ref, 0.0
            print(f"    ⚠️ Excel指定的Provider未找到: {excel_provider}")

        if not candidates or len(candidates) == 0:
            return None, 0.0

        if len(candidates) == 1:
            print(f"    ✓ 仅一个候选Provider: {candidates[0].name}")
            return candidates[0], 0.0

        provider_ref, metadata = self._select_by_semantic_similarity(
            flow_name, candidates
        )
        if provider_ref:
            score = metadata.get("semantic_score", 0.0)
            print(
                f"    ✓ 语义匹配选择Provider: {provider_ref.name} "
                f"(score={score:.3f})"
            )
            return provider_ref, 0.0

        default_provider = candidates[0]
        print(f"    ✓ 使用默认Provider: {default_provider.name}")
        return default_provider, 0.0

    def _select_by_semantic_similarity(
        self, flow_name: str, candidates: List[o.Ref]
    ) -> Tuple[Optional[o.Ref], Dict[str, Any]]:

        candidate_mode = (
            str(self.config.get("CANDIDATE_CONSTRAINT_MODE", CANDIDATE_CONSTRAINT_MODE))
            .strip()
            .lower()
        )
        pool = list(candidates)
        if candidate_mode != "expanded_or_unconstrained":
            market_refs = [ref for ref in pool if _is_market_activity(ref.name or "")]
            if market_refs:
                pool = market_refs
            max_candidates = int(
                self.config.get(
                    "SEMANTIC_SELECTION_MAX_CANDIDATES",
                    LLM_PROVIDER_SELECTION_MAX_CANDIDATES,
                )
                or 0
            )
            if max_candidates > 0:
                pool = pool[:max_candidates]

        scored: List[Tuple[float, o.Ref]] = []
        target = (flow_name or "").lower()
        for candidate in pool:
            cand_name = (candidate.name or "").lower()
            if not cand_name:
                continue
            scored.append((Levenshtein.ratio(target, cand_name), candidate))

        if not scored:
            return None, {}

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_provider = scored[0]
        return best_provider, {
            "selection_mode": "semantic_only",
            "semantic_score": best_score,
            "candidate_count": len(pool),
        }

    def _find_excel_provider(self, provider_name: str) -> Optional[o.Ref]:

        try:
            processes = self.client.get_all(o.Process)
            for process_ref in processes:
                if process_ref.name == provider_name:
                    return process_ref

            for process_ref in processes:
                if provider_name.lower() in process_ref.name.lower():
                    return process_ref

            return None

        except Exception as e:
            print(f"    ⚠️ 查找Provider时出错: {e}")
            return None

    def select_providers_for_case(
        self, lca_case: LCACase, flow_refs: Dict[str, o.Ref]
    ) -> Dict[str, Any]:

        print(f"\n🎯 开始为 {len(lca_case.processes)} 个Processes选择Providers...")

        provider_results = {
            "providers": {},
            "cv_values": {},
            "summary": {},
        }

        total_selections = 0

        for process_spec in lca_case.processes:
            process_name = process_spec.name

            if not hasattr(process_spec, "_simple_exchanges"):
                continue

            for simple_ex in process_spec._simple_exchanges:
                if not simple_ex.is_input and not simple_ex.is_avoided_product:
                    continue

                flow_name = simple_ex.flow_name
                flow_ref = flow_refs.get(flow_name)

                if not flow_ref:
                    continue

                excel_provider = (
                    simple_ex.provider_name if simple_ex.provider_name else None
                )
                candidates = self._get_provider_candidates(flow_ref)

                provider_ref, cv = self.select_provider(
                    flow_ref, flow_name, process_name, excel_provider, candidates
                )

                if provider_ref:
                    key = f"{process_name}_{flow_name}"
                    provider_results["providers"][key] = {
                        "ref": provider_ref,
                        "cv": cv,
                    }
                    provider_results["cv_values"][key] = cv
                    total_selections += 1

        provider_results["summary"] = {
            "total_selections": total_selections,
            "default_selections": total_selections,
        }

        print(f"\n✅ Provider选择完成:")
        print(f"  - 总选择数: {total_selections}")

        return provider_results

    def _get_provider_candidates(self, flow_ref: o.Ref) -> List[o.Ref]:

        try:
            providers = self.client.get_providers_of(flow_ref)
            valid_providers = []
            for provider in providers:
                if provider and hasattr(provider, "name"):
                    valid_providers.append(provider)
            return valid_providers
        except Exception as e:
            print(f"    ⚠️ 获取候选providers时出错: {e}")
            return []

    def get_upstream_provider_uuids(
        self, lca_case: LCACase, provider_results: Dict
    ) -> List[str]:

        provider_uuids = []

        for key, data in provider_results.get("providers", {}).items():
            provider_ref = data.get("ref")
            if provider_ref and hasattr(provider_ref, "id"):
                provider_uuids.append(provider_ref.id)

        provider_uuids = list(set(provider_uuids))
        print(f"\n🔗 找到 {len(provider_uuids)} 个唯一的上游Providers")
        return provider_uuids


if __name__ == "__main__":
    print("ProviderSelector模块 - 使用语义匹配选择Provider")
