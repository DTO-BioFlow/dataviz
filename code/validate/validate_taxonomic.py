import csv
from pathlib import Path

# loop over ../data/3.harvest_etn and selet all files with taxonomic_count in the filename
# it looks like this;
# animal_scientific_name,count
# Anguilla anguilla,108260
# Anguilla rostrata,723

# provide the totat count of all files

# Get the path to the data directory
data_path = Path(__file__).parent.parent.parent / "data" / "3.harvest_ETN"

# Find all files with taxonomic_count in the filename
taxonomic_files = sorted(data_path.glob("*taxonomic_count.csv"))

print(f"Found {len(taxonomic_files)} taxonomic count files\n")

total_count = 0
file_counts = {}
sync_tag_files = []
sync_tag_total = 0

# Process each file
for file_path in taxonomic_files:
    file_total = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # normalize name to match variants like 'Sync tag' or 'sync_tag'
                name = row.get('animal_scientific_name', '')
                if name is None:
                    name = ''
                name_norm = name.strip().lower().replace('_', ' ')

                # parse count robustly
                try:
                    count = int(float(row['count']))
                except Exception:
                    # fallback if parsing fails
                    count = int(row['count']) if row.get('count') and row['count'].isdigit() else 0

                file_total += count

                # if this row is a Sync tag, count it separately
                if name_norm == 'sync tag':
                    sync_tag_total += count
                    # record this file as containing Sync tag
                    if file_path.name not in sync_tag_files:
                        sync_tag_files.append(file_path.name)
            except (ValueError, KeyError):
                pass

    file_counts[file_path.name] = file_total
    total_count += file_total
    print(f"{file_path.name}: {file_total}")

print(f"\n{'='*60}")
print(f"Total count across all taxonomic files: {total_count}")
print(f"{'='*60}")

if sync_tag_total > 0:
    print(f"\nSync tag total count: {sync_tag_total}")
    print(f"Datasets with Sync tag ({len(sync_tag_files)}):")
    for name in sorted(sync_tag_files):
        print(f" - {name}")
else:
    print("\nNo Sync tag rows found in taxonomic files.")

