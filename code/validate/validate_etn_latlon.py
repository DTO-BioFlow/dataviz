from __future__ import annotations

import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
ETN_DIR = ROOT_DIR / "data" / "3.harvest_ETN"
REQUIRED_COLUMNS = {
	"deployment_station_name",
	"deployment_latitude",
	"deployment_longitude",
	"count",
}


def normalize_header_map(fieldnames):
	"""Map normalized header names to the original CSV header names."""
	return {name.strip().lower(): name for name in fieldnames or [] if name and name.strip()}


def is_blank(value):
	return value is None or str(value).strip() == "" or str(value).strip().lower() in {"nan", "none", "null"}


def parse_coordinate(value, label, file_name, line_no):
	"""Return a float coordinate or an error message."""
	if is_blank(value):
		return None, f"{file_name}:{line_no} missing {label}"

	try:
		coordinate = float(str(value).strip())
	except ValueError:
		return None, f"{file_name}:{line_no} invalid {label}={value!r}"

	if label == "latitude" and not (-90.0 <= coordinate <= 90.0):
		return None, f"{file_name}:{line_no} out-of-range {label}={coordinate}"
	if label == "longitude" and not (-180.0 <= coordinate <= 180.0):
		return None, f"{file_name}:{line_no} out-of-range {label}={coordinate}"

	return coordinate, None


def validate_file(csv_file: Path):
	"""Validate one ETN detections CSV file.

	Returns a tuple of (row_count, issue_count, issues).
	"""
	issues = []
	row_count = 0

	with csv_file.open(newline="", encoding="utf-8") as handle:
		reader = csv.DictReader(handle)
		header_map = normalize_header_map(reader.fieldnames)
		missing_columns = sorted(column for column in REQUIRED_COLUMNS if column not in header_map)
		if missing_columns:
			issues.append(f"{csv_file.name}: missing required columns: {', '.join(missing_columns)}")
			return row_count, len(issues), issues

		station_col = header_map["deployment_station_name"]
		lat_col = header_map["deployment_latitude"]
		lon_col = header_map["deployment_longitude"]
		count_col = header_map["count"]

		for line_no, row in enumerate(reader, start=2):
			if not any((value or "").strip() for value in row.values()):
				continue

			row_count += 1

			station_name = (row.get(station_col) or "").strip() or "<missing station name>"
			lat, lat_issue = parse_coordinate(row.get(lat_col), "latitude", csv_file.name, line_no)
			lon, lon_issue = parse_coordinate(row.get(lon_col), "longitude", csv_file.name, line_no)

			if lat_issue:
				issues.append(f"{lat_issue} (station={station_name})")
			if lon_issue:
				issues.append(f"{lon_issue} (station={station_name})")

			count_value = row.get(count_col)
			if is_blank(count_value):
				issues.append(f"{csv_file.name}:{line_no} missing count (station={station_name})")
			else:
				try:
					count_int = int(str(count_value).strip())
				except ValueError:
					issues.append(f"{csv_file.name}:{line_no} invalid count={count_value!r} (station={station_name})")
				else:
					if count_int < 0:
						issues.append(f"{csv_file.name}:{line_no} negative count={count_int} (station={station_name})")

	return row_count, len(issues), issues


def main():
	if not ETN_DIR.exists():
		raise FileNotFoundError(f"ETN data directory not found: {ETN_DIR}")

	csv_files = sorted(ETN_DIR.glob("*_detections.csv"))
	if not csv_files:
		print(f"No detection CSV files found in {ETN_DIR}")
		return

	grand_rows = 0
	grand_issues = 0

	for csv_file in csv_files:
		row_count, issue_count, issues = validate_file(csv_file)
		grand_rows += row_count
		grand_issues += issue_count

		status = "OK" if issue_count == 0 else "ISSUES"
		print(f"{csv_file.name}: status={status}, rows={row_count}, issues={issue_count}")
		for issue in issues[:10]:
			print(f"  - {issue}")
		if issue_count > 10:
			print(f"  - ... {issue_count - 10} more issue(s)")

	print("-" * 72)
	print(f"Files scanned: {len(csv_files)}")
	print(f"Rows scanned: {grand_rows}")
	print(f"Total issues: {grand_issues}")


if __name__ == "__main__":
	main()
