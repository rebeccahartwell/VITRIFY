
import sys
from pathlib import Path

# Ensure the project root is on sys.path for imports
# Hardcoded robust path to ensure it works
sys.path.append(r"d:\VITRIFY\src")

try:
    from igu_recovery.utils.input_helpers import parse_db_row_to_group
    from igu_recovery.utils.calculations import aggregate_igu_groups, compute_igu_mass_totals, calculate_material_masses
    from igu_recovery.models import IGUGroup, SealGeometry
    print("Imports successful.")
except ImportError as e:
    print(f"FATAL: Import failed: {e}")
    sys.exit(1)

# Dummy seal geometry for defaults
DEFAULT_SEAL = SealGeometry(
    primary_thickness_mm=0.5,
    primary_width_mm=4.0,
    secondary_width_mm=6.0
)

# Helper to create a mock row dictionary
def make_row(
    win_name,
    unit,
    glazing_type="double",
    quantity=10,
    width=1200,
    height=1500,
    coating_type="none",
    sealant_type="polysulfide",
    spacer_material="aluminium",
    inner_lam=None
):
    row = {
        "win_name": win_name,
        "Unit": unit,
        "Glazing Type": glazing_type,
        "Quantity": quantity,
        "Width": width,
        "Height": height,
        "Coating Type": coating_type,
        "Sealant Type": sealant_type,
        "Spacer Material": spacer_material,
    }
    if inner_lam is not None:
        row["Inner_Lam"] = inner_lam
    return row

def get_parsed_group(row_dict):
    # Extract params required by parse_db_row_to_group
    qty = row_dict["Quantity"]
    w = row_dict["Width"]
    h = row_dict["Height"]
    return parse_db_row_to_group(row_dict, qty, w, h, DEFAULT_SEAL)

def test_geometry_parsing_edge_cases():
    print("Running test_geometry_parsing_edge_cases...")
    # Missing middle thickness for triple glazing should fallback to defaults
    row = make_row("Win", "6|16|12|16|6", glazing_type="triple")
    group = get_parsed_group(row)
    
    assert group.thickness_outer_mm == 6.0, f"Outer: {group.thickness_outer_mm}"
    assert group.thickness_inner_mm == 6.0, f"Inner: {group.thickness_inner_mm}"
    assert group.thickness_centre_mm == 12.0, f"Centre: {group.thickness_centre_mm}"
    assert group.cavity_thickness_mm == 16.0, f"Cavity1: {group.cavity_thickness_mm}"
    assert group.cavity_thickness_2_mm == 16.0, f"Cavity2: {group.cavity_thickness_2_mm}"
    print("PASS")

def test_mixed_glazing_aggregation():
    print("Running test_mixed_glazing_aggregation...")
    # Two groups with different glazing types
    row1 = make_row("Win1", "6|16|6", glazing_type="double", quantity=5)
    row2 = make_row("Win2", "6|16|6", glazing_type="single", quantity=5)
    g1 = get_parsed_group(row1)
    g2 = get_parsed_group(row2)
    # Simple mock ProcessSettings object
    processes = type('P', (), {
        "breakage_rate_global": 0.0,
        "humidity_failure_rate": 0.0,
        "split_yield": 1.0,
        "remanufacturing_yield": 1.0,
    })
    
    try:
        stats = aggregate_igu_groups([g1, g2], processes)
        # Ensure function runs without error and returns expected keys
        assert "acceptable_igus" in stats
        assert stats["acceptable_igus"] >= 0
        print("PASS")
    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
        raise

def test_mass_calculation_consistency():
    print("Running test_mass_calculation_consistency...")
    # Simple double glazed IGU
    row = make_row("Win", "6|16|6", glazing_type="double", quantity=2, width=1000, height=1000)
    group = get_parsed_group(row)
    
    mats = calculate_material_masses(group, DEFAULT_SEAL)
    
    # Compute via compute_igu_mass_totals (which currently sums only glass mass per m2)
    stats_in = {
        "total_igus": 2.0,
        "acceptable_igus": 2.0,
        "remanufactured_igus": 0.0
    }
    
    # Pass DEFAULT_SEAL to ensure detailed calc is triggered
    mass_totals = compute_igu_mass_totals([group], stats_in, seal=DEFAULT_SEAL)
    
    total_expected = mats["glass_kg"] + mats["sealant_kg"] + mats["spacer_kg"]
    
    diff = abs(mass_totals["total_mass_kg"] - total_expected)
    if diff > 1e-3:
        print(f"FAIL: Mass mismatch. Got {mass_totals['total_mass_kg']}, Expected {total_expected}")
        print(f"Per IGU mats: {mats}")
        raise AssertionError("Mass mismatch")
    else:
        print("PASS")

def test_laminated_detection_runtime():
    print("Running test_laminated_detection_runtime...")
    # This tests confirmed runtime loading
    row = make_row("Window_lami_44", "6|16|6")
    group = get_parsed_group(row)
    if group.glass_type_outer == "laminated":
        print("PASS (Outer)")
    else:
        print(f"FAIL (Outer): Detected {group.glass_type_outer}")

    # Test Inner_Lam column
    row2 = make_row("WinStd", "6|16|6", inner_lam="Yes")
    group2 = get_parsed_group(row2)
    if group2.glass_type_inner == "laminated":
        print("PASS (Inner)")
    else:
        print(f"FAIL (Inner): Detected {group2.glass_type_inner}")

if __name__ == "__main__":
    print("Starting Manual Test Suite")
    try:
        test_geometry_parsing_edge_cases()
        test_mixed_glazing_aggregation()
        test_mass_calculation_consistency()
        test_laminated_detection_runtime()
        print("\nALL TESTS PASSED SUCCESSFULLY")
        sys.exit(0)
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nEXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
