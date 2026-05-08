import pandas as pd
from pathlib import Path
import json
import warnings

warnings.filterwarnings('ignore')



def get_datasets():
    """Get all the CSV files from ../data/3.harvest_ETN without the taxonomy files.

    Returns a list of CSV file paths (excluding _taxonomic_count.csv files).
    """
    data_dir = Path("../data/3.harvest_ETN")
    csv_files = sorted([f for f in data_dir.glob("*.csv")
                       if not str(f).endswith("_taxonomic_count.csv")])
    return csv_files





def combined_map(datasets):
    """Combine all CSV data into a GeoJSON file.

    Merges all dataset points and saves as a GeoJSON file.
    """
    all_features = []

    for dataset in datasets:
        df = pd.read_csv(dataset)

        # Skip if no data
        if df.empty:
            continue

        # Remove rows with missing coordinates
        df = df.dropna(subset=['deployment_latitude', 'deployment_longitude'])

        if df.empty:
            continue

        # Create features for each row
        for idx, row in df.iterrows():
            feature = {
                "type": "Feature",
                "properties": {
                    "station_name": str(row.get('deployment_station_name', '')),
                    "count": int(row['count']),
                    "dataset": dataset.stem
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['deployment_longitude']),
                                   float(row['deployment_latitude'])]
                }
            }
            all_features.append(feature)

    # Create GeoJSON FeatureCollection
    geojson_data = {
        "type": "FeatureCollection",
        "features": all_features
    }

    # Create output directory if it doesn't exist
    output_dir = Path("../plots")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save GeoJSON
    output_path = output_dir / "etn_combined_map.geojson"
    with open(output_path, 'w') as f:
        json.dump(geojson_data, f, indent=2)

    print(f"✔ Saved combined GeoJSON: {output_path}")
    print(f"  Total features: {len(all_features)}")


if __name__ == '__main__':

    datasets = get_datasets()
    print(f"Found {len(datasets)} dataset(s)")

    try:
        combined_map(datasets)
    except Exception as e:
        print(f"⚠ Error creating combined map: {e}")
