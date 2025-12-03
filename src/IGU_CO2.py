from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2, ceil, floor
from typing import List, Optional, Literal, Dict
import requests

# ============================================================================
# SETTINGS
# ============================================================================

GEOCODER_USER_AGENT = "igu-reuse-tool/0.1 (CHANGE_THIS_TO_YOUR_EMAIL@DOMAIN)"

# Dismantling from Building (on-site removal) energy factor:
# kg CO2e per m² of IGU surface area removed from the existing building.
E_SITE_KGCO2_PER_M2 = 0.15

REMANUFACTURING_KGCO2_PER_M2 = 7.5
DISASSEMBLY_KGCO2_PER_M2 = 0.5

REPURPOSE_LIGHT_KGCO2_PER_M2 = 0.5
REPURPOSE_MEDIUM_KGCO2_PER_M2 = 1.0
REPURPOSE_HEAVY_KGCO2_PER_M2 = 2.0

STILLAGE_MANUFACTURE_KGCO2 = 500.0
STILLAGE_LIFETIME_CYCLES = 100
INCLUDE_STILLAGE_EMBODIED = False

# Emission factors in kgCO2e per tonne·km (tkm).
# These are GWP (CO2-equivalent) intensities, where:
# - "tonne" is the transported payload mass (IGUs + stillages) in metric tonnes
# - "km" is the distance travelled between the relevant locations (origin/processor/reuse)
EMISSIONFACTOR_TRUCK = 0.04   # kgCO2e/tkm (HGV lorry)
EMISSIONFACTOR_FERRY = 0.045  # kgCO2e/tkm (ferry)

BACKHAUL_FACTOR = 1.3

TRUCK_CAPACITY_T = 20.0
FERRY_CAPACITY_T = 1000.0

DISTANCE_FALLBACK_A_KM = 100.0
DISTANCE_FALLBACK_B_KM = 100.0

# Approximate surface mass of IGUs by glazing type (kg/m²).
# Single: approx. 4 mm float glass (~10 kg/m²).
MASS_PER_M2_SINGLE = 10.0
MASS_PER_M2_DOUBLE = 20.0
MASS_PER_M2_TRIPLE = 30.0

BREAKAGE_RATE_GLOBAL = 0.05
HUMIDITY_FAILURE_RATE = 0.05
SPLIT_YIELD = 0.95
REMANUFACTURING_YIELD = 0.90

IGUS_PER_STILLAGE = 20
STILLAGE_MASS_EMPTY_KG = 300.0
MAX_TRUCK_LOAD_KG = 20000.0

# Default transport modes for A-leg (building → processor) and B-leg (processor → 2nd site).
ROUTE_A_MODE = "HGV lorry"          # Road-only
ROUTE_B_MODE = "HGV lorry+ferry"    # Road + ferry mixed mode

# Installation energy for system routes (kg CO2e per m² of glass installed)
INSTALL_SYSTEM_KGCO2_PER_M2 = 0.25

DECIMALS = 3

# RepurposePreset defines the intensity preset for repurposing IGUs.
# It is used to select the appropriate CO2e per m² factor.
RepurposePreset = Literal["light", "medium", "heavy"]

GlazingType = Literal["double", "triple", "single"]
GlassType = Literal["annealed", "tempered", "laminated"]
CoatingType = Literal["none", "hard_lowE", "soft_lowE", "solar_control"]
SealantType = Literal["polysulfide", "polyurethane", "silicone", "combination", "combi"]
SpacerMaterial = Literal["aluminium", "steel", "warm_edge_composite"]
EdgeSealCondition = Literal["ok", "damaged", "unknown"]

# TransportMode defines the mode of transport for route configurations.
# "HGV lorry"       = road-only
# "HGV lorry+ferry" = HGV lorry plus ferry leg(s).
TransportMode = Literal["HGV lorry", "HGV lorry+ferry"]

# ProcessLevel indicates whether calculations are at component or system level.
ProcessLevel = Literal["component", "system"]

# SystemPath indicates the overall system path: reuse or repurpose.
SystemPath = Literal["reuse", "repurpose"]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Location:
    lat: float
    lon: float


@dataclass
class TransportModeConfig:
    """
    Transport mode configuration and distances between the three key locations:
    - origin    : project origin (Dismantling from Building / on-site removal)
    - processor : main processing site
    - reuse     : second site (reuse or repurposed installation location)
    """
    lat: float = 0.0  # unused, but kept for possible extensions


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
    route_A_mode: TransportMode = ROUTE_A_MODE  # type: ignore[assignment]
    route_B_mode: TransportMode = ROUTE_B_MODE  # type: ignore[assignment]
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
class IGUGroup:
    """
    Describes a homogeneous group of IGUs with identical geometry, build-up and condition.
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


# ============================================================================
# HELPER FUNCTIONS (project-scale aggregation and routing utilities)
# ============================================================================

def f3(x: float) -> str:
    """
    Format a float with a fixed number of decimal places (DECIMALS).
    """
    return f"{x:.{DECIMALS}f}"


def haversine_km(a: Location, b: Location) -> float:
    """
    Compute great-circle distance in km between two locations (lat/lon in degrees).
    Used to estimate straight-line distances between project origin, processor and reuse sites.
    """
    r = 6371.0
    lat1 = radians(a.lat)
    lon1 = radians(a.lon)
    lat2 = radians(b.lat)
    lon2 = radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(h), sqrt(1 - h))
    return r * c


def compute_route_distances(transport: TransportModeConfig) -> Dict[str, float]:
    """
    Compute baseline A-leg and B-leg distances (truck and ferry) between the three sites.
    Returns a dict (km) for:
      - truck_A_km / ferry_A_km : origin → processor
      - truck_B_km / ferry_B_km : processor → reuse
    """
    base_A = haversine_km(transport.origin, transport.processor)
    base_B = haversine_km(transport.processor, transport.reuse)

    if base_A <= 0:
        base_A = transport.distance_fallback_A_km
    if base_B <= 0:
        base_B = transport.distance_fallback_B_km

    truck_A = (
        transport.travel_truck_A_km_override
        if transport.travel_truck_A_km_override is not None
        else base_A
    )
    ferry_A = (
        transport.travel_ferry_A_km_override
        if transport.travel_ferry_A_km_override is not None
        else 0.0
    )
    truck_B = (
        transport.travel_truck_B_km_override
        if transport.travel_truck_B_km_override is not None
        else base_B
    )
    ferry_B = (
        transport.travel_ferry_B_km_override
        if transport.travel_ferry_B_km_override is not None
        else 0.0
    )

    return {
        "truck_A_km": truck_A,
        "ferry_A_km": ferry_A,
        "truck_B_km": truck_B,
        "ferry_B_km": ferry_B,
    }


def default_mass_per_m2(glazing_type: GlazingType) -> float:
    """
    Default surface mass per m² for IGUs, by glazing type.
    Used when mass_per_m2_override is not provided in IGUGroup.
    """
    if glazing_type == "single":
        return MASS_PER_M2_SINGLE
    if glazing_type == "double":
        return MASS_PER_M2_DOUBLE
    if glazing_type == "triple":
        return MASS_PER_M2_TRIPLE
    raise ValueError("Unsupported glazing_type")


def aggregate_igu_groups(
    groups: List[IGUGroup], processes: ProcessSettings
) -> Dict[str, float]:
    """
    Aggregate IGU groups at project/batch level.

    Returns counts and surface areas describing:
      - total_IGU_surface_area_m2 : total IGU exposed surface area on the project
      - acceptable_igus           : IGUs acceptable for reuse after visual checks and condition filters
      - acceptable_area_m2        : surface area of acceptable IGUs
      - remanufactured_igus       : IGUs that can be remanufactured (component route, pane-splitting logic)
      - remanufactured_area_m2    : corresponding surface area
    """
    total_igus = 0
    total_IGU_surface_area_m2 = 0.0
    acceptable_igus = 0

    for g in groups:
        area_per_igu = (g.unit_width_mm / 1000.0) * (g.unit_height_mm / 1000.0)
        total_igus += g.quantity
        total_IGU_surface_area_m2 += area_per_igu * g.quantity

        # Define "acceptable" IGUs for reuse (no cracks, acceptable edge seal, no fogging, reuse allowed).
        if g.condition.reuse_allowed and not g.condition.cracks_chips:
            if (
                g.condition.visible_edge_seal_condition != "damaged"
                and not g.condition.visible_fogging
            ):
                acceptable_igus += g.quantity

    # Global breakage and humidity failure applied to acceptable IGUs.
    after_breakage = acceptable_igus * (1.0 - processes.breakage_rate_global)
    after_humidity = after_breakage * (1.0 - processes.humidity_failure_rate)

    # Simple pane-count logic: single/double/triple; mixed batches are currently not supported.
    if all(g.glazing_type == "single" for g in groups):
        panes_per_igu = 1
    elif all(g.glazing_type == "double" for g in groups):
        panes_per_igu = 2
    elif all(g.glazing_type == "triple" for g in groups):
        panes_per_igu = 3
    else:
        raise ValueError("Mixed glazing types in batch are not supported.")

    total_panes = after_humidity * panes_per_igu * processes.split_yield
    remanufactured_igus_raw = floor(total_panes / panes_per_igu)
    remanufactured_igus = remanufactured_igus_raw * processes.remanufacturing_yield

    average_area_per_igu = (
        total_IGU_surface_area_m2 / total_igus if total_igus > 0 else 0.0
    )
    acceptable_area_m2 = average_area_per_igu * acceptable_igus
    remanufactured_area_m2 = average_area_per_igu * remanufactured_igus

    return {
        "total_igus": float(total_igus),
        "total_IGU_surface_area_m2": total_IGU_surface_area_m2,
        "acceptable_igus": float(acceptable_igus),
        "acceptable_area_m2": acceptable_area_m2,
        "remanufactured_igus": float(remanufactured_igus),
        "remanufactured_area_m2": remanufactured_area_m2,
        "average_area_per_igu": average_area_per_igu,
    }


def compute_igu_mass_totals(
    groups: List[IGUGroup], stats: Dict[str, float]
) -> Dict[str, float]:
    """
    Compute IGU mass totals for the project batch:
      - total_mass_kg / total_mass_t
      - acceptable_mass_kg (mass associated with acceptable_igus)
      - remanufactured_mass_kg (mass associated with remanufactured_igus)
      - avg_mass_per_igu_kg
    """
    total_mass_kg = 0.0

    for g in groups:
        area_per_igu = (g.unit_width_mm / 1000.0) * (g.unit_height_mm / 1000.0)
        m2 = area_per_igu * g.quantity
        mass_per_m2 = (
            g.mass_per_m2_override
            if g.mass_per_m2_override is not None
            else default_mass_per_m2(g.glazing_type)
        )
        total_mass_kg += m2 * mass_per_m2

    total_mass_t = total_mass_kg / 1000.0
    avg_mass_per_igu_kg = (
        total_mass_kg / stats["total_igus"] if stats["total_igus"] > 0 else 0.0
    )

    acceptable_mass_kg = avg_mass_per_igu_kg * stats["acceptable_igus"]
    remanufactured_mass_kg = avg_mass_per_igu_kg * stats["remanufactured_igus"]

    return {
        "total_mass_kg": total_mass_kg,
        "total_mass_t": total_mass_t,
        "acceptable_mass_kg": acceptable_mass_kg,
        "remanufactured_mass_kg": remanufactured_mass_kg,
        "avg_mass_per_igu_kg": avg_mass_per_igu_kg,
    }


def packaging_factor_per_igu(processes: ProcessSettings) -> float:
    """
    Compute the stillage manufacturing emission allocation per IGU (kg CO2e/IGU),
    based on stillage lifetime and IGUs per stillage. Returns 0 if stillage emissions
    are excluded or the parameters are invalid.
    """
    if not processes.include_stillage_embodied:
        return 0.0
    if processes.igus_per_stillage <= 0 or STILLAGE_LIFETIME_CYCLES <= 0:
        return 0.0
    return STILLAGE_MANUFACTURE_KGCO2 / (
        STILLAGE_LIFETIME_CYCLES * processes.igus_per_stillage
    )


# ============================================================================
# DISMANTLING & TRANSPORT TO PROCESSOR STAGE
# (Previously "Phase A" – renamed to avoid confusion with LCA Stage A)
# ============================================================================

def compute_dismantling_and_transport_to_processor_stage(
    transport: TransportModeConfig,
    processes: ProcessSettings,
    groups: List[IGUGroup],
) -> Dict[str, object]:
    """
    Compute emissions and mass/area stats for the stage:
    "Dismantling from Building & transport to processor" (A-leg).

    Includes:
      - Dismantling from Building (E_site)
      - Packaging (stillage manufacturing, if included)
      - Transport A (origin → processor, truck + optional ferry)
    """
    stats = aggregate_igu_groups(groups, processes)
    masses = compute_igu_mass_totals(groups, stats)

    n_stillages_A = (
        ceil(stats["acceptable_igus"] / processes.igus_per_stillage)
        if processes.igus_per_stillage > 0
        else 0
    )
    stillage_mass_A_kg = n_stillages_A * processes.stillage_mass_empty_kg

    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"]
    ferry_A_km = distances["ferry_A_km"]

    # Route A mode: HGV-only vs HGV lorry + ferry.
    if processes.route_A_mode == "HGV lorry":
        ferry_A_km = 0.0

    truck_A_km *= transport.backhaul_factor
    ferry_A_km *= transport.backhaul_factor

    mass_A_t = (masses["acceptable_mass_kg"] + stillage_mass_A_kg) / 1000.0

    dismantling_kgco2 = (
        stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    )

    pkg_per_igu = packaging_factor_per_igu(processes)
    packaging_kgco2 = stats["acceptable_igus"] * pkg_per_igu

    transport_A_kgco2 = mass_A_t * (
        truck_A_km * transport.emissionfactor_truck
        + ferry_A_km * transport.emissionfactor_ferry
    )

    return {
        "stats": stats,
        "masses": masses,
        "n_stillages_A": n_stillages_A,
        "stillage_mass_A_kg": stillage_mass_A_kg,
        "truck_A_km_eff": truck_A_km,
        "ferry_A_km_eff": ferry_A_km,
        "mass_A_t": mass_A_t,
        "dismantling_kgco2": dismantling_kgco2,
        "packaging_kgco2": packaging_kgco2,
        "transport_A_kgco2": transport_A_kgco2,
        "packaging_per_igu": pkg_per_igu,
    }


# ============================================================================
# SYSTEM ROUTE – B-LEG TRANSPORT (PROCESSOR → REUSE / REPURPOSED SITE)
# ============================================================================

def compute_system_transport_B(
    transport: TransportModeConfig,
    processes: ProcessSettings,
    stats: Dict[str, float],
    masses: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute emissions and mass/transport stats for the B-leg:
    processor → reuse/repurposed destination.
    """
    if processes.igus_per_stillage > 0:
        n_stillages_B = ceil(
            stats["acceptable_igus"] / processes.igus_per_stillage
        )
    else:
        n_stillages_B = 0

    stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

    distances = compute_route_distances(transport)
    truck_B_km = distances["truck_B_km"]
    ferry_B_km = distances["ferry_B_km"]

    # Route B mode: HGV-only vs HGV lorry + ferry.
    if processes.route_B_mode == "HGV lorry":
        ferry_B_km = 0.0

    truck_B_km *= transport.backhaul_factor
    ferry_B_km *= transport.backhaul_factor

    mass_B_t = (masses["acceptable_mass_kg"] + stillage_mass_B_kg) / 1000.0

    transport_B_kgco2 = mass_B_t * (
        truck_B_km * transport.emissionfactor_truck
        + ferry_B_km * transport.emissionfactor_ferry
    )

    return {
        "transport_B_kgco2": transport_B_kgco2,
        "truck_B_km_eff": truck_B_km,
        "ferry_B_km_eff": ferry_B_km,
        "mass_B_t": mass_B_t,
        "n_stillages_B": float(n_stillages_B),
        "stillage_mass_B_kg": stillage_mass_B_kg,
    }


# ============================================================================
# FULL CHAIN (kept for later development; not used in main flow yet)
# ============================================================================

def compute_full_chain_emissions(batch: BatchInput) -> EmissionBreakdown:
    """
    Compute a full-chain emission breakdown (Dismantling from Building
    → processor → second site), for possible future integration.
    """
    stats = aggregate_igu_groups(batch.igu_groups, batch.processes)
    masses = compute_igu_mass_totals(batch.igu_groups, stats)

    n_stillages_A = (
        ceil(stats["acceptable_igus"] / batch.processes.igus_per_stillage)
        if batch.processes.igus_per_stillage > 0
        else 0
    )

    if batch.processes.igus_per_stillage > 0:
        if batch.processes.process_level == "component":
            n_stillages_B = ceil(
                stats["remanufactured_igus"] / batch.processes.igus_per_stillage
            )
        else:
            n_stillages_B = ceil(
                stats["acceptable_igus"] / batch.processes.igus_per_stillage
            )
    else:
        n_stillages_B = 0

    stillage_mass_A_kg = n_stillages_A * batch.processes.stillage_mass_empty_kg
    stillage_mass_B_kg = n_stillages_B * batch.processes.stillage_mass_empty_kg

    dismantling_kgco2 = (
        stats["total_IGU_surface_area_m2"] * batch.processes.e_site_kgco2_per_m2
    )

    pkg_per_igu = packaging_factor_per_igu(batch.processes)
    packaging_kgco2 = stats["acceptable_igus"] * pkg_per_igu

    distances = compute_route_distances(batch.transport)
    truck_A_km = distances["truck_A_km"]
    ferry_A_km = distances["ferry_A_km"]
    truck_B_km = distances["truck_B_km"]
    ferry_B_km = distances["ferry_B_km"]

    if batch.processes.route_A_mode == "HGV lorry":
        ferry_A_km = 0.0
    if batch.processes.route_B_mode == "HGV lorry":
        ferry_B_km = 0.0

    truck_A_km *= batch.transport.backhaul_factor
    ferry_A_km *= batch.transport.backhaul_factor
    truck_B_km *= batch.transport.backhaul_factor
    ferry_B_km *= batch.transport.backhaul_factor

    mass_A_t = (masses["acceptable_mass_kg"] + stillage_mass_A_kg) / 1000.0

    if batch.processes.process_level == "component":
        mass_B_t = (masses["remanufactured_mass_kg"] + stillage_mass_B_kg) / 1000.0
    else:
        mass_B_t = (masses["acceptable_mass_kg"] + stillage_mass_B_kg) / 1000.0

    transport_A_kgco2 = mass_A_t * (
        truck_A_km * batch.transport.emissionfactor_truck
        + ferry_A_km * batch.transport.emissionfactor_ferry
    )
    transport_B_kgco2 = mass_B_t * (
        truck_B_km * batch.transport.emissionfactor_truck
        + ferry_B_km * batch.transport.emissionfactor_ferry
    )

    disassembly_kgco2 = 0.0
    if batch.processes.process_level == "system":
        disassembly_kgco2 = stats["acceptable_area_m2"] * DISASSEMBLY_KGCO2_PER_M2

    remanufacturing_kgco2 = 0.0
    if batch.processes.process_level == "component":
        remanufacturing_kgco2 = (
            stats["remanufactured_area_m2"] * REMANUFACTURING_KGCO2_PER_M2
        )
    elif batch.processes.process_level == "system":
        if batch.processes.system_path == "reuse":
            remanufacturing_kgco2 = 0.0
        elif batch.processes.system_path == "repurpose":
            repurpose_area_m2 = stats["acceptable_area_m2"]
            remanufacturing_kgco2 = (
                repurpose_area_m2 * batch.processes.repurpose_kgco2_per_m2
            )

    quality_control_kgco2 = 0.0

    total_kgco2 = (
        dismantling_kgco2
        + packaging_kgco2
        + transport_A_kgco2
        + disassembly_kgco2
        + remanufacturing_kgco2
        + quality_control_kgco2
        + transport_B_kgco2
    )

    extra: Dict[str, float] = {}
    extra.update(stats)
    extra.update(masses)
    extra["n_stillages_A"] = float(n_stillages_A)
    extra["n_stillages_B"] = float(n_stillages_B)
    extra["truck_A_km_effective"] = truck_A_km
    extra["ferry_A_km_effective"] = ferry_A_km
    extra["truck_B_km_effective"] = truck_B_km
    extra["ferry_B_km_effective"] = ferry_B_km
    extra["mass_A_t"] = mass_A_t
    extra["mass_B_t"] = mass_B_t
    extra["disassembly_kgco2"] = disassembly_kgco2
    extra["process_level"] = batch.processes.process_level  # type: ignore[assignment]
    extra["system_path"] = batch.processes.system_path      # type: ignore[assignment]
    extra["packaging_per_igu_kgco2"] = pkg_per_igu
    extra["repurpose_preset"] = batch.processes.repurpose_preset  # type: ignore[assignment]
    extra["repurpose_kgco2_per_m2"] = batch.processes.repurpose_kgco2_per_m2

    return EmissionBreakdown(
        dismantling_from_building_kgco2=dismantling_kgco2,
        packaging_kgco2=packaging_kgco2,
        transport_A_kgco2=transport_A_kgco2,
        disassembly_kgco2=disassembly_kgco2,
        remanufacturing_kgco2=remanufacturing_kgco2,
        quality_control_kgco2=quality_control_kgco2,
        transport_B_kgco2=transport_B_kgco2,
        total_kgco2=total_kgco2,
        extra=extra,
    )


# ============================================================================
# GEOCODING AND INPUT HELPERS
# ============================================================================

def geocode_address(address: str) -> Optional[Location]:
    """
    Geocode a free-text address to a Location (lat/lon) using Nominatim/OSM.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": GEOCODER_USER_AGENT}
    try:
        print(f"Geocoding '{address}' ...")
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"Geocoder HTTP status: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        if not data:
            print("No geocoding results returned.")
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return Location(lat=lat, lon=lon)
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None


def try_parse_lat_lon(text: str) -> Optional[Location]:
    """
    Try to parse 'lat,lon' text into a Location.
    """
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        return Location(lat=lat, lon=lon)
    except ValueError:
        return None


def prompt_location(label: str) -> Location:
    """
    Prompt user for either a free-text address or a 'lat,lon' pair and return a Location.
    """
    while True:
        s = input(f"Enter {label} address or 'lat,lon': ").strip()
        if not s:
            continue
        loc = try_parse_lat_lon(s)
        if loc is not None:
            print(f"{label} set to {loc.lat:.6f}, {loc.lon:.6f} (manual lat,lon)")
            return loc
        loc = geocode_address(s)
        if loc is not None:
            print(f"{label} geocoded to {loc.lat:.6f}, {loc.lon:.6f}")
            return loc
        print("Could not geocode input. Try again with another address or 'lat,lon'.")


def prompt_choice(label: str, options: List[str], default: str) -> str:
    """
    Prompt user to pick one value from a list of options; returns the chosen option.
    """
    opts_str = "/".join(options)
    while True:
        s = input(f"{label} [{opts_str}] (default={default}): ").strip().lower()
        if not s:
            return default
        for opt in options:
            if s == opt.lower():
                return opt
        print(f"Invalid choice. Please choose one of: {opts_str}")


def prompt_yes_no(label: str, default: bool) -> bool:
    """
    Prompt user for yes/no answer, returning True/False.
    """
    d = "y" if default else "n"
    while True:
        s = input(f"{label} [y/n] (default={d}): ").strip().lower()
        if not s:
            return default
        if s in ("y", "yes"):
            return True
        if s in ("n", "no"):
            return False
        print("Please answer y or n.")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("IGU recovery environmental impact prototype\n")

    print("First, provide the key locations.\n")
    origin = prompt_location("project origin (Dismantling from Building / on-site removal)")
    processor = prompt_location("processor location (main processing site)")

    transport = TransportModeConfig(origin=origin, processor=processor, reuse=processor)

    print("\nLocations used:")
    print(f"  Origin   : {origin.lat:.6f}, {origin.lon:.6f}")
    print(f"  Processor: {processor.lat:.6f}, {processor.lon:.6f}\n")

    processes = ProcessSettings()

    # Allow the user to configure different modes for A-leg and B-leg.
    route_A_mode_str = prompt_choice(
        "Route A transport mode (origin → processor)",
        ["HGV lorry", "HGV lorry+ferry"],
        default=ROUTE_A_MODE,
    )
    route_B_mode_str = prompt_choice(
        "Route B transport mode (processor → second site)",
        ["HGV lorry", "HGV lorry+ferry"],
        default=ROUTE_B_MODE,
    )
    processes.route_A_mode = route_A_mode_str  # type: ignore[assignment]
    processes.route_B_mode = route_B_mode_str  # type: ignore[assignment]

    print("Now describe the IGU batch.\n")
    total_igus_str = input("Total number of IGUs in this batch: ").strip()
    width_str = input("Width of each IGU in mm (unit_width_mm): ").strip()
    height_str = input("Height of each IGU in mm (unit_height_mm): ").strip()

    try:
        total_igus = int(total_igus_str)
        unit_width_mm = float(width_str)
        unit_height_mm = float(height_str)
    except ValueError:
        print("Invalid numeric input for IGU count or dimensions.")
        raise SystemExit(1)

    glazing_type_str = prompt_choice(
        "Glazing type", ["double", "triple", "single"], default="double"
    )
    glass_outer_str = prompt_choice(
        "Outer glass type", ["annealed", "tempered", "laminated"], default="annealed"
    )
    glass_inner_str = prompt_choice(
        "Inner glass type", ["annealed", "tempered", "laminated"], default="annealed"
    )
    coating_str = prompt_choice(
        "Coating type",
        ["none", "hard_lowE", "soft_lowE", "solar_control"],
        default="none",
    )
    sealant_str = prompt_choice(
        "Secondary sealant type",
        ["polysulfide", "polyurethane", "silicone", "combination", "combi"],
        default="polysulfide",
    )
    spacer_str = prompt_choice(
        "Spacer material",
        ["aluminium", "steel", "warm_edge_composite"],
        default="aluminium",
    )

    if glazing_type_str == "single":
        pane_th_str = input("Pane thickness (mm): ").strip()
        try:
            pane_thickness_single_mm = float(pane_th_str)
        except ValueError:
            print("Invalid numeric input for pane thickness.")
            raise SystemExit(1)

        pane_thickness_outer_mm = pane_thickness_single_mm
        pane_thickness_inner_mm = 0.0
        cavity_thickness_1_mm = 0.0
        thickness_centre_mm: Optional[float] = None
        cavity_thickness_2_mm: Optional[float] = None
        IGU_depth_mm_val = pane_thickness_single_mm

    elif glazing_type_str == "double":
        outer_th_str = input("Outer pane thickness (mm): ").strip()
        inner_th_str = input("Inner pane thickness (mm): ").strip()
        cavity1_str = input("Cavity thickness (mm): ").strip()
        try:
            pane_thickness_outer_mm = float(outer_th_str)
            pane_thickness_inner_mm = float(inner_th_str)
            cavity_thickness_1_mm = float(cavity1_str)
        except ValueError:
            print("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        thickness_centre_mm = None
        cavity_thickness_2_mm = None
        IGU_depth_mm_val = (
            pane_thickness_outer_mm + cavity_thickness_1_mm + pane_thickness_inner_mm
        )

    else:  # glazing_type_str == "triple"
        outer_th_str = input("Outer pane thickness (mm): ").strip()
        middle_th_str = input("Centre pane thickness (mm): ").strip()
        inner_th_str = input("Inner pane thickness (mm): ").strip()
        cavity1_str = input("First cavity thickness (mm): ").strip()
        cavity2_str = input("Second cavity thickness (mm): ").strip()
        try:
            pane_thickness_outer_mm = float(outer_th_str)
            thickness_centre_mm = float(middle_th_str)
            pane_thickness_inner_mm = float(inner_th_str)
            cavity_thickness_1_mm = float(cavity1_str)
            cavity_thickness_2_mm = float(cavity2_str)
        except ValueError:
            print("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        IGU_depth_mm_val = (
            pane_thickness_outer_mm
            + cavity_thickness_1_mm
            + thickness_centre_mm
            + cavity_thickness_2_mm
            + pane_thickness_inner_mm
        )

    edge_cond_str = prompt_choice(
        "Visible edge seal condition", ["ok", "damaged", "unknown"], default="ok"
    )
    fogging = prompt_yes_no("Visible fogging?", default=False)
    cracks = prompt_yes_no("Cracks or chips present?", default=False)
    reuse_allowed = prompt_yes_no("Reuse allowed by owner/regulations?", default=True)

    age_str = input("Approximate age of IGUs in years (default=20): ").strip()
    try:
        age_years = float(age_str) if age_str else 20.0
    except ValueError:
        age_years = 20.0

    condition = IGUCondition(
        visible_edge_seal_condition=edge_cond_str,  # type: ignore[arg-type]
        visible_fogging=fogging,
        cracks_chips=cracks,
        age_years=age_years,
        reuse_allowed=reuse_allowed,
    )

    group = IGUGroup(
        quantity=total_igus,
        unit_width_mm=unit_width_mm,
        unit_height_mm=unit_height_mm,
        glazing_type=glazing_type_str,  # type: ignore[arg-type]
        glass_type_outer=glass_outer_str,  # type: ignore[arg-type]
        glass_type_inner=glass_inner_str,  # type: ignore[arg-type]
        coating_type=coating_str,  # type: ignore[arg-type]
        sealant_type_secondary=sealant_str,  # type: ignore[arg-type]
        spacer_material=spacer_str,  # type: ignore[arg-type]
        interlayer_type=None,
        condition=condition,
        thickness_outer_mm=pane_thickness_outer_mm,
        thickness_inner_mm=pane_thickness_inner_mm,
        cavity_thickness_mm=cavity_thickness_1_mm,
        IGU_depth_mm=IGU_depth_mm_val,
        mass_per_m2_override=None,
        thickness_centre_mm=thickness_centre_mm,
        cavity_thickness_2_mm=cavity_thickness_2_mm,
    )

    stats_initial = aggregate_igu_groups([group], processes)
    total_IGU_surface_area_m2_initial = stats_initial["total_IGU_surface_area_m2"]

    e_site_str = input(
        f"\nDismantling from Building factor E_site (kg CO2e/m² glass) "
        f"(press Enter for {E_SITE_KGCO2_PER_M2}): "
    ).strip()
    if e_site_str:
        try:
            processes.e_site_kgco2_per_m2 = float(e_site_str)
        except ValueError:
            print("Invalid E_site value, keeping default.")

    dismantling_only_kgco2 = (
        total_IGU_surface_area_m2_initial * processes.e_site_kgco2_per_m2
    )
    print(
        f"\nEstimated 'Dismantling from Building' emissions for IGU removal: "
        f"{f3(dismantling_only_kgco2)} kg CO2e"
    )

    include_stillage = prompt_yes_no(
        "\nInclude stillage manufacturing emissions?",
        default=INCLUDE_STILLAGE_EMBODIED,
    )
    processes.include_stillage_embodied = include_stillage

    print("\nSelect HGV lorry emission factor preset:")
    print("  eu_legacy    = 0.06 kgCO2e/tkm  (older diesel HGV lorries)")
    print("  eu_current   = 0.04 kgCO2e/tkm  (current EU average HGV lorry)")
    print("  best_diesel  = 0.03 kgCO2e/tkm  (best-in-class diesel HGV lorry)")
    print("  ze_truck     = 0.0075 kgCO2e/tkm (electric HGV lorry, grid mix)")

    truck_preset = prompt_choice(
        "HGV lorry emission preset",
        ["eu_legacy", "eu_current", "best_diesel", "ze_truck"],
        default="eu_current",
    )

    if truck_preset == "eu_legacy":
        transport.emissionfactor_truck = 0.06
    elif truck_preset == "eu_current":
        transport.emissionfactor_truck = 0.04
    elif truck_preset == "best_diesel":
        transport.emissionfactor_truck = 0.03
    elif truck_preset == "ze_truck":
        transport.emissionfactor_truck = 0.0075

    transport.emissionfactor_ferry = EMISSIONFACTOR_FERRY

    print(
        f"\nUsing HGV lorry emission factor: {transport.emissionfactor_truck} kg CO2e/tkm "
        f"(preset: {truck_preset})"
    )
    print(
        f"Using ferry emission factor: {transport.emissionfactor_ferry} kg CO2e/tkm\n"
    )

    print("Select observed breakage rate during Dismantling from Building.")
    print("  very_low = 0.5% of IGUs")
    print("  low      = 1% of IGUs")
    print("  medium   = 3% of IGUs")
    print("  high     = 5% of IGUs")

    breakage_preset = prompt_choice(
        "Breakage rate preset",
        ["very_low", "low", "medium", "high"],
        default="very_low",
    )

    if breakage_preset == "very_low":
        processes.breakage_rate_global = 0.005
    elif breakage_preset == "low":
        processes.breakage_rate_global = 0.01
    elif breakage_preset == "medium":
        processes.breakage_rate_global = 0.03
    elif breakage_preset == "high":
        processes.breakage_rate_global = 0.05

    print(
        f"Using breakage rate: {processes.breakage_rate_global * 100:.2f}% "
        "of acceptable IGUs\n"
    )

    stage_ctp = compute_dismantling_and_transport_to_processor_stage(
        transport, processes, [group]
    )
    stats_ctp = stage_ctp["stats"]   # type: ignore[assignment]
    masses_ctp = stage_ctp["masses"] # type: ignore[assignment]

    print("=== Dismantling from Building & transport to processor stage ===")
    print(f"  Dismantling from Building : {f3(stage_ctp['dismantling_kgco2'])} kg CO2e")
    print(f"  Packaging                 : {f3(stage_ctp['packaging_kgco2'])} kg CO2e")
    print(f"  Transport A (to processor): {f3(stage_ctp['transport_A_kgco2'])} kg CO2e")
    print(
        f"  Packaging factor          : {f3(stage_ctp['packaging_per_igu'])} "
        "kg CO2e / IGU (stillage manufacturing)"
    )

    print("\nDismantling & transport to processor – key stats:")
    print(f"  Total IGUs (input)             : {int(stats_ctp['total_igus'])}")
    print(f"  Acceptable IGUs                : {int(stats_ctp['acceptable_igus'])}")
    print(f"  Total IGU surface area         : {f3(stats_ctp['total_IGU_surface_area_m2'])} m²")
    print(f"  Acceptable IGU surface area    : {f3(stats_ctp['acceptable_area_m2'])} m²")
    print(f"  Average area per IGU           : {f3(stats_ctp['average_area_per_igu'])} m²")
    print(f"  Avg mass per IGU               : {f3(masses_ctp['avg_mass_per_igu_kg'])} kg")
    print(f"  HGV lorry distance A (eff.)    : {f3(stage_ctp['truck_A_km_eff'])} km")
    print(f"  Mass on HGV lorry A            : {f3(stage_ctp['mass_A_t'])} t\n")

    print("Next, select the processing route after the processor.\n")
    route_choice = prompt_choice(
        "Processing route", ["system", "component"], default="system"
    )

    if route_choice == "component":
        print(
            "Component route will be detailed in a later step. "
            "Calculation ends after the Dismantling & transport to processor stage."
        )
        raise SystemExit(0)

    processes.process_level = "system"

    system_option = prompt_choice(
        "System route option", ["reuse", "repurpose"], default="reuse"
    )

    if system_option == "reuse":
        processes.system_path = "reuse"  # type: ignore[assignment]

        print("\nSystem route: REUSE selected.\n")
        print("Overview of the modelled IGU batch:")
        print(f"  Quantity              : {group.quantity}")
        print(f"  Dimensions (mm)       : {group.unit_width_mm} x {group.unit_height_mm}")
        print(f"  Glazing type          : {group.glazing_type}")
        print(f"  Glass outer / inner   : {group.glass_type_outer} / {group.glass_type_inner}")
        print(f"  Coating type          : {group.coating_type}")
        print(f"  Spacer material       : {group.spacer_material}")
        print(f"  Approx. age (years)   : {group.condition.age_years}")
        print(f"  IGU depth (mm)        : {group.IGU_depth_mm}")
        print(f"  Acceptable IGUs       : {int(stats_ctp['acceptable_igus'])}")
        print(f"  Acceptable area       : {f3(stats_ctp['acceptable_area_m2'])} m²")
        print(f"  Breakage rate used    : {processes.breakage_rate_global * 100:.2f}%")
        print(
            f"  E_site (Dismantling)  : {processes.e_site_kgco2_per_m2} kg CO2e/m²\n"
        )

        confirm_reuse = prompt_yes_no(
            "Proceed with system REUSE for this IGU batch?", default=True
        )
        if not confirm_reuse:
            print(
                "System reuse not confirmed. Calculation ends after the "
                "Dismantling & transport to processor stage."
            )
            raise SystemExit(0)

        print("\nProvide the location where the IGUs will be reused.\n")
        reuse_location = prompt_location("reuse destination (system reuse)")
        transport.reuse = reuse_location

        print("\nUpdated reuse destination:")
        print(f"  Reuse location: {reuse_location.lat:.6f}, {reuse_location.lon:.6f}\n")

        system_B = compute_system_transport_B(transport, processes, stats_ctp, masses_ctp)

        print("=== System route – transport to reuse destination (B-leg) ===")
        print(f"  HGV lorry distance B (eff.) : {f3(system_B['truck_B_km_eff'])} km")
        print(f"  Mass on HGV lorry B         : {f3(system_B['mass_B_t'])} t")
        print(f"  Transport B                 : {f3(system_B['transport_B_kgco2'])} kg CO2e")
        print(f"  Stillages B (count)         : {int(system_B['n_stillages_B'])}")
        print(f"  Stillage mass B             : {f3(system_B['stillage_mass_B_kg'])} kg\n")

        install_factor = INSTALL_SYSTEM_KGCO2_PER_M2
        install_str = input(
            f"Installation factor E_install (kg CO2e/m² of glass installed) "
            f"(press Enter for {INSTALL_SYSTEM_KGCO2_PER_M2}): "
        ).strip()
        if install_str:
            try:
                install_factor = float(install_str)
            except ValueError:
                print("Invalid E_install value, keeping default.")

        install_kgco2 = stats_ctp["acceptable_area_m2"] * install_factor

        print(
            f"\nEstimated emissions for installation of IGUs into the new frame: "
            f"{f3(install_kgco2)} kg CO2e"
        )

        total_system_reuse_kgco2 = (
            stage_ctp["dismantling_kgco2"]
            + stage_ctp["packaging_kgco2"]
            + stage_ctp["transport_A_kgco2"]
            + system_B["transport_B_kgco2"]
            + install_kgco2
        )

        print("\n=== Combined results – System REUSE pathway ===")
        print(f"  Dismantling from Building : {f3(stage_ctp['dismantling_kgco2'])} kg CO2e")
        print(f"  Packaging                 : {f3(stage_ctp['packaging_kgco2'])} kg CO2e")
        print(f"  Transport A               : {f3(stage_ctp['transport_A_kgco2'])} kg CO2e")
        print(f"  Transport B (reuse)       : {f3(system_B['transport_B_kgco2'])} kg CO2e")
        print(f"  Installation              : {f3(install_kgco2)} kg CO2e")
        print(f"  Total (system reuse)      : {f3(total_system_reuse_kgco2)} kg CO2e\n")

    else:  # system_option == "repurpose"
        processes.system_path = "repurpose"  # type: ignore[assignment]

        print("\nSystem route: REPURPOSE selected.\n")
        print("Overview of the modelled IGU batch for repurposing:")
        print(f"  Quantity              : {group.quantity}")
        print(f"  Dimensions (mm)       : {group.unit_width_mm} x {group.unit_height_mm}")
        print(f"  Glazing type          : {group.glazing_type}")
        print(f"  Glass outer / inner   : {group.glass_type_outer} / {group.glass_type_inner}")
        print(f"  Coating type          : {group.coating_type}")
        print(f"  Spacer material       : {group.spacer_material}")
        print(f"  Approx. age (years)   : {group.condition.age_years}")
        print(f"  IGU depth (mm)        : {group.IGU_depth_mm}")
        print(f"  Acceptable IGUs       : {int(stats_ctp['acceptable_igus'])}")
        print(f"  Acceptable area       : {f3(stats_ctp['acceptable_area_m2'])} m²\n")

        confirm_repurpose = prompt_yes_no(
            "Proceed with system REPURPOSE for this IGU batch?", default=True
        )
        if not confirm_repurpose:
            print(
                "System repurpose not confirmed. Calculation ends after the "
                "Dismantling & transport to processor stage."
            )
            raise SystemExit(0)

        re_adapt = prompt_yes_no(
            "Is re-adaptation required (cutting, drilling, tempering, etc.)?",
            default=True,
        )

        repurpose_kgco2 = 0.0
        repurpose_intensity = "none"

        if re_adapt:
            print("\nSelect repurposing intensity preset (kg CO2e per m² of glass processed):")
            print("  light  = low-intervention (cleaning, minor repairs, fittings)")
            print("  medium = moderate rework (cutting, edge finishing, some drilling)")
            print("  heavy  = intensive rework (e.g. tempering, fritting, major adaptation)")

            repurpose_preset_str = prompt_choice(
                "Repurposing intensity", ["light", "medium", "heavy"], default="medium"
            )

            if repurpose_preset_str == "light":
                processes.repurpose_kgco2_per_m2 = REPURPOSE_LIGHT_KGCO2_PER_M2
            elif repurpose_preset_str == "medium":
                processes.repurpose_kgco2_per_m2 = REPURPOSE_MEDIUM_KGCO2_PER_M2
            elif repurpose_preset_str == "heavy":
                processes.repurpose_kgco2_per_m2 = REPURPOSE_HEAVY_KGCO2_PER_M2

            processes.repurpose_preset = repurpose_preset_str  # type: ignore[assignment]
            repurpose_intensity = repurpose_preset_str

            repurpose_kgco2 = (
                stats_ctp["acceptable_area_m2"] * processes.repurpose_kgco2_per_m2
            )

            print(
                f"\nEstimated repurposing emissions "
                f"({repurpose_intensity}, {processes.repurpose_kgco2_per_m2} kg CO2e/m²): "
                f"{f3(repurpose_kgco2)} kg CO2e"
            )
        else:
            print("\nNo re-adaptation selected. Repurposing process emissions set to 0 kg CO2e.")

        print("\nProvide the location where the repurposed IGU system will be installed.\n")
        repurpose_location = prompt_location("repurposed system destination")
        transport.reuse = repurpose_location

        print("\nUpdated repurposed destination:")
        print(f"  Repurpose location: {repurpose_location.lat:.6f}, {repurpose_location.lon:.6f}\n")

        system_B = compute_system_transport_B(transport, processes, stats_ctp, masses_ctp)

        print("=== System route – transport to repurposed destination (B-leg) ===")
        print(f"  HGV lorry distance B (eff.) : {f3(system_B['truck_B_km_eff'])} km")
        print(f"  Mass on HGV lorry B         : {f3(system_B['mass_B_t'])} t")
        print(f"  Transport B                 : {f3(system_B['transport_B_kgco2'])} kg CO2e")
        print(f"  Stillages B (count)         : {int(system_B['n_stillages_B'])}")
        print(f"  Stillage mass B             : {f3(system_B['stillage_mass_B_kg'])} kg\n")

        install_factor = INSTALL_SYSTEM_KGCO2_PER_M2
        install_str = input(
            f"Installation factor E_install (kg CO2e/m² of glass installed) "
            f"(press Enter for {INSTALL_SYSTEM_KGCO2_PER_M2}): "
        ).strip()
        if install_str:
            try:
                install_factor = float(install_str)
            except ValueError:
                print("Invalid E_install value, keeping default.")

        install_kgco2 = stats_ctp["acceptable_area_m2"] * install_factor

        print(
            f"\nEstimated emissions for installation of the repurposed IGU system: "
            f"{f3(install_kgco2)} kg CO2e"
        )

        total_system_repurpose_kgco2 = (
            stage_ctp["dismantling_kgco2"]
            + stage_ctp["packaging_kgco2"]
            + stage_ctp["transport_A_kgco2"]
            + repurpose_kgco2
            + system_B["transport_B_kgco2"]
            + install_kgco2
        )

        print("\n=== Combined results – System REPURPOSE pathway ===")
        print(f"  Dismantling from Building   : {f3(stage_ctp['dismantling_kgco2'])} kg CO2e")
        print(f"  Packaging                   : {f3(stage_ctp['packaging_kgco2'])} kg CO2e")
        print(f"  Transport A                 : {f3(stage_ctp['transport_A_kgco2'])} kg CO2e")
        print(f"  Repurposing                 : {f3(repurpose_kgco2)} kg CO2e")
        print(f"  Transport B (repurpose)     : {f3(system_B['transport_B_kgco2'])} kg CO2e")
        print(f"  Installation                : {f3(install_kgco2)} kg CO2e")
        print(f"  Total (system repurpose)    : {f3(total_system_repurpose_kgco2)} kg CO2e\n")
