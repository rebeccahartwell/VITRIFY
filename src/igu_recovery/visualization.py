import matplotlib.pyplot as plt
from typing import List
from .models import ScenarioResult

def plot_single_scenario(result: ScenarioResult):
    """
    Plots a bar chart detailing the emissions by stage for a single scenario result.
    """
    if not result.by_stage:
        print("No stage data to visualize.")
        return

    stages = list(result.by_stage.keys())
    values = list(result.by_stage.values())
    
    # Sort for better reading? keep arbitrary order usually ok if logical
    
    plt.figure(figsize=(10, 6))
    bars = plt.bar(stages, values, color='skyblue', edgecolor='black')
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                 f'{height:.1f}',
                 ha='center', va='bottom')

    plt.title(f"Emissions Breakdown: {result.scenario_name}")
    plt.ylabel("Emissions (kgCO2e)")
    plt.xlabel("Stage")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.show()

def plot_comparison(results: List[ScenarioResult]):
    """
    Plots a comparison of Total Emissions and Yield % across multiple scenarios.
    """
    if not results:
        print("No results to compare.")
        return
        
    names = [r.scenario_name for r in results]
    emissions = [r.total_emissions_kgco2 for r in results]
    yields = [r.yield_percent for r in results]
    
    fig, ax1 = plt.subplots(figsize=(12, 7))
    
    # Bar Chart for Emissions
    color = 'tab:blue'
    ax1.set_xlabel('Scenario')
    ax1.set_ylabel('Total Emissions (kgCO2e)', color=color)
    bars = ax1.bar(names, emissions, color=color, alpha=0.7, label='Emissions')
    ax1.tick_params(axis='y', labelcolor=color)
    
    # Value labels for emissions
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                 f'{height:.1f}',
                 ha='center', va='bottom', color='black')
    
    # Line/Mark Chart for Yield
    ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
    color = 'tab:green'
    ax2.set_ylabel('Final Yield (%)', color=color)  # we already handled the x-label with ax1
    ax2.plot(names, yields, color=color, marker='o', linewidth=2, linestyle='--', label='Yield %')
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(0, 110)
    
    # Value labels for yield
    for i, txt in enumerate(yields):
        ax2.text(i, txt + 2, f'{txt:.1f}%', color=color, ha='center', fontweight='bold')

    plt.title(f"Scenario Comparison: Emissions vs Yield")
    fig.autofmt_xdate(rotation=45) # Rotate x labels
    plt.tight_layout()
    plt.show()
