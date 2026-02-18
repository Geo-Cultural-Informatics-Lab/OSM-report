"""
Find missing/failed data points in OSM report CSVs and prepare fill-in runs.

A row is considered failed if:
  - entity_count == 0, OR
  - unique_tags_count == 0

For each failed row this script:
  1. Deletes cached grid files for that (country, year, entity) combination
     so the next run re-fetches from the API instead of reusing the bad result.
  2. Prints ready-to-run fill-in commands grouped by country.

Usage (run from the OSM-report directory):
    python scripts/find_and_fix_missing.py
    python scripts/find_and_fix_missing.py --results results --cache cache --dry-run
"""

import argparse
import glob
import os
import re
from collections import defaultdict
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    raise SystemExit("pandas is required: pip install pandas")


def parse_args():
    parser = argparse.ArgumentParser(description="Find and fix missing OSM report data")
    parser.add_argument("--results", default="results", help="Results directory (default: results)")
    parser.add_argument("--cache", default="cache", help="Cache directory (default: cache)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting",
    )
    return parser.parse_args()


def find_failed_rows(results_dir: Path):
    """
    Scan all CSVs in results_dir and return failed rows.

    Returns dict: {csv_file: DataFrame of failed rows}
    """
    failed = {}
    csv_files = sorted(results_dir.glob("*.csv"))

    for csv_path in csv_files:
        name = csv_path.name
        # Skip detail/tag files — they don't have entity_count
        if "detail" in name or name.endswith("_tags.csv"):
            continue

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"  [WARN] Could not read {name}: {e}")
            continue

        if df.empty:
            continue

        # Identify failed rows
        mask = pd.Series([False] * len(df), index=df.index)
        if "entity_count" in df.columns:
            mask |= df["entity_count"].fillna(0) == 0
        if "unique_tags_count" in df.columns:
            mask |= df["unique_tags_count"].fillna(0) == 0

        failed_df = df[mask]
        if not failed_df.empty:
            failed[csv_path] = failed_df

    return failed


def delete_cache_files(cache_dir: Path, iso: str, year: int, entity: str,
                       province_code: str = None, dry_run: bool = False) -> int:
    """
    Delete cache files matching the given (iso, year, entity) combination.

    Cache file naming convention:
      Country-level:  {ISO}_grid_{row}_{col}_{year}_{entity}_{chunk}km_combined.json
      Province-level: {ISO}_{PROV}_grid_{row}_{col}_{year}_{entity}_{chunk}km_combined.json

    Returns number of files deleted (or that would be deleted).
    """
    if province_code:
        # Province cache key format: {ISO}_{PROVINCE_CODE}
        prefix = f"{iso}_{province_code}_"
    else:
        prefix = f"{iso}_"

    pattern = str(cache_dir / f"{prefix}grid_*_{year}_{entity}_*km_combined.json")
    matches = glob.glob(pattern)

    count = 0
    for fpath in matches:
        if dry_run:
            print(f"    [DRY-RUN] Would delete: {os.path.basename(fpath)}")
        else:
            try:
                os.remove(fpath)
                count += 1
            except OSError as e:
                print(f"    [ERROR] Could not delete {fpath}: {e}")
    if not dry_run:
        return count
    return len(matches)


def build_fill_commands(country_jobs: dict) -> list:
    """
    Build fill-in commands grouped by country.

    country_jobs: {country: {'years': set, 'entities': set, 'is_province': bool,
                              'province_years': {entity: set_of_years}}}
    Returns list of command strings.
    """
    commands = []
    for country, info in sorted(country_jobs.items()):
        years = sorted(info["years"])
        entities = sorted(info["entities"])
        is_province = info.get("is_province", False)

        years_arg = " ".join(str(y) for y in years)
        if len(years) == 1:
            years_str = str(years[0])
        elif years == list(range(years[0], years[-1] + 1)):
            years_str = f"{years[0]}-{years[-1]}"
        else:
            years_str = f'"{years_arg}"'

        entities_str = " ".join(entities)
        province_flag = " --province-level" if is_province else ""

        cmd = (
            f"python main.py --countries {country} --years {years_str} "
            f"--entities {entities_str}{province_flag} --api-timeout 60"
        )
        commands.append((country, is_province, cmd))

    return commands


def main():
    args = parse_args()
    results_dir = Path(args.results)
    cache_dir = Path(args.cache)

    if not results_dir.exists():
        raise SystemExit(f"Results directory not found: {results_dir}")
    if not cache_dir.exists():
        print(f"[WARN] Cache directory not found: {cache_dir} — skipping cache deletion")

    print("=" * 60)
    print("OSM Report — Missing Data Scanner & Cache Cleaner")
    print("=" * 60)
    if args.dry_run:
        print("[DRY-RUN MODE] No files will be deleted\n")

    # --- Find failed rows ---
    print(f"\nScanning {results_dir} for failed rows...\n")
    all_failed = find_failed_rows(results_dir)

    if not all_failed:
        print("No failed rows found! All data looks complete.")
        return

    # Group jobs by country (separately for country-level and province-level)
    country_jobs = defaultdict(lambda: {"years": set(), "entities": set(), "is_province": False})
    province_jobs = defaultdict(lambda: {"years": set(), "entities": set(), "is_province": True})

    total_deleted = 0

    for csv_path, failed_df in all_failed.items():
        is_province = "province_code" in failed_df.columns
        print(f"{'─'*50}")
        print(f"FILE: {csv_path.name}  ({len(failed_df)} failed rows)")

        for _, row in failed_df.iterrows():
            country = str(row["country"])
            year = int(row["year"])
            entity = str(row["entity"])
            province_code = str(row.get("province_code", "")) if is_province else None
            province_name = str(row.get("province_name", "")) if is_province else ""

            if is_province:
                label = f"  {country} [{province_code}] {province_name}  {year}  {entity}"
            else:
                label = f"  {country}  {year}  {entity}"
            print(label)

            # Delete bad cache files
            if cache_dir.exists():
                deleted = delete_cache_files(
                    cache_dir, country, year, entity,
                    province_code=province_code,
                    dry_run=args.dry_run
                )
                total_deleted += deleted
                if deleted and not args.dry_run:
                    print(f"    → Deleted {deleted} cache file(s)")

            # Record for fill-in commands
            if is_province:
                province_jobs[country]["years"].add(year)
                province_jobs[country]["entities"].add(entity)
                province_jobs[country]["is_province"] = True
            else:
                country_jobs[country]["years"].add(year)
                country_jobs[country]["entities"].add(entity)

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"[DRY-RUN] Would delete {total_deleted} cache file(s) total")
    else:
        print(f"Deleted {total_deleted} cache file(s) total")

    # --- Print fill-in commands ---
    print(f"\n{'='*60}")
    print("FILL-IN COMMANDS")
    print(f"{'='*60}")
    print("Run these from the OSM-report directory:\n")

    all_jobs = {**{f"_cl_{k}": v for k, v in country_jobs.items()},
                **{f"_pr_{k}": v for k, v in province_jobs.items()}}

    if country_jobs:
        print("# Country-level reruns:")
        for country, info in sorted(country_jobs.items()):
            years = sorted(info["years"])
            entities = sorted(info["entities"])
            if years == list(range(years[0], years[-1] + 1)):
                years_str = f"{years[0]}-{years[-1]}"
            elif len(years) == 1:
                years_str = str(years[0])
            else:
                years_str = '"' + " ".join(str(y) for y in years) + '"'
            entities_str = " ".join(entities)
            print(f"python main.py --countries {country} --years {years_str} "
                  f"--entities {entities_str} --api-timeout 60")
        print()

    if province_jobs:
        print("# Province-level reruns:")
        for country, info in sorted(province_jobs.items()):
            years = sorted(info["years"])
            entities = sorted(info["entities"])
            if years == list(range(years[0], years[-1] + 1)):
                years_str = f"{years[0]}-{years[-1]}"
            elif len(years) == 1:
                years_str = str(years[0])
            else:
                years_str = '"' + " ".join(str(y) for y in years) + '"'
            entities_str = " ".join(entities)
            print(f"python main.py --countries {country} --years {years_str} "
                  f"--entities {entities_str} --province-level --api-timeout 60")
        print()

    print("Tip: run each command in its own tmux session, e.g.:")
    print("  tmux new -s fill_TH")
    print("  python main.py --countries TH ...")


if __name__ == "__main__":
    main()
