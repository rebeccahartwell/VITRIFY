import logging
import sys

# Append parent dir to sys.path to allow imports from sibling modules if executed directly
# But better to assume executed as module or package.
# We will assume python -m igu_recovery.main

from .constants import ROUTE_A_MODE, ROUTE_B_MODE
from .models import (
    ProcessSettings, TransportModeConfig, IGUGroup, FlowState, RouteConfig, Location,
    SealGeometry, IGUCondition
)
import pandas as pd
import os
import re
from .utils.input_helpers import (
    prompt_choice, prompt_location, prompt_igu_source, define_igu_system_from_manual,
    define_igu_system_from_database, ask_igu_condition_and_eligibility, print_igu_geometry_overview,
    print_scenario_overview, print_header, prompt_seal_geometry, parse_db_row_to_group,
    prompt_yes_no, style_prompt, C_SUCCESS, C_RESET, C_HEADER, format_and_clean_report_dataframe,
    configure_route
)
from .utils.calculations import (
    aggregate_igu_groups, compute_igu_mass_totals, haversine_km, get_osrm_distance
)
from .scenarios import (
    run_scenario_system_reuse,
    run_scenario_component_reuse,
    run_scenario_component_repurpose,
    run_scenario_closed_loop_recycling,
    run_scenario_open_loop_recycling,
    run_scenario_landfill
)
from .logging_conf import setup_logging
from .visualization import Visualizer
from .reporting import save_scenario_md # NEW
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
    
    # Forward fill the Group/ID column to handle merged cells in Excel
    if 'Group/ID' in df.columns:
        df['Group/ID'] = df['Group/ID'].ffill()

    
    print(f"\n{C_SUCCESS}Loaded {len(df)} products from database.{C_RESET}")
    
    # 2. Global Inputs
    print_header("Global Inputs (Applied to ALL products)")
    
    # Locations
    origin = prompt_location("project origin (Global)")
    processor = prompt_location("processor location (Global)")
    transport = TransportModeConfig(origin=origin, processor=processor, reuse=processor)
    
    # Transport Configurations
    processes.route_configs = {}
    
    # Route A (Origin -> Processor)
    processes.route_configs["origin_to_processor"] = configure_route(
        "Origin -> Processor", origin, processor, interactive=False
    )
    
    # Route B (Processor -> Reuse) - Need reusedst first
    # Global Reuse Destination (for Reuse paths)
    reuse_dst = prompt_location("Global Reuse Destination (for Reuse/Repurpose)")
    transport.reuse = reuse_dst
    
    processes.route_configs["processor_to_reuse"] = configure_route(
        "Processor -> Reuse", processor, reuse_dst, interactive=False
    )

    # Global Recycling Destination (for Closed-loop path)
    recycling_dst = prompt_location("Global Recycling Destination (for Closed-loop)")
    
    processes.route_configs["processor_to_recycling"] = configure_route(
        "Processor -> Recycling", processor, recycling_dst, interactive=False
    )
    
    # Global Landfill Location (for waste/yield losses)
    landfill_dst = prompt_location("Global Landfill Location (for waste/yield losses)")
    transport.landfill = landfill_dst
    
    # Waste Routes
    processes.route_configs["origin_to_landfill"] = configure_route(
        "Origin -> Landfill", origin, landfill_dst, interactive=False
    )
    processes.route_configs["processor_to_landfill"] = configure_route(
        "Processor -> Landfill", processor, landfill_dst, interactive=False
    )
    
    # Truck Preset
    print("\nSelect HGV lorry emission factor preset:")
    truck_preset = prompt_choice("HGV lorry emission preset", ["defra_2024", "legacy_rigid", "best_diesel", "ze_truck"], default="defra_2024")
    
    if truck_preset == "defra_2024": transport.emissionfactor_truck = 0.098
    elif truck_preset == "legacy_rigid": transport.emissionfactor_truck = 0.175
    elif truck_preset == "best_diesel": transport.emissionfactor_truck = 0.080
    elif truck_preset == "ze_truck": transport.emissionfactor_truck = 0.024
    
    # Removed old global input prompts as they are now integrated above
    # transport.reuse / landfill set above
    
    # Seal Geometry
    seal_geometry = prompt_seal_geometry()
    
    # Dimensions (Unit)
    print(f"\n{C_HEADER}Global Unit Dimensions for Simulation{C_RESET}")
    print("To make results comparable, define a standard IGU size and count per product run.")
    try:
        total_igus = int(input(style_prompt("Number of IGUs [default=1]: ") or "1"))
        unit_width_mm = float(input(style_prompt("Width (mm) [default=1000]: ") or "1000"))
        unit_height_mm = float(input(style_prompt("Height (mm) [default=1000]: ") or "1000"))
        if total_igus < 1: raise ValueError("IGU count must be >= 1")
        if unit_width_mm <= 0 or unit_height_mm <= 0: raise ValueError("Dimensions must be positive")
    except ValueError as e:
        logger.error(f"Invalid input: {e}. Using defaults (1 unit, 1m x 1m).")
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
    execute_analysis_batch(
        df=df,
        processes=processes,
        transport=transport,
        total_igus=total_igus,
        unit_width_mm=unit_width_mm,
        unit_height_mm=unit_height_mm,
        seal_geometry=seal_geometry,
        global_condition=global_condition,
        recycling_dst=recycling_dst
    )

def execute_analysis_batch(
    df: pd.DataFrame,
    processes: ProcessSettings,
    transport: TransportModeConfig,
    total_igus: int,
    unit_width_mm: float,
    unit_height_mm: float,
    seal_geometry: SealGeometry,
    global_condition: IGUCondition,
    recycling_dst: Location,
    reports_dir: str = r"d:\VITRIFY\reports"
):
    scenarios = [
        # System Reuse Variants
        ("System Reuse (Direct)", run_scenario_system_reuse, {"repair_needed": False}),
        ("System Reuse (Repair)", run_scenario_system_reuse, {"repair_needed": True}),
        
        # Component Reuse
        ("Component Reuse", run_scenario_component_reuse, {}),
        
        # Component Repurpose Variants
        ("Repurpose (Light)", run_scenario_component_repurpose, {"repurpose_intensity": "light"}),
        ("Repurpose (Medium)", run_scenario_component_repurpose, {"repurpose_intensity": "medium"}),
        ("Repurpose (Heavy)", run_scenario_component_repurpose, {"repurpose_intensity": "heavy"}),
        
        # Closed-loop Recycling
        ("Closed-loop (Intact)", run_scenario_closed_loop_recycling, {"send_intact": True}),
        ("Closed-loop (Broken)", run_scenario_closed_loop_recycling, {"send_intact": False}),
        
        # Open-loop Recycling
        ("Open-loop (Intact)", run_scenario_open_loop_recycling, {"send_intact": True}),
        ("Open-loop (Broken)", run_scenario_open_loop_recycling, {"send_intact": False}),
        
        # Landfill
        ("Straight to Landfill", run_scenario_landfill, {})
    ]
    
    # Setup Reports Dir
    os.makedirs(reports_dir, exist_ok=True)
    
    results = []
    
    print_header(f"Starting Analysis of {len(df)} products x {len(scenarios)} scenarios...")
    
    for idx, row in df.iterrows():
        try:
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
            masses = compute_igu_mass_totals([group], stats, seal=seal_geometry)
            
            # Init Flow
            flow_start = FlowState(
                igus=float(group.quantity),
                area_m2=stats["total_IGU_surface_area_m2"],
                mass_kg=masses["total_mass_kg"]
            )
            
            # Run Scenarios
            for sc_name, sc_func, kwargs in scenarios:
                try:
                    # Set specific args per scenario
                    res = None
                    if sc_func == run_scenario_system_reuse:
                        res = run_scenario_system_reuse(processes, transport, group, flow_start, stats, masses, interactive=False, **kwargs)
                    elif sc_func == run_scenario_component_reuse:
                        res = run_scenario_component_reuse(processes, transport, group, seal_geometry, flow_start, stats, interactive=False, **kwargs)
                    elif sc_func == run_scenario_component_repurpose:
                        res = run_scenario_component_repurpose(processes, transport, group, flow_start, stats, interactive=False, **kwargs)
                    elif sc_func == run_scenario_closed_loop_recycling:
                        # For Closed-loop, we use the recycling destination
                        transport_recycling = TransportModeConfig(**transport.__dict__)
                        transport_recycling.reuse = recycling_dst
                        res = run_scenario_closed_loop_recycling(processes, transport_recycling, group, flow_start, interactive=False, **kwargs)
                    elif sc_func == run_scenario_open_loop_recycling:
                        res = run_scenario_open_loop_recycling(processes, transport, group, flow_start, interactive=False, **kwargs)
                    elif sc_func == run_scenario_landfill:
                        res = run_scenario_landfill(processes, transport, group, flow_start, interactive=False, **kwargs)
                    
                    if res:
                        entry = {
                            "Product Group": group_id,
                            "Product Name": product_name,
                            "Scenario": sc_name,
                            "Total Emissions (kgCO2e)": res.total_emissions_kgco2,
                            "Final Yield (%)": res.yield_percent,
                            "Final Mass (kg)": res.final_mass_kg,
                            "Intensity (kgCO2e/m2 output)": (res.total_emissions_kgco2 / res.final_area_m2) if res.final_area_m2 > 0 else 0,
                            # Route Metadata
                            "Origin": f"{transport.origin.lat},{transport.origin.lon}",
                            "Processor": f"{transport.processor.lat},{transport.processor.lon}",
                            "Route A Mode": processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).mode,
                            "Route A Dist (km)": processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).truck_km + processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).ferry_km,
                        }
                        
                        # Explode by_stage dictionary into columns
                        if res.by_stage:
                            for stage, val in res.by_stage.items():
                                entry[f"Emissions_{stage}"] = val
                                
                        results.append(entry)
                        product_results.append(entry)
                    
                except Exception as e:
                    logger.error(f"Error processing {product_name} - {sc_name}: {e}")
        except Exception as e_prod:
            logger.error(f"CRITICAL ERROR processing product row {idx}: {e_prod}. Skipping product.")
            continue
                
    # 4. Save Report
    if not results:
        print("No results to save.")
        return

    report_df = pd.DataFrame(results)
    
    # --- PHASE 4: REPORT REFINEMENT (Option A) ---
    report_df = format_and_clean_report_dataframe(report_df)

    basename = "automated_analysis_report"
    out_file = os.path.join(reports_dir, f"{basename}.csv")
    
    try:
        report_df.to_csv(out_file, index=False)
        print(f"Report saved to: {out_file}")
    except PermissionError:
        # Fallback if file is locked
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback_file = f"d:\\VITRIFY\\{basename}_{ts}.csv"
        logger.warning(f"Could not save to {out_file} (File Locked?). Saving to {fallback_file} instead.")
        report_df.to_csv(fallback_file, index=False)
        print(f"Report saved to: {fallback_file}")
        out_file = fallback_file # Update for visualization linkage
    if not report_df.empty:
        # Show breakdown of mean total emissions by scenario
        print(report_df.groupby("Scenario")[["Total Emissions (kgCO2e)", "Yield (%)"]].mean())
    
    # --- VISUALIZATION (BATCH) ---
    try:
        vis = Visualizer(mode="batch_run")
        vis.plot_batch_summary(report_df)
        print(f"\nCharts saved to: {vis.session_dir}")
    except Exception as e:
        logger.error(f"Batch visualization failed: {e}")


def main():
    # 1. LOGGING SETUP
    setup_logging(console_level=logging.INFO)
    
    # 2. PROCESS START BANNER
    print_header("IGU recovery environmental impact prototype – Start")
    
    processes = ProcessSettings()
    
    print("Welcome! Select operation mode:")
    mode = prompt_choice("Mode", ["Single Run (Interactive)", "Automated Analysis (Batch)"], default="Single Run (Interactive)")
    
    # Setup process settings dict
    processes.route_configs = {}
    
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
    
    # Global Landfill
    print("\\nHow do you want to define Landfill locations?")
    landfill_mode = prompt_choice(
        "Landfill Mode", 
        ["Specific Global Location", "Default Local Landfills (50km from source)"], 
        default="Specific Global Location"
    )
    
    landfill_dst = None
    use_default_landfill = False
    
    if landfill_mode == "Specific Global Location":
        landfill_dst = prompt_location("Global Landfill Location (for waste/yield losses)")
        transport.landfill = landfill_dst
    else:
        # Default Mode
        use_default_landfill = True
        # Create dummy location so check passes
        landfill_dst = Location(lat=0.0, lon=0.0)
        transport.landfill = landfill_dst
        print(f"{C_SUCCESS}  -> Using default 50km local landfill assumptions.{C_RESET}")
    
    logger.info("\nLocations defined:")
    logger.info(f"  Origin   : {origin.lat:.6f}, {origin.lon:.6f}")
    logger.info(f"  Processor: {processor.lat:.6f}, {processor.lon:.6f}")
    
    logger.info(f"  Processor: {processor.lat:.6f}, {processor.lon:.6f}")
    
    # Configure Routes Interactively
    
    # 1. Route A: Origin -> Processor
    processes.route_configs["origin_to_processor"] = configure_route(
        "Origin -> Processor", origin, processor, interactive=True
    )
    

    
    # Waste Routes
    if use_default_landfill:
        # Manually configure 50km routes
        processes.route_configs["origin_to_landfill"] = RouteConfig(mode="HGV lorry", truck_km=50.0, ferry_km=0.0)
        processes.route_configs["processor_to_landfill"] = RouteConfig(mode="HGV lorry", truck_km=50.0, ferry_km=0.0)
        print(f"\\n--- Configured Waste Routes (Default 50km) ---")
        print(f"  Origin -> Landfill: 50.0 km")
        print(f"  Processor -> Landfill: 50.0 km")
    else:
        # Specific Location
        processes.route_configs["origin_to_landfill"] = configure_route(
            "Origin -> Landfill", origin, landfill_dst, interactive=True
        )
        processes.route_configs["processor_to_landfill"] = configure_route(
            "Processor -> Landfill", processor, landfill_dst, interactive=True
        )
    
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
    masses = compute_igu_mass_totals([group], stats, seal_geometry)
    
    # 7. RECOVERY SCENARIO SELECTION
    print_header("Step 7: Recovery Scenario Selection")
    logger.info("Select one of the following scenarios:")
    logger.info("  a) System Reuse (Dismantle -> Transport -> Repair -> Transport -> Install)")
    logger.info("  b) Component Reuse (Dismantle -> Disassemble -> Recondition -> Assemble -> Install)")
    logger.info("  c) Component Repurpose (Dismantle -> Disassemble -> Repurpose -> Install)")
    logger.info("  d) Closed-loop Recycling (Dismantle -> Float Plant -> New Glass)")
    logger.info("  e) Open-loop Recycling (Dismantle -> Glasswool/Container)")
    logger.info("  f) Straight to Landfill (Dismantle -> Landfill)")
    
    scenario_choice = prompt_choice(
        "Select scenario",
        ["system_reuse", "component_reuse", "component_repurpose", "closed_loop_recycling", "open_loop_recycling", "landfill"],
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
        save_scenario_md(result) # NEW
        
    elif scenario_choice == "component_reuse":
        result = run_scenario_component_reuse(processes, transport, group, seal_geometry, flow_start, stats, interactive=True)
        print_scenario_overview(result)
        save_scenario_md(result) # NEW
        
    elif scenario_choice == "component_repurpose":
        result = run_scenario_component_repurpose(processes, transport, group, flow_start, stats, interactive=True)
        print_scenario_overview(result)
        save_scenario_md(result) # NEW
        
    elif scenario_choice == "closed_loop_recycling":
        result = run_scenario_closed_loop_recycling(processes, transport, group, flow_start, interactive=True)
        print_scenario_overview(result)
        save_scenario_md(result) # NEW
        
    elif scenario_choice == "open_loop_recycling":
        result = run_scenario_open_loop_recycling(processes, transport, group, flow_start, interactive=True)
        print_scenario_overview(result)
        save_scenario_md(result) # NEW
        
    elif scenario_choice == "landfill":
        result = run_scenario_landfill(processes, transport, group, flow_start, interactive=True)
        print_scenario_overview(result)
        save_scenario_md(result) # NEW

    # 8. VISUALIZATION & COMPARISON
    print("\n" + "="*60)
    print("Post-Analysis Visualization")
    print("="*60)
    print("Would you like to:")
    print("  a) Visualize emissions for this scenario only")
    print("  b) Compare this scenario with ALL other scenarios (will calculate others now)")
    print("  c) Exit")
    
    viz_choice = prompt_choice("Select option", ["a", "b", "c"], default="c")
    
    if viz_choice == "a":
        # Single Scenario Breakdown
        if 'result' in locals() and result:
            vis = Visualizer(mode="single_run")
            p_name = group.glazing_type
            vis.plot_single_scenario_breakdown(result, product_name=f"Manual Config: {p_name}")
            # print(f"Plot saved to: {vis.session_dir}")
        else:
            print("No result to visualize.")
            
    elif viz_choice == "b":
        print("\nCalculations running for comparisons...")
        
        comparison_results = []
        
        if "processor_to_reuse" not in processes.route_configs:
             print("\n(Comparison requires Reuse destination)")
             tgt_reuse = prompt_location("Reuse Destination")
             transport.reuse = tgt_reuse
             processes.route_configs["processor_to_reuse"] = configure_route("Processor -> Reuse", transport.processor, tgt_reuse, interactive=True)
             
        if "processor_to_recycling" not in processes.route_configs:
             print("\n(Comparison requires Recycling destination)")
             tgt_recycling = prompt_location("Recycling Destination")
             processes.route_configs["processor_to_recycling"] = configure_route("Processor -> Recycling", transport.processor, tgt_recycling, interactive=True)
        
        comparison_results = []
        
        # Define the list of scenarios to run (name, func)
        all_scenarios = [
            ("System Reuse", run_scenario_system_reuse),
            ("Component Reuse", run_scenario_component_reuse),
            ("Component Repurpose", run_scenario_component_repurpose),
            ("Closed-loop Recycling", run_scenario_closed_loop_recycling),
            ("Open-loop Recycling", run_scenario_open_loop_recycling),
            ("Straight to Landfill", run_scenario_landfill)
        ]
        
        for sc_name, sc_func in all_scenarios:
            t_copy = TransportModeConfig(**transport.__dict__)
            
            # Setup Specific Destinations for non-interactive run
            # We rely on processes.route_configs being set above.
            # We update t_copy.reuse/recycling logic if strictly needed for context, 
            # but emissions drive off route keys.
            if sc_name == "Straight to Landfill":
                t_copy.landfill = landfill_dst
            
            # Run
            try:
                # Dispatch based on signature
                res_cmp = None
                if sc_name == "System Reuse":
                    res_cmp = run_scenario_system_reuse(processes, t_copy, group, flow_start, stats, masses, interactive=False)
                elif sc_name == "Component Reuse":
                    res_cmp = run_scenario_component_reuse(processes, t_copy, group, seal_geometry, flow_start, stats, interactive=False)
                elif sc_name == "Component Repurpose":
                    res_cmp = run_scenario_component_repurpose(processes, t_copy, group, flow_start, stats, interactive=False)
                elif sc_name == "Closed-loop Recycling":
                    res_cmp = run_scenario_closed_loop_recycling(processes, t_copy, group, flow_start, interactive=False)
                elif sc_name == "Open-loop Recycling":
                    res_cmp = run_scenario_open_loop_recycling(processes, t_copy, group, flow_start, interactive=False)
                elif sc_name == "Straight to Landfill":
                    res_cmp = run_scenario_landfill(processes, t_copy, group, flow_start, interactive=False)
                
                if res_cmp:
                    comparison_results.append(res_cmp)
            except Exception as e:
                logger.error(f"Error calculating {sc_name} for comparison: {e}")
                
        # Print Text Table
        print("\n" + "-"*80)
        print(f"{'Scenario':<25} | {'Emissions (kgCO2e)':<20} | {'Yield %':<10}")
        print("-" * 60)
        for r in comparison_results:
             print(f"{r.scenario_name:<25} | {r.total_emissions_kgco2:<20.2f} | {r.yield_percent:<10.1f}")
        print("-" * 80)
        
        # Plot
        vis = Visualizer(mode="single_run")
        p_name = group.glazing_type
        vis.plot_scenario_comparison(comparison_results, product_name=f"Manual Config: {p_name}")

if __name__ == "__main__":
    main()
