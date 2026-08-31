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
            "ℹ️ Public snapshot: provider quality-scoring is not included; "
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
        print(f"🌍 从Excel提取系统边界: {system_boundary_desc[:150]}...")
        if context.system_boundary.geographic_scope:
            print(f"🌍 识别到地理范围: {context.system_boundary.geographic_scope}")

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
        print(f"🌍 系统边界描述中未识别到具体地区信息，默认使用中国地区(CN)")


def run_automated_lca_workflow(
    excel_path: str,
    database_path: str = "ecoinvent_0121",
    config: dict = None,
    ablation_variant: Optional[str] = None,
    ipc_port: int = 8080,
) -> dict:

    config = build_ablation_config(config or {}, ablation_variant=ablation_variant)

    print("=" * 80)
    print("🌍 自动化LCA建模系统")
    print("=" * 80)
    print(f"📄 Excel文件: {excel_path}")
    print(f"🗄️ 数据库: {database_path}")
    print(
        "🧪 消融配置: "
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
        print("🔌 步骤1：连接OpenLCA")
        print("=" * 80)

        try:
            client = ipc.Client(ipc_port)
            print(f"✅ 成功连接到OpenLCA (端口 {ipc_port})")
        except Exception as e:
            print(f"❌ 无法连接到OpenLCA: {e}")
            print("请确保：")
            print("  - OpenLCA正在运行")
            print("  - IPC服务器已在开发者工具中启用")
            print(f"  - IPC服务器端口为{ipc_port}")
            result["error"] = f"OpenLCA连接失败: {e}"
            return result

        print("\n🤖 初始化LLM客户端...")
        llm_clients = initialize_llm_clients()
        working_llms = [
            name for name, client in llm_clients.items() if client is not None
        ]

        if working_llms:
            print(f"✅ 可用的LLM: {', '.join(working_llms)}")
        else:
            print("⚠️ 没有可用的LLM，将使用基础模式")

        print(f"\n{'='*80}")
        print("📊 步骤2：解析Excel数据")
        print("=" * 80)

        parser = DataParser(excel_path, database_path)
        lca_case = parser.parse()
        result["lca_case"] = lca_case

        if not lca_case or not lca_case.processes:
            print("❌ Excel解析失败或没有发现有效的过程")
            result["error"] = "Excel解析失败"
            return result

        print(f"\n{'='*80}")
        print("🏗️ 步骤3：构建完整LCA模型")
        print("=" * 80)

        project_context = _build_project_context_from_metadata(lca_case)

        builder = ModelBuilder(client, llm_clients, project_context, config=config)

        build_results = builder.build_complete_model(lca_case)

        if not build_results or "flows" not in build_results:
            print("❌ 模型构建失败")
            result["error"] = "模型构建失败"
            return result

        flow_refs = build_results.get("flows", {})
        process_refs = build_results.get("processes", {})
        system_results = build_results.get("product_systems", {})

        result["flow_refs"] = flow_refs
        result["process_refs"] = process_refs

        if not flow_refs or not process_refs or not system_results:
            print("❌ 模型构建失败")
            result["error"] = "模型构建失败"
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
            result["error"] = "ProductSystem获取失败"
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
            print(f"  ⚠️ 获取产品系统过程信息失败: {e}")

        print(f"\n✅ 模型构建完成:")
        print(f"  - Flows: {len(flow_refs)}")
        print(f"  - Processes: {len(process_refs)}")
        print(f"  - Product Systems: {len(system_results)}")
        if process_info_list:
            print(f"  - 产品系统中的过程 (共 {len(process_info_list)} 个):")
            for i, (proc_name, proc_id) in enumerate(process_info_list, 1):
                print(f"    {i}. {proc_name} (UUID: {proc_id})")

        print(f"\n📦 产品系统: {system_name}")

        print(f"\n{'='*80}")
        print("🔗 步骤6：扩展上游供应链")
        print("=" * 80)

        from .config import DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG

        if DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG:
            print("⚠️ 上游供应链扩展已禁用 (DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG=True)")
            print("   这是诊断模式，用于排查 MC 分析问题")
            upstream_count = 0
        else:
            upstream_count = 0
            try:
                system = client.get(o.ProductSystem, system_uuid)

                excel_process_ids = set()
                for proc_ref in process_refs.values():
                    if proc_ref and hasattr(proc_ref, "id"):
                        excel_process_ids.add(proc_ref.id)

                print(f"  - Excel创建的过程数: {len(excel_process_ids)}")

                existing_process_ids = set()
                if hasattr(system, "processes") and system.processes:
                    for proc_ref in system.processes:
                        if proc_ref and hasattr(proc_ref, "id"):
                            existing_process_ids.add(proc_ref.id)

                print(f"  - 当前系统过程数: {len(existing_process_ids)}")

                upstream_provider_processes = []
                for proc_id in existing_process_ids:
                    if proc_id not in excel_process_ids:
                        upstream_provider_processes.append(proc_id)

                upstream_count = len(upstream_provider_processes)

                if upstream_provider_processes:
                    print(f"  - 发现 {upstream_count} 个上游提供者过程需要追溯")

                    merger = UpstreamMerger(client)
                    merge_result = merger.merge_upstream_chains(
                        system_uuid, upstream_provider_processes
                    )
                    if merge_result:
                        print(f"✅ 上游供应链扩展成功 ({upstream_count} 个providers)")
                    else:
                        print(f"⚠️ 上游供应链扩展失败，但继续进行")
                else:
                    print("ℹ️ 没有发现上游Providers需要追溯，跳过上游扩展")
            except Exception as e:
                print(f"⚠️ 上游扩展出错: {e}")
                print("   继续进行后续步骤...")

        model_build_elapsed = time.time() - model_build_start
        minutes, seconds = divmod(model_build_elapsed, 60)
        print(f"\n⏱️ 模型构建耗时（步骤1~6）: {int(minutes)}分{seconds:.1f}秒")
        print(f"\n📊 LCA计算...")
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
            print(f"⚠️ LCA计算出错: {e}")
            result["lca_results"] = None
        lca_calc_elapsed = time.time() - lca_calc_start

        print(f"\n{'='*80}")
        print("🎉 自动化LCA工作流完成！")
        print("=" * 80)

        total_elapsed = model_build_elapsed + lca_calc_elapsed

        print(f"\n📊 工作流统计:")
        print(f"  - Flows创建: {len(flow_refs)}")
        print(f"  - Processes创建: {len(process_refs)}")
        print(f"  - Product Systems: {len(system_results)}")
        print(f"  - 系统名称: {system_name}")
        print(f"  - 系统UUID: {system_uuid}")
        print(f"  - 上游扩展: {upstream_count} 个providers")

        m1, s1 = divmod(model_build_elapsed, 60)
        m2, s2 = divmod(lca_calc_elapsed, 60)
        m3, s3 = divmod(total_elapsed, 60)
        print(f"\n⏱️ 耗时统计:")
        print(f"  - 模型构建（步骤1~6）: {int(m1)}分{s1:.1f}秒")
        print(f"  - LCA计算（步骤7）:    {int(m2)}分{s2:.1f}秒")
        print(f"  - 总计:                {int(m3)}分{s3:.1f}秒")

        result["success"] = True
        result["timing_breakdown"] = {
            "model_build_seconds": model_build_elapsed,
            "lca_calc_seconds": lca_calc_elapsed,
            "total_seconds": total_elapsed,
        }
        return result

    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ 工作流执行失败")
        print("=" * 80)
        print(f"错误: {e}")
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

    parser = argparse.ArgumentParser(description="自动化LCA工作流（支持消融实验变体）")
    parser.add_argument(
        "excel_file", nargs="?", default="HS_case_EN_0120.xlsx", help="Excel文件路径"
    )
    parser.add_argument(
        "--ablation-variant",
        default="config",
        choices=["config"] + list(ABLATION_VARIANT_CONFIGS.keys()),
        help="消融实验变体（config=使用config.py设定）",
    )
    args = parser.parse_args()

    print(f"运行自动化LCA工作流...")
    print(f"Excel文件: {args.excel_file}")
    selected_variant = (
        None if args.ablation_variant == "config" else args.ablation_variant
    )
    print(f"消融变体: {args.ablation_variant}")

    results = run_automated_lca_workflow(
        args.excel_file, ablation_variant=selected_variant
    )

    if results["success"]:
        print(f"\n✅ 工作流成功完成！")
        print(f"系统UUID: {results['system_uuid']}")
    else:
        print(f"\n❌ 工作流失败")
        print(f"错误: {results.get('error', 'Unknown error')}")
