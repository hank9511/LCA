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

        print(f"\n📊 Starting LCA calculation...")
        print(f"  - Product system: {system_name}")
        if system_uuid:
            print(f"  - System UUID: {system_uuid}")
        print(f"  - Uncertainty analysis: {'enabled' if self.uncertainty_enabled else 'disabled'}")
        if self.uncertainty_enabled:
            print(f"  - Monte Carlo iterations: {self.mc_iterations}")

        if provider_cv_results:
            self.modeler.provider_cv_results = provider_cv_results

        try:
            comprehensive_results = self.modeler.get_comprehensive_lca_results(
                system_name, system_uuid=system_uuid
            )

            print(f"\n✅ LCA calculation completed!")

            if comprehensive_results:
                self._print_results_summary(comprehensive_results)

            return comprehensive_results

        except Exception as e:
            print(f"\n❌ LCA calculation failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def calculate_deterministic_only(self, system_name: str) -> dict:

        print(f"\n📊 Starting deterministic LCA calculation...")
        print(f"  - Product system: {system_name}")

        try:
            results = self.modeler.calculate_results(system_name)

            print(f"\n✅ Deterministic calculation completed!")

            return results

        except Exception as e:
            print(f"\n❌ Deterministic calculation failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def run_monte_carlo_only(
        self, system_name: str, provider_cv_results: dict = None
    ) -> dict:

        print(f"\n🎲 Starting Monte Carlo uncertainty analysis...")
        print(f"  - Product system: {system_name}")
        print(f"  - Iterations: {self.mc_iterations}")

        if provider_cv_results:
            self.modeler.provider_cv_results = provider_cv_results

        try:
            mc_results = self.modeler.run_monte_carlo_analysis(system_name)

            print(f"\n✅ Monte Carlo analysis completed!")

            return mc_results

        except Exception as e:
            print(f"\n❌ Monte Carlo analysis failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_contribution_analysis(self, system_name: str) -> dict:

        print(f"\n🌳 Starting contribution analysis...")
        print(f"  - Product system: {system_name}")

        try:

            system_ref = self.client.find(o.ProductSystem, system_name)
            if not system_ref:
                print(f"❌ Product system not found: {system_name}")
                return None

            system = self.client.get(o.ProductSystem, system_ref.id)

            contribution_results = self.modeler._get_contribution_analysis(system)

            print(f"\n✅ Contribution analysis completed!")

            return contribution_results

        except Exception as e:
            print(f"\n❌ Contribution analysis failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _print_results_summary(self, results: dict):

        print(f"\n{'='*60}")
        print(f"📊 LCA results summary")
        print(f"{'='*60}")

        if "system_info" in results:
            sys_info = results["system_info"]
            print(f"\n📦 System info:")
            print(f"  - Name: {sys_info.get('name', 'N/A')}")
            print(f"  - Process count: {sys_info.get('process_count', 'N/A')}")

        if "impact_analysis" in results:
            impact = results["impact_analysis"]
            print(f"\n🌍 Impact assessment:")
            print(f"  - Method: {impact.get('impact_method', 'N/A')}")
            impact_results = impact.get("impact_results", [])
            if impact_results:
                print(f"  - Impact category count: {len(impact_results)}")

                for i, imp in enumerate(impact_results[:3], 1):
                    cat_name = imp.get("category", "Unknown")
                    value = imp.get("value", 0)
                    unit = imp.get("unit", "")
                    print(f"    {i}. {cat_name}: {value:.6e} {unit}")
                if len(impact_results) > 3:
                    print(f"    ... and {len(impact_results) - 3} more impact categories")

        if "uncertainty_analysis" in results and results["uncertainty_analysis"]:
            unc = results["uncertainty_analysis"]
            print(f"\n🎲 Uncertainty analysis:")
            if "iterations" in unc:
                print(f"  - Monte Carlo iterations: {unc['iterations']}")
            if "impact_categories" in unc:
                print(f"  - Impact categories analyzed: {len(unc['impact_categories'])}")

        print(f"\n{'='*60}")

    def export_results(self, results: dict, output_path: str, format: str = "json"):

        import json

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"✅ Results exported to: {output_path}")

        elif format == "excel":
            print(f"⚠️ Excel export is not implemented yet")
        elif format == "html":
            print(f"⚠️ HTML export is not implemented yet")


if __name__ == "__main__":

    print("ResultCalculator module - for LCA result calculation")
    print("Includes inventory analysis, impact assessment, contribution analysis, and uncertainty analysis")
