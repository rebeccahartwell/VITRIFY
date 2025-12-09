
import pandas as pd
import os

# Define the data structure with Sections, Descriptions, and Units
# KEY: (Value, Unit, Section, Description, Name/Label)
# We keep the KEY identical to code for compatibility.

PARAMS = [
    # --- SECTION: GLOBAL ---
    {
        "Key": "GEOCODER_USER_AGENT",
        "Value": "igu-reuse-tool/0.1 (CHANGE_THIS_TO_YOUR_EMAIL@DOMAIN)",
        "Unit": "Text",
        "Section": "1. Global Settings",
        "Description": "User-agent string used for OpenStreetMap geocoding requests."
    },
    {
        "Key": "DECIMALS",
        "Value": 3,
        "Unit": "Integer",
        "Section": "1. Global Settings",
        "Description": "Number of decimal places to use for reporting results."
    },

    # --- SECTION: EMISSION FACTORS (PROCESS) ---
    {
        "Key": "E_SITE_KGCO2_PER_M2",
        "Value": 0.15,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions generated during on-site removal/dismantling of IGUs from the building."
    },
    {
        "Key": "DISASSEMBLY_KGCO2_PER_M2",
        "Value": 0.5,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for separating an IGU into its components (glass, spacer, etc.)."
    },
    {
        "Key": "REMANUFACTURING_KGCO2_PER_M2",
        "Value": 7.5,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions associated with remanufacturing glass components."
    },
    {
        "Key": "REPAIR_KGCO2_PER_M2",
        "Value": 0.5,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for repairing a system (e.g., resealing, valve replacement)."
    },
    {
        "Key": "INSTALL_SYSTEM_KGCO2_PER_M2",
        "Value": 0.25,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for installing the recovered system/unit into a new building."
    },
    
    # --- REPURPOSE FACTORS ---
    {
        "Key": "REPURPOSE_LIGHT_KGCO2_PER_M2",
        "Value": 0.5,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for 'Light' repurposing intensity."
    },
    {
        "Key": "REPURPOSE_MEDIUM_KGCO2_PER_M2",
        "Value": 1.0,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for 'Medium' repurposing intensity."
    },
    {
        "Key": "REPURPOSE_HEAVY_KGCO2_PER_M2",
        "Value": 2.0,
        "Unit": "kgCO2e/m²",
        "Section": "2. Process Emissions",
        "Description": "Emissions for 'Heavy' repurposing intensity."
    },

    # --- SECTION: TRANSPORT ---
    {
        "Key": "EMISSIONFACTOR_TRUCK",
        "Value": 0.098,
        "Unit": "kgCO2e/tkm",
        "Section": "3. Transport",
        "Description": "Truck emission factor (Default: DEFRA 2024 Artic >33t Avg Laden)."
    },
    {
        "Key": "EMISSIONFACTOR_FERRY",
        "Value": 0.129,
        "Unit": "kgCO2e/tkm",
        "Section": "3. Transport",
        "Description": "Ferry emission factor (Ro-Ro Freight)."
    },
    {
        "Key": "BACKHAUL_FACTOR",
        "Value": 1.3,
        "Unit": "Multiplier",
        "Section": "3. Transport",
        "Description": "Multiplier to account for empty return journeys (1.0 = no empty return)."
    },
    {
        "Key": "TRUCK_CAPACITY_T",
        "Value": 20.0,
        "Unit": "Tonnes",
        "Section": "3. Transport",
        "Description": "Maximum weight capacity of a standard truck."
    },
    {
        "Key": "FERRY_CAPACITY_T",
        "Value": 1000.0,
        "Unit": "Tonnes",
        "Section": "3. Transport",
        "Description": "Nominal capacity for ferry calculations (reference only)."
    },
    {
        "Key": "DISTANCE_FALLBACK_A_KM",
        "Value": 100.0,
        "Unit": "km",
        "Section": "3. Transport",
        "Description": "Default distance for Route A if geolocation fails."
    },
    {
        "Key": "DISTANCE_FALLBACK_B_KM",
        "Value": 100.0,
        "Unit": "km",
        "Section": "3. Transport",
        "Description": "Default distance for Route B if geolocation fails."
    },
    {
        "Key": "ROUTE_A_MODE",
        "Value": "HGV lorry",
        "Unit": "Mode",
        "Section": "3. Transport",
        "Description": "Default transport mode for Route A (HGV lorry / HGV lorry+ferry)."
    },
    {
        "Key": "ROUTE_B_MODE",
        "Value": "HGV lorry+ferry",
        "Unit": "Mode",
        "Section": "3. Transport",
        "Description": "Default transport mode for Route B."
    },

    # --- SECTION: MATERIALS & GEOMETRY ---
    {
        "Key": "GLASS_DENSITY_KG_M3",
        "Value": 2500.0,
        "Unit": "kg/m³",
        "Section": "4. Materials",
        "Description": "Density of float glass."
    },
    {
        "Key": "SEALANT_DENSITY_KG_M3",
        "Value": 1500.0,
        "Unit": "kg/m³",
        "Section": "4. Materials",
        "Description": "Avg density of sealant materials."
    },
    {
        "Key": "MASS_PER_M2_SINGLE",
        "Value": 10.0,
        "Unit": "kg/m²",
        "Section": "4. Materials",
        "Description": "Approx mass of single glazing (reference)."
    },
    {
        "Key": "MASS_PER_M2_DOUBLE",
        "Value": 20.0,
        "Unit": "kg/m²",
        "Section": "4. Materials",
        "Description": "Approx mass of double glazing (reference)."
    },
    {
        "Key": "MASS_PER_M2_TRIPLE",
        "Value": 30.0,
        "Unit": "kg/m²",
        "Section": "4. Materials",
        "Description": "Approx mass of triple glazing (reference)."
    },

    # --- SECTION: YIELD & FAILURE ---
    {
        "Key": "BREAKAGE_RATE_GLOBAL",
        "Value": 0.05,
        "Unit": "Ratio",
        "Section": "5. Yield Factors",
        "Description": "Global average breakage rate."
    },
    {
        "Key": "HUMIDITY_FAILURE_RATE",
        "Value": 0.05,
        "Unit": "Ratio",
        "Section": "5. Yield Factors",
        "Description": "Rate of units failing humidity tests."
    },
    {
        "Key": "SPLIT_YIELD",
        "Value": 0.95,
        "Unit": "Ratio",
        "Section": "5. Yield Factors",
        "Description": "Yield after splitting process."
    },
    {
        "Key": "REMANUFACTURING_YIELD",
        "Value": 0.90,
        "Unit": "Ratio",
        "Section": "5. Yield Factors",
        "Description": "Yield after remanufacturing process."
    },

    # --- SECTION: LOGISTICS & PACKAGING ---
    {
        "Key": "IGUS_PER_STILLAGE",
        "Value": 20,
        "Unit": "Count",
        "Section": "6. Logistics",
        "Description": "Average number of IGUs per stillage."
    },
    {
        "Key": "STILLAGE_MASS_EMPTY_KG",
        "Value": 300.0,
        "Unit": "kg",
        "Section": "6. Logistics",
        "Description": "Weight of an empty stillage."
    },
    {
        "Key": "MAX_TRUCK_LOAD_KG",
        "Value": 20000.0,
        "Unit": "kg",
        "Section": "6. Logistics",
        "Description": "Max legal payload for truck."
    },
    {
        "Key": "STILLAGE_MANUFACTURE_KGCO2",
        "Value": 500.0,
        "Unit": "kgCO2e",
        "Section": "6. Logistics",
        "Description": "Embodied carbon of manufacturing one stillage."
    },
    {
        "Key": "STILLAGE_LIFETIME_CYCLES",
        "Value": 100,
        "Unit": "Count",
        "Section": "6. Logistics",
        "Description": "Expected lifecycle trips for a stillage."
    },
    {
        "Key": "INCLUDE_STILLAGE_EMBODIED",
        "Value": False,
        "Unit": "Bool",
        "Section": "6. Logistics",
        "Description": "Whether to amortize stillage embodied carbon in calculations."
    },
]

def create_formatted_excel():
    df = pd.DataFrame(PARAMS)
    
    # Reorder
    df = df[["Section", "Key", "Value", "Unit", "Description"]]
    
    output_path = "d:/VITRIFY/data/parameters_config/project_parameters.xlsx"
    
    # Use xlsxwriter for formatting
    writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Parameters')
    
    workbook = writer.book
    worksheet = writer.sheets['Parameters']
    
    # Formats
    header_fmt = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'valign': 'top',
        'fg_color': '#4F81BD',
        'font_color': '#FFFFFF',
        'border': 1
    })
    
    section_fmt = workbook.add_format({
        'bold': True,
        'bg_color': '#DCE6F1',
        'border': 1
    })
    
    key_fmt = workbook.add_format({
        'bold': True,
        'font_color': '#333333',
        'bg_color': '#F2F2F2',
        'border': 1
    })
    
    value_fmt = workbook.add_format({
        'bg_color': '#FFFFCC', # Light yellow to indicate editable
        'border': 1
    })
    
    text_fmt = workbook.add_format({
        'text_wrap': True,
        'valign': 'top',
        'border': 1
    })
    
    # Apply column widths
    worksheet.set_column('A:A', 25) # Section
    worksheet.set_column('B:B', 35) # Key
    worksheet.set_column('C:C', 15, value_fmt) # Value (Editable)
    worksheet.set_column('D:D', 10) # Unit
    worksheet.set_column('E:E', 60, text_fmt) # Description
    
    # Apply header format
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_fmt)
        
    # Apply conditional/row formatting
    # Note: iterating rows to apply format based on section is decent
    for row_num, row_data in enumerate(PARAMS):
        # Row index in excel will be row_num + 1 (header is 0)
        r = row_num + 1
        
        # Write Section (Merged or just bold?) -> Let's just write styled
        worksheet.write(r, 0, row_data["Section"], section_fmt)
        worksheet.write(r, 1, row_data["Key"], key_fmt)
        # Value is written by pandas, but we overwrote column format. 
        # We might need to rewrite value to ensure format sticks if pandas didn't?
        # Pandas write takes precedence, but column format applies to empty cells.
        # Let's explicitly write the value with format
        worksheet.write(r, 2, row_data["Value"], value_fmt)
        worksheet.write(r, 3, row_data["Unit"], text_fmt)
        worksheet.write(r, 4, row_data["Description"], text_fmt)
        
    writer.close()
    print(f"Formatted Excel created at {output_path}")

if __name__ == "__main__":
    create_formatted_excel()
