"""
This script finds the EDITO occurrence parquet and loops over all unique
dasids, creating a folder ../data/0.harvest_all_occurrence_data and saving
each dasid as its own CSV with columns latitude, longitude, observationdate,
aphiaid.
"""
import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow.fs
import pystac_client
from urllib.parse import urlparse
from pathlib import Path


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


def extract_data(columns_needed, dataset, dataset_id: int, output_dir: Path):
    """
    Extract data for one dataset ID, keep unique latitude, longitude, observationdate combinations,
    and store all unique aphiaids at that location and time in a list. Save to its own CSV.
    """

    # Filter for the current dataset_id
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

    # Drop duplicates across all grouping keys + aphiaid
    df = df.drop_duplicates(subset=["latitude", "longitude", "observationdate", "aphiaid"])

    # Group by lat, lon, datetime and aggregate unique aphiaids
    df_grouped = (
        df.groupby(["latitude", "longitude", "observationdate"], as_index=False)
          .agg({"aphiaid": lambda x: sorted(set(x))})
    )

    # Save CSV
    csv_name = output_dir / f"dasid_{dataset_id}.csv"
    df_grouped.to_csv(csv_name, index=False)
    print(f"✅ Saved {len(df_grouped)} aggregated records for datasetid {dataset_id} to {csv_name}")
    print(f"   ↳ Each (lat, lon, time) has {df_grouped['aphiaid'].apply(len).max()} max unique aphiaids")


def load_progress(progress_file: Path):
    """Load already processed dataset IDs from a text file."""
    if progress_file.exists():
        with open(progress_file, "r") as f:
            processed = {int(line.strip()) for line in f if line.strip().isdigit()}
        return processed
    return set()


def save_progress(progress_file: Path, dataset_id: int):
    """Append a finished dataset ID to the progress file."""
    with open(progress_file, "a") as f:
        f.write(f"{dataset_id}\n")


if __name__ == "__main__":
    # Get first available parquet dataset URL from STAC
    occ = find_occurrence_data()
    data_file = next(occ)
    print(f"Using dataset: {data_file}")

    # Prepare output_call1 directory
    output_dir = Path("../data/0.harvest_all_occurrence_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare progress tracking file
    progress_file = output_dir / "progress.txt"
    processed_ids = load_progress(progress_file)
    print(f"Already processed dataset IDs: {sorted(processed_ids)}")

    # Set up S3 dataset once
    dataset = setup_s3_dataset(data_file)

    # Get all unique dataset IDs from the Parquet
    print("Fetching unique dataset IDs from Parquet...")
    unique_ids = dataset.to_table(columns=["datasetid"]).to_pandas()["datasetid"].unique()
    print(f"Found {len(unique_ids)} unique dataset IDs.")

    columns_needed = ["datasetid", "latitude", "longitude", "observationdate", "aphiaid"]

    # Loop over all dataset IDs and save each to its own CSV
    for i, did in enumerate(unique_ids, 1):
        if did in processed_ids:
            print(f"Skipping already processed datasetid {did}")
            continue

        print(f"\nProcessing dataset {i} of {len(unique_ids)}: datasetid {did}")
        extract_data(columns_needed=columns_needed,
                     dataset=dataset,
                     dataset_id=did,
                     output_dir=output_dir)

        # Mark as done
        save_progress(progress_file, did)
