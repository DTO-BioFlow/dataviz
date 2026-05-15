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


def aggregate_cumulative_values(df):
    """
    Given a dataframe with rows for each node (id, label, parent) and 'value'
    that currently contains counts only for the original leaves, compute the
    cumulative value for each node as the sum of all descendant leaf counts.
    This updates the 'value' column so parent nodes reflect the sum of
    their children (which Plotly expects when using branchvalues='total').
    """
    # Build map of id -> value
    val_map = {row['id']: float(row['value']) for _, row in df.iterrows()}

    # Ensure every node has an entry (parents might be missing until add_missing_parents)
    for _, row in df.iterrows():
        val_map.setdefault(row['id'], 0.0)

    # Sort ids by depth (deeper nodes first) so we can accumulate up to parents
    ids_sorted = sorted(val_map.keys(), key=lambda s: s.count('|'), reverse=True)
    for node_id in ids_sorted:
        if '|' in node_id:
            parent = node_id.rsplit('|', 1)[0]
        else:
            parent = ""
        if parent:
            val_map[parent] = val_map.get(parent, 0.0) + val_map.get(node_id, 0.0)

    # Apply back to dataframe
    df = df.copy()
    df['value'] = df['id'].map(lambda i: val_map.get(i, 0.0))
    return df



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

    # Define sources: two folders and one ETN file
    script_dir = Path(__file__).resolve().parent
    sources = [
        {"path": script_dir / ".." / "data" / "worms" / "worms_call1_data", "name": "call1", "kind": "folder"},
        {"path": script_dir / ".." / "data" / "worms" / "worms_sensor_data", "name": "sensor", "kind": "folder"},
        {"path": script_dir / ".." / "data" / "worms" / "etn.json", "name": "etn", "kind": "file"},
    ]

    output_base_dir = (script_dir / ".." / "plots" / "sunburst").resolve()
    output_base_dir.mkdir(parents=True, exist_ok=True)

    all_records = []

    for source in sources:
        input_path = source["path"]
        name = source["name"]
        kind = source["kind"]

        records = []

        if kind == "folder":
            if not input_path.exists():
                print(f"Warning: folder not found for source '{name}': {input_path}")
                continue
            for json_file in sorted(input_path.glob("*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        taxonomy_data = json.load(f)
                        if isinstance(taxonomy_data, list):
                            records.extend(taxonomy_data)
                        else:
                            print(f"Skipping {json_file} - expected list of records")

                        # Individual sunburst per file (optional)
                        df_sb = build_sunburst_df(taxonomy_data)
                        df_sb = add_missing_parents(df_sb)
                        df_sb = aggregate_cumulative_values(df_sb)
                        df_sb = remove_zero_branches(df_sb)
                        colors = assign_nested_colors(df_sb)
                        fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
                        fig.update_traces(marker=dict(colors=colors))
                        fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
                        out_dir = output_base_dir / name
                        out_dir.mkdir(parents=True, exist_ok=True)
                        output_file = out_dir / f"{json_file.stem}.html"
                        fig.write_html(output_file, include_plotlyjs='cdn', full_html=True)
                        print(f"Saved individual sunburst: {output_file}")

                except Exception as e:
                    print(f"Failed to read {json_file}: {e}")

        else:  # single file
            if not input_path.exists():
                print(f"Warning: file not found for source '{name}': {input_path}")
                continue
            try:
                with open(input_path, "r", encoding="utf-8") as f:
                    taxonomy_data = json.load(f)
                    if isinstance(taxonomy_data, list):
                        records.extend(taxonomy_data)
                    else:
                        print(f"Unexpected content in {input_path} - expected list of records")
            except Exception as e:
                print(f"Failed to read {input_path}: {e}")
                continue

        if not records:
            print(f"No taxonomy records found for source '{name}', skipping output.")
            continue

        # Save merged sunburst for this source
        merged_data = merge_taxonomies(records)
        df_sb = build_sunburst_df(merged_data)
        df_sb = add_missing_parents(df_sb)
        df_sb = aggregate_cumulative_values(df_sb)
        df_sb = remove_zero_branches(df_sb)
        colors = assign_nested_colors(df_sb)
        fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
        fig.update_traces(marker=dict(colors=colors))
        fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
        merged_file = output_base_dir / f"{name}.html"
        fig.write_html(merged_file, include_plotlyjs='cdn', full_html=True)
        print(f"Saved merged sunburst for {name}: {merged_file}")

        all_records.extend(records)

    # Create combined sunburst of all sources
    if all_records:
        merged_all = merge_taxonomies(all_records)
        df_sb = build_sunburst_df(merged_all)
        df_sb = add_missing_parents(df_sb)
        df_sb = aggregate_cumulative_values(df_sb)
        df_sb = remove_zero_branches(df_sb)
        colors = assign_nested_colors(df_sb)
        fig = px.sunburst(df_sb, ids='id', names='label', parents='parent', values='value', branchvalues='total')
        fig.update_traces(marker=dict(colors=colors))
        fig.update_layout(margin=dict(t=10, l=10, r=10, b=10))
        combined_file = output_base_dir / "all_data.html"
        fig.write_html(combined_file, include_plotlyjs='cdn', full_html=True)
        print(f"Saved merged sunburst for all data: {combined_file}")
