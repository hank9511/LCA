"""Project Context Module"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import re
import json
from .config import PREFERRED_LCIA_METHOD


@dataclass
class FunctionalUnitSpec:
    """Functional unit specification parsed from user input"""

    amount: float = 1.0
    unit: str = "kg"
    flow_property: str = "Mass"
    description: str = ""

    @classmethod
    def parse(cls, functional_unit_str: Optional[str]) -> "FunctionalUnitSpec":
        """Parse functional unit string into structured specification"""
        if not functional_unit_str or not functional_unit_str.strip():
            return cls()

        unit_to_property = {
            "kg": "Mass",
            "g": "Mass",
            "t": "Mass",
            "ton": "Mass",
            "tonnes": "Mass",
            "lb": "Mass",
            "oz": "Mass",
            "m3": "Volume",
            "l": "Volume",
            "liter": "Volume",
            "litre": "Volume",
            "ml": "Volume",
            "gallon": "Volume",
            "gal": "Volume",
            "mj": "Energy",
            "kj": "Energy",
            "kwh": "Energy",
            "j": "Energy",
            "piece": "Number",
            "pieces": "Number",
            "item": "Number",
            "items": "Number",
            "item(s)": "Number",
            "unit": "Number",
            "units": "Number",
            "p": "Number",
            "t*km": "Mass transport",
            "tkm": "Mass transport",
            "kg*km": "Mass transport",
            "m2": "Area",
            "ha": "Area",
            "hectare": "Area",
            "m": "Length",
            "km": "Length",
            "cm": "Length",
            "mm": "Length",
        }

        pattern = r"(\d+\.?\d*)\s*([a-zA-Z0-9³²]+)"
        match = re.search(pattern, functional_unit_str.strip())

        if match:
            amount = float(match.group(1))
            unit = match.group(2).lower()

            flow_property = unit_to_property.get(unit, "Mass")

            return cls(
                amount=amount,
                unit=match.group(2),
                flow_property=flow_property,
                description=functional_unit_str.strip(),
            )

        return cls(description=functional_unit_str.strip())


@dataclass
class SystemBoundarySpec:
    """System boundary specifications from user input"""

    description: str = ""
    stages: list = field(default_factory=list)
    geographic_scope: str = ""
    time_scale: str = ""
    cutoff_criteria: str = ""

    @classmethod
    def from_report_info(cls, report_info: Dict[str, Any]) -> "SystemBoundarySpec":
        """Create from ProjectReportInfo dictionary"""
        stages = []
        if report_info.get("system_boundary_stages"):
            try:
                stages = json.loads(report_info["system_boundary_stages"])
            except:
                stages = []

        geographic_scope = ""
        description = report_info.get("system_boundary_description", "")

        geo_keywords = [
            "China",
            "Chinese",
            "Europe",
            "European",
            "USA",
            "US",
            "Global",
            "Asia",
            "Africa",
            "Americas",
        ]
        for keyword in geo_keywords:
            if keyword.lower() in description.lower():
                geographic_scope = keyword
                break

        return cls(
            description=description,
            stages=stages,
            geographic_scope=geographic_scope,
            time_scale=report_info.get("time_scale", ""),
            cutoff_criteria=report_info.get("cutoff_criteria", ""),
        )


@dataclass
class ProjectContext:
    """Project context encapsulating all project-specific information"""

    project_id: str = ""
    product_name: str = ""
    producer_name: str = ""

    lcia_method_keyword: str = field(default_factory=lambda: PREFERRED_LCIA_METHOD)
    functional_unit: FunctionalUnitSpec = field(default_factory=FunctionalUnitSpec)
    system_boundary: SystemBoundarySpec = field(default_factory=SystemBoundarySpec)

    primary_data_source: str = ""
    secondary_data_source: str = ""

    allocation_basis: str = ""
    allocation_procedure: str = ""

    quantitative_purpose: str = ""
    product_function: str = ""

    @classmethod
    def from_report_info(
        cls, project_id: str, report_info: Dict[str, Any]
    ) -> "ProjectContext":
        """Create ProjectContext from ProjectReportInfo database record"""
        return cls(
            project_id=project_id,
            product_name=report_info.get("product_name", ""),
            producer_name=report_info.get("producer_name", ""),
            lcia_method_keyword=(
                report_info.get("standard_used") or PREFERRED_LCIA_METHOD
            ),
            functional_unit=FunctionalUnitSpec.parse(
                report_info.get("functional_unit")
            ),
            system_boundary=SystemBoundarySpec.from_report_info(report_info),
            primary_data_source=report_info.get("primary_data_source", ""),
            secondary_data_source=report_info.get("secondary_data_source", ""),
            allocation_basis=report_info.get("allocation_basis", ""),
            allocation_procedure=report_info.get("allocation_procedure", ""),
            quantitative_purpose=report_info.get("quantitative_purpose", ""),
            product_function=report_info.get("product_function", ""),
        )

    @classmethod
    def default(cls) -> "ProjectContext":
        """Create default project context when no report info is available"""
        return cls(
            lcia_method_keyword=PREFERRED_LCIA_METHOD,
            functional_unit=FunctionalUnitSpec(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            "project_id": self.project_id,
            "product_name": self.product_name,
            "producer_name": self.producer_name,
            "lcia_method_keyword": self.lcia_method_keyword,
            "functional_unit": {
                "amount": self.functional_unit.amount,
                "unit": self.functional_unit.unit,
                "flow_property": self.functional_unit.flow_property,
                "description": self.functional_unit.description,
            },
            "system_boundary": {
                "description": self.system_boundary.description,
                "geographic_scope": self.system_boundary.geographic_scope,
                "time_scale": self.system_boundary.time_scale,
            },
            "primary_data_source": self.primary_data_source,
            "secondary_data_source": self.secondary_data_source,
        }

    def print_summary(self):
        """Print a human-readable summary of the project context"""
        print("\n" + "=" * 80)
        print("📋 Project Context Summary")
        print("=" * 80)
        print(f"🏷️  Project: {self.product_name} ({self.project_id})")
        print(f"🏢 Producer: {self.producer_name}")
        print(f"📊 LCIA Method: {self.lcia_method_keyword}")
        print(
            f"🎯 Functional Unit: {self.functional_unit.amount} {self.functional_unit.unit}"
        )
        print(f"   - Flow Property: {self.functional_unit.flow_property}")
        if self.functional_unit.description:
            print(f"   - Description: {self.functional_unit.description}")

        print(f"🌍 System Boundary:")
        if self.system_boundary.geographic_scope:
            print(f"   - Geographic: {self.system_boundary.geographic_scope}")
        if self.system_boundary.time_scale:
            print(f"   - Time: {self.system_boundary.time_scale}")
        if self.system_boundary.description:
            print(f"   - Description: {self.system_boundary.description[:100]}...")

        if self.primary_data_source:
            print(f"📚 Primary Data: {self.primary_data_source[:50]}...")
        if self.secondary_data_source:
            print(f"📚 Secondary Data: {self.secondary_data_source[:50]}...")

        print("=" * 80 + "\n")
