import pandas as pd
import requests
from pathlib import Path
from collections import Counter
import ast
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ------------------------
# Cache setup
# ------------------------
cache_dir = Path("../cache")
cache_dir.mkdir(parents=True, exist_ok=True)
cache_file = cache_dir / "aphia_cache.json"

aphia_cache = {}
if cache_file.exists():
    try:
        with open(cache_file, "r") as f:
            aphia_cache = json.load(f)
    except Exception:
        aphia_cache = {}

cache_lock = threading.Lock()

# ------------------------
# WoRMS API function
# ------------------------
def get_aphia_record(aphia_id: int):
    """
    Retrieve WoRMS Aphia record using cache if available.
    """
    aphia_id_str = str(aphia_id)
    if aphia_id_str in aphia_cache:
        return aphia_cache[aphia_id_str]

    url = f"https://www.marinespecies.org/rest/AphiaRecordByAphiaID/{aphia_id}"
    try:
        print(f"request WORMS for {aphia_id}")
        response = requests.get(url, headers={"accept": "application/json"}, timeout=10)
        response.raise_for_status()
        record = response.json()
    except Exception:
        record = None

    with cache_lock:
        aphia_cache[aphia_id_str] = record

    return record

# ------------------------
# Process CSV
# ------------------------
def process_csv(csv_file: Path, max_threads=10):
    """
    Process one CSV:
      1. Count occurrences of each AphiaID
      2. Get taxonomy info (from cache or REST API, multithreaded)
      3. Return list of dicts {"taxonomy": [...], "count": n}
      4. Save cache after processing CSV
    """
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"⚠️ Failed to read {csv_file}: {e}")
        return None

    aphia_counter = Counter()

    # Preprocess aphiaids to avoid repeated ast.literal_eval
    aphia_lists = []
    for row in df.itertuples():
        try:
            val = row.aphiaid
            if isinstance(val, str):
                val_list = ast.literal_eval(val)
            elif isinstance(val, int):
                val_list = [val]
            else:
                val_list = []
            aphia_lists.append(val_list)
            aphia_counter.update(val_list)
        except Exception:
            continue

    results = []

    # Multithreaded fetching of records
    def fetch_record(aid):
        rec = get_aphia_record(aid)
        if rec:
            taxonomy = [
                rec.get("kingdom"),
                rec.get("phylum"),
                rec.get("class"),
                rec.get("order"),
                rec.get("family"),
                rec.get("genus"),
            ]

            # Only add scientificname if it is NOT identical to any earlier rank
            sci = rec.get("scientificname")
            if sci not in taxonomy:
                taxonomy.append(sci)
            else:
                taxonomy.append(None)
            return {"taxonomy": taxonomy, "count": aphia_counter[aid]}
        return None

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(fetch_record, aid): aid for aid in aphia_counter.keys()}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    # Save cache after processing CSV
    with cache_lock:
        try:
            with open(cache_file, "w") as f:
                json.dump(aphia_cache, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to write cache to disk: {e}")

    return results

# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    output_dir = Path("../data/worms")
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_dirs = {
        "call1": Path("../data/1.harvest_wp2_observation_data"),
        "sensor": Path("../data/2.harvest_wp3_sensor_observation_data")
    }

    for source_name, csv_dir in csv_dirs.items():
        sub_output_dir = output_dir / f"worms_{source_name}_data"
        sub_output_dir.mkdir(parents=True, exist_ok=True)

        csv_files = sorted(csv_dir.glob("*.csv"))

        for file in csv_files:
            dasid = file.stem.split("_")[-1]
            print(f"Processing DASID {dasid} from {source_name}...")

            data = process_csv(file)
            if data is None:
                continue

            out_file = sub_output_dir / f"worms_info_dasid_{dasid}.json"
            with open(out_file, "w") as f:
                json.dump(data, f, indent=2)

            print(f"✅ Saved taxonomy counts for DASID {dasid} to {out_file}")

    print(f"✅ All done. Aphia cache stored at {cache_file}")