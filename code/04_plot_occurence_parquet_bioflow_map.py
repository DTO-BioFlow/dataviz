#!/usr/bin/env python3
"""
Plot unique observation/sensor locations for WP2 call 1 data and WP3 sensor
data. Data are sourced from /data/1.harvest_wp2_observation_data and from
data/2.harvest_wp3_sensor_observation_data. Plots are stored in
/plots/wp2_call1_observation_maps and /plots/wp3_sensor_observation_maps.
Makes also gif for each cluster which is stored in /plots.
"""
from pathlib import Path
import ast
import pandas as pd
import geopandas as gpd
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import contextily as ctx
import textwrap
import numpy as np
import datashader as ds
import datashader.transfer_functions as tf
import colorcet as cc
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from scipy.cluster import hierarchy
from PIL import Image

# -------------------------
# Configuration
# -------------------------
WEB_MERC_MAX_X = 20037508.34
WEB_MERC_MIN_X = -20037508.34
WEB_MERC_YMIN = -9074929
WEB_MERC_YMAX = 16847944
MIN_SIDE = 150_000  # 150 km minimum side for extents


def parse_aphia(val):
    """Safely parse aphiaid column values into a list."""
    if isinstance(val, list):
        return val
    if pd.isna(val):
        return []
    try:
        return ast.literal_eval(str(val))
    except Exception:
        # if parsing fails, return empty list
        return []


def read_csv_as_unique_gdf(csv_file):
    """
    Read CSV and return GeoDataFrame in Web Mercator (EPSG:3857).
    Does NOT collapse duplicates; all rows are preserved.
    Columns: latitude, longitude, aphiaid (list), obs_count, dasid, geometry.
    Returns None if CSV cannot be read or has no valid coordinates.
    """
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"⚠️ Could not read {csv_file}: {e}")
        return None

    if "latitude" not in df.columns or "longitude" not in df.columns:
        print(f"⚠️ Missing lat/lon in {csv_file} - skipping")
        return None

    # ensure numeric lat/lon and drop rows without coords
    df = df.dropna(subset=["latitude", "longitude"])
    if df.empty:
        print(f"⚠️ No coordinate rows in {csv_file} - skipping")
        return None

    # parse aphiaid column
    if "aphiaid" in df.columns:
        df["aphiaid"] = df["aphiaid"].apply(parse_aphia)
    else:
        df["aphiaid"] = [[] for _ in range(len(df))]

    # add obs_count column (length of aphiaid list)
    df["obs_count"] = df["aphiaid"].apply(len)

    # add dasid
    dasid = Path(csv_file).stem.split("_")[-1]
    df["dasid"] = dasid

    # create geodataframe and convert to web mercator
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.longitude, df.latitude),
        crs="EPSG:4326"
    )

    # Convert to Web Mercator (EPSG:3857)
    try:
        gdf = gdf.to_crs(3857)
    except Exception as e:
        print(f"⚠️ CRS transform failed for {csv_file}: {e}")
        return None

    # drop rows with invalid geometry
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    if gdf.empty:
        print(f"⚠️ No valid geometries in {csv_file} after processing - skipping")
        return None

    return gdf


def add_inset_world(ax, x_left, x_right, y_bot, y_top, side, world_gdf):
    """Add a small inset world map showing the region rectangle."""
    # Skip inset if world_gdf has no geometry
    if world_gdf is None or len(world_gdf) == 0 or world_gdf.geometry is None or world_gdf.geometry.empty:
        return

    inset = inset_axes(ax, width="28%", height="28%", loc="lower left", borderpad=1.2)
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


def plot_gdf_map(
        gdf,
        out_base: Path,
        filename: str,
        title: str = "",
        dasids_text: str = "",
        show_inset: bool = True,
        marker_size: float = 10,
        alpha: float = 0.7,
        format: str = "png",
        dpi: int = 300,
        quality: int = 85
):
    """
    Plot a single GeoDataFrame (EPSG:3857) to output file.
    Adds an inset and a text box for DASIDs unless disabled.
    marker_size and alpha control the point style.

    Args:
        out_base: Output directory
        filename: Filename without extension (extension added based on format)
        format: "png" or "webp"
        dpi: DPI for PNG output (default 300)
        quality: Quality for WebP output 1-100 (default 85)
    """
    out_base.mkdir(parents=True, exist_ok=True)
    output_path = out_base / f"{filename}.{format.lower()}"

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])

    # scatter points
    gdf.plot(ax=ax, markersize=marker_size, color=(1, 0, 0, alpha))

    # compute extents
    if show_inset:
        x_min, y_min, x_max, y_max = gdf.total_bounds
        dx, dy = x_max - x_min, y_max - y_min
        side = max(dx, dy, MIN_SIDE)

        cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
        x_left = cx - side / 2.0
        x_right = cx + side / 2.0
        y_bot = max(cy - side / 2.0, WEB_MERC_YMIN)
        y_top = min(cy + side / 2.0, WEB_MERC_YMAX)
    else:
        x_left, x_right = WEB_MERC_MIN_X, WEB_MERC_MAX_X
        y_bot, y_top = WEB_MERC_YMIN, WEB_MERC_YMAX

    ax.set_xlim(x_left, x_right)
    ax.set_ylim(y_bot, y_top)
    ax.set_aspect("equal")

    # basemap
    try:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception:
        pass

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_axis_off()

    # add number of features in the title + unique aphiaIDs
    n_observations = len(gdf)
    n_taxa = gdf["aphiaid"].apply(len).sum() if "aphiaid" in gdf.columns else 0
    n_unique_aphia = len(
        set([aid for sublist in gdf.get("aphiaid", []) for aid in sublist]))

    if title:
        ax.set_title(
            f"{title}\nObservations: {n_observations} | Taxa: {n_unique_aphia}",
            fontsize=13)

    # INSET WORLD MAP — only if show_inset=True
    if show_inset:
        try:
            add_inset_world(ax, x_left, x_right, y_bot, y_top,
                            x_right - x_left, PLOT_WORLD_GDF)
        except Exception as e:
            print("aj exception")
            print(e)
            pass

    # DASID textbox
    if dasids_text:
        wrapped = textwrap.fill(dasids_text, width=100)
        ax.text(
            0.98, 0.02,
            f"DASIDs:\n{wrapped}",
            transform=ax.transAxes,
            va="bottom",
            ha="right",
            fontsize=8,
            linespacing=1.2,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="black",
                      linewidth=0.5)
        )

    # Save with appropriate format
    save_kwargs = {"bbox_inches": "tight"}
    if format.lower() == "webp":
        save_kwargs["format"] = "webp"
        save_kwargs["pil_kwargs"] = {"quality": quality}
    else:  # png
        save_kwargs["format"] = "png"
        save_kwargs["dpi"] = dpi

    fig.savefig(output_path, **save_kwargs)
    plt.close(fig)
    print(f"✔ Saved map: {output_path}")


def plot_each_csv_individual(csv_files, out_base: Path, filename_prefix: str = "dasid", format: str = "png", dpi: int = 300, quality: int = 85):
    """
    Plot every CSV in csv_files individually. Save outputs in out_base with filename_prefix.

    Args:
        out_base: Output directory
        filename_prefix: Prefix for filenames (default "dasid")
        format: "png" or "webp"
        dpi: DPI for PNG output (default 300)
        quality: Quality for WebP output 1-100 (default 85)
    """
    out_base.mkdir(parents=True, exist_ok=True)

    for csv_path in csv_files:
        gdf = read_csv_as_unique_gdf(csv_path)
        if gdf is None:
            continue
        dasid = gdf["dasid"].iloc[0]
        filename = f"{filename_prefix}_{dasid}"
        plot_gdf_map(gdf, out_base, filename, title=f"DASID {dasid}", dasids_text=dasid,
                    format=format, dpi=dpi, quality=quality)


def make_gif(dir, output, name):
    """
    Create a GIF from all WebP files in a directory.

    Args:
        dir: Path to directory containing WebP files
        output: Output directory path for the GIF
        name: Output filename (without extension; .gif will be added)
    """
    # Convert to Path objects if strings are passed
    if isinstance(dir, str):
        dir = Path(dir)
    if isinstance(output, str):
        output = Path(output)

    # Create output directory if it doesn't exist
    output.mkdir(parents=True, exist_ok=True)

    # Get all WebP files sorted by name
    webp_files = sorted(dir.glob("*.webp"))

    if not webp_files:
        print(f"⚠️ No WebP files found in {dir}")
        return

    # Open all WebP images
    images = []
    for webp_path in webp_files:
        try:
            img = Image.open(webp_path)
            images.append(img)
        except Exception as e:
            print(f"⚠️ Could not load {webp_path}: {e}")
            continue

    if not images:
        print(f"⚠️ No valid images could be loaded from {dir}")
        return

    # Create output path
    output_path = output / f"{name}.gif"

    # Save as GIF (convert to RGB mode if needed)
    try:
        # Convert all images to RGB mode for compatibility
        images_rgb = [img.convert("RGB") if img.mode != "RGB" else img for img in images]

        # Save as animated GIF with 500ms duration per frame
        images_rgb[0].save(
            output_path,
            save_all=True,
            append_images=images_rgb[1:],
            duration=2000,
            loop=0  # Loop indefinitely
        )
        print(f"✔ Created GIF: {output_path} ({len(images_rgb)} frames)")
    except Exception as e:
        print(f"⚠️ Could not create GIF: {e}")


if __name__ == "__main__":
    # input directories (adjust as needed)
    dir_call1 = Path("../data/1.harvest_wp2_observation_data")
    dir_wp3 = Path("../data/2.harvest_wp3_sensor_observation_data")

    csv_call1 = sorted(dir_call1.glob("*.csv"))
    csv_wp3 = sorted(dir_wp3.glob("*.csv"))
    csv_all = csv_call1 + csv_wp3

    # where to write plots
    out_base = Path("../../plots")
    out_base.mkdir(parents=True, exist_ok=True)

    # Load world once in Web Mercator for inset; set as global for helper use
    try:
        PLOT_WORLD_GDF = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres")).to_crs(3857)
    except Exception as e:
        print(f"⚠️ Could not load naturalearth_lowres world dataset: {e}")
        # Try to load from remote URL (naturalearth public repository)
        try:
            print("Attempting to load naturalearth data from remote URL...")
            PLOT_WORLD_GDF = gpd.read_file(
                "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
            ).to_crs(3857)
            print("✔ Successfully loaded naturalearth data from remote")
        except Exception as e2:
            print(f"⚠️ Could not load from remote either: {e2}")
            # make a minimal empty GeoDataFrame as fallback (inset will be skipped)
            PLOT_WORLD_GDF = gpd.GeoDataFrame()

    # 1) Plot each CSV individually (loop over all CSVs)
    print(">> Plotting each CSV individually...")
    # plot_each_csv_individual(csv_call1, Path("../plots/wp2_call1_observation_maps"), format='webp')
    make_gif(Path("../plots/wp2_call1_observation_maps"), Path("../plots"), "wp2_call1_observation_maps_gif")

    # plot_each_csv_individual(csv_wp3, Path("../plots/wp3_sensor_observation_maps"), format='webp')
    make_gif(Path("../plots/wp3_sensor_observation_maps"), Path("../plots"), "wp3_sensor_observation_maps_gif")

