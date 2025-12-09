# VITRIFY - IGU Recovery Environmental Impact Prototype

This project calculates and compares the environmental impact (Carbon Emissions in kg CO2e) of various recovery scenarios for Insulating Glass Units (IGUs) removed from buildings. It is designed to help decision-making regarding checking, repairing, repurposing, or recycling used IGUs.

## Features

- **5 Recovery Scenarios**:
  - **System Reuse**: Direct reuse of the IGU system (with optional repair).
  - **Component Reuse**: Disassembly and re-manufacturing of IGU components.
  - **Component Repurpose**: Repurposing components for other uses (downcycling/upcycling).
  - **Closed-loop Recycling**: Recycling into new glass (float plant).
  - **Open-loop Recycling**: Recycling into glasswool or containers.
  
- **Yield Tracking**: Tracks mass, area, and unit counts through every step of the process (removal, disassembly, breaking, etc.).
- **Transport Modeling**: Calculator for transport emissions (Truck/Ferry) with customizable emission factors (EU Legacy vs Z.E. Trucks).
- **Material Calculations**: Detailed mass and volume calculations for glass, spacers, and sealants (Primary/Secondary).
- **Modular Architecture**: Organized as a Python package (`igu_recovery`) for maintainability.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd VITRIFY
    ```

2.  **Create and activate a virtual environment** (optional but recommended):
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Unix/MacOS:
    source .venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

You can run the prototype using the legacy shim script (if you are familiar with the previous version) or directly via the package module.

### Option 1: Legacy Shim (Recommended)
This script sits in `src/` and points to the new package structure.

```bash
cd src
python Recovery_IGU_CO2.py
```

### Option 2: Run as Module
Run the `igu_recovery` package directly from `src/`.

```bash
cd src
python -m igu_recovery.main
```

## Project Structure

```
d:\VITRIFY\
├── src\
│   ├── Recovery_IGU_CO2.py      # Shim entry point (legacy support)
│   ├── logging_config.py        # Shared logging configuration (legacy/shared)
│   └── igu_recovery\            # Main Package
│       ├── __init__.py
│       ├── main.py              # Main orchestrator / entry point logic
│       ├── constants.py         # Configuration constants and settings
│       ├── models.py            # Data classes (Location, IGUGroup, etc.)
│       ├── scenarios.py         # Logic for the 5 recovery scenarios
│       ├── logging_conf.py      # Logging setup for the package
│       └── utils\
│           ├── __init__.py
│           ├── calculations.py  # Math, distance, and yield calculations
│           └── input_helpers.py # User prompts and geocoding
├── requirements.txt
└── README.md
```

## Development

- **Logging**: The project uses structured logging with `colorama` for console output.
- **Dependencies**: Key libraries include `requests` (for geocoding) and `colorama`.

## License

[License Information Here]
