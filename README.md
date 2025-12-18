# VITRIFY - IGU Recovery Environmental Impact Prototype

**VITRIFY** is a robust environmental impact assessment tool designed to calculate the Carbon Footprint (kg CO2e) of recovering Insulating Glass Units (IGUs). It compares 11 distinct recovery scenarios, from direct reuse to recycling and landfill, helping decision-makers choose the most sustainable path.

## 🚀 Key Capabilities

### 1. Recovery Scenarios (The 11 Paths)
The tool models the detailed physics and logistics of:
- **System Reuse**: Safely removing and re-installing the IGU (with optional repair).
- **Component Reuse**: Disassembling the IGU to recover panes for re-manufacturing.
- **Component Repurpose**: Re-using glass in lower-grade applications (3 intensity levels).
- **Closed-loop Recycling**: Returning cullet to a flat glass float plant (High quality).
- **Open-loop Recycling**: Down-cycling to glass wool or container glass.
- **Landfill**: The baseline "business as usual" disposal.

### 2. Advanced Inputs
- **Complex Glazing**: Supports **Single, Double, and Triple** glazing units.
- **Detailed Geometry**: Configurable pane thicknesses (inner/outer/centre), cavity widths, and sealant masses.
- **Material Specifics**: Select from Annealed/Tempered/Laminated glass, various sealants (Polysulfide, Silicone, etc.), and spacers (Aluminium, Steel, Warm Edge).

### 3. Logistics & Transport
- **Multi-Leg Routing**: Models `Origin -> Processor` and `Processor -> Destination`.
- **Geocoding & OSRM**: Automatically calculates real-world driving distances from city names (e.g., "London" to "Birmingham").
- **Transport Modes**: Choose between HGV Trucks (various emission standards like DEFRA 2024, Z.E. Electric) and Ferries.

### 4. Yield & Waste
- **Real-world Losses**: Accounts for breakage during removal, processing, and transport.
- **Waste Allocation**: Automatically assigns emissions from broken/waste glass to the "Waste" category.

---

## 🛠️ Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd VITRIFY
    ```

2.  **Set up Python Environment**:
    ```bash
    python -m venv .venv
    .venv\Scripts\activate  # Windows
    # source .venv/bin/activate  # Mac/Linux
    pip install -r requirements.txt
    pip install matplotlib
    ```

---

## 📖 Usage Guide

Run the tool via the command line:
```bash
python src/Recovery_IGU_CO2.py
```

### Mode 1: Single Run (Interactive)
Best for testing specific configurations or answering "What if?" questions.

**Step-by-Step Example (Complex Triple Glazing Run):**
1.  **Select Source**: `Manual`
2.  **Define Geometry**:
    - **Seal**: Primary 0.4x4mm, Secondary 10mm.
    - **Unit**: 1 Unit, 1500x2500mm (Large).
    - **Type**: `Triple` Glazing.
    - **Glass**: Outer (Tempered), Inner (Tempered), Coating (Solar Control).
    - **Build-up**: 8mm Pane -> 16mm Cavity -> 6mm Pane -> 16mm Cavity -> 8mm Pane.
3.  **Define Locations**:
    - **Origin**: `Berlin` (Removal site)
    - **Processor**: `Paris` (Factory)
    - **Landfill**: Select Default (50km local).
4.  **Transport Config**:
    - The tool will geocode cities and calculate KM.
    - Select Truck Type (e.g., `DEFRA 2024`).
5.  **Conditions**:
    - Set Age (e.g., 30 years).
    - Define if "Repair" or "Recondition" is needed.
6.  **Scenario**:
    - Choose `Component Reuse` (Scenario B) to model the full disassembly process.
7.  **Visualize**:
    - Select `a) Visualize this scenario` to generate charts.

### Mode 2: Automated Analysis (Batch)
Best for processing large datasets (e.g., entire building manifest).

1.  Ensure `data/saint_gobain/saint gobain product database.xlsx` is present.
2.  Run the tool and select **Automated Analysis**.
3.  Define **Global Parameters** (Processor location, Truck type) once.
4.  The tool will:
    - Iterate through every row in the Excel file.
    - Run **ALL scenarios** for each product.
    - Generate a master report: `d:\VITRIFY\reports\automated_analysis_report.csv`.

---

## 📊 Outputs

The tool generates artifacts in `d:\VITRIFY\reports\`:
- **Plots**: `reports/plots/` (Waterfalls, Donut Charts, Breakdowns).
- **Markdown Logs**: `reports/markdown_breakdowns/` (Detailed text summaries of every calculation step).
- **Audit Logs**: `reports/audit_logs/` (Traceability of every math operation).

## 📂 Project Structure
```text
d:\VITRIFY\
├── src\
│   ├── Recovery_IGU_CO2.py      # Main Launcher
│   └── igu_recovery\            # Core Logic
│       ├── scenarios.py         # Physics of the 11 paths
│       ├── calculations.py      # Math & Geometry
│       └── visualization.py     # Plotting logic
├── data\                        # Product Databases
└── reports\                     # Your Results
```

## License
Proprietary. All rights reserved.
