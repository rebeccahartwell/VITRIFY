from math import radians, sin, cos, sqrt, atan2, floor
from typing import Dict, List, Optional
from ..constants import (
    DECIMALS, MASS_PER_M2_SINGLE, MASS_PER_M2_DOUBLE, MASS_PER_M2_TRIPLE,
    STILLAGE_LIFETIME_CYCLES, STILLAGE_MANUFACTURE_KGCO2,
    GLASS_DENSITY_KG_M3, SEALANT_DENSITY_KG_M3, SPACER_MASS_PER_M_KG
)
from ..models import Location, TransportModeConfig, IGUGroup, ProcessSettings, SealGeometry, BatchInput, GlazingType, FlowState
import requests
import logging

logger = logging.getLogger(__name__)
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
    c = 2 * atan2(sqrt(h), sqrt(1 - h))
    return r * c


from typing import Dict, List, Optional, Tuple

def get_osrm_distance(origin: Location, dest: Location) -> Tuple[Optional[float], bool]:
    """
    Get driving distance in km and ferry presence from OSRM public API.
    Returns (distance_km, has_ferry).
    distance_km is None if request fails.
    """
    # Request steps to check for ferry maneuvers
    url = f"http://router.project-osrm.org/route/v1/driving/{origin.lon},{origin.lat};{dest.lon},{dest.lat}?overview=false&steps=true"
    
    try:
        # Custom User-Agent to avoid blocking
        headers = {'User-Agent': 'IGURecoveryTool/1.0'}
        # 10s timeout
        resp = requests.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if "routes" in data and len(data["routes"]) > 0:
                route = data["routes"][0]
                dist_meters = route["distance"]
                
                # Check for ferry in steps
                has_ferry = False
                if "legs" in route:
                    for leg in route["legs"]:
                        for step in leg.get("steps", []):
                            # OSRM usually marks ferry steps with maneuver type 'notification' and modifier or mode 'ferry'
                            # Simpler check: step['mode'] == 'ferry' if available, or maneuver type
                            # The 'mode' property is standard in OSRM v5
                            if step.get("mode") == "ferry":
                                has_ferry = True
                                break
                        if has_ferry: break
                
                return (dist_meters / 1000.0, has_ferry)
    except Exception as e:
        logger.warning(f"OSRM request failed: {e}")
    
    return (None, False)


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
                g.condition.visible_edge_seal_condition != "unacceptable"
                and not g.condition.visible_fogging
            ):
                acceptable_igus += g.quantity

    # Global breakage and humidity failure applied to acceptable IGUs.
    after_breakage = acceptable_igus * (1.0 - processes.breakage_rate_global)
    after_humidity = after_breakage * (1.0 - processes.humidity_failure_rate)

    # Calculate weighted average panes per IGU
    total_quantity_acceptable = 0
    total_panes_sum = 0.0
    for g in groups:
        # Only consider groups that contribute to acceptable_igus for the weighted average
        # This is a simplification, assuming the distribution of glazing types among acceptable IGUs
        # is similar to the overall distribution.
        # A more precise approach would be to track acceptable_igus per group.
        if g.condition.reuse_allowed and not g.condition.cracks_chips and \
           g.condition.visible_edge_seal_condition != "unacceptable" and not g.condition.visible_fogging:
            
            panes_in_group = 0
            if g.glazing_type == "single":
                panes_in_group = 1
            elif g.glazing_type == "double":
                panes_in_group = 2
            elif g.glazing_type == "triple":
                panes_in_group = 3
            else:
                # Should not happen if GlazingType is an Enum
                raise ValueError(f"Unsupported glazing type: {g.glazing_type}")
            
            total_panes_sum += g.quantity * panes_in_group
            total_quantity_acceptable += g.quantity

    panes_per_igu = total_panes_sum / total_quantity_acceptable if total_quantity_acceptable > 0 else 0.0

    total_panes = after_humidity * panes_per_igu * processes.split_yield
    remanufactured_igus_raw = floor(total_panes / panes_per_igu) if panes_per_igu > 0 else 0.0
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


def secondary_seal_thickness_mm_for_group(g: IGUGroup) -> float:
    """
    Derive the secondary seal thickness based on glazing type and cavity thickness.
    Rules:
      - Double: equals cavity_thickness_mm
      - Triple: equals max(cavity_thickness_mm, cavity_thickness_2_mm)
      - Single: 0.0
    """
    if g.glazing_type == "single":
        return 0.0
    elif g.glazing_type == "double":
        return g.cavity_thickness_mm
    elif g.glazing_type == "triple":
        c1 = g.cavity_thickness_mm
        c2 = g.cavity_thickness_2_mm if g.cavity_thickness_2_mm is not None else 0.0
        return max(c1, c2)
    else:
        raise ValueError(f"Unsupported glazing type for seal calculation: {g.glazing_type}")


def compute_sealant_volumes(group: IGUGroup, seal: SealGeometry) -> Dict[str, float]:
    """
    Compute primary and secondary sealant volumes for an IGU group.
    Returns a dict with per-IGU and total volumes (m3).
    """
    # 1. Dimensions in metres
    W_m = group.unit_width_mm / 1000.0
    H_m = group.unit_height_mm / 1000.0
    perimeter_m = 2.0 * (W_m + H_m)

    # 2. Primary seal (constant cross-section)
    # Area = thickness * width
    A_primary_m2 = (seal.primary_thickness_mm / 1000.0) * (seal.primary_width_mm / 1000.0)
    V_primary_igu_m3 = perimeter_m * A_primary_m2

    # 3. Secondary seal
    # Thickness logic: use helper
    t_sec_mm = secondary_seal_thickness_mm_for_group(group)
    A_secondary_m2 = (t_sec_mm / 1000.0) * (seal.secondary_width_mm / 1000.0)
    V_secondary_igu_m3 = perimeter_m * A_secondary_m2

    # 4. Totals
    V_primary_total_m3 = V_primary_igu_m3 * group.quantity
    V_secondary_total_m3 = V_secondary_igu_m3 * group.quantity

    return {
        "primary_volume_per_igu_m3": V_primary_igu_m3,
        "secondary_volume_per_igu_m3": V_secondary_igu_m3,
        "primary_volume_total_m3": V_primary_total_m3,
        "secondary_volume_total_m3": V_secondary_total_m3,
        "secondary_thickness_mm": t_sec_mm,
    }


def apply_yield_loss(state: FlowState, loss_fraction: float) -> FlowState:
    """
    Apply a generic yield loss to the flow state.
    Returns a new FlowState with reduced quantities.
    """
    keep_factor = 1.0 - loss_fraction
    return FlowState(
        igus=state.igus * keep_factor,
        area_m2=state.area_m2 * keep_factor,
        mass_kg=state.mass_kg * keep_factor,
    )


def calculate_material_masses(group: IGUGroup, seal: SealGeometry) -> Dict[str, float]:
    """
    Calculate total mass (kg) of Glass, Sealant, and Spacer for the group.
    Returns:
        {
            "glass_kg": float,
            "sealant_kg": float,
            "spacer_kg": float
        }
    """
    # Dimensions
    W_m = group.unit_width_mm / 1000.0
    H_m = group.unit_height_mm / 1000.0
    area_per_igu = W_m * H_m
    perimeter_m = 2.0 * (W_m + H_m)
    qty = group.quantity

    # 1. Glass Mass
    # Sum of pane thicknesses
    t_glass_mm = group.thickness_outer_mm + group.thickness_inner_mm
    if group.glazing_type == "triple" and group.thickness_centre_mm:
        t_glass_mm += group.thickness_centre_mm
    
    # Volume = Area * thickness
    vol_glass_m3 = (t_glass_mm / 1000.0) * area_per_igu * qty
    mass_glass_kg = vol_glass_m3 * GLASS_DENSITY_KG_M3

    # 2. Sealant Mass
    # Use existing volume helper
    vols = compute_sealant_volumes(group, seal)
    # Total volume (primary + secondary) for the whole group
    vol_seal_total_m3 = vols["primary_volume_total_m3"] + vols["secondary_volume_total_m3"]
    
    # Map Sealant Type to Density Factor
    # Base density is ~1700 kg/m3 (Polysulfide)
    density_factor = 1.0
    stype = group.sealant_type_secondary
    if stype == "polyurethane":
        density_factor = 0.85
    elif stype == "silicone":
        density_factor = 0.82
    # polysulfide stays 1.0 (base)
    
    mass_sealant_kg = vol_seal_total_m3 * SEALANT_DENSITY_KG_M3 * density_factor

    # 3. Spacer Mass
    # Length = Perimeter * Cavities
    cavities = 0
    if group.glazing_type == "double":
        cavities = 1
    elif group.glazing_type == "triple":
        cavities = 2
    
    total_spacer_len_m = perimeter_m * cavities * qty
    
    # Map Spacer Material to Linear Weight
    # Base (Alu) ~0.04 kg/m? Or constant?
    # SPACER_MASS_PER_M_KG is loaded from constants.
    weight_factor = 1.0
    smat = group.spacer_material
    if smat == "steel":
        weight_factor = 2.0
    elif smat == "warm_edge_composite":
        weight_factor = 0.6
    # aluminium stays 1.0
    
    mass_spacer_kg = total_spacer_len_m * SPACER_MASS_PER_M_KG * weight_factor

    return {
        "glass_kg": mass_glass_kg,
        "sealant_kg": mass_sealant_kg,
        "spacer_kg": mass_spacer_kg
    }


def compute_igu_mass_totals(
    groups: List[IGUGroup], stats: Dict[str, float], seal: Optional[SealGeometry] = None
) -> Dict[str, float]:
    """
    Compute IGU mass totals for the project batch:
      - total_mass_kg / total_mass_t
      - acceptable_mass_kg (mass associated with acceptable_igus)
      - remanufactured_mass_kg (mass associated with remanufactured_igus)
      - avg_mass_per_igu_kg
      
    If 'seal' is provided, performs detailed calculation summing Glass + Sealant + Spacer.
    Arguments:
        groups: List of IGUGroup
        stats: Dictionary of aggregated stats (from aggregate_igu_groups)
        seal: Optional SealGeometry for accurate material mass calculation
    """
    total_mass_kg = 0.0

    for g in groups:
        # If we have a seal geometry, use independent calculation summing components
        if seal is not None:
            mats = calculate_material_masses(g, seal)
            # calculate_material_masses returns TOTAL mass for the group (all items)
            group_mass_kg = mats["glass_kg"] + mats["sealant_kg"] + mats["spacer_kg"]
            total_mass_kg += group_mass_kg
        else:
            # Fallback to simplified Area * Mass/m2 logic
            area_per_igu = (g.unit_width_mm / 1000.0) * (g.unit_height_mm / 1000.0)
            m2 = area_per_igu * g.quantity
            mass_per_m2 = (
                g.mass_per_m2_override
                if g.mass_per_m2_override is not None
                else default_mass_per_m2(g.glazing_type)
            )
            total_mass_kg += m2 * mass_per_m2

    total_mass_t = total_mass_kg / 1000.0
    
    # Avg mass per IGU based on total count
    total_igus_count = stats.get("total_igus", 0.0)
    avg_mass_per_igu_kg = (
        total_mass_kg / total_igus_count if total_igus_count > 0 else 0.0
    )

    # Derived masses for fractions
    acceptable_mass_kg = avg_mass_per_igu_kg * stats.get("acceptable_igus", 0.0)
    remanufactured_mass_kg = avg_mass_per_igu_kg * stats.get("remanufactured_igus", 0.0)

    return {
        "total_mass_kg": total_mass_kg,
        "total_mass_t": total_mass_t,
        "acceptable_mass_kg": acceptable_mass_kg,
        "remanufactured_mass_kg": remanufactured_mass_kg,
        "avg_mass_per_igu_kg": avg_mass_per_igu_kg,
    }
