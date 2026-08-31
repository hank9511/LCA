import json
import queue
import threading
import time
import traceback
import uuid
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.ioff()

try:
    import olca_ipc as ipc

    OLCA_IPC_AVAILABLE = True
except ImportError:
    ipc = None
    OLCA_IPC_AVAILABLE = False


class AsyncLCAService:
    def __init__(
        self,
        app,
        lca_service_instance,
        max_concurrent_tasks: int = 5,
        ipc_ports=None,
    ):
        """Initializes the service with queue scheduling and worker pool."""
        self.app = app
        self.lca_service = lca_service_instance
        self.max_concurrent_tasks = max(1, int(max_concurrent_tasks))
        self.ipc_ports = self._normalize_ipc_ports(ipc_ports)

        self.running_tasks = {}
        self.task_lock = threading.Lock()

        self.task_queue = queue.Queue()
        self.ipc_port_queue = queue.Queue()
        for port in self.ipc_ports:
            self.ipc_port_queue.put(port)
        self.active_task_ids = set()
        self.task_port_map = {}
        self.workers = []
        self.worker_lock = threading.Lock()
        self.port_health = {}
        self.port_health_lock = threading.Lock()
        self.last_port_check_at = None

        self.analysis_steps = {
            1: {"name": "Step 1: 连接openLCA服务器", "progress": 10},
            2: {"name": "Step 2: 解析Excel文件", "progress": 20},
            3: {"name": "Step 3: 创建LCA流程", "progress": 35},
            4: {"name": "Step 4: 建立流程关系", "progress": 50},
            5: {"name": "Step 5: 创建产品系统", "progress": 70},
            6: {"name": "Step 6: 运行影响评估", "progress": 85},
            7: {"name": "Step 7: 保存分析结果", "progress": 100},
        }

        self._start_worker_pool()
        self.run_ipc_self_check(force=True, startup=True)

    def _normalize_ipc_ports(self, ipc_ports):

        if ipc_ports is None:
            return [8080]
        normalized = []
        for item in ipc_ports:
            try:
                port = int(item)
                if port not in normalized:
                    normalized.append(port)
            except (TypeError, ValueError):
                continue
        return normalized or [8080]

    def _start_worker_pool(self):

        with self.worker_lock:
            if self.workers:
                return
            for worker_idx in range(self.max_concurrent_tasks):
                thread = threading.Thread(
                    target=self._worker_loop,
                    name=f"lca-worker-{worker_idx + 1}",
                    daemon=True,
                )
                thread.start()
                self.workers.append(thread)
        print(f"✅ AsyncLCAService worker pool started: {len(self.workers)} workers")

    def _worker_loop(self):

        while True:
            task_id = self.task_queue.get()
            if task_id is None:
                self.task_queue.task_done()
                break
            ipc_port = self.ipc_port_queue.get()
            try:
                self._mark_task_running(task_id, ipc_port)
                task_info = self.running_tasks.get(task_id, {})
                self._run_lca_analysis_thread(
                    task_id,
                    task_info.get("file_path"),
                    task_info.get("project_id"),
                    task_info.get("preferred_lcia_method"),
                    ipc_port,
                )
            finally:
                self._mark_task_finished(task_id)
                self.ipc_port_queue.put(ipc_port)
                self.task_queue.task_done()

    def _refresh_queue_positions(self):

        with self.task_queue.mutex:
            queued_task_ids = list(self.task_queue.queue)

        with self.task_lock:
            for idx, queued_task_id in enumerate(queued_task_ids, start=1):
                if queued_task_id in self.running_tasks:
                    self.running_tasks[queued_task_id]["queue_position"] = idx
                    if self.running_tasks[queued_task_id].get("status") == "queued":
                        self.running_tasks[queued_task_id][
                            "step_name"
                        ] = f"Waiting in queue (position {idx})"

    def _mark_task_running(self, task_id: str, ipc_port: int):

        with self.task_lock:
            if task_id not in self.running_tasks:
                return
            self.active_task_ids.add(task_id)
            self.task_port_map[task_id] = ipc_port
            self.running_tasks[task_id]["status"] = "running"
            self.running_tasks[task_id]["progress"] = 0
            self.running_tasks[task_id]["current_step"] = 0
            self.running_tasks[task_id]["step_name"] = f"Starting on IPC {ipc_port}..."
            self.running_tasks[task_id]["queue_position"] = 0
            self.running_tasks[task_id]["start_time"] = datetime.now()
            self.running_tasks[task_id]["ipc_port"] = ipc_port
        self._refresh_queue_positions()

    def _mark_task_finished(self, task_id: str):

        with self.task_lock:
            self.active_task_ids.discard(task_id)
            self.task_port_map.pop(task_id, None)
        self._refresh_queue_positions()

    def _probe_ipc_port(self, port: int) -> dict:

        start_time = time.time()
        if not OLCA_IPC_AVAILABLE:
            return {
                "port": port,
                "reachable": False,
                "error": "olca_ipc not installed",
                "latency_ms": 0,
                "checked_at": datetime.now().isoformat(),
            }

        try:
            ipc.Client(port)
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "port": port,
                "reachable": True,
                "error": None,
                "latency_ms": latency_ms,
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "port": port,
                "reachable": False,
                "error": str(exc),
                "latency_ms": latency_ms,
                "checked_at": datetime.now().isoformat(),
            }

    def run_ipc_self_check(self, force: bool = False, startup: bool = False) -> dict:

        with self.port_health_lock:
            if self.port_health and not force:
                return {
                    "checked_at": self.last_port_check_at,
                    "ports": [
                        self.port_health[p] for p in sorted(self.port_health.keys())
                    ],
                }

        probe_results = {}
        for port in self.ipc_ports:
            probe_results[port] = self._probe_ipc_port(port)

        checked_at = datetime.now().isoformat()
        with self.port_health_lock:
            self.port_health = probe_results
            self.last_port_check_at = checked_at

        healthy_count = sum(
            1 for item in probe_results.values() if item.get("reachable")
        )
        check_label = "startup self-check" if startup else "manual self-check"
        print(
            f"🔎 IPC {check_label}: {healthy_count}/{len(self.ipc_ports)} ports reachable; "
            f"checked_at={checked_at}"
        )
        for port in sorted(probe_results.keys()):
            item = probe_results[port]
            if item.get("reachable"):
                print(f"  ✅ IPC {port} reachable ({item.get('latency_ms', 0)} ms)")
            else:
                print(f"  ❌ IPC {port} unreachable: {item.get('error')}")

        return {
            "checked_at": checked_at,
            "ports": [probe_results[p] for p in sorted(probe_results.keys())],
        }

    def get_port_health(self, force_check: bool = False) -> dict:

        if force_check:
            return self.run_ipc_self_check(force=True)

        need_refresh = False
        with self.port_health_lock:
            if not self.port_health:
                need_refresh = True
            else:
                checked_at = self.last_port_check_at
                ports = [self.port_health[p] for p in sorted(self.port_health.keys())]

        if need_refresh:

            return self.run_ipc_self_check(force=True)

        return {
            "checked_at": checked_at,
            "ports": ports,
        }

    def start_lca_analysis(
        self,
        file_id: int,
        excel_file_path: str,
        project_id: str = None,
        preferred_lcia_method: str = None,
    ) -> str:
        """Enqueue one LCA analysis task."""
        task_id = f"lca_{file_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        now = datetime.now()

        task_info = {
            "task_id": task_id,
            "file_id": file_id,
            "file_path": excel_file_path,
            "project_id": project_id,
            "preferred_lcia_method": preferred_lcia_method,
            "status": "queued",
            "submitted_at": now,
            "queued_at": now,
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
            "progress": 0,
            "current_step": 0,
            "step_name": "Waiting in queue",
            "queue_position": None,
            "ipc_port": None,
        }

        with self.task_lock:
            self.running_tasks[task_id] = task_info

        self.task_queue.put(task_id)
        self._refresh_queue_positions()
        return task_id

    def _update_task_step(
        self, task_id: str, step_number: int, status: str = "running"
    ):
        """Thread-safe method to update task step and progress."""
        with self.task_lock:
            if task_id in self.running_tasks:
                step_info = self.analysis_steps.get(
                    step_number, {"name": f"Step {step_number}", "progress": 0}
                )
                self.running_tasks[task_id]["current_step"] = step_number
                self.running_tasks[task_id]["step_name"] = step_info["name"]
                self.running_tasks[task_id]["progress"] = step_info["progress"]
                self.running_tasks[task_id]["status"] = status
                print(
                    f"📊 Task {task_id}: {step_info['name']} ({step_info['progress']}%)"
                )

    def _run_lca_analysis_thread(
        self,
        task_id: str,
        excel_file_path: str,
        project_id: str = None,
        preferred_lcia_method: str = None,
        ipc_port: int = 8080,
    ):
        """Runs the LCA analysis in a background thread with detailed step tracking."""
        try:
            print(f"🚀 Starting LCA analysis task: {task_id} on IPC {ipc_port}")
            if preferred_lcia_method:
                print(f"🎯 [ASYNC] User-selected LCIA method: {preferred_lcia_method}")

            self._update_task_step(task_id, 1, "connecting")
            time.sleep(1)

            self._update_task_step(task_id, 2, "parsing")
            time.sleep(1)

            self._update_task_step(task_id, 3, "creating_flows")

            self._update_task_step(task_id, 4, "building_processes")

            self._update_task_step(task_id, 5, "creating_system")

            self._update_task_step(task_id, 6, "running_assessment")

            print(f"🔄 Task {task_id}: Executing core LCA analysis...")
            result = self.lca_service.run_lca_analysis_on_file(
                excel_file_path,
                project_id,
                preferred_lcia_method=preferred_lcia_method,
                ipc_port=ipc_port,
            )

            self._update_task_step(task_id, 7, "saving_results")

            with self.task_lock:
                self.running_tasks[task_id]["end_time"] = datetime.now()
                self.running_tasks[task_id]["result"] = result

                if result and result.get("success"):
                    self.running_tasks[task_id]["status"] = "completed"
                    print(f"✅ Task {task_id}: Analysis completed successfully!")
                else:
                    self.running_tasks[task_id]["status"] = "failed"
                    error_msg = (
                        result.get("error", "Unknown error")
                        if result
                        else "LCA service returned None"
                    )
                    self.running_tasks[task_id]["error"] = error_msg
                    print(f"❌ Task {task_id}: Analysis failed - {error_msg}")

            self._safe_save_to_database(task_id)

        except Exception as e:
            print(f"💥 Task {task_id}: Exception occurred - {str(e)}")
            print(f"💥 Full traceback: {traceback.format_exc()}")

            with self.task_lock:
                self.running_tasks[task_id]["status"] = "failed"
                self.running_tasks[task_id]["error"] = str(e)
                self.running_tasks[task_id]["end_time"] = datetime.now()
                self.running_tasks[task_id]["progress"] = 0
                self.running_tasks[task_id]["step_name"] = "Analysis failed"

            self._safe_save_to_database(task_id)

        print(f"🏁 Task {task_id}: Thread execution finished.")

    def _safe_save_to_database(self, task_id: str):
        """Safely saves the result to the database by creating an independent session,"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app import LCAResult

        session = None
        try:

            engine = create_engine(self.app.config["SQLALCHEMY_DATABASE_URI"])
            Session = sessionmaker(bind=engine)
            session = Session()

            with self.task_lock:
                if task_id not in self.running_tasks:
                    print(f"⚠️ Task {task_id}: Task not found for db save.")
                    return
                task_info = self.running_tasks[task_id].copy()

            print(f"📝 Saving task {task_id} to database using independent session...")

            task_start_time = (
                task_info.get("start_time")
                or task_info.get("submitted_at")
                or datetime.now()
            )
            lca_result = (
                session.query(LCAResult)
                .filter_by(
                    excel_file_id=task_info["file_id"], start_time=task_start_time
                )
                .first()
            )

            if not lca_result:
                print(f"✅ Task {task_id}: Creating new result record.")
                lca_result = LCAResult(
                    excel_file_id=task_info["file_id"], start_time=task_start_time
                )
                session.add(lca_result)
            else:
                print(f"⚠️ Task {task_id}: Result record already exists. Updating it.")

            lca_result.analysis_status = task_info.get("status", "unknown")
            lca_result.end_time = task_info.get("end_time")
            lca_result.duration_seconds = (
                (task_info["end_time"] - task_start_time).total_seconds()
                if task_info.get("end_time")
                else None
            )
            lca_result.openLCA_connected = True
            lca_result.error_message = task_info.get("error")

            original_result = task_info.get("result")
            print(f"🔍 异步任务 {task_id}: 原始结果类型: {type(original_result)}")
            if original_result:
                print(
                    f"🔍 异步任务 {task_id}: 原始结果键: {list(original_result.keys()) if isinstance(original_result, dict) else 'Not a dict'}"
                )

            safe_result_str = json.dumps(
                original_result, default=str, ensure_ascii=False
            )
            safe_result = json.loads(safe_result_str)

            print(f"🔍 异步任务 {task_id}: 序列化后结果类型: {type(safe_result)}")
            if safe_result and isinstance(safe_result, dict):
                print(
                    f"🔍 异步任务 {task_id}: 序列化后结果键: {list(safe_result.keys())}"
                )

            if safe_result and isinstance(safe_result, dict):
                basic_results = safe_result.get("basic_results", {})
                print(
                    f"🔍 异步任务 {task_id}: basic_results类型: {type(basic_results)}"
                )
                if basic_results:
                    print(
                        f"🔍 异步任务 {task_id}: basic_results内容: {list(basic_results.keys()) if isinstance(basic_results, dict) else basic_results}"
                    )
                    flows = basic_results.get("flows", [])
                    processes = basic_results.get("processes", [])
                    systems = basic_results.get("product_systems", [])

                    lca_result.flows_count = len(flows)
                    lca_result.processes_count = len(processes)
                    lca_result.product_systems_count = len(systems)
                    print(
                        f"✅ 异步任务 {task_id}: 提取统计信息 flows={lca_result.flows_count}, processes={lca_result.processes_count}, systems={lca_result.product_systems_count}"
                    )
                else:

                    lca_result.flows_count = 0
                    lca_result.processes_count = 0
                    lca_result.product_systems_count = 0
                    print(
                        f"⚠️ 异步任务 {task_id}: basic_results为空或不存在，设置统计信息为0"
                    )
            else:

                lca_result.flows_count = 0
                lca_result.processes_count = 0
                lca_result.product_systems_count = 0
                print(f"⚠️ 异步任务 {task_id}: 结果数据格式异常，设置统计信息为0")

            if safe_result and isinstance(safe_result, dict):

                analysis_details_to_save = {
                    "final_step": task_info.get("step_name", "Unknown"),
                    "steps_completed": task_info.get("current_step", 0),
                    "success": safe_result.get("success", False),
                    "message": safe_result.get("message", ""),
                }

                if "basic_results" in safe_result:
                    analysis_details_to_save["basic_results"] = safe_result[
                        "basic_results"
                    ]
                    print(f"✅ 异步任务 {task_id}: 保存basic_results")

                if "comprehensive_results" in safe_result:
                    analysis_details_to_save["comprehensive_results"] = safe_result[
                        "comprehensive_results"
                    ]
                    print(f"✅ 异步任务 {task_id}: 保存comprehensive_results")
                else:
                    print(f"⚠️ 异步任务 {task_id}: 结果中没有comprehensive_results")

                if "details" in safe_result:
                    analysis_details_to_save["details"] = safe_result["details"]

                if "timing_breakdown" in safe_result:
                    analysis_details_to_save["timing_breakdown"] = safe_result[
                        "timing_breakdown"
                    ]
                    print(f"✅ 异步任务 {task_id}: 保存timing_breakdown")

                lca_result.analysis_details = json.dumps(
                    analysis_details_to_save, ensure_ascii=False, default=str
                )
                print(
                    f"🔍 异步任务 {task_id}: 保存的数据键: {list(analysis_details_to_save.keys())}"
                )
            else:

                lca_result.analysis_details = json.dumps(
                    {
                        "final_step": task_info.get("step_name", "Unknown"),
                        "steps_completed": task_info.get("current_step", 0),
                        "error": "No valid result data",
                    },
                    ensure_ascii=False,
                    default=str,
                )
                print(f"⚠️ 异步任务 {task_id}: 结果数据无效，只保存基本信息")

            session.commit()
            print(
                f"💾 Task {task_id}: Successfully saved to database (ID: {lca_result.id})"
            )

        except Exception as e:
            print(
                f"❌ CRITICAL: Independent database save failed for task {task_id}: {str(e)}"
            )
            print(f"❌ Full traceback: {traceback.format_exc()}")
            if session:
                session.rollback()
        finally:
            if session:
                session.close()

    def get_task_status(self, task_id: str) -> dict:

        with self.task_lock:
            if task_id not in self.running_tasks:
                return {"success": False, "error": "Task not found"}
            task_info = self.running_tasks[task_id].copy()

        start_time = task_info.get("start_time")
        submitted_at = task_info.get("submitted_at")
        if start_time and task_info.get("end_time"):
            duration = (task_info["end_time"] - start_time).total_seconds()
        elif start_time:
            duration = (datetime.now() - start_time).total_seconds()
        elif submitted_at:
            duration = (datetime.now() - submitted_at).total_seconds()
        else:
            duration = 0

        try:

            safe_task_info_str = json.dumps(task_info, default=str, ensure_ascii=False)
            safe_task_info = json.loads(safe_task_info_str)
        except (TypeError, ValueError) as e:

            return {
                "success": False,
                "error": f"Failed to serialize task status: {e}",
                "task_id": task_id,
                "status": "serialization_error",
            }

        return {
            "success": True,
            "task_id": task_id,
            "status": safe_task_info.get("status", "unknown"),
            "progress": safe_task_info.get("progress", 0),
            "current_step": safe_task_info.get("current_step", 0),
            "step_name": safe_task_info.get("step_name", "Initializing..."),
            "total_steps": len(self.analysis_steps),
            "duration": duration,
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": safe_task_info.get("end_time"),
            "result": safe_task_info.get("result"),
            "error": safe_task_info.get("error"),
            "queue_position": safe_task_info.get("queue_position"),
            "ipc_port": safe_task_info.get("ipc_port"),
            "max_concurrent_tasks": self.max_concurrent_tasks,
        }

    def get_queue_stats(self, force_check: bool = False) -> dict:

        with self.task_lock:
            tasks = list(self.running_tasks.values())
            running_count = len(self.active_task_ids)
            queued_count = sum(1 for t in tasks if t.get("status") == "queued")
            completed_count = sum(1 for t in tasks if t.get("status") == "completed")
            failed_count = sum(1 for t in tasks if t.get("status") == "failed")
            busy_ports = sorted(list(self.task_port_map.values()))

        port_health = self.get_port_health(force_check=force_check)
        health_by_port = {
            item.get("port"): item
            for item in port_health.get("ports", [])
            if isinstance(item, dict)
        }
        port_status = []
        for port in self.ipc_ports:
            item = health_by_port.get(
                port,
                {
                    "port": port,
                    "reachable": False,
                    "error": "Not checked",
                    "latency_ms": 0,
                    "checked_at": None,
                },
            )
            item = dict(item)
            item["busy"] = port in busy_ports
            port_status.append(item)

        healthy_ports = sum(1 for item in port_status if item.get("reachable"))

        return {
            "success": True,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "ipc_ports": self.ipc_ports,
            "total_ipc_ports": len(self.ipc_ports),
            "busy_ports": busy_ports,
            "available_ports": self.ipc_port_queue.qsize(),
            "healthy_ports": healthy_ports,
            "unhealthy_ports": len(self.ipc_ports) - healthy_ports,
            "port_check_time": port_health.get("checked_at"),
            "port_status": port_status,
            "running_count": running_count,
            "queued_count": queued_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "total_tasks_tracked": len(tasks),
            "queue_size": self.task_queue.qsize(),
        }

    def cleanup_old_tasks(self, max_age_hours: int = 24):

        current_time = datetime.now()
        to_remove = []

        for task_id, task_info in self.running_tasks.items():
            reference_time = task_info.get("start_time") or task_info.get(
                "submitted_at"
            )
            if not reference_time:
                continue
            task_age = (current_time - reference_time).total_seconds() / 3600
            if task_age > max_age_hours:
                to_remove.append(task_id)

        for task_id in to_remove:
            del self.running_tasks[task_id]

    def update_max_concurrency(self, new_max_concurrent_tasks: int):

        target = max(1, int(new_max_concurrent_tasks))
        if target <= self.max_concurrent_tasks:
            return

        with self.worker_lock:
            current = self.max_concurrent_tasks
            self.max_concurrent_tasks = target
            for worker_idx in range(current, target):
                thread = threading.Thread(
                    target=self._worker_loop,
                    name=f"lca-worker-{worker_idx + 1}",
                    daemon=True,
                )
                thread.start()
                self.workers.append(thread)
        print(f"✅ Increased worker pool size to {self.max_concurrent_tasks}")
