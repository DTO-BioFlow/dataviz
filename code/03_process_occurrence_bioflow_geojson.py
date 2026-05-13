"""
Reads the harvested data from /data/1.harvest_wp2_observation_data and
/data/2.harvest_wp3_sensor_observation_data.

The script groups unique latitude/longitude/observationdate/timeofday records
into H3 hexagons and counts each Aphia ID in the `aphiaid` list individually.
3 files are generated (stored in /plots):
- wp2_observations_hexagons.geojson
- wp3_sensor_observations_hexagons.geojson
- all_observations_hexagons.geojson
"""

import ast
import geopandas as gpd
import pandas as pd
import h3
from shapely.geometry import Polygon
from pathlib import Path


REQUIRED_COLUMNS = {"latitude", "longitude", "observationdate", "timeofday", "aphiaid"}


def parse_aphiaid_value(value):
    """Return a list of AphiaIDs from scalars, list-like strings, or lists."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return []

        try:
            parsed = ast.literal_eval(text)
        except Exception:
            parsed = text

        if isinstance(parsed, (list, tuple, set)):
            items = parsed
        else:
            items = [parsed]

    aphiaid_values = []
    for item in items:
        item_text = str(item).strip().strip("[]").strip("'").strip('"')
        if item_text.isdigit():
            aphiaid_values.append(int(item_text))

    return aphiaid_values


def read_csv_as_gdf(csv_file):
    """Read CSV and return GeoDataFrame in WGS84 (EPSG:4326)."""
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"⚠️ Could not read {csv_file}: {e}")
        return None

    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        print(f"⚠️ Missing required columns in {csv_file}: {sorted(missing_columns)} - skipping")
        return None

    df = df.dropna(subset=["latitude", "longitude"])
    if df.empty:
        print(f"⚠️ No coordinate rows in {csv_file} - skipping")
        return None

    df["aphiaid_values"] = df["aphiaid"].apply(parse_aphiaid_value)
    df = df.explode("aphiaid_values", ignore_index=True)
    df["aphiaid_value"] = pd.to_numeric(df["aphiaid_values"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["aphiaid_value"])
    if df.empty:
        print(f"⚠️ No valid Aphia IDs in {csv_file} - skipping")
        return None

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.longitude, df.latitude),
        crs="EPSG:4326"
    )

    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    if gdf.empty:
        print(f"⚠️ No valid geometries in {csv_file} after processing - skipping")
        return None

    return gdf


def h3_to_polygon(h):
    """Convert H3 cell to Polygon."""
    boundary = h3.cell_to_boundary(h)
    coords = [(lng, lat) for lat, lng in boundary]
    return Polygon(coords)


def create_hexagon_geojson(csv_files, h3_resolution, output_file, out_dir):
    """
    Create H3 hexagon grid from CSV files and export to GeoJSON.

    Args:
        csv_files: List of CSV file paths
        h3_resolution: H3 resolution level (lower = bigger hexagons)
        output_file: Output filename (without extension)
        out_dir: Output directory path
    """
    gdfs = []
    for csv_path in csv_files:
        gdf = read_csv_as_gdf(csv_path)
        if gdf is None or len(gdf) == 0:
            continue
        gdfs.append(gdf)

    if not gdfs:
        print("⚠️ No valid data loaded")
        return

    gdf = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True),
        crs="EPSG:4326"
    )

    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    unique_columns = ["latitude", "longitude", "observationdate", "timeofday", "aphiaid_value"]
    gdf = gdf.drop_duplicates(subset=unique_columns)
    if gdf.empty:
        print("⚠️ No unique observation-time Aphia records found")
        return

    gdf["h3_index"] = gdf.geometry.apply(
        lambda geom: h3.latlng_to_cell(geom.y, geom.x, h3_resolution)
    )

    hex_counts = (
        gdf.groupby("h3_index")
        .size()
        .reset_index(name="count")
    )

    hex_counts["geometry"] = hex_counts["h3_index"].apply(h3_to_polygon)

    hex_gdf = gpd.GeoDataFrame(
        hex_counts,
        geometry="geometry",
        crs="EPSG:4326"
    )


    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{output_file}.geojson"

    hex_gdf.to_file(output_path, driver="GeoJSON")
    print(f"✔ Saved: {output_path}")
    # print(hex_gdf.head())

    return hex_gdf


if __name__ == "__main__":
    dir_call1 = Path("../data/1.harvest_wp2_observation_data")
    dir_wp3 = Path("../data/2.harvest_wp3_sensor_observation_data")

    csv_call1 = sorted(dir_call1.glob("*.csv"))
    csv_wp3 = sorted(dir_wp3.glob("*.csv"))
    csv_all = csv_call1 + csv_wp3

    print("working on wp2.")
    create_hexagon_geojson(
        csv_files=csv_call1,
        h3_resolution=4,
        output_file="wp2_observations_hexagons",
        out_dir="../plots"
    )
    print("working on WP3...")
    create_hexagon_geojson(
        csv_files=csv_wp3,
        h3_resolution=4,
        output_file="wp3_sensor_observations_hexagons",
        out_dir="../plots"
    )
    print("working on wp2+wp3...")
    create_hexagon_geojson(
        csv_files=csv_all,
        h3_resolution=4,
        output_file="all_observations_hexagons",
        out_dir="../plots"
    )

