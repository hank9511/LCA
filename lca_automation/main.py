import sys
import os
from typing import Optional, Dict, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


from .excel_parser import ExcelLCAParser
from .llm_utils import initialize_llm_clients
from .project_context import ProjectContext
from .data_structures import LCACase
from .main_workflow import run_automated_lca_workflow
from .lca_modeler import UniversalLCAModeler
import olca_ipc as ipc
import olca_schema as o


def run_lca_analysis(
    excel_file_path: str,
    project_context: Optional[ProjectContext] = None,
    lifecycle_stage_mapping: Optional[Dict[str, str]] = None,
    ablation_variant: Optional[str] = None,
    ipc_port: int = 8080,
) -> Dict[str, Any]:

    try:

        if project_context is None:
            project_context = ProjectContext.default()
            print("⚠️  Using default project context (no project info provided)")
        else:
            project_context.print_summary()

        print("=" * 80)
        print(f"🌍 LCA analysis - {os.path.basename(excel_file_path)}")
        print("=" * 80)

        print("🔌 Step 1: Connecting to openLCA...")
        try:
            client = ipc.Client(ipc_port)
            print("✅ openLCA connection successful")
        except ConnectionRefusedError:
            print("❌ openLCA connection failed")
            print("Please ensure:")
            print("  - openLCA is running")
            print("  - The IPC server is enabled in developer tools")
            print(f"  - The IPC server port is {ipc_port}")
            return {
                "success": False,
                "error": "openLCA connection failed",
                "comprehensive_results": None,
                "system_name": None,
            }

        print("\n🤖 Step 2: Initializing LLM clients...")
        llm_clients = initialize_llm_clients()
        working_llms = [
            name for name, client in llm_clients.items() if client is not None
        ]

        if working_llms:
            print(f"✅ Available LLMs: {working_llms}")
        else:
            print("⚠️  No available LLMs; falling back to basic mode")

        print(f"\n📋 Step 3: Creating LCA case from Excel file...")
        lca_case = create_lca_case_from_excel(excel_file_path, project_context)

        if lifecycle_stage_mapping:
            print(f"\n🔗 Step 3.5: Applying life-cycle stage mapping...")
            for process in lca_case.processes:
                if process.name in lifecycle_stage_mapping:

                    process.lifecycle_stage = lifecycle_stage_mapping[process.name]
                    print(
                        f"  ✓ {process.name} -> {lifecycle_stage_mapping[process.name]}"
                    )
            print(
                f"✅ Applied {len([p for p in lca_case.processes if hasattr(p, 'lifecycle_stage')])} life-cycle stage mappings"
            )

        print("\n🏗️ Step 4: Running automated LCA workflow...")

        config = {
            "USE_LLM_FOR_PROVIDER_SELECTION": len(working_llms) > 0,
            "UNCERTAINTY_ANALYSIS_ENABLED": True,
        }
        if ablation_variant:
            config["ABLATION_VARIANT"] = ablation_variant

        if project_context and project_context.lcia_method_keyword:
            config["PREFERRED_LCIA_METHOD"] = project_context.lcia_method_keyword

        from .config import DATABASE_PATH

        workflow_result = run_automated_lca_workflow(
            excel_path=excel_file_path,
            database_path=DATABASE_PATH,
            config=config,
            ablation_variant=ablation_variant,
            ipc_port=ipc_port,
        )

        if not workflow_result.get("success"):
            return {
                "success": False,
                "error": workflow_result.get("error", "Workflow execution failed"),
                "comprehensive_results": None,
                "system_name": None,
            }

        print("\n📊 Step 5: Retrieving comprehensive LCA results...")

        system_uuid = workflow_result.get("system_uuid")
        lca_results = workflow_result.get("lca_results")

        system_name = None
        if system_uuid:
            try:
                system = client.get(o.ProductSystem, system_uuid)
                if system:
                    system_name = system.name
            except:
                pass

        comprehensive_results = None
        if lca_results:
            comprehensive_results = {
                "system_info": {"name": system_name or "Unknown", "uuid": system_uuid},
                "impact_analysis": lca_results.get("impact_analysis"),
                "contribution_analysis": lca_results.get("contribution_analysis"),
                "uncertainty_analysis": lca_results.get("uncertainty_analysis"),
            }

        basic_results = {
            "flows": workflow_result.get("flow_refs", {}),
            "processes": workflow_result.get("process_refs", {}),
            "product_systems": (
                {system_name: system_uuid} if system_name and system_uuid else {}
            ),
        }

        print("\n" + "=" * 80)
        print("🎉 LCA analysis completed!")
        print("=" * 80)
        print(f"📊 Analysis statistics:")
        print(f"  - Flows processed: {len(basic_results['flows'])}")
        print(f"  - Processes created: {len(basic_results['processes'])}")
        print(f"  - Systems built: {len(basic_results['product_systems'])}")

        return {
            "success": True,
            "basic_results": basic_results,
            "comprehensive_results": comprehensive_results,
            "system_name": system_name,
            "timing_breakdown": workflow_result.get("timing_breakdown"),
        }

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "comprehensive_results": None,
            "system_name": None,
        }


def create_lca_case_from_excel(
    excel_file_path: str, project_context: Optional[ProjectContext] = None
) -> LCACase:

    import os

    if not os.path.exists(excel_file_path):
        raise FileNotFoundError(f"Excel file not found: {excel_file_path}")

    if project_context is None:
        project_context = ProjectContext.default()

    filename = os.path.splitext(os.path.basename(excel_file_path))[0]

    if project_context.product_name:
        case_name = f"{project_context.product_name} LCA case"
        case_description = f"LCA case for {project_context.product_name}"
        if project_context.producer_name:
            case_description += f", produced by {project_context.producer_name}"
    else:
        case_name = f"{filename.upper()} LCA case"
        case_description = f"LCA case auto-generated from Excel file {filename}.xlsx"

    print(f"📊 Creating LCA case from Excel file: {filename}.xlsx")

    excel_parser = ExcelLCAParser(excel_file_path, project_context)
    lca_case = excel_parser.parse_excel_to_lca_case(
        case_name=case_name, case_description=case_description, category="Excel import"
    )

    lca_case.flow_metadata = {
        flow_name: {
            "provider_flow_meta": info.get("provider_flow_meta", {}),
            "explicit_provider": info.get("explicit_provider", ""),
        }
        for flow_name, info in excel_parser.flows_data.items()
    }
    lca_case.process_provider_metadata = excel_parser.process_provider_metadata

    print(f"✅ Successfully created LCA case: {case_name}")
    print(f"📝 Contains: {len(lca_case.flows)} flows, {len(lca_case.processes)} processes")

    return lca_case


def main():

    import argparse
    import os

    DEFAULT_EXCEL_FILE = "brick.xlsx"

    current_dir = os.getcwd()
    default_path = os.path.join(current_dir, DEFAULT_EXCEL_FILE)

    parser = argparse.ArgumentParser(description="Run automated LCA analysis")
    parser.add_argument("excel_file", nargs="?", default="", help="Path to Excel file")
    parser.add_argument(
        "--ablation-variant",
        default="config",
        choices=[
            "config",
            "full",
            "semantic_only",
            "unconstrained_candidate",
            "no_stage_classification",
        ],
        help="Ablation experiment variant (config=use settings from config.py)",
    )
    args = parser.parse_args()

    if args.excel_file:
        excel_file = args.excel_file

        if not os.path.isabs(excel_file):
            excel_file = os.path.join(current_dir, excel_file)

        if not os.path.exists(excel_file):
            print(f"❌ File not found: {excel_file}")
            print("💡 Please ensure the Excel file exists at the specified path")
            return False

        print(f"🎯 Specified Excel file: {os.path.basename(excel_file)}")
    else:

        excel_file = default_path

        if not os.path.exists(excel_file):
            print(f"❌ Default file not found: {DEFAULT_EXCEL_FILE}")
            print("💡 Place the Excel file in the project directory, or specify a file path")
            return False

        print(f"🎯 Using default Excel file: {DEFAULT_EXCEL_FILE}")

    selected_variant = (
        None if args.ablation_variant == "config" else args.ablation_variant
    )
    result = run_lca_analysis(excel_file, ablation_variant=selected_variant)

    if result.get("success"):
        print(f"\n🎉 LCA analysis for {os.path.basename(excel_file)} completed successfully!")
    else:
        print(f"\n❌ LCA analysis for {os.path.basename(excel_file)} failed")
        print(f"Error: {result.get('error', 'Unknown error')}")

    return result.get("success", False)


if __name__ == "__main__":

    success = main()
