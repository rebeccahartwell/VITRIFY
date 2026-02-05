import logging
from math import ceil
from typing import Dict, Tuple

from .constants import (
    DISASSEMBLY_KGCO2_PER_M2,
    REPURPOSE_LIGHT_KGCO2_PER_M2, REPURPOSE_MEDIUM_KGCO2_PER_M2, REPURPOSE_HEAVY_KGCO2_PER_M2,
    INSTALL_SYSTEM_KGCO2_PER_M2, REPAIR_KGCO2_PER_M2, FLOAT_GLASS_REPROCESSING_KGCO2_PER_KG,
    REMANUFACTURING_KGCO2_PER_M2, RECONDITION_KGCO2_PER_M2, BREAKING_KGCO2_PER_M2,
    YIELD_SYSTEM_REUSE, YIELD_REPAIR, YIELD_DISASSEMBLY_REUSE, YIELD_DISASSEMBLY_REMANUFACTURE, YIELD_DISASSEMBLY_REPURPOSE,
    SHARE_CULLET_FLOAT, SHARE_CULLET_OPEN_LOOP_GW, SHARE_CULLET_OPEN_LOOP_CONT,
    EF_MAT_SPACER_ALU, EF_MAT_SPACER_STEEL, EF_MAT_SPACER_SWISS, EF_MAT_SEALANT, EF_MAT_GLASS_VIRGIN,
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

#Note: flow_start = Initial Flow of Materials Available for Recovery

def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

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
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    interactive: bool = True,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: Straight to Landfill: All mass recovered goes to landfill
    """
    logger.info("Running Scenario: Landfill")
    if interactive:
        print_header("Scenario: Landfill")
    
    # 100% goes to landfill from Origin
    total_mass_kg = flow_start.mass_kg
    
    # Transport Origin -> Landfill
    landfill_transport_kgco2 = 0.0
    if transport.landfill:
        landfill_transport_kgco2 = get_route_emissions(total_mass_kg, "origin_to_landfill", processes, transport)
    else:
        logger.warning("No landfill location defined! Assuming 0 transport emissions.")
        
    # Dismantling emissions (still happen?) -> "Straight to landfill" usually implies removal.
    # Using e_site_kgco2_per_m2 (removal)
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2

    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass
    # ! Assembly IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_start.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)
    # ! Assembly Energy
    process_energy_kgco2 = flow_start.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    if equivalent_product:
        logger.info(
            f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
            f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        if "processor_to_reuse" not in processes.route_configs:
            if interactive:
                print("Configuration for Site of Next Use required:")
                next_location = prompt_location("Final installation location for IGUs (from new float glass)")
                transport.reuse = next_location
                processes.route_configs["processor_to_reuse"] = configure_route(
                    "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
                )
        # ! Transport B (Processor -> Next use)
        stillage_mass_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_B = ceil(flow_start.igus / processes.igus_per_stillage)
            stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

        total_mass_B_kg = flow_start.mass_kg + stillage_mass_B_kg
        transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 = flow_start.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 = 0
        assembly_kgco2 = 0
        transport_B_kgco2 = 0
        install_kgco2 = 0
    # --------------------------------------

    total = (dismantling_kgco2 + landfill_transport_kgco2 +
            new_glass_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2)
    
    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Landfill Transport (Waste)": landfill_transport_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
    }
    
    return ScenarioResult(
        scenario_name="Landfill",
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
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    initial_masses: Dict[str, float],
    interactive: bool = True,
    repair_needed: bool = None,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: IGU System is reused in its recovered form with or without repair (user-determined)
    """
    logger.info("Running Scenario: System Reuse")
    if interactive:
        print_header("Scenario: System Reuse")

    # ! Calculate on-site dismantling emissions based on original area
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2

    # ! On-Site Removal + Yield
    if interactive:
        print(f"  > Starting Mass: {flow_start.mass_kg:.2f} kg ({flow_start.igus:.1f} IGUs)")

    site_yield_loss = 0.0
    if interactive:
        site_yield_loss_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str)/100.0 if site_yield_loss_str else 0.0
    
    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    
    
    if interactive and site_yield_loss > 0:
        lost_mass = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        print(f"  > Yield Loss from On-site Building Dismantling ({site_yield_loss:.1%}): -{lost_mass:.2f} kg sent to Waste.")
        print(f"  > Remaining Mass: {flow_post_site_yield_loss.mass_kg:.2f} kg")
    
    # ! Transport A (Origin -> Processor)
    # Replaced compute_route_distances with configured route
    
    # Calculate transportation associated with IGUs and Packaging (stillages)
    stillage_mass_A_kg = 0.0
        #Update IGUS_per_stillage in project_parameters file
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # ! Packaging emissions (embodied) excluded from calculation if INCLUDE_STILLAGE_EMBODIED = 0. See "Calculations.py"
    packaging_kgco2 = flow_post_site_yield_loss.igus * packaging_factor_per_igu(processes)

    # ! Repair decision
    if interactive:
        repair_needed = prompt_yes_no("Does the IGU system require repair?", default=False)
    elif repair_needed is None:
        repair_needed = False # Default batch behavior

    repair_kgco2 = 0.0
    if repair_needed:
        # Yield loss 10%
        logger.info(f"Applying {YIELD_REPAIR*100}% yield loss for repair process.")
        flow_reuse_ready = apply_yield_loss(flow_post_site_yield_loss, YIELD_REPAIR)
        
        # Calculate repair emissions on the remaining area
        if group.glazing_type == "double":
            repair_kgco2 = flow_reuse_ready.area_m2 * REPAIR_KGCO2_PER_M2
        elif group.glazing_type == "triple": # refill 2 x cavity
            repair_kgco2 = flow_reuse_ready.area_m2 * REPAIR_KGCO2_PER_M2 * 2

        if interactive:
            mass_loss_reuse_ready = flow_post_site_yield_loss.mass_kg - flow_reuse_ready.mass_kg
            print(f"  > Yield Loss at Repair Stage ({YIELD_REPAIR:.1%}): {mass_loss_reuse_ready:.2f} kg sent to Waste.")
            print(f"  > Remaining Mass: {flow_reuse_ready.mass_kg:.2f} kg (Ready for Reuse)")

    elif repair_needed == False:
        # Yield loss 20%
        logger.info(f"Applying {YIELD_SYSTEM_REUSE * 100}% yield loss for reuse-ready systems.")
        flow_reuse_ready = apply_yield_loss(flow_post_site_yield_loss, YIELD_SYSTEM_REUSE)

        if interactive:
            mass_loss_reuse_ready = flow_post_site_yield_loss.mass_kg - flow_reuse_ready.mass_kg
            print(f"  > Applied Yield for Reuse-Ready ({YIELD_SYSTEM_REUSE:.1%}): {mass_loss_reuse_ready:.2f} kg sent to Waste.")
            print(f"  > Remaining Mass: {flow_reuse_ready.mass_kg:.2f} kg (Ready for Reuse)")


    # ! New recipient location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("\\nConfiguration for next-use destination required::")
            reuse_location = prompt_location("new recipient building / reuse destination")
            transport.reuse = reuse_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )
        else:
            # Batch mode should have configured this or fail
            logger.warning("Route processor_to_reuse missing in batch mode!")
    
    # ! Transport B (Processor -> Reuse)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_reuse_ready.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    total_mass_B_kg = flow_reuse_ready.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

    if interactive:
        print(f"  > Transporting {flow_reuse_ready.mass_kg:.2f} kg to Reuse Site...")
        
    # ! Installation
    install_kgco2 = flow_reuse_ready.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    # ! Calculate Transport to Waste emissions
    waste_transport_kgco2 = 0.0
    if transport.landfill:
        # 1. Removal Yield Loss (Allocated at Origin)
        mass_loss_on_site_removal = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        waste_transport_kgco2 += get_route_emissions(mass_loss_on_site_removal, "origin_to_landfill", processes, transport)
        
        # 2. Repair Yield Loss (Allocated at Processor)
        mass_loss_reuse_ready = flow_post_site_yield_loss.mass_kg - flow_reuse_ready.mass_kg
        waste_transport_kgco2 += get_route_emissions(mass_loss_reuse_ready, "processor_to_landfill", processes, transport)

    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False

    # NEW GLASS
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg - flow_reuse_ready.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass

    # IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = 1 - (flow_reuse_ready.area_m2 / flow_start.area_m2)
    flow_equiv_quantity = apply_yield_loss(flow_start, scale_factor)

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor
    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    process_energy_kgco2 = flow_equiv_quantity.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    if equivalent_product:
        logger.info(
            f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
            f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        # ! Transport B (Processor -> Next use)
        stillage_mass_equiv_product_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_equiv_product_B = ceil(flow_equiv_quantity.igus / processes.igus_per_stillage)
            stillage_mass_equiv_product_B_kg = n_stillages_equiv_product_B * processes.stillage_mass_empty_kg

        total_mass_equiv_product_B_kg = (flow_equiv_quantity.mass_kg + stillage_mass_equiv_product_B_kg)
        transport_B_kgco2 += get_route_emissions(total_mass_equiv_product_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 += flow_equiv_quantity.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 = 0
        assembly_kgco2 = 0
        transport_B_kgco2 += 0
        install_kgco2 += 0
    # --------------------------------------

    # ! Overview
    total = (dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + repair_kgco2 + transport_B_kgco2 + install_kgco2 + waste_transport_kgco2 +
                new_glass_kgco2 + assembly_kgco2)
    
    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Repair": repair_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }
    
    return ScenarioResult(
        scenario_name="System Reuse",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus=flow_reuse_ready.igus,
        initial_area_m2=flow_start.area_m2,
        final_area_m2=flow_reuse_ready.area_m2,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg=flow_reuse_ready.mass_kg,
        yield_percent=(flow_reuse_ready.area_m2 / flow_start.area_m2 * 100.0) if flow_start.area_m2 > 0 else 0.0
    )


def run_scenario_component_reuse(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    interactive: bool = True,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: System is disassembled for Component Reuse
    """
    logger.info("Running Scenario: Component Reuse")
    if interactive:
        print_header("Scenario: Component Reuse")

    # ! Calculate on-site dismantling emissions based on original area
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2

    # ! On-Site Removal
    site_yield_loss = 0.0
    if interactive:
        site_yield_loss_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str)/100.0 if site_yield_loss_str else 0.0
    
    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    if interactive and site_yield_loss > 0:
        removed_mass = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        print(f"  > Yield Loss from On-site Building Dismantling ({site_yield_loss:.1%}): {removed_mass:.2f} kg sent to Waste.")

    # ! Transport A (Origin Site -> Processor)
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)

    # ! Packaging
    packaging_kgco2 = flow_post_site_yield_loss.igus * packaging_factor_per_igu(processes)

    # ! Disassembly activities Emissions based on available yield
    disassembly_kgco2 = flow_post_site_yield_loss.area_m2 * DISASSEMBLY_KGCO2_PER_M2

    # ! System Disassembly (20% loss as standard - configure in project_parameters file)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REUSE * 100}% yield loss for disassembly for component reuse.")
    flow_post_disassembly = apply_yield_loss(flow_post_site_yield_loss, YIELD_DISASSEMBLY_REUSE)

    if interactive:
        removed_mass_disassembly = flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg
        print(
            f"  > Yield Loss at System Disassembly Stage ({YIELD_DISASSEMBLY_REUSE:.1%}): {removed_mass_disassembly:.2f} kg sent to Waste.")
        print(f"  > Remaining Mass: {flow_post_disassembly.mass_kg:.2f} kg (Components)")
    
    # ! Component recondition
    recondition = True
    if interactive:
        recondition = prompt_yes_no("Is recondition of components required?", default=True)
    
    recond_kgco2 = 0.0
    if recondition:
        logger.info(f"Applying reconditioning step with {RECONDITION_KGCO2_PER_M2} kgCO2e/m2")
        recond_kgco2 = flow_post_disassembly.area_m2 * RECONDITION_KGCO2_PER_M2
    
    # ! Assembly IGU
    # Material-based Calculation
        # i. Configure Spacer EF (kgCO2/linear metre)
    ef_spacer = EF_MAT_SPACER_ALU # Default
    if group.spacer_material == "aluminium": ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel": ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite": ef_spacer = EF_MAT_SPACER_SWISS
    
        # ii. Configure Sealant EF (kgCO2/kg)
    ef_sealant = EF_MAT_SEALANT

        # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_post_disassembly.igus / group.quantity if group.quantity > 0 else 0.0
    
    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor
    
    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)
    
        # iv. Re-Assembly Energy
    process_energy_kgco2 = flow_post_disassembly.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2
    
    logger.info(f"New Materials Required: Spacer {length_spacer_needed_m:.2f} m, Sealant {mass_sealant_needed_kg:.2f} kg -> {embodied_new_mat_kgco2:.2f} kgCO2e"
                f"\n Assembly: {process_energy_kgco2:.2f} kgCO2e "
                f"\n Total Emissions Associated with Re-Assembly: {assembly_kgco2:.2f} kgCO2e")

    # ! Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("Configuration for next-use destination required:")
            next_location = prompt_location("final installation location for reused IGUs")
            transport.reuse = next_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )
    
    # ! Transport B (Processor -> Next Use Location)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    total_mass_B_kg = flow_post_disassembly.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)
    
    # ! Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    # ! Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # i. Removal Yield Loss (Origin)
         mass_loss_on_site_removal = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_on_site_removal, "origin_to_landfill", processes, transport)
         
         # ii. Disassembly Yield Loss (Processor)
         mass_loss_disassembly = flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_disassembly, "processor_to_landfill", processes, transport)


    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False

    # NEW GLASS
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg - flow_post_disassembly.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass

    # IGU
    # Material-based Calculation (carry sealant and spacer from above)

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor_equiv_quant = 1 - (flow_post_disassembly.area_m2 / flow_start.area_m2)
    flow_equiv_quantity = apply_yield_loss(flow_start, scale_factor_equiv_quant)

    additional_length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor_equiv_quant
    additional_mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor_equiv_quant
    additional_embodied_new_mat_kgco2 = (additional_length_spacer_needed_m * ef_spacer) + (additional_mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    additional_process_energy_kgco2 = flow_equiv_quantity.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    additional_assembly_kgco2 = additional_embodied_new_mat_kgco2 + additional_process_energy_kgco2
    assembly_kgco2 += additional_assembly_kgco2

    if equivalent_product:
        logger.info(
            f"Additional New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Additional Assembly: Spacer {additional_length_spacer_needed_m:.2f}m, "
            f"Additional Sealant {additional_mass_sealant_needed_kg:.2f}kg -> {additional_assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        # ! Transport B (Processor -> Next use)
        stillage_mass_equiv_product_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_equiv_product_B = ceil(flow_equiv_quantity.igus / processes.igus_per_stillage)
            stillage_mass_equiv_product_B_kg = n_stillages_equiv_product_B * processes.stillage_mass_empty_kg

        total_mass_equiv_product_B_kg = (flow_equiv_quantity.mass_kg + stillage_mass_equiv_product_B_kg)
        transport_B_kgco2 += get_route_emissions(total_mass_equiv_product_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 += flow_equiv_quantity.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 += 0
        assembly_kgco2 += 0
        transport_B_kgco2 += 0
        install_kgco2 += 0
    # --------------------------------------



    # ! Overview
    total = (dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 + recond_kgco2 +
             new_glass_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2 + waste_transport_kgco2)

    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "System Disassembly": disassembly_kgco2,
        "Recondition": recond_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
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


def run_scenario_remanufacture(
        processes: ProcessSettings,
        transport: TransportModeConfig,
        group: IGUGroup,
        seal_geometry: SealGeometry,
        flow_start: FlowState,
        initial_stats: Dict[str, float],
        interactive: bool = True,
        equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: System is disassembled for Remanufacture (Product Upgrade)
    """
    logger.info("Running Scenario: Remanufacture")
    if interactive:
        print_header("Scenario: Remanufacture")

    # ! Calculate on-site dismantling emissions based on original area
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2

    # ! On-Site Removal
    site_yield_loss = 0.0
    if interactive:
        site_yield_loss_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str) / 100.0 if site_yield_loss_str else 0.0

    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    if interactive and site_yield_loss > 0:
        removed_mass = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        print(f"  > Yield Loss from On-site Building Dismantling ({site_yield_loss:.1%}): {removed_mass:.2f} kg sent to Waste.")

    # ! Transport A (Origin Site -> Processor)
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
        n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
        stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg

    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)

    # ! Packaging
    packaging_kgco2 = flow_post_site_yield_loss.igus * packaging_factor_per_igu(processes)

    # ! Disassembly activities Emissions based on available yield
    disassembly_kgco2 = flow_post_site_yield_loss.area_m2 * DISASSEMBLY_KGCO2_PER_M2
    flow_post_disassembly = apply_yield_loss(flow_post_site_yield_loss, YIELD_DISASSEMBLY_REMANUFACTURE)

    replaced_pane_mass = 0
    replaced_pane_ratio = 0
    if group.glazing_type == "double":
        replaced_pane_ratio = (group.thickness_inner_mm / (group.thickness_inner_mm + group.thickness_outer_mm))
        replaced_pane_mass = replaced_pane_ratio * flow_post_disassembly.mass_kg
    elif group.glazing_type == "triple":
        replaced_pane_ratio = (group.thickness_inner_mm / (group.thickness_inner_mm + group.thickness_centre_mm + group.thickness_outer_mm))
        replaced_pane_mass = replaced_pane_ratio * flow_post_disassembly.mass_kg

    removed_mass_disassembly = flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg
    if interactive:

        print(
            f"  > Yield Loss at System Disassembly Stage ({YIELD_DISASSEMBLY_REMANUFACTURE:.1%}): {removed_mass_disassembly:.2f} kg sent to Waste. \n"
            f"  > Removal of Outer pane ({replaced_pane_ratio:.1%}): {float(replaced_pane_mass):.2f} kg set to Waste.")

    # ! New (coated) glass required for remanufactured unit
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_kgco2 = replaced_pane_mass * ef_new_glass

    logger.info(
        f"New Glass Required: {replaced_pane_mass:.2f} kg, equivalent to {new_glass_kgco2:.2f} kgCO2e")

    # ! Assembly IGU
    # Material-based Calculation
    # i. Configure Spacer EF (kgCO2/linear metre)
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Configure Sealant EF (kgCO2/kg)
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_post_disassembly.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = (mat_masses["spacer_length_m"]) * scale_factor
    mass_sealant_needed_kg = (mat_masses["sealant_kg"]) * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)

    # iv. Re-Assembly Energy
    process_energy_kgco2 = flow_post_disassembly.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2

    assembly_kgco2 = new_glass_kgco2 + embodied_new_mat_kgco2 + process_energy_kgco2

    logger.info(
        f"New Materials Required: Spacer {length_spacer_needed_m:.2f} m, Sealant {mass_sealant_needed_kg:.2f} kg -> {embodied_new_mat_kgco2:.2f} kgCO2e"
        f"\n Assembly: {process_energy_kgco2:.2f} kgCO2e "
        f"\n Total Emissions Associated with Re-manufacture: {assembly_kgco2:.2f} kgCO2e")

    # ! Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("Configuration for next-use destination required:")
            next_location = prompt_location("final installation location for reused IGUs")
            transport.reuse = next_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )

    # ! Transport B (Processor -> Next Use Location)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
        n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
        stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

    total_mass_B_kg = flow_post_disassembly.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

    # ! Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    # ! Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
        # i. On-Site Yield Losses
        mass_loss_yield_losses = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        waste_transport_kgco2 += get_route_emissions(mass_loss_yield_losses, "origin_to_landfill", processes,
                                                     transport)


        # ii. Disassembly & Remanufacture Yield Loss (Processor)
        mass_loss_disassembly = (flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg) + removed_mass_disassembly
        waste_transport_kgco2 += get_route_emissions(mass_loss_disassembly, "processor_to_landfill", processes,
                                                     transport)
    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False

    # NEW GLASS
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg - flow_post_disassembly.mass_kg
    additional_new_glass_kgco2 = new_glass_mass * ef_new_glass
    new_glass_kgco2 += additional_new_glass_kgco2

    # IGU
    # Material-based Calculation (carry sealant and spacer from above)

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor_equiv_quant = 1 - (flow_post_disassembly.area_m2 / flow_start.area_m2)
    flow_equiv_quantity = apply_yield_loss(flow_start, scale_factor_equiv_quant)

    additional_length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor_equiv_quant
    additional_mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor_equiv_quant
    additional_embodied_new_mat_kgco2 = (additional_length_spacer_needed_m * ef_spacer) + (additional_mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    additional_process_energy_kgco2 = flow_equiv_quantity.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    additional_assembly_kgco2 = additional_embodied_new_mat_kgco2 + additional_process_energy_kgco2
    assembly_kgco2 += additional_assembly_kgco2

    if equivalent_product:
        logger.info(
            f"Additional New Glass Required: {new_glass_mass:.2f}kg, equivalent to {additional_new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Additional Assembly: Spacer {additional_length_spacer_needed_m:.2f}m, "
            f"Additional Sealant {additional_mass_sealant_needed_kg:.2f}kg -> {additional_assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        # ! Transport B (Processor -> Next use)
        stillage_mass_equiv_product_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_equiv_product_B = ceil(flow_equiv_quantity.igus / processes.igus_per_stillage)
            stillage_mass_equiv_product_B_kg = n_stillages_equiv_product_B * processes.stillage_mass_empty_kg

        total_mass_equiv_product_B_kg = (flow_equiv_quantity.mass_kg + stillage_mass_equiv_product_B_kg)
        transport_B_kgco2 += get_route_emissions(total_mass_equiv_product_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 += flow_equiv_quantity.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 += 0
        assembly_kgco2 += 0
        transport_B_kgco2 += 0
        install_kgco2 += 0
    # --------------------------------------
    # ! Overview
    total = (dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 +
             new_glass_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2 + waste_transport_kgco2)

    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "System Disassembly": disassembly_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2
    }

    return ScenarioResult(
        scenario_name="Remanufacture",
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

def run_scenario_repurpose(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    interactive: bool = True,
    repurpose_intensity: str = None,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: System is disassembled for components to be repurposed (into different product)
    """
    logger.info("Running Scenario: Component Repurpose")
    if interactive:
        print_header("Scenario: Component Repurpose")
    
    # ! On-Site Removal
    site_yield_loss = 0.0
    if interactive:
        site_yield_loss_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str)/100.0 if site_yield_loss_str else 0.0
    
    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    if interactive and site_yield_loss > 0:
        loss = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        print(f"  > Yield Loss from On-site Building Dismantling: {loss:.2f} kg Waste.")
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # ! Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)

    # ! Packaging
    packaging_kgco2 = flow_post_site_yield_loss.igus * packaging_factor_per_igu(processes)

    # ! Disassembly activities based on available yield
    disassembly_kgco2 = flow_post_site_yield_loss.area_m2 * DISASSEMBLY_KGCO2_PER_M2

    # ! Disassembly (10% loss as standard - configure in project_parameters file)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REPURPOSE * 100}% yield loss for disassembly for repurpose.")
    flow_post_disassembly = apply_yield_loss(flow_post_site_yield_loss, YIELD_DISASSEMBLY_REUSE)

    if interactive:
        loss = flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg
        print(f"  > Yield Loss at System Disassembly Stage ({YIELD_DISASSEMBLY_REUSE:.1%}): {loss:.2f} kg Waste.")

    # ! Repurpose Intensity
    if interactive:
        logger.info("Select embodied carbon intensity of repurposing activities:")
        logger.info("  Light/Medium/Heavy")
        rep_preset = prompt_choice("Intensity", ["Light", "Medium", "Heavy"], default="Medium")
    elif repurpose_intensity:
        rep_preset = repurpose_intensity
    else:
        rep_preset = "Medium"
    
    rep_factor = REPURPOSE_MEDIUM_KGCO2_PER_M2
    if rep_preset == "Light": rep_factor = REPURPOSE_LIGHT_KGCO2_PER_M2
    if rep_preset == "Heavy": rep_factor = REPURPOSE_HEAVY_KGCO2_PER_M2
    
    repurpose_kgco2 = flow_post_disassembly.area_m2 * rep_factor

    # ! Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("Configuration for next-use destination required::")
            repurpose_dst = prompt_location("Installation location for repurposed product")
            transport.reuse = repurpose_dst
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )

    # ! Transport B (Processor -> Reuse)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
    
    total_mass_B_kg = flow_post_disassembly.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)


    # ! New glass required to reach equivalent quantity
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass

    logger.info(
        f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

    # ! Assembly IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_start.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    process_energy_kgco2 = flow_start.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    logger.info(
        f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
        f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

    # ! Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("Configuration for Site of Next Use required:")
            next_location = prompt_location("Final installation location for IGUs (from new float glass)")
            transport.reuse = next_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )

    # ! Transport B (Processor -> Next use as recycled product)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
        n_stillages_B = ceil(flow_start.igus / processes.igus_per_stillage)
        stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

    total_mass_B_kg = flow_start.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

    # ! Installation
    install_kgco2 = flow_start.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2


    # ! Note, currently considered as zero value given that an assumption for the repurposed product is not yet made
    install_kgco2 = flow_post_disassembly.area_m2 * 0

    # ! Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # i.) Removal Yield Loss (Origin)
         mass_loss_on_site_removal = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_on_site_removal, "origin_to_landfill", processes, transport)
         
         # ii.) Disassembly Yield Loss (Processor)
         mass_loss_disassembly = flow_post_site_yield_loss.mass_kg - flow_post_disassembly.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_disassembly, "processor_to_landfill", processes, transport)

    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass
    # ! Assembly IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_start.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)
    # ! Assembly Energy
    process_energy_kgco2 = flow_start.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    if equivalent_product:
        logger.info(
            f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
            f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        if "processor_to_reuse" not in processes.route_configs:
            if interactive:
                print("Configuration for Site of Next Use required:")
                next_location = prompt_location("Final installation location for IGUs (from new float glass)")
                transport.reuse = next_location
                processes.route_configs["processor_to_reuse"] = configure_route(
                    "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
                )
        # ! Transport B (Processor -> Next use)
        stillage_mass_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_B = ceil(flow_start.igus / processes.igus_per_stillage)
            stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

        total_mass_B_kg = flow_start.mass_kg + stillage_mass_B_kg
        transport_B_kgco2 += get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 = flow_start.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 = 0
        assembly_kgco2 = 0
        transport_B_kgco2 += 0
        install_kgco2 = 0
    # --------------------------------------
    total = (dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 +
             repurpose_kgco2 +  waste_transport_kgco2 + transport_B_kgco2 +
             new_glass_kgco2 + assembly_kgco2 + install_kgco2 )
    
    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "System Disassembly": disassembly_kgco2,
        "Repurpose": repurpose_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2

    }
    
    return ScenarioResult(
        scenario_name=f"Repurpose Intensity ({rep_preset})",
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
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    interactive: bool = True,
    send_intact: bool = None,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario: Closed-loop Recycling
    """
    logger.info("Running Scenario: Closed-loop Recycling")
    if interactive:
        print_header("Scenario: Closed-loop Recycling")
    # ! Decision: IGUs sent intact to processor?
    if interactive:
        send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    elif send_intact is None:
        send_intact = True
    
    # ! On-site removal + Break IGU
    site_yield_loss = 0.0
    yield_break = 0.0
    
    # ! Standard removal yield
    if interactive:
        # Change default yield loss for sending in-tact IGUs here (default = 0)
        site_yield_loss_str = input(style_prompt("% yield loss at removal from building (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str)/100.0 if site_yield_loss_str else 0.0

    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    flow_step1 = apply_yield_loss(flow_post_site_yield_loss, yield_break)

    # ! Emissions
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2
    if send_intact:
        dismantling_kgco2 += (flow_post_site_yield_loss.area_m2 * DISASSEMBLY_KGCO2_PER_M2)
    if not send_intact:
        # Breaking emissions
        dismantling_kgco2 += flow_post_site_yield_loss.area_m2 * BREAKING_KGCO2_PER_M2

    # ! Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)

    # ! Processor fractions
    # Laminated Glass Logic: Here, the option to send in-tact applies
    # If in-tact applies and laminated (e.g. 44.2) is present in product, the reduced recovery yield applies to relevant pane only
    # If in-tact does not apply (if not send_intact), the reduced recovery yield applies to the whole product
    # Check glass types.
    is_laminated = False
    total_mass_laminated = 0
    non_laminated_yield = 0
    if send_intact:
        if "laminated" in group.glass_type_outer.lower():
            total_mass_laminated += (group.thickness_outer_mm * 0.001 * flow_post_site_yield_loss.area_m2 * 2500)
        if "laminated" in group.glass_type_centre.lower():
            total_mass_laminated += (group.thickness_centre_mm * 0.001 * flow_post_site_yield_loss.area_m2 * 2500)
        if "laminated" in group.glass_type_inner.lower():
            total_mass_laminated += (group.thickness_inner_mm * 0.001 * flow_post_site_yield_loss.area_m2 * 2500)
        is_laminated = True
        non_laminated_yield = 1 - (total_mass_laminated / flow_post_site_yield_loss.mass_kg)

    if not send_intact:
        if ("laminated" in group.glass_type_outer.lower()
                or "laminated" in group.glass_type_centre.lower()
                or "laminated" in group.glass_type_inner.lower()):
            is_laminated = True
            non_laminated_yield = 0

    
    # Check thickness (e.g. 44.2, we rely on type string)
    # The database loader will populate glass_type_outer/inner with "laminated" if applicable
    # If product name contains "44.2", we assume laminated.
    # Group names often don't travel here, but let's trust the type.

    if is_laminated:
        logger.warning(f"Laminated glass detected! If shipped in-tact, the closed-loop yield for the relevant laminated pane is reduced to 0%. "
                       f"If not in-tact, the closed-loop yield for the full product is reduced to 0%.")
        CULLET_FLOAT_SHARE = non_laminated_yield

    else:
        CULLET_FLOAT_SHARE = SHARE_CULLET_FLOAT

    flow_float = apply_yield_loss(flow_post_site_yield_loss, (1.0 - CULLET_FLOAT_SHARE))
    flow_open_loop = apply_yield_loss(flow_post_site_yield_loss, (CULLET_FLOAT_SHARE))

    if interactive:
        if is_laminated:
             print(f"LAMINATED GLASS DETECTED. If shipped in-tact, the closed-loop yield for the relevant laminated pane is reduced to 0%. "
                       f"If not in-tact, the closed-loop yield for the full product is reduced to 0%. \n"
                   f"Non-laminated yield = {non_laminated_yield:.2%}")
        else:
             loss = flow_post_site_yield_loss.mass_kg - flow_float.mass_kg
             print(f"  > Float Plant Quality Check (Yield {CULLET_FLOAT_SHARE:.1%}): {loss:.2f} kg rejected.")
        
        print(f"  > Sending {flow_float.mass_kg:.2f} kg to Closed-Loop Recycling and {flow_open_loop.mass_kg:.2f} kg to Open-Loop Recycling.")


    # ! Glass Reprocessing
    #   i.Recovered Yield to be reprocessed
    flat_glass_reprocessing_kgco2 = processes.flat_glass_reprocessing_kgco2_per_kg * flow_post_site_yield_loss.mass_kg

    # ! Assembly IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_post_site_yield_loss.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    process_energy_kgco2 = flow_post_site_yield_loss.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    logger.info(
        f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
        f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

    # ! Next location
    if "processor_to_reuse" not in processes.route_configs:
        if interactive:
            print("Configuration for Site of Next Use required:")
            next_location = prompt_location("Final installation location for IGUs (from recycled glass)")
            transport.reuse = next_location
            processes.route_configs["processor_to_reuse"] = configure_route(
                "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
            )

    # ! Transport B (Processor -> Next use as recycled product)
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
        n_stillages_B = ceil(flow_start.igus / processes.igus_per_stillage)
        stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

    total_mass_B_kg = flow_start.mass_kg + stillage_mass_B_kg
    transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

    # ! Installation
    install_kgco2 = flow_start.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    # ! Open-Loop Transport. Here, it is assumed that open-loop recycling takes place in the form of glass wool.
    open_loop_transport_kgco2 = 0.0
    if "processor_to_open_loop_GW" not in processes.route_configs:
        if interactive:
            print("Configuration for Site of Open-Loop Recycling Facility required:")
            open_loop_location_GW = prompt_location("Glass Wool Recycling Facility Location")
            transport.open_loop_GW = open_loop_location_GW
            processes.route_configs["processor_to_open_loop_GW"] = configure_route(
                "Processor -> Glass Wool Recycling Facility", transport.processor, transport.open_loop_GW, interactive=True
            )
        open_loop_transport_kgco2 += get_route_emissions(flow_open_loop.mass_kg, "processor_to_open_loop_GW", processes, transport)

    # ! Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. On-Site Yield Loss (Origin)
         mass_loss_on_site_removal = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg # flow_post_site_yield_loss is post-removal
         waste_transport_kgco2 += get_route_emissions(mass_loss_on_site_removal, "origin_to_landfill", processes, transport)

         # 2. Cullet Share Loss (Processor -> Landfill or Open-Loop)
         # flow_float is post-cullet-share
         mass_loss_float = flow_post_site_yield_loss.mass_kg - flow_float.mass_kg - flow_open_loop.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_float, "processor_to_landfill", processes, transport)

    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False

    # NEW GLASS
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass

    # IGU
    # Material-based Calculation (carry sealant and spacer from above)

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor_equiv_quant = 1 - (flow_post_site_yield_loss.area_m2 / flow_start.area_m2)
    flow_equiv_quantity = apply_yield_loss(flow_start, scale_factor_equiv_quant)

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor_equiv_quant
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor_equiv_quant
    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)

    # ! Assembly Energy
    process_energy_kgco2 = flow_equiv_quantity.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2
    assembly_kgco2 += assembly_kgco2

    if equivalent_product:
        logger.info(
            f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
            f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        # ! Transport B (Processor -> Next use)
        stillage_mass_equiv_product_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_equiv_product_B = ceil(flow_equiv_quantity.igus / processes.igus_per_stillage)
            stillage_mass_equiv_product_B_kg = n_stillages_equiv_product_B * processes.stillage_mass_empty_kg

        total_mass_equiv_product_B_kg = (flow_equiv_quantity.mass_kg + stillage_mass_equiv_product_B_kg)
        transport_B_kgco2 += get_route_emissions(total_mass_equiv_product_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 += flow_equiv_quantity.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 += 0
        assembly_kgco2 += 0
        transport_B_kgco2 += 0
        install_kgco2 += 0
    # --------------------------------------

    total = (dismantling_kgco2 + transport_A_kgco2 +
             flat_glass_reprocessing_kgco2 + new_glass_kgco2 +
             assembly_kgco2 + transport_B_kgco2 + install_kgco2 +
             open_loop_transport_kgco2 + waste_transport_kgco2)
    
    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Transport A": transport_A_kgco2,
        "Glass Reprocessing": flat_glass_reprocessing_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
        "Open-Loop Transport": open_loop_transport_kgco2,
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
    seal_geometry: SealGeometry,
    flow_start: FlowState,
    interactive: bool = True,
    send_intact: bool = None,
    equivalent_product: bool = None,
) -> ScenarioResult:
    """
    Scenario (e): Open-loop Recycling
    """
    logger.info("Running Scenario: Open-loop Recycling")
    if interactive:
        print_header("Scenario: Open-loop Recycling")
    
    # ! Decision: IGUs sent intact to processor?
    if interactive:
        send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    elif send_intact is None:
        send_intact = True
    
    # ! On-site Yield
    site_yield_loss = 0.0
    yield_break = 0.0
    if interactive:
        site_yield_loss_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
        site_yield_loss = float(site_yield_loss_str)/100.0 if site_yield_loss_str else 0.0

    flow_post_site_yield_loss = apply_yield_loss(flow_start, site_yield_loss)
    
    dismantling_kgco2 = flow_start.area_m2 * processes.e_site_kgco2_per_m2
    if send_intact:
        dismantling_kgco2 += (flow_post_site_yield_loss.area_m2 * DISASSEMBLY_KGCO2_PER_M2)
    if not send_intact:
        # Breaking emissions
        dismantling_kgco2 += flow_post_site_yield_loss.area_m2 * BREAKING_KGCO2_PER_M2

    # ! Transport A (Origin -> Processor)
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_site_yield_loss.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg

    total_mass_A_kg = flow_post_site_yield_loss.mass_kg + stillage_mass_A_kg
    transport_A_kgco2 = get_route_emissions(total_mass_A_kg, "origin_to_processor", processes, transport)
    
    # ! Processor Fractions
    CULLET_CW_SHARE = SHARE_CULLET_OPEN_LOOP_GW
    CULLET_CONT_SHARE = SHARE_CULLET_OPEN_LOOP_CONT
    
    # ! Task: "Recycle to Glasswool / Container"
    open_loop_transport_kgco2 = 0.0
    if "processor_to_open_loop_GW" or "processor_to_open_loop_CG" not in processes.route_configs:
        mass_gw_kg = (flow_post_site_yield_loss.mass_kg * CULLET_CW_SHARE)
        mass_cont_kg = (flow_post_site_yield_loss.mass_kg * CULLET_CONT_SHARE)
        if interactive:
            print("Configuration for Site of Open-Loop Recycling Facility required:")
            open_loop_location_GW = prompt_location("Glass Wool Recycling Facility Location")
            open_loop_location_CG = prompt_location("Container Glass Recycling Facility Location")
            transport.open_loop_GW = open_loop_location_GW
            transport.open_loop_CG = open_loop_location_CG
            processes.route_configs["processor_to_open_loop_GW"] = configure_route(
                "Processor -> Glass Wool Recycling Facility", transport.processor, transport.open_loop_GW, interactive=True
            )
            processes.route_configs["processor_to_open_loop_CG"] = configure_route(
                "Processor -> Container Glass Recycling Facility", transport.processor, transport.open_loop_CG,
                interactive=True
            )
        open_loop_transport_kgco2 += get_route_emissions(mass_gw_kg, "processor_to_open_loop_GW", processes,
                                                         transport)
        open_loop_transport_kgco2 += get_route_emissions(mass_cont_kg, "processor_to_open_loop_CG",
                                                         processes, transport)

    
    # ! Calculate final flow before waste calc
    final_useful_fraction = CULLET_CW_SHARE + CULLET_CONT_SHARE # 80%
    
    if interactive:
        loss = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
        print(f"  > Useful Fraction (GW {CULLET_CW_SHARE:.1%} + Cont {CULLET_CONT_SHARE:.1%}): {loss:.2f} kg rejected as waste.")
    
    # ! Waste Transport
    waste_transport_kgco2 = 0.0
    if transport.landfill:
         # 1. Removal Yield Loss (Origin)
         mass_loss_on_site_removal = flow_start.mass_kg - flow_post_site_yield_loss.mass_kg
         waste_transport_kgco2 += get_route_emissions(mass_loss_on_site_removal, "origin_to_landfill", processes, transport)

    #--------------------------------------------
    # ! NEW GLASS REQUIRED TO REACH EQUIVALENT QUANTITY
    if interactive:
        equivalent_product = prompt_yes_no("Would you like to evaluate with consideration of the equivalent original batch?", default=False)
    elif equivalent_product is None:
        equivalent_product = False
    ef_new_glass = EF_MAT_GLASS_VIRGIN
    new_glass_mass = flow_start.mass_kg
    new_glass_kgco2 = new_glass_mass * ef_new_glass
    # ! Assembly IGU
    # Material-based Calculation
    # i. Determine Spacer EF
    ef_spacer = EF_MAT_SPACER_ALU  # Default
    if group.spacer_material == "aluminium":
        ef_spacer = EF_MAT_SPACER_ALU
    elif group.spacer_material == "steel":
        ef_spacer = EF_MAT_SPACER_STEEL
    elif group.spacer_material == "warm_edge_composite":
        ef_spacer = EF_MAT_SPACER_SWISS

    # ii. Determine Sealant EF
    ef_sealant = EF_MAT_SEALANT

    # iii. Calculate Mass of New Materials needed
    # We calculate masses for the FULL group, then scale down by the current flow count
    mat_masses = calculate_material_masses(group, seal_geometry)
    scale_factor = flow_start.igus / group.quantity if group.quantity > 0 else 0.0

    length_spacer_needed_m = mat_masses["spacer_length_m"] * scale_factor
    mass_sealant_needed_kg = mat_masses["sealant_kg"] * scale_factor

    embodied_new_mat_kgco2 = (length_spacer_needed_m * ef_spacer) + (mass_sealant_needed_kg * ef_sealant)
    # ! Assembly Energy
    process_energy_kgco2 = flow_start.area_m2 * PROCESS_ENERGY_ASSEMBLY_KGCO2_PER_M2
    assembly_kgco2 = embodied_new_mat_kgco2 + process_energy_kgco2

    if equivalent_product:
        logger.info(
            f"New Glass Required: {new_glass_mass:.2f}kg, equivalent to {new_glass_kgco2:.2f}kgCO2e")

        logger.info(
            f"Assembly: Spacer {length_spacer_needed_m:.2f}m, "
            f"Sealant {mass_sealant_needed_kg:.2f}kg -> {assembly_kgco2:.2f} kgCO2e")

        # ! Next location
        if "processor_to_reuse" not in processes.route_configs:
            if interactive:
                print("Configuration for Site of Next Use required:")
                next_location = prompt_location("Final installation location for IGUs (from new float glass)")
                transport.reuse = next_location
                processes.route_configs["processor_to_reuse"] = configure_route(
                    "Processor -> Reuse", transport.processor, transport.reuse, interactive=True
                )
        # ! Transport B (Processor -> Next use)
        stillage_mass_B_kg = 0.0
        if processes.igus_per_stillage > 0:
            n_stillages_B = ceil(flow_start.igus / processes.igus_per_stillage)
            stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg

        total_mass_B_kg = flow_start.mass_kg + stillage_mass_B_kg
        transport_B_kgco2 = get_route_emissions(total_mass_B_kg, "processor_to_reuse", processes, transport)

        # ! Installation
        install_kgco2 = flow_start.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2

    if not equivalent_product:
        new_glass_kgco2 = 0
        assembly_kgco2 = 0
        transport_B_kgco2 = 0
        install_kgco2 = 0
    # --------------------------------------

    total = (dismantling_kgco2 + transport_A_kgco2 + open_loop_transport_kgco2 + waste_transport_kgco2 +
                new_glass_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2)
    
    by_stage = {
        "Building Site Dismantling": dismantling_kgco2,
        "Transport A": transport_A_kgco2,
        "Open-Loop Transport": open_loop_transport_kgco2,
        "Landfill Transport (Waste)": waste_transport_kgco2,
        "New Glass": new_glass_kgco2,
        "Re-Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2,
    }
    
    return ScenarioResult(
        scenario_name=f"Open-Loop Recycling",
        total_emissions_kgco2=total,
        by_stage=by_stage,
        initial_igus=flow_start.igus,
        final_igus= 0,
        initial_area_m2=flow_start.area_m2,
        final_area_m2= 0,
        initial_mass_kg=flow_start.mass_kg,
        final_mass_kg= 0,
        yield_percent=final_useful_fraction * 100.0
    )

