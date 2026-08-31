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
            print("⚠️  使用默认项目上下文（未提供项目信息）")
        else:
            project_context.print_summary()

        print("=" * 80)
        print(f"🌍 LCA分析 - {os.path.basename(excel_file_path)}")
        print("=" * 80)

        print("🔌 步骤1：连接到openLCA...")
        try:
            client = ipc.Client(ipc_port)
            print("✅ openLCA连接成功")
        except ConnectionRefusedError:
            print("❌ openLCA连接失败")
            print("请确保：")
            print("  - openLCA正在运行")
            print("  - 在开发者工具中启用了IPC服务器")
            print(f"  - IPC服务器端口为{ipc_port}")
            return {
                "success": False,
                "error": "openLCA connection failed",
                "comprehensive_results": None,
                "system_name": None,
            }

        print("\n🤖 步骤2：初始化LLM客户端...")
        llm_clients = initialize_llm_clients()
        working_llms = [
            name for name, client in llm_clients.items() if client is not None
        ]

        if working_llms:
            print(f"✅ 可用的LLM: {working_llms}")
        else:
            print("⚠️  没有可用的LLM，将使用基础模式")

        print(f"\n📋 步骤3：从Excel文件创建LCA案例...")
        lca_case = create_lca_case_from_excel(excel_file_path, project_context)

        if lifecycle_stage_mapping:
            print(f"\n🔗 步骤3.5：应用生命周期阶段映射...")
            for process in lca_case.processes:
                if process.name in lifecycle_stage_mapping:

                    process.lifecycle_stage = lifecycle_stage_mapping[process.name]
                    print(
                        f"  ✓ {process.name} -> {lifecycle_stage_mapping[process.name]}"
                    )
            print(
                f"✅ 已应用 {len([p for p in lca_case.processes if hasattr(p, 'lifecycle_stage')])} 个生命周期阶段映射"
            )

        print("\n🏗️ 步骤4：运行自动化LCA工作流...")

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
                "error": workflow_result.get("error", "工作流执行失败"),
                "comprehensive_results": None,
                "system_name": None,
            }

        print("\n📊 步骤5：获取综合LCA结果...")

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
        print("🎉 LCA分析完成！")
        print("=" * 80)
        print(f"📊 分析统计:")
        print(f"  - 处理的流: {len(basic_results['flows'])}")
        print(f"  - 创建的过程: {len(basic_results['processes'])}")
        print(f"  - 构建的系统: {len(basic_results['product_systems'])}")

        return {
            "success": True,
            "basic_results": basic_results,
            "comprehensive_results": comprehensive_results,
            "system_name": system_name,
            "timing_breakdown": workflow_result.get("timing_breakdown"),
        }

    except Exception as e:
        print(f"\n❌ 分析过程中发生错误: {e}")
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
        raise FileNotFoundError(f"Excel文件不存在: {excel_file_path}")

    if project_context is None:
        project_context = ProjectContext.default()

    filename = os.path.splitext(os.path.basename(excel_file_path))[0]

    if project_context.product_name:
        case_name = f"{project_context.product_name} LCA案例"
        case_description = f"{project_context.product_name}的LCA案例"
        if project_context.producer_name:
            case_description += f"，由{project_context.producer_name}生产"
    else:
        case_name = f"{filename.upper()} LCA案例"
        case_description = f"从Excel文件{filename}.xlsx自动生成的LCA案例"

    print(f"📊 从Excel文件创建LCA案例: {filename}.xlsx")

    excel_parser = ExcelLCAParser(excel_file_path, project_context)
    lca_case = excel_parser.parse_excel_to_lca_case(
        case_name=case_name, case_description=case_description, category="Excel导入"
    )

    lca_case.flow_metadata = {
        flow_name: {
            "provider_flow_meta": info.get("provider_flow_meta", {}),
            "explicit_provider": info.get("explicit_provider", ""),
        }
        for flow_name, info in excel_parser.flows_data.items()
    }
    lca_case.process_provider_metadata = excel_parser.process_provider_metadata

    print(f"✅ 成功创建LCA案例: {case_name}")
    print(f"📝 包含: {len(lca_case.flows)} 个流, {len(lca_case.processes)} 个过程")

    return lca_case


def main():

    import argparse
    import os

    DEFAULT_EXCEL_FILE = "brick.xlsx"

    current_dir = os.getcwd()
    default_path = os.path.join(current_dir, DEFAULT_EXCEL_FILE)

    parser = argparse.ArgumentParser(description="运行LCA自动化分析")
    parser.add_argument("excel_file", nargs="?", default="", help="Excel文件路径")
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
        help="消融实验变体（config=使用config.py设定）",
    )
    args = parser.parse_args()

    if args.excel_file:
        excel_file = args.excel_file

        if not os.path.isabs(excel_file):
            excel_file = os.path.join(current_dir, excel_file)

        if not os.path.exists(excel_file):
            print(f"❌ 文件不存在: {excel_file}")
            print("💡 请确保Excel文件存在于指定路径")
            return False

        print(f"🎯 指定的Excel文件: {os.path.basename(excel_file)}")
    else:

        excel_file = default_path

        if not os.path.exists(excel_file):
            print(f"❌ 默认文件不存在: {DEFAULT_EXCEL_FILE}")
            print("💡 请将Excel文件放在项目目录中，或指定文件路径")
            return False

        print(f"🎯 使用默认Excel文件: {DEFAULT_EXCEL_FILE}")

    selected_variant = (
        None if args.ablation_variant == "config" else args.ablation_variant
    )
    result = run_lca_analysis(excel_file, ablation_variant=selected_variant)

    if result.get("success"):
        print(f"\n🎉 {os.path.basename(excel_file)}的LCA分析成功完成！")
    else:
        print(f"\n❌ {os.path.basename(excel_file)}的LCA分析失败")
        print(f"错误: {result.get('error', '未知错误')}")

    return result.get("success", False)


if __name__ == "__main__":

    success = main()
