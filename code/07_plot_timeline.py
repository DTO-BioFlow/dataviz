from pathlib import Path
import json
import pandas as pd


def _load_csvs(csv_files, date_col):
    frames = []
    for f in csv_files:
        frames.append(pd.read_csv(f, parse_dates=[date_col]))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _yearly_cumulative_from_obs(csv_files):
    """Return a yearly cumulative series from CSVs with an observation datetime column."""
    data = _load_csvs(csv_files, "observationdate")
    if data.empty:
        return pd.Series(dtype="int64")
    years = data["observationdate"].dt.year
    yearly = years.groupby(years).size().sort_index()
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

