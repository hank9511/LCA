import time
from typing import Dict, Optional, Any

import olca_ipc as ipc
import olca_schema as o
from .llm_utils import initialize_llm_clients
from .project_context import ProjectContext

from .data_parser import DataParser
from .model_builder import ModelBuilder
from .provider_selector import ProviderSelector
from .upstream_merger import UpstreamMerger
from .result_calculator import ResultCalculator
from .config import (
    PROVIDER_SELECTION_MODE,
    CANDIDATE_CONSTRAINT_MODE,
    ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
)

ABLATION_VARIANT_CONFIGS = {
    "full": {
        "PROVIDER_SELECTION_MODE": "semantic_only",
        "CANDIDATE_CONSTRAINT_MODE": "constrained",
        "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION": True,
    },
    "semantic_only": {
        "PROVIDER_SELECTION_MODE": "semantic_only",
        "CANDIDATE_CONSTRAINT_MODE": "constrained",
        "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION": True,
    },
    "unconstrained_candidate": {
        "PROVIDER_SELECTION_MODE": "semantic_only",
        "CANDIDATE_CONSTRAINT_MODE": "expanded_or_unconstrained",
        "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION": True,
    },
    "no_stage_classification": {
        "PROVIDER_SELECTION_MODE": "semantic_only",
        "CANDIDATE_CONSTRAINT_MODE": "constrained",
        "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION": False,
    },
}

DEFAULT_ABLATION_SETTINGS = {
    "PROVIDER_SELECTION_MODE": PROVIDER_SELECTION_MODE,
    "CANDIDATE_CONSTRAINT_MODE": CANDIDATE_CONSTRAINT_MODE,
    "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION": ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
}


def _to_bool(value: Any) -> bool:

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return bool(value)


def _infer_variant_from_settings(config: Dict[str, Any]) -> str:

    for variant, variant_cfg in ABLATION_VARIANT_CONFIGS.items():
        if (
            str(config.get("PROVIDER_SELECTION_MODE", "")).strip().lower()
            == str(variant_cfg["PROVIDER_SELECTION_MODE"]).strip().lower()
            and str(config.get("CANDIDATE_CONSTRAINT_MODE", "")).strip().lower()
            == str(variant_cfg["CANDIDATE_CONSTRAINT_MODE"]).strip().lower()
            and _to_bool(config.get("ENABLE_LIFECYCLE_STAGE_CLASSIFICATION"))
            == bool(variant_cfg["ENABLE_LIFECYCLE_STAGE_CLASSIFICATION"])
        ):
            return variant
    return "custom"


def build_ablation_config(
    config: Dict[str, Any], ablation_variant: Optional[str] = None
) -> Dict[str, Any]:

    incoming = dict(config or {})
    requested_variant = (
        incoming.get("ABLATION_VARIANT")
        or incoming.get("ablation_variant")
        or ablation_variant
    )

    merged = dict(DEFAULT_ABLATION_SETTINGS)

    if requested_variant in ABLATION_VARIANT_CONFIGS:
        merged.update(ABLATION_VARIANT_CONFIGS[requested_variant])

    merged.update(incoming)

    merged["PROVIDER_SELECTION_MODE"] = (
        str(merged.get("PROVIDER_SELECTION_MODE", PROVIDER_SELECTION_MODE))
        .strip()
        .lower()
    )
    if merged["PROVIDER_SELECTION_MODE"] == "full":
        print(
            "ℹ️ Public snapshot: pedigree-matrix provider screening is not included; "
            "using semantic matching."
        )
        merged["PROVIDER_SELECTION_MODE"] = "semantic_only"
    merged["CANDIDATE_CONSTRAINT_MODE"] = (
        str(merged.get("CANDIDATE_CONSTRAINT_MODE", CANDIDATE_CONSTRAINT_MODE))
        .strip()
        .lower()
    )
    merged["ENABLE_LIFECYCLE_STAGE_CLASSIFICATION"] = _to_bool(
        merged.get(
            "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION",
            ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
        )
    )
    merged["ABLATION_VARIANT"] = (
        requested_variant
        if requested_variant in ABLATION_VARIANT_CONFIGS
        else _infer_variant_from_settings(merged)
    )
    return merged


def _build_project_context_from_metadata(lca_case) -> ProjectContext:

    from .project_context import FunctionalUnitSpec

    context = ProjectContext.default()

    excel_metadata = getattr(lca_case, "excel_metadata", None)
    if not excel_metadata:
        return context

    scope = excel_metadata.get("quantification_scope", {})
    system_boundary_desc = scope.get("system_boundary", "")
    functional_unit_str = scope.get("functional_unit", "")

    if system_boundary_desc:
        context.system_boundary.description = system_boundary_desc

        _extract_geographic_scope(context, system_boundary_desc)

    if functional_unit_str:
        context.functional_unit = FunctionalUnitSpec.parse(functional_unit_str)

    product_info = excel_metadata.get("product_info", {})
    context.product_name = product_info.get("product_name", "")

    producer_info = excel_metadata.get("producer_info", {})
    context.producer_name = producer_info.get("producer_name", "")

    if system_boundary_desc:
        print(f"🌍 Extracted system boundary from Excel: {system_boundary_desc[:150]}...")
        if context.system_boundary.geographic_scope:
            print(f"🌍 Identified geographic scope: {context.system_boundary.geographic_scope}")

    return context


def _extract_geographic_scope(context: ProjectContext, description: str):

    desc_lower = description.lower()

    geo_keywords = {
        "india": "India",
        "indian": "India",
        "china": "China",
        "chinese": "China",
        "shanghai": "China",
        "germany": "Germany",
        "german": "Germany",
        "berlin": "Germany",
        "europe": "Europe",
        "european": "Europe",
        "usa": "USA",
        "united states": "USA",
        "american": "USA",
        "japan": "Japan",
        "japanese": "Japan",
        "korea": "Korea",
        "korean": "Korea",
        "brazil": "Brazil",
        "brazilian": "Brazil",
        "australia": "Australia",
        "australian": "Australia",
        "canada": "Canada",
        "canadian": "Canada",
        "france": "France",
        "french": "France",
        "uk": "UK",
        "united kingdom": "UK",
        "britain": "UK",
        "british": "UK",
        "italy": "Italy",
        "italian": "Italy",
        "spain": "Spain",
        "spanish": "Spain",
        "russia": "Russia",
        "russian": "Russia",
        "africa": "Africa",
        "african": "Africa",
        "asia": "Asia",
        "asian": "Asia",
        "south america": "South America",
        "north america": "North America",
        "global": "Global",
    }

    found_regions = []
    for keyword, region_name in geo_keywords.items():
        if keyword in desc_lower and region_name not in found_regions:
            found_regions.append(region_name)

    if found_regions:
        context.system_boundary.geographic_scope = ", ".join(found_regions)
    else:
        context.system_boundary.geographic_scope = "China"
        print(f"🌍 No specific region found in system boundary description; defaulting to China (CN)")


def run_automated_lca_workflow(
    excel_path: str,
    database_path: str = "ecoinvent_0121",
    config: dict = None,
    ablation_variant: Optional[str] = None,
    ipc_port: int = 8080,
) -> dict:

    config = build_ablation_config(config or {}, ablation_variant=ablation_variant)

    print("=" * 80)
    print("🌍 Automated LCA modeling system")
    print("=" * 80)
    print(f"📄 Excel file: {excel_path}")
    print(f"🗄️ Database: {database_path}")
    print(
        "🧪 Ablation config: "
        f"variant={config.get('ABLATION_VARIANT', 'custom')}, "
        f"provider_mode={config.get('PROVIDER_SELECTION_MODE', PROVIDER_SELECTION_MODE)}, "
        f"candidate_mode={config.get('CANDIDATE_CONSTRAINT_MODE', CANDIDATE_CONSTRAINT_MODE)}, "
        f"stage_classification={config.get('ENABLE_LIFECYCLE_STAGE_CLASSIFICATION', ENABLE_LIFECYCLE_STAGE_CLASSIFICATION)}"
    )
    print("=" * 80)

    result = {
        "success": False,
        "lca_case": None,
        "flow_refs": {},
        "process_refs": {},
        "system_uuid": None,
        "provider_results": {},
        "lca_results": None,
        "ablation_settings": {},
        "error": None,
    }

    try:

        model_build_start = time.time()
        print(f"\n{'='*80}")
        print("🔌 Step 1: Connecting to OpenLCA")
        print("=" * 80)

        try:
            client = ipc.Client(ipc_port)
            print(f"✅ Successfully connected to OpenLCA (port {ipc_port})")
        except Exception as e:
            print(f"❌ Unable to connect to OpenLCA: {e}")
            print("Please ensure:")
            print("  - OpenLCA is running")
            print("  - The IPC server is enabled in developer tools")
            print(f"  - The IPC server port is {ipc_port}")
            result["error"] = f"OpenLCA connection failed: {e}"
            return result

        print("\n🤖 Initializing LLM clients...")
        llm_clients = initialize_llm_clients()
        working_llms = [
            name for name, client in llm_clients.items() if client is not None
        ]

        if working_llms:
            print(f"✅ Available LLMs: {', '.join(working_llms)}")
        else:
            print("⚠️ No available LLMs; falling back to basic mode")

        print(f"\n{'='*80}")
        print("📊 Step 2: Parsing Excel data")
        print("=" * 80)

        parser = DataParser(excel_path, database_path)
        lca_case = parser.parse()
        result["lca_case"] = lca_case

        if not lca_case or not lca_case.processes:
            print("❌ Excel parsing failed or no valid processes found")
            result["error"] = "Excel parsing failed"
            return result

        print(f"\n{'='*80}")
        print("🏗️ Step 3: Building complete LCA model")
        print("=" * 80)

        project_context = _build_project_context_from_metadata(lca_case)

        builder = ModelBuilder(client, llm_clients, project_context, config=config)

        build_results = builder.build_complete_model(lca_case)

        if not build_results or "flows" not in build_results:
            print("❌ Model build failed")
            result["error"] = "Model build failed"
            return result

        flow_refs = build_results.get("flows", {})
        process_refs = build_results.get("processes", {})
        system_results = build_results.get("product_systems", {})

        result["flow_refs"] = flow_refs
        result["process_refs"] = process_refs

        if not flow_refs or not process_refs or not system_results:
            print("❌ Model build failed")
            result["error"] = "Model build failed"
            return result

        provider_cv_results = (
            builder.modeler.provider_cv_results
            if hasattr(builder.modeler, "provider_cv_results")
            else {}
        )
        provider_results = {
            "providers": {},
            "cv_values": provider_cv_results,
            "summary": {
                "total_selections": len(provider_cv_results),
                "llm_selections": sum(
                    1
                    for v in provider_cv_results.values()
                    if (v.get("cv", 0) if isinstance(v, dict) else float(v or 0)) > 0
                ),
            },
        }
        result["provider_results"] = provider_results
        result["ablation_settings"] = {
            "variant": config.get("ABLATION_VARIANT", "custom"),
            "provider_selection_mode": config.get(
                "PROVIDER_SELECTION_MODE", PROVIDER_SELECTION_MODE
            ),
            "candidate_constraint_mode": config.get(
                "CANDIDATE_CONSTRAINT_MODE", CANDIDATE_CONSTRAINT_MODE
            ),
            "enable_lifecycle_stage_classification": config.get(
                "ENABLE_LIFECYCLE_STAGE_CLASSIFICATION",
                ENABLE_LIFECYCLE_STAGE_CLASSIFICATION,
            ),
        }

        if not system_results:
            result["error"] = "Failed to obtain ProductSystem"
            return result

        system_name = list(system_results.keys())[0]
        system_uuid = system_results[system_name]
        if hasattr(system_uuid, "id"):
            system_uuid = system_uuid.id
        result["system_uuid"] = system_uuid

        process_info_list = []
        try:
            system = client.get(o.ProductSystem, system_uuid)
            if system and system.processes:
                for proc_ref in system.processes:
                    if proc_ref:
                        proc_id = proc_ref.id if hasattr(proc_ref, "id") else "N/A"
                        proc_name = (
                            proc_ref.name
                            if hasattr(proc_ref, "name") and proc_ref.name
                            else "N/A"
                        )

                        if proc_name == "N/A" and proc_id != "N/A":
                            try:
                                proc = client.get(o.Process, proc_id)
                                if proc:
                                    proc_name = proc.name
                            except:
                                pass
                        process_info_list.append((proc_name, proc_id))
        except Exception as e:
            print(f"  ⚠️ Failed to get product system process info: {e}")

        print(f"\n✅ Model build completed:")
        print(f"  - Flows: {len(flow_refs)}")
        print(f"  - Processes: {len(process_refs)}")
        print(f"  - Product Systems: {len(system_results)}")
        if process_info_list:
            print(f"  - Processes in product system ({len(process_info_list)} total):")
            for i, (proc_name, proc_id) in enumerate(process_info_list, 1):
                print(f"    {i}. {proc_name} (UUID: {proc_id})")

        print(f"\n📦 Product system: {system_name}")

        print(f"\n{'='*80}")
        print("🔗 Step 6: Expanding upstream supply chain")
        print("=" * 80)

        from .config import DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG

        if DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG:
            print("⚠️ Upstream supply-chain expansion disabled (DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG=True)")
            print("   Diagnostic mode for troubleshooting MC analysis issues")
            upstream_count = 0
        else:
            upstream_count = 0
            try:
                system = client.get(o.ProductSystem, system_uuid)

                excel_process_ids = set()
                for proc_ref in process_refs.values():
                    if proc_ref and hasattr(proc_ref, "id"):
                        excel_process_ids.add(proc_ref.id)

                print(f"  - Processes created from Excel: {len(excel_process_ids)}")

                existing_process_ids = set()
                if hasattr(system, "processes") and system.processes:
                    for proc_ref in system.processes:
                        if proc_ref and hasattr(proc_ref, "id"):
                            existing_process_ids.add(proc_ref.id)

                print(f"  - Current system process count: {len(existing_process_ids)}")

                upstream_provider_processes = []
                for proc_id in existing_process_ids:
                    if proc_id not in excel_process_ids:
                        upstream_provider_processes.append(proc_id)

                upstream_count = len(upstream_provider_processes)

                if upstream_provider_processes:
                    print(f"  - Found {upstream_count} upstream provider processes to trace")

                    merger = UpstreamMerger(client)
                    merge_result = merger.merge_upstream_chains(
                        system_uuid, upstream_provider_processes
                    )
                    if merge_result:
                        print(f"✅ Upstream supply-chain expansion succeeded ({upstream_count} providers)")
                    else:
                        print(f"⚠️ Upstream supply-chain expansion failed; continuing")
                else:
                    print("ℹ️ No upstream providers to trace; skipping upstream expansion")
            except Exception as e:
                print(f"⚠️ Upstream expansion error: {e}")
                print("   Continuing with subsequent steps...")

        model_build_elapsed = time.time() - model_build_start
        minutes, seconds = divmod(model_build_elapsed, 60)
        print(f"\n⏱️ Model build time (steps 1–6): {int(minutes)} min {seconds:.1f} s")
        print(f"\n📊 LCA calculation...")
        lca_calc_start = time.time()
        try:
            calculator = ResultCalculator(client, llm_clients, config, project_context)
            lca_results = calculator.calculate_comprehensive_results(
                system_name=system_name,
                provider_cv_results=provider_results.get("cv_values", {}),
                system_uuid=system_uuid,
            )
            result["lca_results"] = lca_results
        except Exception as e:
            print(f"⚠️ LCA calculation error: {e}")
            result["lca_results"] = None
        lca_calc_elapsed = time.time() - lca_calc_start

        print(f"\n{'='*80}")
        print("🎉 Automated LCA workflow completed!")
        print("=" * 80)

        total_elapsed = model_build_elapsed + lca_calc_elapsed

        print(f"\n📊 Workflow statistics:")
        print(f"  - Flows created: {len(flow_refs)}")
        print(f"  - Processes created: {len(process_refs)}")
        print(f"  - Product Systems: {len(system_results)}")
        print(f"  - System name: {system_name}")
        print(f"  - System UUID: {system_uuid}")
        print(f"  - Upstream expansion: {upstream_count} providers")

        m1, s1 = divmod(model_build_elapsed, 60)
        m2, s2 = divmod(lca_calc_elapsed, 60)
        m3, s3 = divmod(total_elapsed, 60)
        print(f"\n⏱️ Timing statistics:")
        print(f"  - Model build (steps 1–6): {int(m1)} min {s1:.1f} s")
        print(f"  - LCA calculation (step 7): {int(m2)} min {s2:.1f} s")
        print(f"  - Total:                 {int(m3)} min {s3:.1f} s")

        result["success"] = True
        result["timing_breakdown"] = {
            "model_build_seconds": model_build_elapsed,
            "lca_calc_seconds": lca_calc_elapsed,
            "total_seconds": total_elapsed,
        }
        return result

    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ Workflow execution failed")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

        result["error"] = str(e)
        result["success"] = False
        return result


def run_simple_workflow(
    excel_path: str,
    database_path: str = "ecoinvent_0121",
    skip_upstream: bool = False,
    skip_uncertainty: bool = False,
) -> dict:

    config = {
        "USE_LLM_FOR_PROVIDER_SELECTION": False if skip_upstream else True,
        "UNCERTAINTY_ANALYSIS_ENABLED": not skip_uncertainty,
    }

    return run_automated_lca_workflow(excel_path, database_path, config)


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(description="Automated LCA workflow (supports ablation variants)")
    parser.add_argument(
        "excel_file", nargs="?", default="HS_case_EN_0120.xlsx", help="Path to Excel file"
    )
    parser.add_argument(
        "--ablation-variant",
        default="config",
        choices=["config"] + list(ABLATION_VARIANT_CONFIGS.keys()),
        help="Ablation experiment variant (config=use settings from config.py)",
    )
    args = parser.parse_args()

    print(f"Running automated LCA workflow...")
    print(f"Excel file: {args.excel_file}")
    selected_variant = (
        None if args.ablation_variant == "config" else args.ablation_variant
    )
    print(f"Ablation variant: {args.ablation_variant}")

    results = run_automated_lca_workflow(
        args.excel_file, ablation_variant=selected_variant
    )

    if results["success"]:
        print(f"\n✅ Workflow completed successfully!")
        print(f"System UUID: {results['system_uuid']}")
    else:
        print(f"\n❌ Workflow failed")
        print(f"Error: {results.get('error', 'Unknown error')}")
