from typing import Dict, List, Optional, Any, Tuple

import olca_ipc as ipc
import olca_schema as o
from .data_structures import LCACase, Flow, Process, ProductSystem, SimpleExchange
from .lca_modeler import UniversalLCAModeler
from .config import CUTOFF_THRESHOLD


class ModelBuilder:

    def __init__(
        self,
        client: ipc.Client,
        llm_clients: dict = None,
        project_context=None,
        config: dict = None,
    ):

        self.client = client
        self.llm_clients = llm_clients or {}
        self.config = config or {}

        self.modeler = UniversalLCAModeler(
            client,
            llm_clients,
            project_context,
            runtime_config=self.config,
        )

        self.created_flows = {}
        self.created_processes = {}

    def build_flows(self, lca_case: LCACase) -> Dict[str, o.Ref]:

        return self.modeler.created_flows

    def build_complete_model(self, lca_case: LCACase) -> Dict[str, Any]:

        return self.modeler.build_lca_case(lca_case)

    def build_processes(
        self,
        lca_case: LCACase,
        flow_refs: Dict[str, o.Ref],
        provider_results: Dict = None,
    ) -> Dict[str, o.Ref]:

        print(f"\n🏗️ 开始创建 {len(lca_case.processes)} 个Processes...")

        process_refs = {}

        for i, process_spec in enumerate(lca_case.processes, 1):
            process_name = process_spec.name

            try:

                exchanges = []

                if hasattr(process_spec, "_simple_exchanges"):
                    simple_exchanges = process_spec._simple_exchanges

                    for simple_ex in simple_exchanges:
                        flow_name = simple_ex.flow_name
                        flow_ref = flow_refs.get(flow_name)

                        if not flow_ref:
                            print(f"    ⚠️ Flow未找到: {flow_name}")
                            continue

                        exchange = o.Exchange()
                        exchange.flow = flow_ref
                        exchange.amount = simple_ex.amount
                        exchange.is_input = simple_ex.is_input
                        exchange.is_quantitative_reference = (
                            simple_ex.is_quantitative_reference
                        )
                        exchange.is_avoided_product = simple_ex.is_avoided_product

                        unit_name = simple_ex.unit
                        unit_ref = self.modeler._find_unit_ref(unit_name, flow_ref)
                        if unit_ref:
                            exchange.unit = unit_ref

                        flow_property = self.modeler._get_flow_property_for_unit(
                            flow_ref, unit_name
                        )
                        if flow_property:
                            exchange.flow_property = flow_property

                        if provider_results and simple_ex.provider_name:
                            provider_data = provider_results.get("providers", {}).get(
                                f"{process_name}_{flow_name}", None
                            )
                            if provider_data:
                                exchange.default_provider = provider_data["ref"]

                        cv = provider_data.get("cv", 0.0)
                        if cv > 0:
                            from .uncertainty import create_uncertainty_from_cv

                            exchange.uncertainty = create_uncertainty_from_cv(
                                cv, simple_ex.amount
                            )

                        if simple_ex.allocation_value > 0:
                            exchange.cost_value = simple_ex.allocation_value
                        if simple_ex.cost_value > 0:
                            exchange.cost_value = simple_ex.cost_value

                        exchanges.append(exchange)

                process = o.Process()
                process.name = process_name
                process.category = process_spec.category
                process.description = process_spec.description
                process.process_type = o.ProcessType.UNIT_PROCESS
                process.exchanges = exchanges

                process_ref = self.client.insert(process)
                process_refs[process_name] = process_ref
                self.created_processes[process_name] = process_ref

                print(
                    f"  [{i}/{len(lca_case.processes)}] ✓ {process_name} ({len(exchanges)} exchanges)"
                )

            except Exception as e:
                print(f"  [{i}/{len(lca_case.processes)}] ✗ {process_name} - 错误: {e}")
                import traceback

                traceback.print_exc()

        print(f"✅ 完成Process创建: {len(process_refs)}/{len(lca_case.processes)}")
        return process_refs

    def build_product_systems(
        self, lca_case: LCACase, process_refs: Dict[str, o.Ref]
    ) -> Dict[str, str]:

        print(f"\n🏗️ 开始创建 {len(lca_case.product_systems)} 个Product Systems...")

        system_results = {}

        for i, system_spec in enumerate(lca_case.product_systems, 1):
            system_name = system_spec.name

            try:

                ref_process_name = None
                if hasattr(system_spec, "ref_process") and system_spec.ref_process:
                    if hasattr(system_spec.ref_process, "name"):
                        ref_process_name = system_spec.ref_process.name

                if not ref_process_name and lca_case.processes:
                    ref_process_name = lca_case.processes[-1].name

                ref_process_ref = process_refs.get(ref_process_name)

                if not ref_process_ref:
                    print(
                        f"  [{i}/{len(lca_case.product_systems)}] ✗ {system_name} - 参考过程未找到"
                    )
                    continue

                linking_config = o.LinkingConfig(
                    prefer_unit_processes=False,
                    provider_linking=o.ProviderLinking.ONLY_DEFAULTS,
                )

                if CUTOFF_THRESHOLD is not None:
                    linking_config.cutoff = CUTOFF_THRESHOLD
                    print(
                        f"  ✓ 应用截断阈值: {CUTOFF_THRESHOLD * 100}%（贡献度低于此值的上游链将被截断）"
                    )

                system_ref = self.client.create_product_system(
                    ref_process_ref, linking_config
                )

                system = self.client.get(o.ProductSystem, system_ref.id)
                system.name = system_name
                system.description = system_spec.description
                system.target_amount = 1.0

                self.client.put(system)

                system_results[system_name] = system.id

                print(
                    f"  [{i}/{len(lca_case.product_systems)}] ✓ {system_name} (UUID: {system.id})"
                )

            except Exception as e:
                print(
                    f"  [{i}/{len(lca_case.product_systems)}] ✗ {system_name} - 错误: {e}"
                )
                import traceback

                traceback.print_exc()

        print(
            f"✅ 完成Product System创建: {len(system_results)}/{len(lca_case.product_systems)}"
        )
        return system_results


if __name__ == "__main__":

    print("ModelBuilder模块 - 用于创建Flow、Process和ProductSystem")
