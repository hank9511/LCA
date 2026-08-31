"""Excel parser for LCA data"""

import pandas as pd
import openpyxl
from typing import List, Dict, Optional
import re
from .data_structures import LCACase, Process, Flow, ProductSystem, SimpleExchange
from .project_context import ProjectContext

_EMISSION_PATTERNS = [
    r"\bcarbon dioxide\b",
    r"\bco2\b",
    r"\bmethane\b",
    r"\bch4\b",
    r"\bnitrous oxide\b",
    r"\bdinitrogen monoxide\b",
    r"\bn2o\b",
    r"\bnitrogen oxides?\b",
    r"\bnitrogen monoxide\b",
    r"\bnitrogen dioxide\b",
    r"\bnox\b",
    r"\b(?:sulfur|sulphur) dioxide\b",
    r"\b(?:sulfur|sulphur) oxides?\b",
    r"\bsox\b",
    r"\bso2\b",
    r"\bparticulate matter\b",
    r"\bparticulates?\b",
    r"\bpm\s*10\b",
    r"\bpm\s*2[.,]?5\b",
    r"\b(?:n)?mvoc\b",
    r"\bvoc\b",
    r"\bvolatile organic compound",
    r"\bcarbon monoxide\b",
    r"\bammonia\b",
    r"\bnh3\b",
    r"\bhydrogen sulfide\b",
    r"\bh2s\b",
    r"\bhydrogen fluoride\b",
    r"\bhf\b",
    r"\bhydrogen chloride\b",
    r"\bhcl\b",
    r"\bcfc[-\s]?\d",
    r"\bhcfc[-\s]?\d",
    r"\bhfc[-\s]?\d",
    r"\bsf6\b",
]
_EMISSION_REGEX = re.compile("|".join(_EMISSION_PATTERNS), re.IGNORECASE)

_CHINESE_EMISSION_NAMES = {
    "二氧化碳",
    "甲烷",
    "氧化亚氮",
    "一氧化碳",
    "氮氧化物",
    "一氧化氮",
    "二氧化氮",
    "二氧化硫",
    "三氧化硫",
    "硫氧化物",
    "颗粒物",
    "可吸入颗粒物",
    "粉尘",
    "烟尘",
    "挥发性有机物",
    "氨",
    "氨气",
    "硫化氢",
    "氟化氢",
    "氯化氢",
}

_FLOW_TYPE_TOKEN_MAP = {
    "product flow": "PRODUCT_FLOW",
    "product": "PRODUCT_FLOW",
    "product_flow": "PRODUCT_FLOW",
    "产品流": "PRODUCT_FLOW",
    "产品": "PRODUCT_FLOW",
    "waste flow": "WASTE_FLOW",
    "waste": "WASTE_FLOW",
    "waste_flow": "WASTE_FLOW",
    "废物流": "WASTE_FLOW",
    "废物": "WASTE_FLOW",
    "elementary flow": "ELEMENTARY_FLOW",
    "elementary": "ELEMENTARY_FLOW",
    "elementary_flow": "ELEMENTARY_FLOW",
    "emission": "ELEMENTARY_FLOW",
    "基本流": "ELEMENTARY_FLOW",
    "排放流": "ELEMENTARY_FLOW",
    "排放": "ELEMENTARY_FLOW",
}

_FLOW_TYPE_SNIFF_TOKENS = set(_FLOW_TYPE_TOKEN_MAP.keys())

_PROCESS_HEADER_REGEX = re.compile(
    r"(?:Processes?|过程|工序|工艺|生命周期阶段)\s*\d*\s*[:：]",
    re.IGNORECASE,
)

_HEADER_ROW_REGEX = re.compile(
    r"(?:input\s*/?\s*output|输入\s*/?\s*输出)",
    re.IGNORECASE,
)

_COLUMN_ALIAS_MAP = {
    "输入/输出": "input/output",
    "输入 / 输出": "input/output",
    "输入输出": "input/output",
    "方向": "input/output",
    "流": "flow",
    "流名称": "flow",
    "流名": "flow",
    "流的种类": "flow type",
    "流类型": "flow type",
    "流的类型": "flow type",
    "类别": "category",
    "分类": "category",
    "数量": "amount",
    "数值": "amount",
    "单位": "unit",
    "排放因子": "emission factor",
    "排放系数": "emission factor",
    "排放因子单位": "ef unit",
    "排放系数单位": "ef unit",
    "避免废物": "avoided waste",
    "避免产品": "avoided product",
    "提供者": "provider",
    "供应商": "provider",
    "地区": "location",
    "地理位置": "location",
    "区域": "location",
    "分配": "allocation",
    "分配因子": "allocation factor",
    "成本": "cost",
    "价格": "price",
    "收入": "revenue",
}

_INPUT_TOKENS = {"input", "in", "输入", "投入"}
_OUTPUT_TOKENS = {"output", "out", "输出", "产出"}


def _normalize_io_token(io_type_raw: str) -> str:

    if not io_type_raw:
        return ""
    token = io_type_raw.strip().lower()
    if token in _INPUT_TOKENS:
        return "input"
    if token in _OUTPUT_TOKENS:
        return "output"

    for safe_token in ("input", "输入", "投入"):
        if safe_token in token:
            return "input"
    for safe_token in ("output", "输出", "产出"):
        if safe_token in token:
            return "output"
    return ""


class ExcelLCAParser:
    """Parser for Excel-based LCA data"""

    def __init__(
        self, excel_file_path: str, project_context: Optional[ProjectContext] = None
    ):
        """Initialize Excel LCA Parser"""
        self.excel_file_path = excel_file_path
        self.project_context = (
            project_context if project_context is not None else ProjectContext.default()
        )
        self.processes_data = []
        self.flows_data = {}
        self.process_provider_metadata = {}
        self.functional_unit_product_name = None

        self._ef_provider_process_registry = {}

    def parse_excel_to_lca_case(
        self,
        case_name: str = "Excel-driven LCA Case",
        case_description: str = "LCA case generated from Excel data",
        category: str = "Excel Import",
    ) -> LCACase:
        """Parse Excel file and convert to LCACase"""
        print(f"📊 Parsing Excel file: {self.excel_file_path}")

        metadata = self.parse_excel_metadata()
        if metadata.get("quantification_scope", {}).get("functional_unit"):
            functional_unit = metadata["quantification_scope"]["functional_unit"]

            import re

            product_match = re.search(
                r"[\d.]+?\s*(?:kg|g|mg|t|ton|件|个|m3|m³|kwh|mj|j|wh)?\s*(.+)",
                functional_unit,
                re.IGNORECASE,
            )
            if product_match:
                product_name = product_match.group(1).strip()
                self.functional_unit_product_name = product_name
                print(f"📌 从功能单位提取产品名称用于目标产品识别: {product_name}")

        self._read_excel_data()

        flows = self._extract_flows()
        processes = self._extract_processes()

        product_systems = self._extract_product_systems(processes)

        lca_case = LCACase(
            case_name=case_name,
            description=case_description,
            category=category,
            flows=flows,
            processes=processes,
            product_systems=product_systems,
        )

        print(f"✅ Successfully parsed Excel data:")
        print(f"  - Flows: {len(flows)}")
        print(f"  - Processes: {len(processes)}")
        print(f"  - Product Systems: {len(product_systems)}")

        return lca_case

    def _read_excel_data(self):
        """Read and parse Excel sheets"""
        try:

            workbook = openpyxl.load_workbook(self.excel_file_path)
            sheet_names = workbook.sheetnames

            for sheet_name in sheet_names:
                if sheet_name.lower() in ["sheet2", "empty"]:
                    continue

                print(f"📋 Reading sheet: {sheet_name}")
                df = pd.read_excel(self.excel_file_path, sheet_name=sheet_name)

                if not df.empty:
                    self._parse_process_sheet(df, sheet_name)

        except Exception as e:
            print(f"❌ Error reading Excel data: {e}")
            raise

    def _parse_process_sheet(self, df: pd.DataFrame, sheet_name: str):
        """Parse a process sheet from the Excel file"""
        try:
            print(f"📋 Analyzing sheet structure: {sheet_name}")

            raw_df = pd.read_excel(
                self.excel_file_path, sheet_name=sheet_name, header=None
            )

            process_sections = []
            for row_idx in range(raw_df.shape[0]):
                for col_idx in range(raw_df.shape[1]):
                    cell_value = raw_df.iloc[row_idx, col_idx]
                    if pd.notna(cell_value) and _PROCESS_HEADER_REGEX.search(
                        str(cell_value)
                    ):
                        process_name = str(cell_value)

                        for sep in (":", "："):
                            if sep in process_name:
                                process_name = process_name.split(sep, 1)[1].strip()
                                break

                        process_sections.append(
                            {
                                "name": process_name,
                                "start_row": row_idx,
                                "col_idx": col_idx,
                            }
                        )

            if not process_sections:
                print(f"⚠️ No process sections found in sheet {sheet_name}")
                return

            print(f"🔍 Found {len(process_sections)} process sections")

            for i, section in enumerate(process_sections):

                if i < len(process_sections) - 1:

                    end_row = process_sections[i + 1]["start_row"]
                else:

                    end_row = raw_df.shape[0]

                section["end_row"] = end_row
                self._parse_single_process_vertical(raw_df, section, sheet_name)

        except Exception as e:
            print(f"❌ Error parsing process sheet {sheet_name}: {e}")

    def _parse_single_process_vertical(
        self, raw_df: pd.DataFrame, section: dict, sheet_name: str
    ):
        """Parse a single process from vertically arranged Excel data"""
        try:
            process_name = section["name"]
            start_row = section["start_row"]
            end_row = section["end_row"]

            print(f"🏭 Parsing process: {process_name} (rows {start_row}-{end_row})")

            process_data = raw_df.iloc[start_row:end_row, :]

            header_row_idx = None
            for idx in range(len(process_data)):
                row = process_data.iloc[idx]
                if pd.notna(row.iloc[0]) and _HEADER_ROW_REGEX.search(str(row.iloc[0])):
                    header_row_idx = idx
                    break

            if header_row_idx is None:
                print(f"⚠️ Could not find header row for process {process_name}")
                return

            header_row = process_data.iloc[header_row_idx]
            col_mapping = {}
            for i, col_name in enumerate(header_row):
                if pd.notna(col_name):
                    col_mapping[str(col_name).strip()] = i

            print(f"📋 Column mapping for {process_name}: {list(col_mapping.keys())}")

            lower_mapping: Dict[str, int] = {}
            for raw_key, col_idx in col_mapping.items():
                key_stripped = raw_key.strip()
                key_lower = key_stripped.lower()
                lower_mapping[key_lower] = col_idx

                canonical = _COLUMN_ALIAS_MAP.get(
                    key_stripped
                ) or _COLUMN_ALIAS_MAP.get(key_lower)
                if canonical and canonical not in lower_mapping:
                    lower_mapping[canonical] = col_idx
            print(f"🔍 DEBUG: Normalized column names: {list(lower_mapping.keys())}")

            if "flow type" not in lower_mapping:
                inferred_idx = self._sniff_flow_type_column(
                    process_data, header_row_idx, lower_mapping
                )
                if inferred_idx is not None:
                    lower_mapping["flow type"] = inferred_idx
                    col_mapping.setdefault("Flow type", inferred_idx)
                    print(
                        f"📋 表头缺失 'Flow type'，按位置兜底将列 {inferred_idx} "
                        f"识别为 Flow type（数据行内容包含显式声明）"
                    )

            exchanges = []
            for idx in range(header_row_idx + 1, len(process_data)):
                row = process_data.iloc[idx]

                if pd.isna(row.iloc[0]) or str(row.iloc[0]).strip() == "":
                    continue

                try:

                    io_col_idx = lower_mapping.get("input/output", 0)
                    io_type_raw = str(row.iloc[io_col_idx]).strip()

                    io_type = _normalize_io_token(io_type_raw)
                    print(
                        f"🔍 DEBUG: Row {idx} - io_type_raw: '{io_type_raw}' -> io_type: '{io_type}'"
                    )

                    flow_cell_value = row.iloc[lower_mapping.get("flow", 1)]
                    if pd.isna(flow_cell_value):
                        flow_name = ""
                    else:

                        flow_name = str(flow_cell_value).strip()

                        flow_name = flow_name.rstrip("\t\n\r")

                        if flow_name.endswith(","):
                            flow_name = flow_name.rstrip(",")

                        flow_name = flow_name.strip()

                    if "flow type" in lower_mapping:
                        flow_type_cell = row.iloc[lower_mapping.get("flow type", 2)]
                        flow_type_raw = (
                            ""
                            if pd.isna(flow_type_cell)
                            else str(flow_type_cell).strip()
                        )
                    else:
                        flow_type_raw = ""

                    has_explicit_flow_type = bool(
                        flow_type_raw
                    ) and flow_type_raw.lower() not in ["nan", "none", "undefined"]
                    flow_type = self._convert_flow_type(flow_type_raw, flow_name)

                    if "category" in lower_mapping:
                        category_cell = row.iloc[lower_mapping.get("category", 3)]
                        category_raw = (
                            "" if pd.isna(category_cell) else str(category_cell).strip()
                        )
                    else:
                        category_raw = ""

                    category = category_raw
                    category_path = (
                        self._build_category_path(category) if category else []
                    )
                    amount = row.iloc[lower_mapping.get("amount", 4)]
                    unit = str(row.iloc[lower_mapping.get("unit", 5)]).strip()

                    provider_name = ""
                    if "provider" in lower_mapping:
                        provider_col_idx = lower_mapping.get("provider")
                        provider_cell_value = row.iloc[provider_col_idx]
                        print(
                            f"🔍 DEBUG: Provider column for '{flow_name}': cell value = '{provider_cell_value}', is_na = {pd.isna(provider_cell_value)}"
                        )
                        if (
                            pd.notna(provider_cell_value)
                            and str(provider_cell_value).strip() != ""
                        ):
                            provider_name = str(provider_cell_value).strip()

                            provider_name = provider_name.rstrip("\t\n\r")
                            if provider_name.endswith(","):
                                provider_name = provider_name.rstrip(",")
                            provider_name = provider_name.strip()
                            print(
                                f"🔍 DEBUG: Extracted provider name: '{provider_name}'"
                            )

                    emission_factor_value, ef_unit_raw = (
                        self._extract_emission_factor_info(
                            row=row, lower_mapping=lower_mapping
                        )
                    )
                    if (
                        io_type == "input"
                        and emission_factor_value is not None
                        and ef_unit_raw
                    ):
                        provider_from_ef = (
                            self._register_emission_factor_provider_process(
                                source_process_name=process_name,
                                base_flow_name=flow_name,
                                base_flow_unit=(
                                    unit if unit.lower() != "nan" else "kg"
                                ),
                                emission_factor=emission_factor_value,
                                ef_unit_raw=ef_unit_raw,
                                base_flow_category=(
                                    category if category.lower() != "nan" else ""
                                ),
                            )
                        )
                        if provider_from_ef:
                            if not provider_name:
                                provider_name = provider_from_ef
                                print(
                                    f"🌫️ 使用 Emission Factor 自动提供者: "
                                    f"{flow_name} -> {provider_name}"
                                )
                            else:
                                print(
                                    f"ℹ️ 流 '{flow_name}' 同时存在 Provider 与 Emission Factor；"
                                    f"保留显式 Provider='{provider_name}'，仅创建排放因子过程供复用。"
                                )

                    exchange_location = ""
                    for loc_key in ("location", "loc", "region", "地区", "地理位置"):
                        if loc_key in lower_mapping:
                            loc_col_idx = lower_mapping.get(loc_key)
                            loc_cell_value = row.iloc[loc_col_idx]
                            if pd.notna(loc_cell_value) and str(
                                loc_cell_value
                            ).strip() not in ("", "nan", "none"):
                                exchange_location = str(loc_cell_value).strip().upper()
                                print(
                                    f"📍 Exchange location for '{flow_name}': {exchange_location}"
                                )
                            break

                    is_avoided_product = False
                    avoided_col_name = None
                    if "avoided waste" in lower_mapping:
                        avoided_col_name = "avoided waste"
                        avoided_col = lower_mapping.get("avoided waste")
                    elif "avoided product" in lower_mapping:
                        avoided_col_name = "avoided product"
                        avoided_col = lower_mapping.get("avoided product")
                    elif "avoided wast" in lower_mapping:
                        avoided_col_name = "avoided wast"
                        avoided_col = lower_mapping.get("avoided wast")

                    if avoided_col_name:
                        avoided_cell_value = row.iloc[avoided_col]
                        if pd.notna(avoided_cell_value):
                            avoided_str = str(avoided_cell_value).strip().lower()
                            is_avoided_product = avoided_str in [
                                "true",
                                "yes",
                                "1",
                                "t",
                                "y",
                                "x",
                                "✓",
                                "✔",
                            ]
                            if is_avoided_product:
                                print(
                                    f"🔍 DEBUG: Found avoided product flag in column '{avoided_col_name}': '{avoided_str}' for flow '{flow_name}'"
                                )

                    allocation_value = 0.0
                    if (
                        "allocation" in lower_mapping
                        or "allocation factor" in lower_mapping
                    ):
                        alloc_col = lower_mapping.get(
                            "allocation"
                        ) or lower_mapping.get("allocation factor")
                        alloc_cell_value = row.iloc[alloc_col]
                        if pd.notna(alloc_cell_value):
                            try:
                                allocation_value = float(alloc_cell_value)
                            except (ValueError, TypeError):
                                allocation_value = 0.0

                    cost_value = 0.0
                    if (
                        "cost" in lower_mapping
                        or "price" in lower_mapping
                        or "revenue" in lower_mapping
                    ):
                        cost_col = (
                            lower_mapping.get("cost")
                            or lower_mapping.get("price")
                            or lower_mapping.get("revenue")
                        )
                        cost_cell_value = row.iloc[cost_col]
                        if pd.notna(cost_cell_value):
                            try:
                                cost_value = float(cost_cell_value)
                            except (ValueError, TypeError):
                                cost_value = 0.0

                    if (
                        pd.isna(amount)
                        or flow_name == "nan"
                        or flow_name == ""
                        or str(amount).lower() in ["amount", "nan", "数量", "数值"]
                        or str(flow_name).lower()
                        in ["flow", "nan", "流", "流名称", "流名"]
                        or len(flow_name.strip()) == 0
                    ):
                        print(
                            f"⚠️ Skipping invalid row - flow_name: '{flow_name}', amount: '{amount}'"
                        )
                        continue

                    provider_canonical_flow_type = flow_type
                    provider_canonical_category = category
                    provider_canonical_path = category_path
                    provider_canonical_unit = unit if unit.lower() != "nan" else "kg"
                    provider_meta = {
                        "flow_name": flow_name,
                        "flow_type": provider_canonical_flow_type,
                        "category": provider_canonical_category,
                        "category_path": provider_canonical_path,
                        "unit": provider_canonical_unit,
                    }

                    if flow_name not in self.flows_data:
                        self.flows_data[flow_name] = {
                            "name": flow_name,
                            "flow_type": flow_type,
                            "category": category if category.lower() != "nan" else "",
                            "category_path": category_path,
                            "unit": unit if unit.lower() != "nan" else "kg",
                            "original_sheet": sheet_name,
                            "source_process": process_name,
                            "explicit_flow_type": has_explicit_flow_type,
                        }
                        print(
                            f"📝 Registered new flow: '{flow_name}' from process '{process_name}'"
                        )
                    else:
                        existing_flow = self.flows_data[flow_name]

                        existing_type = existing_flow.get("flow_type", "PRODUCT_FLOW")
                        existing_explicit = existing_flow.get(
                            "explicit_flow_type", False
                        )

                        if flow_type and flow_type != existing_type:
                            if existing_explicit and not has_explicit_flow_type:
                                print(
                                    f"🔒 流 '{flow_name}' 在 '{existing_flow.get('source_process', '?')}' 已被 Excel 显式声明为 {existing_type}，"
                                    f"忽略 '{process_name}' 的推断值 {flow_type}"
                                )
                            elif (not existing_explicit) and has_explicit_flow_type:
                                print(
                                    f"✅ 流 '{flow_name}' 由推断值 {existing_type} 升级为 Excel 显式声明 {flow_type}"
                                )
                                existing_flow["flow_type"] = flow_type
                            elif existing_explicit and has_explicit_flow_type:
                                print(
                                    f"⚠️ 流 '{flow_name}' 在多个过程中显式声明的 Flow type 不一致："
                                    f"{existing_type} (来自 '{existing_flow.get('source_process', '?')}') vs "
                                    f"{flow_type} (来自 '{process_name}')。保留先到的 {existing_type}，请检查 Excel。"
                                )
                            else:

                                if self._flow_type_priority(
                                    flow_type
                                ) > self._flow_type_priority(existing_type):
                                    print(
                                        f"ℹ️ 推断更新流 '{flow_name}' 类型：{existing_type} → {flow_type}"
                                    )
                                    existing_flow["flow_type"] = flow_type

                        if (
                            category
                            and category.lower() != "nan"
                            and not existing_flow.get("category")
                        ):
                            existing_flow["category"] = category
                            existing_flow["category_path"] = category_path

                        if has_explicit_flow_type:
                            existing_flow["explicit_flow_type"] = True

                        print(
                            f"🔄 Flow already exists: '{flow_name}' (reusing existing definition)"
                        )

                    print(
                        f"🔍 DEBUG: Before correction - flow '{flow_name}': is_avoided_product={is_avoided_product}, io_type='{io_type}'"
                    )
                    if is_avoided_product and io_type == "output":
                        print(
                            f"⚠️ Correcting avoided product '{flow_name}' from OUTPUT to INPUT (data model requirement)"
                        )
                        print(
                            f"   Note: openLCA UI will display this as OUTPUT automatically"
                        )
                        io_type = "input"
                    print(
                        f"🔍 DEBUG: After correction - flow '{flow_name}': is_avoided_product={is_avoided_product}, io_type='{io_type}'"
                    )

                    if (io_type == "input" or is_avoided_product) and provider_name:

                        self.flows_data[flow_name]["explicit_provider"] = provider_name
                        self.flows_data[flow_name]["provider_flow_meta"] = provider_meta
                        if process_name not in self.process_provider_metadata:
                            self.process_provider_metadata[process_name] = {}
                        self.process_provider_metadata[process_name][flow_name] = {
                            "provider": provider_name,
                            "metadata": provider_meta,
                        }
                        if is_avoided_product:
                            print(
                                f"📋 Explicit provider for avoided product '{flow_name}': {provider_name}"
                            )
                        else:
                            print(
                                f"📋 Explicit provider specified for '{flow_name}': {provider_name}"
                            )

                    is_quantitative_reference = False
                    can_be_qr = self._can_be_quantitative_reference(
                        flow_name, flow_type
                    )
                    if io_type == "output" and not is_avoided_product and not can_be_qr:
                        resolved_ft = self._resolve_flow_type_for_name(
                            flow_name, flow_type
                        )
                        print(
                            f"⏭️  Skipping quantitative reference for '{flow_name}' "
                            f"(flow_type={resolved_ft}; only PRODUCT_FLOW outputs may be QR)"
                        )
                    elif io_type == "output" and not is_avoided_product and can_be_qr:

                        if self._matches_functional_unit_product(flow_name):
                            existing_qr = any(
                                ex.is_quantitative_reference for ex in exchanges
                            )
                            if not existing_qr:
                                is_quantitative_reference = True
                                print(
                                    f"🎯 Setting '{flow_name}' as quantitative reference "
                                    f"(exact match to functional unit product "
                                    f"'{self.functional_unit_product_name}')"
                                )

                        if not is_quantitative_reference:
                            product_output_count = sum(
                                1
                                for ex in exchanges
                                if self._is_product_like_output_exchange(ex)
                            )
                            if product_output_count == 0:
                                is_quantitative_reference = True
                                print(
                                    f"📌 Setting '{flow_name}' as quantitative reference (first product output)"
                                )

                    final_is_input = io_type == "input"
                    print(
                        f"🔍 DEBUG: Creating exchange for '{flow_name}': is_input={final_is_input}, is_avoided_product={is_avoided_product}, is_quantitative_reference={is_quantitative_reference}"
                    )

                    exchange = SimpleExchange(
                        flow_name=flow_name,
                        amount=float(amount),
                        unit=unit if unit != "nan" else "kg",
                        is_input=final_is_input,
                        is_quantitative_reference=is_quantitative_reference,
                        provider_name=provider_name,
                        is_avoided_product=is_avoided_product,
                        allocation_value=allocation_value,
                        cost_value=cost_value,
                        location=exchange_location,
                    )

                    if is_avoided_product:
                        print(
                            f"🔄 Flow '{flow_name}' marked as avoided product (system expansion) - is_input={exchange.is_input}"
                        )
                    if allocation_value > 0:
                        print(
                            f"📊 Allocation factor for '{flow_name}': {allocation_value}"
                        )
                    if cost_value > 0:
                        print(f"💰 Cost/revenue for '{flow_name}': {cost_value}")

                    if len(exchange.flow_name.strip()) == 0:
                        print(
                            f"❌ Warning: Empty flow name detected in exchange for process '{process_name}'"
                        )
                        continue

                    exchanges.append(exchange)

                except Exception as e:
                    print(
                        f"⚠️ Error parsing row {start_row + idx} for process {process_name}: {e}"
                    )
                    continue

            if exchanges:
                process_spec = Process(
                    name=process_name,
                    category="Excel Import",
                    description=f"Process imported from Excel sheet: {sheet_name} with {len(exchanges)} exchanges",
                )

                process_spec._simple_exchanges = exchanges

                self.processes_data.append(process_spec)
                print(
                    f"✅ Added process '{process_name}' with {len(exchanges)} exchanges"
                )

            else:
                print(f"⚠️ No valid exchanges found for process '{process_name}'")

        except Exception as e:
            print(f"❌ Error parsing single process {section['name']}: {e}")

    def _sniff_flow_type_column(
        self,
        process_data: pd.DataFrame,
        header_row_idx: int,
        lower_mapping: Dict[str, int],
    ) -> Optional[int]:

        candidate_indices = []
        flow_col = lower_mapping.get("flow")
        category_col = lower_mapping.get("category")
        if (
            flow_col is not None
            and category_col is not None
            and category_col - flow_col >= 2
        ):
            for idx in range(flow_col + 1, category_col):
                candidate_indices.append(idx)

        used_cols = set(lower_mapping.values())
        for col_idx in range(process_data.shape[1]):
            if col_idx not in used_cols and col_idx not in candidate_indices:
                candidate_indices.append(col_idx)

        scored: Dict[int, int] = {}
        sniff_end = min(header_row_idx + 1 + 8, len(process_data))
        for sniff_idx in range(header_row_idx + 1, sniff_end):
            row = process_data.iloc[sniff_idx]
            for col_idx in candidate_indices:
                if col_idx >= len(row):
                    continue
                cell = row.iloc[col_idx]
                if pd.isna(cell):
                    continue
                token = str(cell).strip().lower()
                if not token:
                    continue

                if token in _FLOW_TYPE_SNIFF_TOKENS or any(
                    t in token for t in _FLOW_TYPE_SNIFF_TOKENS
                ):
                    scored[col_idx] = scored.get(col_idx, 0) + 1

        if not scored:
            return None

        best_idx = max(
            scored.items(), key=lambda kv: (kv[1], -abs(kv[0] - (flow_col or 0) - 1))
        )[0]
        return best_idx

    def _extract_emission_factor_info(
        self, row: pd.Series, lower_mapping: Dict[str, int]
    ) -> tuple:

        ef_col = None
        ef_unit_col = None

        for key in ("emission factor", "emissionfactor"):
            if key in lower_mapping:
                ef_col = lower_mapping[key]
                break
        for key in ("ef unit", "efunit"):
            if key in lower_mapping:
                ef_unit_col = lower_mapping[key]
                break

        if ef_col is None or ef_unit_col is None:
            return None, ""

        ef_cell = row.iloc[ef_col]
        ef_unit_cell = row.iloc[ef_unit_col]
        if pd.isna(ef_cell) or pd.isna(ef_unit_cell):
            return None, ""

        ef_unit_raw = str(ef_unit_cell).strip()
        if not ef_unit_raw or ef_unit_raw.lower() in {"nan", "none"}:
            return None, ""

        try:
            factor_value = float(ef_cell)
        except (ValueError, TypeError):
            return None, ""

        return factor_value, ef_unit_raw

    def _parse_ef_unit(self, ef_unit_raw: str) -> Optional[Dict[str, str]]:

        if not ef_unit_raw:
            return None

        normalized = ef_unit_raw.strip().lower()
        replace_map = {
            " ": "",
            "／": "/",
            "⁄": "/",
            "\\": "/",
            "·": "",
            "*": "",
            "×": "",
            "-": "",
            "_": "",
            "（": "(",
            "）": ")",
            "，": ",",
            "。": ".",
            "³": "3",
            "₂": "2",
            "₃": "3",
            "₄": "4",
            "₅": "5",
            "₆": "6",
            "₇": "7",
            "₈": "8",
            "₉": "9",
            "₂e": "2e",
        }
        for old, new in replace_map.items():
            normalized = normalized.replace(old, new)

        normalized = normalized.replace("per", "/")

        while "//" in normalized:
            normalized = normalized.replace("//", "/")

        normalized = normalized.replace("eq", "e")
        normalized = normalized.replace("co2-e", "co2e")
        normalized = normalized.replace("co2e", "co2e")

        parts = normalized.split("/")
        if len(parts) != 2:
            return None
        numerator, denominator = parts[0].strip(), parts[1].strip()
        if not numerator or not denominator:
            return None

        numerator_match = re.match(
            r"^(kg|g|mg)?\(?([a-z0-9\u4e00-\u9fa5]+)\)?$", numerator
        )
        if not numerator_match:
            return None
        emission_unit = numerator_match.group(1) or "kg"
        pollutant_token = (numerator_match.group(2) or "").strip()
        if not pollutant_token:
            return None

        pollutant_aliases = {
            "co2": "Carbon dioxide, fossil",
            "co2e": "Carbon dioxide, fossil",
            "carbondioxide": "Carbon dioxide, fossil",
            "carbondioxidefossil": "Carbon dioxide, fossil",
            "二氧化碳": "Carbon dioxide, fossil",
            "二氧化碳当量": "Carbon dioxide, fossil",
            "温室气体当量": "Carbon dioxide, fossil",
            "ghg": "Carbon dioxide, fossil",
            "ghgco2e": "Carbon dioxide, fossil",
        }
        emission_flow_name = pollutant_aliases.get(pollutant_token, "")
        if not emission_flow_name:
            return None

        denominator_aliases = {
            "kg": "kg",
            "g": "g",
            "mg": "mg",
            "t": "t",
            "ton": "t",
            "tons": "t",
            "tonne": "t",
            "tonnes": "t",
            "m3": "m3",
            "m^3": "m3",
            "m³": "m3",
            "nm3": "m3",
            "nm^3": "m3",
            "nm³": "m3",
            "kwh": "kWh",
            "kwhr": "kWh",
            "kwhrs": "kWh",
            "kilowatthour": "kWh",
            "kilowatthours": "kWh",
            "l": "L",
            "liter": "L",
            "litre": "L",
            "liters": "L",
            "litres": "L",
        }
        denominator_unit = denominator_aliases.get(denominator, "")
        if not denominator_unit:
            return None

        return {
            "emission_unit": emission_unit,
            "emission_flow_name": emission_flow_name,
            "denominator_unit": denominator_unit,
            "normalized_key": f"{emission_unit}{pollutant_token}/{denominator_unit.lower()}",
        }

    def _register_emission_factor_provider_process(
        self,
        source_process_name: str,
        base_flow_name: str,
        base_flow_unit: str,
        emission_factor: float,
        ef_unit_raw: str,
        base_flow_category: str = "",
    ) -> str:

        parsed_ef = self._parse_ef_unit(ef_unit_raw)
        if not parsed_ef:
            print(f"⚠️ 无法解析 EF Unit='{ef_unit_raw}'，跳过自动排放因子过程创建")
            return ""

        denominator_unit = parsed_ef["denominator_unit"]
        emission_unit = parsed_ef["emission_unit"]
        emission_flow_name = parsed_ef["emission_flow_name"]

        ef_key = (
            base_flow_name,
            round(float(emission_factor), 12),
            parsed_ef["normalized_key"],
        )
        if ef_key in self._ef_provider_process_registry:
            return self._ef_provider_process_registry[ef_key]

        if base_flow_name not in self.flows_data:
            self.flows_data[base_flow_name] = {
                "name": base_flow_name,
                "flow_type": "PRODUCT_FLOW",
                "category": base_flow_category,
                "category_path": (
                    self._build_category_path(base_flow_category)
                    if base_flow_category
                    else []
                ),
                "unit": denominator_unit or base_flow_unit or "kg",
                "original_sheet": "emission_factor_auto",
                "source_process": source_process_name,
                "explicit_flow_type": True,
                "has_emission_factor_provider": True,
                "force_foreground_flow": True,
            }
        else:

            if not self.flows_data[base_flow_name].get("unit"):
                self.flows_data[base_flow_name]["unit"] = (
                    denominator_unit or base_flow_unit or "kg"
                )

            self.flows_data[base_flow_name]["has_emission_factor_provider"] = True
            self.flows_data[base_flow_name]["force_foreground_flow"] = True

        if emission_flow_name not in self.flows_data:
            emission_category = "Emissions to air/high population density"
            self.flows_data[emission_flow_name] = {
                "name": emission_flow_name,
                "flow_type": "ELEMENTARY_FLOW",
                "category": emission_category,
                "category_path": self._build_category_path(emission_category),
                "unit": emission_unit,
                "original_sheet": "emission_factor_auto",
                "source_process": source_process_name,
                "explicit_flow_type": True,
            }

        normalized_suffix = parsed_ef["normalized_key"].replace("/", "_per_")
        ef_process_name = f"EF_{base_flow_name}_{normalized_suffix}"
        ef_process = Process(
            name=ef_process_name,
            category="Excel Import/Emission Factor",
            description=(
                f"Auto-generated EF process for '{base_flow_name}' from '{source_process_name}'. "
                f"Factor={emission_factor} {ef_unit_raw}"
            ),
        )
        ef_process._simple_exchanges = [
            SimpleExchange(
                flow_name=base_flow_name,
                amount=1.0,
                unit=denominator_unit,
                is_input=False,
                is_quantitative_reference=True,
            ),
            SimpleExchange(
                flow_name=emission_flow_name,
                amount=float(emission_factor),
                unit=emission_unit,
                is_input=False,
                is_quantitative_reference=False,
            ),
        ]
        self.processes_data.append(ef_process)
        self._ef_provider_process_registry[ef_key] = ef_process_name
        print(
            f"✅ 创建排放因子过程: {ef_process_name} "
            f"(产品={base_flow_name} 1 {denominator_unit}, 排放={emission_factor} {emission_unit})"
        )
        return ef_process_name

    def _is_elementary_flow(self, flow_name: str) -> bool:

        if not flow_name:
            return False

        stripped = flow_name.strip()
        if not stripped:
            return False

        if stripped in _CHINESE_EMISSION_NAMES:
            return True

        return bool(_EMISSION_REGEX.search(stripped.lower()))

    def _convert_flow_type(self, flow_type_str: str, flow_name: str = "") -> str:

        if flow_type_str is not None and not (
            isinstance(flow_type_str, float) and pd.isna(flow_type_str)
        ):
            raw = str(flow_type_str).strip()
            if raw and raw.lower() not in {"nan", "none", "undefined"}:
                normalized = raw.lower()

                if normalized in _FLOW_TYPE_TOKEN_MAP:
                    return _FLOW_TYPE_TOKEN_MAP[normalized]

                for token, value in _FLOW_TYPE_TOKEN_MAP.items():
                    if token in normalized:
                        return value

                upper = raw.upper()
                if upper in {"PRODUCT_FLOW", "WASTE_FLOW", "ELEMENTARY_FLOW"}:
                    return upper

                print(
                    f"⚠️ 无法识别 Flow type 单元格内容 '{raw}' (流: '{flow_name}')，"
                    f"将转用排放白名单兜底"
                )

        if self._is_elementary_flow(flow_name):
            print(
                f"ℹ️ '{flow_name}' Excel 未填 Flow type，根据排放白名单推断为 ELEMENTARY_FLOW"
            )
            return "ELEMENTARY_FLOW"

        print(
            f"⚠️ '{flow_name}' Excel 未填 Flow type 且不在排放白名单中，默认设为 PRODUCT_FLOW。"
            f"如有误请在 Excel 'Flow type' 列显式声明。"
        )
        return "PRODUCT_FLOW"

    def _flow_type_priority(self, flow_type: str) -> int:

        priority_map = {"ELEMENTARY_FLOW": 3, "WASTE_FLOW": 2, "PRODUCT_FLOW": 1}
        return priority_map.get(flow_type, 0)

    def _resolve_flow_type_for_name(
        self, flow_name: str, flow_type_hint: str = ""
    ) -> str:
        """Resolve the canonical flow type for a flow name during Excel parsing."""
        hinted = (flow_type_hint or "").upper().strip()
        if hinted in {"PRODUCT_FLOW", "WASTE_FLOW", "ELEMENTARY_FLOW"}:
            return hinted
        cached = self.flows_data.get(flow_name) or {}
        cached_type = (cached.get("flow_type") or "PRODUCT_FLOW").upper().strip()
        return (
            cached_type
            if cached_type in {"PRODUCT_FLOW", "WASTE_FLOW", "ELEMENTARY_FLOW"}
            else "PRODUCT_FLOW"
        )

    def _matches_functional_unit_product(self, flow_name: str) -> bool:
        """True when a flow name matches the functional-unit product (exact only)."""
        if not self.functional_unit_product_name:
            return False
        flow_name_lower = flow_name.lower().strip()
        fu_product_lower = self.functional_unit_product_name.lower().strip()
        return flow_name_lower == fu_product_lower

    def _can_be_quantitative_reference(
        self, flow_name: str, flow_type_hint: str = ""
    ) -> bool:
        """Whether an output exchange may become the process quantitative reference."""
        return (
            self._resolve_flow_type_for_name(flow_name, flow_type_hint)
            == "PRODUCT_FLOW"
        )

    def _is_product_like_output_exchange(self, exchange: SimpleExchange) -> bool:
        """True when an already-parsed exchange is a product output eligible for QR."""
        if exchange.is_input or getattr(exchange, "is_avoided_product", False):
            return False
        return self._can_be_quantitative_reference(exchange.flow_name)

    def _build_category_path(self, category: str) -> List[str]:
        """Split category strings into hierarchical path list"""
        if not category or category.lower() == "nan":
            return []

        separators = ["/", "\\", ">"]
        for sep in separators:
            if sep in category:
                segments = [
                    segment.strip()
                    for segment in category.split(sep)
                    if segment.strip()
                ]
                if len(segments) > 1:
                    return segments
        return [category.strip()]

    def _extract_flows(self) -> List[Flow]:
        """Extract flow specifications from parsed data with complete names preserved"""
        flows = []

        print(
            f"📊 Extracting {len(self.flows_data)} flows with complete name preservation..."
        )

        for flow_name, flow_data in self.flows_data.items():
            if not flow_name or len(flow_name.strip()) == 0:
                print(f"❌ Skipping invalid flow with empty name")
                continue

            print(f"🔍 Extracting flow: '{flow_name}'")

            flow_unit = flow_data.get("unit", "kg")
            print(f"   单位: {flow_unit}")

            flow_spec = Flow(
                name=flow_name,
                category=flow_data.get("category", ""),
                flow_type=flow_data.get("flow_type", "PRODUCT_FLOW"),
                description=f"Flow from {flow_data.get('source_process', 'unknown process')} in sheet {flow_data.get('original_sheet', 'unknown')}",
                cas="",
                formula="",
                synonyms="",
                is_infrastructure_flow=False,
            )

            flow_spec.unit = flow_unit

            flows.append(flow_spec)

        print(f"🏁 Flow extraction completed: {len(flows)} flows ready for creation")
        return flows

    def _extract_processes(self) -> List[Process]:
        """Return the parsed process specifications"""
        return self.processes_data

    def _extract_product_systems(self, processes: List[Process]) -> List[ProductSystem]:
        """Create product systems based on processes"""
        if not processes:
            return []

        reference_process = processes[-1]

        target_amount = 1.0

        system_description = f"Product system based on {reference_process.name}"
        if self.project_context and self.project_context.functional_unit.description:
            system_description += (
                f" ({self.project_context.functional_unit.description})"
            )

        product_system = ProductSystem(
            name=f"{reference_process.name} System",
            category="Excel Import",
            description=system_description,
            target_amount=target_amount,
        )

        ref_process = reference_process
        product_system.ref_process = ref_process

        return [product_system]

    def parse_excel_metadata(self) -> Dict:

        print(f"📋 开始解析Excel元数据: {self.excel_file_path}")

        metadata = {
            "product_info": {},
            "producer_info": {},
            "quantification_method": {},
            "quantification_purpose": "",
            "quantification_scope": {},
            "inventory_analysis": {},
            "lifecycle_stages": [],
        }

        try:

            df = pd.read_excel(self.excel_file_path, sheet_name=0, header=None)

            data = df.fillna("").astype(str)

            metadata["product_info"] = self._extract_product_info(data)

            metadata["producer_info"] = self._extract_producer_info(data)

            metadata["quantification_method"] = self._extract_quantification_method(
                data
            )

            metadata["quantification_purpose"] = self._extract_quantification_purpose(
                data
            )

            metadata["quantification_scope"] = self._extract_quantification_scope(data)

            metadata["inventory_analysis"] = self._extract_inventory_analysis(data)

            metadata["lifecycle_stages"] = self._extract_lifecycle_stages(data)

            print(f"✅ Excel元数据解析完成")
            return metadata

        except Exception as e:
            print(f"⚠️ 解析Excel元数据时出错: {e}")
            return metadata

    def _find_value_after_label(
        self,
        data: pd.DataFrame,
        label: str,
        row_offset: int = 0,
        col_offset: int = 1,
        fuzzy: bool = False,
    ) -> str:

        for i in range(len(data)):
            for j in range(len(data.columns)):
                cell_value = str(data.iloc[i, j]).strip()

                match = False
                if fuzzy:

                    match = label.lower() in cell_value.lower()
                else:

                    match = label in cell_value

                if match:

                    target_row = i + row_offset
                    target_col = j + col_offset

                    if target_row < len(data) and target_col < len(data.columns):
                        value = str(data.iloc[target_row, target_col]).strip()

                        if value and value.lower() not in ["nan", "none", ""]:
                            return value
        return ""

    def _is_valid_functional_unit(self, value: str) -> bool:

        if not value or value.lower() == "nan":
            return False

        invalid_patterns = [
            "百分比",
            "%",
            "percentage",
            "unit:",
            "functional unit",
            "declared unit",
        ]

        value_lower = value.lower().strip()

        if len(value_lower) < 3:
            return False

        if all(c in " /-.,;:()[]{}" for c in value):
            return False

        for pattern in invalid_patterns:
            if pattern in value_lower:

                if pattern in ["functional unit", "declared unit"] and len(value) > 30:
                    continue
                return False

        has_digit = any(c.isdigit() for c in value)
        has_letter = any(c.isalpha() for c in value)

        if has_digit and has_letter and len(value) >= 3:
            return True

        if len(value) >= 10:
            return True

        return False

    def _find_multiline_value(
        self, data: pd.DataFrame, label_keywords: list, min_length: int = 10
    ) -> str:

        for i in range(len(data)):
            for j in range(len(data.columns)):
                cell_value = str(data.iloc[i, j]).strip().lower()

                if any(kw.lower() in cell_value for kw in label_keywords):

                    lines = []

                    if j + 1 < len(data.columns):
                        right_value = str(data.iloc[i, j + 1]).strip()
                        if (
                            right_value
                            and right_value.lower() != "nan"
                            and len(right_value) >= min_length
                        ):
                            return right_value

                    for offset in range(1, 10):
                        if i + offset < len(data):
                            line = str(data.iloc[i + offset, j]).strip()

                            if not line or line.lower() == "nan":
                                break

                            if any(
                                stop_word in line.lower()
                                for stop_word in [
                                    "四、",
                                    "五、",
                                    "iv.",
                                    "v.",
                                    "清单",
                                    "inventory",
                                    "影响",
                                    "impact",
                                ]
                            ):
                                break
                            lines.append(line)

                    if lines:
                        result = " ".join(lines)
                        if len(result) >= min_length:
                            return result

        return ""

    def _extract_product_info(self, data: pd.DataFrame) -> Dict:

        product_info = {}

        product_name = self._find_value_after_label(data, "产品名称")
        if not product_name:
            product_name = self._find_value_after_label(data, "Product name")
        if not product_name:
            product_name = self._find_value_after_label(data, "Product")
        if product_name:
            product_info["product_name"] = product_name
            print(f"  - 找到产品名称: {product_name[:100]}")

        product_model = self._find_value_after_label(data, "产品规格型号")
        if not product_model:
            product_model = self._find_value_after_label(data, "Product model")
        if not product_model:
            product_model = self._find_value_after_label(data, "Model")
        if not product_model:
            product_model = self._find_value_after_label(data, "Specification")
        if product_model:
            product_info["product_model"] = product_model
            print(f"  - 找到产品规格型号: {product_model[:100]}")

        product_function = self._find_value_after_label(data, "产品功能")
        if not product_function:
            product_function = self._find_value_after_label(data, "Product function")
        if not product_function:
            product_function = self._find_value_after_label(data, "Function")
        if product_function:
            product_info["product_function"] = product_function
            print(f"  - 找到产品功能: {product_function[:100]}")

        product_description = self._find_value_after_label(data, "产品介绍")
        if not product_description:
            product_description = self._find_value_after_label(
                data, "Product description"
            )
        if not product_description:
            product_description = self._find_value_after_label(data, "Description")
        if product_description:
            product_info["product_description"] = product_description
            print(f"  - 找到产品介绍: {product_description[:100]}")

        return product_info

    def _extract_producer_info(self, data: pd.DataFrame) -> Dict:

        producer_info = {}

        producer_name = self._find_value_after_label(data, "生产者名称")
        if not producer_name:
            producer_name = self._find_value_after_label(data, "Producer name")
        if not producer_name:
            producer_name = self._find_value_after_label(data, "Producer")
        if not producer_name:
            producer_name = self._find_value_after_label(data, "Manufacturer")
        if producer_name:
            producer_info["producer_name"] = producer_name
            print(f"  - 找到生产者名称: {producer_name[:100]}")

        address = self._find_value_after_label(data, "地址")
        if not address:
            address = self._find_value_after_label(data, "Address")
        if address:
            producer_info["address"] = address
            print(f"  - 找到地址: {address[:100]}")

        legal_representative = self._find_value_after_label(data, "法定代表人")
        if not legal_representative:
            legal_representative = self._find_value_after_label(
                data, "Legal representative"
            )
        if legal_representative:
            producer_info["legal_representative"] = legal_representative
            print(f"  - 找到法定代表人: {legal_representative[:100]}")

        contact_person = self._find_value_after_label(data, "授权人(联系人)")
        if not contact_person:
            contact_person = self._find_value_after_label(data, "联系人")
        if not contact_person:
            contact_person = self._find_value_after_label(data, "Contact person")
        if not contact_person:
            contact_person = self._find_value_after_label(data, "Contact")
        if contact_person:
            producer_info["contact_person"] = contact_person
            print(f"  - 找到联系人: {contact_person[:100]}")

        contact_phone = self._find_value_after_label(data, "联系电话")
        if not contact_phone:
            contact_phone = self._find_value_after_label(data, "Contact phone")
        if not contact_phone:
            contact_phone = self._find_value_after_label(data, "Phone")
        if not contact_phone:
            contact_phone = self._find_value_after_label(data, "Telephone")
        if contact_phone:
            producer_info["contact_phone"] = contact_phone
            print(f"  - 找到联系电话: {contact_phone[:100]}")

        company_overview = self._find_value_after_label(data, "企业概况")
        if not company_overview:
            company_overview = self._find_value_after_label(data, "Company overview")
        if company_overview:
            producer_info["company_overview"] = company_overview
            print(f"  - 找到企业概况: {company_overview[:100]}")

        report_no = self._find_value_after_label(data, "报告编号")
        if not report_no:
            report_no = self._find_value_after_label(data, "Report number")
        if not report_no:
            report_no = self._find_value_after_label(data, "Report no")
        if report_no:
            producer_info["report_number"] = report_no
            print(f"  - 找到报告编号: {report_no[:100]}")

        return producer_info

    def _extract_quantification_method(self, data: pd.DataFrame) -> Dict:

        method = {}

        based_on_standard = self._find_value_after_label(data, "Based on the standard:")
        if not based_on_standard:
            based_on_standard = self._find_value_after_label(data, "Based on standard:")
        if not based_on_standard:
            based_on_standard = self._find_value_after_label(data, "基于标准:")

        if not based_on_standard:
            based_on_standard = self._find_value_after_label(data, "依据标准")
        if not based_on_standard:
            based_on_standard = self._find_value_after_label(data, "Standard")
        if not based_on_standard:
            based_on_standard = self._find_value_after_label(data, "Standards used")
        if not based_on_standard:
            based_on_standard = self._find_value_after_label(
                data, "Assessment standard"
            )

        if based_on_standard:
            method["standard"] = based_on_standard
            method["quantitative_method"] = based_on_standard
            print(f"  - 找到依据标准: {based_on_standard[:100]}")

        quantitative_method = self._find_value_after_label(data, "Quantitative method")
        if not quantitative_method:
            quantitative_method = self._find_value_after_label(data, "量化方法")
        if not quantitative_method:
            quantitative_method = self._find_value_after_label(data, "LCIA method")
        if not quantitative_method:
            quantitative_method = self._find_value_after_label(
                data, "Impact assessment method"
            )
        if not quantitative_method:
            quantitative_method = self._find_value_after_label(data, "评价方法")

        if quantitative_method:
            method["quantitative_method"] = quantitative_method
            method["standard"] = quantitative_method
            print(f"  - 找到量化方法: {quantitative_method[:100]}")

        if method.get("quantitative_method") or method.get("standard"):
            final_method = method.get("quantitative_method") or method.get("standard")
            print(f"  ℹ️  将使用此方法进行LCIA计算: {final_method[:100]}")

        return method

    def _extract_quantification_purpose(self, data: pd.DataFrame) -> str:

        keywords = ["量化目的", "二、量化目的", "goal", "purpose", "aim", "objective"]

        for i in range(len(data)):
            for j in range(len(data.columns)):
                cell_value = str(data.iloc[i, j]).strip().lower()

                if any(keyword in cell_value for keyword in keywords):

                    purpose_lines = []
                    for offset in range(1, 5):
                        if i + offset < len(data):
                            line = str(data.iloc[i + offset, j]).strip()
                            if (
                                line
                                and line.lower() not in ["nan", "none", ""]
                                and not any(
                                    x in line
                                    for x in ["三、", "scope", "system boundary"]
                                )
                            ):
                                purpose_lines.append(line)
                            else:
                                break

                    if purpose_lines:
                        result = " ".join(purpose_lines)
                        print(f"  - 找到量化目的: {result[:100]}")
                        return result

        return ""

    def _extract_quantification_scope(self, data: pd.DataFrame) -> Dict:

        scope = {}

        functional_unit = None

        functional_unit = self._find_value_after_label(
            data, "功能单位", row_offset=0, col_offset=1
        )
        if functional_unit and self._is_valid_functional_unit(functional_unit):
            pass
        else:

            functional_unit = self._find_value_after_label(
                data, "功能单位", row_offset=1, col_offset=0
            )
            if functional_unit and not self._is_valid_functional_unit(functional_unit):
                functional_unit = None

        if not functional_unit:

            functional_unit = self._find_value_after_label(
                data, "Functional unit", row_offset=0, col_offset=1
            )
            if functional_unit and not self._is_valid_functional_unit(functional_unit):
                functional_unit = None

            if not functional_unit:
                functional_unit = self._find_value_after_label(
                    data, "Functional unit", row_offset=1, col_offset=0
                )
                if functional_unit and not self._is_valid_functional_unit(
                    functional_unit
                ):
                    functional_unit = None

            if not functional_unit:
                functional_unit = self._find_value_after_label(
                    data, "Functional unit", row_offset=0, col_offset=1, fuzzy=True
                )
                if functional_unit and not self._is_valid_functional_unit(
                    functional_unit
                ):
                    functional_unit = None
                if not functional_unit:
                    functional_unit = self._find_value_after_label(
                        data, "Functional unit", row_offset=1, col_offset=0, fuzzy=True
                    )
                    if functional_unit and not self._is_valid_functional_unit(
                        functional_unit
                    ):
                        functional_unit = None

        if not functional_unit:

            functional_unit = self._find_value_after_label(
                data, "声明单位", row_offset=0, col_offset=1
            )
            if functional_unit and not self._is_valid_functional_unit(functional_unit):
                functional_unit = None
            if not functional_unit:
                functional_unit = self._find_value_after_label(
                    data, "声明单位", row_offset=1, col_offset=0
                )
                if functional_unit and not self._is_valid_functional_unit(
                    functional_unit
                ):
                    functional_unit = None

        if not functional_unit:

            functional_unit = self._find_value_after_label(
                data, "Declared unit", row_offset=0, col_offset=1
            )
            if functional_unit and not self._is_valid_functional_unit(functional_unit):
                functional_unit = None
            if not functional_unit:
                functional_unit = self._find_value_after_label(
                    data, "Declared unit", row_offset=1, col_offset=0
                )
                if functional_unit and not self._is_valid_functional_unit(
                    functional_unit
                ):
                    functional_unit = None

        if not functional_unit:

            for i in range(len(data)):
                for j in range(len(data.columns)):
                    cell_value = str(data.iloc[i, j]).strip().lower()

                    if ("functional" in cell_value and "unit" in cell_value) or (
                        "declared" in cell_value and "unit" in cell_value
                    ):

                        if j + 1 < len(data.columns):
                            value = str(data.iloc[i, j + 1]).strip()
                            if self._is_valid_functional_unit(value):
                                functional_unit = value
                                break

                        if not functional_unit and i + 1 < len(data):
                            value = str(data.iloc[i + 1, j]).strip()
                            if self._is_valid_functional_unit(value):
                                functional_unit = value
                                break
                if functional_unit:
                    break

        if not functional_unit:
            temp_value = self._find_multiline_value(
                data,
                ["functional unit", "declared unit", "功能单位", "声明单位"],
                min_length=10,
            )
            if temp_value and self._is_valid_functional_unit(temp_value):
                functional_unit = temp_value

        if not functional_unit:
            for i in range(len(data)):
                for j in range(len(data.columns)):
                    cell_value = str(data.iloc[i, j]).strip()

                    if any(
                        keyword in cell_value.lower()
                        for keyword in ["三、", "scope", "量化", "quantif"]
                    ):

                        for offset in range(1, 20):
                            if i + offset < len(data):
                                for search_col in range(len(data.columns)):
                                    search_cell = (
                                        str(data.iloc[i + offset, search_col])
                                        .strip()
                                        .lower()
                                    )
                                    if any(
                                        kw in search_cell
                                        for kw in ["functional", "declared", "功能单位"]
                                    ):

                                        if search_col + 1 < len(data.columns):
                                            value = str(
                                                data.iloc[i + offset, search_col + 1]
                                            ).strip()
                                            if self._is_valid_functional_unit(value):
                                                functional_unit = value
                                                break
                                        if (
                                            not functional_unit
                                            and i + offset + 1 < len(data)
                                        ):
                                            value = str(
                                                data.iloc[i + offset + 1, search_col]
                                            ).strip()
                                            if self._is_valid_functional_unit(value):
                                                functional_unit = value
                                                break
                                if functional_unit:
                                    break
                        if functional_unit:
                            break
                if functional_unit:
                    break

        if functional_unit:
            scope["functional_unit"] = functional_unit
            print(f"  ✅ 找到功能单位: {functional_unit[:100]}")
        else:
            print(
                f"  ⚠️ 未能找到功能单位，请检查Excel文件中是否包含'Functional Unit'或'功能单位'标签"
            )

        system_boundary = None

        system_boundary = self._find_value_after_label(data, "系统边界")

        if not system_boundary:
            system_boundary = self._find_value_after_label(data, "System boundary")
        if not system_boundary:
            system_boundary = self._find_value_after_label(data, "System boundaries")

        if not system_boundary:
            system_boundary = self._find_value_after_label(
                data, "system boundary", fuzzy=True
            )
        if not system_boundary:
            system_boundary = self._find_value_after_label(data, "boundary", fuzzy=True)

        if not system_boundary:
            system_boundary = self._find_multiline_value(
                data,
                ["system boundary", "system boundaries", "系统边界"],
                min_length=15,
            )

        if not system_boundary:
            for i in range(len(data)):
                for j in range(len(data.columns)):
                    cell_value = str(data.iloc[i, j]).strip()

                    if any(
                        keyword in cell_value.lower()
                        for keyword in ["三、", "scope", "量化", "quantif"]
                    ):

                        for offset in range(1, 30):
                            if i + offset < len(data):
                                for search_col in range(len(data.columns)):
                                    search_cell = (
                                        str(data.iloc[i + offset, search_col])
                                        .strip()
                                        .lower()
                                    )
                                    if any(
                                        kw in search_cell
                                        for kw in ["system", "boundary", "系统边界"]
                                    ):

                                        if search_col + 1 < len(data.columns):
                                            value = str(
                                                data.iloc[i + offset, search_col + 1]
                                            ).strip()
                                            if (
                                                value
                                                and value.lower() != "nan"
                                                and len(value) > 15
                                            ):
                                                system_boundary = value
                                                break

                                        if (
                                            not system_boundary
                                            and i + offset + 1 < len(data)
                                        ):
                                            lines = []
                                            for line_offset in range(1, 5):
                                                if i + offset + line_offset < len(data):
                                                    line_value = str(
                                                        data.iloc[
                                                            i + offset + line_offset,
                                                            search_col,
                                                        ]
                                                    ).strip()
                                                    if (
                                                        line_value
                                                        and line_value.lower() != "nan"
                                                    ):
                                                        lines.append(line_value)
                                                    else:
                                                        break
                                            if lines:
                                                combined = " ".join(lines)
                                                if len(combined) > 15:
                                                    system_boundary = combined
                                                    break
                                if system_boundary:
                                    break
                        if system_boundary:
                            break
                if system_boundary:
                    break

        if system_boundary:
            scope["system_boundary"] = system_boundary
            print(f"  - 找到系统边界: {system_boundary[:100]}")

        cutoff_criteria = self._find_value_after_label(data, "取舍准则")
        if not cutoff_criteria:
            cutoff_criteria = self._find_value_after_label(data, "Cut-off criteria")
        if not cutoff_criteria:
            cutoff_criteria = self._find_value_after_label(data, "Cutoff criteria")
        if cutoff_criteria:
            scope["cutoff_criteria"] = cutoff_criteria
            print(f"  - 找到取舍准则: {cutoff_criteria[:100]}")

        time_scope = self._find_value_after_label(data, "时间范围")
        if not time_scope:
            time_scope = self._find_value_after_label(data, "Time scope")
        if not time_scope:
            time_scope = self._find_value_after_label(data, "Time period")
        if not time_scope:
            time_scope = self._find_value_after_label(data, "Temporal scope")
        if time_scope:
            scope["time_scope"] = time_scope
            print(f"  - 找到时间范围: {time_scope[:100]}")

        return scope

    def _extract_inventory_analysis(self, data: pd.DataFrame) -> Dict:

        inventory = {}

        primary_data = self._find_value_after_label(data, "初级数据")
        if not primary_data:
            primary_data = self._find_value_after_label(data, "初级数据来源")
        if not primary_data:
            primary_data = self._find_value_after_label(data, "Primary data source")
        if not primary_data:
            primary_data = self._find_value_after_label(data, "Primary data")
        if primary_data:
            inventory["primary_data_source"] = primary_data
            print(f"  - 找到初级数据来源: {primary_data[:100]}")

        secondary_data = self._find_value_after_label(data, "次级数据")
        if not secondary_data:
            secondary_data = self._find_value_after_label(data, "次级数据来源")
        if not secondary_data:
            secondary_data = self._find_value_after_label(data, "Secondary data source")
        if not secondary_data:
            secondary_data = self._find_value_after_label(data, "Secondary data")
        if secondary_data:
            inventory["secondary_data_source"] = secondary_data
            print(f"  - 找到次级数据来源: {secondary_data[:100]}")

        allocation_basis = self._find_value_after_label(data, "分配依据")
        if not allocation_basis:
            allocation_basis = self._find_value_after_label(data, "Allocation basis")
        if not allocation_basis:
            allocation_basis = self._find_value_after_label(data, "Allocation method")
        if allocation_basis:
            inventory["allocation_basis"] = allocation_basis
            print(f"  - 找到分配依据: {allocation_basis[:100]}")

        allocation_procedure = self._find_value_after_label(data, "分配程序")
        if not allocation_procedure:
            allocation_procedure = self._find_value_after_label(
                data, "Allocation procedure"
            )
        if not allocation_procedure:
            allocation_procedure = self._find_value_after_label(
                data, "Allocation process"
            )
        if allocation_procedure:
            inventory["allocation_procedure"] = allocation_procedure
            print(f"  - 找到分配程序: {allocation_procedure[:100]}")

        return inventory

    def _extract_lifecycle_stages(self, data: pd.DataFrame) -> List[str]:

        stages = []

        for i in range(len(data)):
            cell_value = str(data.iloc[i, 0]).strip()
            if cell_value == "生命周期阶段":

                for offset in range(1, 10):
                    if i + offset < len(data):
                        stage = str(data.iloc[i + offset, 0]).strip()
                        if (
                            stage
                            and stage.lower() not in ["nan", "none", ""]
                            and not any(
                                x in stage for x in ["表", "图", "五、", "六、"]
                            )
                        ):
                            stages.append(stage)
                        else:
                            break
                break

        return stages
