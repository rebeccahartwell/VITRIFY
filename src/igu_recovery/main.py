import logging
import sys

# Append parent dir to sys.path to allow imports from sibling modules if executed directly
# But better to assume executed as module or package.
# We will assume python -m igu_recovery.main

from .constants import ROUTE_A_MODE, ROUTE_B_MODE
from .models import (
    ProcessSettings, TransportModeConfig, IGUGroup, FlowState
)
from .utils.input_helpers import (
    prompt_choice, prompt_location, prompt_igu_source, define_igu_system_from_manual,
    ask_igu_condition_and_eligibility, print_igu_geometry_overview, print_scenario_overview, print_header
)
from .utils.calculations import (
    aggregate_igu_groups, compute_igu_mass_totals
)
from .scenarios import (
    run_scenario_system_reuse,
    run_scenario_component_reuse,
    run_scenario_component_repurpose,
    run_scenario_closed_loop_recycling,
    run_scenario_open_loop_recycling
)
from .logging_conf import setup_logging

logger = logging.getLogger(__name__)

def main():
    # 1. LOGGING SETUP
    setup_logging(console_level=logging.INFO)
    
    # 2. PROCESS START BANNER
    print_header("IGU recovery environmental impact prototype – Start")
    
    processes = ProcessSettings()
    
    # 2. IGU SOURCE SELECTION
    source_mode = prompt_igu_source()
    
    # 3. IGU SYSTEM DEFINITION
    # (Since database is not implemented, we always fall through to manual)
    group, seal_geometry = define_igu_system_from_manual()
    
    # 4. LOCATION DEFINITION
    print_header("Step 3: Locations & Transport Configuration")
    origin = prompt_location("project origin (Dismantling from Building / on-site removal)")
    processor = prompt_location("processor location (main processing site)")
    
    # Initial transport config (reuse destination is placeholder until scenario selection)
    transport = TransportModeConfig(origin=origin, processor=processor, reuse=processor)
    
    logger.info("\nLocations defined:")
    logger.info(f"  Origin   : {origin.lat:.6f}, {origin.lon:.6f}")
    logger.info(f"  Processor: {processor.lat:.6f}, {processor.lon:.6f}")
    
    # Transport Modes
    print("Select Transport Modes:")
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
    
    # Truck settings
    logger.info("\nSelect HGV lorry emission factor preset (DEFRA 2024 / Industry benchmarks):")
    logger.info("  defra_2024   = 0.098 kgCO2e/tkm (Artic >33t, Avg Laden) [DEFAULT]")
    logger.info("  legacy_rigid = 0.175 kgCO2e/tkm (Rigid >7.5t, Avg Laden)")
    logger.info("  best_diesel  = 0.080 kgCO2e/tkm (Modern efficient fleet)")
    logger.info("  ze_truck     = 0.024 kgCO2e/tkm (Electric, UK Grid 2023)")
    
    truck_preset = prompt_choice(
        "HGV lorry emission preset",
        ["defra_2024", "legacy_rigid", "best_diesel", "ze_truck"],
        default="defra_2024",
    )
    
    if truck_preset == "defra_2024":
        transport.emissionfactor_truck = 0.098
    elif truck_preset == "legacy_rigid":
        transport.emissionfactor_truck = 0.175
    elif truck_preset == "best_diesel":
        transport.emissionfactor_truck = 0.080
    elif truck_preset == "ze_truck":
        transport.emissionfactor_truck = 0.024
    
    logger.info(f"  -> Using truck factor: {transport.emissionfactor_truck} kgCO2e/tkm")
    
    # 5. GEOMETRY REPORTING
    print_igu_geometry_overview(group, seal_geometry, processes)
    
    # 6. CONDITIONS & ELIGIBILITY QUESTIONS
    condition = ask_igu_condition_and_eligibility()
    group.condition = condition
    
    # Re-calculate stats with conditions applied (not fully used for filtering in main flow yet, but available)
    stats = aggregate_igu_groups([group], processes)
    masses = compute_igu_mass_totals([group], stats)
    
    # 7. RECOVERY SCENARIO SELECTION
    print_header("Step 7: Recovery Scenario Selection")
    logger.info("Select one of the following scenarios:")
    logger.info("  a) System Reuse (Dismantle -> Transport -> Repair -> Transport -> Install)")
    logger.info("  b) Component Reuse (Dismantle -> Disassemble -> Recondition -> Assemble -> Install)")
    logger.info("  c) Component Repurpose (Dismantle -> Disassemble -> Repurpose -> Install)")
    logger.info("  d) Closed-loop Recycling (Dismantle -> Float Plant -> New Glass)")
    logger.info("  e) Open-loop Recycling (Dismantle -> Glasswool/Container)")
    
    scenario_choice = prompt_choice(
        "Select scenario",
        ["system_reuse", "component_reuse", "component_repurpose", "closed_loop_recycling", "open_loop_recycling"],
        default="system_reuse"
    )
    
    # INITIAL FLOW STATE (Pre-yield)
    # Start with total IGUs in batch? Or acceptable?
    # Usually we start with the whole batch trying to be recovered.
    # Yield losses at removal apply to the whole installation.
    initial_igus = float(group.quantity)
    initial_area = stats["total_IGU_surface_area_m2"]
    initial_mass = masses["total_mass_kg"]
    
    flow_start = FlowState(igus=initial_igus, area_m2=initial_area, mass_kg=initial_mass)
    
    if scenario_choice == "system_reuse":
        result = run_scenario_system_reuse(processes, transport, group, flow_start, stats, masses)
        print_scenario_overview(result)
        
    elif scenario_choice == "component_reuse":
        result = run_scenario_component_reuse(processes, transport, group, flow_start, stats)
        print_scenario_overview(result)
        
    elif scenario_choice == "component_repurpose":
        result = run_scenario_component_repurpose(processes, transport, group, flow_start, stats)
        print_scenario_overview(result)
        
    elif scenario_choice == "closed_loop_recycling":
        result = run_scenario_closed_loop_recycling(processes, transport, group, flow_start)
        print_scenario_overview(result)
        
    elif scenario_choice == "open_loop_recycling":
        result = run_scenario_open_loop_recycling(processes, transport, group, flow_start)
        print_scenario_overview(result)

if __name__ == "__main__":
    main()
