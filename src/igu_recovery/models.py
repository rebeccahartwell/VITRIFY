from dataclasses import dataclass
from typing import List, Optional, Dict
from .constants import (
    BACKHAUL_FACTOR, EMISSIONFACTOR_TRUCK, EMISSIONFACTOR_FERRY,
    TRUCK_CAPACITY_T, FERRY_CAPACITY_T, DISTANCE_FALLBACK_A_KM, DISTANCE_FALLBACK_B_KM,
    BREAKAGE_RATE_GLOBAL, HUMIDITY_FAILURE_RATE, SPLIT_YIELD, REMANUFACTURING_YIELD,
    ROUTE_A_MODE, ROUTE_B_MODE, IGUS_PER_STILLAGE, STILLAGE_MASS_EMPTY_KG,
    MAX_TRUCK_LOAD_KG, E_SITE_KGCO2_PER_M2, INCLUDE_STILLAGE_EMBODIED,
    REPURPOSE_MEDIUM_KGCO2_PER_M2,
    GlazingType, GlassType, CoatingType, SealantType, SpacerMaterial,
    EdgeSealCondition, TransportMode, ProcessLevel, SystemPath, RepurposePreset
)

@dataclass
class Location:
    lat: float
    lon: float


@dataclass
class RouteConfig:
    """
    Configuration for a specific transport route.
    """
    mode: TransportMode
    truck_km: float = 0.0
    ferry_km: float = 0.0


@dataclass
class TransportModeConfig:
    """
    Transport configuration between:
    - origin: project origin (Dismantling from Building / on-site removal)
    - processor: main processing site
    - reuse: second site (reuse/repurposed installation site)
    """
    origin: Location
    processor: Location
    reuse: Location
    include_ferry: bool = False
    backhaul_factor: float = BACKHAUL_FACTOR
    emissionfactor_truck: float = EMISSIONFACTOR_TRUCK
    emissionfactor_ferry: float = EMISSIONFACTOR_FERRY
    capacity_truck_t: float = TRUCK_CAPACITY_T
    capacity_ferry_t: float = FERRY_CAPACITY_T
    distance_fallback_A_km: float = DISTANCE_FALLBACK_A_KM
    distance_fallback_B_km: float = DISTANCE_FALLBACK_B_KM
    travel_truck_A_km_override: Optional[float] = None
    travel_ferry_A_km_override: Optional[float] = None
    travel_truck_B_km_override: Optional[float] = None
    travel_ferry_B_km_override: Optional[float] = None
    landfill: Optional[Location] = None


@dataclass
class ProcessSettings:
    """
    Settings controlling process assumptions and routing:
    - breakage/humidity/splitting/remanufacturing yields
    - transport modes for A-leg (building→processor) and B-leg (processor→2nd site)
    - stillage settings and truck capacity
    - process level (component vs system) and system path (reuse vs repurpose)
    - Dismantling from Building and repurposing emission factors.
    """
    breakage_rate_global: float = BREAKAGE_RATE_GLOBAL
    humidity_failure_rate: float = HUMIDITY_FAILURE_RATE
    split_yield: float = SPLIT_YIELD
    remanufacturing_yield: float = REMANUFACTURING_YIELD
    split_yield: float = SPLIT_YIELD
    remanufacturing_yield: float = REMANUFACTURING_YIELD
    # route_A_mode / route_B_mode replaced by route_configs registry
    # key: str (e.g. "origin_to_processor", "processor_to_reuse") -> RouteConfig
    route_configs: Dict[str, 'RouteConfig'] = None # type: ignore
    igus_per_stillage: int = IGUS_PER_STILLAGE
    stillage_mass_empty_kg: float = STILLAGE_MASS_EMPTY_KG
    max_truck_load_kg: float = MAX_TRUCK_LOAD_KG
    process_level: ProcessLevel = "component"
    system_path: SystemPath = "reuse"
    e_site_kgco2_per_m2: float = E_SITE_KGCO2_PER_M2
    include_stillage_embodied: bool = INCLUDE_STILLAGE_EMBODIED
    repurpose_preset: RepurposePreset = "medium"
    repurpose_kgco2_per_m2: float = REPURPOSE_MEDIUM_KGCO2_PER_M2


@dataclass
class IGUCondition:
    visible_edge_seal_condition: EdgeSealCondition
    visible_fogging: bool
    cracks_chips: bool
    age_years: float
    reuse_allowed: bool


@dataclass
class SealGeometry:
    """
    Global seal geometry settings (constant for all IGUs in the batch).
    - primary_thickness_mm: Thickness of the primary seal (e.g. butyl).
    - primary_width_mm: Width of the primary seal.
    - secondary_width_mm: Width of the secondary seal.
    
    Note: Secondary seal *thickness* is not constant; it is derived from the
    IGU's cavity thickness(es) using the modelling rules defined above.
    """
    primary_thickness_mm: float
    primary_width_mm: float
    secondary_width_mm: float


@dataclass
class IGUGroup:
    """
    Describes a homogeneous group of IGUs with identical geometry, build-up and condition.
    Note: cavity_thickness_mm (and cavity_thickness_2_mm) are used both for the
    IGU build-up depth and to derive the secondary seal thickness.
    """
    quantity: int
    unit_width_mm: float
    unit_height_mm: float
    glazing_type: GlazingType
    glass_type_outer: GlassType
    glass_type_inner: GlassType
    coating_type: CoatingType
    sealant_type_secondary: SealantType
    spacer_material: SpacerMaterial
    interlayer_type: Optional[str]
    condition: IGUCondition
    thickness_outer_mm: float          # pane thickness (outer)
    thickness_inner_mm: float          # pane thickness (inner)
    cavity_thickness_mm: float         # cavity thickness (first cavity)
    IGU_depth_mm: float                # overall IGU build-up depth
    mass_per_m2_override: Optional[float] = None
    thickness_centre_mm: Optional[float] = None   # pane thickness (centre, triple)
    cavity_thickness_2_mm: Optional[float] = None # second cavity thickness (triple)
    sealant_type_primary: Optional[SealantType] = None  # Metadata only


@dataclass
class BatchInput:
    """
    Wrapper for a complete calculation batch: transport config, process settings and IGU groups.
    """
    transport: TransportModeConfig
    processes: ProcessSettings
    igu_groups: List[IGUGroup]


@dataclass
class EmissionBreakdown:
    """
    Full-chain emission breakdown for a batch.
    """
    dismantling_from_building_kgco2: float
    packaging_kgco2: float
    transport_A_kgco2: float
    disassembly_kgco2: float
    remanufacturing_kgco2: float
    quality_control_kgco2: float
    transport_B_kgco2: float
    total_kgco2: float
    extra: Dict[str, float]


@dataclass
class FlowState:
    """
    Tracks the mass/count flow through the recovery process, accounting for yield losses.
    """
    igus: float
    area_m2: float
    mass_kg: float


@dataclass
class ScenarioResult:
    """
    Summary of a Scenario run.
    """
    scenario_name: str
    total_emissions_kgco2: float
    by_stage: Dict[str, float]
    initial_igus: float
    final_igus: float
    initial_area_m2: float
    final_area_m2: float
    initial_mass_kg: float
    final_mass_kg: float
    yield_percent: float
