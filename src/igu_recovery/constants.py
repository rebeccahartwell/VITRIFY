from typing import Literal
from .config import load_excel_config

# ============================================================================
# SETTINGS & CONSTANTS
# ============================================================================

# Load configuration immediately (blocking)
# We expect project_parameters.xlsx to exist and be fully populated.
_config = load_excel_config()

# Helper to fetch with strict error if missing
# This replaces hardcoded default values.
def _get(key):
    if key not in _config:
        # We allow GEOCODER_USER_AGENT to fall back or be hardcoded if not in excel, 
        # but for calculation factors requested by user, we crash.
        # Exception: types and literals are handled below.
        raise KeyError(f"Missing required parameter '{key}' in project_parameters.xlsx")
    return _config[key]

GEOCODER_USER_AGENT = _config.get("GEOCODER_USER_AGENT", "igu-reuse-tool/0.1 (CHANGE_THIS_TO_YOUR_EMAIL@DOMAIN)")

# Dismantling / Site
E_SITE_KGCO2_PER_M2 = _get("E_SITE_KGCO2_PER_M2")

# Processing / Repurposing
REMANUFACTURING_KGCO2_PER_M2 = _get("REMANUFACTURING_KGCO2_PER_M2")
DISASSEMBLY_KGCO2_PER_M2 = _get("DISASSEMBLY_KGCO2_PER_M2")
REPURPOSE_LIGHT_KGCO2_PER_M2 = _get("REPURPOSE_LIGHT_KGCO2_PER_M2")
REPURPOSE_MEDIUM_KGCO2_PER_M2 = _get("REPURPOSE_MEDIUM_KGCO2_PER_M2")
REPURPOSE_HEAVY_KGCO2_PER_M2 = _get("REPURPOSE_HEAVY_KGCO2_PER_M2")

# Repair
REPAIR_KGCO2_PER_M2 = _get("REPAIR_KGCO2_PER_M2")

# Recondition (Component Reuse)
RECONDITION_KGCO2_PER_M2 = _get("RECONDITION_KGCO2_PER_M2")

# Breaking (Recycling)
BREAKING_KGCO2_PER_M2 = _get("BREAKING_KGCO2_PER_M2")

# Stillage
STILLAGE_MANUFACTURE_KGCO2 = _get("STILLAGE_MANUFACTURE_KGCO2")
STILLAGE_LIFETIME_CYCLES = _get("STILLAGE_LIFETIME_CYCLES")
INCLUDE_STILLAGE_EMBODIED = _get("INCLUDE_STILLAGE_EMBODIED")

# Transport Factors
EMISSIONFACTOR_TRUCK = _get("EMISSIONFACTOR_TRUCK")
EMISSIONFACTOR_FERRY = _get("EMISSIONFACTOR_FERRY")
BACKHAUL_FACTOR = _get("BACKHAUL_FACTOR")

# Capacities
TRUCK_CAPACITY_T = _get("TRUCK_CAPACITY_T")
FERRY_CAPACITY_T = _get("FERRY_CAPACITY_T")

# Defaults
DISTANCE_FALLBACK_A_KM = _get("DISTANCE_FALLBACK_A_KM")
DISTANCE_FALLBACK_B_KM = _get("DISTANCE_FALLBACK_B_KM")

# IGU Masses
MASS_PER_M2_SINGLE = _get("MASS_PER_M2_SINGLE")
MASS_PER_M2_DOUBLE = _get("MASS_PER_M2_DOUBLE")
MASS_PER_M2_TRIPLE = _get("MASS_PER_M2_TRIPLE")

# Yield / Failure Rates
BREAKAGE_RATE_GLOBAL = _get("BREAKAGE_RATE_GLOBAL")
HUMIDITY_FAILURE_RATE = _get("HUMIDITY_FAILURE_RATE")
SPLIT_YIELD = _get("SPLIT_YIELD")
REMANUFACTURING_YIELD = _get("REMANUFACTURING_YIELD")

# Process Yields (formerly hardcoded)
YIELD_SYSTEM_REUSE = _get("YIELD_SYSTEM_REUSE")
YIELD_REPAIR = _get("YIELD_REPAIR")
YIELD_DISASSEMBLY_REUSE = _get("YIELD_DISASSEMBLY_REUSE")
YIELD_DISASSEMBLY_REMANUFACTURE = _get("YIELD_DISASSEMBLY_REMANUFACTURE")
YIELD_DISASSEMBLY_REPURPOSE = _get("YIELD_DISASSEMBLY_REPURPOSE")

# Processor Fractions (formerly hardcoded)
# Share of flow that goes to Float plant in closed-loop recycling
# (The rest, 1.0 - SHARE, is yield loss)
SHARE_CULLET_FLOAT = _get("SHARE_CULLET_FLOAT") 

# Open-loop shares
SHARE_CULLET_OPEN_LOOP_GW = _get("SHARE_CULLET_OPEN_LOOP_GW")
SHARE_CULLET_OPEN_LOOP_CONT = _get("SHARE_CULLET_OPEN_LOOP_CONT")

# Glass reprocessing
FLOAT_GLASS_REPROCESSING_KGCO2_PER_KG = (_get("FLOAT_GLASS_REPROCESSING"))

# Logistics
IGUS_PER_STILLAGE = _get("IGUS_PER_STILLAGE")
STILLAGE_MASS_EMPTY_KG = _get("STILLAGE_MASS_EMPTY_KG")
MAX_TRUCK_LOAD_KG = _get("MAX_TRUCK_LOAD_KG")

# Modes (Strings)
ROUTE_A_MODE = _get("ROUTE_A_MODE")
ROUTE_B_MODE = _get("ROUTE_B_MODE")

# Installation
INSTALL_SYSTEM_KGCO2_PER_M2 = _get("INSTALL_SYSTEM_KGCO2_PER_M2")

# Densities
GLASS_DENSITY_KG_M3 = _get("GLASS_DENSITY_KG_M3")
SEALANT_DENSITY_KG_M3 = _get("SEALANT_DENSITY_KG_M3")
SPACER_MASS_PER_M_KG = _get("SPACER_MASS_PER_M_KG")

# Process Energy (Assembly)
PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2 = _get("PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2")

# Material Emission Factors (kgCO2e/kg unless specified)
# From Image Data
EF_MAT_SPACER_ALU = _get("EF_MAT_SPACER_ALU")
EF_MAT_SPACER_STEEL = _get("EF_MAT_SPACER_STEEL")
EF_MAT_SPACER_SWISS = _get("EF_MAT_SPACER_SWISS")
EF_MAT_PVB = _get("EF_MAT_PVB")
EF_MAT_SEALANT = _get("EF_MAT_SEALANT")

# Glass Materials
EF_MAT_GLASS_VIRGIN = _get("EF_MAT_GLASS_VIRGIN")   # Soda-lime glass (0% RC)
EF_MAT_GLASS_100RC = _get("EF_MAT_GLASS_100RC")     # Soda-lime glass (100% RC)

# Process Increments (kgCO2e/kg of glass processed? or m2?)
# Image says: Toughened Glass +0.39, Coated Glass +0.27, Laminated +0.30
# The units in image column "A1-A2 [kgCO2/kg]" but Toughened/Coated might be per kg or per m2. 
# Typically processes like toughening are per kg or m2. Image shows +0.39 in a column that implies addition to base.
# We will assume /kg for now to match the glass base, but check usage.
EF_PROCESS_COATING = _get("EF_PROCESS_COATING")
EF_PROCESS_TOUGHENING = _get("EF_PROCESS_TOUGHENING")
EF_PROCESS_LAMINATING = _get("EF_PROCESS_LAMINATING")

DECIMALS = _get("DECIMALS")

# ============================================================================
# TYPES (Code constructs, not excel parameters)
# ============================================================================

RepurposePreset = Literal["Light", "Medium", "Heavy"]
GlazingType = Literal["double", "triple", "single"]
GlassType = Literal["annealed", "tempered", "laminated"]
CoatingType = Literal["none", "hard_lowE", "soft_lowE", "solar_control"]
SealantType = Literal["polysulfide", "polyurethane", "silicone", "combination", "combi"]
SpacerMaterial = Literal["aluminium", "steel", "warm_edge_composite"]
EdgeSealCondition = Literal["acceptable", "unacceptable", "not assessed"]
TransportMode = Literal["HGV lorry", "HGV lorry+ferry"]
ProcessLevel = Literal["component", "system"]
SystemPath = Literal["reuse", "repurpose"]
