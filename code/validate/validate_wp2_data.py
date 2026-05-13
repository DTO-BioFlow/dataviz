from __future__ import annotations

import ast
import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
WP2_DIR = ROOT_DIR / "data" / "1.harvest_wp2_observation_data"


def parse_aphiaid_value(value):
	"""Return a list of AphiaIDs from scalars, list-like strings, or lists."""
	if value is None:
		return []

	if isinstance(value, (list, tuple, set)):
		items = value
	else:
		text = str(value).strip()
		if not text or text.lower() in {"nan", "none", "null"}:
			return []

		try:
			parsed = ast.literal_eval(text)
		except Exception:
			parsed = text

		if isinstance(parsed, (list, tuple, set)):
			items = parsed
		else:
			items = [parsed]

	aphiaid_values = []
	for item in items:
		item_text = str(item).strip().strip("[]").strip("'").strip('"')
		if item_text.isdigit():
			aphiaid_values.append(int(item_text))

	return aphiaid_values


def count_csv_occurrences(csv_file: Path):
	"""Count rows and expanded occurrences in a WP2 CSV file."""
	with csv_file.open(newline="", encoding="utf-8") as handle:
		rows = list(csv.reader(handle))

	if not rows:
		return 0, 0

	header = rows[0]
	has_header = any(cell.strip().lower() == "aphiaid" for cell in header)

	if has_header:
		aphiaid_index = next(i for i, cell in enumerate(header) if cell.strip().lower() == "aphiaid")
		data_rows = rows[1:]
	else:
		aphiaid_index = -1
		data_rows = rows

	row_count = 0
	occurrence_count = 0

	for row in data_rows:
		if not row:
			continue

		row_count += 1
		raw_aphiaid = row[aphiaid_index] if abs(aphiaid_index) < len(row) else ""
		aphiaid_values = parse_aphiaid_value(raw_aphiaid)

		# A row always represents at least one occurrence.
		occurrence_count += max(1, len(aphiaid_values))

	return row_count, occurrence_count


def main():
	if not WP2_DIR.exists():
		raise FileNotFoundError(f"WP2 data directory not found: {WP2_DIR}")

	csv_files = sorted(WP2_DIR.glob("*.csv"))
	if not csv_files:
		print(f"No CSV files found in {WP2_DIR}")
		return

	grand_rows = 0
	grand_occurrences = 0

	for csv_file in csv_files:
		row_count, occurrence_count = count_csv_occurrences(csv_file)
		grand_rows += row_count
		grand_occurrences += occurrence_count
		print(f"{csv_file.name}: rows={row_count}, occurrences={occurrence_count}")

	print("-" * 60)
	print(f"Grand total rows: {grand_rows}")
	print(f"Grand total occurrences: {grand_occurrences}")


if __name__ == "__main__":
	main()








