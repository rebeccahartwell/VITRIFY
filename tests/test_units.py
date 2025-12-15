import sys
import os
import math

# Add src to path
sys.path.append(os.path.abspath("d:/VITRIFY/src"))

from igu_recovery.models import IGUGroup, SealGeometry, Location, ProcessSettings, TransportModeConfig, IGUCondition
from igu_recovery.utils.calculations import calculate_material_masses
from igu_recovery.scenarios import get_route_emissions

def test_mass_calculation():
    print("Testing Mass Calculation (mm -> m conversion)...")
    
    # Define a 1x1m IGU, Single Glazing, 6mm thick
    # Expected Volume: 1 * 1 * 0.006 = 0.006 m3
    # Expected Mass (Density 2500): 15.0 kg
    
    group = IGUGroup(
        quantity=1,
        unit_width_mm=1000.0,
        unit_height_mm=1000.0,
        glazing_type="single",
        glass_type_outer="annealed",
        glass_type_inner="annealed",
        coating_type="none",
        sealant_type_secondary="silicone", # factor 0.82
        spacer_material="aluminium",
        interlayer_type=None,
        condition=None, # not needed for mass
        thickness_outer_mm=6.0,
        thickness_inner_mm=0.0,
        cavity_thickness_mm=16.0,
        IGU_depth_mm=6.0, # single pane
        mass_per_m2_override=None
    )
    
    # Dummy Seal for calc (Primary 4x4mm, Secondary 4mm width)
    # Primary Area = 0.004 * 0.004 = 0.000016 m2
    # Perimeter = 4.0 m
    # Primary Vol = 0.000064 m3
    # Sealant Density ~1200? Let's check calculations.py const or just check it ran.
    # Actually density is loaded from constants. we need to trust the loaded value or mock it.
    # For now we check Glass which is dominant.
    
    seal = SealGeometry(primary_thickness_mm=4, primary_width_mm=4, secondary_width_mm=4)
    
    res = calculate_material_masses(group, seal)
    glass_kg = res["glass_kg"]
    
    # We know default GLASS_DENSITY_KG_M3 is usually 2500
    expected_mass = 1.0 * 1.0 * (6.0/1000.0) * 2500.0
    
    print(f"Glass Mass: {glass_kg:.4f} kg")
    
    # Allow small float diff
    if abs(glass_kg - expected_mass) < 0.01:
        print("PASS: Glass Mass calculation is correct (mm converted to m).")
    else:
        print(f"FAIL: Expected {expected_mass}, got {glass_kg}. Check Density or Conversion.")

def test_transport_emissions():
    print("\nTesting Transport Emissions (kg -> tonnes conversion)...")
    
    # 1000 kg payload, 100 km distance
    # Factor = 0.1 kgCO2e/tkm
    # Expected: (1000/1000) * 100 * 0.1 = 10.0 kgCO2e
    
    mass_kg = 1000.0
    
    # Mock Config
    from dataclasses import dataclass
    @dataclass 
    class MockConfig:
        truck_km: float = 100.0
        ferry_km: float = 0.0
        
    procs = ProcessSettings()
    procs.route_configs = {"test_route": MockConfig()}
    
    trans = TransportModeConfig(
        origin=Location(0,0), processor=Location(0,0), reuse=Location(0,0),
        emissionfactor_truck=0.1, # Mock factor
        emissionfactor_ferry=0.0,
        backhaul_factor=1.0 # Simple
    )
    
    e = get_route_emissions(mass_kg, "test_route", procs, trans)
    
    print(f"Emission Result: {e:.4f} kgCO2e")
    
    if abs(e - 10.0) < 0.001:
        print("PASS: Transport calculation is correct (kg -> tonne).")
    else:
        print(f"FAIL: Expected 10.0, got {e}")

if __name__ == "__main__":
    test_mass_calculation()
    test_transport_emissions()
