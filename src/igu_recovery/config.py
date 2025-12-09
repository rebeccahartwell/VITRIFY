import os
import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Path to the Excel file (relative to project root usually)
# We assume it is in the project root: d:\VITRIFY\project_parameters.xlsx
# Since this code is in d:\VITRIFY\src\igu_recovery\config.py
# The project root is two levels up.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "parameters_config", "project_parameters.xlsx")

def load_excel_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """
    Load configuration from Excel file.
    Expected columns: Key, Value, Unit, Description
    Returns a dictionary of Key -> Value
    """
    config = {}
    if not os.path.exists(path):
        logger.warning(f"Config file not found at {path}. Using defaults.")
        return config
        
    try:
        df = pd.read_excel(path)
        # Expecting columns Key and Value
        if "Key" in df.columns and "Value" in df.columns:
            for _, row in df.iterrows():
                key = str(row["Key"]).strip()
                val = row["Value"]
                # Basic type inference if needed, but usually pandas handles it.
                config[key] = val
            logger.info(f"Loaded {len(config)} parameters from {path}")
        else:
            logger.warning(f"Excel file {path} missing 'Key' or 'Value' columns.")
    except Exception as e:
        logger.error(f"Failed to load config from {path}: {e}")
        
    return config
