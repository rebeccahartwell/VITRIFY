import logging
import sys
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os
import re

# Append parent dir to sys.path to allow imports from sibling modules if executed directly
# But better to assume executed as module or package.
# We will assume python -m igu_recovery.main

from igu_recovery.constants import ROUTE_A_MODE, ROUTE_B_MODE
from igu_recovery.models import (
    ProcessSettings, TransportModeConfig, IGUGroup, FlowState, RouteConfig, Location,
    SealGeometry, IGUCondition
)


from igu_recovery.utils.input_helpers import (
    prompt_choice, prompt_location, prompt_igu_source, define_igu_system_from_manual,
    define_igu_system_from_database, ask_igu_condition_and_eligibility, print_igu_geometry_overview,
    print_scenario_overview, print_header, prompt_seal_geometry, parse_db_row_to_group,
    prompt_yes_no, style_prompt, C_SUCCESS, C_RESET, C_HEADER, format_and_clean_report_dataframe,
    configure_route
)
from igu_recovery.utils.calculations import (
    aggregate_igu_groups, compute_igu_mass_totals, haversine_km, get_osrm_distance,
    run_sensitivity_analysis
)
from igu_recovery.scenarios import (
    run_scenario_system_reuse,
    run_scenario_component_reuse,
    run_scenario_remanufacture,
    run_scenario_repurpose,
    run_scenario_closed_loop_recycling,
    run_scenario_open_loop_recycling,
    run_scenario_landfill,
)
from igu_recovery.logging_conf import setup_logging
from igu_recovery.visualization import Visualizer
from igu_recovery.reporting import save_scenario_md # NEW
from igu_recovery.models import IGUCondition

logger = logging.getLogger(__name__)

vis = Visualizer(mode="batch_run")
vis.plot_product_intensity_stacked_2x2(
            "local_automated_analysis_report.csv",
            "european_automated_analysis_report.csv",
            products=["1.1_DGU_6_16_6_Bronze","1.3_TGU_6_16_6_16_6_Bronze_Low-e"]
        )