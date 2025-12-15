# IGU Recovery Tool - Technical Reference

## 1. Overview
The **IGU Recovery Calculator** is a Python-based command-line tool designed to estimate the embodied carbon (kgCO2e) benefits of various recovery scenarios for Insulated Glass Units (IGUs). 

It allows users to model different end-of-life pathways including:
*   **System Reuse**: Repairing and reinstalling the entire unit.
*   **Component Reuse**: Disassembling and reconditioning glass/components.
*   **Component Repurpose**: Using glass for other low-grade applications.
*   **Recycling**: Closed-loop (float glass) and Open-loop (glasswool/aggregate).

## 2. Directory Structure
The project is organized as a modular Python package (`igu_recovery`) located in `src/`.

```
d:/VITRIFY/
├── data/
│   └── parameters_config/
│       └── project_parameters.xlsx   <-- Configuration Source
├── src/
│   ├── igu_recovery/                <-- Main Package
│   │   ├── __init__.py
│   │   ├── config.py                <-- Excel Loader
│   │   ├── constants.py             <-- Parameter Registry
│   │   ├── main.py                  <-- Entry Point (Logic)
│   │   ├── models.py                <-- Data Classes
│   │   ├── scenarios.py             <-- Calculation Logic
│   │   ├── logging_conf.py          <-- Log/Color Setup
│   │   └── utils/
│   │       ├── calculations.py
│   │       └── input_helpers.py
│   └── Recovery_IGU_CO2.py          <-- Execution Wrapper
└── requirements.txt
```

## 3. Module Descriptions

### Core Modules

*   **`main.py`**: The application controller. It orchestrates the user flow:
    1.  Sets up logging.
    2.  Prompts for input (IGU details, locations, transport modes).
    3.  Runs the selected scenario.
    4.  Displays results.
*   **`scenarios.py`**: Contains the specific logic for each of the 5 recovery paths. Each function represents a distinct workflow (e.g., `run_scenario_system_reuse`), calculating emissions step-by-step (Dismantling -> Transport -> Processing -> Installation).
*   **`models.py`**: Defines strictly typed data structures used throughout the app, such as `IGUGroup`, `FlowState` (mass/area tracker), `ProcessSettings`, and `ScenarioResult`.
*   **`logging_conf.py`**: Configures the console output, including the logic for coloring log messages (Green for Info, Yellow for Warning).

### Configuration & Data

*   **`config.py`**: Responsible for loading the `project_parameters.xlsx` file. It reads the Excel sheet and returns a dictionary of settings.
*   **`constants.py`**: Acts as the central registry for all physical constants and emission factors. It dynamically imports values from `config.py` at startup. **Note**: If the Excel file is missing, the application will fail to start to prevent incorrect calculations.

### Utilities

*   **`utils/input_helpers.py`**: Handles all user interaction. It provides styled prompts (Yellow), geocoding for addresses, and menu selection logic (supporting both text and numeric input).
*   **`utils/calculations.py`**: Pure functions for math, such as the Haversine formula (distance between coordinates) and geometry helpers (calculating glass mass from thickness/area).

## 4. Configuration (Excel)

The system is data-driven. All key parameters—such as emission factors, density values, and default distances—are stored in:
`data/parameters_config/project_parameters.xlsx`

*   **Editable**: Users can modify values in the **Value** column (Yellow cells).
*   **Static Keys**: The **Key** column must not be changed, as the code relies on these specific variable names.

## 5. How to Run

### Prerequisites
*   Python 3.x
*   Dependencies installed: `pip install -r requirements.txt`

### Execution
Run the wrapper script from the project root:
```bash
python src/Recovery_IGU_CO2.py
```

### Usage Flow
1.  **Define IGU**: Enter dimensions, quantity, and glazing type.
2.  **Locations**: Enter text addresses (e.g., "London", "Manchester") for the building and processor. The tool geocodes these to lat/lon.
3.  **Transport**: Select vehicle types (HGV, Ferry).
4.  **Scenario**: Choose the recovery path (1-5).
5.  **Overrides**: Input specific yield losses or extra processing emissions if known (defaults available).
6.  **Results**: View the total kgCO2e and breakdown by stage.
