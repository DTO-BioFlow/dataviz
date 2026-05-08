"""
This script finds the EDITO occurrence parquet and loops over all datasets
from DTO-Bioflow using dasids. The dasids are stored in /sources/...
The results are stored in 2 directories that will be created:
../data/1_harvest_wp2_observation_data
and
../data/2_harvest_wp3_sensor_observation_data
In each directory, the datasets are stored each in separate CSV with columns
latitude, longitude, observationdate, aphiaid.
"""
import pyarrow.fs
import pyarrow.dataset as ds
import pyarrow.fs
import pystac_client
from urllib.parse import urlparse
from datetime import datetime, timezone
import pandas as pd
from pathlib import Path
import pyarrow.compute as pc
import shutil


def read_dataset_ids(file_path: str):
    """Read dataset IDs (integers) from a text file, one per line."""
    with open(file_path, "r") as f:
        ids = [int(line.strip()) for line in f if line.strip().isdigit()]
    print(f"Loaded {len(ids)} dataset IDs from {file_path}")
    return ids

def parse_aphiaid_value(value):
    """Parse aphiaid values that may be scalars, strings, or list-like strings."""
    if isinstance(value, list):
        return [int(v) for v in value if str(v).strip().isdigit()]
    if isinstance(value, tuple):
        return [int(v) for v in value if str(v).strip().isdigit()]
    if pd.isna(value):
        return []
    if isinstance(value, str):
        cleaned = value.strip().strip("[]")
        if not cleaned:
            return []
        parts = [part.strip().strip('"').strip("'") for part in cleaned.split(",")]
        return [int(part) for part in parts if part.isdigit()]
    if str(value).strip().isdigit():
        return [int(value)]
    return []


def find_occurrence_data():
    """Find EMODnet occurrence parquet URLs from the STAC catalog."""
    url = 'https://catalog.dive.edito.eu'
    client = pystac_client.Client.open(url)
    variable = "emodnet-occurrence_data"

    for collection in client.get_collections():
        if variable in collection.id:
            for item in collection.get_items():
                for key, value in item.assets.items():
                    if key == "parquet":
                        yield value.href


def setup_s3_dataset(url: str):
    """Set up S3 connection and return dataset object."""
    parsed = urlparse(url)

    if parsed.scheme in ("http", "https") and "cloudferro.com" in parsed.netloc:
        endpoint = parsed.netloc
        s3_path = parsed.path.lstrip("/")
        s3 = pyarrow.fs.S3FileSystem(endpoint_override=endpoint, anonymous=True)
    elif parsed.scheme == "s3":
        endpoint = "s3.waw3-1.cloudferro.com"
        s3_path = f"{parsed.netloc}/{parsed.path.lstrip('/')}"
        s3 = pyarrow.fs.S3FileSystem(endpoint_override=endpoint, anonymous=True)
    else:
        raise ValueError(f"Unsupported URL scheme: {url}")

    print(f"Connected to endpoint: {endpoint}")
    print(f"Dataset path: {s3_path}")

    dataset = ds.dataset(s3_path, filesystem=s3, format="parquet")
    return dataset


def extract_call1_data(dataset, dataset_id: int, output_dir: Path):
    """
    Extract data for one dataset ID, keep unique latitude, longitude, observationdate, timeofday combinations,
    store all unique aphiaids at that location and time in a list, and save to CSV.
    Handles missing timeofday and empty aphiaid values.
    """
    columns_needed = ["datasetid", "latitude", "longitude", "observationdate", "aphiaid", "timeofday"]
    dataset_filter = pc.field("datasetid") == dataset_id

    try:
        table = dataset.to_table(columns=columns_needed, filter=dataset_filter)
        df = table.to_pandas()
    except Exception as e:
        print(f"⚠️ Error extracting datasetid {dataset_id}: {e}")
        return

    if df.empty:
        print(f"No records found for datasetid {dataset_id}")
        return

    # ----------------------------
    # Clean and prepare columns
    # ----------------------------
    # Ensure 'timeofday' exists and fill missing values
    if "timeofday" not in df.columns:
        df["timeofday"] = ""
    df["timeofday"] = df["timeofday"].fillna("")

    # Drop duplicates across grouping keys + aphiaid
    df = df.drop_duplicates(subset=["latitude", "longitude", "observationdate", "aphiaid", "timeofday"])

    # Parse aphiaid column (ensure list of unique integers)
    df["aphiaid"] = df["aphiaid"].apply(lambda x: sorted(set(parse_aphiaid_value(x))))

    # Group by lat, lon, datetime, timeofday
    df_grouped = (
        df.groupby(["latitude", "longitude", "observationdate", "timeofday"], as_index=False)
          .agg({"aphiaid": lambda x: sorted(set([a for sub in x for a in (sub if isinstance(sub, list) else [sub])]))})
    )

    # Save to CSV
    csv_name = output_dir / f"dasid_{dataset_id}.csv"
    df_grouped.to_csv(csv_name, index=False)
    max_aphiaids = df_grouped["aphiaid"].apply(len).max() if not df_grouped.empty else 0
    print(f"✅ Saved {len(df_grouped)} aggregated records for datasetid {dataset_id} to {csv_name}")
    print(f"   ↳ Each (lat, lon, time) has {max_aphiaids} max unique aphiaids")


def extract_sensor_data(dataset, dataset_id: int, output_dir: Path):
    """
    Extract sensor data for one dataset ID with unique spatial-temporal coordinates.
    Handles missing timeofday and cleans aphiaids.
    """
    columns_needed = ["datasetid", "latitude", "longitude", "observationdate", "aphiaid", "timeofday"]
    dataset_filter = pc.field("datasetid") == dataset_id

    try:
        table = dataset.to_table(columns=columns_needed, filter=dataset_filter)
        df = table.to_pandas()
    except Exception as e:
        print(f"⚠️ Error extracting datasetid {dataset_id}: {e}")
        return

    if df.empty:
        print(f"No records found for datasetid {dataset_id}")
        return

    # Clean observationdate
    df["observationdate"] = pd.to_datetime(df["observationdate"], errors="coerce")

    # Filter for recent data if needed
    if dataset_id in [3117, 4688, 5531]:
        cutoff = datetime(2023, 9, 1, tzinfo=timezone.utc)
        df = df[df["observationdate"] >= cutoff]
        if df.empty:
            print(f"No records from September 2023 onwards for datasetid {dataset_id}")
            return

    # Clean aphiaid column
    df["aphiaid"] = df["aphiaid"].astype(str).str.replace(",", "", regex=False).str.strip()
    df["aphiaid"] = df["aphiaid"].replace(["nan", "None", "none", "null", "", "[]"], pd.NA)
    df = df.dropna(subset=["aphiaid"])
    df["aphiaid"] = pd.to_numeric(df["aphiaid"], errors="coerce").dropna().astype(int)

    # Ensure 'timeofday' exists and fill missing
    if "timeofday" not in df.columns:
        df["timeofday"] = ""
    df["timeofday"] = df["timeofday"].fillna("")

    # Drop duplicates and group
    df = df.drop_duplicates(subset=["latitude", "longitude", "observationdate", "aphiaid", "timeofday"])
    df_grouped = (
        df.groupby(["latitude", "longitude", "observationdate", "timeofday"], as_index=False)
          .agg({"aphiaid": lambda x: sorted(set([a for a in x]))})
    )

    csv_name = output_dir / f"dasid_{dataset_id}.csv"
    df_grouped.to_csv(csv_name, index=False)
    max_aphiaids = df_grouped["aphiaid"].apply(len).max() if not df_grouped.empty else 0
    print(f"✅ Saved {len(df_grouped)} aggregated records for datasetid {dataset_id} to {csv_name}")
    print(f"   ↳ Each (lat, lon, time) has {max_aphiaids} max unique aphiaids")


def extract_tracking_data(dataset, dataset_id: int, output_dir: Path):
    """
    Extract tracking data for one dataset ID with unique spatial-temporal coordinates.
    Handles missing timeofday and cleans aphiaids.
    """
    columns_needed = ["datasetid", "latitude", "longitude", "observationdate", "aphiaid", "timeofday"]
    dataset_filter = pc.field("datasetid") == dataset_id

    try:
        table = dataset.to_table(columns=columns_needed, filter=dataset_filter)
        df = table.to_pandas()
    except Exception as e:
        print(f"⚠️ Error extracting datasetid {dataset_id}: {e}")
        return

    if df.empty:
        print(f"No records found for datasetid {dataset_id}")
        return

    # Ensure 'timeofday' exists and fill missing
    if "timeofday" not in df.columns:
        df["timeofday"] = ""
    df["timeofday"] = df["timeofday"].fillna("")

    # Drop duplicates and group
    df = df.drop_duplicates(subset=["latitude", "longitude", "observationdate", "aphiaid", "timeofday"])
    df["aphiaid"] = df["aphiaid"].apply(lambda x: sorted(set(ast.literal_eval(x))) if isinstance(x, str) else ([x] if pd.notna(x) else []))
    df_grouped = (
        df.groupby(["latitude", "longitude", "observationdate", "timeofday"], as_index=False)
          .agg({"aphiaid": lambda x: sorted(set([a for sub in x for a in (sub if isinstance(sub, list) else [sub])]))})
    )

    csv_name = output_dir / f"dasid_{dataset_id}.csv"
    df_grouped.to_csv(csv_name, index=False)
    max_aphiaids = df_grouped["aphiaid"].apply(len).max() if not df_grouped.empty else 0
    print(f"✅ Saved {len(df_grouped)} aggregated records for datasetid {dataset_id} to {csv_name}")
    print(f"   ↳ Each (lat, lon, time) has {max_aphiaids} max unique aphiaids")



if __name__ == "__main__":

    # Setup data lake connection
    occ = find_occurrence_data()
    data_file = next(occ)
    print(f"Using dataset: {data_file}")
    dataset = setup_s3_dataset(data_file)

    # -------------------------------------------------------------------------
    # call1 data
    print("-"*50)
    print("working on call1 datasets")
    call1_source = "../sources/dasid_wp2_observations_call1.txt"
    call1_dasids = read_dataset_ids(call1_source)
    mirror_text_file_to_docs(call1_source)
    write_ids_js_to_docs(call1_source, call1_dasids, "WP2_DASIDS")
    output_dir = Path("../data/1.harvest_wp2_observation_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, did in enumerate(call1_dasids):
        print(f"dataset {i} out of {len(call1_dasids)}")
        extract_call1_data(dataset, did, output_dir)

    # -------------------------------------------------------------------------
    # sensor datasets
    print("-"*50)
    print("working on sensor datasets")
    sensor_source = "../sources/dasid_wp3_sensor_observations.txt"
    sensor_dasids = read_dataset_ids(sensor_source)
    mirror_text_file_to_docs(sensor_source)
    write_ids_js_to_docs(sensor_source, sensor_dasids, "WP3_SENSOR_DASIDS")
    output_dir = Path("../data/2.harvest_wp3_sensor_observation_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, did in enumerate(sensor_dasids):
        print(f"dataset {i} out of {len(sensor_dasids)}")
        extract_sensor_data(dataset, did, output_dir)

    # # -------------------------------------------------------------------------
    # # sensor datasets
    # print("-"*50)
    # print("working on tracking datasets")
    # tracking_dasids = read_dataset_ids("../sources/dasid_tracking_data.txt")
    # output_dir = Path("../data/output_tracking_data")
    # output_dir.mkdir(parents=True, exist_ok=True)
    #
    # for i, did in enumerate(tracking_dasids):
    #     print(f"dataset {i} out of {len(tracking_dasids)}")
    #     extract_tracking_data(dataset, did, output_dir)
