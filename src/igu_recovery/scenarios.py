import logging
from math import ceil
from typing import Dict, Tuple

from .constants import (
    DISASSEMBLY_KGCO2_PER_M2,
    REPURPOSE_LIGHT_KGCO2_PER_M2, REPURPOSE_MEDIUM_KGCO2_PER_M2, REPURPOSE_HEAVY_KGCO2_PER_M2,
    INSTALL_SYSTEM_KGCO2_PER_M2, REPAIR_KGCO2_PER_M2,
    REMANUFACTURING_KGCO2_PER_M2, RECONDITION_KGCO2_PER_M2, BREAKING_KGCO2_PER_M2,
    YIELD_REPAIR, YIELD_DISASSEMBLY_REUSE, YIELD_DISASSEMBLY_REPURPOSE,
    SHARE_CULLET_FLOAT, SHARE_CULLET_OPEN_LOOP_GW, SHARE_CULLET_OPEN_LOOP_CONT,
    EF_MAT_SPACER_ALU, EF_MAT_SPACER_STEEL, EF_MAT_SPACER_SWISS, EF_MAT_SEALANT,
    PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
)
from .models import (
    ProcessSettings, TransportModeConfig, IGUGroup, FlowState, ScenarioResult, Location, SealGeometry
)
from .utils.calculations import (
    apply_yield_loss, packaging_factor_per_igu, calculate_material_masses, haversine_km
)
from .utils.input_helpers import prompt_yes_no, prompt_location, prompt_choice, print_header, style_prompt, configure_route
from .audit import audit_logger

logger = logging.getLogger(__name__)



def get_route_emissions(mass_kg: float, route_key: str, processes: ProcessSettings, transport: TransportModeConfig) -> float:
    """
    Calculate transport emissions for a specific route key (e.g., 'origin_to_processor')
    using the stored RouteConfig.
    """
    if not processes.route_configs or route_key not in processes.route_configs:
         return 0.0
    
    config = processes.route_configs[route_key]
    mass_t = mass_kg / 1000.0
    
    # Calculate emissions based on config
    truck_e = mass_t * config.truck_km * transport.emissionfactor_truck
    ferry_e = mass_t * config.ferry_km * transport.emissionfactor_ferry
    
    # Apply backhaul factor to TRUCK leg? 
    # Usually backhaul applies to the road portion.
    truck_e *= transport.backhaul_factor
    # Ferry usually implies a booked crossing, maybe no empty return? 
    # Let's apply backhaul to truck only for now or consistent with previous logic?
    # Previous logic: distances["truck_A_km"] * transport.backhaul_factor
    # So yes, apply to truck km.
    
    # Previous logic applied backhaul to ferry km too:
    # ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor)
    ferry_e *= transport.backhaul_factor
    
    ferry_e *= transport.backhaul_factor
    
    total_e = truck_e + ferry_e

    # AUDIT LOG
    audit_logger.log_calculation(
        context=f"Transport Emissions (Route: {route_key})",
        formula="Mass(t) * [TruckDist(km)*EF_Truck + FerryDist(km)*EF_Ferry] * Backhaul",
        variables={
            "Mass_t": round(mass_t, 4),
            "Truck_km": config.truck_km,
            "Ferry_km": config.ferry_km,
            "EF_Truck": transport.emissionfactor_truck,
            "EF_Ferry": transport.emissionfactor_ferry,
            "Backhaul": transport.backhaul_factor
        },
        result=total_e,
        unit="kgCO2e"
    )

    return total_e

def run_scenario_landfill(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    interactive: bool = True
) -> ScenarioResult:
    """
    Scenario (f): Straight to Landfill
    """
    logger.info("Running Scenario: Straight to Landfill")
    if interactive:
        print_header("Scenario (f): Straight to Landfill")
    
    # 100% goes to landfill from Origin
    total_mass_kg = flow_start.mass_kg
    
    # Transport Origin -> Landfill
    landfill_kgco2 = 0.0
    if transport.landfill:
        landfill_kgco2 = get_route_emissions(total_mass_kg, "origin_to_landfill", processes, transport)
    else:
        logger.warning("No landfill location defined! Assuming 0 transport emissions.")
        
    # Dismantling emissions (still happen?) -> "Straight to landfill" usually implies removal.
    # Using e_site_kgco2_per_m2 (removal)
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2
    
    total = dismantling_kgco2 + landfill_kgco2
    
    by_stage = {
        "Dismantling": dismantling_kgco2,
        "Landfill Transport (Waste)": landfill_kgco2
    }
    
    return ScenarioResult(
        scenario_name="Straight to Landfill",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=0.0,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=0.0,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=0.0,
        yield_percent=0.0
    )

def run_scenario_system_reuse(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    initial_masses: Dict[str, float],
    interactive: bool = True,
    repair_needed: bool = None
) -> ScenarioResult:
    """
    Scenario (a): System Reuse
    """
    logger.info("Running Scenario: System Reuse")
    if interactive:
        print_header("Scenario (a): System Reuse")
    
    # a) On-Site Removal + Yield
    if interactive:
        print(f"  > Starting Mass: {flow_start.mass_kg:.2f} kg ({flow_start.igus:.1f} IGUs)")

    yield_removal = 0.0
    if interactive:
        yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)
    
    
    if interactive and yield_removal > 0:
        removed_mass = flow_start.mass_kg - flow_post_removal.mass_kg
        print(f"  > Applied Removal Yield ({yield_removal:.1%}): -{removed_mass:.2f} kg sent to Waste.")
        print(f"  > Remaining Mass: {flow_post_removal.mass_kg:.2f} kg")
    
    # Calculate dismantling emissions based on original area
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # 1. Transport A (Origin -> Processor)
    # Replaced compute_route_distances with configured route
    
    # Packaging (stillages) for transported amount
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_removal.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # Packaging emissions (embodied)
    pkg_per_igu = packaging_factor_per_igu(processes)
    packaging_kgco2 = flow_post_removal.igus * pkg_per_igu
    
    # b) Repair decision
    # b) Repair decision
    if interactive:
        repair_needed = prompt_yes_no("Does the IGU system require repair?", default=False)
    elif repair_needed is None:
        repair_needed = False # Default batch behavior

    
    repair_kgco2 = 0.0
    flow_post_repair = flow_post_removal
    
    if repair_needed:
        # Yield loss 20%
        logger.info(f"Applying {YIELD_REPAIR*100}% yield loss for repair process.")
        flow_post_repair = apply_yield_loss(flow_post_removal, YIELD_REPAIR)
        
        # Calculate repair emissions on the remaining area 
        repair_kgco2 = flow_post_repair.area_m2 * REPAIR_KGCO2_PER_M2

        if interactive:
            removed_mass_repair = flow_post_removal.mass_kg - flow_post_repair.mass_kg
            print(f"  > Applied Repair Yield ({YIELD_REPAIR:.1%}): -{removed_mass_repair:.2f} kg sent to Waste.")
            print(f"  > Remaining Mass: {flow_post_repair.mass_kg:.2f} kg (Ready for Reuse)")
    
    # c) New recipient location
    # c) New recipient location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("\\nConfiguration for Reuse path required:")
            reuse_location = prompt_location("new recipient building / reuse destination")
            transport.reuse = reuse_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )
        else:
            # Batch mode should have configured this or fail
            logger.warning("Route processor_to_reuse missing in batch mode!")
    
    # d) Transport B (Processor -> Reuse)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_repair.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    total_mass_B_kg = flow_post_repair.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

    if interactive:
        print(f"  > Transporting {total_mass_B_kg:.2f} kg to Reuse Site...")
        
    # Installation
    install_kgco2 = flow_post_repair.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    # e) Overview
    # Calculate waste transport emissions
    waste_transport_kgco2 = 0.0
    if transport.landfill:
        # 1. Removal Yield Loss (Allocated at Origin)
        mass_loss_removal = flow_start.mass_kg - flow_post_removal.mass_kg
        waste_transport_kgco2 += get_route_emissions(mass_loss_removal, "origin_to_landfill", processes, transport)
        
        # 2. Repair Yield Loss (Allocated at Processor)
        mass_loss_repair = flow_post_removal.mass_kg - flow_post_repair.mass_kg
        waste_transport_kgco2 += get_route_emissions(mass_loss_repair, "processor_to_landfill", processes, transport)

    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + repair_kgco2 + transport_B_kgco2 + install_kgco2 + waste_transport_kgco2
    
    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Repair": repair_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name="System Reuse",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_post_repair.igus,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_post_repair.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_post_repair.mass_kg,
        yield_percent=(flow_post_repair.area_m2 / flow_start.area_m2 * 100.0) if flow_start.area_m2 > 0 else 0.0
    )


def run_scenario_component_reuse(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    interactive: bool = True
) -> ScenarioResult:
    """
    Scenario (b): Component Reuse
    """
    logger.info("Running Scenario: Component Reuse")
    if interactive:
        print_header("Scenario (b): Component Reuse")
    
    # a) On-Site Removal
    yield_removal = 0.0
    if interactive:
        yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)

    if interactive and yield_removal > 0:
        removed_mass = flow_start.mass_kg - flow_post_removal.mass_kg
        print(f"  > Applied Removal Yield ({yield_removal:.1%}): -{removed_mass:.2f} kg sent to Waste.")
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # b) Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_removal.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # Packaging
    packaging_kgco2 = flow_post_removal.igus * packaging_factor_per_igu(processes)

    # c) System Disassembly (20% loss)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REUSE*100}% yield loss for disassembly.")
    DISASSEMBLY_YIELD = YIELD_DISASSEMBLY_REUSE
    flow_post_disassembly = apply_yield_loss(flow_post_removal, DISASSEMBLY_YIELD)
    
    
    if interactive:
        removed_mass_disas = flow_post_removal.mass_kg - flow_post_disassembly.mass_kg
        print(f"  > Applied Disassembly Yield ({DISASSEMBLY_YIELD:.1%}): -{removed_mass_disas:.2f} kg sent to Waste.")
        print(f"  > Remaining Mass: {flow_post_disassembly.mass_kg:.2f} kg (Components)")

    # Disassembly Emissions
    # Used flow_post_disassembly (post-yield) area
    disassembly_kgco2 = flow_post_disassembly.area_m2 * DISASSEMBLY_KGCO2_PER_M2
    
    # d) Recondition
    recondition = True
    if interactive:
        recondition = prompt_yes_no("Is recondition of components required?", default=True)
    
    recond_kgco2 = 0.0
    if recondition:
        logger.info(f"Applying reconditioning step with {RECONDITION_KGCO2_PER_M2} kgCO2e/m2")
        recond_kgco2 = flow_post_disassembly.area_m2 * RECONDITION_KGCO2_PER_M2
    
    # e) Assembly IGU
    # Material-based Calculation
    # 1. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU # Default
    if group.spacer_material == "aluminium": ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel": ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite": ef_spacer = EF_MAT_SPACER_SWISS
    
    # 2. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # 3. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_post_disassembly.igus / group.quantity if group.quantity > 0 else 0.0
    
    mass_spacer_needed_kg = mat_masses["spacer_kg"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor
    
    embodied_new_mat_kgco2 = (mass_spacer_needed_kg * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)
    
    # 4. Assembly Energy
    process_energy_kgco2 = flow_post_disassembly.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2
    
    logger.info(f"Assembly: Spacer {mass_spacer_needed_kg:.2f}kg, Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")
    
    # f) Next location
    # f) Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("\\nConfiguration for Reuse path required:")
            next_location = prompt_location("final installation location for reused IGUs")
            transport.reuse = next_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )
    
    # g) Transport B (Processor -> Reuse)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    total_mass_B_kg = flow_post_disassembly.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)
    
    # Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 + recond_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2
    
    # Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. Removal Yield Loss (Origin)
         mass_loss_removal = flow_start.mass_kg - flow_post_removal.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_removal, "origin_to_landfill", processes, transport)
         
         # 2. Disassembly Yield Loss (Processor)
         mass_loss_disassembly = flow_post_removal.mass_kg - flow_post_disassembly.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_disassembly, "processor_to_landfill", processes, transport)

    total += waste_transport_kgco2

    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Disassembly": disassembly_kgco2,
        "Recondition": recond_kgco2,
        "Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name="Component Reuse",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_post_disassembly.igus,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_post_disassembly.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_post_disassembly.mass_kg,
        yield_percent=(flow_post_disassembly.area_m2 / flow_start.area_m2 * 100.0) if flow_start.area_m2 > 0 else 0.0
    )


def run_scenario_component_repurpose(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    interactive: bool = True,
    repurpose_intensity: str = None
) -> ScenarioResult:
    """
    Scenario (c): Component Repurpose
    """
    logger.info("Running Scenario: Component Repurpose")
    if interactive:
        print_header("Scenario (c): Component Repurpose")
    
    # a) On-Site Removal
    yield_removal = 0.0
    if interactive:
        yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)
    if interactive and yield_removal > 0:
        loss = flow_start.mass_kg - flow_post_removal.mass_kg
        print(f"  > Applied Removal Yield: -{loss:.2f} kg Waste.")
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_removal.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    packaging_kgco2 = flow_post_removal.igus * packaging_factor_per_igu(processes)

    # c) Disassembly (10% loss)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REPURPOSE*100}% yield loss for disassembly (repurpose).")
    DISASSEMBLY_YIELD = YIELD_DISASSEMBLY_REPURPOSE
    flow_post_disassembly = apply_yield_loss(flow_post_removal, DISASSEMBLY_YIELD)
    
    if interactive:
        loss = flow_post_removal.mass_kg - flow_post_disassembly.mass_kg
        print(f"  > Applied Disassembly Yield ({DISASSEMBLY_YIELD:.1%}): -{loss:.2f} kg Waste.")
    

    # Used flow_post_disassembly (post-yield) area
    disassembly_kgco2 = flow_post_disassembly.area_m2 * DISASSEMBLY_KGCO2_PER_M2
    
    # e) Repurpose Intensity
    # e) Repurpose Intensity
    if interactive:
        logger.info("Select repurposing intensity:")
        logger.info("  light/medium/heavy")
        rep_preset = prompt_choice("Intensity", ["light", "medium", "heavy"], default="medium")
    elif repurpose_intensity:
        rep_preset = repurpose_intensity
    else:
        rep_preset = "medium"
    
    rep_factor = REPURPOSE_MEDIUM_KGCO2_PER_M2
    if rep_preset == "light": rep_factor = REPURPOSE_LIGHT_KGCO2_PER_M2
    if rep_preset == "heavy": rep_factor = REPURPOSE_HEAVY_KGCO2_PER_M2
    
    repurpose_kgco2 = flow_post_disassembly.area_m2 * rep_factor
    
    # f) Next location
    # f) Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("\\nConfiguration for Repurpose path required:")
            repurpose_dst = prompt_location("installation location for repurposed product")
            transport.reuse = repurpose_dst
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )
    
    # g) Transport B (Processor -> Reuse)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
    
    total_mass_B_kg = flow_post_disassembly.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)
    
    # Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 + repurpose_kgco2 + transport_B_kgco2 + install_kgco2
    
    # Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. Removal Yield Loss (Origin)
         mass_loss_removal = flow_start.mass_kg - flow_post_removal.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_removal, "origin_to_landfill", processes, transport)
         
         # 2. Disassembly Yield Loss (Processor)
         mass_loss_disassembly = flow_post_removal.mass_kg - flow_post_disassembly.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_disassembly, "processor_to_landfill", processes, transport)

    total += waste_transport_kgco2
    
    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Disassembly": disassembly_kgco2,
        "Repurposing": repurpose_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name=f"Repurpose ({rep_preset})",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_post_disassembly.igus,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_post_disassembly.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_post_disassembly.mass_kg,
        yield_percent=(flow_post_disassembly.area_m2 / flow_start.area_m2 * 100.0) if flow_start.area_m2 > 0 else 0.0
    )


def run_scenario_closed_loop_recycling(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    interactive: bool = True,
    send_intact: bool = None
) -> ScenarioResult:
    """
    Scenario (d): Closed-loop Recycling
    """
    logger.info("Running Scenario: Closed-loop Recycling")
    if interactive:
        print_header("Scenario (d): Closed-loop Recycling")
    
    # a) Intact decision
    if interactive:
        send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    elif send_intact is None:
        send_intact = True
    
    # b/c) On-site removal + Break IGU
    yield_removal = 0.0
    yield_break = 0.0
    
    # Standard removal yield
    if interactive:
        yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
        
        if not send_intact:
            yield_break_str = input(style_prompt("% yield loss at breaking (0-100) [default=0]: ")).strip()
            yield_break = float(yield_break_str)/100.0 if yield_break_str else 0.0
    
    flow_step1 = apply_yield_loss(flow_start, yield_removal)
    flow_step2 = apply_yield_loss(flow_step1, yield_break)
    
    # Emissions
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2
    breaking_kgco2 = 0.0
    if not send_intact:
        # Breaking emissions
        breaking_kgco2 = flow_step1.area_m2 * BREAKING_KGCO2_PER_M2
        
    # d) Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_step2.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_step2.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # e) Processor fractions
    CULLET_FLOAT_SHARE = SHARE_CULLET_FLOAT
    
    # Laminated Glass Logic:
    # If laminated (e.g. 44.2), it cannot be easily recycled into float.
    # Check glass types.
    is_laminated = False
    if "laminated" in group.glass_type_outer.lower() or "laminated" in group.glass_type_inner.lower():
        is_laminated = True
    
    # Also check thickness (e.g. 44.2 implies 8.something mm, we rely on type string)
    # The database loader should populate glass_type_outer/inner with "laminated" if applicable
    # If product name contains "44.2", we assume laminated.
    # Group names often don't travel here, but let's trust the type.
    
    if is_laminated:
        logger.warning(f"Laminated glass detected! Reducing Closed-loop yield to 0%.")
        CULLET_FLOAT_SHARE = 0.0

    flow_float = apply_yield_loss(flow_step2, 1.0 - CULLET_FLOAT_SHARE)
    
    if interactive:
        if is_laminated:
             print(f"  ! LAMINATED GLASS DETECTED. Yield = 0%. All mass to Waste.")
        else:
             loss = flow_step2.mass_kg - flow_float.mass_kg
             print(f"  > Float Plant Quality Check (Yield {CULLET_FLOAT_SHARE:.1%}): -{loss:.2f} kg rejected.")
        
        print(f"  > Sending {flow_float.mass_kg:.2f} kg to Float Plant.")
    
    # f) Dispatch to float plant
    # f) Dispatch to float plant
    if "processor_to_recycling" not in processes.route_configs:
        if interactive:
            print("\\nConfiguration for Recycling path required:")
            float_plant = prompt_location("Second Use Processing Facility (float glass plant)")
            transport.reuse = float_plant # Reuse field reused for recycling dst in some contexts? Better stick to route key.
            # Ideally transport.recycling? The model uses transport.reuse for B-leg often.
            # But here we are configuring "processor_to_recycling".
            
            processes.route_configs["processor_to_recycling"] = configure_route(
                "Processor -> Recycling", transport.processor, float_plant, interactive=True
            )
    
    # NOTE: "processor_to_recycling" should be configured for the float plant / recycling destination
    # We used "processor_to_reuse" in previous scenarios.
    # In Closed Loop, this is B-leg.
    
    # Bulk cullet, no stillages
    # Bulk cullet, no stillages
    transport_B_kgco2 = get_route_emissions(flow_float.mass_kg, "processor_to_recycling", processes, transport)
    if interactive:
         print(f"  > Transporting {flow_float.mass_kg:.2f} kg to Recycling Facility.")
    
    total = dismantling_kgco2 + breaking_kgco2 + transport_A_kgco2 + transport_B_kgco2
    
    # Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. Removal Yield Loss (Origin)
         mass_loss_removal = flow_start.mass_kg - flow_step1.mass_kg # flow_step1 is post-removal
         waste_transport_kgco2 += get_route_emissions(mass_loss_removal, "origin_to_landfill", processes, transport)
         
         # 2. Breaking Yield Loss (Origin if !send_intact)
         mass_loss_break = flow_step1.mass_kg - flow_step2.mass_kg
         if not send_intact:
             # Broken ON SITE, so loss is at Origin
             waste_transport_kgco2 += get_route_emissions(mass_loss_break, "origin_to_landfill", processes, transport)
         else:
             # Broken AT PROCESSOR (implicit?), actually flow_step2 applies break yield too?
             # Logic check: if send_intact, flow_step2 is reduced by yield_break?
             # Re-reading code: flow_step2 applies break yield regardless.
             # If send_intact, breaking happens at processor?
             # The existing code structure calculates 'breaking_kgco2' only if !send_intact.
             # If send_intact, presumably breaking happens at float plant or processor?
             # Let's assume if send_intact, any yield loss (breakage) happens at Processor.
             waste_transport_kgco2 += get_route_emissions(mass_loss_break, "processor_to_landfill", processes, transport)
             
         # 3. Cullet Share Loss (Processor -> Float Plant yield)
         # flow_float is post-cullet-share
         mass_loss_float = flow_step2.mass_kg - flow_float.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_float, "processor_to_landfill", processes, transport)

    total += waste_transport_kgco2
    
    by_stage = {
        "Dismantling/Removal": dismantling_kgco2,
        "Breaking": breaking_kgco2,
        "Transport A": transport_A_kgco2,
        "Transport B (Float)": transport_B_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name="Closed-Loop Recycling",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_float.igus, # Pseudo-count
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_float.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_float.mass_kg,
        yield_percent=CULLET_FLOAT_SHARE * 100.0
    )


def run_scenario_open_loop_recycling(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    interactive: bool = True,
    send_intact: bool = None
) -> ScenarioResult:
    """
    Scenario (e): Open-loop Recycling
    """
    logger.info("Running Scenario: Open-loop Recycling")
    if interactive:
        print_header("Scenario (e): Open-loop Recycling")
    
    # a) Intact vs break
    if interactive:
        send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    elif send_intact is None:
        send_intact = True
    
    # yield
    yield_removal = 0.0
    yield_break = 0.0
    if interactive:
        yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
        
        if not send_intact:
            yield_break_str = input(style_prompt("% yield loss at breaking (0-100) [default=0]: ")).strip()
            yield_break = float(yield_break_str)/100.0 if yield_break_str else 0.0
    
    flow_step1 = apply_yield_loss(flow_start, yield_removal)
    flow_step2 = apply_yield_loss(flow_step1, yield_break)
    
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2
    breaking_kgco2 = 0.0
    if not send_intact:
         breaking_kgco2 = flow_step1.area_m2 * BREAKING_KGCO2_PER_M2

    # Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_step2.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg

    total_mass_A_kg = flow_step2.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # Processor Fractions
    CULLET_CW_SHARE = SHARE_CULLET_OPEN_LOOP_GW
    CULLET_CONT_SHARE = SHARE_CULLET_OPEN_LOOP_CONT
    
    # Task: "Recycle to Glasswool / Container"
    # d) Optional transport
    model_transport = False
    if interactive:
        model_transport = prompt_yes_no("Model transport to glasswool/container plants?", default=False)
    else:
        # In batch mode, always model transport, using generic recycling route as proxy
        model_transport = True
    
    open_loop_transport_kgco2 = 0.0
    
    if model_transport:
        if interactive:
             if "processor_to_recycling" not in processes.route_configs:
                 print("\\nConfiguration for Open-loop Recycling path required:")
                 recycling_loc = prompt_location("Glasswool/Container processing facility")
                 processes.route_configs["processor_to_recycling"] = configure_route(
                    "Processor -> Recycling", transport.processor, recycling_loc, interactive=True
                 )
        
        # In batch, we definitely rely on "processor_to_recycling".
        
        mass_gw_kg = (flow_step2.mass_kg * CULLET_CW_SHARE)
        mass_cont_kg = (flow_step2.mass_kg * CULLET_CONT_SHARE)
        
        e_gw = get_route_emissions(mass_gw_kg, "processor_to_recycling", processes, transport)
        e_cont = get_route_emissions(mass_cont_kg, "processor_to_recycling", processes, transport)
        
        open_loop_transport_kgco2 = e_gw + e_cont

    total = dismantling_kgco2 + breaking_kgco2 + transport_A_kgco2 + open_loop_transport_kgco2
    
    # Calculate final flow before waste calc
    final_useful_fraction = CULLET_CW_SHARE + CULLET_CONT_SHARE # 20%
    flow_final = apply_yield_loss(flow_step2, 1.0 - final_useful_fraction)
    
    if interactive:
        if yield_removal > 0:
            print(f"  > Removal Loss: -{flow_start.mass_kg - flow_step1.mass_kg:.2f} kg")
        if yield_break > 0:
             print(f"  > Breaking Loss: -{flow_step1.mass_kg - flow_step2.mass_kg:.2f} kg")
             
        loss = flow_step2.mass_kg - flow_final.mass_kg
        print(f"  > Useful Fraction (GW {CULLET_CW_SHARE:.1%} + Cont {CULLET_CONT_SHARE:.1%}): -{loss:.2f} kg rejected.")
        print(f"  > Sending {flow_final.mass_kg:.2f} kg to Recycling.")
    
    # Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. Removal Yield Loss (Origin)
         mass_loss_removal = flow_start.mass_kg - flow_step1.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_removal, "origin_to_landfill", processes, transport)
         
         # 2. Breaking Yield Loss
         mass_loss_break = flow_step1.mass_kg - flow_step2.mass_kg
         if not send_intact:
             waste_transport_kgco2 += get_route_emissions(mass_loss_break, "origin_to_landfill", processes, transport)
         else:
             waste_transport_kgco2 += get_route_emissions(mass_loss_break, "processor_to_landfill", processes, transport)
             
         # 3. Useful Fraction Loss (Processor)
         # flow_step2 is mass entering processor (after break)
         # flow_final is mass successfully recycled
         mass_loss_final = flow_step2.mass_kg - flow_final.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_final, "processor_to_landfill", processes, transport)

    total += waste_transport_kgco2
    
    by_stage = {
        "Dismantling": dismantling_kgco2,
        "Breaking": breaking_kgco2,
        "Transport A": transport_A_kgco2,
        "Open-Loop Transport": open_loop_transport_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name="Open-Loop Recycling",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_final.igus,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_final.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_final.mass_kg,
        yield_percent=final_useful_fraction * 100.0
    )

