from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]
GEOJSON_FILES = [
	ROOT / "docs" / "resources" / "maps" / "wp2_observations_hexagons.geojson",
	ROOT / "docs" / "resources" / "maps" / "wp3_sensor_observations_hexagons.geojson",
	ROOT / "docs" / "resources" / "maps" / "all_observations_hexagons.geojson",
	ROOT / "docs" / "resources" / "maps" / "etn_combined_map.geojson",
]


def sum_counts(geojson_path: Path) -> int:
	try:
		with geojson_path.open("r", encoding="utf-8") as fh:
			data = json.load(fh)
	except FileNotFoundError:
		print(f"Missing file: {geojson_path}")
		return 0
	except json.JSONDecodeError as exc:
		print(f"Invalid JSON in {geojson_path}: {exc}")
		return 0

	features = data.get("features", [])
	total = 0
	for feature in features:
		props = feature.get("properties", {}) if isinstance(feature, dict) else {}
		count = props.get("count", 0) if isinstance(props, dict) else 0
		try:
			total += int(count)
		except (TypeError, ValueError):
			print(f"Skipping non-numeric count in {geojson_path}: {count!r}")
	return total


def main() -> None:
	grand_total = 0
	for geojson_path in GEOJSON_FILES:
		file_total = sum_counts(geojson_path)
		grand_total += file_total
		print(f"{geojson_path.name}: {file_total}")

	print(f"Grand total: {grand_total}")


if __name__ == "__main__":
	main()
