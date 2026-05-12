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
from PIL import Image

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


def build_global_count_scale(datasets):
    """Build one shared count-to-normalized-value mapping across all datasets."""
    all_counts = set()

    for dataset in datasets:
        try:
            df = pd.read_csv(dataset, usecols=["count"])
            all_counts.update(df["count"].dropna().unique().tolist())
        except Exception as e:
            print(f"Warning: Could not read counts from {dataset.stem}: {e}")

    unique_counts = sorted(all_counts)
    if not unique_counts:
        return None

    if len(unique_counts) == 1:
        return {unique_counts[0]: 0.5}

    return {val: i / (len(unique_counts) - 1) for i, val in enumerate(unique_counts)}


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


def plot_etn_individuel(dataset, store: str, format: str, world_gdf=None, count_to_norm=None):
    """Plot a map for an individual dataset.

    Creates a lat/lon plot with color gradient based on count, includes unique
    deployment station names in a text box, and adds a world basemap with inset.
    
    Args:
        dataset: Path to the dataset CSV file
        world_gdf: GeoDataFrame of world map (optional)
        store: Path where to store the plots (default: "../plots/etn_maps")
        format: Output format, either "png" or "webp" (default: "png")
        count_to_norm: Optional shared mapping from count values to [0, 1]
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

    # Use a shared scale when provided so every GIF frame uses the same colors.
    if count_to_norm is None:
        unique_counts = sorted(df['count'].unique())
        if len(unique_counts) == 1:
            count_to_norm = {unique_counts[0]: 0.5}
        else:
            count_to_norm = {val: i / (len(unique_counts) - 1) for i, val in enumerate(unique_counts)}

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
    output_dir = Path(store)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate format parameter
    if format.lower() not in ["png", "webp"]:
        raise ValueError(f"Invalid format '{format}'. Must be 'png' or 'webp'")

    # Save figure in the specified format
    output_path = output_dir / f"{dataset.stem}.{format.lower()}"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"✔ Saved map: {output_path}")


def make_gif(dir, output, name, frame_format="webp", output_format="gif"):
    """
    Create an animation from PNG or WebP files in a directory.

    Args:
        dir: Path to directory containing frame images
        output: Output directory path for the animation
        name: Output filename (without extension; extension added based on output_format)
        frame_format: Input image format, either "webp" or "png"
        output_format: Output animation format: "gif" (default) or "apng".
            - "gif": produce an animated GIF (colors will be palettized)
            - "apng": produce an animated PNG (preserves truecolor/alpha)
    """
    # Convert to Path objects if strings are passed
    if isinstance(dir, str):
        dir = Path(dir)
    if isinstance(output, str):
        output = Path(output)

    # Create output directory if it doesn't exist
    output.mkdir(parents=True, exist_ok=True)

    frame_format = frame_format.lower().lstrip(".")
    output_format = output_format.lower().lstrip(".")

    if frame_format not in {"webp", "png"}:
        raise ValueError(f"Invalid frame_format '{frame_format}'. Must be 'webp' or 'png'")
    if output_format not in {"gif", "apng"}:
        raise ValueError(f"Invalid output_format '{output_format}'. Must be 'gif' or 'apng'")

    # Get all frame files sorted by name for the selected input format
    frame_files = sorted(dir.glob(f"*.{frame_format}"))

    if not frame_files:
        print(f"⚠️ No .{frame_format} files found in {dir}")
        return

    # Open all frames
    images = []
    for frame_path in frame_files:
        try:
            img = Image.open(frame_path)
            images.append(img)
        except Exception as e:
            print(f"⚠️ Could not load {frame_path}: {e}")
            continue

    if not images:
        print(f"⚠️ No valid images could be loaded from {dir}")
        return

    # Create output path and write animation.
    try:
        if output_format == "apng":
            if frame_format != "png":
                raise ValueError("APNG output requires PNG input frames")
            # Write an animated PNG (APNG) to preserve original PNG colors and alpha.
            output_path = output / f"{name}.png"
            images[0].save(
                output_path,
                save_all=True,
                append_images=images[1:],
                duration=2000,
                loop=0,
                format='PNG'
            )
            print(f"✔ Created APNG: {output_path} ({len(images)} frames)")
        else:
            # Produce a GIF using a single shared adaptive palette to avoid
            # per-frame palette differences which cause color shifts/banding.
            output_path = output / f"{name}.gif"

            # Convert all frames to RGB
            frames_rgb = [img.convert("RGB") if img.mode != "RGB" else img.copy() for img in images]

            # Build small thumbnails to derive a representative global palette
            thumbs = []
            thumb_w, thumb_h = 160, 120
            for fr in frames_rgb:
                t = fr.copy()
                t.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
                thumbs.append(t)

            # Composite thumbnails side-by-side to collect colors from all frames
            total_w = sum(t.width for t in thumbs)
            max_h = max(t.height for t in thumbs)
            palette_canvas = Image.new("RGB", (max(1, total_w), max_h), (0, 0, 0))
            x = 0
            for t in thumbs:
                palette_canvas.paste(t, (x, 0))
                x += t.width

            # Create a single adaptive palette image (P-mode) from the composite
            try:
                palette_image = palette_canvas.convert("P", palette=Image.ADAPTIVE, colors=256)
            except Exception:
                # Fallback if ADAPTIVE not available
                palette_image = palette_canvas.convert("P", colors=256)

            # Quantize each full-size frame using the same palette (use dithering to reduce banding)
            paletted_frames = []
            for fr in frames_rgb:
                try:
                    q = fr.quantize(palette=palette_image, dither=Image.FLOYDSTEINBERG)
                except Exception:
                    q = fr.quantize(palette=palette_image)
                paletted_frames.append(q)

            # Save paletted frames as an animated GIF
            try:
                paletted_frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=paletted_frames[1:],
                    duration=2000,
                    loop=0,
                    disposal=2,
                    optimize=False
                )
                print(f"✔ Created GIF with shared palette: {output_path} ({len(paletted_frames)} frames)")
            except Exception as e:
                print(f"⚠️ Could not create paletted GIF: {e}")
    except Exception as e:
        print(f"⚠️ Could not create animation: {e}")

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

    shared_count_to_norm = build_global_count_scale(datasets)
    if shared_count_to_norm is None:
        print("⚠️ Could not build a shared count scale; falling back to per-file color normalization.")



    # make gif (produce a GIF from PNG frames)
    make_gif(dir="../plots/etn_maps_png", output="../plots", name="etn_maps_animation", frame_format="png", output_format="gif")

