import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np
from pathlib import Path
import json
import warnings
import contextily as ctx
from pyproj import Transformer

warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore')

# Web Mercator extents
WEB_MERC_MAX_X = 20037508.34
WEB_MERC_MIN_X = -20037508.34
WEB_MERC_YMIN = -9074929
WEB_MERC_YMAX = 16847944
MIN_SIDE = 150_000  # 150 km minimum side for extents
BOTTOM_PANEL_Y = 0.03
BOTTOM_PANEL_H = 0.22


def get_datasets():
    """Get all the CSV files from ../data/3.harvest_ETN without the taxonomy files.

    Returns a list of CSV file paths (excluding _taxonomic_count.csv files).
    """
    data_dir = Path("../data/3.harvest_ETN")
    csv_files = sorted([f for f in data_dir.glob("*.csv")
                       if not str(f).endswith("_taxonomic_count.csv")])
    return csv_files


def get_taxonomic_data(dataset_name):
    """Load taxonomic count data for a dataset.

    Returns a DataFrame with animal_scientific_name and count columns,
    or None if file doesn't exist.
    """
    tax_file = Path("../data/3.harvest_ETN") / f"{dataset_name}_taxonomic_count.csv"
    if tax_file.exists():
        try:
            return pd.read_csv(tax_file)
        except Exception as e:
            print(f"Warning: Could not load taxonomic data for {dataset_name}: {e}")
    return None


def add_inset_world(ax, x_left, x_right, y_bot, y_top, side, world_gdf):
    """Add a small inset world map showing the region rectangle."""
    if world_gdf is None or len(world_gdf) == 0 or world_gdf.geometry is None or world_gdf.geometry.empty:
        return

    inset = ax.inset_axes([0.03, BOTTOM_PANEL_Y, 0.22, BOTTOM_PANEL_H])
    inset.set_aspect("equal")
    # plot world boundary (already in web mercator)
    world_gdf.boundary.plot(ax=inset, linewidth=0.4, edgecolor="gray")

    inset.set_xlim(WEB_MERC_MIN_X, WEB_MERC_MAX_X)
    inset.set_ylim(WEB_MERC_YMIN, WEB_MERC_YMAX)

    pad = side * 0.15
    rect = Rectangle(
        (x_left - pad, y_bot - pad),
        (x_right - x_left) + 2 * pad,
        (y_top - y_bot) + 2 * pad,
        linewidth=2.0,
        edgecolor="red",
        facecolor="none"
    )
    inset.add_patch(rect)

    inset.set_xticks([])
    inset.set_yticks([])


def plot_etn_individuel(dataset, world_gdf=None):
    """Plot a PNG map for an individual dataset.

    Creates a lat/lon plot with color gradient based on count, includes unique
    deployment station names in a text box, and adds a world basemap with inset.
    """
    df = pd.read_csv(dataset)

    # Skip if no data
    if df.empty or df[['deployment_latitude', 'deployment_longitude']].isnull().all().any():
        print(f"Skipping {dataset.stem}: No valid location data")
        return

    # Remove rows with missing coordinates
    df = df.dropna(subset=['deployment_latitude', 'deployment_longitude'])

    if df.empty:
        print(f"Skipping {dataset.stem}: No valid rows after filtering")
        return

    # Create GeoDataFrame in EPSG:4326
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.deployment_longitude, df.deployment_latitude),
        crs="EPSG:4326"
    )

    # Convert to Web Mercator for plotting
    gdf = gdf.to_crs(3857)

    # Create figure and axis (square)
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_axes([0.08, 0.08, 0.84, 0.84])

    # Compute extent in Web Mercator and force square bounds
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    lon_min, lon_max = df['deployment_longitude'].min(), df['deployment_longitude'].max()
    lat_min, lat_max = df['deployment_latitude'].min(), df['deployment_latitude'].max()

    lon_extent = lon_max - lon_min
    lat_extent = lat_max - lat_min

    lon_margin = 1 if lon_extent > 5 else max(0, (5 - lon_extent) / 2)
    lat_margin = 1 if lat_extent > 5 else max(0, (5 - lat_extent) / 2)

    lon_min_map = lon_min - lon_margin
    lon_max_map = lon_max + lon_margin
    lat_min_map = lat_min - lat_margin
    lat_max_map = lat_max + lat_margin

    x_min_map, y_min_map = transformer.transform(lon_min_map, lat_min_map)
    x_max_map, y_max_map = transformer.transform(lon_max_map, lat_max_map)

    width = x_max_map - x_min_map
    height = y_max_map - y_min_map

    # Reserve extra space below the plotted data so bottom insets stay clear.
    bottom_buffer = max(height * 0.18, 250_000)
    top_buffer = max(height * 0.04, 75_000)

    x_min_map -= lon_margin * 0.5
    x_max_map += lon_margin * 0.5
    y_min_map -= bottom_buffer
    y_max_map += top_buffer

    side = max(x_max_map - x_min_map, y_max_map - y_min_map)
    cx = (x_min_map + x_max_map) / 2.0
    x_min_map = cx - side / 2.0
    x_max_map = cx + side / 2.0
    y_max_map = y_min_map + side

    ax.set_xlim(x_min_map, x_max_map)
    ax.set_ylim(y_min_map, y_max_map)
    ax.set_aspect("equal")

    # Add basemap
    try:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik,
                       zoom="auto", interpolation="bilinear")
    except Exception as e:
        print(f"Warning: Could not add basemap for {dataset.stem}: {e}")
        ax.set_facecolor('lightblue')

    # Quantile-based normalization: evenly space unique values across colormap
    unique_counts = sorted(df['count'].unique())
    n_unique = len(unique_counts)

    if n_unique == 1:
        # Single value: map to middle of colormap (0.5)
        count_to_norm = {unique_counts[0]: 0.5}
    else:
        # Multiple values: evenly space across [0, 1]
        # e.g., 5 unique values map to 0.0, 0.25, 0.5, 0.75, 1.0
        count_to_norm = {
            val: i / (n_unique - 1)
            for i, val in enumerate(unique_counts)
        }

    # Create normalized count column for plotting
    df['normalized_count'] = df['count'].map(count_to_norm)
    norm = Normalize(vmin=0, vmax=1)
    cmap = plt.cm.winter

    # Plot points with color gradient
    scatter = ax.scatter(gdf.geometry.x,
                        gdf.geometry.y,
                        c=df['normalized_count'],
                        cmap=cmap,
                        norm=norm,
                        s=100,
                        alpha=0.7,
                        edgecolors='black',
                        linewidth=0.5,
                        zorder=5)

    # Bottom aligned inset panels: world map (left), colorbar (middle), stations (right)
    cax = ax.inset_axes([0.30, BOTTOM_PANEL_Y + 0.075, 0.36, 0.045])
    cbar = plt.colorbar(scatter, cax=cax, orientation='horizontal', aspect=7)
    cbar.set_ticks([])
    cbar.outline.set_linewidth(0.8)
    cbar.set_label('low - high', fontsize=8, labelpad=2)
    cbar.ax.text(0.00, 1.12, 'low', transform=cbar.ax.transAxes,
                 ha='left', va='bottom', fontsize=8)
    cbar.ax.text(1.00, 1.12, 'high', transform=cbar.ax.transAxes,
                 ha='right', va='bottom', fontsize=8)

    # Get unique deployment station names - placed on the right
    unique_stations = df['deployment_station_name'].unique()
    stations_text = "Stations:\n" + "\n".join([str(s) for s in unique_stations[:15]])
    if len(unique_stations) > 15:
        stations_text += f"\n... and {len(unique_stations) - 15} more"

    station_ax = ax.inset_axes([0.68, BOTTOM_PANEL_Y, 0.29, BOTTOM_PANEL_H])
    station_ax.set_axis_off()
    station_ax.text(
        1.0, 1.0, stations_text,
        transform=station_ax.transAxes,
        fontsize=7,
        va='top',
        ha='right',
        family='monospace',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    )

    # Calculate statistics
    n_observations = df['count'].sum()  # Sum of all detections across locations

    # Load and count unique taxa
    tax_df = get_taxonomic_data(dataset.stem)
    n_unique_taxa = len(tax_df) if tax_df is not None else 0

    # Set labels and title with statistics
    title = dataset.stem.replace('_', ' ')
    title_text = f"{title}\nObservations: {n_observations} | Unique Taxa: {n_unique_taxa}"
    ax.set_title(title_text, fontsize=12, fontweight='bold')

    ax.set_xticks([])
    ax.set_yticks([])

    # Add inset world map
    if world_gdf is not None:
        try:
            add_inset_world(ax, x_min_map, x_max_map, y_min_map, y_max_map, x_max_map - x_min_map, world_gdf)
        except Exception as e:
            pass

    # Create output directory if it doesn't exist
    output_dir = Path("../plots/etn_maps")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save figure
    output_path = output_dir / f"{dataset.stem}.png"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"✔ Saved map: {output_path}")


def combined_map(datasets):
    """Combine all CSV data into a GeoJSON file.

    Merges all dataset points and saves as a GeoJSON file.
    """
    all_features = []

    for dataset in datasets:
        df = pd.read_csv(dataset)

        # Skip if no data
        if df.empty:
            continue

        # Remove rows with missing coordinates
        df = df.dropna(subset=['deployment_latitude', 'deployment_longitude'])

        if df.empty:
            continue

        # Create features for each row
        for idx, row in df.iterrows():
            feature = {
                "type": "Feature",
                "properties": {
                    "station_name": str(row.get('deployment_station_name', '')),
                    "count": int(row['count']),
                    "dataset": dataset.stem
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['deployment_longitude']),
                                   float(row['deployment_latitude'])]
                }
            }
            all_features.append(feature)

    # Create GeoJSON FeatureCollection
    geojson_data = {
        "type": "FeatureCollection",
        "features": all_features
    }

    # Create output directory if it doesn't exist
    output_dir = Path("../plots")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save GeoJSON
    output_path = output_dir / "etn_combined_map.geojson"
    with open(output_path, 'w') as f:
        json.dump(geojson_data, f, indent=2)

    print(f"✔ Saved combined GeoJSON: {output_path}")
    print(f"  Total features: {len(all_features)}")


if __name__ == '__main__':
    # Load world map once in Web Mercator for inset
    try:
        PLOT_WORLD_GDF = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres")).to_crs(3857)
    except Exception as e:
        print(f"⚠️ Could not load naturalearth_lowres world dataset: {e}")
        # Try to load from remote URL
        try:
            print("Attempting to load naturalearth data from remote URL...")
            PLOT_WORLD_GDF = gpd.read_file(
                "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
            ).to_crs(3857)
            print("✔ Successfully loaded naturalearth data from remote")
        except Exception as e2:
            print(f"⚠️ Could not load from remote either: {e2}")
            PLOT_WORLD_GDF = None

    datasets = get_datasets()
    print(f"Found {len(datasets)} dataset(s)")

    for dataset in datasets:
        try:
            plot_etn_individuel(dataset, world_gdf=PLOT_WORLD_GDF)
        except Exception as e:
            print(f"⚠ Error plotting {dataset.stem}: {e}")

    try:
        combined_map(datasets)
    except Exception as e:
        print(f"⚠ Error creating combined map: {e}")
