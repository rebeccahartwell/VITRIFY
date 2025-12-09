import logging
import requests
from typing import Optional, List, Tuple, Dict
from ..models import Location, IGUGroup, SealGeometry, SealantType, IGUCondition, ProcessSettings, ScenarioResult, BatchInput, TransportModeConfig, FlowState
from ..constants import GEOCODER_USER_AGENT, DECIMALS
from .calculations import aggregate_igu_groups, compute_igu_mass_totals, compute_sealant_volumes, default_mass_per_m2

logger = logging.getLogger(__name__)

def geocode_address(address: str) -> Optional[Location]:
    """
    Geocode a free-text address to a Location (lat/lon) using Nominatim/OSM.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": GEOCODER_USER_AGENT}
    try:
        logger.info(f"Geocoding '{address}' ...")
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        logger.info(f"Geocoder HTTP status: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        if not data:
            logger.warning("No geocoding results returned.")
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return Location(lat=lat, lon=lon)
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
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
            logger.info(f"{label} set to {loc.lat:.6f}, {loc.lon:.6f} (manual lat,lon)")
            return loc
        loc = geocode_address(s)
        if loc is not None:
            logger.info(f"{label} geocoded to {loc.lat:.6f}, {loc.lon:.6f}")
            return loc
        logger.warning("Could not geocode input. Try again with another address or 'lat,lon'.")


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
        logger.warning(f"Invalid choice. Please choose one of: {opts_str}")


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
        logger.warning("Please answer y or n.")


def prompt_igu_source() -> str:
    """
    Step 2: Ask for IGU source (manual vs database).
    """
    logger.info("\n--- Step 1: IGU Source Selection ---")
    source = prompt_choice("Select IGU definition source", ["manual", "database"], default="manual")
    
    if source == "database":
        # Placeholder for DB lookup
        # db_id = input("Enter Saint-Gobain IGU product ID: ").strip()
        logger.info("Saint Gobain Database Not Found")
        logger.info("Falling back to manual definition.")
        # Fallback to manual
        return "manual"
    
    return "manual"


def define_igu_system_from_manual() -> Tuple[IGUGroup, SealGeometry]:
    """
    Step 3: Define IGU system (geometry + build-up + materials) manually.
    Prompts user for all IGU parameters and constructs the IGUGroup and SealGeometry.
    """
    logger.info("\n--- Step 2: IGU System Definition (Manual) ---")
    
    logger.info("\nDefine global seal geometry (constant for all IGUs).")
    p_th_str = input("Primary seal thickness (mm) [constant]: ").strip()
    p_wd_str = input("Primary seal width (mm) [constant]: ").strip()
    s_wd_str = input("Secondary seal width (mm) [constant]: ").strip()

    try:
        seal_p_th = float(p_th_str)
        seal_p_wd = float(p_wd_str)
        seal_s_wd = float(s_wd_str)
    except ValueError:
        logger.info("Invalid numeric input for seal geometry.")
        raise SystemExit(1)

    seal_geometry = SealGeometry(
        primary_thickness_mm=seal_p_th,
        primary_width_mm=seal_p_wd,
        secondary_width_mm=seal_s_wd,
    )

    logger.info("\nNow describe the IGU batch geometry.\n")
    total_igus_str = input("Total number of IGUs in this batch: ").strip()
    width_str = input("Width of each IGU in mm (unit_width_mm): ").strip()
    height_str = input("Height of each IGU in mm (unit_height_mm): ").strip()

    try:
        total_igus = int(total_igus_str)
        unit_width_mm = float(width_str)
        unit_height_mm = float(height_str)
    except ValueError:
        logger.info("Invalid numeric input for IGU count or dimensions.")
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
            logger.info("Invalid numeric input for pane thickness.")
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
            logger.info("Invalid numeric input for pane or cavity thickness.")
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
            logger.info("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        IGU_depth_mm_val = (
            pane_thickness_outer_mm
            + cavity_thickness_1_mm
            + thickness_centre_mm
            + cavity_thickness_2_mm
            + pane_thickness_inner_mm
        )
    
    # Construct a temporary condition object to satisfy IGUGroup init (will be updated later)
    # Using defaults/placeholders as condition is asked in a later step.
    temp_condition = IGUCondition(
        visible_edge_seal_condition="not assessed",
        visible_fogging=False,
        cracks_chips=False,
        age_years=20.0,
        reuse_allowed=True
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
        condition=temp_condition,
        thickness_outer_mm=pane_thickness_outer_mm,
        thickness_inner_mm=pane_thickness_inner_mm,
        cavity_thickness_mm=cavity_thickness_1_mm,
        IGU_depth_mm=IGU_depth_mm_val,
        mass_per_m2_override=None,
        thickness_centre_mm=thickness_centre_mm,
        cavity_thickness_2_mm=cavity_thickness_2_mm,
        sealant_type_primary=None,
    )
    
    logger.info("\n--- IGU System Defined ---")
    logger.info(f"  Quantity: {group.quantity}, Size: {group.unit_width_mm}x{group.unit_height_mm} mm")
    logger.info(f"  Type: {group.glazing_type}, Depth: {group.IGU_depth_mm} mm")
    logger.info(f"  Build-up: {group.thickness_outer_mm} / {group.cavity_thickness_mm} / {group.thickness_inner_mm} (plus centre if triple)")
    
    return group, seal_geometry


def ask_igu_condition_and_eligibility() -> IGUCondition:
    """
    Step 6: Conditions and eligibility questions.
    """
    logger.info("\n--- Step 6: Conditions & Eligibility ---")
    
    edge_cond_str = prompt_choice(
        "Visible edge seal condition", ["acceptable", "unacceptable", "not assessed"], default="acceptable"
    )
    fogging = prompt_yes_no("Visible fogging?", default=False)
    cracks = prompt_yes_no("Cracks or chips present?", default=False)
    reuse_allowed = prompt_yes_no("Reuse allowed by owner/regulations?", default=True)

    age_str = input("Approximate age of IGUs in years (default=20): ").strip()
    try:
        age_years = float(age_str) if age_str else 20.0
    except ValueError:
        age_years = 20.0
        
    return IGUCondition(
        visible_edge_seal_condition=edge_cond_str,  # type: ignore[arg-type]
        visible_fogging=fogging,
        cracks_chips=cracks,
        age_years=age_years,
        reuse_allowed=reuse_allowed,
    )


def print_igu_geometry_overview(group: IGUGroup, seal_geometry: SealGeometry, processes: ProcessSettings):
    """
    Step 5: Geometry information and build-up overview.
    Calculates and prints geometric properties, masses, and sealant volumes.
    """
    logger.info("\n--- Step 5: Geometry & Materials Overview ---")
    
    # 1. Compute stats
    # Note: Using a list with one group for aggregation
    stats = aggregate_igu_groups([group], processes)
    masses = compute_igu_mass_totals([group], stats)
    seal_vols = compute_sealant_volumes(group, seal_geometry)
    
    logger.info(f"IGU Geometric Properties:")
    logger.info(f"  Dimensions: {group.unit_width_mm} mm x {group.unit_height_mm} mm")
    logger.info(f"  Depth:      {group.IGU_depth_mm} mm")
    logger.info(f"  Area (1):   {stats['average_area_per_igu']:.3f} m²")
    logger.info(f"  Area (all): {stats['total_IGU_surface_area_m2']:.3f} m² (Total Batch)")
    
    logger.info(f"\nBuild-up & Materials:")
    logger.info(f"  Glazing:    {group.glazing_type}")
    logger.info(f"  Glass:      {group.glass_type_outer} (outer), {group.glass_type_inner} (inner)")
    if group.thickness_centre_mm:
         logger.info(f"              {group.thickness_centre_mm} mm (centre)")
    logger.info(f"  Cavity:     {group.cavity_thickness_mm} mm")
    if group.cavity_thickness_2_mm:
        logger.info(f"              {group.cavity_thickness_2_mm} mm (2nd cavity)")
    logger.info(f"  Spacer:     {group.spacer_material}")
    logger.info(f"  Sealants:   Primary={seal_geometry.primary_thickness_mm}x{seal_geometry.primary_width_mm}mm")
    logger.info(f"              Secondary Type={group.sealant_type_secondary}, Width={seal_geometry.secondary_width_mm}mm")
    logger.info(f"              Sec. Thickness={seal_vols['secondary_thickness_mm']} mm (derived)")
    
    logger.info(f"\nMass Information:")
    logger.info(f"  Per m²:     {default_mass_per_m2(group.glazing_type)} kg/m² (approx)")
    logger.info(f"  Per IGU:    {masses['avg_mass_per_igu_kg']:.2f} kg")
    logger.info(f"  Total Batch:{masses['total_mass_t']:.3f} tonnes")
    
    logger.info(f"\nSealant Volumes (Total Batch):")
    logger.info(f"  Primary:    {seal_vols['primary_volume_total_m3']:.4f} m³")
    logger.info(f"  Secondary:  {seal_vols['secondary_volume_total_m3']:.4f} m³")


def print_scenario_overview(result: ScenarioResult):
    """
    Common reporting for all scenarios.
    """
    logger.info(f"\n========================================================")
    logger.info(f"   SCENARIO RESULT: {result.scenario_name.upper()}")
    logger.info(f"========================================================")
    
    logger.info(f"\nYield Summary:")
    logger.info(f"  Initial Acceptable IGUs: {result.initial_igus:.0f}")
    logger.info(f"  Initial Area:            {result.initial_area_m2:.3f} m²")
    logger.info(f"  Final Output IGUs/Units: {result.final_igus:.0f}")
    logger.info(f"  Final Output Area:       {result.final_area_m2:.3f} m²")
    logger.info(f"  Yield (Area basis):      {result.yield_percent:.1f}%")
    logger.info(f"  Initial Mass:            {result.initial_mass_kg/1000.0:.3f} t")
    logger.info(f"  Final Mass:              {result.final_mass_kg/1000.0:.3f} t")
    
    logger.info(f"\nCarbon Emissions (kg CO2e):")
    for stage, val in result.by_stage.items():
        logger.info(f"  {stage:<30} : {val:.3f}")
    
    logger.info(f"--------------------------------------------------------")
    logger.info(f"  TOTAL EMISSIONS              : {result.total_emissions_kgco2:.3f} kg CO2e")
    
    if result.final_area_m2 > 0:
         logger.info(f"  Intensity (per output m²)    : {result.total_emissions_kgco2 / result.final_area_m2:.3f} kgCO2e/m²")
    logger.info(f"========================================================\n")
