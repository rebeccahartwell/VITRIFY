import logging
import requests
import pandas as pd
import re
import os
from typing import Optional, List, Tuple, Dict
from ..models import Location, IGUGroup, SealGeometry, SealantType, IGUCondition, ProcessSettings, ScenarioResult, BatchInput, TransportModeConfig, FlowState
from ..constants import GEOCODER_USER_AGENT, DECIMALS
from .calculations import aggregate_igu_groups, compute_igu_mass_totals, compute_sealant_volumes, default_mass_per_m2

# COLORAMA SETUP
try:
    import colorama
    from colorama import Fore, Style, Back
    colorama.init(autoreset=True)
    HAS_COLORABLE_CLI = True
except ImportError:
    HAS_COLORABLE_CLI = False
    class Fore:
        CYAN = ""
        YELLOW = ""
        GREEN = ""
        RED = ""
        WHITE = ""
        MAGENTA = ""
        BLUE = ""
    class Style:
        BRIGHT = ""
        RESET_ALL = ""
    class Back:
        BLACK = ""

logger = logging.getLogger(__name__)

# Style Constants
C_HEADER = Fore.CYAN + Style.BRIGHT
C_PROMPT = Fore.YELLOW
C_CHOICE = Fore.MAGENTA
C_ERROR = Fore.RED
C_SUCCESS = Fore.GREEN
C_RESET = Style.RESET_ALL

def style_prompt(prompt_text: str) -> str:
    """Helper to wrap input prompt in color."""
    return f"{C_PROMPT}{prompt_text}{C_RESET}"

def print_header(text: str):
    """Print a styled header."""
    # We use print directly for visual flair, bypassing the logger formatter which might be green
    print(f"\n{C_HEADER}{'='*60}")
    print(f"{text.center(60)}")
    print(f"{'='*60}{C_RESET}")

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
        s = input(style_prompt(f"Enter {label} address or 'lat,lon': ")).strip()
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
    Supports selecting by index (1-based) or typing the name.
    """
    # Build display string with indices: [1] opt1 / [2] opt2
    display_parts = []
    for idx, opt in enumerate(options, 1):
        display_parts.append(f"[{C_SUCCESS}{idx}{C_PROMPT}] {C_CHOICE}{opt}{C_PROMPT}")
    
    opts_str = " / ".join(display_parts)
    
    while True:
        # Show options differently if there are many? For now inline is fine.
        print(f"\n{C_PROMPT}{label} options:{C_RESET} {opts_str}")
        s = input(style_prompt(f"Select option (name or number) [default={default}]: ")).strip().lower()
        
        if not s:
            return default
            
        # Check if digit
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(options):
                choice = options[idx-1]
                # print(f"{C_PROMPT}Selected: {C_SUCCESS}{choice}{C_RESET}")
                return choice
        
        # Check text match
        for opt in options:
            if s == opt.lower():
                return opt
                
        logger.warning(f"Invalid choice '{s}'. Please enter a number 1-{len(options)} or the option name.")


def prompt_yes_no(label: str, default: bool) -> bool:
    """
    Prompt user for yes/no answer, returning True/False.
    """
    d = "y" if default else "n"
    # Colorize defaults
    opts = f"{C_CHOICE}y{C_PROMPT}/{C_CHOICE}n{C_PROMPT}"
    while True:
        s = input(style_prompt(f"{label} [{opts}] (default={d}): ")).strip().lower()
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
    print_header("Step 1: IGU Source Selection")
    source = prompt_choice("Select IGU definition source", ["manual", "database"], default="manual")
    return source

def prompt_seal_geometry() -> SealGeometry:
    """
    Prompt for global seal geometry parameters.
    """
    print(f"\n{C_HEADER}Define global seal geometry (constant for all IGUs){C_RESET}")
    p_th_str = input(style_prompt("Primary seal thickness (mm) [constant]: ")).strip()
    p_wd_str = input(style_prompt("Primary seal width (mm) [constant]: ")).strip()
    s_wd_str = input(style_prompt("Secondary seal width (mm) [constant]: ")).strip()

    try:
        seal_p_th = float(p_th_str)
        seal_p_wd = float(p_wd_str)
        seal_s_wd = float(s_wd_str)
    except ValueError:
        logger.error("Invalid numeric input for seal geometry.")
        raise SystemExit(1)

    return SealGeometry(
        primary_thickness_mm=seal_p_th,
        primary_width_mm=seal_p_wd,
        secondary_width_mm=seal_s_wd,
    )


def define_igu_system_from_manual() -> Tuple[IGUGroup, SealGeometry]:
    """
    Step 3: Define IGU system (geometry + build-up + materials) manually.
    Prompts user for all IGU parameters and constructs the IGUGroup and SealGeometry.
    """
    print_header("Step 2: IGU System Definition (Manual)")
    
    seal_geometry = prompt_seal_geometry()

    print(f"\n{C_HEADER}Now describe the IGU batch geometry{C_RESET}")
    total_igus_str = input(style_prompt("Total number of IGUs in this batch: ")).strip()
    width_str = input(style_prompt("Width of each IGU in mm (unit_width_mm): ")).strip()
    height_str = input(style_prompt("Height of each IGU in mm (unit_height_mm): ")).strip()

    try:
        total_igus = int(total_igus_str)
        unit_width_mm = float(width_str)
        unit_height_mm = float(height_str)
    except ValueError:
        logger.error("Invalid numeric input for IGU count or dimensions.")
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
        pane_th_str = input(style_prompt("Pane thickness (mm): ")).strip()
        try:
            pane_thickness_single_mm = float(pane_th_str)
        except ValueError:
            logger.error("Invalid numeric input for pane thickness.")
            raise SystemExit(1)

        pane_thickness_outer_mm = pane_thickness_single_mm
        pane_thickness_inner_mm = 0.0
        cavity_thickness_1_mm = 0.0
        thickness_centre_mm: Optional[float] = None
        cavity_thickness_2_mm: Optional[float] = None
        IGU_depth_mm_val = pane_thickness_single_mm

    elif glazing_type_str == "double":
        outer_th_str = input(style_prompt("Outer pane thickness (mm): ")).strip()
        inner_th_str = input(style_prompt("Inner pane thickness (mm): ")).strip()
        cavity1_str = input(style_prompt("Cavity thickness (mm): ")).strip()
        try:
            pane_thickness_outer_mm = float(outer_th_str)
            pane_thickness_inner_mm = float(inner_th_str)
            cavity_thickness_1_mm = float(cavity1_str)
        except ValueError:
            logger.error("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        thickness_centre_mm = None
        cavity_thickness_2_mm = None
        IGU_depth_mm_val = (
            pane_thickness_outer_mm + cavity_thickness_1_mm + pane_thickness_inner_mm
        )

    else:  # glazing_type_str == "triple"
        outer_th_str = input(style_prompt("Outer pane thickness (mm): ")).strip()
        middle_th_str = input(style_prompt("Centre pane thickness (mm): ")).strip()
        inner_th_str = input(style_prompt("Inner pane thickness (mm): ")).strip()
        cavity1_str = input(style_prompt("First cavity thickness (mm): ")).strip()
        cavity2_str = input(style_prompt("Second cavity thickness (mm): ")).strip()
        try:
            pane_thickness_outer_mm = float(outer_th_str)
            thickness_centre_mm = float(middle_th_str)
            pane_thickness_inner_mm = float(inner_th_str)
            cavity_thickness_1_mm = float(cavity1_str)
            cavity_thickness_2_mm = float(cavity2_str)
        except ValueError:
            logger.error("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        IGU_depth_mm_val = (
            pane_thickness_outer_mm
            + cavity_thickness_1_mm
            + thickness_centre_mm
            + cavity_thickness_2_mm
            + pane_thickness_inner_mm
        )
    
    # Construct a temporary condition object to satisfy IGUGroup init (will be updated later)
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
    
    print_header("IGU System Defined")
    print(f"  {C_PROMPT}Quantity:{C_RESET} {group.quantity}, Size: {group.unit_width_mm}x{group.unit_height_mm} mm")
    print(f"  {C_PROMPT}Type:{C_RESET} {group.glazing_type}, Depth: {group.IGU_depth_mm} mm")
    
    return group, seal_geometry


def define_igu_system_from_database() -> Tuple[IGUGroup, SealGeometry]:
    """
    Step 3 (DB): Load from Database, select product, and prompt for quantities.
    """
    print_header("Step 2: IGU System Definition (Database)")
    db_path = r'd:\VITRIFY\data\saint_gobain\saint gobain product database.xlsx'
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found at {db_path}")
        raise FileNotFoundError(db_path)

    # Load DB
    try:
        df = pd.read_excel(db_path)
    except Exception as e:
        logger.error(f"Error reading database: {e}")
        raise SystemExit(1)
        
    # Check if we have 'win_name'.
    if 'win_name' not in df.columns:
         logger.error("Invalid database format: 'win_name' column missing.")
         raise SystemExit(1)
         
    # Display Options
    options = df['win_name'].tolist()
    print(f"\n{C_HEADER}Available Products:{C_RESET}")
    selected_name = prompt_choice("Select Product", options, default=options[0])
    
    # Get Row
    row = df[df['win_name'] == selected_name].iloc[0]
    
    print(f"{C_SUCCESS}Selected: {row['win_name']} (Group: {row.get('Group/ID', 'N/A')}){C_RESET}")
    
    # Prompt for missing info (Quantity + Dimensions + Seal Geometry)
    seal_geometry = prompt_seal_geometry()

    print(f"\n{C_HEADER}Enter Quantity and Dimensions for this batch{C_RESET}")
    total_igus_str = input(style_prompt("Total number of IGUs: ")).strip()
    width_str = input(style_prompt("Width (mm): ")).strip()
    height_str = input(style_prompt("Height (mm): ")).strip()

    try:
        total_igus = int(total_igus_str)
        unit_width_mm = float(width_str)
        unit_height_mm = float(height_str)
    except ValueError:
        logger.error("Invalid numeric input.")
        raise SystemExit(1)
        
    group = parse_db_row_to_group(
        row, 
        total_igus, 
        unit_width_mm, 
        unit_height_mm, 
        seal_geometry
    )
    
    print_header("IGU System Defined from Database")
    print(f"  {C_PROMPT}Product:{C_RESET} {selected_name}")
    print(f"  {C_PROMPT}Type:{C_RESET} {group.glazing_type}, Depth: {group.IGU_depth_mm} mm")
    print(f"  {C_PROMPT}Spacer:{C_RESET} {group.spacer_material}, Sealant: {group.sealant_type_secondary}")
    
    return group, seal_geometry


def parse_db_row_to_group(
    row: pd.Series,
    quantity: int,
    width_mm: float,
    height_mm: float,
    seal_geometry: SealGeometry
) -> IGUGroup:
    """
    Parses a single row from the product database into an IGUGroup object.
    """
    # 1. Glazing Type
    # DB has "Double" or "Triple". Model expects "double", "triple"
    raw_type = str(row.get('Glazing Type', 'double')).lower()
    glazing_type = "double" # default
    if "trip" in raw_type or "tgu" in raw_type or "3" in raw_type:
        glazing_type = "triple"
    elif "doub" in raw_type or "dgu" in raw_type or "2" in raw_type:
        glazing_type = "double"
    elif "sing" in raw_type or "sgu" in raw_type or "1" in raw_type:
        glazing_type = "single"
    
    # 2. Spacer
    # DB: "Aluminum" -> Model "aluminium"
    spacer_raw = str(row.get('Spacer Bar', 'aluminium')).lower()
    spacer_material = "aluminium"
    if "aluminum" in spacer_raw or "aluminium" in spacer_raw:
        spacer_material = "aluminium"
    elif "steel" in spacer_raw:
        spacer_material = "steel"
    elif "warm" in spacer_raw or "swiss" in spacer_raw:
        spacer_material = "warm_edge_composite"
        
    # 3. Sealant
    # DB: "Silicone" -> Model expects "silicone"
    sealant_raw = str(row.get('Sealant', 'polysulfide')).lower()
    sealant_type = "polysulfide"
    # Basic matching
    if "silicone" in sealant_raw: sealant_type = "silicone"
    elif "polyurethane" in sealant_raw: sealant_type = "polyurethane"
    
    # 4. Coating
    # Check 'Solar Coating' or 'Low E Coating'
    # If anything other than "-" -> "soft_lowE" (assumption for modern coatings) or "solar_control"
    solar = str(row.get('Solar Coating', '-'))
    low_e = str(row.get('Low E Coating', '-'))
    coating_type = "none"
    if solar != '-' and len(solar) > 2:
        coating_type = "solar_control"
    elif low_e != '-' and len(low_e) > 2:
        coating_type = "soft_lowE" # or hard_lowE, hard to tell from name alone without lookup
        
    # 5. Parse Unit thicknesses
    # "DGU 6 | 16 | 6 mm"
    unit_str = str(row.get('Unit', ''))
    # Extract numbers
    # Remove chars
    cleaned = re.sub(r'[A-Za-z]', '', unit_str).strip()
    parts = [p.strip() for p in cleaned.split('|') if p.strip()]
    
    # Defaults
    t_outer = 6.0
    t_inner = 6.0
    t_mid = None
    c1 = 16.0
    c2 = None
    
    try:
        if glazing_type == "double" and len(parts) >= 3:
             t_outer = float(parts[0])
             c1 = float(parts[1])
             t_inner = float(parts[2])
        elif glazing_type == "triple" and len(parts) >= 5:
             t_outer = float(parts[0])
             c1 = float(parts[1])
             t_mid = float(parts[2])
             c2 = float(parts[3])
             t_inner = float(parts[4])
    except ValueError:
        logger.warning(f"Could not parse geometry from '{unit_str}'. Using defaults.")
    
    # Calculation of Depth
    depth = t_outer + c1 + t_inner
    if t_mid and c2:
        depth += t_mid + c2

    # Temp condition
    temp_condition = IGUCondition(
        visible_edge_seal_condition="not assessed",
        visible_fogging=False,
        cracks_chips=False,
        age_years=20.0,
        reuse_allowed=True
    )

    group = IGUGroup(
        quantity=quantity,
        unit_width_mm=width_mm,
        unit_height_mm=height_mm,
        glazing_type=glazing_type, # type: ignore
        glass_type_outer="annealed", # Default as DB doesn't specify heat treatment per pane clearly enough yet
        glass_type_inner="annealed",
        coating_type=coating_type, # type: ignore
        sealant_type_secondary=sealant_type, # type: ignore
        spacer_material=spacer_material, # type: ignore
        interlayer_type=None,
        condition=temp_condition,
        thickness_outer_mm=t_outer,
        thickness_inner_mm=t_inner,
        thickness_centre_mm=t_mid,
        cavity_thickness_mm=c1,
        cavity_thickness_2_mm=c2,
        IGU_depth_mm=depth,
        mass_per_m2_override=None,
        sealant_type_primary=None
    )
    
    return group


def ask_igu_condition_and_eligibility() -> IGUCondition:
    """
    Step 6: Conditions and eligibility questions.
    """
    print_header("Step 6: Conditions & Eligibility")
    
    edge_cond_str = prompt_choice(
        "Visible edge seal condition", ["acceptable", "unacceptable", "not assessed"], default="acceptable"
    )
    fogging = prompt_yes_no("Visible fogging?", default=False)
    cracks = prompt_yes_no("Cracks or chips present?", default=False)
    reuse_allowed = prompt_yes_no("Reuse allowed by owner/regulations?", default=True)

    age_str = input(style_prompt("Approximate age of IGUs in years (default=20): ")).strip()
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
    print_header("Step 5: Geometry & Materials Overview")
    
    # 1. Compute stats
    # Note: Using a list with one group for aggregation
    stats = aggregate_igu_groups([group], processes)
    masses = compute_igu_mass_totals([group], stats)
    seal_vols = compute_sealant_volumes(group, seal_geometry)
    
    # We can use standard logs but user might want colors here too.
    # Let's simple print styled lines.
    
    print(f"{C_HEADER}IGU Geometric Properties:{C_RESET}")
    print(f"  Dimensions: {group.unit_width_mm} mm x {group.unit_height_mm} mm")
    print(f"  Depth:      {group.IGU_depth_mm} mm")
    print(f"  Area (1):   {stats['average_area_per_igu']:.3f} m²")
    print(f"  Area (all): {stats['total_IGU_surface_area_m2']:.3f} m² (Total Batch)")
    
    print(f"\n{C_HEADER}Build-up & Materials:{C_RESET}")
    print(f"  Glazing:    {group.glazing_type}")
    print(f"  Glass:      {group.glass_type_outer} (outer), {group.glass_type_inner} (inner)")
    if group.thickness_centre_mm:
         print(f"              {group.thickness_centre_mm} mm (centre)")
    print(f"  Cavity:     {group.cavity_thickness_mm} mm")
    if group.cavity_thickness_2_mm:
        print(f"              {group.cavity_thickness_2_mm} mm (2nd cavity)")
    print(f"  Spacer:     {group.spacer_material}")
    print(f"  Sealants:   Primary={seal_geometry.primary_thickness_mm}x{seal_geometry.primary_width_mm}mm")
    print(f"              Secondary Type={group.sealant_type_secondary}, Width={seal_geometry.secondary_width_mm}mm")
    print(f"              Sec. Thickness={seal_vols['secondary_thickness_mm']} mm (derived)")
    
    print(f"\n{C_HEADER}Mass Information:{C_RESET}")
    print(f"  Per m²:     {default_mass_per_m2(group.glazing_type)} kg/m² (approx)")
    print(f"  Per IGU:    {masses['avg_mass_per_igu_kg']:.2f} kg")
    print(f"  Total Batch:{masses['total_mass_t']:.3f} tonnes")
    
    print(f"\n{C_HEADER}Sealant Volumes (Total Batch):{C_RESET}")
    print(f"  Primary:    {seal_vols['primary_volume_total_m3']:.4f} m³")
    print(f"  Secondary:  {seal_vols['secondary_volume_total_m3']:.4f} m³")


def print_scenario_overview(result: ScenarioResult):
    """
    Common reporting for all scenarios.
    """
    print(f"\n{Back.BLACK}{C_HEADER}{'='*60}")
    print(f"   SCENARIO RESULT: {result.scenario_name.upper()}")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    print(f"\n{C_HEADER}Yield Summary:{C_RESET}")
    print(f"  Initial Acceptable IGUs: {result.initial_igus:.0f}")
    print(f"  Initial Area:            {result.initial_area_m2:.3f} m²")
    print(f"  Final Output IGUs/Units: {result.final_igus:.0f}")
    print(f"  Final Output Area:       {result.final_area_m2:.3f} m²")
    print(f"  Yield (Area basis):      {result.yield_percent:.1f}%")
    print(f"  Initial Mass:            {result.initial_mass_kg/1000.0:.3f} t")
    print(f"  Final Mass:              {result.final_mass_kg/1000.0:.3f} t")
    
    print(f"\n{C_HEADER}Carbon Emissions (kg CO2e):{C_RESET}")
    for stage, val in result.by_stage.items():
        print(f"  {stage:<30} : {val:.3f}")
    
    print(f"{'-'*60}")
    print(f"  {Style.BRIGHT}TOTAL EMISSIONS              : {C_SUCCESS}{result.total_emissions_kgco2:.3f}{C_RESET} {Style.BRIGHT}kg CO2e{C_RESET}")
    
    if result.final_area_m2 > 0:
         print(f"  Intensity (per output m²)    : {result.total_emissions_kgco2 / result.final_area_m2:.3f} kgCO2e/m²")
    print(f"{'='*60}\n")
