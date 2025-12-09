from typing import Literal

# ============================================================================
# SETTINGS & CONSTANTS
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

# ============================================================================
# TYPES
# ============================================================================

# RepurposePreset defines the intensity preset for repurposing IGUs.
# It is used to select the appropriate CO2e per m² factor.
RepurposePreset = Literal["light", "medium", "heavy"]

GlazingType = Literal["double", "triple", "single"]
GlassType = Literal["annealed", "tempered", "laminated"]
CoatingType = Literal["none", "hard_lowE", "soft_lowE", "solar_control"]
SealantType = Literal["polysulfide", "polyurethane", "silicone", "combination", "combi"]
SpacerMaterial = Literal["aluminium", "steel", "warm_edge_composite"]
EdgeSealCondition = Literal["acceptable", "unacceptable", "not assessed"]

# TransportMode defines the mode of transport for route configurations.
# "HGV lorry"       = road-only
# "HGV lorry+ferry" = HGV lorry plus ferry leg(s).
TransportMode = Literal["HGV lorry", "HGV lorry+ferry"]

# ProcessLevel indicates whether calculations are at component or system level.
ProcessLevel = Literal["component", "system"]

# SystemPath indicates the overall system path: reuse or repurpose.
SystemPath = Literal["reuse", "repurpose"]
