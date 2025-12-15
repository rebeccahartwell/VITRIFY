
import sys
import pandas as pd
import numpy as np

# Ensure project root is on sys.path
sys.path.append(r"d:\VITRIFY\src")

try:
    from igu_recovery.utils.input_helpers import format_and_clean_report_dataframe
    print("Imports successful.")
except ImportError as e:
    print(f"FATAL: Import failed: {e}")
    sys.exit(1)

def test_dataframe_formatting():
    print("Running test_dataframe_formatting...")
    
    # Create mock data mimicking the raw output
    data = {
        "Product Group": ["1.1", "1.1"],
        "Product Name": ["WinA", "WinA"],
        "Scenario": ["System Reuse", "Landfill"],
        "Total Emissions (kgCO2e)": [10.5, 50.0],
        "Final Yield (%)": [100.0, 0.0],
        "Final Mass (kg)": [200.0, 0.0],
        "Intensity (kgCO2e/m2 output)": [1.2, 0.0],
        "Emissions_Transport A": [10.0, 10.0],
        "Emissions_Dismantling/Removal": [5.0, 5.0],
        "Emissions_Landfill Transport": [np.nan, 20.0], # Test missing/NaN handling
        "Origin": ["LocA", "LocA"],
        "ExtraColumn": ["KeepMe", "KeepMe"] # Test preservation of extra columns
    }
    
    df = pd.DataFrame(data)
    
    # Run formatting
    formatted = format_and_clean_report_dataframe(df)
    
    # Checks
    cols = list(formatted.columns)
    
    # 1. Order Check
    print("Columns:", cols)
    assert cols[0] == "Product ID"
    assert cols[1] == "Product Name"
    assert cols[2] == "Scenario"
    assert "ExtraColumn" in cols
    assert cols[-1] == "ExtraColumn" or cols[-2] == "ExtraColumn" # It should be at the end, after defined ones
    
    # 2. Rename Check
    assert "[Stage] Removal" in cols
    assert "[Stage] Transport: Site->Processor" in cols
    
    # 3. Missing Column Fill Check
    assert "[Stage] Packaging" in cols # Was not in input, should be added
    assert (formatted["[Stage] Packaging"] == 0.0).all()
    
    # 4. NaNs filled
    assert not formatted.isnull().values.any()
    
    # 5. Rounding
    # Check if Total Emissions kept reasonable value
    assert formatted.loc[0, "Total Emissions (kgCO2e)"] == 10.5
    
    print("PASS")

if __name__ == "__main__":
    try:
        test_dataframe_formatting()
        print("ALL TESTS PASSED")
        sys.exit(0)
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
