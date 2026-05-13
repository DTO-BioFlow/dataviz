from collections import defaultdict
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import json
from pathlib import Path
from collections import defaultdict
from matplotlib import colors as mcolors


def build_sunburst_df(taxonomy_data):
    rows = []
    for record in taxonomy_data:

        # Trim taxonomy at first None
        path = []
        for val in record["taxonomy"]:
            if val is None:
                break
            path.append(val)

        count = record.get("count", 0)

        # Build nodes only for actual known taxonomy levels
        for i, name in enumerate(path):
            node_id = "|".join(path[:i+1])
            parent = "" if i == 0 else "|".join(path[:i])
            value = count if i == len(path) - 1 else 0

            rows.append({
                "id": node_id,
                "label": name,
                "parent": parent,
                "value": value
            })

    df = pd.DataFrame(rows)
    df = df.groupby(["id", "label", "parent"], as_index=False)["value"].sum()
    return df


def remove_zero_branches(df):
    leaves = df[df["value"] > 0]
    valid_ids = set()
    for leaf_id in leaves["id"]:
        parts = leaf_id.split("|")
        for i in range(1, len(parts)+1):
            valid_ids.add("|".join(parts[:i]))
    return df[df["id"].isin(valid_ids)].reset_index(drop=True)


def add_missing_parents(df):
    all_ids = set(df['id'])
    all_parents = set(df['parent']) - {""}
    missing_parents = all_parents - all_ids
    rows = []
    for parent in missing_parents:
        parts = parent.split("|")
        label = parts[-1]
        parent_id = "" if len(parts) == 1 else "|".join(parts[:-1])
        rows.append({"id": parent, "label": label, "parent": parent_id, "value": 0})
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    return df


def merge_taxonomies(all_taxonomies):
    merged = defaultdict(int)

    for record in all_taxonomies:
        key = []
        for val in record["taxonomy"]:
            if val is None:
                break
            key.append(val)

        merged[tuple(key)] += record.get("count", 0)

    return [{"taxonomy": list(k), "count": v} for k, v in merged.items()]



def assign_nested_colors(df):
    """
    Assign all nodes a blue color,
    with deeper levels getting progressively lighter.
    """

    base_blue = "#033f69"  # Plotly's default blue
    rgb_base = mcolors.to_rgb(base_blue)

    color_map = {}

    for idx, row in df.iterrows():
        parts = row['id'].split('|')
        depth = len(parts) - 1  # 0 = root, deeper = higher number

        # Lighten the blue depending on depth
        # factor < 1 = darker ; factor > 1 = lighter
        factor = 1 + depth * 0.18
        shaded = [min(1, c * factor) for c in rgb_base]

        # Convert to RGB string
        color_map[row['id']] = f"rgb({int(shaded[0]*255)}, {int(shaded[1]*255)}, {int(shaded[2]*255)})"

    # Return colors matching df order
    return [color_map[i] for i in df['id']]


if __name__ == "__main__":

    script_dir = Path(__file__).resolve().parent

    # Input folders
    sources = [
        {"path": script_dir / ".." / "data" / "worms" / "worms_call1_data", "name": "call1", "kind": "folder"},
        {"path": script_dir / ".." / "data" / "worms" / "worms_sensor_data", "name": "sensor", "kind": "folder"},
        {"path": script_dir / ".." / "data" / "worms" / "etn.json", "name": "etn", "kind": "file"},
    ]

    output_base_dir = (script_dir / ".." / "plots" / "sunburst").resolve()
    output_base_dir.mkdir(parents=True, exist_ok=True)

    all_data_combined = []

    for source in sources:
        input_path = source["path"]
        name = source["name"]
        kind = source["kind"]
        folder_data = []

        if kind == "folder":
            output_dir = output_base_dir / name
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process each JSON file
            for json_file in input_path.glob("*.json"):
                with open(json_file, "r") as f:
                    taxonomy_data = json.load(f)
                    folder_data.extend(taxonomy_data)

                # Individual sunburst
                df_sb = build_sunburst_df(taxonomy_data)
                df_sb = remove_zero_branches(df_sb)
                df_sb = add_missing_parents(df_sb)
                fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value')
                fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
                fig.update_traces(marker=dict(colors=colors))
                fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
                output_file = output_dir / f"{json_file.stem}.html"
                fig.write_html(output_file)
                print(f"Saved individual sunburst: {output_file}")

        else:
            with open(input_path, "r") as f:
                taxonomy_data = json.load(f)
                folder_data.extend(taxonomy_data)

            df_sb = build_sunburst_df(taxonomy_data)
            df_sb = remove_zero_branches(df_sb)
            fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value')
            colors = assign_nested_colors(df_sb)
            fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
            fig.update_traces(marker=dict(colors=colors))
            fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
            output_file = output_base_dir / f"{name}.html"
            fig.write_html(output_file)
            print(f"Saved individual sunburst: {output_file}")

        # Merge all JSONs in the folder; for single-file sources, the standalone output is already the merged output.
        if kind == "folder":
            merged_data = merge_taxonomies(folder_data)
            df_sb = build_sunburst_df(merged_data)
            fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value')
            df_sb = add_missing_parents(df_sb)
            colors = assign_nested_colors(df_sb)
            fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
            fig.update_traces(marker=dict(colors=colors))
            fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
            merged_file = output_base_dir / f"{name}.html"  # call1.html or sensor.html
            fig.write_html(merged_file)
            print(f"Saved merged sunburst for {name}: {merged_file}")

        all_data_combined.extend(folder_data)

    # Merge all data together
    fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value')
    df_sb = build_sunburst_df(merged_all)
    df_sb = remove_zero_branches(df_sb)
    df_sb = add_missing_parents(df_sb)
    colors = assign_nested_colors(df_sb)
    fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
    fig.update_traces(marker=dict(colors=colors))
    fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
    combined_file = output_base_dir / "all_data.html"
    fig.write_html(combined_file)
    print(f"Saved merged sunburst for all data: {combined_file}")