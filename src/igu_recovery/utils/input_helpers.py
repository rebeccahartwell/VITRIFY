import logging
import requests
import pandas as pd
import re
import os
from typing import Optional, List, Tuple, Dict
from ..models import Location, IGUGroup, SealGeometry, SealantType, IGUCondition, ProcessSettings, ScenarioResult, BatchInput, TransportModeConfig, FlowState, RouteConfig
from ..constants import GEOCODER_USER_AGENT, DECIMALS
from ..config import load_excel_config
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
        
        logger.warning(f"Invalid answer '{s}'. Please enter y/n.")

def prompt_float(label: str, default: float) -> float:
    """
    Prompt user for a float value.
    """
    while True:
        s = input(style_prompt(f"{label} [default={default}]: ")).strip()
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            print(f"{C_ERROR}Invalid input. Please enter a number.{C_RESET}")

def prompt_igu_source() -> str:
    """
    Step 2: Ask for IGU source (manual vs database).
    """
    print_header("Step 1: IGU Source Selection")
    source = prompt_choice("Select IGU definition source", ["manual", "database"], default="database")
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

def laminated_glass_input(value, laminated_glass=0, PVB=0):
    if value is None:
        return laminated_glass, PVB
    try:
        s = str(value)
        if "." not in s:
            # No decimal: sum digits of whole number, after_digit = default
            return sum(int(d) for d in s if d.isdigit()), PVB
        before, after = s.split(".", 1)
        glass_thickness = sum(int(d) for d in before if d.isdigit())
        PVB_thickness = float(after[0]) * 0.38 if after and after[0].isdigit() else PVB
        return glass_thickness, PVB_thickness

    except (TypeError, ValueError):
        return laminated_glass, PVB

def define_igu_system_from_manual() -> Tuple[IGUGroup, SealGeometry]:
    """
    Step 3: Define IGU system (geometry + build-up + materials) manually.
    Prompts user for all IGU parameters and constructs the IGUGroup and SealGeometry.
    """
    print_header("Step 2: IGU System Definition (Manual)")
    # ! IGU Batch Description
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

    # ! Product Description
    glazing_type_str = prompt_choice(
        "Glazing type", ["double", "triple", "single"], default="double"
    )
    if glazing_type_str == "single":
        glass_outer_str = prompt_choice(
            "Glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )
        coating_outer_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )
        glass_inner_str = "annealed" # Check models.py if None is allowed, else defaulting to dummy
        glass_centre_str = "annealed" # Check models.py if None is allowed, else defaulting to dummy
        coating_inner_str = "none"
        coating_centre_str = "none"

    elif glazing_type_str == "double":
        glass_outer_str = prompt_choice(
            "Outer glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )

        coating_outer_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )
        glass_inner_str = prompt_choice(
            "Inner glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )
        coating_inner_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )
        glass_centre_str = "annealed"  # Check models.py if None is allowed, else defaulting to dummy
        coating_centre_str = "none"
    else: #glazing_type = "triple"
        glass_outer_str = prompt_choice(
            "Outer glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )
        coating_outer_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )
        glass_centre_str = prompt_choice(
            "Centre glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )
        coating_centre_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )
        glass_inner_str = prompt_choice(
            "Inner glass type", ["annealed", "tempered", "laminated"], default="annealed"
        )
        coating_inner_str = prompt_choice(
            "Coating type",
            ["none", "hard_lowE", "soft_lowE", "solar_control"],
            default="none",
        )


    # ! Pane Types Description
    outer_th_str: Optional[str] = None
    inner_th_str: Optional[str] = None
    centre_th_str: Optional[str] = None
    if glazing_type_str == "single":
        outer_th_str  = input(style_prompt("Pane thickness (mm): ")).strip()
        inner_th_str = None
        centre_th_str = None
        try:
            if glass_outer_str == "laminated":
                pane_thickness_single_mm = float(laminated_glass_input(outer_th_str)[0])
                PVB_thickness_mm = laminated_glass_input(outer_th_str)[1]
            else:
                pane_thickness_single_mm = float(outer_th_str)
        except ValueError:
            logger.error("Invalid numeric input for pane thickness.")
            raise SystemExit(1)

        pane_thickness_outer_mm = pane_thickness_single_mm
        pane_thickness_inner_mm = 0.0
        cavity_thickness_1_mm = 0.0
        pane_thickness_centre_mm: Optional[float] = None
        cavity_thickness_2_mm: Optional[float] = None
        IGU_depth_mm_val = pane_thickness_single_mm

    elif glazing_type_str == "double":
        outer_th_str = input(style_prompt("Outer pane thickness (mm): ")).strip()
        cavity1_str = input(style_prompt("Cavity thickness (mm): ")).strip()
        inner_th_str = input(style_prompt("Inner pane thickness (mm): ")).strip()
        centre_th_str = None
        try:
            if glass_outer_str == "laminated":
                pane_thickness_outer_mm = float(laminated_glass_input(outer_th_str)[0])
                PVB_thickness_outer_mm = laminated_glass_input(outer_th_str)[1]
            else:
                pane_thickness_outer_mm = float(outer_th_str)

            if glass_inner_str == "laminated":
                pane_thickness_inner_mm = float(laminated_glass_input(inner_th_str)[0])
                PVB_thickness_inner_mm = laminated_glass_input(inner_th_str)[1]
            else:
                pane_thickness_inner_mm = float(inner_th_str)

            cavity_thickness_1_mm = float(cavity1_str)

        except ValueError:
            logger.error("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        pane_thickness_centre_mm = None
        cavity_thickness_2_mm = None
        IGU_depth_mm_val = (
            pane_thickness_outer_mm + cavity_thickness_1_mm + pane_thickness_inner_mm
        )

    else:  # glazing_type_str == "triple"
        outer_th_str = input(style_prompt("Outer pane thickness (mm): ")).strip()
        cavity1_str = input(style_prompt("First cavity thickness (mm): ")).strip()
        centre_th_str = input(style_prompt("Centre pane thickness (mm): ")).strip()
        cavity2_str = input(style_prompt("Second cavity thickness (mm): ")).strip()
        inner_th_str = input(style_prompt("Inner pane thickness (mm): ")).strip()
        try:
            if glass_outer_str == "laminated":
                pane_thickness_outer_mm = float(laminated_glass_input(outer_th_str)[0])
                PVB_thickness_outer_mm = laminated_glass_input(outer_th_str)[1]
            else:
                pane_thickness_outer_mm = float(outer_th_str)

            cavity_thickness_1_mm = float(cavity1_str)

            if glass_inner_str == "laminated":
                pane_thickness_centre_mm = float(laminated_glass_input(centre_th_str)[0])
                PVB_thickness_centre_mm = laminated_glass_input(centre_th_str)[1]
            else:
                pane_thickness_centre_mm = float(centre_th_str)

            cavity_thickness_2_mm = float(cavity2_str)
            if glass_inner_str == "laminated":
                pane_thickness_inner_mm = float(laminated_glass_input(inner_th_str)[0])
                PVB_thickness_inner_mm = laminated_glass_input(inner_th_str)[1]
            else:
                pane_thickness_inner_mm = float(inner_th_str)

        except ValueError:
            logger.error("Invalid numeric input for pane or cavity thickness.")
            raise SystemExit(1)
        IGU_depth_mm_val = (
            pane_thickness_outer_mm
            + cavity_thickness_1_mm
            + pane_thickness_centre_mm
            + cavity_thickness_2_mm
            + pane_thickness_inner_mm
        )

    seal_geometry = prompt_seal_geometry()
    sealant_str = prompt_choice(
        "Secondary sealant type",
        ["polyisobutylene", "polysulfide", "silicone", "PIB/PS"],
        default="PIB/PS",
    )
    spacer_str = prompt_choice(
        "Spacer material",
        ["aluminium", "steel", "warm_edge_composite"],
        default="aluminium",
    )


    
    #  !Construct a temporary condition object to satisfy IGUGroup init (will be updated later)
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
        coating_type_outer=coating_outer_str,
        coating_type_centre=coating_centre_str,
        coating_type_inner=coating_inner_str,
        sealant_type_secondary=sealant_str,  # type: ignore[arg-type]
        spacer_material=spacer_str,  # type: ignore[arg-type]
        interlayer_type=None,
        condition=temp_condition,
        thickness_outer_mm=pane_thickness_outer_mm,
        thickness_outer_str=outer_th_str,
        thickness_inner_mm=pane_thickness_inner_mm,
        thickness_inner_str=inner_th_str,
        cavity_thickness_mm=cavity_thickness_1_mm,
        IGU_depth_mm=IGU_depth_mm_val,
        glass_type_centre=glass_centre_str,  # type: ignore[arg-type]
        mass_per_m2_override=None,
        thickness_centre_mm=pane_thickness_centre_mm,
        thickness_centre_str=centre_th_str,
        cavity_thickness_2_mm=cavity_thickness_2_mm,
        sealant_type_primary=None,
    )
    
    print_header("IGU System Defined")
    print(f"  {C_PROMPT}Quantity:{C_RESET} {group.quantity}, Size: {group.unit_width_mm}x{group.unit_height_mm} mm")
    print(f"  {C_PROMPT}Type:{C_RESET} {group.glazing_type}, Depth: {group.IGU_depth_mm} mm, Glazing Build-Up = {group.thickness_outer_str} | "
          f" {group.cavity_thickness_mm} | {group.thickness_centre_str} | {group.cavity_thickness_2_mm} | {group.thickness_inner_str}")
    
    return group, seal_geometry


def define_igu_system_from_database() -> Tuple[IGUGroup, SealGeometry]:
    """
    Step 3 (DB): Load from Database, select product, and prompt for quantities.
    """
    print_header("Step 2: IGU System Definition (Database)")
    # Get the current directory where the script is located
    current_directory =  os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # Build the path to the database file relative to the current directory
    db_path = os.path.join(current_directory, 'data', 'saint_gobain', 'saint gobain product database.xlsx')

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
    #! Defaults to "2.1_DGU_6_16_6_Bronze".
    selected_name = prompt_choice("Select Product", options, default=options[4])
    
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
    sealant_raw = str(row.get('Sealant', 'PIB/PS')).lower()
    sealant_type = "PIB/PS"
    # Basic matching
    if "silicone" in sealant_raw: sealant_type = "silicone"
    elif "polyurethane" in sealant_raw: sealant_type = "polyurethane"
    
    # 4. Coating
    # Check 'Solar Coating' or 'Low E Coating'
    # If anything other than "-" -> "soft_lowE" (assumption for modern coatings) or "solar_control"
    solar = str(row.get('Solar Coating', '-'))
    low_e = str(row.get('Low E Coating', '-'))
    coating_outer_str = "none"
    coating_inner_str = "none"
    coating_centre_str = "none"
    if solar != '-' and len(solar) > 2:
        coating_outer_str = "solar_control"
    elif low_e != '-' and len(low_e) > 2:
        coating_inner_str = "soft_lowE" # or hard_lowE, hard to tell from name alone without lookup
        
    # 5. Parse Unit thicknesses
    # "DGU 6 | 16 | 6 mm"
    unit_str = str(row.get('Unit', ''))
    # Extract numbers
    # Remove chars
    cleaned = re.sub(r'[A-Za-z]', '', unit_str).strip()
    parts = [p.strip() for p in cleaned.split('|') if p.strip()]
    # Defaults
    pane_thickness_outer_mm = 6.0
    outer_th_str = "6"
    pane_thickness_inner_mm = 6.0
    inner_th_str = "6"
    pane_thickness_centre_mm = None
    centre_th_str = None
    c1 = 16.0
    c2 = 0

    # ! Determine glass type and correct thickness (for lamination):
    try:
        if glazing_type == "double" and len(parts) == 3: #i.e double-glazing
            c1 = float(parts[1])
            outer_th_str = parts[0]
            inner_th_str = parts[2]
            if "." in parts[0]:
                t, pvb = laminated_glass_input(parts[0])
                pane_thickness_outer_mm = float(t)
                PVB_thickness_outer_mm = float(pvb)
            if "." in parts[2]:
                t, pvb = laminated_glass_input(parts[2])
                pane_thickness_inner_mm = float(t)
                PVB_thickness_inner_mm = float(pvb)
            g_type_outer = "laminated" if "." in parts[0] else "annealed"
            g_type_centre = "annealed" #NB, not called - used as dummy
            g_type_inner = "laminated" if "." in parts[2] else "annealed"
        elif glazing_type == "triple" and len(parts) == 5: #i.e triple-glazing
            c1 = float(parts[1])
            c2 = float(parts[3])
            outer_th_str = parts[0]
            centre_th_str = parts[2]
            inner_th_str = parts[4]
            if "." in parts[0]:
                t, pvb = laminated_glass_input(parts[0])
                pane_thickness_outer_mm = float(t)
                PVB_thickness_outer_mm = float(pvb)
            else:
                pane_thickness_outer_mm = float(outer_th_str)

            if "." in parts[2]:
                t, pvb = laminated_glass_input(parts[2])
                pane_thickness_centre_mm = float(t)
                PVB_thickness_centre_mm = float(pvb)
            else:
                pane_thickness_centre_mm = float(centre_th_str)

            if "." in parts[4]:
                t, pvb = laminated_glass_input(parts[4])
                pane_thickness_inner_mm = float(t)
                PVB_thickness_inner_mm = float(pvb)
            else:
                pane_thickness_inner_mm = float(inner_th_str)
            g_type_outer = "laminated" if "." in parts[0] else "annealed"
            g_type_centre = "laminated" if "." in parts[2] else "annealed"
            g_type_inner = "laminated" if "." in parts[4] else "annealed"
    except ValueError:
        logger.warning(f"Could not parse geometry from '{unit_str}'. Using defaults.")
    
    # Calculation of Depth
    depth = pane_thickness_outer_mm + c1 + pane_thickness_inner_mm
    if glazing_type == "triple":
        depth += pane_thickness_centre_mm + c2
    elif glazing_type == "single":
        depth = pane_thickness_outer_mm

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
        glass_type_outer=g_type_outer,
        glass_type_inner=g_type_inner,
        coating_type_outer=coating_outer_str,
        coating_type_centre=coating_centre_str,
        coating_type_inner=coating_inner_str,
        sealant_type_secondary=sealant_type, # type: ignore
        spacer_material=spacer_material, # type: ignore
        interlayer_type=None,
        condition=temp_condition,
        thickness_outer_mm=pane_thickness_outer_mm,
        thickness_outer_str=outer_th_str,
        thickness_inner_mm=pane_thickness_inner_mm,
        thickness_inner_str=inner_th_str,
        cavity_thickness_mm=c1,
        cavity_thickness_2_mm=c2,
        IGU_depth_mm=depth,
        glass_type_centre=g_type_centre,
        mass_per_m2_override=None,
        thickness_centre_mm=pane_thickness_centre_mm,
        thickness_centre_str=centre_th_str,
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
    
    # Load default lifetime from config
    config = load_excel_config()
    default_lifetime = float(config.get("Default IGU Service Lifetime (years)", 25.0))
    
    age_years = prompt_float(f"Approximate age of IGUs in years", default=default_lifetime)
    
    return IGUCondition(
        visible_edge_seal_condition=edge_cond_str,
        visible_fogging=fogging,
        cracks_chips=cracks,
        age_years=age_years,
        reuse_allowed=reuse_allowed
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
    masses = compute_igu_mass_totals([group], stats, seal=seal_geometry)
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

# Imports needed for configure_route (should be at top, but appending here for now)
# We will fix imports in next step to be clean.

def configure_route(name: str, origin: Location, destination: Location, interactive: bool = True) -> RouteConfig:
    """
    Configures a transport route. 
    Calculates air distance.
    If interactive, prompts for mode and specific distances (e.g. Ferry).
    Returns RouteConfig.
    """
    # Import locally to avoid circular import if calculations imports input_helpers
    from .calculations import haversine_km, get_osrm_distance
    
    dist_air = haversine_km(origin, destination)
    
    # Try OSRM first
    osrm_km, has_ferry = get_osrm_distance(origin, destination)
    
    ferry_detected_msg = ""
    default_mode = "HGV lorry"
    
    if osrm_km:
        est_road_km = int(osrm_km)
        dist_label = f"OSM Driving Distance: {osrm_km:.1f} km"
        if has_ferry:
            ferry_detected_msg = f" {C_HEADER}[!] OSRM detected a ferry crossing.{C_RESET}"
            default_mode = "HGV lorry+ferry"
        else:
            ferry_detected_msg = " (No ferry detected)"
    else:
        # Fallback
        est_road_km = int(dist_air * 1.3)
        dist_label = f"Estimated Road Distance (Air x 1.3): ~{est_road_km} km"
    
    print(f"\\n--- Configuring Route: {name} ---")
    print(f"  Origin: {origin.lat:.4f}, {origin.lon:.4f}")
    print(f"  Destination: {destination.lat:.4f}, {destination.lon:.4f}")
    print(f"  {dist_label}{ferry_detected_msg}")

    if not interactive:
        # Default fallback for non-interactive (Batch mode)
        final_km = osrm_km if osrm_km else float(est_road_km)
        
        if has_ferry:
            # Auto-configure ferry split for batch mode
            ferry_km_batch = 50.0
            truck_km_batch = max(0.0, final_km - ferry_km_batch)
            print(f"  -> Batch Mode: Auto-configuring {default_mode} (assumed 50km ferry).")
            return RouteConfig(mode="HGV lorry+ferry", truck_km=truck_km_batch, ferry_km=ferry_km_batch)
        else:
            return RouteConfig(mode="HGV lorry", truck_km=final_km, ferry_km=0.0)

    # INTERACTIVE MODE
    
    # 1. OSRM Success: Auto-accept to save user clicks (User Request)
    if osrm_km and not has_ferry:
        print(f"{C_SUCCESS}  -> Auto-accepted OSRM route: {osrm_km:.1f} km (Road){C_RESET}")
        return RouteConfig(mode="HGV lorry", truck_km=osrm_km, ferry_km=0.0)
        
    # 2. OSRM Success but FERRY detected: Must prompt for split (unavoidable ambiguity)
    if osrm_km and has_ferry:
         print(f"{C_HEADER}  -> Ferry detected! Please confirm split.{C_RESET}")

    # 3. OSRM Failed: Auto-accept fallback to avoid annoying prompt loops (User Request)
    if not osrm_km:
        print(f"{C_HEADER}  -> OSRM failed. Auto-accepting estimated road distance (Air x 1.3): {est_road_km} km.{C_RESET}")
        return RouteConfig(mode="HGV lorry", truck_km=float(est_road_km), ferry_km=0.0)

    # 4. Fallback Prompt (Should rarely be reached now, mainly if has_ferry)
    mode = prompt_choice(f"Transport Mode for {name}", ["HGV lorry", "HGV lorry+ferry"], default=default_mode)
    
    truck_km = 0.0
    ferry_km = 0.0
    
    if mode == "HGV lorry":
        # If we have osrm_km (but maybe user overrode ferry detection?), use it as default
        def_km = osrm_km if osrm_km else est_road_km
        truck_km_str = input(style_prompt(f"Road distance (km) [default={def_km:.1f}]: ")).strip()
        truck_km = float(truck_km_str) if truck_km_str else float(def_km)
    else:
        # Ferry
        print("For Ferry mode, please specify the split:")
        ferry_km_str = input(style_prompt("  Ferry distance (km) [default=50]: ")).strip()
        ferry_km = float(ferry_km_str) if ferry_km_str else 50.0
        
        # Remaining distance for truck
        def_road = max(0, (osrm_km if osrm_km else est_road_km) - ferry_km)
        truck_km_str = input(style_prompt(f"  Road distance (km) [default={def_road:.1f}]: ")).strip()
        truck_km = float(truck_km_str) if truck_km_str else float(def_road)
        
    return RouteConfig(mode=mode, truck_km=truck_km, ferry_km=ferry_km)

def format_and_clean_report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Refine the automated analysis report DataFrame:
     - Rename columns to readable format (Option A)
     - Reorder columns logically (ID -> KPI -> Stages -> Metadata)
     - Fill missing values with 0.0
     - Round numerics
    """
    # Create a copy to avoid SettingWithCopy warnings if slice
    df = df.copy()

    # 1. Rename Columns
    rename_map = {
        "Product Group": "Product ID",
        # "Product Name": "Product Name", # Stays
        # "Scenario": "Scenario", # Stays
        # "Total Emissions (kgCO2e/batch)": "Total Emissions (kgCO2e/batch)", # Stays
        #"Final Yield (%)": "Final Yield (%))", # Stays
        "Final Mass (kg)": "Recovered Mass (kg)",
        #Total Emission Intensity (kgCO2e/m2): Total Emission Intensity (kgCO2e/m2), #Stays"
        
        # Stages
        "Emissions_Building Site Dismantling": "[Stage] Building Site Dismantling",
        "Emissions_Transport A": "[Stage] Transport: Site->Processor",
        "Emissions_System Disassembly": "[Stage] System Disassembly",
        "Emissions_Repurpose": "[Stage] Repurpose",
        "Emissions_Recondition": "[Stage] Recondition",
        "Emissions_Repair": "[Stage] Repair",
        "Emissions_Glass Reprocessing": "[Stage] Glass Reprocessing",
        "Emissions_New Glass": "[Stage] New Glass",
        "Emissions_Re-Assembly": "[Stage] IGU Re-Assembly",
        "Emissions_Transport B": "[Stage] Transport: Processor->Next Use",
        "Emissions_Installation": "[Stage] Next Use Installation",
        "Emissions_Packaging": "[Stage] Packaging",
        "Emissions_Landfill Transport (Waste)": "[Stage] Transport: Landfill Disposal",
        "Emissions_Open-Loop Transport": "[Stage] Transport: Processor->Open-Loop Facility"
    }
    
    df.rename(columns=rename_map, inplace=True)
    
    # 2. Define Desired Column Order
    desired_order = [
        # Identifiers
        "Product ID", "Product Name", "Scenario",
        
        # Key KPIs
        "Total Emissions (kgCO2e/batch)", "Total Emission Intensity (kgCO2e/m2)", "Final Yield (%)", "Recovered Mass (kg)",
        
        # Stages (Chronological Flow)
        "[Stage] Building Site Dismantling",
        "[Stage] Transport: Site->Processor",
        "[Stage] System Disassembly",
        "[Stage] Repair",
        "[Stage] Recondition",
        "[Stage] Repurpose",
        "[Stage] Glass Reprocessing",
        "[Stage] New Glass",
        "[Stage] IGU Re-Assembly",
        "[Stage] Packaging",
        "[Stage] Transport: Processor->Next Use",
        "[Stage] Next Use Installation",
        "[Stage] Transport: Processor->Open-Loop Facility",
        "[Stage] Transport: Landfill Disposal",
        
        # Metadata
        "Origin", "Processor", "Route A Mode", "Route A Dist (km)"
    ]
    
    # 3. Apply Order and Fill Missing
    for col in desired_order:
        if col not in df.columns:
            df[col] = 0.0
            
    # Keep any extra columns at the end
    existing_cols = list(df.columns)
    extra_cols = [c for c in existing_cols if c not in desired_order]
    
    final_cols = desired_order + extra_cols
    df = df[final_cols]
    
    # Fill defaults
    df.fillna(0.0, inplace=True)
    
    # Round
    numeric_cols = df.select_dtypes(include=['float', 'int']).columns
    df[numeric_cols] = df[numeric_cols].round(3)
    
    return df


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
