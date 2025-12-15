
import os
import sys

# Ensure 'src' is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # d:\VITRIFY
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

import random
import pandas as pd
from igu_recovery.models import (
    ProcessSettings, TransportModeConfig, RouteConfig, IGUCondition, 
    Location, SealGeometry, FlowState, IGUGroup
)
from igu_recovery.utils.input_helpers import (
    C_SUCCESS, C_RESET, C_HEADER, parse_db_row_to_group, print_header
)
from igu_recovery.utils.calculations import (
    aggregate_igu_groups, compute_igu_mass_totals
)
from igu_recovery.scenarios import (
    run_scenario_system_reuse,
    run_scenario_component_reuse,
    run_scenario_component_repurpose,
    run_scenario_closed_loop_recycling,
    run_scenario_open_loop_recycling,
    run_scenario_landfill
)

def random_lat_lon_europe():
    # Roughly Europe
    lat = random.uniform(36.0, 70.0)
    lon = random.uniform(-10.0, 30.0)
    return lat, lon

def generate_random_location():
    lat, lon = random_lat_lon_europe()
    return Location(lat=lat, lon=lon)

def generate_random_route_config():
    is_truck = random.random() > 0.2 # 80% truck
    if is_truck:
        dist = random.uniform(50.0, 1500.0)
        return RouteConfig(mode="HGV lorry", truck_km=dist, ferry_km=0.0)
    else:
        truck_dist = random.uniform(50.0, 1000.0)
        ferry_dist = random.uniform(20.0, 300.0)
        return RouteConfig(mode="HGV lorry+ferry", truck_km=truck_dist, ferry_km=ferry_dist)

def print_context(
    origin: Location, processor: Location, reuse: Location, recycling: Location, landfill: Location,
    processes: ProcessSettings, transport: TransportModeConfig, seal_geometry: SealGeometry, 
    condition: IGUCondition, total_igus: int, unit_width: float, unit_height: float,
    send_intact: bool
):
    print(f"\n{C_HEADER}>>> RANDOM SIMULATION CONTEXT GENERATED <<<{C_RESET}")
    print("-" * 50)
    print(f"{C_HEADER}1. Locations (Europe){C_RESET}")
    print(f"   Origin:      {origin.lat:.4f}, {origin.lon:.4f}")
    print(f"   Processor:   {processor.lat:.4f}, {processor.lon:.4f}")
    print(f"   Reuse Dst:   {reuse.lat:.4f}, {reuse.lon:.4f}")
    print(f"   Recycling:   {recycling.lat:.4f}, {recycling.lon:.4f}")
    print(f"   Landfill:    {landfill.lat:.4f}, {landfill.lon:.4f}")
    
    print(f"\n{C_HEADER}2. Routes{C_RESET}")
    for k, v in processes.route_configs.items():
        dist = v.truck_km + v.ferry_km
        print(f"   {k:<22}: {v.mode:<15} (Total: {dist:.1f} km)")
    
    print(f"\n{C_HEADER}3. Process Settings{C_RESET}")
    print(f"   Site Emissions: {processes.e_site_kgco2_per_m2} kgCO2/m2")
    print(f"   Stillage Cap:   {processes.igus_per_stillage} IGUs")
    print(f"   Truck EF:       {transport.emissionfactor_truck} kgCO2/tkm")
    
    print(f"\n{C_HEADER}4. Condition Assumptions{C_RESET}")
    print(f"   Edge Seal: {condition.visible_edge_seal_condition}")
    print(f"   Fogging:   {condition.visible_fogging}")
    print(f"   Cracks:    {condition.cracks_chips}")
    print(f"   Age:       {condition.age_years:.1f} years")
    print(f"   Reuse?:    {condition.reuse_allowed}")
    print(f"   Send Intact?: {send_intact} (Controls on-site breaking)")
    
    print(f"\n{C_HEADER}5. IGU Specs (Standard Unit){C_RESET}")
    print(f"   Quantity: {total_igus}")
    print(f"   Dims:     {unit_width}mm x {unit_height}mm")
    print(f"   Primary:  {seal_geometry.primary_thickness_mm}mm thick x {seal_geometry.primary_width_mm}mm width")
    print(f"   Second.:  {seal_geometry.secondary_width_mm}mm width")
    print("-" * 50)
    print("")

def main():
    print(f"{C_SUCCESS}Starting Random Test Runner...{C_RESET}")
    
    # 1. Load Database
    db_path = r'd:\VITRIFY\data\saint_gobain\saint gobain product database.xlsx'
    if not os.path.exists(db_path):
        print(f"Error: DB not found at {db_path}")
        return
    
    try:
        df = pd.read_excel(db_path)
        if 'Group/ID' in df.columns:
            df['Group/ID'] = df['Group/ID'].ffill()
    except Exception as e:
        print(f"Error reading DB: {e}")
        return

    results = []
    
    scenarios = [
        ("System Reuse", run_scenario_system_reuse),
        ("Component Reuse", run_scenario_component_reuse),
        ("Component Repurpose", run_scenario_component_repurpose),
        ("Closed-loop Recycling", run_scenario_closed_loop_recycling),
        ("Open-loop Recycling", run_scenario_open_loop_recycling),
        ("Straight to Landfill", run_scenario_landfill)
    ]

    print_header(f"Initialization: Loaded {len(df)} products from database.")
    
    # --- Global Random Context Generation ---
    
    # 1. Random Locations
    origin = generate_random_location()
    processor = generate_random_location()
    reuse_dst = generate_random_location()
    recycling_dst = generate_random_location()
    landfill_dst = generate_random_location()
    
    # 2. Random Process Settings
    processes = ProcessSettings(
        e_site_kgco2_per_m2=random.choice([0.15, 0.25, 0.5]),
        igus_per_stillage=random.choice([15, 20, 25, 30])
    )
    
    # 3. Random Routes
    processes.route_configs = {
        "origin_to_processor": generate_random_route_config(),
        "processor_to_reuse": generate_random_route_config(),
        "processor_to_recycling": generate_random_route_config(),
        "origin_to_landfill": generate_random_route_config(),
        "processor_to_landfill": generate_random_route_config(),
    }
    
    # 4. Random Transport Config
    truck_ef = random.choice([0.098, 0.175, 0.080, 0.024])
    transport = TransportModeConfig(
        origin=origin,
        processor=processor,
        reuse=reuse_dst,
        landfill=landfill_dst,
        emissionfactor_truck=truck_ef
    )
    
    # 5. Random Seal Geometry
    seal_geometry = SealGeometry(
        primary_thickness_mm=random.choice([4.0, 6.0, 8.0]),
        primary_width_mm=random.choice([10.0, 12.0, 14.0]),
        secondary_width_mm=random.choice([6.0, 8.0, 10.0])
    )
    
    # 6. Random Condition
    global_condition = IGUCondition(
        visible_edge_seal_condition=random.choice(["acceptable", "unacceptable", "not assessed"]),
        visible_fogging=random.choice([True, False]),
        cracks_chips=random.choice([True, False]),
        age_years=random.uniform(10.0, 40.0),
        reuse_allowed=random.choice([True, False])
    )
    
    # 7. Random Dims (Global Standard Unit)
    total_igus = random.randint(10, 100)
    unit_width_mm = random.choice([500.0, 1000.0, 1200.0, 1500.0])
    unit_height_mm = random.choice([1000.0, 1500.0, 2000.0, 2500.0])
    
    # 8. Random Intact Decision (Recycling)
    send_intact = random.choice([True, False])

    # PRINT CONTEXT
    print_context(
        origin, processor, reuse_dst, recycling_dst, landfill_dst, 
        processes, transport, seal_geometry, global_condition, 
        total_igus, unit_width_mm, unit_height_mm,
        send_intact
    )

    print(f"Running Analysis on {len(df)} products...")
    
    for idx, row in df.iterrows():
        product_name = row.get('win_name', 'Unknown')
        group_id = row.get('Group/ID', 'N/A')
        
        # Friendly progress indicator
        print(f"[{idx+1}/{len(df)}] Processing: {product_name}...", end="\r")
        
        # --- Execution using Global Context ---

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
                    # For Closed-loop, we use the recycling destination
                    transport_recycling = TransportModeConfig(**transport.__dict__)
                    transport_recycling.reuse = recycling_dst
                    res = run_scenario_closed_loop_recycling(processes, transport_recycling, group, flow_start, interactive=False, send_intact=send_intact)
                elif sc_name == "Open-loop Recycling":
                    res = run_scenario_open_loop_recycling(processes, transport, group, flow_start, interactive=False, send_intact=send_intact)
                elif sc_name == "Straight to Landfill":
                    res = run_scenario_landfill(processes, transport, group, flow_start, interactive=False)
                
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
                        "Origin": f"{transport.origin.lat:.4f},{transport.origin.lon:.4f}",
                        "Processor": f"{transport.processor.lat:.4f},{transport.processor.lon:.4f}",
                        "Route A Mode": processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).mode,
                        "Route A Dist (km)": processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).truck_km + processes.route_configs.get("origin_to_processor", RouteConfig(mode="N/A")).ferry_km,
                    }
                    
                    # Explode by_stage dictionary into columns
                    if res.by_stage:
                        for stage, val in res.by_stage.items():
                            entry[f"Emissions_{stage}"] = val
                            
                    results.append(entry)
                
            except Exception as e:
                # print newline to not overwrite progress
                print(f"\nError processing {product_name} - {sc_name}: {e}")

    # Clear progress line
    print(" " * 80, end="\r")
    
    # Save
    if not results:
        print("No results to save.")
        return

    report_df = pd.DataFrame(results)
    
    # Organize columns
    base_cols = [
        "Product Group", "Product Name", "Scenario", 
        "Total Emissions (kgCO2e)", "Final Yield (%)", "Final Mass (kg)", "Intensity (kgCO2e/m2 output)",
        "Origin", "Processor", "Route A Mode", "Route A Dist (km)"
    ]
    
    emission_cols = [c for c in report_df.columns if c.startswith("Emissions_")]
    emission_cols.sort()
    
    final_cols = base_cols + emission_cols
    final_cols = [c for c in final_cols if c in report_df.columns]
    
    report_df = report_df[final_cols]
    
    numeric_cols = report_df.select_dtypes(include=['float', 'int']).columns
    report_df[numeric_cols] = report_df[numeric_cols].round(3)

    out_file = "d:\\VITRIFY\\automated_analysis_report.csv"
    report_df.to_csv(out_file, index=False)
    
    print(f"\n{C_SUCCESS}Random Run Complete! Saved to: {out_file}{C_RESET}")
    print("\nSample Data (First 5 Rows):")
    print(report_df[["Product Name", "Scenario", "Total Emissions (kgCO2e)"]].head().to_string(index=False))

if __name__ == "__main__":
    main()
