from typing import Dict, Optional, Any

import olca_ipc as ipc
import olca_schema as o
from .lca_modeler import UniversalLCAModeler
from .config import (
    UNCERTAINTY_ANALYSIS_ENABLED,
    MONTE_CARLO_ITERATIONS,
    PREFERRED_LCIA_METHOD,
)


class ResultCalculator:

    def __init__(
        self,
        client: ipc.Client,
        llm_clients: dict = None,
        config: dict = None,
        project_context=None,
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

        self.uncertainty_enabled = self.config.get(
            "UNCERTAINTY_ANALYSIS_ENABLED", UNCERTAINTY_ANALYSIS_ENABLED
        )
        self.mc_iterations = self.config.get(
            "MONTE_CARLO_ITERATIONS", MONTE_CARLO_ITERATIONS
        )
        self.preferred_method = self.config.get(
            "PREFERRED_LCIA_METHOD", PREFERRED_LCIA_METHOD
        )

        if self.preferred_method:
            self.modeler.set_preferred_impact_method(self.preferred_method)

    def calculate_comprehensive_results(
        self,
        system_name: str,
        provider_cv_results: dict = None,
        system_uuid: str = None,
    ) -> dict:

        print(f"\n📊 开始LCA计算...")
        print(f"  - 产品系统: {system_name}")
        if system_uuid:
            print(f"  - 系统UUID: {system_uuid}")
        print(f"  - 不确定性分析: {'启用' if self.uncertainty_enabled else '不启用'}")
        if self.uncertainty_enabled:
            print(f"  - Monte Carlo迭代次数: {self.mc_iterations}")

        if provider_cv_results:
            self.modeler.provider_cv_results = provider_cv_results

        try:
            comprehensive_results = self.modeler.get_comprehensive_lca_results(
                system_name, system_uuid=system_uuid
            )

            print(f"\n✅ LCA计算完成!")

            if comprehensive_results:
                self._print_results_summary(comprehensive_results)

            return comprehensive_results

        except Exception as e:
            print(f"\n❌ LCA计算失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def calculate_deterministic_only(self, system_name: str) -> dict:

        print(f"\n📊 开始确定性LCA计算...")
        print(f"  - 产品系统: {system_name}")

        try:
            results = self.modeler.calculate_results(system_name)

            print(f"\n✅ 确定性计算完成!")

            return results

        except Exception as e:
            print(f"\n❌ 确定性计算失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def run_monte_carlo_only(
        self, system_name: str, provider_cv_results: dict = None
    ) -> dict:

        print(f"\n🎲 开始Monte Carlo不确定性分析...")
        print(f"  - 产品系统: {system_name}")
        print(f"  - 迭代次数: {self.mc_iterations}")

        if provider_cv_results:
            self.modeler.provider_cv_results = provider_cv_results

        try:
            mc_results = self.modeler.run_monte_carlo_analysis(system_name)

            print(f"\n✅ Monte Carlo分析完成!")

            return mc_results

        except Exception as e:
            print(f"\n❌ Monte Carlo分析失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_contribution_analysis(self, system_name: str) -> dict:

        print(f"\n🌳 开始贡献分析...")
        print(f"  - 产品系统: {system_name}")

        try:

            system_ref = self.client.find(o.ProductSystem, system_name)
            if not system_ref:
                print(f"❌ 产品系统未找到: {system_name}")
                return None

            system = self.client.get(o.ProductSystem, system_ref.id)

            contribution_results = self.modeler._get_contribution_analysis(system)

            print(f"\n✅ 贡献分析完成!")

            return contribution_results

        except Exception as e:
            print(f"\n❌ 贡献分析失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _print_results_summary(self, results: dict):

        print(f"\n{'='*60}")
        print(f"📊 LCA结果摘要")
        print(f"{'='*60}")

        if "system_info" in results:
            sys_info = results["system_info"]
            print(f"\n📦 系统信息:")
            print(f"  - 名称: {sys_info.get('name', 'N/A')}")
            print(f"  - 过程数: {sys_info.get('process_count', 'N/A')}")

        if "impact_analysis" in results:
            impact = results["impact_analysis"]
            print(f"\n🌍 影响评价:")
            print(f"  - 方法: {impact.get('impact_method', 'N/A')}")
            impact_results = impact.get("impact_results", [])
            if impact_results:
                print(f"  - 影响类别数: {len(impact_results)}")

                for i, imp in enumerate(impact_results[:3], 1):
                    cat_name = imp.get("category", "Unknown")
                    value = imp.get("value", 0)
                    unit = imp.get("unit", "")
                    print(f"    {i}. {cat_name}: {value:.6e} {unit}")
                if len(impact_results) > 3:
                    print(f"    ... 还有 {len(impact_results) - 3} 个影响类别")

        if "uncertainty_analysis" in results and results["uncertainty_analysis"]:
            unc = results["uncertainty_analysis"]
            print(f"\n🎲 不确定性分析:")
            if "iterations" in unc:
                print(f"  - Monte Carlo迭代: {unc['iterations']}")
            if "impact_categories" in unc:
                print(f"  - 分析的影响类别: {len(unc['impact_categories'])}")

        print(f"\n{'='*60}")

    def export_results(self, results: dict, output_path: str, format: str = "json"):

        import json

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"✅ 结果已导出到: {output_path}")

        elif format == "excel":
            print(f"⚠️ Excel导出功能尚未实现")
        elif format == "html":
            print(f"⚠️ HTML导出功能尚未实现")


if __name__ == "__main__":

    print("ResultCalculator模块 - 用于LCA结果计算")
    print("包括清单分析、影响评价、贡献分析和不确定性分析")
