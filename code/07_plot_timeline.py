"""
create timeline values in geojson. The occurrences are grouped per year and
stored in a json with format year and count. The script reads the CSV files
from the three harvest folders, extracts the relevant date information, and
computes cumulative counts of occurrences per year. The resulting data is
structured in a JSON format suitable for use in the `docs/temporal.html`
visualization. The script also ensures that the output JSON file is saved to
the appropriate location within the project structure.
"""
from pathlib import Path
import ast
import json
import pandas as pd


def _load_csvs(csv_files, date_col):
    frames = []
    for f in csv_files:
        frame = pd.read_csv(f)  # type: ignore[call-overload]
        frame[date_col] = pd.to_datetime(frame[date_col])
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _parse_aphiaid_value(value):
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


def _yearly_cumulative_from_obs(csv_files):
    """Return a yearly cumulative series from CSVs with observation datetime and aphiaid columns."""
    data = _load_csvs(csv_files, "observationdate")
    if data.empty:
        return pd.Series(dtype="int64")

    data["year"] = data["observationdate"].dt.year
    data["count"] = data["aphiaid"].apply(lambda value: max(1, len(_parse_aphiaid_value(value))))
    yearly = data.groupby("year")["count"].sum().sort_index()
    return yearly.cumsum()


def _yearly_cumulative_from_counts(csv_files):
    """Return a yearly cumulative series from CSVs with date/count columns."""
    data = _load_csvs(csv_files, "date")
    if data.empty:
        return pd.Series(dtype="int64")
    data["year"] = data["date"].dt.year
    yearly = data.groupby("year")["count"].sum().sort_index()
    return yearly.cumsum()


def _series_to_xy(series):
    return {
        "x": [int(v) for v in series.index.tolist()],
        "y": [int(v) for v in series.tolist()],
    }


def build_temporal_data(csv_dir_wp2, csv_dir_wp3, csv_dir_etn):
    """Build the JSON payload used by `docs/temporal.html`."""
    csv_dir_wp2 = Path(csv_dir_wp2)
    csv_dir_wp3 = Path(csv_dir_wp3)
    csv_dir_etn = Path(csv_dir_etn)

    wp2 = _yearly_cumulative_from_obs(sorted(csv_dir_wp2.glob("*.csv")))
    wp3 = _yearly_cumulative_from_obs(sorted(csv_dir_wp3.glob("*.csv")))
    etn = _yearly_cumulative_from_counts(sorted(csv_dir_etn.glob("*temporal_count.csv")))

    return {
        "wp2": _series_to_xy(wp2),
        "wp3": _series_to_xy(wp3),
        "etn": _series_to_xy(etn),
    }


def write_temporal_data_json(output_path, csv_dir_wp2, csv_dir_wp3, csv_dir_etn):
    """Create `docs/resources/temporal_data.json` from the harvested CSV folders."""
    payload = build_temporal_data(csv_dir_wp2, csv_dir_wp3, csv_dir_etn)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    data_root = root / "data"
    output_path = root / "docs" / "resources" / "temporal_data.json"

    write_temporal_data_json(
        output_path=output_path,
        csv_dir_wp2=data_root / "1.harvest_wp2_observation_data",
        csv_dir_wp3=data_root / "2.harvest_wp3_sensor_observation_data",
        csv_dir_etn=data_root / "3.harvest_ETN",
    )

    print(f"Saved temporal JSON to {output_path}")

