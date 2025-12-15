import sys
sys.path.append(r"d:\VITRIFY\src")
import os
import shutil
import pandas as pd
from igu_recovery.main import execute_analysis_batch
from igu_recovery.models import ProcessSettings, TransportModeConfig, Location, SealGeometry, IGUCondition

def test_full_batch_execution():
    print("Running test_full_batch_execution...")
    
    # 1. Setup Dummy Data
    df = pd.DataFrame([
        {
            "win_name": "TestProduct_1",
            "Group/ID": "G1",
            "Quantity": 10,
            "Width": 1000,
            "Height": 1000,
            "Glazing Type": "double",
            "Coating Type": "none",
            "Sealant Type": "polysulfide",
            "Spacer Material": "aluminium"
        }
    ])
    
    # 2. Setup Context Objects
    processes = ProcessSettings()
    
    # Needs valid routes
    origin = Location(lat=51.5, lon=-0.1)
    processor = Location(lat=52.5, lon=-1.9)
    landfill = Location(lat=52.0, lon=-1.0)
    
    transport = TransportModeConfig(
        origin=origin,
        processor=processor,
        reuse=Location(lat=53.0, lon=-2.0), # Dummy reuse
        landfill=landfill,
        emissionfactor_truck=0.098
    )
    
    # Pre-configure routes (main.py batch expects them)
    from igu_recovery.main import configure_route, RouteConfig
    processes.route_configs = {
        "origin_to_processor": RouteConfig(mode="HGV lorry", truck_km=100.0, ferry_km=0.0),
        "processor_to_reuse": RouteConfig(mode="HGV lorry", truck_km=50.0, ferry_km=0.0),
        "processor_to_recycling": RouteConfig(mode="HGV lorry", truck_km=50.0, ferry_km=0.0),
        "origin_to_landfill": RouteConfig(mode="HGV lorry", truck_km=20.0, ferry_km=0.0),
        "processor_to_landfill": RouteConfig(mode="HGV lorry", truck_km=20.0, ferry_km=0.0)
    }
    
    seal_geometry = SealGeometry(
        primary_thickness_mm=3.0,
        primary_width_mm=4.0,
        secondary_width_mm=6.0
    )
    
    global_condition = IGUCondition(
        visible_edge_seal_condition="acceptable",
        visible_fogging=False,
        cracks_chips=False,
        age_years=20.0,
        reuse_allowed=True
    )
    
    recycling_dst = Location(lat=53.5, lon=-1.5)
    
    # 3. Define Temporary Output Dir
    tmp_reports = r"d:\VITRIFY\tests\tmp_reports"
    if os.path.exists(tmp_reports):
        shutil.rmtree(tmp_reports)
    os.makedirs(tmp_reports, exist_ok=True)
    
    try:
        # 4. Execute Batch
        execute_analysis_batch(
            df=df,
            processes=processes,
            transport=transport,
            total_igus=1,
            unit_width_mm=1000.0,
            unit_height_mm=1000.0,
            seal_geometry=seal_geometry,
            global_condition=global_condition,
            recycling_dst=recycling_dst,
            reports_dir=tmp_reports
        )
        
        # 5. Verification
        expected_file = os.path.join(tmp_reports, "automated_analysis_report.csv")
        if not os.path.exists(expected_file):
            raise AssertionError(f"Report file not created at {expected_file}")
            
        print(f"Report created: {expected_file}")
        
        # Check Scenarios
        res_df = pd.read_csv(expected_file)
        scenarios_found = res_df["Scenario"].unique()
        print(f"Scenarios found: {len(scenarios_found)}")
        print(scenarios_found)
        
        # Expect 11 scenarios
        if len(scenarios_found) != 11:
            raise AssertionError(f"Expected 11 scenarios, found {len(scenarios_found)}")
            
        print("PASS: Full batch execution verified.")
        
    finally:
        # Cleanup
        if os.path.exists(tmp_reports):
            shutil.rmtree(tmp_reports)
            print("Cleanup: Temporary reports deleted.")

if __name__ == "__main__":
    test_full_batch_execution()
