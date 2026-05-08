#!/usr/bin/env python3
"""
Plot unique observation/sensor locations:

- plot every CSV individually (loop over csv_all)
- plot combined map for WP3 (csv_wp3)
- plot combined map for Call1 (csv_call1)
- plot combined map for Call1+WP3 (csv_all)

Each combined map includes a text box listing DASIDs.
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
        output_path: Path,
        title: str = "",
        dasids_text: str = "",
        show_inset: bool = True,
        marker_size: float = 10,
        alpha: float = 0.7
):
    """
    Plot a single GeoDataFrame (EPSG:3857) to output_path PNG.
    Adds an inset and a text box for DASIDs unless disabled.
    marker_size and alpha control the point style.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"✔ Saved map: {output_path}")


def plot_large_gdf(gdf, output_path, title=None, dasids=None):

    # Web Mercator global extent
    # WEB_MERC_MAX_X = 20037508.34
    # WEB_MERC_MIN_X = -20037508.34
    # WEB_MERC_YMIN = -9074929
    # WEB_MERC_YMAX = 16847944

    # Web Mercator local extent
    WEB_MERC_MAX_X = 5000000
    WEB_MERC_MIN_X = -7500000
    WEB_MERC_YMIN = -7500000
    WEB_MERC_YMAX = 11500000

    # Web Mercator EU extent
    WEB_MERC_MAX_X = 5000000
    WEB_MERC_MIN_X = -1500000
    WEB_MERC_YMIN = 3500000
    WEB_MERC_YMAX = 9000000

    print("=== Starting plot_large_gdf ===")

    # --- 1. Project to Web Mercator ---
    gdf = gdf.to_crs(3857)
    print("Projected bounds:", gdf.total_bounds)

    width = (WEB_MERC_MAX_X - WEB_MERC_MIN_X)
    height = (WEB_MERC_YMAX - WEB_MERC_YMIN)

    # --- 2. Datashader canvas ---
    cvs = ds.Canvas(
        plot_width=int(800*width/height),
        plot_height=int(800*height/width),
        x_range=(WEB_MERC_MIN_X, WEB_MERC_MAX_X),
        y_range=(WEB_MERC_YMIN, WEB_MERC_YMAX)
    )

    # --- 3. Aggregate ---
    gdf["x"] = gdf.geometry.x
    gdf["y"] = gdf.geometry.y
    agg = cvs.points(gdf, x="x", y="y")
    print("Aggregation min/max:", agg.values.min(), agg.values.max())

    # --- 4. Scale nonzero values only ---
    agg_scaled = agg.copy()
    nonzero_mask = agg_scaled.values > 0
    agg_scaled.values[nonzero_mask] = agg_scaled.values[nonzero_mask] ** 0.3  # enhanced power scaling for better mid-tone visibility

    # Clip to lower and upper percentiles for better dynamic range
    nonzero = agg_scaled.values[nonzero_mask]
    vmin = np.percentile(nonzero, 0)  # lower percentile for better low-value visibility
    vmax = np.percentile(nonzero, 90)  # upper percentile to reduce extreme outliers
    agg_scaled.values[nonzero_mask] = np.clip(nonzero, vmin, vmax)

    # Enhanced colormap: use twilight or create a custom vibrant map with better contrast
    # Using 'cet_isoluminant_cm' or a blend for better visibility of density variations
    cwr_cmap = LinearSegmentedColormap.from_list("enhanced_density", cc.cwr[50:128])

    # Shade
    img = tf.shade(agg_scaled, cmap=cwr_cmap, how="linear", min_alpha=0).to_pil()
    print("Shading done. Nonzero cells visible, zero cells stay black.")

    # --- 5. Stats ---
    n_obs = len(gdf)
    if "aphiaid" in gdf.columns:
        all_ids = [i for row in gdf["aphiaid"] for i in row]
        n_unique_taxa = len(set(all_ids))
    else:
        n_unique_taxa = 0

    # --- 6. Plot with Cartopy ---
    fig = plt.figure(figsize=(14, 10))
    ax = plt.axes(projection=ccrs.Mercator())
    ax.set_extent([WEB_MERC_MIN_X, WEB_MERC_MAX_X, WEB_MERC_YMIN, WEB_MERC_YMAX], crs=ccrs.Mercator())
    ax.set_facecolor("black")
    ax.add_feature(cfeature.LAND, facecolor="black", edgecolor="white", linewidth=0.3)
    ax.add_feature(cfeature.COASTLINE, edgecolor="white", linewidth=0.3)

    # --- 7. Overlay image ---
    img_array = np.array(img)
    img_array = np.flipud(img_array)
    ax.imshow(
        img_array,
        extent=(WEB_MERC_MIN_X, WEB_MERC_MAX_X, WEB_MERC_YMIN, WEB_MERC_YMAX),
        transform=ccrs.Mercator(),
        origin="lower"
    )

    # --- 8. Title ---
    auto_stats = f"Observations: {n_obs} | Taxa: {n_unique_taxa}"
    final_title = f"{title}\n{auto_stats}" if title else f"Observation Data\n{auto_stats}"
    plt.title(final_title, fontsize=16, pad=20, color="white")

    # --- 8b. DASID textbox (bottom right) ---
    if dasids:
        wrapped_dasids = textwrap.fill(dasids, width=100)
        ax.text(
            0.98, 0.02,
            f"DASIDs:\n{wrapped_dasids}",
            transform=ax.transAxes,
            va="bottom",
            ha="right",
            fontsize=8,
            linespacing=1.2,
            bbox=dict(facecolor="black", alpha=0.7, edgecolor="white", linewidth=0.5),
            color="white"
        )

    # --- 9. Save ---
    fig.savefig(output_path, dpi=1000, bbox_inches="tight", facecolor="black")
    plt.close(fig)
    print("=== Finished plot_large_gdf ===")


def plot_each_csv_individual(csv_files, outdir_base: Path):
    """Plot every CSV in csv_files individually. Save outputs in outdir_base/map_per_dasid/."""
    outdir = outdir_base
    outdir.mkdir(parents=True, exist_ok=True)

    for csv_path in csv_files:
        gdf = read_csv_as_unique_gdf(csv_path)
        if gdf is None:
            continue
        dasid = gdf["dasid"].iloc[0]
        out_file = outdir / f"dasid_{dasid}.png"
        plot_gdf_map(gdf, out_file, title=f"DASID {dasid}", dasids_text=dasid)


def plot_combined(csv_files, out_file_base: Path, title: str, show_inset=True):
    """
    Combine all CSVs in csv_files and plot a single map.
    Generates two versions:
      1) alpha=1, markersize=1
      2) alpha=0.01, markersize=1
    The DASID textbox contains the comma-separated list of DASIDs used.
    """
    gdfs = []
    dasids = []
    for csv_path in csv_files:
        gdf = read_csv_as_unique_gdf(csv_path)
        if gdf is None:
            continue
        gdfs.append(gdf)
        dasids.append(str(gdf["dasid"].iloc[0]))

    if not gdfs:
        print(f"⚠️ No valid input files for combined plot '{title}' - skipping")
        return

    combined = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
    combined = combined.drop_duplicates(subset=["geometry"])

    dasids_text = ", ".join(dasids)

    # Version 1: alpha=1
    out_file_alpha1 = out_file_base.with_name(f"{out_file_base.stem}_alpha1.png")
    plot_gdf_map(
        combined,
        out_file_alpha1,
        title=title,
        dasids_text=dasids_text,
        show_inset=show_inset,
        marker_size=1,
        alpha=1
    )

    # Version 2: alpha=0.01
    out_file_alpha001 = out_file_base.with_name(f"{out_file_base.stem}_alpha0_01.png")
    plot_gdf_map(
        combined,
        out_file_alpha001,
        title=f"{title} (transparent)",
        dasids_text=dasids_text,
        show_inset=show_inset,
        marker_size=1,
        alpha=0.01
    )


def plot_shader(csv_files, output_path, title):
    gdfs = []
    dasids = []

    # --- Load CSV files ---
    for csv_path in csv_files:
        gdf = read_csv_as_unique_gdf(csv_path)
        if gdf is None or len(gdf) == 0:
            continue

        gdfs.append(gdf)

        # collect DASID if available
        if "dasid" in gdf.columns:
            dasids.append(str(gdf["dasid"].iloc[0]))

    if not gdfs:
        print(f"⚠️ No valid input files for combined plot '{title}' — skipping")
        return

    # --- Merge into one GeoDataFrame ---
    combined = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True),
        crs=gdfs[0].crs
    )

    # Drop duplicates based on geometry
    combined = combined.drop_duplicates(subset="geometry")

    # # DASIDs text (comma-separated)
    dasids_text = ", ".join(dasids)

    # Add DASID text to the title (optional)
    # full_title = f"{title}\nDASIDs: {dasids_text}"

    # --- Call your existing fast Datashader plotter ---
    plot_large_gdf(
        gdf=combined,
        output_path=output_path,
        title=title,
        dasids=dasids_text
    )

    print(f"✔ Combined shader plot saved: {output_path}")


if __name__ == "__main__":
    # input directories (adjust as needed)
    dir_call1 = Path("../data/1.harvest_wp2_observation_data")
    dir_wp3 = Path("../data/2.harvest_wp3_sensor_observation_data")

    csv_call1 = sorted(dir_call1.glob("*.csv"))
    csv_wp3 = sorted(dir_wp3.glob("*.csv"))
    csv_all = csv_call1 + csv_wp3

    # where to write plots
    out_base = Path("../plots")
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

    # plot_each_csv_individual(csv_call1, Path("../plots/wp2_call1_observation_maps"))
    # plot_each_csv_individual(csv_wp3, Path("../plots/wp3_sensor_observation_maps"))

    # 2) Call1 combined
    print(">> Plotting combined Call1 (observation) map...")

    # plot_combined(csv_call1, out_base / "wp2_observation_scatter.png",
    #               show_inset=False,
    #               title="WP2 Observation Data")

    plot_shader(csv_call1,
                out_base / "wp2_observation_shader.png",
                title="WP2 Observation Data")

    # 3) WP3 combined
    # print(">> Plotting combined WP3 (sensor) map...")

    # plot_combined(csv_wp3, out_base / "wp3_sensor_observation_scatter.png",
    #               show_inset=False,
    #               title="WP3 Sensor Observation Data")
    # plot_shader(csv_wp3,
    #             out_base / "wp3_sensor_observation_shader.png",
    #             title="WP3 Sensor Observation Data")

    # 4) All combined
    # print(">> Plotting combined Call1 + WP3 map...")
    #
    # plot_combined(csv_all, out_base / "wp2_wp3_observation_scatter.png",
    #               show_inset=False,
    #               title="Combined WP2 Observation & WP3 Sensor Observation Data")
    #
    # plot_shader(csv_all,
    #             out_base / "WP2_WP3_observations_combined_shader.png",
    #             title="Combined WP2 Observation & WP3 Sensor Observation Data")
    # print("All done.")


