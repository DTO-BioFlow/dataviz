from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


def read_csv_files(csv_files):
    """Read and combine CSV files into a single DataFrame, sorted by
    observationdate."""
    all_data = []
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=['observationdate'])
        all_data.append(df)
    if all_data:
        data = pd.concat(all_data, ignore_index=True)
        return data.sort_values('observationdate')
    return pd.DataFrame(columns=['observationdate'])


def plot_timeline_single(data, store, color='tab:blue', label='Data'):
    """Plot a single timeline with filled area under the curve."""
    if data.empty:
        print(f"No data to plot for {label}.")
        return
    y = np.arange(len(data))
    plt.figure(figsize=(12, 6))
    plt.plot(data['observationdate'], y, color=color, label=label)
    plt.fill_between(data['observationdate'], 0, y, color=color, alpha=0.3)
    plt.xlabel('Observation Date')
    plt.ylabel('Observation Index')
    plt.title('Cumulative Timeline')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(store)
    plt.close()


def plot_timeline_combined(data1, data2, store,
                           color1='tab:blue',
                           color2='tab:orange',
                           label1='CSV Set 1',
                           label2='CSV Set 2',
                           log=False):

    plt.figure(figsize=(12, 6))

    # Count observations per date
    s1 = data1.groupby('observationdate').size()
    s2 = data2.groupby('observationdate').size()

    # Align on all shared dates
    all_dates = s1.index.union(s2.index)
    s1 = s1.reindex(all_dates, fill_value=0)
    s2 = s2.reindex(all_dates, fill_value=0)

    # Cumulative series
    c1 = s1.cumsum()
    c2 = s2.cumsum()
    c2_stacked = c1 + c2

    # ---- Helper to avoid plotting zero-lines ----
    def first_nonzero_index(series):
        nz = np.flatnonzero(series.values > 0)
        return nz[0] if len(nz) else None

    idx1 = first_nonzero_index(c1)
    idx2 = first_nonzero_index(c2)

    # Plot first dataset (only after first nonzero)
    if idx1 is not None:
        plt.plot(all_dates[idx1:], c1[idx1:], color=color1, label=label1)
        plt.fill_between(all_dates, 0, c1, color=color1, alpha=0.3)

    # Plot second dataset (only after its first nonzero)
    if idx2 is not None:
        plt.plot(all_dates[idx2:], c2_stacked[idx2:], color=color2, label=label2)
        plt.fill_between(all_dates, c1, c2_stacked, color=color2, alpha=0.3)

    if log:
        plt.yscale('log')
    plt.xlabel('Observation Date')
    plt.ylabel('Cumulative Count (stacked)')
    plt.title('Cumulative Timeline')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(store)
    plt.close()


def plot_timeline_etn(csv_dir):
    """Plot timeline from ETN temporal count CSVs.

    Gets all CSVs that contain 'temporal_count' in the name.
    Each CSV has columns: date, count
    Creates a timeline plot from ETN detection datasets.
    """
    csv_dir = Path(csv_dir)
    csv_files = sorted(csv_dir.glob("*temporal_count.csv"))

    if not csv_files:
        print(f"No temporal_count CSV files found in {csv_dir}")
        return

    # Read and combine all temporal count CSVs
    all_data = []
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=['date'])
        all_data.append(df)

    data = pd.concat(all_data, ignore_index=True)

    # Group by date and sum counts
    grouped = data.groupby('date')['count'].sum().sort_index()

    # Create cumulative counts
    cumulative = grouped.cumsum()

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(cumulative.index, cumulative.values, color='tab:green', label='ETN Detections')
    plt.fill_between(cumulative.index, 0, cumulative.values, color='tab:green', alpha=0.3)
    plt.xlabel('Date')
    plt.ylabel('Cumulative Count')
    plt.title('ETN Temporal Timeline')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    out_dir = Path("../plots")
    out_dir.mkdir(parents=True, exist_ok=True)
    store = out_dir / 'timeline_etn.png'
    plt.savefig(store)
    plt.close()
    print(f"Saved ETN timeline plot to {store}")

if __name__ == "__main__":
    # Directories
    csv_dir1 = Path("../data/1.harvest_wp2_observation_data")
    csv_dir2 = Path("../data/2.harvest_wp3_sensor_observation_data")
    csv_dir_etn = Path("../data/3.harvest_ETN")

    csv_files1 = sorted(csv_dir1.glob("*.csv"))
    csv_files2 = sorted(csv_dir2.glob("*.csv"))

    out_dir = Path("../plots")

    # Read CSVs
    data_obs = read_csv_files(csv_files1)
    data_sen = read_csv_files(csv_files2)

    # Plot first CSV set
    name_obs = "observations"
    store_obs = out_dir / f'timeline_{name_obs}.png'

    plot_timeline_single(data_obs,
                         store=store_obs,
                         color='tab:blue',
                         label=name_obs)

    # Plot second CSV set
    name_sen = "sensor_observations"
    store_sen = out_dir / f'timeline_{name_sen}.png'

    plot_timeline_single(data_sen,
                         store=store_sen,
                         color='tab:orange',
                         label=name_sen)

    # Plot combined stacked timeline
    name_all = "all_combined"
    store_all = out_dir / f'timeline_{name_all}.png'

    plot_timeline_combined(data_sen,
                           data_obs,
                           store=store_all,
                           label1=name_sen,
                           label2=name_obs,
                           log=False)

    store_all_log = out_dir / f'timeline_{name_all}_log.png'
    plot_timeline_combined(data_sen,
                           data_obs,
                           store=store_all_log,
                           label1=name_sen,
                           label2=name_obs,
                           log=True)

    # Plot ETN timeline
    plot_timeline_etn(csv_dir_etn)

