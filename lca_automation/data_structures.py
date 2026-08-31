"""Data structure definitions for the LCA analysis system, compliant with openLCA schema"""

from dataclasses import dataclass
from typing import Dict, List, Optional


class FlowType:
    ELEMENTARY_FLOW = "ELEMENTARY_FLOW"
    PRODUCT_FLOW = "PRODUCT_FLOW"
    WASTE_FLOW = "WASTE_FLOW"


class ProcessType:
    UNIT_PROCESS = "UNIT_PROCESS"
    LCI_RESULT = "LCI_RESULT"


class UncertaintyType:
    LOG_NORMAL_DISTRIBUTION = "LOG_NORMAL_DISTRIBUTION"
    NORMAL_DISTRIBUTION = "NORMAL_DISTRIBUTION"
    TRIANGLE_DISTRIBUTION = "TRIANGLE_DISTRIBUTION"
    UNIFORM_DISTRIBUTION = "UNIFORM_DISTRIBUTION"


class AllocationType:
    """Allocation method types compatible with openLCA AllocationType schema"""

    PHYSICAL_ALLOCATION = "PHYSICAL_ALLOCATION"
    ECONOMIC_ALLOCATION = "ECONOMIC_ALLOCATION"
    CAUSAL_ALLOCATION = "CAUSAL_ALLOCATION"
    USE_DEFAULT_ALLOCATION = "USE_DEFAULT_ALLOCATION"
    NO_ALLOCATION = "NO_ALLOCATION"


@dataclass
class Ref:
    """Reference to another entity"""

    id: str = ""
    name: str = ""
    category: str = ""
    description: str = ""


@dataclass
class ExchangeRef:
    """Reference to an exchange in a process"""

    internal_id: int = 0


@dataclass
class AllocationFactor:
    """Allocation factor compatible with openLCA AllocationFactor schema"""

    allocation_type: str = AllocationType.PHYSICAL_ALLOCATION
    product: Optional[Ref] = None
    value: float = 0.0
    formula: str = ""
    exchange: Optional[ExchangeRef] = None


@dataclass
class Uncertainty:
    """Uncertainty distribution compatible with openLCA Uncertainty schema"""

    distribution_type: str = UncertaintyType.NORMAL_DISTRIBUTION
    geom_mean: Optional[float] = None
    geom_sd: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    minimum: Optional[float] = None
    mode: Optional[float] = None
    sd: Optional[float] = None


@dataclass
class FlowPropertyFactor:
    """Flow property factor compatible with openLCA FlowPropertyFactor schema"""

    conversion_factor: float = 1.0
    flow_property: Optional[Ref] = None
    is_ref_flow_property: bool = True


@dataclass
class Flow:
    """Flow compatible with openLCA Flow schema"""

    id: str = ""
    cas: str = ""
    category: str = ""
    description: str = ""
    flow_properties: List[FlowPropertyFactor] = None
    flow_type: str = FlowType.PRODUCT_FLOW
    formula: str = ""
    is_infrastructure_flow: bool = False
    last_change: str = ""
    library: str = ""
    location: Optional[Ref] = None
    name: str = ""
    synonyms: str = ""
    tags: List[str] = None
    version: str = ""

    def __post_init__(self):
        if self.flow_properties is None:
            self.flow_properties = []
        if self.tags is None:
            self.tags = []


@dataclass
class Exchange:
    """Exchange compatible with openLCA Exchange schema"""

    amount: float = 0.0
    amount_formula: str = ""
    base_uncertainty: Optional[float] = None
    cost_formula: str = ""
    cost_value: Optional[float] = None
    currency: Optional[Ref] = None
    default_provider: Optional[Ref] = None
    description: str = ""
    dq_entry: str = ""
    flow: Optional[Ref] = None
    flow_property: Optional[Ref] = None
    internal_id: int = 1
    is_avoided_product: bool = False
    is_input: bool = True
    is_quantitative_reference: bool = False
    location: Optional[Ref] = None
    uncertainty: Optional[Uncertainty] = None
    unit: Optional[Ref] = None


@dataclass
class Process:
    """Simplified Process compatible with openLCA Process schema"""

    id: str = ""
    category: str = ""
    description: str = ""
    exchanges: List[Exchange] = None
    last_internal_id: int = 0
    location: Optional[Ref] = None
    name: str = ""
    process_type: str = ProcessType.UNIT_PROCESS
    tags: List[str] = None
    allocation_factors: List[AllocationFactor] = None
    default_allocation_method: str = AllocationType.NO_ALLOCATION

    def __post_init__(self):
        if self.exchanges is None:
            self.exchanges = []
        if self.tags is None:
            self.tags = []
        if self.allocation_factors is None:
            self.allocation_factors = []


@dataclass
class ProcessLink:
    """Process link compatible with openLCA ProcessLink schema"""

    exchange: Optional[int] = None
    flow: Optional[Ref] = None
    process: Optional[Ref] = None
    provider: Optional[Ref] = None


@dataclass
class ProductSystem:
    """Simplified Product system compatible with openLCA ProductSystem schema"""

    id: str = ""
    category: str = ""
    description: str = ""
    name: str = ""
    processes: List[Ref] = None
    ref_exchange: Optional[Dict] = None
    ref_process: Optional[Ref] = None
    target_amount: float = 1.0

    def __post_init__(self):
        if self.processes is None:
            self.processes = []


@dataclass
class ImpactFactor:
    """Impact factor compatible with openLCA ImpactFactor schema"""

    flow: Optional[Ref] = None
    flow_property: Optional[Ref] = None
    formula: str = ""
    location: Optional[Ref] = None
    uncertainty: Optional[Uncertainty] = None
    unit: Optional[Ref] = None
    value: float = 0.0


@dataclass
class ImpactCategory:
    """Impact category compatible with openLCA ImpactCategory schema"""

    id: str = ""
    category: str = ""
    code: str = ""
    description: str = ""
    direction: str = ""
    impact_factors: List[ImpactFactor] = None
    last_change: str = ""
    library: str = ""
    name: str = ""
    parameters: List[Dict] = None
    ref_unit: str = ""
    source: Optional[Ref] = None
    tags: List[str] = None
    version: str = ""

    def __post_init__(self):
        if self.impact_factors is None:
            self.impact_factors = []
        if self.parameters is None:
            self.parameters = []
        if self.tags is None:
            self.tags = []


@dataclass
class NwFactor:
    """NW factor compatible with openLCA NwFactor schema"""

    impact_category: Optional[Ref] = None
    normalisation_factor: float = 0.0
    weighting_factor: float = 0.0


@dataclass
class NwSet:
    """NW set compatible with openLCA NwSet schema"""

    id: str = ""
    description: str = ""
    factors: List[NwFactor] = None
    name: str = ""
    weighted_score_unit: str = ""

    def __post_init__(self):
        if self.factors is None:
            self.factors = []


@dataclass
class ImpactMethod:
    """Impact method compatible with openLCA ImpactMethod schema"""

    id: str = ""
    category: str = ""
    code: str = ""
    description: str = ""
    impact_categories: List[Ref] = None
    last_change: str = ""
    library: str = ""
    name: str = ""
    nw_sets: List[NwSet] = None
    source: Optional[Ref] = None
    tags: List[str] = None
    version: str = ""

    def __post_init__(self):
        if self.impact_categories is None:
            self.impact_categories = []
        if self.nw_sets is None:
            self.nw_sets = []
        if self.tags is None:
            self.tags = []


FlowSpec = Flow
ProcessSpec = Process
ProductSystemSpec = ProductSystem


@dataclass
class SimpleExchange:
    """Simplified exchange for Excel parsing"""

    flow_name: str
    amount: float
    is_input: bool = True
    is_quantitative_reference: bool = False
    unit: str = "kg"
    provider_name: str = ""
    is_avoided_product: bool = False
    allocation_value: float = 0.0
    cost_value: float = 0.0
    location: str = ""


@dataclass
class LCACase:
    """Complete LCA case definition"""

    case_name: str
    description: str
    category: str
    flows: List[Flow]
    processes: List[Process]
    product_systems: List[ProductSystem]
