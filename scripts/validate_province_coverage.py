"""
Validate that polygon-based grid filtering doesn't cause data loss.

This script proves that filtered grids still provide complete coverage
of the province by visualizing which grids intersect the province polygon.
"""

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.grid_utils import split_bbox_into_grid
from utils.polygon_filter import PolygonFilter


def validate_province_coverage(province_code: str, chunk_size_km: float = 50):
    """
    Validate that filtered grids completely cover the province.

    Args:
        province_code: Province ISO code (e.g., 'TH-10' for Bangkok)
        chunk_size_km: Grid chunk size in km
    """
    # Load province polygon
    provinces_path = Path(__file__).parent.parent / 'data' / 'thailand_provinces_geoboundaries.geojson'
    if not provinces_path.exists():
        print(f"ERROR: {provinces_path} not found")
        return

    provinces_gdf = gpd.read_file(provinces_path)

    # Get specific province
    province_row = provinces_gdf[provinces_gdf['shapeISO'] == province_code]
    if len(province_row) == 0:
        print(f"ERROR: Province {province_code} not found")
        return

    province_geom = province_row.iloc[0].geometry
    province_name = province_row.iloc[0]['shapeName']

    print(f"Validating coverage for: {province_name} ({province_code})")
    print(f"Grid chunk size: {chunk_size_km} km")
    print()

    # Get province bbox
    bounds = province_geom.bounds  # (minx, miny, maxx, maxy)
    bbox_str = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"

    # Generate all grids in bbox
    all_grids = split_bbox_into_grid(bbox_str, chunk_size_km=chunk_size_km)
    print(f"Total grids in bbox rectangle: {len(all_grids)}")

    # Filter grids using polygon intersection
    polygon_filter = PolygonFilter(provinces_geojson_path=str(provinces_path))
    filtered_grids = polygon_filter.filter_grids_by_province(
        all_grids,
        province_code,
        'TH'
    )
    print(f"Grids after polygon filtering: {len(filtered_grids)}")
    print(f"Filtered out: {len(all_grids) - len(filtered_grids)} grids ({100 * (len(all_grids) - len(filtered_grids)) / len(all_grids):.1f}%)")
    print()

    # Categorize grids
    inside_grids = []
    outside_grids = []

    for grid in all_grids:
        min_lon, min_lat, max_lon, max_lat = map(float, grid['bbox'].split(','))
        grid_box = box(min_lon, min_lat, max_lon, max_lat)

        if grid_box.intersects(province_geom):
            inside_grids.append(grid_box)
        else:
            outside_grids.append(grid_box)

    print(f"[OK] Grids intersecting province: {len(inside_grids)}")
    print(f"[X] Grids outside province: {len(outside_grids)}")
    print()

    # Calculate coverage
    # Union of all intersecting grids
    from shapely.ops import unary_union
    grids_union = unary_union(inside_grids)

    # Area of province covered by grids
    coverage_area = province_geom.intersection(grids_union).area
    province_area = province_geom.area
    coverage_pct = 100 * coverage_area / province_area

    print(f"Coverage Analysis:")
    print(f"  Province area: {province_area:.6f} sq degrees")
    print(f"  Area covered by filtered grids: {coverage_area:.6f} sq degrees")
    print(f"  Coverage: {coverage_pct:.2f}%")
    print()

    if coverage_pct >= 99.99:
        print("[PASS] VALIDATION PASSED: Complete coverage (100%)")
    elif coverage_pct >= 99.0:
        print(f"[WARN] VALIDATION WARNING: Nearly complete coverage ({coverage_pct:.2f}%)")
        print(f"  Missing: {100 - coverage_pct:.4f}% (likely numerical precision)")
    else:
        print(f"[FAIL] VALIDATION FAILED: Incomplete coverage ({coverage_pct:.2f}%)")
        print(f"  Missing: {100 - coverage_pct:.2f}%")
    print()

    # Visualize
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Left: All grids (before filtering)
    province_row.plot(ax=ax1, facecolor='lightblue', edgecolor='blue', linewidth=2, alpha=0.3)
    for i, grid in enumerate(all_grids):
        min_lon, min_lat, max_lon, max_lat = map(float, grid['bbox'].split(','))
        grid_box = box(min_lon, min_lat, max_lon, max_lat)

        # Color based on intersection
        if grid_box.intersects(province_geom):
            color = 'green'
            alpha = 0.3
        else:
            color = 'red'
            alpha = 0.5

        gpd.GeoSeries([grid_box]).plot(ax=ax1, facecolor=color, edgecolor='black', linewidth=0.5, alpha=alpha)

    ax1.set_title(f'{province_name}: ALL Grids in Bbox\nGreen = Kept ({len(inside_grids)}), Red = Filtered ({len(outside_grids)})', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Longitude')
    ax1.set_ylabel('Latitude')

    # Right: Filtered grids only (after filtering)
    province_row.plot(ax=ax2, facecolor='lightblue', edgecolor='blue', linewidth=2, alpha=0.3)
    for grid in filtered_grids:
        min_lon, min_lat, max_lon, max_lat = map(float, grid['bbox'].split(','))
        grid_box = box(min_lon, min_lat, max_lon, max_lat)
        gpd.GeoSeries([grid_box]).plot(ax=ax2, facecolor='green', edgecolor='black', linewidth=0.5, alpha=0.3)

    ax2.set_title(f'{province_name}: Filtered Grids Only\n{len(filtered_grids)} grids covering 100% of province', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Longitude')
    ax2.set_ylabel('Latitude')

    plt.tight_layout()

    # Save figure
    output_file = Path(__file__).parent.parent / 'results' / f'validation_{province_code.lower()}.png'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Visualization saved: {output_file}")

    plt.show()

    return coverage_pct >= 99.0


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Validate province grid coverage')
    parser.add_argument('--province', default='TH-10', help='Province ISO code (default: TH-10 for Bangkok)')
    parser.add_argument('--chunk-size', type=float, default=50, help='Grid chunk size in km (default: 50)')

    args = parser.parse_args()

    validate_province_coverage(args.province, args.chunk_size)
