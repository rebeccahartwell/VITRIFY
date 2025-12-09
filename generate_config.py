import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
import pandas as pd
from igu_recovery import constants

def generate_excel():
    data = []
    
    # Iterate over module attributes
    for name in dir(constants):
        if name.startswith("_"): continue
        val = getattr(constants, name)
        
        # Filter for simple types (int, float, str, bool) that are uppercase (constants convention)
        if name.isupper() and isinstance(val, (int, float, str, bool)):
            # Special case: don't export TYPES or large blocks, just parameters
            data.append({
                "Key": name,
                "Value": val,
                "Unit": "-", # Placeholder
                "Description": "Imported from constants.py"
            })
            
    df = pd.DataFrame(data)
    
    # Reorder columns
    df = df[["Key", "Value", "Unit", "Description"]]
    
    output_file = "d:/VITRIFY/project_parameters.xlsx"
    print(f"Generating {output_file}...")
    df.to_excel(output_file, index=False)
    print("Done.")

if __name__ == "__main__":
    generate_excel()
