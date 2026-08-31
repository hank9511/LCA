"""LCA Analysis Service"""

import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any
import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.ioff()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
lca_automation_path = os.path.join(parent_dir, "lca_automation")

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"[INFO] Looking for lca_automation at: {lca_automation_path}")
print(f"[INFO] Parent directory: {parent_dir}")
print(f"[INFO] lca_automation exists: {os.path.exists(lca_automation_path)}")

try:

    import olca_ipc as ipc

    print("[OK] olca_ipc imported successfully")

    from lca_automation.main import run_lca_analysis, create_lca_case_from_excel
    from lca_automation.lca_modeler import UniversalLCAModeler
    import olca_schema as o

    LCA_PACKAGE_AVAILABLE = True
    print("[OK] LCA automation package loaded successfully (replacing lca_package)")

except ImportError as e:
    print(f"[WARN] LCA package not available: {e}")

    try:
        import olca_ipc as ipc

        print("[OK] olca_ipc available for basic connection testing")
        LCA_PACKAGE_AVAILABLE = True

        def run_lca_analysis(excel_file_path):
            return False

        def create_lca_case_from_excel(excel_file_path):
            return None

    except ImportError:
        print("[ERROR] olca_ipc not available")
        LCA_PACKAGE_AVAILABLE = False

        class MockIPC:
            class Client:
                def __init__(self, port):
                    raise ConnectionRefusedError("olca_ipc not available")

        ipc = MockIPC


class LCAAnalysisService:
    """Service for performing LCA analysis on Excel files"""

    def __init__(self):
        self.client = None
        self.is_connected = False
        self.default_ipc_port = self._resolve_default_ipc_port()

    def _resolve_default_ipc_port(self) -> int:
        """Resolve default IPC port from env vars."""
        for env_key in (
            "LCA_IPC_PORT",
            "OPENLCA_IPC_PORT",
            "LCA_IPC_PORTS",
            "OPENLCA_IPC_PORTS",
        ):
            raw_value = os.environ.get(env_key)
            if not raw_value:
                continue
            normalized = raw_value.replace("，", ",").replace(";", ",")
            first = normalized.split(",")[0].strip()
            if not first:
                continue
            try:
                return int(first)
            except ValueError:
                continue
        return 8080

    def check_olca_connection(self, ipc_port: Optional[int] = None) -> Dict[str, Any]:
        """Check if openLCA is available and connected"""
        try:
            if ipc_port is None:
                ipc_port = self.default_ipc_port
            if not LCA_PACKAGE_AVAILABLE:
                return {
                    "success": False,
                    "error": "LCA package not available",
                    "details": "lca_automation module could not be imported",
                }

            self.client = ipc.Client(ipc_port)
            self.is_connected = True

            return {
                "success": True,
                "message": "openLCA connection successful",
                "port": ipc_port,
            }

        except ConnectionRefusedError:
            self.is_connected = False
            return {
                "success": False,
                "error": "openLCA connection failed",
                "details": f"Please ensure openLCA is running with IPC server enabled on port {ipc_port}",
            }
        except Exception as e:
            self.is_connected = False
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "details": "An unexpected error occurred while connecting to openLCA",
            }

    def run_lca_analysis_on_file(
        self,
        excel_file_path: str,
        project_id: Optional[str] = None,
        preferred_lcia_method: Optional[str] = None,
        ipc_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run LCA analysis on the specified Excel file"""
        if not LCA_PACKAGE_AVAILABLE:
            return {
                "success": False,
                "error": "LCA package not available",
                "details": "lca_package module could not be imported",
            }

        if not os.path.exists(excel_file_path):
            return {
                "success": False,
                "error": "File not found",
                "details": f"Excel file does not exist: {excel_file_path}",
            }

        try:
            if ipc_port is None:
                ipc_port = self.default_ipc_port
            print(f"🚀 Starting LCA analysis for: {excel_file_path}")

            project_context = None
            if project_id:
                try:
                    from lca_automation.project_context import ProjectContext

                    project_context = self._get_project_context(project_id)
                    if project_context:
                        print(f"[OK] Loaded project context for project: {project_id}")
                    else:
                        print(
                            f"[WARN]  No project context found for project: {project_id}, using defaults"
                        )
                except Exception as e:
                    print(
                        f"[WARN]  Could not load project context: {e}, using defaults"
                    )

            if preferred_lcia_method:
                if project_context:
                    project_context.lcia_method_keyword = preferred_lcia_method
                    print(
                        f"[USER CHOICE] Using user-selected LCIA method: {preferred_lcia_method}"
                    )
                else:

                    from lca_automation.project_context import ProjectContext

                    project_context = ProjectContext.default()
                    project_context.lcia_method_keyword = preferred_lcia_method
                    print(
                        f"[USER CHOICE] Created project context with user-selected method: {preferred_lcia_method}"
                    )

            lifecycle_stage_mapping = {}
            try:

                from app import ExcelFile, ProcessLifecycleStage, db

                excel_file = ExcelFile.query.filter_by(
                    file_path=excel_file_path
                ).first()

                if excel_file:

                    stage_mappings = ProcessLifecycleStage.query.filter_by(
                        excel_file_id=excel_file.id
                    ).all()
                    lifecycle_stage_mapping = {
                        mapping.process_name: mapping.lifecycle_stage
                        for mapping in stage_mappings
                    }
                    print(
                        f"[OK] Loaded {len(lifecycle_stage_mapping)} lifecycle stage mappings"
                    )
                else:
                    print("[WARN]  Could not find Excel file record in database")
            except Exception as e:
                print(f"[WARN]  Could not load lifecycle stage mappings: {e}")

            connection_status = self.check_olca_connection(ipc_port=ipc_port)
            if not connection_status["success"]:
                return {
                    "success": False,
                    "error": "openLCA connection failed",
                    "details": connection_status["details"],
                    "connection_info": connection_status,
                }

            analysis_start_time = datetime.now()

            try:

                if LCA_PACKAGE_AVAILABLE:
                    print("🔬 Running real LCA analysis...")
                    analysis_result = run_lca_analysis(
                        excel_file_path,
                        project_context,
                        lifecycle_stage_mapping,
                        ipc_port=ipc_port,
                    )

                    if isinstance(analysis_result, dict):
                        analysis_success = analysis_result.get("success", False)
                        comprehensive_results = analysis_result.get(
                            "comprehensive_results"
                        )
                    else:

                        analysis_success = bool(analysis_result)
                        comprehensive_results = None
                else:

                    print(
                        "📝 Running simulated LCA analysis (lca_automation not fully available)"
                    )
                    import time

                    time.sleep(2)
                    analysis_success = True
                    comprehensive_results = None
            except Exception as analysis_error:
                return {
                    "success": False,
                    "error": f"LCA analysis execution failed: {str(analysis_error)}",
                    "details": f"Error during analysis execution: {analysis_error}",
                }

            analysis_end_time = datetime.now()
            analysis_duration = (
                analysis_end_time - analysis_start_time
            ).total_seconds()

            if analysis_success:
                result = {
                    "success": True,
                    "message": "LCA analysis completed successfully",
                    "details": {
                        "file_path": excel_file_path,
                        "start_time": analysis_start_time.isoformat(),
                        "end_time": analysis_end_time.isoformat(),
                        "duration_seconds": analysis_duration,
                        "openLCA_connected": True,
                        "ipc_port": ipc_port,
                    },
                }

                if (
                    isinstance(analysis_result, dict)
                    and "basic_results" in analysis_result
                ):
                    result["basic_results"] = analysis_result["basic_results"]
                    basic_results = analysis_result["basic_results"]
                    print(
                        f"[OK] Basic results included: flows={len(basic_results.get('flows', []))}, processes={len(basic_results.get('processes', []))}, systems={len(basic_results.get('product_systems', []))}"
                    )
                else:
                    print(f"[WARN] No basic results available in analysis_result")

                if comprehensive_results:
                    result["comprehensive_results"] = comprehensive_results
                    print(f"[OK] Comprehensive results included in response")
                else:
                    print(f"[WARN] No comprehensive results available")

                if (
                    isinstance(analysis_result, dict)
                    and "timing_breakdown" in analysis_result
                ):
                    result["timing_breakdown"] = analysis_result["timing_breakdown"]
                    print(f"[OK] Timing breakdown included in response")

                return result
            else:
                return {
                    "success": False,
                    "error": "LCA analysis failed",
                    "details": "Analysis completed but returned failure status",
                }

        except Exception as e:
            error_traceback = traceback.format_exc()
            return {
                "success": False,
                "error": f"Analysis error: {str(e)}",
                "details": error_traceback,
            }

    def create_lca_case_preview(self, excel_file_path: str) -> Dict[str, Any]:
        """Create an LCA case preview from Excel file without full analysis"""
        if not LCA_PACKAGE_AVAILABLE:
            return {"success": False, "error": "LCA package not available"}

        if not os.path.exists(excel_file_path):
            return {
                "success": False,
                "error": "File not found",
                "details": f"Excel file does not exist: {excel_file_path}",
            }

        try:
            print(f"📋 Creating LCA case preview for: {excel_file_path}")

            lca_case = create_lca_case_from_excel(excel_file_path)

            return {
                "success": True,
                "lca_case_info": {
                    "case_name": lca_case.case_name,
                    "description": lca_case.description,
                    "category": lca_case.category,
                    "flows_count": len(lca_case.flows),
                    "processes_count": len(lca_case.processes),
                    "product_systems_count": len(lca_case.product_systems),
                    "flows": [
                        {
                            "name": flow.name,
                            "flow_type": flow.flow_type,
                            "category": flow.category,
                        }
                        for flow in lca_case.flows[:10]
                    ],
                    "processes": [
                        {"name": process.name, "category": process.category}
                        for process in lca_case.processes
                    ],
                },
            }

        except Exception as e:
            error_traceback = traceback.format_exc()
            return {
                "success": False,
                "error": f"LCA case creation failed: {str(e)}",
                "details": error_traceback,
            }

    def _get_project_context(self, project_id: str):
        """Get project context from database"""
        try:

            from lca_automation.project_context import ProjectContext

            from app import ProjectReportInfo, db

            report_info = ProjectReportInfo.query.filter_by(
                project_id=project_id
            ).first()

            if not report_info:
                return None

            report_info_dict = {
                "product_name": report_info.product_name,
                "producer_name": report_info.producer_name,
                "standard_used": report_info.standard_used,
                "functional_unit": report_info.functional_unit,
                "system_boundary_description": report_info.system_boundary_description,
                "system_boundary_stages": report_info.system_boundary_stages,
                "time_scale": report_info.time_scale,
                "cutoff_criteria": report_info.cutoff_criteria,
                "primary_data_source": report_info.primary_data_source,
                "secondary_data_source": report_info.secondary_data_source,
                "allocation_basis": report_info.allocation_basis,
                "allocation_procedure": report_info.allocation_procedure,
                "quantitative_purpose": report_info.quantitative_purpose,
                "product_function": report_info.product_function,
            }

            return ProjectContext.from_report_info(project_id, report_info_dict)

        except Exception as e:
            print(f"[ERROR] Error getting project context: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status for LCA analysis capability"""
        status = {
            "lca_package_available": LCA_PACKAGE_AVAILABLE,
            "openLCA_connection": None,
            "system_ready": False,
        }

        if LCA_PACKAGE_AVAILABLE:
            connection_status = self.check_olca_connection()
            status["openLCA_connection"] = connection_status
            status["system_ready"] = connection_status["success"]

        return status

    def get_available_lcia_methods(
        self, ipc_port: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get list of available LCIA methods from openLCA"""
        if not LCA_PACKAGE_AVAILABLE:
            return {
                "success": False,
                "error": "LCA package not available",
                "methods": [],
            }

        try:
            if ipc_port is None:
                ipc_port = self.default_ipc_port

            connection_status = self.check_olca_connection(ipc_port=ipc_port)
            if not connection_status["success"]:
                return {
                    "success": False,
                    "error": "openLCA connection failed",
                    "methods": [],
                }

            print("[INFO] Fetching available LCIA methods from openLCA...")

            import olca_schema as o

            methods = self.client.get_all(o.ImpactMethod)

            method_list = []
            for method in methods:
                method_info = {
                    "id": method.id,
                    "name": method.name,
                    "description": method.description or "",
                    "category": method.category if hasattr(method, "category") else "",
                }
                method_list.append(method_info)

            method_list.sort(key=lambda x: x["name"])

            print(f"[OK] Found {len(method_list)} LCIA methods")

            return {"success": True, "methods": method_list, "count": len(method_list)}

        except Exception as e:
            print(f"[ERROR] Failed to fetch LCIA methods: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e), "methods": []}


lca_service = LCAAnalysisService()
