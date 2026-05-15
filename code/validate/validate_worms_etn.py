import json
from pathlib import Path

# read ../data/worms/etn.json
# this is how the json looks like;
# [
#   {
#     "animal_scientific_name": "Abramis brama",
#     "aphia_id": 154281,
#     "taxonomy": [
#       "Animalia",
#       "Chordata",
#       "Teleostei",
#       "Cypriniformes",
#       "Cyprinidae",
#       "Abramis",
#       "Abramis brama"
#     ],
#     "count": 370287
#   },

# count the total count over all items

# Get the path to the data file
file_path = Path(__file__).parent.parent.parent / "data" / "worms" / "etn.json"

# Read the JSON file
with open(file_path, 'r') as f:
    data = json.load(f)

# Count the total count over all items
total_count = sum(item.get("count", 0) for item in data)

print(f"Total count across all items: {total_count}")
print(f"Number of unique species: {len(data)}")

