import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns
import pandas as pd
import numpy as np
import math
import os
from datetime import datetime
from typing import List, Dict, Optional
from .models import ScenarioResult
import logging

#Seaborn colour palettes https://www.practicalpythonfordatascience.com/ap_seaborn_palette

logger = logging.getLogger(__name__)

# ============================================================================
# VISUALIZER CLASS
# ============================================================================

# 1. Load Report Save Location
current_directory =  os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Build the path to reports relative to the current directory
report_directory = os.path.join(current_directory, 'reports')

class Visualizer:
    def __init__(self, mode: str = "single_run"):
        """
        Initialize Visualizer.
        mode: 'single_run' (for interactive) or 'batch_run' (for automated analysis)
        """
        self.mode = mode
        self.output_root = report_directory
        self._setup_style()
        self.session_dir = self._create_session_dir()

    def _setup_style(self):
        """Configure matplotlib for professional, publication-quality plots."""
        # Clean foundation
        plt.rcParams.update(plt.rcParamsDefault)
        
        # Typography
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['Arial', 'Helvetica', 'Calibri', 'DejaVu Sans'],
            'font.size': 12,
            'axes.titlesize': 16,
            'axes.titleweight': 'bold',
            'axes.labelsize': 13,
            'xtick.labelsize': 11,
            'ytick.labelsize': 11,
            'legend.fontsize': 11,
            'figure.titlesize': 18,
            'figure.titleweight': 'bold',
            'text.color': '#2C3E50',
            'axes.labelcolor': '#2C3E50',
            'xtick.color': '#2C3E50',
            'ytick.color': '#2C3E50'
        })

        # Layout & Lines
        plt.rcParams.update({
            'axes.spines.top': False,
            'axes.spines.right': False,
            'axes.spines.left': False,  # Clean look, use grid
            'axes.spines.bottom': True,
            'axes.linewidth': 1.2,
            'grid.color': '#E0E0E0',
            'grid.linestyle': ':',
            'grid.linewidth': 1.0,
            'axes.grid': True,          # Enable grid by default
            'axes.grid.axis': 'y',      # Horizontal grid only usually
            'axes.axisbelow': True      # Grid behind plot elements
        })
        
        # Color Palette (Premium)
        self.colors = {
            'emissions_light': '#FF8A65',   # Light Coral
            'emissions_dark': '#D32F2F',    # Dark Red
            'yield_light': '#81C784',       # Light Green
            'yield_dark': '#388E3C',        # Forest Green
            'neutral': '#5D6D7E',           # Slate Blue/Grey
            'text': '#2C3E50',              # Dark Blue Grey
            'bg': '#FFFFFF'                 # White
        }

    def _create_session_dir(self) -> str:
        """Create the specific directory for this session's plots."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subdir = "batch_run" if self.mode == "batch_run" else "single_run"
        path = os.path.join(self.output_root, subdir, timestamp)
        os.makedirs(path, exist_ok=True)
        return path

    def get_save_path(self, filename: str) -> str:
        return os.path.join(self.session_dir, filename)

    # ============================================================================
    # SINGLE RUN PLOTS
    # ============================================================================

    def plot_single_scenario_breakdown(self, result: ScenarioResult, product_name: str = ""):
        """Bar chart of emission stages for one scenario."""
        if not result.by_stage: return

        stages = list(result.by_stage.keys())
        values = list(result.by_stage.values())
        
        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
        
        # Monochromatic elegant bars
        bars = ax.bar(stages, values, color=self.colors['neutral'], alpha=0.85, width=0.6, edgecolor='none')
        
        # Labels
        ax.set_ylabel("Emissions (kgCO2e)", fontweight='bold')
        ax.set_title(f"Detailed Emissions Breakdown\n{result.scenario_name}", pad=20, loc='left')
        plt.xticks(rotation=45, ha='right')
        
        # Remove Y-axis ticks for cleaner look if we have value labels
        ax.yaxis.set_ticks_position('none') 
        
        # Value tags
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height + (max(values)*0.01),
                        f'{height:.1f}',
                        ha='center', va='bottom', fontsize=10, fontweight='bold', color=self.colors['text'])

        plt.tight_layout()
        
        # Save
        safe_name = result.scenario_name.replace(" ", "_").lower()
        filepath = self.get_save_path(f"breakdown_{safe_name}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved breakdown to: {filepath}")

    def plot_scenario_comparison(self, results: List[ScenarioResult], product_name: str = ""):
        """Compare all scenarios (Emissions vs Yield)."""
        if not results: return

        names = [r.scenario_name.replace(" ", "\n") for r in results]
        emissions = [r.total_emissions_kgco2 for r in results]
        yields = [r.total_recovered_yield for r in results]
        
        fig, ax1 = plt.subplots(figsize=(12, 7), dpi=150)
        
        # 1. Emissions (Bars)
        bars = ax1.bar(names, emissions, color=self.colors['emissions_light'], alpha=0.8, label='Total Emissions', width=0.5)
        
        ax1.set_ylabel('Total Emissions (kgCO2e/batch)', color=self.colors['emissions_dark'], fontweight='bold')
        ax1.tick_params(axis='y', labelcolor=self.colors['emissions_dark'])
        ax1.grid(True, axis='y', linestyle=':', alpha=0.6)
        ax1.set_ylim(0, max(emissions)*1.15) # Room for labels

        # Labels on bars (inside if possible, or top)
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax1.text(bar.get_x() + bar.get_width()/2., height/2,
                         f'{height:.0f}',
                         ha='center', va='center', fontweight='bold', fontsize=10, color='white')
        
        # 2. Yield (Line)
        ax2 = ax1.twinx()
        ax2.plot(names, yields, color=self.colors['yield_dark'], marker='o', linewidth=3, markersize=10, 
                 markerfacecolor='white', markeredgewidth=2, label='Recovered Yield')
        
        ax2.set_ylabel('Recovered Yield (%)', color=self.colors['yield_dark'], fontweight='bold')
        ax2.tick_params(axis='y', labelcolor=self.colors['yield_dark'])
        ax2.set_ylim(0, 115)
        ax2.spines['right'].set_visible(False) # Clean look
        ax2.spines['top'].set_visible(False)
        ax2.grid(False) # Only one grid

        # Labels on line
        for i, val in enumerate(yields):
            ax2.text(i, val + 5, f'{val:.0f}%', ha='center', color=self.colors['yield_dark'], fontweight='bold', fontsize=10)

        # Title
        plt.title(f"Scenario Comparison: Impact vs Circularity\n{product_name}", pad=20, loc='left')
        
        plt.tight_layout()
        filepath = self.get_save_path("scenario_comparison.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved comparison to: {filepath}")


    # ============================================================================
    # BATCH ANALYSIS PLOTS
    # ============================================================================

    def plot_batch_summary(self, df: pd.DataFrame):
        """Generate summary plots for the entire batch."""
        if df.empty: return
        
        # Call all batch visualization methods
        self.generate_all_batch_plots(df)
        self.plot_product_intensity_stacked_2x2(
            "local_automated_analysis_report.csv",
            "european_automated_analysis_report.csv",
            products=["1.1_DGU_6_16_6_Bronze","1.3_TGU_6_16_6_16_6_Bronze_Low-e"]
        )




    def _plot_batch_distribution(self, df: pd.DataFrame):
        fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
        
        try:
            pivot = df.pivot_table(index='Product Name', columns='Scenario', values='Total Emissions (kgCO2e/batch)')
            sorted_cols = pivot.median().sort_values().index
            pivot = pivot[sorted_cols]
            
            # Modern Boxplot customization
            boxprops = dict(linestyle='-', linewidth=1.5, color=self.colors['neutral'])
            medianprops = dict(linestyle='-', linewidth=2, color=self.colors['emissions_dark'])
            flierprops = dict(marker='o', markerfacecolor=self.colors['neutral'], markersize=4, linestyle='none', alpha=0.5)
            
            pivot.boxplot(ax=ax, rot=45, grid=False, 
                          boxprops=boxprops, medianprops=medianprops, flierprops=flierprops,
                          patch_artist=True) # Fill boxes?

            # Fill colors manually if using pandas boxplot is tricky, 
            # but standard pandas boxplot with patch_artist=True fills with blue by default.
            # Does pandas exposed easy fill control? No.
            # Let's rely on line styling for elegance or switch to matplotlib.
            # Matplotlib direct approach:
            
        except:
            # Fallback to matplotlib direct if pivot fails
            pass
            
        # Re-do with direct matplotlib for better style control
        data_to_plot = []
        labels = []
        # Get sorted scenarios
        scenarios = df['Scenario'].unique()
        # sort by median
        medians = df.groupby('Scenario')['Total Emissions (kgCO2e/batch)'].median().sort_values()
        
        for sc in medians.index:
            data = df[df['Scenario'] == sc]['Total Emissions (kgCO2e/batch)'].dropna().values
            data_to_plot.append(data)
            labels.append(sc)
            
        if not data_to_plot:
            logger.warning("No data to plot in batch distribution.")
            plt.close(fig)
            return

        bplot = ax.boxplot(data_to_plot, patch_artist=True, labels=labels,
                           flierprops=dict(marker='o', markersize=4, alpha=0.5, color=self.colors['neutral']))
        
        # Coloring
        for patch in bplot['boxes']:
            patch.set_facecolor('#ECEFF1') # Light Grey fill
            patch.set_edgecolor(self.colors['neutral'])
            patch.set_alpha(0.7)
            
        for median in bplot['medians']:
            median.set_color(self.colors['emissions_dark'])
            median.set_linewidth(2)

        ax.set_ylabel("Total Emissions (kgCO2e/batch)", fontweight='bold')
        ax.set_title("Emissions Distribution by Scenario", loc='left', pad=15)
        plt.xticks(rotation=45, ha='right')
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        filepath = self.get_save_path("batch_emissions_distribution.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved batch distribution to: {filepath}")

    def _plot_batch_scatter(self, df: pd.DataFrame):
        """Scatter plot of Yield (X) vs Emissions (Y), colored by Scenario."""
        fig, ax = plt.subplots(figsize=(11, 8), dpi=150)
        
        scenarios = df['Scenario'].unique()
        if len(scenarios) == 0:
            logger.warning("No scenarios found for batch scatter plot.")
            plt.close(fig)
            return

        # Use a qualitative colormap from matplotlib
        cmap = plt.get_cmap('tab10') # or 'Set2' for softer
        
        for i, sc in enumerate(scenarios):
            subset = df[df['Scenario'] == sc]
            # Big bubbles with transparency
            ax.scatter(subset['Recovered Yield (%)'], subset['Total Emissions (kgCO2e/batch)'],
                       label=sc, alpha=0.6, edgecolors='white', linewidth=1.5, s=150, color=cmap(i))
            
        ax.set_xlabel("Material Yield (%)", fontweight='bold')
        ax.set_ylabel("Total Emissions (kgCO2e/batch)", fontweight='bold')
        ax.set_title("Eco-Efficiency Frontier: Yield vs Carbon", loc='left', pad=15)
        
        # Grid
        ax.grid(True, linestyle='--', alpha=0.4)
        
        # Legend outside
        ax.legend(title="Scenario", bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False)
        
        plt.tight_layout()
        filepath = self.get_save_path("batch_yield_vs_carbon.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved batch scatter to: {filepath}")

    def _plot_product_intensity(self, df: pd.DataFrame):
        sns.set_theme(style="whitegrid")

        for product, subset in df.groupby("Product Name"):
            # Sort scenarios by total emissions for readability
            subset = subset.sort_values("Total Emissions (kgCO2e/batch)")

            # Create a new figure and axis for each product
            fig, ax = plt.subplots(figsize=(8, 6))

            # Plot the horizontal bar chart
            sns.barplot(
                data=subset,
                x="Total Emissions (kgCO2e/batch)",
                y="Scenario",
                color="steelblue",
                ax=ax
            )

            # Add title and labels
            ax.set_title(product)
            ax.set_xlabel("Total Emission Intensity (kgCO2e/m2)")
            ax.set_ylabel("Scenario")

            # Adjust layout so labels/legend are not clipped
            fig.tight_layout()

            # Save the figure with a product-specific filename
            filepath = self.get_save_path(f"{product}_intensity.png")
            fig.savefig(filepath, dpi=300, bbox_inches="tight")
            print(f"   [Plot] Saved intensity plot to: {filepath}")

            # Close the figure to free memory
            plt.close(fig)

    def _plot_product_intensity_faceted(self, df: pd.DataFrame):
        sns.set_theme(style="whitegrid")

        # Sort scenarios within each product (important for readability)
        df_sorted = df.sort_values(
            ["Product Name", "Total Emission Intensity (kgCO2e/m2)"]
        )

        g = sns.FacetGrid(
            df_sorted,
            col="Product Name",
            sharex=True,
            sharey=False,
            height=6,
            aspect=0.8
        )

        g.map_dataframe(
            sns.barplot,
            x="Total Emissions (kgCO2e/batch)",
            y="Scenario",
            color="steelblue"
        )

        g.set_axis_labels("Total Emissions (kgCO2e/batch)", "Scenario")
        g.set_titles("{col_name}")

        # Apply layout to the FacetGrid figure
        g.fig.tight_layout()

        filepath = self.get_save_path("product_intensity_faceted.png")
        g.fig.savefig(filepath, dpi=300, bbox_inches="tight")
        plt.close(g.fig)  # 👈 correct way to close FacetGrid

        print(f"   [Plot] Saved intensity plot to: {filepath}")

    def _plot_product_intensity_stacked(self, df: pd.DataFrame):
        sns.set_theme(style="whitegrid")
        mpl.rcParams["font.family"] = "Verdana"

        stack_cols = [
            "[Stage] Building Site Dismantling",
            "[Stage] Transport: Site->Processor",
            "[Stage] System Disassembly",
            "[Stage] Repair",
            "[Stage] Recondition",
            "[Stage] Repurpose",
            "[Stage] Glass Reprocessing",
            "[Stage] New Glass",
            "[Stage] IGU Re-Assembly",
            "[Stage] Packaging",
            "[Stage] Transport: Processor->Next Use",
            "[Stage] Next Use Installation",
            "[Stage] Transport: Processor->Open-Loop Facility",
            "[Stage] Transport: Landfill Disposal",
        ]
        palette_colors = [
            "#1B9E77",
            "#FC8D62",
            "#7570B3",
            "#A6D854",
            "#D95F02",
            "#8DA0CB",
            "#E7298A",
            "#66C2A5",
            "#E6AB02",
            "#E78AC3",
            "#66A61E",
            "#FFD92F",
            "#666666",
            "#A6761D",
        ]
        palette = sns.color_palette(palette_colors[:len(stack_cols)])
        colors = dict(zip(stack_cols, palette))
        # Initiate if landfill to be omitted:
        #df = df[df['Recovered Yield (%)'] > 0.0]
        df = df[df["Scenario"] != "Closed-loop (Intact)"]
        df = df[df["Scenario"] != "Open-loop (Intact)"]
        if df.empty:
            raise ValueError("No data left after scenario filtering.")
        xmax = df["Total Emission Intensity (kgCO2e/m2)"].max()

        for product, subset in df.groupby("Product Name"):
            subset = subset.copy()
            subset[stack_cols] = subset[stack_cols].div(subset["Initial Global Area (m2)"], axis=0)
            subset["Total"] = subset[stack_cols].sum(axis=1)
            subset = subset.sort_values("Total")

            y = np.arange(len(subset))
            left = np.zeros(len(subset))

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.yaxis.grid(False)
            ax.xaxis.grid(False)

            for col in stack_cols:
                ax.barh(
                    y,
                    subset[col],
                    height = 0.8,
                    left=left,
                    label=col,
                    color=colors[col],
                    edgecolor="none"
                )
                left += subset[col]


            upper = math.ceil((xmax * 1.05) / 10) * 10
            ax.set_xlim(0, upper)
            ax.set_yticks(y)
            ax.set_yticklabels(subset["Scenario"],fontsize=12)
            ax.set_xlabel("Emissions (kgCO$_2$e/m$^2$)", fontsize=12)
            #ax.set_title(product)

            # Total labels
            for i, total in enumerate(subset["Total"]):
                ax.text(
                    total + 0.5,
                    i,
                    f"{total:.0f}",
                    va="center",
                    fontsize = 12,
                    fontweight="bold")
            handles, labels = ax.get_legend_handles_labels()
            ax.legend(
                handles,
                [l.replace("[Stage] ", "") for l in labels],
                title="Emission Source",
                bbox_to_anchor=(1.05, 1),
                loc="upper left"
            )

            #fig.tight_layout()

            filepath = self.get_save_path(f"{product}_intensity_stacked.png")
            fig.savefig(filepath, dpi=600, bbox_inches="tight")
            plt.close(fig)

            print(f"   [Plot] Saved intensity plot to: {filepath}")

    #Plot Local and European on the same plot
    def plot_product_intensity_comparison_from_csv(
            self,
            csv_path1: str,
            csv_path2: str,
            product_filter=None,
            labels=("Local", "European")
    ):
        import numpy as np
        import pandas as pd
        import seaborn as sns
        import matplotlib.pyplot as plt
        import matplotlib as mpl
        import math


        df1 = pd.read_csv(csv_path1)
        df2 = pd.read_csv(csv_path2)

        sns.set_theme(style="whitegrid")
        mpl.rcParams["font.family"] = "Verdana"

        stack_cols = [
            "[Stage] Building Site Dismantling",
            "[Stage] Transport: Site->Processor",
            "[Stage] System Disassembly",
            "[Stage] Repair",
            "[Stage] Recondition",
            "[Stage] Repurpose",
            "[Stage] Glass Reprocessing",
            "[Stage] New Glass",
            "[Stage] IGU Re-Assembly",
            "[Stage] Packaging",
            "[Stage] Transport: Processor->Next Use",
            "[Stage] Next Use Installation",
            "[Stage] Transport: Processor->Open-Loop Facility",
            "[Stage] Transport: Landfill Disposal",
        ]

        palette_colors = [
            "#1B9E77", "#FC8D62", "#7570B3", "#A6D854",
            "#D95F02", "#8DA0CB", "#E7298A", "#66C2A5",
            "#E6AB02", "#E78AC3", "#66A61E", "#FFD92F",
            "#666666", "#A6761D",
        ]
        palette = sns.color_palette(palette_colors[:len(stack_cols)])
        colors = dict(zip(stack_cols, palette))

        # --- Prepare data ---
        df1 = df1.copy()
        df2 = df2.copy()

        df1["Source"] = labels[0]
        df2["Source"] = labels[1]

        df = pd.concat([df1, df2], ignore_index=True)

        # Filter scenarios
        df = df[df["Scenario"] != "Closed-loop (Intact)"]
        df = df[df["Scenario"] != "Open-loop (Intact)"]
        if df.empty:
            raise ValueError("No data left after scenario filtering.")

        # Optional product filter
        if product_filter is not None:
            if isinstance(product_filter, str):
                df = df[df["Product Name"] == product_filter]
            else:
                df = df[df["Product Name"].isin(product_filter)]

        if df.empty:
            print("No data to plot.")
            return

        xmax = df["Total Emission Intensity (kgCO2e/m2)"].max()

        # --- Plot per product ---
        for product, subset in df.groupby("Product Name"):

            subset = subset.copy()
            if subset.empty:
                continue

            # Normalize
            subset[stack_cols] = subset[stack_cols].div(
                subset["Initial Global Area (m2)"], axis=0
            )
            subset["Total"] = subset[stack_cols].sum(axis=1)

            # Sort by scenario + source for consistency
            subset = subset.sort_values(["Scenario", "Source"])

            scenarios = subset["Scenario"].unique()
            y_base = np.arange(len(scenarios))

            bar_height = 0.35

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.yaxis.grid(False)
            ax.xaxis.grid(False)

            for i, source in enumerate(labels):
                sub = subset[subset["Source"] == source]

                # Align y positions
                y = y_base + (i - 0.5) * bar_height

                left = np.zeros(len(sub))

                for col in stack_cols:
                    ax.barh(
                        y,
                        sub[col],
                        height=bar_height,
                        left=left,
                        color=colors[col],
                        edgecolor="none"
                    )
                    left += sub[col].values

                # Total labels
                for j, total in enumerate(sub["Total"]):
                    ax.text(
                        total + 0.5,
                        y[j],
                        f"{total:.0f}",
                        va="center",
                        fontsize=10,
                        fontweight="bold"
                    )

            # Y labels (centered)
            ax.set_yticks(y_base)
            ax.set_yticklabels(scenarios, fontsize=12)

            upper = math.ceil((xmax * 1.05) / 10) * 10
            ax.set_xlim(0, upper)

            ax.set_xlabel("Emissions (kgCO$_2$e/m$^2$)", fontsize=12)

            # Legend (only once for stacks)
            handles = [
                plt.Rectangle((0, 0), 1, 1, color=colors[col])
                for col in stack_cols
            ]
            ax.legend(
                handles,
                [c.replace("[Stage] ", "") for c in stack_cols],
                title="Emission Source",
                bbox_to_anchor=(1.05, 1),
                loc="upper left"
            )

            # Add source legend manually
            for i, source in enumerate(labels):
                ax.barh([], [], color="gray", label=source)

            ax.legend(title="Emission Source", bbox_to_anchor=(1.05, 1), loc="upper left")

            filename = f"{product}_comparison_stacked.png"
            filepath = self.get_save_path(filename)

            fig.savefig(filepath, dpi=600, bbox_inches="tight")
            plt.close(fig)

            print(f"[Plot] Saved comparison plot to: {filepath}")

    def plot_product_intensity_stacked_2x2(
            self,
            csv_local: str,
            csv_europe: str,
            products: list,
    ):
        """
        Create a 2x2 stacked horizontal bar matrix.

        Rows    = geographical datasets
        Columns = products

        Example layout:
            (a) Local - DGU      (b) Local - TGU
            (c) Europe - DGU     (d) Europe - TGU
        """

        # ------------------------------------------------------------------
        # STYLE
        # ------------------------------------------------------------------

        sns.set_theme(style="white")

        mpl.rcParams["font.family"] = "Verdana"
        mpl.rcParams["axes.titlesize"] = 14
        mpl.rcParams["axes.labelsize"] = 12
        mpl.rcParams["xtick.labelsize"] = 10
        mpl.rcParams["ytick.labelsize"] = 10

        # ------------------------------------------------------------------
        # DATA
        # ------------------------------------------------------------------

        stack_cols = [
            "[Stage] Building Site Dismantling",
            "[Stage] Transport: Site->Processor",
            "[Stage] System Disassembly",
            "[Stage] Repair",
            "[Stage] Recondition",
            "[Stage] Repurpose",
            "[Stage] Glass Reprocessing",
            "[Stage] New Glass",
            "[Stage] IGU Re-Assembly",
            "[Stage] Packaging",
            "[Stage] Transport: Processor->Next Use",
            "[Stage] Next Use Installation",
            "[Stage] Transport: Processor->Open-Loop Facility",
            "[Stage] Transport: Landfill Disposal",
        ]

        palette_colors = [
            "#1B9E77",
            "#FC8D62",
            "#7570B3",
            "#A6D854",
            "#D95F02",
            "#8DA0CB",
            "#E7298A",
            "#66C2A5",
            "#E6AB02",
            "#E78AC3",
            "#66A61E",
            "#FFD92F",
            "#666666",
            "#A6761D",
        ]

        colors = dict(zip(stack_cols, palette_colors))

        # ------------------------------------------------------------------
        # LOAD DATA
        # ------------------------------------------------------------------

        df_local = pd.read_csv(csv_local)
        df_europe = pd.read_csv(csv_europe)

        def clean(df):
            df = df.copy()

            df = df[df["Scenario"] != "Closed-loop (Intact)"]
            df = df[df["Scenario"] != "Open-loop (Intact)"]

            return df

        datasets = [
            ("Local", clean(df_local)),
            ("European", clean(df_europe)),
        ]

        # ------------------------------------------------------------------
        # GLOBAL X LIMIT
        # ------------------------------------------------------------------

        xmax = max(
            df_local["Total Emission Intensity (kgCO2e/m2)"].max(),
            df_europe["Total Emission Intensity (kgCO2e/m2)"].max(),
        )

        upper = math.ceil((xmax * 1.10) / 10) * 10

        # ------------------------------------------------------------------
        # FIGURE
        # ------------------------------------------------------------------

        fig, axes = plt.subplots(
            nrows=2,
            ncols=2,
            figsize=(13, 9),
            sharex=True,
        )

        fig.patch.set_facecolor("white")

        panel_labels = ["(a)", "(b)", "(c)", "(d)"]

        # ------------------------------------------------------------------
        # PLOTTING
        # ------------------------------------------------------------------

        panel_counter = 0

        for row_idx, (geo_name, df_geo) in enumerate(datasets):

            for col_idx, product in enumerate(products):

                ax = axes[row_idx, col_idx]

                subset = df_geo[
                    df_geo["Product Name"] == product
                    ].copy()

                if subset.empty:
                    ax.axis("off")
                    continue

                # ----------------------------------------------------------
                # NORMALIZE
                # ----------------------------------------------------------

                subset[stack_cols] = subset[stack_cols].div(
                    subset["Initial Global Area (m2)"],
                    axis=0,
                )

                subset["Total"] = subset[stack_cols].sum(axis=1)

                # Reverse display order
                subset = subset.iloc[::-1]

                y = np.arange(len(subset))


                # ----------------------------------------------------------
                # STACKED BARS
                # ----------------------------------------------------------

                y = np.arange(len(subset))

                left = np.zeros(len(subset))

                for col in stack_cols:
                    ax.barh(
                        y,
                        subset[col],
                        left=left,
                        height=0.8,
                        color=colors[col],
                        edgecolor="none",
                    )

                    left += subset[col].values

                # ----------------------------------------------------------
                # AXES FORMAT
                # ----------------------------------------------------------

                ax.set_xlim(0, upper)

                ax.set_yticks(y)

                ax.set_yticklabels(
                    subset["Scenario"],
                    fontsize=9,
                )

                ax.set_facecolor("white")

                ax.grid(False)

                # panel title
                short_name = (
                    "DGU"
                    if "DGU" in product
                    else "TGU"
                )

                ax.set_title(
                    f"{geo_name} - {short_name}",
                    fontsize=12,
                    fontweight="bold",
                    pad=4,
                )

                # subplot label
                ax.text(
                    -0.15,
                    1.03,
                    panel_labels[panel_counter],
                    transform=ax.transAxes,
                    fontsize=12,
                    fontweight="bold",
                )

                panel_counter += 1

                # ----------------------------------------------------------
                # TOTAL LABELS
                # ----------------------------------------------------------

                for i, total in enumerate(subset["Total"]):
                    ax.text(
                        total + 1,
                        i,
                        f"{total:.0f}",
                        va="center",
                        fontsize=8,
                        fontweight="bold",
                    )

                # ----------------------------------------------------------
                # SPINES
                # ----------------------------------------------------------

                ax.spines["top"].set_linewidth(0.5)
                ax.spines["right"].set_linewidth(0.5)

                ax.spines["left"].set_linewidth(0.5)
                ax.spines["bottom"].set_linewidth(0.5)

        # ------------------------------------------------------------------
        # SHARED X LABEL
        # ------------------------------------------------------------------

        fig.supxlabel(
            "Emissions (kgCO$_2$e/m$^2$)",
            fontsize=12,
            y=0.1,
        )

        # ------------------------------------------------------------------
        # LEGEND
        # ------------------------------------------------------------------

        handles = [
            plt.Rectangle(
                (0, 0),
                1,
                1,
                color=colors[col],
            )
            for col in stack_cols
        ]

        legend_labels = [
            c.replace("[Stage] ", "")
            for c in stack_cols
        ]

        fig.legend(
            handles,
            legend_labels,
            title="Emission Source",
            ncol=5,
            loc="lower center",
            bbox_to_anchor=(0.5, 0),
            fontsize=8,
            title_fontsize=9,
            frameon=True,
        )

        # ------------------------------------------------------------------
        # LAYOUT
        # ------------------------------------------------------------------

        fig.tight_layout(rect=[0, 0.08, 1, 1])

        # ------------------------------------------------------------------
        # SAVE
        # ------------------------------------------------------------------

        filepath = self.get_save_path(
            "2x2_product_intensity_matrix.png"
        )
        fig.savefig(
            filepath,
            dpi=600,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )

        plt.close(fig)

        print(f"[Plot] Saved 2x2 matrix plot to: {filepath}")

    def _plot_average_batch_intensity(self, df: pd.DataFrame):
        """Bar chart of average Intensity (kgCO2e/m2 output) where yield > 0."""
        subset = df
        # To remove Landfill from plot, intitate the following:
        # subset = df[df['Recovered Yield (%)'] > 1.0]
        if subset.empty: return

        grouped = subset.groupby('Scenario')['Total Emission Intensity (kgCO2e/m2)'].mean().sort_values()
        if grouped.empty: return

        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
        
        # Gradient colors from green (low intensity = good) to red (high intensity = bad)
        colors = plt.cm.RdYlGn_r([i/len(grouped) for i in range(len(grouped))])
        
        # Horizontal Bars with gradient
        bars = ax.barh(grouped.index, grouped.values, color=colors, edgecolor='white', linewidth=1.5)
        
        ax.set_xlabel("Avg Intensity (kgCO2e per m² recovered)", fontweight='bold')
        ax.set_title("Carbon Intensity of Recovered Glass", loc='left', pad=15)
        ax.grid(True, axis='x', linestyle=':', alpha=0.5)
        
        # Remove Y axis line
        ax.spines['left'].set_visible(False)
        
        # Value tags
        for bar in bars:
            width = bar.get_width()
            ax.text(width + (grouped.max()*0.02), bar.get_y() + bar.get_height()/2, 
                    f'{width:.2f}', 
                    va='center', color=self.colors['text'], fontweight='bold', fontsize=10)
            
        plt.tight_layout()
        filepath = self.get_save_path("batch_avg_intensity.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved intensity plot to: {filepath}")

    # ============================================================================
    # NEW ADVANCED VISUALIZATIONS
    # ============================================================================

    def plot_grouped_bar_emissions(self, results: List[ScenarioResult], product_name: str = ""):
        """Grouped bar chart: Total emissions by scenario for a single product."""
        if not results: return
        
        names = [r.scenario_name for r in results]
        emissions = [r.total_emissions_kgco2 for r in results]
        
        # Sort by emissions
        sorted_data = sorted(zip(names, emissions), key=lambda x: x[1])
        names, emissions = zip(*sorted_data)
        
        fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
        
        # Color gradient from green (low) to red (high)
        colors = plt.cm.RdYlGn_r([i/len(emissions) for i in range(len(emissions))])
        
        bars = ax.bar(names, emissions, color=colors, edgecolor='white', linewidth=1.5)
        
        ax.set_ylabel("Total Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title(f"Emissions by Scenario\n{product_name}", loc='left', pad=20)
        plt.xticks(rotation=45, ha='right')
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        # Value labels
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + max(emissions)*0.01,
                    f'{height:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        plt.tight_layout()
        filepath = self.get_save_path("grouped_bar_emissions.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved grouped bar to: {filepath}")

    def plot_stacked_bar_stages(self, results: List[ScenarioResult], product_name: str = ""):
        """Stacked bar chart: Emission breakdown by stage per scenario."""
        if not results: return

        # Collect all unique stages
        all_stages = set()
        for r in results:
            if r.by_stage:
                all_stages.update(r.by_stage.keys())
        all_stages = sorted(list(all_stages))
        
        if not all_stages: return
        
        # Build data matrix
        scenarios = [r.scenario_name for r in results]
        data = {stage: [] for stage in all_stages}
        for r in results:
            for stage in all_stages:
                data[stage].append(r.by_stage.get(stage, 0.0) if r.by_stage else 0.0)
        
        fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
        
        # Stacked bars
        x = range(len(scenarios))
        bottom = [0] * len(scenarios)
        cmap = plt.cm.get_cmap('tab20')
        
        for i, stage in enumerate(all_stages):
            ax.bar(x, data[stage], bottom=bottom, label=stage, color=cmap(i % 20), edgecolor='white', linewidth=0.5)
            bottom = [b + d for b, d in zip(bottom, data[stage])]
        
        ax.set_xticks(x)
        ax.set_xticklabels(scenarios, rotation=45, ha='right')
        ax.set_ylabel("Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title(f"Stage-by-Stage Emission Breakdown\n{product_name}", loc='left', pad=20)
        ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False, fontsize=9)
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        filepath = self.get_save_path("stacked_bar_stages.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved stacked bar to: {filepath}")

    def plot_waterfall(self, result: ScenarioResult, product_name: str = ""):
        """Waterfall chart: Step-by-step emission accumulation."""
        if not result.by_stage: return
        
        stages = list(result.by_stage.keys())
        values = list(result.by_stage.values())
        
        fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
        
        cumulative = 0
        for i, (stage, val) in enumerate(zip(stages, values)):
            # Bar from cumulative to cumulative+val
            ax.bar(i, val, bottom=cumulative, color=self.colors['emissions_light'] if val > 0 else self.colors['yield_dark'],
                   edgecolor='white', linewidth=1.5)
            
            # Connector line
            if i < len(stages) - 1:
                ax.plot([i + 0.4, i + 0.6], [cumulative + val, cumulative + val], 
                        color='#666', linestyle='--', linewidth=1)
            
            cumulative += val
        
        # Total bar
        ax.bar(len(stages), result.total_emissions_kgco2, color=self.colors['emissions_dark'], 
               edgecolor='white', linewidth=1.5)
        
        ax.set_xticks(list(range(len(stages))) + [len(stages)])
        ax.set_xticklabels(stages + ['TOTAL'], rotation=45, ha='right')
        ax.set_ylabel("Cumulative Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title(f"Emission Accumulation: {result.scenario_name}\n{product_name}", loc='left', pad=20)
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        safe_name = result.scenario_name.replace(" ", "_").lower()
        filepath = self.get_save_path(f"waterfall_{safe_name}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved waterfall to: {filepath}")

    def plot_boxplot_batch(self, df: pd.DataFrame):
        """Boxplot: Emission distribution by scenario across all products."""
        if df.empty: return
        
        fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
        
        scenarios = df['Scenario'].unique()
        medians = df.groupby('Scenario')['Total Emissions (kgCO2e/batch)'].median().sort_values()
        
        data_to_plot = []
        labels = []
        for sc in medians.index:
            data = df[df['Scenario'] == sc]['Total Emissions (kgCO2e/batch)'].dropna().values
            data_to_plot.append(data)
            labels.append(sc)
        
        if not data_to_plot: return
        
        bplot = ax.boxplot(data_to_plot, patch_artist=True, labels=labels,
                           flierprops=dict(marker='o', markersize=4, alpha=0.5))
        
        # Color gradient
        colors = plt.cm.viridis([i/len(data_to_plot) for i in range(len(data_to_plot))])
        for patch, color in zip(bplot['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        for median in bplot['medians']:
            median.set_color('red')
            median.set_linewidth(2)
        
        ax.set_ylabel("Total Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title("Emission Distribution by Scenario", loc='left', pad=15)
        plt.xticks(rotation=45, ha='right')
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        filepath = self.get_save_path("boxplot_emissions.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved boxplot to: {filepath}")


    def plot_donut_stages(self, result: ScenarioResult, product_name: str = ""):
        """Donut chart: Stage contribution percentage for one scenario."""
        if not result.by_stage: return
        
        stages = list(result.by_stage.keys())
        values = list(result.by_stage.values())
        
        # Filter out zero values
        filtered = [(s, v) for s, v in zip(stages, values) if v > 0]
        if not filtered: return
        stages, values = zip(*filtered)
        
        fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
        
        colors = plt.cm.Set3([i/len(values) for i in range(len(values))])
        
        wedges, texts, autotexts = ax.pie(values, labels=stages, autopct='%1.1f%%',
                                           colors=colors, startangle=90, 
                                           wedgeprops=dict(width=0.5, edgecolor='white'))
        
        # Center text
        ax.text(0, 0, f'{result.total_emissions_kgco2:.1f}\nkgCO2e',
                ha='center', va='center', fontsize=24, fontweight='bold')
        
        ax.set_title(f"Stage Contribution: {result.scenario_name}\n{product_name}", pad=20)
        
        plt.tight_layout()
        safe_name = result.scenario_name.replace(" ", "_").lower()
        filepath = self.get_save_path(f"donut_{safe_name}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved donut chart to: {filepath}")


    def plot_horizontal_intensity(self, df: pd.DataFrame):
        """Horizontal bar: Carbon intensity ranking by scenario."""
        if df.empty: return
        
        subset = df[df['Recovered Yield (%)'] > 1.0]
        if subset.empty: return
        
        grouped = subset.groupby('Scenario')['Total Emission Intensity (kgCO2e/m2)'].mean().sort_values()
        if grouped.empty: return
        
        fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
        
        colors = plt.cm.RdYlGn_r([i/len(grouped) for i in range(len(grouped))])
        bars = ax.barh(grouped.index, grouped.values, color=colors, edgecolor='white', linewidth=1.5)
        
        ax.set_xlabel("Carbon Intensity (kgCO₂e/m² recovered)", fontweight='bold')
        ax.set_title("Scenario Efficiency Ranking", loc='left', pad=15)
        ax.grid(True, axis='x', linestyle=':', alpha=0.5)
        ax.spines['left'].set_visible(False)
        
        # Value labels
        for bar in bars:
            width = bar.get_width()
            ax.text(width + grouped.max()*0.01, bar.get_y() + bar.get_height()/2,
                    f'{width:.2f}', va='center', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        filepath = self.get_save_path("horizontal_intensity.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved horizontal intensity to: {filepath}")

    # ============================================================================
    # COMPREHENSIVE PLOT GENERATOR
    # ============================================================================

    def generate_all_single_run_plots(self, results: List[ScenarioResult], product_name: str = ""):
        """Generate all applicable plots for a single-run comparison."""
        if not results: return
        
        # Grouped Bar
        self.plot_grouped_bar_emissions(results, product_name)
        
        # Stacked Bar
        self.plot_stacked_bar_stages(results, product_name)
        
        # Scenario Comparison (existing)
        self.plot_scenario_comparison(results, product_name)
        
        # Radar
        #self.plot_radar_comparison(results, product_name)
        
        # Per-scenario plots
        #for r in results:
            #self.plot_waterfall(r, product_name)
            #self.plot_donut_stages(r, product_name)
            #self.plot_tornado_sensitivity(r, product_name=product_name)

        
        print(f"\n   [Complete] All single-run plots saved to: {self.session_dir}")

    def generate_all_batch_plots(self, df: pd.DataFrame):
        """Generate all applicable plots for batch analysis."""
        if df.empty: return
        
        # Distribution plots
        #self.plot_boxplot_batch(df)
        #self.plot_violin_batch(df)
        # Intensity (with gradient colors)
        #self._plot_average_batch_intensity(df)
        #self._plot_product_intensity(df)
        #self._plot_product_intensity_faceted(df)
        self._plot_product_intensity_stacked(df)

        print(f"\n   [Complete] All batch plots saved to: {self.session_dir}")


