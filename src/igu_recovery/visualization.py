import matplotlib.pyplot as plt
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional
from .models import ScenarioResult
import logging

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
        yields = [r.yield_percent for r in results]
        
        fig, ax1 = plt.subplots(figsize=(12, 7), dpi=150)
        
        # 1. Emissions (Bars)
        bars = ax1.bar(names, emissions, color=self.colors['emissions_light'], alpha=0.8, label='Total Emissions', width=0.5)
        
        ax1.set_ylabel('Total Emissions (kgCO2e)', color=self.colors['emissions_dark'], fontweight='bold')
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
                 markerfacecolor='white', markeredgewidth=2, label='Final Yield')
        
        ax2.set_ylabel('Yield (%)', color=self.colors['yield_dark'], fontweight='bold')
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

    def _plot_batch_distribution(self, df: pd.DataFrame):
        fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
        
        try:
            pivot = df.pivot_table(index='Product Name', columns='Scenario', values='Total Emissions (kgCO2e)')
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
        medians = df.groupby('Scenario')['Total Emissions (kgCO2e)'].median().sort_values()
        
        for sc in medians.index:
            data = df[df['Scenario'] == sc]['Total Emissions (kgCO2e)'].dropna().values
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

        ax.set_ylabel("Total Emissions (kgCO2e)", fontweight='bold')
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
            ax.scatter(subset['Yield (%)'], subset['Total Emissions (kgCO2e)'], 
                       label=sc, alpha=0.6, edgecolors='white', linewidth=1.5, s=150, color=cmap(i))
            
        ax.set_xlabel("Material Yield (%)", fontweight='bold')
        ax.set_ylabel("Total Emissions (kgCO2e)", fontweight='bold')
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

    def _plot_batch_intensity(self, df: pd.DataFrame):
        """Bar chart of average Intensity (kgCO2e/m2 output) where yield > 0."""
        subset = df[df['Yield (%)'] > 1.0]
        if subset.empty: return

        grouped = subset.groupby('Scenario')['Intensity (kgCO2e/m²)'].mean().sort_values()
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
        medians = df.groupby('Scenario')['Total Emissions (kgCO2e)'].median().sort_values()
        
        data_to_plot = []
        labels = []
        for sc in medians.index:
            data = df[df['Scenario'] == sc]['Total Emissions (kgCO2e)'].dropna().values
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

    def plot_heatmap(self, df: pd.DataFrame, value_col: str = 'Total Emissions (kgCO2e)'):
        """Heatmap: Product × Scenario matrix."""
        if df.empty: return
        
        try:
            pivot = df.pivot_table(index='Product Name', columns='Scenario', values=value_col, aggfunc='mean')
        except Exception as e:
            logger.warning(f"Could not create heatmap pivot: {e}")
            return
        
        if pivot.empty: return
        
        fig, ax = plt.subplots(figsize=(16, max(8, len(pivot.index) * 0.3)), dpi=150)
        
        # Heatmap
        im = ax.imshow(pivot.values, cmap='RdYlGn_r', aspect='auto')
        
        # Labels
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=45, ha='right', fontsize=9)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index, fontsize=8)
        
        # Colorbar
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label(value_col, fontweight='bold')
        
        ax.set_title(f"Product × Scenario: {value_col}", loc='left', pad=20)
        
        plt.tight_layout()
        safe_col = value_col.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "").lower()
        filepath = self.get_save_path(f"heatmap_{safe_col}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved heatmap to: {filepath}")

    def plot_violin_batch(self, df: pd.DataFrame):
        """Violin plot: Emission density by scenario."""
        if df.empty: return
        
        fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
        
        scenarios = df['Scenario'].unique()
        medians = df.groupby('Scenario')['Total Emissions (kgCO2e)'].median().sort_values()
        
        data_to_plot = []
        labels = []
        for sc in medians.index:
            data = df[df['Scenario'] == sc]['Total Emissions (kgCO2e)'].dropna().values
            if len(data) > 1:  # Violin needs at least 2 points
                data_to_plot.append(data)
                labels.append(sc)
        
        if not data_to_plot: return
        
        parts = ax.violinplot(data_to_plot, showmeans=True, showmedians=True)
        
        # Styling
        for i, pc in enumerate(parts['bodies']):
            pc.set_facecolor(plt.cm.viridis(i/len(data_to_plot)))
            pc.set_edgecolor('black')
            pc.set_alpha(0.7)
        
        ax.set_xticks(range(1, len(labels) + 1))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_ylabel("Total Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title("Emission Density by Scenario", loc='left', pad=15)
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        filepath = self.get_save_path("violin_emissions.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved violin plot to: {filepath}")

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
        ax.text(0, 0, f'{result.total_emissions_kgco2:.1f}\nkgCO₂e', 
                ha='center', va='center', fontsize=16, fontweight='bold')
        
        ax.set_title(f"Stage Contribution: {result.scenario_name}\n{product_name}", pad=20)
        
        plt.tight_layout()
        safe_name = result.scenario_name.replace(" ", "_").lower()
        filepath = self.get_save_path(f"donut_{safe_name}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved donut chart to: {filepath}")

    def plot_radar_comparison(self, results: List[ScenarioResult], product_name: str = ""):
        """Radar chart: Multi-criteria comparison of scenarios."""
        if not results: return
        
        import numpy as np
        
        # Define criteria (normalize 0-1)
        criteria = ['Low Emissions', 'High Yield', 'Low Transport', 'Low Processing', 'Low Waste']
        
        # Calculate normalized scores for each scenario
        max_emissions = max(r.total_emissions_kgco2 for r in results) or 1
        max_yield = max(r.yield_percent for r in results) or 1
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True), dpi=150)
        
        angles = np.linspace(0, 2 * np.pi, len(criteria), endpoint=False).tolist()
        angles += angles[:1]  # Close the loop
        
        cmap = plt.cm.get_cmap('tab10')
        
        for i, r in enumerate(results[:6]):  # Limit to 6 for readability
            # Calculate scores (higher = better)
            transport_e = r.by_stage.get('Transport A', 0) + r.by_stage.get('Transport B', 0) if r.by_stage else 0
            processing_e = r.by_stage.get('Repair', 0) + r.by_stage.get('Disassembly', 0) + r.by_stage.get('Assembly', 0) if r.by_stage else 0
            waste_e = r.by_stage.get('Landfill Transport (Waste)', 0) if r.by_stage else 0
            
            max_transport = max((res.by_stage.get('Transport A', 0) + res.by_stage.get('Transport B', 0)) if res.by_stage else 1 for res in results) or 1
            max_processing = max((res.by_stage.get('Repair', 0) + res.by_stage.get('Disassembly', 0) + res.by_stage.get('Assembly', 0)) if res.by_stage else 1 for res in results) or 1
            max_waste = max((res.by_stage.get('Landfill Transport (Waste)', 0)) if res.by_stage else 1 for res in results) or 1
            
            scores = [
                1 - (r.total_emissions_kgco2 / max_emissions),
                r.yield_percent / 100.0,
                1 - (transport_e / max_transport) if max_transport > 0 else 1,
                1 - (processing_e / max_processing) if max_processing > 0 else 1,
                1 - (waste_e / max_waste) if max_waste > 0 else 1
            ]
            scores += scores[:1]  # Close
            
            ax.plot(angles, scores, 'o-', linewidth=2, label=r.scenario_name, color=cmap(i))
            ax.fill(angles, scores, alpha=0.1, color=cmap(i))
        
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(criteria, fontsize=10)
        ax.set_ylim(0, 1)
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=9)
        ax.set_title(f"Multi-Criteria Comparison\n{product_name}", pad=30)
        
        plt.tight_layout()
        filepath = self.get_save_path("radar_comparison.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved radar chart to: {filepath}")

    def plot_horizontal_intensity(self, df: pd.DataFrame):
        """Horizontal bar: Carbon intensity ranking by scenario."""
        if df.empty: return
        
        subset = df[df['Yield (%)'] > 1.0]
        if subset.empty: return
        
        grouped = subset.groupby('Scenario')['Intensity (kgCO2e/m²)'].mean().sort_values()
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

    def plot_tornado_sensitivity(self, base_result: ScenarioResult, 
                                  sensitivity_params: Dict[str, tuple] = None,
                                  product_name: str = ""):
        """
        Tornado chart: Parameter sensitivity analysis.
        sensitivity_params: dict of {param_name: (low_emission, high_emission)}
        If not provided, uses mock data based on by_stage.
        """
        if not base_result.by_stage: return
        
        # If no sensitivity data provided, estimate from stages
        if sensitivity_params is None:
            # Create mock sensitivity based on ±20% variation
            sensitivity_params = {}
            for stage, val in base_result.by_stage.items():
                if val > 0:
                    low = base_result.total_emissions_kgco2 - val * 0.2
                    high = base_result.total_emissions_kgco2 + val * 0.2
                    sensitivity_params[stage] = (low, high)
        
        if not sensitivity_params: return
        
        fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
        
        # Sort by impact (high - low)
        sorted_params = sorted(sensitivity_params.items(), key=lambda x: x[1][1] - x[1][0], reverse=True)
        
        base_val = base_result.total_emissions_kgco2
        labels = []
        low_deltas = []
        high_deltas = []
        
        for param, (low, high) in sorted_params:
            labels.append(param)
            low_deltas.append(low - base_val)
            high_deltas.append(high - base_val)
        
        y_pos = range(len(labels))
        
        # Plot bars
        ax.barh(y_pos, low_deltas, color=self.colors['yield_dark'], alpha=0.8, label='Low Value')
        ax.barh(y_pos, high_deltas, color=self.colors['emissions_dark'], alpha=0.8, label='High Value')
        
        # Base line
        ax.axvline(x=0, color='black', linewidth=2)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.set_xlabel("Change in Total Emissions (kgCO₂e)", fontweight='bold')
        ax.set_title(f"Sensitivity Analysis: {base_result.scenario_name}\n{product_name}", loc='left', pad=20)
        ax.legend(loc='lower right')
        ax.grid(True, axis='x', linestyle=':', alpha=0.5)
        
        plt.tight_layout()
        safe_name = base_result.scenario_name.replace(" ", "_").lower()
        filepath = self.get_save_path(f"tornado_{safe_name}.png")
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   [Plot] Saved tornado chart to: {filepath}")

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
        self.plot_radar_comparison(results, product_name)
        
        # Per-scenario plots
        for r in results:
            self.plot_waterfall(r, product_name)
            self.plot_donut_stages(r, product_name)
            self.plot_tornado_sensitivity(r, product_name=product_name)
        
        print(f"\n   [Complete] All single-run plots saved to: {self.session_dir}")

    def generate_all_batch_plots(self, df: pd.DataFrame):
        """Generate all applicable plots for batch analysis."""
        if df.empty: return
        
        # Distribution plots
        self.plot_boxplot_batch(df)
        self.plot_violin_batch(df)
        
        # Intensity (with gradient colors)
        self._plot_batch_intensity(df)
        
        print(f"\n   [Complete] All batch plots saved to: {self.session_dir}")

