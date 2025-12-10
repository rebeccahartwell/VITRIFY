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
    apply_yield_loss, compute_route_distances, packaging_factor_per_igu, calculate_material_masses
)
from .utils.input_helpers import prompt_yes_no, prompt_location, prompt_choice, print_header, style_prompt

logger = logging.getLogger(__name__)

def run_scenario_system_reuse(
    processes: ProcessSettings,
    transport: TransportModeConfig,
    group: IGUGroup,
    flow_start: FlowState,
    initial_stats: Dict[str, float],
    initial_masses: Dict[str, float]
) -> ScenarioResult:
    """
    Scenario (a): System Reuse
    """
    logger.info("Running Scenario: System Reuse")
    print_header("Scenario (a): System Reuse")
    
    # a) On-Site Removal + Yield
    yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
    yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)
    
    # Calculate dismantling emissions based on original area
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # 1. Transport A
    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"] * transport.backhaul_factor
    ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor) if processes.route_A_mode == "HGV lorry+ferry" else 0.0
    
    # Packaging (stillages) for transported amount
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    mass_A_t = (flow_post_removal.mass_kg + stillage_mass_A_kg) / 1000.0
    transport_A_kgco2 = mass_A_t * (truck_A_km * transport.emissionfactor_truck + ferry_A_km * transport.emissionfactor_ferry)
    
    # Packaging emissions (embodied)
    pkg_per_igu = packaging_factor_per_igu(processes)
    packaging_kgco2 = flow_post_removal.igus * pkg_per_igu
    
    # b) Repair decision
    repair_needed = prompt_yes_no("Does the IGU system require repair?", default=False)
    repair_kgco2 = 0.0
    flow_post_repair = flow_post_removal
    
    if repair_needed:
        # Yield loss 20%
        logger.info(f"Applying {YIELD_REPAIR*100}% yield loss for repair process.")
        flow_post_repair = apply_yield_loss(flow_post_removal, YIELD_REPAIR)
        
        # Calculate repair emissions on the remaining area 
        repair_kgco2 = flow_post_repair.area_m2 * REPAIR_KGCO2_PER_M2
    
    # c) New recipient location
    reuse_location = prompt_location("new recipient building / reuse destination")
    transport.reuse = reuse_location
    
    # d) Transport B
    distances_B = compute_route_distances(transport)
    truck_B_km = distances_B["truck_B_km"] * transport.backhaul_factor
    ferry_B_km = (distances_B["ferry_B_km"] * transport.backhaul_factor) if processes.route_B_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_repair.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    mass_B_t = (flow_post_repair.mass_kg + stillage_mass_B_kg) / 1000.0
    transport_B_kgco2 = mass_B_t * (truck_B_km * transport.emissionfactor_truck + ferry_B_km * transport.emissionfactor_ferry)
    
    # Installation
    install_kgco2 = flow_post_repair.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    # e) Overview
    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + repair_kgco2 + transport_B_kgco2 + install_kgco2
    
    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging (Stillages)": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Repair": repair_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2
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
    initial_stats: Dict[str, float]
) -> ScenarioResult:
    """
    Scenario (b): Component Reuse
    """
    logger.info("Running Scenario: Component Reuse")
    print_header("Scenario (b): Component Reuse")
    
    # a) On-Site Removal
    yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
    yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # b) Transport A
    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"] * transport.backhaul_factor
    ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor) if processes.route_A_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    mass_A_t = (flow_post_removal.mass_kg + stillage_mass_A_kg) / 1000.0
    transport_A_kgco2 = mass_A_t * (truck_A_km * transport.emissionfactor_truck + ferry_A_km * transport.emissionfactor_ferry)
    
    # Packaging
    packaging_kgco2 = flow_post_removal.igus * packaging_factor_per_igu(processes)

    # c) System Disassembly (20% loss)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REUSE*100}% yield loss for disassembly.")
    DISASSEMBLY_YIELD = YIELD_DISASSEMBLY_REUSE
    flow_post_disassembly = apply_yield_loss(flow_post_removal, DISASSEMBLY_YIELD)
    
    # Disassembly Emissions
    # Used flow_post_disassembly (post-yield) area
    disassembly_kgco2 = flow_post_disassembly.area_m2 * DISASSEMBLY_KGCO2_PER_M2
    
    # d) Recondition
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
    next_location = prompt_location("final installation location for reused IGUs")
    transport.reuse = next_location
    
    # g) Transport B
    distances_B = compute_route_distances(transport)
    truck_B_km = distances_B["truck_B_km"] * transport.backhaul_factor
    ferry_B_km = (distances_B["ferry_B_km"] * transport.backhaul_factor) if processes.route_B_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
         
    mass_B_t = (flow_post_disassembly.mass_kg + stillage_mass_B_kg) / 1000.0
    transport_B_kgco2 = mass_B_t * (truck_B_km * transport.emissionfactor_truck + ferry_B_km * transport.emissionfactor_ferry)
    
    # Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 + recond_kgco2 + assembly_kgco2 + transport_B_kgco2 + install_kgco2
    
    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Disassembly": disassembly_kgco2,
        "Recondition": recond_kgco2,
        "Assembly": assembly_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2
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
    initial_stats: Dict[str, float]
) -> ScenarioResult:
    """
    Scenario (c): Component Repurpose
    """
    logger.info("Running Scenario: Component Repurpose")
    print_header("Scenario (c): Component Repurpose")
    
    # a) On-Site Removal
    yield_removal_str = input(style_prompt("% yield loss at on-site removal (0-100) [default=0]: ")).strip()
    yield_removal = float(yield_removal_str)/100.0 if yield_removal_str else 0.0
    flow_post_removal = apply_yield_loss(flow_start, yield_removal)
    dismantling_kgco2 = initial_stats["total_IGU_surface_area_m2"] * processes.e_site_kgco2_per_m2
    
    # Transport A
    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"] * transport.backhaul_factor
    ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor) if processes.route_A_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_A_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_post_removal.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    mass_A_t = (flow_post_removal.mass_kg + stillage_mass_A_kg) / 1000.0
    transport_A_kgco2 = mass_A_t * (truck_A_km * transport.emissionfactor_truck + ferry_A_km * transport.emissionfactor_ferry)
    packaging_kgco2 = flow_post_removal.igus * packaging_factor_per_igu(processes)

    # c) Disassembly (10% loss)
    logger.info(f"Applying {YIELD_DISASSEMBLY_REPURPOSE*100}% yield loss for disassembly (repurpose).")
    DISASSEMBLY_YIELD = YIELD_DISASSEMBLY_REPURPOSE
    flow_post_disassembly = apply_yield_loss(flow_post_removal, DISASSEMBLY_YIELD)
    # Used flow_post_disassembly (post-yield) area
    disassembly_kgco2 = flow_post_disassembly.area_m2 * DISASSEMBLY_KGCO2_PER_M2
    
    # e) Repurpose Intensity
    logger.info("Select repurposing intensity:")
    logger.info("  light/medium/heavy")
    rep_preset = prompt_choice("Intensity", ["light", "medium", "heavy"], default="medium")
    
    rep_factor = REPURPOSE_MEDIUM_KGCO2_PER_M2
    if rep_preset == "light": rep_factor = REPURPOSE_LIGHT_KGCO2_PER_M2
    if rep_preset == "heavy": rep_factor = REPURPOSE_HEAVY_KGCO2_PER_M2
    
    repurpose_kgco2 = flow_post_disassembly.area_m2 * rep_factor
    
    # f) Next location
    repurpose_dst = prompt_location("installation location for repurposed product")
    transport.reuse = repurpose_dst
    
    # g) Transport B
    distances_B = compute_route_distances(transport)
    truck_B_km = distances_B["truck_B_km"] * transport.backhaul_factor
    ferry_B_km = (distances_B["ferry_B_km"] * transport.backhaul_factor) if processes.route_B_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_B_kg = 0.0
    if processes.igus_per_stillage > 0:
         n_stillages_B = ceil(flow_post_disassembly.igus / processes.igus_per_stillage)
         stillage_mass_B_kg = n_stillages_B * processes.stillage_mass_empty_kg
    mass_B_t = (flow_post_disassembly.mass_kg + stillage_mass_B_kg) / 1000.0
    transport_B_kgco2 = mass_B_t * (truck_B_km * transport.emissionfactor_truck + ferry_B_km * transport.emissionfactor_ferry)
    
    # Installation
    install_kgco2 = flow_post_disassembly.area_m2 * INSTALL_SYSTEM_KGCO2_PER_M2
    
    total = dismantling_kgco2 + packaging_kgco2 + transport_A_kgco2 + disassembly_kgco2 + repurpose_kgco2 + transport_B_kgco2 + install_kgco2
    
    by_stage = {
        "Dismantling (E_site)": dismantling_kgco2,
        "Packaging": packaging_kgco2,
        "Transport A": transport_A_kgco2,
        "Disassembly": disassembly_kgco2,
        "Repurposing": repurpose_kgco2,
        "Transport B": transport_B_kgco2,
        "Installation": install_kgco2
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
    flow_start: FlowState
) -> ScenarioResult:
    """
    Scenario (d): Closed-loop Recycling
    """
    logger.info("Running Scenario: Closed-loop Recycling")
    print_header("Scenario (d): Closed-loop Recycling")
    
    # a) Intact decision
    send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    
    # b/c) On-site removal + Break IGU
    yield_removal = 0.0
    yield_break = 0.0
    
    # Standard removal yield
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
        
    # d) Transport A
    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"] * transport.backhaul_factor
    ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor) if processes.route_A_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_step2.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg
    
    mass_A_t = (flow_step2.mass_kg + stillage_mass_A_kg) / 1000.0
    transport_A_kgco2 = mass_A_t * (truck_A_km * transport.emissionfactor_truck + ferry_A_km * transport.emissionfactor_ferry)
    
    # e) Processor fractions
    CULLET_FLOAT_SHARE = SHARE_CULLET_FLOAT
    flow_float = apply_yield_loss(flow_step2, 1.0 - CULLET_FLOAT_SHARE)
    
    # f) Dispatch to float plant
    float_plant = prompt_location("Second Use Processing Facility (float glass plant)")
    transport.reuse = float_plant
    
    distances_B = compute_route_distances(transport)
    truck_B_km = distances_B["truck_B_km"] * transport.backhaul_factor
    ferry_B_km = (distances_B["ferry_B_km"] * transport.backhaul_factor) if processes.route_B_mode == "HGV lorry+ferry" else 0.0
    
    mass_B_t = flow_float.mass_kg / 1000.0 # Bulk cullet, no stillages
    transport_B_kgco2 = mass_B_t * (truck_B_km * transport.emissionfactor_truck + ferry_B_km * transport.emissionfactor_ferry)
    
    total = dismantling_kgco2 + breaking_kgco2 + transport_A_kgco2 + transport_B_kgco2
    
    by_stage = {
        "Dismantling/Removal": dismantling_kgco2,
        "Breaking": breaking_kgco2,
        "Transport A": transport_A_kgco2,
        "Transport B (Float)": transport_B_kgco2
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
    flow_start: FlowState
) -> ScenarioResult:
    """
    Scenario (e): Open-loop Recycling
    """
    logger.info("Running Scenario: Open-loop Recycling")
    print_header("Scenario (e): Open-loop Recycling")
    
    # a) Intact vs break
    send_intact = prompt_yes_no("Send IGUs intact to processor?", default=True)
    
    # yield
    yield_removal = 0.0
    yield_break = 0.0
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

    # Transport A
    distances = compute_route_distances(transport)
    truck_A_km = distances["truck_A_km"] * transport.backhaul_factor
    ferry_A_km = (distances["ferry_A_km"] * transport.backhaul_factor) if processes.route_A_mode == "HGV lorry+ferry" else 0.0
    
    stillage_mass_A_kg = 0.0
    if send_intact and processes.igus_per_stillage > 0:
         n_stillages = ceil(flow_step2.igus / processes.igus_per_stillage)
         stillage_mass_A_kg = n_stillages * processes.stillage_mass_empty_kg

    mass_A_t = (flow_step2.mass_kg + stillage_mass_A_kg) / 1000.0
    transport_A_kgco2 = mass_A_t * (truck_A_km * transport.emissionfactor_truck + ferry_A_km * transport.emissionfactor_ferry)
    
    # Processor Fractions
    CULLET_CW_SHARE = SHARE_CULLET_OPEN_LOOP_GW
    CULLET_CONT_SHARE = SHARE_CULLET_OPEN_LOOP_CONT
    
    # Task: "Recycle to Glasswool / Container"
    # d) Optional transport
    model_transport = prompt_yes_no("Model transport to glasswool/container plants?", default=False)
    open_loop_transport_kgco2 = 0.0
    
    if model_transport:
        gw_plant = prompt_location("Glasswool plant")
        cont_plant = prompt_location("Container glass plant")
        
        # Calculate transport B for these streams
        # Glasswool
        tr_gw = TransportModeConfig(origin=transport.processor, processor=transport.processor, reuse=gw_plant)
        dist_gw = compute_route_distances(tr_gw)
        mass_gw_t = (flow_step2.mass_kg * CULLET_CW_SHARE) / 1000.0
        
        ferry_gw_km = 0.0
        if processes.route_B_mode == "HGV lorry+ferry":
             ferry_gw_km = dist_gw["ferry_B_km"]
        
        e_gw = mass_gw_t * (dist_gw["truck_B_km"] * transport.emissionfactor_truck + ferry_gw_km * transport.emissionfactor_ferry)
        
        # Container
        tr_cont = TransportModeConfig(origin=transport.processor, processor=transport.processor, reuse=cont_plant)
        dist_cont = compute_route_distances(tr_cont)
        mass_cont_t = (flow_step2.mass_kg * CULLET_CONT_SHARE) / 1000.0
        
        ferry_cont_km = 0.0
        if processes.route_B_mode == "HGV lorry+ferry":
            ferry_cont_km = dist_cont["ferry_B_km"]
            
        e_cont = mass_cont_t * (dist_cont["truck_B_km"] * transport.emissionfactor_truck + ferry_cont_km * transport.emissionfactor_ferry)
        
        open_loop_transport_kgco2 = e_gw + e_cont

    total = dismantling_kgco2 + breaking_kgco2 + transport_A_kgco2 + open_loop_transport_kgco2
    
    by_stage = {
        "Dismantling": dismantling_kgco2,
        "Breaking": breaking_kgco2,
        "Transport A": transport_A_kgco2,
        "Open-Loop Transport": open_loop_transport_kgco2
    }
    
    final_useful_fraction = CULLET_CW_SHARE + CULLET_CONT_SHARE # 20%
    flow_final = apply_yield_loss(flow_step2, 1.0 - final_useful_fraction)
    
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
