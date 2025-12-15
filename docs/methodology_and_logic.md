# VITRIFY IGU Recovery Tool: Methodology & Calculation Logic

This document details the mathematical models, process flows, and emission factors used in the IGU Recovery Analysis Tool.

---

## 1. General Principles

### Mass Balance Approach
All scenarios follow a strict mass balance logic. We start with the **Initial Mass** of the IGU batch. At each step, mass is either:
1.  **Retained**: Moves to the next process stage (generating process/transport emissions).
2.  **Lost (Yield Loss)**: Diverted immediately to Landfill (generating waste transport emissions).

$$ Mass_{output} = Mass_{input} \times (1 - Yield_{loss}) $$
$$ Mass_{waste} = Mass_{input} \times Yield_{loss} $$

### Transport Model
Emissions for any transport leg are calculated as:

$$ E_{transport} = Mass_{tonnes} \times (Dist_{truck} \times EF_{truck} + Dist_{ferry} \times EF_{ferry}) \times BackhaulFactor $$

*   **Stillages**: For scenarios involving *intact* IGUs, the mass of steel stillages (racks) is added to the transport load.
    *   `Stillage Mass Total` = `Ceil(IGUs / Capacity)` * `Stillage Weight`
*   **Backhaul**: A factor (default 1.6) is applied to account for empty return journeys.

---

## 2. Emission Factors & Parameters
*Sourced from `data/parameters_config/project_parameters.xlsx`*

| Parameter | Value (Default) | Unit | Description |
| :--- | :--- | :--- | :--- |
| **Material EFs** | | | |
| Float Glass (Virgin) | 1.43 | kgCO2e/kg | Baseline production |
| Aluminium Spacer | 26.6 | kgCO2e/kg | High embodied carbon |
| Sealant | 2.5 | kgCO2e/kg | Process sealant |
| **Process EFs** | | | |
| Removal (E_site) | 1.5 | kgCO2e/m² | Energy to remove from building |
| Repair | 2.5 | kgCO2e/m² | Cleaning/resealing |
| Disassembly | 3.5 | kgCO2e/m² | Breaking seals, separating panes |
| Breaking | 0.05 | kgCO2e/m² | Crushing glass |
| **Transport EFs** | | | |
| Truck (HGV) | 0.062 | kgCO2e/t.km | Road transport |
| Ferry | 0.015 | kgCO2e/t.km | Sea transport |

---

## 3. Scenario Methodologies

### Scenario A: System Reuse
*Goal: Remove, repair, and reinstall the IGU as a whole unit.*

**Flow:**
1.  **Origin**: Removal (Yield Loss applied $\to$ Landfill).
2.  **Transport A**: Origin $\to$ Processor (Intact + Stillages).
3.  **Processor**: Repair Process (Yield Loss 20% applied $\to$ Landfill).
4.  **Transport B**: Processor $\to$ Reuse Site (Intact + Stillages).
5.  **Destination**: Installation.

**Key Math:**
*   `Repair Emissions` = $Area_{retained} \times 2.5$

### Scenario B: Component Reuse
*Goal: Disassemble IGU, clean components, and re-assemble into a new IGU.*

**Flow:**
1.  **Origin**: Removal (Yield Loss $\to$ Landfill).
2.  **Transport A**: Origin $\to$ Processor (Intact + Stillages).
3.  **Processor**:
    *   **Disassembly**: Yield Loss 20% (Breakage during separation).
    *   **Recondition**: Cleaning panes ($Area \times 1.0$).
    *   **Assembly**: New Spacers + New Sealant added.
        *   `Embodied New` = $(Mass_{spacer} \times EF_{spacer}) + (Mass_{sealant} \times EF_{sealant})$
        *   `Process Energy` = $Area \times EF_{assembly}$
4.  **Transport B**: Processor $\to$ Reuse Site.

### Scenario C: Component Repurpose
*Goal: Cut down or process glass for interior partitions/furniture.*

**Flow:**
1.  **Origin**: Removal (Yield Loss).
2.  **Transport A**: Origin $\to$ Processor.
3.  **Processor**:
    *   **Disassembly**: Yield Loss 10% (Easier than preservation for reuse).
    *   **Repurposing**: Intensity factor applied (Light/Medium/Heavy).
        *   `e.g. Medium` = $Area \times 12.0$ kgCO2e/m².
4.  **Transport B**: Processor $\to$ New Location.

### Scenario D: Closed-Loop Recycling
*Goal: Return cullet to Float Line for new glass production.*

**Critical Logic (Purity):**
*   **Laminated Glass**: If detected, **Yield = 0%**. (PVB contaminates float tanks).
*   **Quality Check**: Uses `SHARE_CULLET_FLOAT` (Default 80-90%).
    *   Only this fraction is sent to the float plant.
    *   The rest is rejected to landfill.

**Flow:**
1.  **Origin**: Removal (Yield Loss).
2.  **Breaking**: Optional on-site (bulk transport) or at processor.
3.  **Processor**:
    *   Calculates `Mass_Float = Mass_In * 0.8`.
    *   Rejects `Mass_In * 0.2` to Landfill.
4.  **Transport B**: Processor $\to$ Float Plant.

### Scenario E: Open-Loop Recycling
*Goal: Downcycle to Glasswool (Insulation) or Container Glass (Bottles).*

**Critical Logic (Useful Fraction):**
*   **Glasswool Share**: `SHARE_CULLET_OPEN_LOOP_GW` (Default 10%).
*   **Container Share**: `SHARE_CULLET_OPEN_LOOP_CONT` (Default 10%).
*   **Total Useful**: Sum (e.g. 20%).
    *   Logic: Flat glass chemistry is often incompatible with these furnaces (Mg/Fe levels).
    *   Rejects `Mass_In * (1.0 - 0.2)` to Landfill.

**Flow:**
1.  **Origin $\to$ Processor**: Same as closed-loop.
2.  **Processor**:
    *   Separates useful fraction (20%).
    *   Sends to Recycling Facility (Transport B).
    *   Sends remainder (80%) to Landfill.

### Scenario F: Landfill
*Goal: Baseline check.*

**Flow:**
1.  **Origin**: Removal.
2.  **Transport**: Origin $\to$ Landfill (100% Mass).
3.  **Emissions**: Transport + Removal energy only.
