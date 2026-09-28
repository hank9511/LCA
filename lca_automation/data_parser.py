import os
from typing import Optional

from .excel_parser import ExcelLCAParser
from .project_context import ProjectContext
from .data_structures import LCACase


class DataParser:

    def __init__(self, excel_path: str, database_path: str = "ecoinvent_0121"):

        self.excel_path = excel_path
        self.database_path = database_path
        self.project_context = self._create_project_context()

    def _create_project_context(self) -> ProjectContext:

        context = ProjectContext.default()

        return context

    def parse(self) -> LCACase:

        print(f"📊 Parsing Excel file: {self.excel_path}")

        parser = ExcelLCAParser(self.excel_path, self.project_context)

        lca_case = parser.parse_excel_to_lca_case(
            case_name=f"LCA Case from {os.path.basename(self.excel_path)}",
            case_description=f"Auto-generated LCA case from: {self.excel_path}",
            category="Automated import",
        )

        lca_case.flow_metadata = {
            flow_name: {
                "provider_flow_meta": info.get("provider_flow_meta", {}),
                "explicit_provider": info.get("explicit_provider", ""),
                "has_emission_factor_provider": info.get(
                    "has_emission_factor_provider", False
                ),
                "force_foreground_flow": info.get("force_foreground_flow", False),
            }
            for flow_name, info in parser.flows_data.items()
        }
        lca_case.process_provider_metadata = parser.process_provider_metadata

        lca_case.excel_metadata = parser.parse_excel_metadata()

        print(f"✅ Parsing completed:")
        print(f"  - Flows: {len(lca_case.flows)}")
        print(f"  - Processes: {len(lca_case.processes)}")
        print(f"  - Product Systems: {len(lca_case.product_systems)}")

        return lca_case

    def parse_metadata(self) -> dict:

        parser = ExcelLCAParser(self.excel_path, self.project_context)
        metadata = parser.parse_excel_metadata()
        return metadata


if __name__ == "__main__":

    import sys
    import os

    if len(sys.argv) > 1:
        excel_file = sys.argv[1]
    else:
        excel_file = "HS_case_EN_0120.xlsx"

    parser = DataParser(excel_file)
    lca_case = parser.parse()

    print(f"\n📋 Parse results:")
    print(f"Case name: {lca_case.case_name}")
    print(f"Description: {lca_case.description}")
    print(f"Flow count: {len(lca_case.flows)}")
    print(f"Process count: {len(lca_case.processes)}")
