import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os


# Current directory (optional check)
current_dir = os.getcwd()
print("Current directory:", current_dir)

# Build the path to your CSV file
current_directory = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)

EE_OC_low_db = os.path.join(current_directory, 'PycharmProjects', 'VITRIFY', 'data', 'results', 'EE_OC_Results_low.csv')
EE_OC_high_db = os.path.join(current_directory, 'PycharmProjects', 'VITRIFY', 'data', 'results', 'EE_OC_Results_high.csv')

# Load CSV
EE_OC_df = pd.read_csv(EE_OC_low_db)


# ---------------------------------------------------------
# Split intervention into Group (prefix) and Label
# ---------------------------------------------------------

EE_OC_df[['Group','Label']] = EE_OC_df['Intervention'].str.split(':', n=1, expand=True)
EE_OC_df['Group'] = EE_OC_df['Group'].str.strip()
EE_OC_df['Label'] = EE_OC_df['Label'].str.strip()

# ---------------------------------------------------------
# Create y positions with spacing between groups
# ---------------------------------------------------------

group_gap = 2

y_positions = []
labels = []
group_centers = []
group_separators = []

current_y = 0

for group, gdf in EE_OC_df.groupby('Group', sort=False):

    start = current_y

    for label in gdf['Label']:
        y_positions.append(current_y)
        labels.append(label)
        current_y += 5

    end = current_y - 5
    group_centers.append((group, (start + end) / 2))

    # separator centered in gap
    group_separators.append(current_y - group_gap)

    current_y += group_gap

y = np.array(y_positions)

# ---------------------------------------------------------
# Extract values
# ---------------------------------------------------------

EC = EE_OC_df['EC'].to_numpy()
delta_OC = EE_OC_df['OC'].to_numpy()

# Create payback array with 'No payback' as string
payback = [
    f'Payback ≈ {-(ec/delta):.1f} yr' if delta < 0 else 'No payback'
    for ec, delta in zip(EC, delta_OC)
]

#Bar Height
height = 2

# ---------------------------------------------------------
# Plot
# ---------------------------------------------------------

fig, ax = plt.subplots(figsize=(14,8))

margin = 120
max_value = max(np.nanmax(EC), np.nanmax(delta_OC)) + margin
min_value = min(0, np.nanmin(delta_OC) - margin)
ax.set_xlim(min_value, max_value)


# Embodied carbon bars
ax.barh(
    y + height/2,
    EC,
    height,
    label='Upfront embodied carbon',
    color='#404040'
)

# Operational carbon bars
ax.barh(
    y - height/2,
    delta_OC,
    height,
    label='Annual avoided operational carbon',
    color=['#808080' if val > 0 else '#808080' for val in delta_OC]
)

# Payback annotations

for i, text in enumerate(payback):
    ax.text(
        EC[i] + 5,           # slight right offset
        y[i] + height/2,     # align with bar/grid
        text,
        va='center',
        ha='left',
        fontsize=8,
        zorder=4
    )

for sep in group_separators[:-1]:  # skip last group
    ax.axhline(
        y=sep,
        color='0.7',
        linewidth=0.5,
        zorder=0
    )

# ---------------------------------------------------------
# Axis formatting
# ---------------------------------------------------------

ax.set_yticks(y)
ax.set_yticklabels(labels)
ax.margins(y=0.02)

ax.set_xlabel('GHG Emissions (kgCO₂-e)')

ax.axvline(0, color='black', linewidth=1)

ax.legend(
    frameon=False,
    loc='lower center',
    bbox_to_anchor=(0.5, 1.0),
    ncol=2
)

# Flip order so first item appears on top
ax.invert_yaxis()

# ---------------------------------------------------------
# Add group labels
# ---------------------------------------------------------

for group, center in group_centers:
    group_display = group.replace('#', r'$^{\#}$')

    ax.text(
        -0.18,                 # position slightly outside the axis
        center,
        group_display,
        transform=ax.get_yaxis_transform(),
        va='center',
        ha='right',
        fontsize=10,
        fontweight='bold'
    )

plt.tight_layout()
plt.subplots_adjust(left=0.22)
plt.subplots_adjust(hspace=10.0, wspace=0.5)
save_dir = os.path.join(current_directory, 'PycharmProjects', 'VITRIFY', 'data', 'results')
output_file = os.path.join(save_dir, "EE_OC_payback_high.png") # can also use .pdf, .svg, etc.
plt.savefig(
    output_file,
    dpi=600,         # high-resolution
    bbox_inches='tight'  # ensures all labels fit
)

plt.show()
