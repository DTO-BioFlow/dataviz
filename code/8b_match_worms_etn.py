"""
Match ETN taxonomic-count CSVs to WoRMS taxonomic hierarchy.

Input:
    ../data/3.harvest_ETN/*_taxonomic_count.csv

Output:
    ../data/worms/etn.json

Each input CSV contains:
    animal_scientific_name,count

The output is a combined JSON list of records with:
    animal_scientific_name, aphia_id, taxonomy, count

WoRMS responses are cached in ../cache/aphia_cache.json.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
import json
import threading

import pandas as pd
import requests

# ------------------------
# Cache setup
# ------------------------
cache_dir = Path("../cache")
cache_dir.mkdir(parents=True, exist_ok=True)
cache_file = cache_dir / "aphia_cache.json"

aphia_cache = {}
if cache_file.exists():
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            aphia_cache = json.load(f)
    except Exception:
        aphia_cache = {}

cache_lock = threading.Lock()


# ------------------------
# WoRMS API function
# ------------------------
def get_aphia_record(scientific_name: str):
    """Retrieve WoRMS Aphia record(s) for a scientific name using cache."""
    name = str(scientific_name).strip()
    if not name:
        return None

    cache_key = name.lower()
    if cache_key in aphia_cache:
        return aphia_cache[cache_key]

    url = f"https://www.marinespecies.org/rest/AphiaRecordsByName/{quote(name)}?marine_only=false"
    try:
        print(f"request WORMS for {name}")
        response = requests.get(url, headers={"accept": "application/json"}, timeout=15)
        response.raise_for_status()
        record = response.json()
    except Exception as e:
        print(f"⚠️ WoRMS lookup failed for {name}: {e}")
        record = None

    with cache_lock:
        aphia_cache[cache_key] = record

    return record


def pick_best_record(records, scientific_name: str):
    """Pick the best matching WoRMS record from a response list."""
    if not records:
        return None
    if isinstance(records, dict):
        return records

    target = str(scientific_name).strip().lower()
    for rec in records:
        if str(rec.get("scientificname", "")).strip().lower() == target:
            return rec
    return records[0]


def build_taxonomy(rec):
    """Return the taxonomic hierarchy in the same rank order as the other script."""
    if not rec:
        return None

    taxonomy = [
        rec.get("kingdom"),
        rec.get("phylum"),
        rec.get("class"),
        rec.get("order"),
        rec.get("family"),
        rec.get("genus"),
    ]

    sci = rec.get("scientificname")
    if sci not in taxonomy:
        taxonomy.append(sci)
    else:
        taxonomy.append(None)

    return taxonomy


# ------------------------
# Process CSV
# ------------------------
def process_taxonomic_file(csv_file: Path, max_threads=10):
    """Process one ETN taxonomic-count CSV and return combined name -> result data."""
    try:
        df = pd.read_csv(str(csv_file))
    except Exception as e:
        print(f"⚠️ Failed to read {csv_file}: {e}")
        return {}

    required_columns = {"animal_scientific_name", "count"}
    if not required_columns.issubset(df.columns):
        print(f"⚠️ Skipping {csv_file.name}: expected columns {sorted(required_columns)}, got {list(df.columns)}")
        return {}

    name_counts = defaultdict(int)
    for row in df.itertuples(index=False):
        name = getattr(row, "animal_scientific_name", None)
        if pd.isna(name) or str(name).strip() == "":
            continue

        try:
            count = int(getattr(row, "count", 0) or 0)
        except Exception:
            count = 0

        name_counts[str(name).strip()] += count

    results = {}

    def fetch_record(name):
        records = get_aphia_record(name)
        rec = pick_best_record(records, name)
        taxonomy = build_taxonomy(rec)
        if taxonomy:
            return name, {
                "animal_scientific_name": name,
                "aphia_id": rec.get("AphiaID") if rec else None,
                "taxonomy": taxonomy,
                "count": name_counts[name],
            }
        return None

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(fetch_record, name): name for name in name_counts.keys()}
        for future in as_completed(futures):
            res = future.result()
            if res:
                name, data = res
                results[name] = data

    with cache_lock:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(aphia_cache, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to write cache to disk: {e}")

    return results


if __name__ == "__main__":
    output_dir = Path("../data/worms")
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_dir = Path("../data/3.harvest_ETN")
    csv_files = sorted(csv_dir.glob("*_taxonomic_count.csv"))

    if not csv_files:
        print(f"⚠️ No ETN taxonomic-count CSV files found in {csv_dir}")

    combined_results = {}

    for file in csv_files:
        print(f"Processing {file.name}...")
        data = process_taxonomic_file(file)
        if not data:
            continue

        for name, info in data.items():
            if name in combined_results:
                combined_results[name]["count"] += info["count"]
            else:
                combined_results[name] = info

        print(f"✅ Processed {file.name}, accumulated {len(combined_results)} unique taxa")

    output_file = output_dir / "etn.json"
    if combined_results:
        results_list = [combined_results[name] for name in sorted(combined_results)]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results_list, f, indent=2)

        print(f"✅ Saved combined taxonomy data to {output_file}")
    else:
        print("⚠️ No data to process")

    print(f"✅ All done. Aphia cache stored at {cache_file}")




