import sys
import os

# Add src to path
sys.path.append(os.path.abspath("d:/VITRIFY/src"))

from igu_recovery.config import load_excel_config
from igu_recovery.utils.input_helpers import prompt_float

def test_param_loading():
    print("Testing Parameter Loading...")
    config = load_excel_config()
    
    key = "Default IGU Service Lifetime (years)"
    if key in config:
        val = config[key]
        print(f"PASS: Found '{key}' = {val}")
        
        if float(val) == 25.0:
            print("PASS: Value is 25.0 as expected.")
        else:
            print(f"FAIL: Value is {val}, expected 25.0")
    else:
        print(f"FAIL: Key '{key}' not found in config.")
        print("Keys found:", list(config.keys()))

if __name__ == "__main__":
    test_param_loading()
