import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import re


@dataclass
class ProcessInfo:

    id: str
    name: str
    category: str
    location: str = ""


@dataclass
class ExchangeInfo:

    flow_id: str
    flow_name: str
    amount: float
    unit: str
    is_input: bool
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None


class JSONQueryEngine:

    def __init__(self, json_export_dir: str):

        self.export_dir = Path(json_export_dir)

        if not self.export_dir.exists():
            raise FileNotFoundError(f"导出目录不存在: {json_export_dir}")

        print(f"📂 加载 JSON-LD 数据...")

        self.processes = {}
        self.flows = {}
        self.process_name_index = {}
        self.flow_name_index = {}

        self._load_data()

        print(f"✅ JSON 查询引擎已初始化")
        self._print_stats()

    def _load_data(self):

        processes_dir = self.export_dir / "processes"
        if processes_dir.exists():
            for json_file in processes_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        proc_id = data.get("@id") or data.get("id")
                        if proc_id:
                            self.processes[proc_id] = data

                            name = data.get("name", "").lower()
                            if name:
                                if name not in self.process_name_index:
                                    self.process_name_index[name] = []
                                self.process_name_index[name].append(proc_id)
                except Exception as e:
                    print(f"⚠️  加载失败: {json_file.name} - {e}")

        flows_dir = self.export_dir / "flows"
        if flows_dir.exists():
            for json_file in flows_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        flow_id = data.get("@id") or data.get("id")
                        if flow_id:
                            self.flows[flow_id] = data

                            name = data.get("name", "").lower()
                            if name:
                                if name not in self.flow_name_index:
                                    self.flow_name_index[name] = []
                                self.flow_name_index[name].append(flow_id)
                except Exception as e:
                    print(f"⚠️  加载失败: {json_file.name} - {e}")

    def _print_stats(self):

        print(f"📊 数据统计:")
        print(f"   - 过程数: {len(self.processes):,}")
        print(f"   - 流数: {len(self.flows):,}")

    def search_processes(
        self, keyword: str, limit: int = 100, exclude_market: bool = True
    ) -> List[ProcessInfo]:

        keyword_lower = keyword.lower()
        results = []

        for proc_id, proc_data in self.processes.items():
            name = proc_data.get("name", "")

            if keyword_lower in name.lower():

                if exclude_market and "market" in name.lower():
                    continue

                location = ""
                if "location" in proc_data and proc_data["location"]:
                    location = proc_data["location"].get("name", "")

                category = ""
                if "category" in proc_data and proc_data["category"]:
                    category = proc_data["category"].get("name", "")

                results.append(
                    ProcessInfo(
                        id=proc_id, name=name, category=category, location=location
                    )
                )

                if len(results) >= limit:
                    break

        return results

    def get_process_exchanges(self, process_id: str) -> List[ExchangeInfo]:

        if process_id not in self.processes:
            return []

        proc_data = self.processes[process_id]
        exchanges = []

        for exchange in proc_data.get("exchanges", []):
            flow_ref = exchange.get("flow")
            if not flow_ref:
                continue

            flow_id = flow_ref.get("@id") or flow_ref.get("id")
            flow_name = flow_ref.get("name", "Unknown")

            amount = exchange.get("amount", 0)
            unit_ref = exchange.get("unit", {})
            unit_name = unit_ref.get("name", "kg")

            is_input = exchange.get("input", False)

            provider_id = None
            provider_name = None
            default_provider = exchange.get("defaultProvider")
            if default_provider:
                provider_id = default_provider.get("@id") or default_provider.get("id")
                provider_name = default_provider.get("name")

            exchanges.append(
                ExchangeInfo(
                    flow_id=flow_id,
                    flow_name=flow_name,
                    amount=amount,
                    unit=unit_name,
                    is_input=is_input,
                    provider_id=provider_id,
                    provider_name=provider_name,
                )
            )

        return exchanges

    def find_best_provider(
        self,
        flow_name: str,
        preferred_keywords: List[str] = None,
        exclude_keywords: List[str] = None,
    ) -> Optional[ProcessInfo]:

        if exclude_keywords is None:
            exclude_keywords = ["market", "import", "treatment", "waste"]

        candidates = []
        flow_name_lower = flow_name.lower()

        for proc_id, proc_data in self.processes.items():
            proc_name = proc_data.get("name", "")
            proc_name_lower = proc_name.lower()

            if any(kw in proc_name_lower for kw in exclude_keywords):
                continue

            for exchange in proc_data.get("exchanges", []):
                if exchange.get("input", False):
                    continue

                flow_ref = exchange.get("flow", {})
                ex_flow_name = flow_ref.get("name", "").lower()

                if flow_name_lower in ex_flow_name or ex_flow_name in flow_name_lower:
                    amount = exchange.get("amount", 0)
                    if amount > 0:
                        candidates.append(
                            {
                                "id": proc_id,
                                "name": proc_name,
                                "amount": amount,
                                "data": proc_data,
                            }
                        )
                    break

        if not candidates:
            return None

        best_score = -1
        best_provider = None

        for candidate in candidates[:50]:
            score = 0
            name_lower = candidate["name"].lower()

            if preferred_keywords:
                for keyword in preferred_keywords:
                    if keyword.lower() in name_lower:
                        score += 10

            if "production" in name_lower:
                score += 5

            score -= len(candidate["name"]) * 0.01

            score += candidate["amount"] * 0.1

            if score > best_score:
                best_score = score

                location = ""
                if "location" in candidate["data"] and candidate["data"]["location"]:
                    location = candidate["data"]["location"].get("name", "")

                category = ""
                if "category" in candidate["data"] and candidate["data"]["category"]:
                    category = candidate["data"]["category"].get("name", "")

                best_provider = ProcessInfo(
                    id=candidate["id"],
                    name=candidate["name"],
                    category=category,
                    location=location,
                )

        return best_provider

    def build_minimal_system(
        self,
        root_process_name: str,
        key_inputs: List[str],
        max_upstream_per_input: int = 0,
        excel_processes: List = None,
    ) -> Dict:

        print(f"\n🔨 构建最小化产品系统: {root_process_name}")

        root = None

        if excel_processes:

            for proc in excel_processes:
                if proc.name == root_process_name:
                    root = ProcessInfo(
                        id=(
                            proc.id
                            if hasattr(proc, "id") and proc.id
                            else f"excel_{proc.name}"
                        ),
                        name=proc.name,
                        category="Excel defined",
                        location="",
                    )
                    print(f"✅ 根过程（来自 Excel）: {root.name}")
                    break

        if not root:

            root_candidates = self.search_processes(root_process_name, limit=10)
            if not root_candidates:
                raise ValueError(f"未找到根过程: {root_process_name}")

            root = root_candidates[0]
            print(f"✅ 根过程（来自数据库）: {root.name}")

        system = {
            "root_id": root.id,
            "root_name": root.name,
            "processes": {root.id: root},
            "links": [],
            "total_processes": 1,
        }

        exchanges = self.get_process_exchanges(root.id)
        input_exchanges = [e for e in exchanges if e.is_input]

        print(f"📊 根过程有 {len(input_exchanges)} 个输入")

        for key_input in key_inputs:
            matching_exchanges = [
                e for e in input_exchanges if key_input.lower() in e.flow_name.lower()
            ]

            if not matching_exchanges:
                print(f"⚠️  未找到关键输入: {key_input}")
                continue

            for exchange in matching_exchanges[:1]:
                provider = self.find_best_provider(
                    exchange.flow_name,
                    preferred_keywords=["production"],
                    exclude_keywords=["market", "import"],
                )

                if provider:
                    if provider.id not in system["processes"]:
                        system["processes"][provider.id] = provider
                        system["total_processes"] += 1

                    system["links"].append(
                        {
                            "from_process": root.id,
                            "to_provider": provider.id,
                            "flow": exchange.flow_name,
                            "amount": exchange.amount,
                        }
                    )

                    print(f"  ✅ {exchange.flow_name[:50]:<50} → {provider.name[:50]}")
                else:
                    print(f"  ⚠️  {exchange.flow_name[:50]:<50} → 未找到 provider")

        print(f"\n✅ 系统构建完成:")
        print(f"   - 总过程数: {system['total_processes']}")
        print(f"   - 链接数: {len(system['links'])}")

        return system


if __name__ == "__main__":

    engine = JSONQueryEngine("ecoinvent_elcd_tiangong")

    procs = engine.search_processes("steel production", limit=10)
    print(f"\n找到 {len(procs)} 个钢铁生产过程:")
    for i, proc in enumerate(procs[:5], 1):
        print(f"  {i}. {proc.name}")

    provider = engine.find_best_provider(
        "electricity, medium voltage", preferred_keywords=["photovoltaic", "production"]
    )
    if provider:
        print(f"\n最佳电力 provider: {provider.name}")

    system = engine.build_minimal_system(
        root_process_name="steel production, converter",
        key_inputs=["electricity", "iron ore", "oxygen"],
        max_upstream_per_input=0,
    )
