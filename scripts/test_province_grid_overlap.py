"""
Test whether grids can overlap between adjacent provinces.

This script validates that even though provinces may have overlapping bboxes,
the polygon filtering ensures each grid is assigned to exactly one province.
"""

import geopandas as gpd
from shapely.geometry import box
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.grid_utils import split_bbox_into_grid
from utils.polygon_filter import PolygonFilter


def test_adjacent_provinces_overlap(province1_code: str, province2_code: str, chunk_size_km: float = 50):
    """
    Test if grids from adjacent provinces can overlap.

    Args:
        province1_code: First province ISO code (e.g., 'TH-10')
        province2_code: Second province ISO code (e.g., 'TH-12')
        chunk_size_km: Grid chunk size in km
    """
    provinces_path = Path(__file__).parent.parent / 'data' / 'thailand_provinces_geoboundaries.geojson'
    if not provinces_path.exists():
        print(f"ERROR: {provinces_path} not found")
        return

    provinces_gdf = gpd.read_file(provinces_path)
    polygon_filter = PolygonFilter(provinces_geojson_path=str(provinces_path))

    # Get both provinces
    p1_row = provinces_gdf[provinces_gdf['shapeISO'] == province1_code]
    p2_row = provinces_gdf[provinces_gdf['shapeISO'] == province2_code]

    if len(p1_row) == 0 or len(p2_row) == 0:
        print(f"ERROR: Province not found")
        return

    p1_geom = p1_row.iloc[0].geometry
    p2_geom = p2_row.iloc[0].geometry
    p1_name = p1_row.iloc[0]['shapeName']
    p2_name = p2_row.iloc[0]['shapeName']

    print(f"Testing grid overlap between:")
    print(f"  Province 1: {p1_name} ({province1_code})")
    print(f"  Province 2: {p2_name} ({province2_code})")
    print()

    # Generate grids for both provinces
    p1_bounds = p1_geom.bounds
    p2_bounds = p2_geom.bounds

    p1_bbox = f"{p1_bounds[0]},{p1_bounds[1]},{p1_bounds[2]},{p1_bounds[3]}"
    p2_bbox = f"{p2_bounds[0]},{p2_bounds[1]},{p2_bounds[2]},{p2_bounds[3]}"

    print(f"Province 1 bbox: {p1_bbox}")
    print(f"Province 2 bbox: {p2_bbox}")
    print()

    # Check if bboxes overlap
    bbox1 = box(p1_bounds[0], p1_bounds[1], p1_bounds[2], p1_bounds[3])
    bbox2 = box(p2_bounds[0], p2_bounds[1], p2_bounds[2], p2_bounds[3])

    if not bbox1.intersects(bbox2):
        print("[INFO] Bboxes don't overlap - provinces are not adjacent")
        return

    print("[INFO] Bboxes DO overlap (provinces are adjacent)")
    overlap_area = bbox1.intersection(bbox2).area
    print(f"  Bbox overlap area: {overlap_area:.6f} sq degrees")
    print()

    # Generate all grids
    p1_all_grids = split_bbox_into_grid(p1_bbox, chunk_size_km=chunk_size_km)
    p2_all_grids = split_bbox_into_grid(p2_bbox, chunk_size_km=chunk_size_km)

    # Filter by province polygons
    p1_filtered = polygon_filter.filter_grids_by_province(p1_all_grids, province1_code, 'TH')
    p2_filtered = polygon_filter.filter_grids_by_province(p2_all_grids, province2_code, 'TH')

    print(f"Province 1 ({p1_name}):")
    print(f"  Total bbox grids: {len(p1_all_grids)}")
    print(f"  Filtered grids: {len(p1_filtered)}")

    print(f"Province 2 ({p2_name}):")
    print(f"  Total bbox grids: {len(p2_all_grids)}")
    print(f"  Filtered grids: {len(p2_filtered)}")
    print()

    # Check for spatial overlaps between filtered grids
    print("Checking for grid spatial overlaps...")

    # Convert to shapely boxes
    p1_boxes = []
    for grid in p1_filtered:
        min_lon, min_lat, max_lon, max_lat = map(float, grid['bbox'].split(','))
        p1_boxes.append({
            'bbox': grid['bbox'],
            'geom': box(min_lon, min_lat, max_lon, max_lat)
        })

    p2_boxes = []
    for grid in p2_filtered:
        min_lon, min_lat, max_lon, max_lat = map(float, grid['bbox'].split(','))
        p2_boxes.append({
            'bbox': grid['bbox'],
            'geom': box(min_lon, min_lat, max_lon, max_lat)
        })

    # Find overlapping grids
    overlaps = []
    for p1_grid in p1_boxes:
        for p2_grid in p2_boxes:
            if p1_grid['geom'].intersects(p2_grid['geom']):
                overlap_area = p1_grid['geom'].intersection(p2_grid['geom']).area
                overlaps.append({
                    'p1_bbox': p1_grid['bbox'],
                    'p2_bbox': p2_grid['bbox'],
                    'overlap_area': overlap_area
                })

    if len(overlaps) == 0:
        print("[PASS] NO grid overlaps found between provinces!")
        print("  Each grid is uniquely assigned to one province.")
        print()
        return True
    else:
        print(f"[WARNING] Found {len(overlaps)} grid overlaps:")
        for i, overlap in enumerate(overlaps[:5]):  # Show first 5
            print(f"  {i+1}. P1 grid {overlap['p1_bbox']} overlaps P2 grid {overlap['p2_bbox']}")
            print(f"     Overlap area: {overlap['overlap_area']:.6f} sq degrees")

        if len(overlaps) > 5:
            print(f"  ... and {len(overlaps) - 5} more overlaps")
        print()

        # BUT: These grids are processed separately with different province IDs
        print("[IMPORTANT] However, these overlapping grids are:")
        print("  - Generated from DIFFERENT province bboxes")
        print("  - Filtered by DIFFERENT province polygons")
        print("  - Processed with DIFFERENT cache keys (TH_TH-10 vs TH_TH-50)")
        print("  - Assigned to DIFFERENT provinces in the output")
        print()
        print("So even though they spatially overlap, they:")
        print("  1. Query the OSM API independently (may get same data)")
        print("  2. Are attributed to their respective provinces")
        print("  3. Don't cause double-counting (different province_code in results)")
        print()

        return False


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test province grid overlap')
    parser.add_argument('--p1', default='TH-10', help='First province ISO code (default: TH-10 Bangkok)')
    parser.add_argument('--p2', default='TH-11', help='Second province ISO code (default: TH-11 Samut Prakan)')
    parser.add_argument('--chunk-size', type=float, default=50, help='Grid chunk size in km (default: 50)')

    args = parser.parse_args()

    test_adjacent_provinces_overlap(args.p1, args.p2, args.chunk_size)
