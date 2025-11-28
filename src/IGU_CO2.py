from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2, ceil, floor
from typing import List, Optional, Literal, Dict
import requests

# ============================================================================
# SETTINGS
# ============================================================================

GEOCODER_USER_AGENT = "igu-reuse-tool/0.1 (CHANGE_THIS_TO_YOUR_EMAIL@DOMAIN)"

E_SITE_KGCO2_PER_M2 = 0.15

REMANUFACTURING_KGCO2_PER_M2 = 7.5
DISASSEMBLY_KGCO2_PER_M2 = 0.5

REPURPOSE_LIGHT_KGCO2_PER_M2 = 0.5
REPURPOSE_MEDIUM_KGCO2_PER_M2 = 1.0
REPURPOSE_HEAVY_KGCO2_PER_M2 = 2.0

STILLAGE_MANUFACTURE_KGCO2 = 500.0
STILLAGE_LIFETIME_CYCLES = 100
INCLUDE_STILLAGE_EMBODIED = False

EMISSIONFACTOR_TRUCK = 0.04
EMISSIONFACTOR_FERRY = 0.045

BACKHAUL_FACTOR = 1.3

TRUCK_CAPACITY_T = 20.0
FERRY_CAPACITY_T = 1000.0

DISTANCE_FALLBACK_A_KM = 100.0
DISTANCE_FALLBACK_B_KM = 100.0

MASS_PER_M2_DOUBLE = 20.0
MASS_PER_M2_TRIPLE = 30.0

BREAKAGE_RATE_GLOBAL = 0.05
HUMIDITY_FAILURE_RATE = 0.05
SPLIT_YIELD = 0.95
REMANUFACTURING_YIELD = 0.90

IGUS_PER_STILLAGE = 20
STILLAGE_MASS_EMPTY_KG = 300.0
MAX_TRUCK_LOAD_KG = 20000.0

ROUTE_A_MODE = "truck_only"
ROUTE_B_MODE = "truck_only"

DECIMALS = 3

# ============================================================================
# TYPE ALIASES
# ============================================================================

GlazingType = Literal["double", "triple"]
GlassType = Literal["annealed", "tempered", "laminated"]
CoatingType = Literal["none", "hard_lowE", "soft_lowE", "solar_control"]
SealantType = Literal["polysulfide", "polyurethane", "silicone"]
SpacerMaterial = Literal["aluminium", "steel", "warm_edge_composite"]
EdgeSealCondition = Literal["ok", "damaged", "unknown"]
RouteMode = Literal["truck_only", "truck+ferry"]
ProcessLevel = Literal["component", "system"]
SystemPath = Literal["reuse", "repurpose"]
RepurposePreset = Literal["light", "medium", "heavy"]

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Location:
    lat: float
    lon: float


@dataclass
class RouteConfig:
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
    breakage_rate_global: float = BREAKAGE_RATE_GLOBAL
    humidity_failure_rate: float = HUMIDITY_FAILURE_RATE
    split_yield: float = SPLIT_YIELD
    remanufacturing_yield: float = REMANUFACTURING_YIELD
    route_A_mode: RouteMode = ROUTE_A_MODE  # type: ignore[assignment]
    route_B_mode: RouteMode = ROUTE_B_MODE  # type: ignore[assignment]
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
    quantity: int
    width_mm: float
    height_mm: float
    glazing_type: GlazingType
    glass_type_outer: GlassType
    glass_type_inner: GlassType
    coating_type: CoatingType
    sealant_type_secondary: SealantType
    spacer_material: SpacerMaterial
    interlayer_type: Optional[str]
    condition: IGUCondition
    pane_thickness_outer_mm: float
    pane_thickness_inner_mm: float
    cavity_thickness_1_mm: float
    mass_per_m2_override: Optional[float] = None
    pane_thickness_middle_mm: Optional[float] = None
    cavity_thickness_2_mm: Optional[float] = None


@dataclass
class BatchInput:
    route: RouteConfig
    processes: ProcessSettings
    igu_groups: List[IGUGroup]


@dataclass
class EmissionBreakdown:
    on_site_dismantling_kgco2: float
    packaging_kgco2: float
    transport_A_kgco2: float
    disassembly_kgco2: float
    remanufacturing_kgco2: float
    quality_control_kgco2: float
    transport_B_kgco2: float
    total_kgco2: float
    extra: Dict[str, float]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def f3(x: float) -> str:
    return f"{x:.{DECIMALS}f}"


def haversine_km(a: Location, b: Location) -> float:
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


def compute_route_distances(route: RouteConfig) -> Dict[str, float]:
    base_A = haversine_km(route.origin, route.processor)
    base_B = haversine_km(route.processor, route.reuse)

    if base_A <= 0:
        base_A = route.distance_fallback_A_km
    if base_B <= 0:
        base_B = route.distance_fallback_B_km

    truck_A = (
        route.travel_truck_A_km_override
        if route.travel_truck_A_km_override is not None
        else base_A
    )
    ferry_A = (
        route.travel_ferry_A_km_override
        if route.travel_ferry_A_km_override is not None
        else 0.0
    )
    truck_B = (
        route.travel_truck_B_km_override
        if route.travel_truck_B_km_override is not None
        else base_B
    )
    ferry_B = (
        route.travel_ferry_B_km_override
        if route.travel_ferry_B_km_override is not None
        else 0.0
    )

    return {
        "truck_A_km": truck_A,
        "ferry_A_km": ferry_A,
        "truck_B_km": truck_B,
        "ferry_B_km": ferry_B,
    }


def default_mass_per_m2(glazing_type: GlazingType) -> float:
    if glazing_type == "double":
        return MASS_PER_M2_DOUBLE
    if glazing_type == "triple":
        return MASS_PER_M2_TRIPLE
    raise ValueError("Unsupported glazing_type")


def aggregate_igu_groups(
    groups: List[IGUGroup], processes: ProcessSettings
) -> Dict[str, float]:
    total_igus = 0
    total_area_m2 = 0.0
    eligible_igus = 0

    for g in groups:
        area_per_igu = (g.width_mm / 1000.0) * (g.height_mm / 1000.0)
        total_igus += g.quantity
        total_area_m2 += area_per_igu * g.quantity

        if g.condition.reuse_allowed and not g.condition.cracks_chips:
            if (
                g.condition.visible_edge_seal_condition != "damaged"
                and not g.condition.visible_fogging
            ):
                eligible_igus += g.quantity

    after_breakage = eligible_igus * (1.0 - processes.breakage_rate_global)
    after_humidity = after_breakage * (1.0 - processes.humidity_failure_rate)

    panes_per_igu = 2 if all(g.glazing_type == "double" for g in groups) else 3
    total_panes = after_humidity * panes_per_igu * processes.split_yield
    remanufactured_igus_raw = floor(total_panes / panes_per_igu)
    remanufactured_igus = remanufactured_igus_raw * processes.remanufacturing_yield

    average_area_per_igu = total_area_m2 / total_igus if total_igus > 0 else 0.0
    eligible_area_m2 = average_area_per_igu * eligible_igus
    remanufactured_area_m2 = average_area_per_igu * remanufactured_igus

    return {
        "total_igus": float(total_igus),
        "total_area_m2": total_area_m2,
        "eligible_igus": float(eligible_igus),
        "eligible_area_m2": eligible_area_m2,
        "remanufactured_igus": float(remanufactured_igus),
        "remanufactured_area_m2": remanufactured_area_m2,
        "average_area_per_igu": average_area_per_igu,
    }


def compute_masses(groups: List[IGUGroup], stats: Dict[str, float]) -> Dict[str, float]:
    total_mass_kg = 0.0

    for g in groups:
        area_per_igu = (g.width_mm / 1000.0) * (g.height_mm / 1000.0)
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

    eligible_mass_kg = avg_mass_per_igu_kg * stats["eligible_igus"]
    remanufactured_mass_kg = avg_mass_per_igu_kg * stats["remanufactured_igus"]

    return {
        "total_mass_kg": total_mass_kg,
        "total_mass_t": total_mass_t,
        "eligible_mass_kg": eligible_mass_kg,
        "remanufactured_mass_kg": remanufactured_mass_kg,
        "avg_mass_per_igu_kg": avg_mass_per_igu_kg,
    }


def packaging_factor_per_igu(processes: ProcessSettings) -> float:
    if not processes.include_stillage_embodied:
        return 0.0
    if processes.igus_per_stillage <= 0 or STILLAGE_LIFETIME_CYCLES <= 0:
        return 0.0
    return STILLAGE_MANUFACTURE_KGCO2 / (
        STILLAGE_LIFETIME_CYCLES * processes.igus_per_stillage
    )

# ============================================================================
# PHASE A
# ============================================================================

def compute_phase_A(
    route: RouteConfig, processes: ProcessSettings, groups: List[IGUGroup]
) -> Dict[str, object]:
    stats = aggregate_igu_groups(groups, processes)
    masses = compute_masses(groups, stats)

    n_stillages_A = (
        ceil(stats["eligible_igus"] / processes.igus_per_stillage)
        if processes.igus_per_stillage > 0
        else 0
    )
    stillage_mass_A_kg = n_stillages_A * processes.stillage_mass_empty_kg

    distances = compute_route_distances(route)
    truck_A_km = distances["truck_A_km"]
    ferry_A_km = distances["ferry_A_km"]

    if processes.route_A_mode == "truck_only":
        ferry_A_km = 0.0

    truck_A_km *= route.backhaul_factor
    ferry_A_km *= route.backhaul_factor

    mass_A_t = (masses["eligible_mass_kg"] + stillage_mass_A_kg) / 1000.0

    dismantling_kgco2 = stats["total_area_m2"] * processes.e_site_kgco2_per_m2

    pkg_per_igu = packaging_factor_per_igu(processes)
    packaging_kgco2 = stats["eligible_igus"] * pkg_per_igu

    transport_A_kgco2 = mass_A_t * (
        truck_A_km * route.emissionfactor_truck
        + ferry_A_km * route.emissionfactor_ferry
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
# FULL CHAIN (kept for later tasks, not invoked in Task 1 main flow)
# ============================================================================

def compute_full_emissions(batch: BatchInput) -> EmissionBreakdown:
    stats = aggregate_igu_groups(batch.igu_groups, batch.processes)
    masses = compute_masses(batch.igu_groups, stats)

    n_stillages_A = (
        ceil(stats["eligible_igus"] / batch.processes.igus_per_stillage)
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
                stats["eligible_igus"] / batch.processes.igus_per_stillage
            )
    else:
        n_stillages_B = 0

    stillage_mass_A_kg = n_stillages_A * batch.processes.stillage_mass_empty_kg
    stillage_mass_B_kg = n_stillages_B * batch.processes.stillage_mass_empty_kg

    dismantling_kgco2 = stats["total_area_m2"] * batch.processes.e_site_kgco2_per_m2

    pkg_per_igu = packaging_factor_per_igu(batch.processes)
    packaging_kgco2 = stats["eligible_igus"] * pkg_per_igu

    distances = compute_route_distances(batch.route)
    truck_A_km = distances["truck_A_km"]
    ferry_A_km = distances["ferry_A_km"]
    truck_B_km = distances["truck_B_km"]
    ferry_B_km = distances["ferry_B_km"]

    if batch.processes.route_A_mode == "truck_only":
        ferry_A_km = 0.0
    if batch.processes.route_B_mode == "truck_only":
        ferry_B_km = 0.0

    truck_A_km *= batch.route.backhaul_factor
    ferry_A_km *= batch.route.backhaul_factor
    truck_B_km *= batch.route.backhaul_factor
    ferry_B_km *= batch.route.backhaul_factor

    mass_A_t = (masses["eligible_mass_kg"] + stillage_mass_A_kg) / 1000.0

    if batch.processes.process_level == "component":
        mass_B_t = (masses["remanufactured_mass_kg"] + stillage_mass_B_kg) / 1000.0
    else:
        mass_B_t = (masses["eligible_mass_kg"] + stillage_mass_B_kg) / 1000.0

    transport_A_kgco2 = mass_A_t * (
        truck_A_km * batch.route.emissionfactor_truck
        + ferry_A_km * batch.route.emissionfactor_ferry
    )
    transport_B_kgco2 = mass_B_t * (
        truck_B_km * batch.route.emissionfactor_truck
        + ferry_B_km * batch.route.emissionfactor_ferry
    )

    disassembly_kgco2 = 0.0
    if batch.processes.process_level == "system":
        disassembly_kgco2 = stats["eligible_area_m2"] * DISASSEMBLY_KGCO2_PER_M2

    remanufacturing_kgco2 = 0.0
    if batch.processes.process_level == "component":
        remanufacturing_kgco2 = (
            stats["remanufactured_area_m2"] * REMANUFACTURING_KGCO2_PER_M2
        )
    elif batch.processes.process_level == "system":
        if batch.processes.system_path == "reuse":
            remanufacturing_kgco2 = 0.0
        elif batch.processes.system_path == "repurpose":
            repurpose_area_m2 = stats["eligible_area_m2"]
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
        on_site_dismantling_kgco2=dismantling_kgco2,
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
# MAIN (TASK 1: up to first transportation leg)
# ============================================================================

if __name__ == "__main__":
    print("IGU reuse carbon prototype – Phase A (on-site removal and first transport)\n")

    print("First, provide the key locations.\n")
    origin = prompt_location("project origin (on-site removal)")
    processor = prompt_location("processor location (main processing site)")

    route = RouteConfig(origin=origin, processor=processor, reuse=processor)

    print("\nLocations used:")
    print(f"  Origin   : {origin.lat:.6f}, {origin.lon:.6f}")
    print(f"  Processor: {processor.lat:.6f}, {processor.lon:.6f}\n")

    processes = ProcessSettings()

    print("Now describe the IGU batch.\n")
    total_igus_str = input("Total number of IGUs in this batch: ").strip()
    width_str = input("Width of each IGU in mm: ").strip()
    height_str = input("Height of each IGU in mm: ").strip()

    try:
        total_igus = int(total_igus_str)
        width_mm = float(width_str)
        height_mm = float(height_str)
    except ValueError:
        print("Invalid numeric input for IGU count or dimensions.")
        raise SystemExit(1)

    glazing_type_str = prompt_choice(
        "Glazing type", ["double", "triple"], default="double"
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
        ["polysulfide", "polyurethane", "silicone"],
        default="polysulfide",
    )
    spacer_str = prompt_choice(
        "Spacer material",
        ["aluminium", "steel", "warm_edge_composite"],
        default="aluminium",
    )

    if glazing_type_str == "double":
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
        pane_thickness_middle_mm = None
        cavity_thickness_2_mm = None
    else:
        outer_th_str = input("Outer pane thickness (mm): ").strip()
        middle_th_str = input("Middle pane thickness (mm): ").strip()
        inner_th_str = input("Inner pane thickness (mm): ").strip()
        cavity1_str = input("First cavity thickness (mm): ").strip()
        cavity2_str = input("Second cavity thickness (mm): ").strip()
        try:
            pane_thickness_outer_mm = float(outer_th_str)
            pane_thickness_middle_mm = float(middle_th_str)
            pane_thickness_inner_mm = float(inner_th_str)
            cavity_thickness_1_mm = float(cavity1_str)
            cavity_thickness_2_mm = float(cavity2_str)
        except ValueError:
            print("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)

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
        width_mm=width_mm,
        height_mm=height_mm,
        glazing_type=glazing_type_str,  # type: ignore[arg-type]
        glass_type_outer=glass_outer_str,  # type: ignore[arg-type]
        glass_type_inner=glass_inner_str,  # type: ignore[arg-type]
        coating_type=coating_str,  # type: ignore[arg-type]
        sealant_type_secondary=sealant_str,  # type: ignore[arg-type]
        spacer_material=spacer_str,  # type: ignore[arg-type]
        interlayer_type=None,
        condition=condition,
        pane_thickness_outer_mm=pane_thickness_outer_mm,
        pane_thickness_inner_mm=pane_thickness_inner_mm,
        cavity_thickness_1_mm=cavity_thickness_1_mm,
        mass_per_m2_override=None,
        pane_thickness_middle_mm=pane_thickness_middle_mm,
        cavity_thickness_2_mm=cavity_thickness_2_mm,
    )

    stats_initial = aggregate_igu_groups([group], processes)
    total_area_m2_initial = stats_initial["total_area_m2"]

    e_site_str = input(
        f"\nOn-site dismantling factor E_site (kg CO2e/m² glass) "
        f"(press Enter for {E_SITE_KGCO2_PER_M2}): "
    ).strip()
    if e_site_str:
        try:
            processes.e_site_kgco2_per_m2 = float(e_site_str)
        except ValueError:
            print("Invalid E_site value, keeping default.")

    dismantling_only_kgco2 = total_area_m2_initial * processes.e_site_kgco2_per_m2
    print(
        f"\nEstimated on-site dismantling emissions for IGU removal: "
        f"{f3(dismantling_only_kgco2)} kg CO2e"
    )

    include_stillage = prompt_yes_no(
        "\nInclude stillage manufacturing emissions?",
        default=INCLUDE_STILLAGE_EMBODIED,
    )
    processes.include_stillage_embodied = include_stillage

    print("\nSelect truck emission factor preset:")
    print("  eu_legacy    = 0.06 kgCO2e/tkm  (older diesel trucks)")
    print("  eu_current   = 0.04 kgCO2e/tkm  (current EU average)")
    print("  best_diesel  = 0.03 kgCO2e/tkm  (best-in-class diesel)")
    print("  ze_truck     = 0.0075 kgCO2e/tkm (electric truck, grid mix)")

    truck_preset = prompt_choice(
        "Truck emission preset",
        ["eu_legacy", "eu_current", "best_diesel", "ze_truck"],
        default="eu_current",
    )

    if truck_preset == "eu_legacy":
        route.emissionfactor_truck = 0.06
    elif truck_preset == "eu_current":
        route.emissionfactor_truck = 0.04
    elif truck_preset == "best_diesel":
        route.emissionfactor_truck = 0.03
    elif truck_preset == "ze_truck":
        route.emissionfactor_truck = 0.0075

    route.emissionfactor_ferry = EMISSIONFACTOR_FERRY

    print(
        f"\nUsing truck emission factor: {route.emissionfactor_truck} kg CO2e/tkm "
        f"(preset: {truck_preset})"
    )
    print(
        f"Using ferry emission factor: {route.emissionfactor_ferry} kg CO2e/tkm\n"
    )

    print("Select observed breakage rate during on-site removal.")
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
        "of eligible IGUs\n"
    )

    phaseA = compute_phase_A(route, processes, [group])
    stats_A = phaseA["stats"]   # type: ignore[assignment]
    masses_A = phaseA["masses"] # type: ignore[assignment]

    print("=== Phase A: up to transport to processor ===")
    print(f"  On-site dismantling : {f3(phaseA['dismantling_kgco2'])} kg CO2e")
    print(f"  Packaging           : {f3(phaseA['packaging_kgco2'])} kg CO2e")
    print(f"  Transport A         : {f3(phaseA['transport_A_kgco2'])} kg CO2e")
    print(
        f"  Packaging factor    : {f3(phaseA['packaging_per_igu'])} "
        "kg CO2e / IGU (stillage manufacturing)"
    )

    print("\nPhase A key stats:")
    print(f"  Total IGUs (input)       : {int(stats_A['total_igus'])}")
    print(f"  Eligible IGUs            : {int(stats_A['eligible_igus'])}")
    print(f"  Total IGU area           : {f3(stats_A['total_area_m2'])} m²")
    print(f"  Average area per IGU     : {f3(stats_A['average_area_per_igu'])} m²")
    print(f"  Avg mass per IGU         : {f3(masses_A['avg_mass_per_igu_kg'])} kg")
    print(f"  Truck distance A (eff.)  : {f3(phaseA['truck_A_km_eff'])} km")
    print(f"  Mass on truck A          : {f3(phaseA['mass_A_t'])} t\n")
