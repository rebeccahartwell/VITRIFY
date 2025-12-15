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

class Visualizer:
    def __init__(self, mode: str = "single_run"):
        """
        Initialize Visualizer.
        mode: 'single_run' (for interactive) or 'batch_run' (for automated analysis)
        """
        self.mode = mode
        self.output_root = r"d:\VITRIFY\reports\plots"
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
        
        # self._plot_batch_distribution(df)
        # self._plot_batch_scatter(df)
        self._plot_batch_intensity(df)

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
        
        # Horizontal Bars
        bars = ax.barh(grouped.index, grouped.values, color=self.colors['yield_dark'], alpha=0.8, edgecolor='none')
        
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
