import logging
import sys

# Append parent dir to sys.path to allow imports from sibling modules if executed directly
# But better to assume executed as module or package.
# We will assume python -m igu_recovery.main

from .constants import ROUTE_A_MODE, ROUTE_B_MODE
from .models import (
    ProcessSettings, TransportModeConfig, IGUGroup, FlowState
)
import pandas as pd
import os
import re
from .utils.input_helpers import (
    prompt_choice, prompt_location, prompt_igu_source, define_igu_system_from_manual,
    define_igu_system_from_database, ask_igu_condition_and_eligibility, print_igu_geometry_overview,
    print_scenario_overview, print_header, prompt_seal_geometry, parse_db_row_to_group,
    prompt_yes_no, style_prompt, C_SUCCESS, C_RESET, C_HEADER
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
from .models import IGUCondition

logger = logging.getLogger(__name__)

def run_automated_analysis(processes: ProcessSettings):
    """
    Automated loop through all products in database and all scenarios.
    """
    print_header("Step 2: Automated Analysis Configuration (Batch Mode)")
    
    # 1. Load Database
    db_path = r'd:\VITRIFY\data\saint_gobain\saint gobain product database.xlsx'
    if not os.path.exists(db_path):
        logger.error(f"Database file not found at {db_path}")
        return

    try:
        df = pd.read_excel(db_path)
    except Exception as e:
        logger.error(f"Error reading database: {e}")
        return
        
    if 'win_name' not in df.columns:
         logger.error("Invalid database format: 'win_name' column missing.")
         return
    
    print(f"\n{C_SUCCESS}Loaded {len(df)} products from database.{C_RESET}")
    
    # 2. Global Inputs
    print_header("Global Inputs (Applied to ALL products)")
    
    # Locations
    origin = prompt_location("project origin (Global)")
    processor = prompt_location("processor location (Global)")
    transport = TransportModeConfig(origin=origin, processor=processor, reuse=processor)
    
    # Transport Modes
    print("\nSelect Transport Modes (Global):")
    processes.route_A_mode = prompt_choice("Route A (origin->processor)", ["HGV lorry", "HGV lorry+ferry"], default=ROUTE_A_MODE) # type: ignore
    processes.route_B_mode = prompt_choice("Route B (processor->destination)", ["HGV lorry", "HGV lorry+ferry"], default=ROUTE_B_MODE) # type: ignore
    
    # Truck Preset
    print("\nSelect HGV lorry emission factor preset:")
    truck_preset = prompt_choice("HGV lorry emission preset", ["defra_2024", "legacy_rigid", "best_diesel", "ze_truck"], default="defra_2024")
    
    if truck_preset == "defra_2024": transport.emissionfactor_truck = 0.098
    elif truck_preset == "legacy_rigid": transport.emissionfactor_truck = 0.175
    elif truck_preset == "best_diesel": transport.emissionfactor_truck = 0.080
    elif truck_preset == "ze_truck": transport.emissionfactor_truck = 0.024
    
    # Global Reuse Destination
    reuse_dst = prompt_location("Global Reuse/Recycling Destination (Start->Processor->Here)")
    transport.reuse = reuse_dst
    
    # Seal Geometry
    seal_geometry = prompt_seal_geometry()
    
    # Dimensions (Unit)
    print(f"\n{C_HEADER}Global Unit Dimensions for Simulation{C_RESET}")
    print("To make results comparable, define a standard IGU size and quantity per product run.")
    try:
        total_igus = int(input(style_prompt("Quantity per product [default=1]: ") or "1"))
        unit_width_mm = float(input(style_prompt("Width (mm) [default=1000]: ") or "1000"))
        unit_height_mm = float(input(style_prompt("Height (mm) [default=1000]: ") or "1000"))
    except ValueError:
        logger.error("Invalid input. Using defaults (1 unit, 1m x 1m).")
        total_igus = 1
        unit_width_mm = 1000.0
        unit_height_mm = 1000.0

    # Conditions
    print(f"\n{C_HEADER}Global Condition Assumptions{C_RESET}")
    cond_edge = prompt_choice("Visible edge seal condition", ["acceptable", "unacceptable", "not assessed"], default="acceptable")
    cond_fog = prompt_yes_no("Visible fogging?", default=False)
    cond_cracks = prompt_yes_no("Cracks or chips present?", default=False)
    cond_reuse = prompt_yes_no("Reuse allowed?", default=True)
    cond_age = 20.0
    
    global_condition = IGUCondition(
        visible_edge_seal_condition=cond_edge, # type: ignore
        visible_fogging=cond_fog,
        cracks_chips=cond_cracks,
        age_years=cond_age,
        reuse_allowed=cond_reuse
    )
    
    # 3. Execution Loop
    results = []
    scenarios = [
        ("System Reuse", run_scenario_system_reuse),
        ("Component Reuse", run_scenario_component_reuse),
        ("Component Repurpose", run_scenario_component_repurpose),
        ("Closed-loop Recycling", run_scenario_closed_loop_recycling),
        ("Open-loop Recycling", run_scenario_open_loop_recycling)
    ]
    
    # Setup Reports Dir
    reports_dir = r"d:\VITRIFY\reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    print_header(f"Starting Analysis of {len(df)} products x {len(scenarios)} scenarios...")
    
    for idx, row in df.iterrows():
        product_name = row['win_name']
        group_id = row.get('Group/ID', 'N/A')
        print(f"Processing ({idx+1}/{len(df)}): {product_name}...")
        
        # Product Results
        product_results = []
        
        # Create Group
        group = parse_db_row_to_group(row, total_igus, unit_width_mm, unit_height_mm, seal_geometry)
        group.condition = global_condition
        
        # Stats
        stats = aggregate_igu_groups([group], processes)
        masses = compute_igu_mass_totals([group], stats)
        
        # Init Flow
        flow_start = FlowState(
            igus=float(group.quantity),
            area_m2=stats["total_IGU_surface_area_m2"],
            mass_kg=masses["total_mass_kg"]
        )
        
        # Run Scenarios
        for sc_name, sc_func in scenarios:
            try:
                # Set specific args per scenario
                res = None
                if sc_name == "System Reuse":
                    res = run_scenario_system_reuse(processes, transport, group, flow_start, stats, masses, interactive=False)
                elif sc_name == "Component Reuse":
                    res = run_scenario_component_reuse(processes, transport, group, seal_geometry, flow_start, stats, interactive=False)
                elif sc_name == "Component Repurpose":
                    res = run_scenario_component_repurpose(processes, transport, group, flow_start, stats, interactive=False)
                elif sc_name == "Closed-loop Recycling":
                    res = run_scenario_closed_loop_recycling(processes, transport, group, flow_start, interactive=False)
                elif sc_name == "Open-loop Recycling":
                    res = run_scenario_open_loop_recycling(processes, transport, group, flow_start, interactive=False)
                
                if res:
                    entry = {
                        "Product Group": group_id,
                        "Product Name": product_name,
                        "Scenario": sc_name,
                        "Total Emissions (kgCO2e)": res.total_emissions_kgco2,
                        "Final Yield (%)": res.yield_percent,
                        "Final Mass (kg)": res.final_mass_kg,
                        "Intensity (kgCO2e/m2 output)": (res.total_emissions_kgco2 / res.final_area_m2) if res.final_area_m2 > 0 else 0
                    }
                    results.append(entry)
                    product_results.append(entry)
                
            except Exception as e:
                logger.error(f"Error processing {product_name} - {sc_name}: {e}")
                
        # Save Individual Report
        if product_results:
            sanitized_name = re.sub(r'[^\w\-_]', '_', str(product_name))
            p_file = os.path.join(reports_dir, f"report_{sanitized_name}.csv")
            pd.DataFrame(product_results).to_csv(p_file, index=False)
            logger.info(f"Saved report: {p_file}")
                
    # 4. Save Report
    report_df = pd.DataFrame(results)
    out_file = "d:\\VITRIFY\\automated_analysis_report.csv"
    report_df.to_csv(out_file, index=False)
    
    print_header("Analysis Complete")
    print(f"Report saved to: {out_file}")
    if not report_df.empty:
        print(report_df.groupby("Scenario")[["Total Emissions (kgCO2e)", "Final Yield (%)"]].mean())


def main():
    # 1. LOGGING SETUP
    setup_logging(console_level=logging.INFO)
    
    # 2. PROCESS START BANNER
    print_header("IGU recovery environmental impact prototype – Start")
    
    processes = ProcessSettings()
    
    print("Welcome! Select operation mode:")
    mode = prompt_choice("Mode", ["Single Run (Interactive)", "Automated Analysis (Batch)"], default="Single Run (Interactive)")
    
    if mode == "Automated Analysis (Batch)":
        run_automated_analysis(processes)
        return

    # --- SINGLE RUN (Original Logic) ---

    # 2. IGU SOURCE SELECTION
    source_mode = prompt_igu_source()
    
    # 3. IGU SYSTEM DEFINITION
    if source_mode == "manual":
        group, seal_geometry = define_igu_system_from_manual()
    else:
        # database
        group, seal_geometry = define_igu_system_from_database()
    
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
        result = run_scenario_system_reuse(processes, transport, group, flow_start, stats, masses, interactive=True)
        print_scenario_overview(result)
        
    elif scenario_choice == "component_reuse":
        result = run_scenario_component_reuse(processes, transport, group, seal_geometry, flow_start, stats, interactive=True)
        print_scenario_overview(result)
        
    elif scenario_choice == "component_repurpose":
        result = run_scenario_component_repurpose(processes, transport, group, flow_start, stats, interactive=True)
        print_scenario_overview(result)
        
    elif scenario_choice == "closed_loop_recycling":
        result = run_scenario_closed_loop_recycling(processes, transport, group, flow_start, interactive=True)
        print_scenario_overview(result)
        
    elif scenario_choice == "open_loop_recycling":
        result = run_scenario_open_loop_recycling(processes, transport, group, flow_start, interactive=True)
        print_scenario_overview(result)

if __name__ == "__main__":
    main()
