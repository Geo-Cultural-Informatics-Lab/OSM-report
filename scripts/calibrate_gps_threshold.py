"""
GPS Road Quality Threshold Calibration

Computes the nodes_per_km threshold above which roads are likely GPS-traced,
by comparing the nodes/km distribution of all roads vs roads tagged source=GPS.

Algorithm:
  1. Query road geometries for all highways and GPS-tagged highways in a small
     calibration bbox (default: central Bangkok).
  2. Compute nodes_per_km for every road in each set.
  3. Build two histograms over the same log-spaced bins.
  4. Find the smallest nodes/km bin where GPS road density is >= 2x all-road density,
     consistently for at least 3 consecutive bins.
  5. Save the threshold to report/config/gps_threshold.json.

Usage (from the report/ directory):
    python scripts/calibrate_gps_threshold.py
    python scripts/calibrate_gps_threshold.py --bbox "100.3,13.5,100.8,14.0" --year 2024
    python scripts/calibrate_gps_threshold.py --bins 50 --ratio 2.0 --min-run 3
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import requests

# ---------------------------------------------------------------------------
# Bootstrap: make sure the geometric_complexity package is importable
# ---------------------------------------------------------------------------
REPORT_DIR = Path(__file__).resolve().parent.parent
OSM_ROOT   = REPORT_DIR.parent
sys.path.insert(0, str(REPORT_DIR))
sys.path.insert(1, str(OSM_ROOT / "geometric_complexity"))

try:
    from geometric_complexity.core.ohsome_client import OhsomeClient
    from geometric_complexity.core.metrics import extract_comprehensive_metrics
except ImportError:
    # Flat import when running from within the geometric_complexity tree
    try:
        _gc_core = OSM_ROOT / "geometric_complexity" / "core"
        sys.path.insert(2, str(_gc_core.parent))
        from geometric_complexity.core.ohsome_client import OhsomeClient
        from geometric_complexity.core.metrics import extract_comprehensive_metrics
    except ImportError as e:
        sys.exit(
            f"Cannot import geometric_complexity: {e}\n"
            "Run: pip install -e ../geometric_complexity"
        )


DEFAULT_BBOX      = "100.4,13.6,100.7,13.9"   # Central Bangkok
DEFAULT_TIMESTAMP = "2024-01-01"
DEFAULT_BINS      = 50
DEFAULT_RATIO     = 2.0
DEFAULT_MIN_RUN   = 3   # consecutive bins where ratio >= threshold


def compute_nodes_per_km(features: list) -> np.ndarray:
    """Extract nodes_per_km for each road feature returned by Ohsome geometry API."""
    if not features:
        return np.array([])

    metrics = extract_comprehensive_metrics(features, bbox="")
    node_counts    = metrics.get("node_counts",    np.array([]))
    road_lengths   = metrics.get("road_lengths",   np.array([]))

    valid = road_lengths > 0
    road_lengths_km = np.where(valid, road_lengths / 1000.0, 1.0)
    npk = np.where(valid, node_counts / road_lengths_km, 0.0)
    return npk[valid]   # keep only roads with valid length


def find_gps_threshold(
    npk_all: np.ndarray,
    npk_gps: np.ndarray,
    bins:    int   = DEFAULT_BINS,
    ratio:   float = DEFAULT_RATIO,
    min_run: int   = DEFAULT_MIN_RUN,
) -> float:
    """
    Find the smallest nodes/km value above which GPS roads are `ratio`× more
    common (in density) than all roads, for at least `min_run` consecutive bins.

    Returns threshold float, or np.nan if no clear threshold found.
    """
    if len(npk_all) == 0 or len(npk_gps) == 0:
        print("WARNING: empty array(s) — cannot compute threshold")
        return float("nan")

    # Log-spaced bins (GPS devices produce characteristic interval patterns)
    min_val = max(min(npk_all.min(), npk_gps.min()), 0.01)
    max_val = max(npk_all.max(), npk_gps.max()) * 1.01
    bin_edges = np.logspace(np.log10(min_val), np.log10(max_val), bins + 1)

    hist_all, _ = np.histogram(npk_all, bins=bin_edges)
    hist_gps, _ = np.histogram(npk_gps, bins=bin_edges)

    # Density = proportion of each group falling in each bin
    density_all = hist_all / len(npk_all) if len(npk_all) > 0 else hist_all * 0.0
    density_gps = hist_gps / len(npk_gps) if len(npk_gps) > 0 else hist_gps * 0.0

    # Ratio; skip bins where all-roads density is 0
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio_arr = np.where(density_all > 0, density_gps / density_all, 0.0)

    print(f"\nnodes/km histogram ({bins} log-spaced bins from {min_val:.1f} to {max_val:.1f}):")
    print(f"  {'Bin centre':>12}  {'all density':>12}  {'gps density':>12}  {'ratio':>8}")
    for i in range(bins):
        centre = np.sqrt(bin_edges[i] * bin_edges[i + 1])
        if hist_all[i] > 0 or hist_gps[i] > 0:
            print(f"  {centre:12.2f}  {density_all[i]:12.6f}  {density_gps[i]:12.6f}  {ratio_arr[i]:8.2f}")

    # Find first bin in a run of min_run consecutive bins with ratio >= threshold
    above = ratio_arr >= ratio
    run_start = None
    run_len   = 0
    for i, flag in enumerate(above):
        if flag:
            if run_len == 0:
                run_start = i
            run_len += 1
            if run_len >= min_run:
                threshold = bin_edges[run_start]
                print(f"\n→ GPS threshold found at bin {run_start}: "
                      f"nodes_per_km >= {threshold:.2f}")
                return float(threshold)
        else:
            run_start = None
            run_len   = 0

    print("\nWARNING: No clear GPS threshold found (ratio never reached consistently)")
    return float("nan")


def main():
    parser = argparse.ArgumentParser(description="Calibrate GPS road quality threshold")
    parser.add_argument("--bbox",      default=DEFAULT_BBOX,
                        help=f"Calibration bounding box (default: {DEFAULT_BBOX})")
    parser.add_argument("--year",      default=DEFAULT_TIMESTAMP,
                        help=f"Timestamp for calibration (default: {DEFAULT_TIMESTAMP})")
    parser.add_argument("--bins",      type=int,   default=DEFAULT_BINS)
    parser.add_argument("--ratio",     type=float, default=DEFAULT_RATIO)
    parser.add_argument("--min-run",   type=int,   default=DEFAULT_MIN_RUN)
    parser.add_argument("--timeout",   type=int,   default=120)
    parser.add_argument("--output",    default=str(REPORT_DIR / "config" / "gps_threshold.json"))
    args = parser.parse_args()

    timestamp = args.year if "-" in args.year else f"{args.year}-01-01"

    print(f"GPS Threshold Calibration")
    print(f"  bbox:      {args.bbox}")
    print(f"  timestamp: {timestamp}")
    print(f"  bins:      {args.bins}  ratio >= {args.ratio}  min_run: {args.min_run}")

    client = OhsomeClient(timeout=args.timeout)

    print("\nFetching ALL highway geometries…")
    all_data = client.query_geometry(args.bbox, "type:way and highway=*", timestamp)
    if all_data is None:
        sys.exit("ERROR: Failed to fetch all highway geometries")
    all_features = all_data.get("features", [])
    print(f"  → {len(all_features):,} highway features")

    print("\nFetching GPS highway geometries…")
    gps_data = client.query_geometry(args.bbox, "type:way and highway=* and source=GPS", timestamp)
    if gps_data is None:
        sys.exit("ERROR: Failed to fetch GPS highway geometries")
    gps_features = gps_data.get("features", [])
    print(f"  → {len(gps_features):,} GPS highway features")

    if not gps_features:
        print("\nWARNING: No GPS-tagged highways in calibration area.")
        print("Consider choosing a different bbox or use a larger region.")
        threshold = float("nan")
    else:
        npk_all = compute_nodes_per_km(all_features)
        npk_gps = compute_nodes_per_km(gps_features)
        print(f"\nAll roads: {len(npk_all):,} valid, "
              f"median nodes/km = {np.median(npk_all):.1f}")
        print(f"GPS roads: {len(npk_gps):,} valid, "
              f"median nodes/km = {np.median(npk_gps):.1f}")

        threshold = find_gps_threshold(npk_all, npk_gps, args.bins, args.ratio, args.min_run)

    result = {
        "nodes_per_km_threshold": threshold if not np.isnan(threshold) else None,
        "calibration_bbox":       args.bbox,
        "calibration_timestamp":  timestamp,
        "histogram_bins":         args.bins,
        "ratio_threshold":        args.ratio,
        "min_consecutive_bins":   args.min_run,
        "all_feature_count":      len(all_features),
        "gps_feature_count":      len(gps_features),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved to: {output_path}")
    if result["nodes_per_km_threshold"] is not None:
        print(f"GPS quality threshold: {result['nodes_per_km_threshold']:.2f} nodes/km")
    else:
        print("GPS quality threshold: NOT DETERMINED (check warnings above)")


if __name__ == "__main__":
    main()
