from pathlib import Path
import urllib.request
import json
from urllib.parse import urljoin
import duckdb


def find_ETN_parquets_alt():
    collection_url = "https://www.lifewatch.be/etn/parquet/animal_tracking_datasets/collection.json"
    try:
        with urllib.request.urlopen(collection_url) as resp:
            coll = json.load(resp)
    except Exception as e:
        # unable to fetch collection
        return

    links = coll.get('links', [])
    for link in links:
        if link.get('rel') != 'item':
            continue
        item_href = urljoin(collection_url, link.get('href'))
        try:
            with urllib.request.urlopen(item_href) as ir:
                item = json.load(ir)
        except Exception:
            continue
        # capture stable item id for output filenames
        item_id = item.get('id') or Path(item_href).stem

        assets = item.get('assets', {})
        for asset in assets.values():
            href = asset.get('href')
            if not href:
                continue
            full = urljoin(item_href, href)
            # only consider detection parquet files
            if 'detections' not in str(full).lower():
                continue
            atype = (asset.get('type') or '').lower()
            roles = asset.get('roles', []) or []
            # heuristics to identify parquet assets
            if atype in ('application/x-parquet', 'application/parquet') or 'data' in roles or str(full).lower().endswith('.parquet'):
                yield item_id, full

def validate(url):
    con = duckdb.connect(database=":memory:")
    try:
        con.execute("LOAD httpfs;")
    except Exception:
        # DuckDB can still read some remote URLs depending on the build.
        pass

    safe_url = url.replace("'", "''")
    sql = (
        "SELECT "
        "COUNT(*) AS total_rows, "
        "SUM(CASE WHEN animal_scientific_name IS NULL OR trim(CAST(animal_scientific_name AS VARCHAR)) = '' THEN 1 ELSE 0 END) AS missing_animal_scientific_name "
        f"FROM read_parquet('{safe_url}')"
    )

    total_rows, missing_rows = con.execute(sql).fetchone()
    missing_rows = missing_rows or 0
    print(f"Total rows: {total_rows}")
    print(f"Missing animal_scientific_name: {missing_rows}")
    return total_rows, missing_rows

if __name__ == "__main__":
    grand_total_rows = 0
    for i, item in enumerate(find_ETN_parquets_alt()):
        try:
            item_id, url = item
        except Exception:
            print("Skipping unexpected item:", item)
            continue

        try:
            total_rows, _ = validate(url)
            grand_total_rows += total_rows

        except Exception as e:
            print(f"Error processing {item_id} -> {url}: {e}")

    print(f"Grand total rows across all ETN files: {grand_total_rows}")
