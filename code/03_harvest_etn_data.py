import pystac_client
from pathlib import Path
import urllib.request
import json
from urllib.parse import urljoin
import duckdb
import csv



def find_ETN_parquets():
    url = 'https://catalog.dive.edito.eu'
    client = pystac_client.Client.open(url)
    variable = "animal_tracking_datasets"

    for collection in client.get_collections():

        if variable in collection.id:
            for item in collection.get_items():
                for key, value in item.assets.items():
                    if key == "data":
                        yield value.href


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


def summarize_parquet_to_csv(item_id: str, url: str, out_base: str = "../data/3.harvest_ETN"):
    """Aggregate counts per deployment station using DuckDB (no download) and save CSV.

    This attempts to use DuckDB's read_parquet() to read remote parquet files directly.
    """
    if duckdb is None:
        raise RuntimeError("duckdb is not installed in this environment.")

    print(f"Processing (duckdb): {item_id} -> {url}")
    con = duckdb.connect(database=":memory:")
    try:
        con.execute("LOAD httpfs;")
    except Exception:
        # If the extension is not available, DuckDB may still read some URLs depending on build.
        pass

    # Escape single quotes in URL for SQL string literal
    safe_url = url.replace("'", "''")
    sql = (
        "SELECT deployment_station_name, deployment_latitude, deployment_longitude, COUNT(*) AS count "
        f"FROM read_parquet('{safe_url}') "
        "GROUP BY deployment_station_name, deployment_latitude, deployment_longitude"
    )

    try:
        df = con.execute(sql).df()
    except Exception as e:
        raise RuntimeError(f"DuckDB query failed for {url}: {e}")

    out_dir = Path(out_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{item_id}.csv"
    df.to_csv(out_file, index=False)
    print(f"Saved summary: {out_file}")


def count_taxonomic_occurrences(item_id: str, url: str, out_base: str = "../data/3.harvest_ETN"):
    """Count occurrences of animal_scientific_name using DuckDB (no download) and save CSV.

    Groups by animal_scientific_name and counts occurrences. Sum of counts equals total rows.
    """
    if duckdb is None:
        raise RuntimeError("duckdb is not installed in this environment.")

    print(f"Processing taxonomic counts (duckdb): {item_id} -> {url}")
    con = duckdb.connect(database=":memory:")
    try:
        con.execute("LOAD httpfs;")
    except Exception:
        # If the extension is not available, DuckDB may still read some URLs depending on build.
        pass

    # Escape single quotes in URL for SQL string literal
    safe_url = url.replace("'", "''")
    sql = (
        "SELECT animal_scientific_name, COUNT(*) AS count "
        f"FROM read_parquet('{safe_url}') "
        "GROUP BY animal_scientific_name "
        "ORDER BY count DESC"
    )

    try:
        df = con.execute(sql).df()
    except Exception as e:
        raise RuntimeError(f"DuckDB query failed for {url}: {e}")

    out_dir = Path(out_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{item_id}_taxonomic_count.csv"
    df.to_csv(out_file, index=False)
    print(f"Saved taxonomic counts: {out_file}")


def assemble_dois(out_base: str = "../data"):
    """Extract metadata (id, parquet URL, and DOI link) from ETN collection items and save to CSV."""
    collection_url = "https://www.lifewatch.be/etn/parquet/animal_tracking_datasets/collection.json"

    metadata = []

    try:
        with urllib.request.urlopen(collection_url) as resp:
            coll = json.load(resp)
    except Exception as e:
        print(f"Error fetching collection: {e}")
        return

    links = coll.get('links', [])
    for link in links:
        if link.get('rel') != 'item':
            continue
        item_href = urljoin(collection_url, link.get('href'))
        try:
            with urllib.request.urlopen(item_href) as ir:
                item = json.load(ir)
        except Exception as e:
            print(f"Error fetching item {item_href}: {e}")
            continue

        # Capture item id
        item_id = item.get('id') or Path(item_href).stem

        # Find parquet data asset
        parquet_url = None
        assets = item.get('assets', {})
        for asset in assets.values():
            href = asset.get('href')
            if not href:
                continue
            full = urljoin(item_href, href)
            # Only consider detection parquet files
            if 'detections' not in str(full).lower():
                continue
            atype = (asset.get('type') or '').lower()
            roles = asset.get('roles', []) or []
            # Heuristics to identify parquet assets
            if atype in ('application/x-parquet', 'application/parquet') or 'data' in roles or str(full).lower().endswith('.parquet'):
                parquet_url = full
                break

        # Find cite-as (DOI) link
        doi_link = None
        item_links = item.get('links', [])
        for item_link in item_links:
            if item_link.get('rel') == 'cite-as':
                doi_link = item_link.get('href')
                break

        # Add to metadata list
        metadata.append({
            'id': item_id,
            'parquet_url': parquet_url or '',
            'doi_link': doi_link or ''
        })

        print(f"Collected metadata for {item_id}")

    # Save to CSV
    out_dir = Path(out_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "ETN_meta.csv"

    if metadata:
        with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'parquet_url', 'doi_link']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metadata)
        print(f"Saved metadata to: {out_file}")
    else:
        print("No metadata collected.")


if __name__ == "__main__":
    assemble_dois()
    for i, item in enumerate(find_ETN_parquets_alt()):
        try:
            item_id, url = item
        except Exception:
            print("Skipping unexpected item:", item)
            continue

        try:
            summarize_parquet_to_csv(item_id, url)
            count_taxonomic_occurrences(item_id, url)  # New line to call the taxonomic count function
        except Exception as e:
            print(f"Error processing {item_id} -> {url}: {e}")