
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 1. Load Report Save Location
current_directory =  os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Build the path to reports relative to the current directory
report_directory = os.path.join(current_directory, 'reports')


class CalculationAudit:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CalculationAudit, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        
        self.enabled = True
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = report_directory
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, f"audit_{self.session_id}.txt")
        self.initialized = True
        
        # Initialize file
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"=== EMISSION CALCULATION AUDIT LOG ===\n")
            f.write(f"Session: {self.session_id}\n")
            f.write("======================================\n\n")
            
    def log_calculation(self, context: str, formula: str, variables: Dict[str, Any], result: float, unit: str = ""):
        """
        Log a calculation step to the audit file.
        
        Args:
            context: Description of what is being calculated (e.g., "Transport: Origin -> Landfill")
            formula: Text representation of equation (e.g., "Mass * Dist * EF * Backhaul")
            variables: Dict of actual values used (e.g., {"Mass": 1.5, "Dist": 100})
            result: The final result
            unit: Unit of the result (e.g., "kgCO2e")
        """
        if not self.enabled:
            return

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {context}\n")
                f.write(f"  Formula: {formula}\n")
                
                # Format variables nicely
                vars_str = ", ".join([f"{k}={v}" for k, v in variables.items()])
                f.write(f"  Inputs:  {vars_str}\n")
                
                f.write(f"  Result:  {result:.4f} {unit}\n")
                f.write("-" * 40 + "\n")
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")

# Global Accessor
audit_logger = CalculationAudit()
