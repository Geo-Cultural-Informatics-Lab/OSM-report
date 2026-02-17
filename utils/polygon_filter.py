"""
Filter grids based on country polygon intersection.

Uses polygon data from geometric_complexity project to filter out
grids that are entirely over water or outside country boundaries.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
import geopandas as gpd
from shapely.geometry import box

logger = logging.getLogger(__name__)


class PolygonFilter:
    """Filter grids by country polygon intersection."""

    def __init__(
        self,
        geojson_path: Optional[str] = None,
        provinces_geojson_path: Optional[str] = None,   # legacy: single country (TH)
        provinces_geojson_paths: Optional[dict] = None  # preferred: dict ISO -> path
    ):
        """
        Initialize polygon filter.

        Args:
            geojson_path: Path to World_Countries.geojson file.
                         If None, tries to find it in geometric_complexity project.
            provinces_geojson_path: Legacy single provinces GeoJSON path (Thailand only).
            provinces_geojson_paths: Dict mapping ISO code -> GeoJSON path, e.g.
                {'TH': '/data/th.geojson', 'ID': '/data/id.geojson'}
        """
        if geojson_path is None:
            # Try to find in geometric_complexity project (works on both Windows and Linux)
            possible_paths = [
                # Relative to this file: report/utils/ -> report/ -> OSM/ -> geometric_complexity/
                Path(__file__).parent.parent.parent / "geometric_complexity" / "countries_polygons" / "World_Countries.geojson",
                # Linux: OSM-geometrical_complexity sibling directory
                Path(__file__).parent.parent.parent / "OSM-geometrical_complexity" / "countries_polygons" / "World_Countries.geojson",
            ]
            for path in possible_paths:
                if path.exists():
                    geojson_path = str(path)
                    break

        if geojson_path is None:
            logger.warning("Could not find World_Countries.geojson, polygon filtering disabled")
            self.gdf = None
            self.enabled = False
            return

        try:
            self.gdf = gpd.read_file(geojson_path)
            self.enabled = True
            logger.info(f"Loaded country polygons from {geojson_path}")
        except Exception as e:
            logger.warning(f"Failed to load country polygons: {e}, filtering disabled")
            self.gdf = None
            self.enabled = False

        # Build a combined dict of ISO -> GeoJSON path from both legacy and new params
        all_province_paths = {}
        if provinces_geojson_paths:
            all_province_paths.update(provinces_geojson_paths)
        if provinces_geojson_path and 'TH' not in all_province_paths:
            all_province_paths['TH'] = provinces_geojson_path

        # Load each country's province GeoJSON into a per-country GeoDataFrame dict
        # self.provinces_gdfs: dict of ISO -> GeoDataFrame
        self.provinces_gdfs = {}
        for iso, path in all_province_paths.items():
            if path and Path(path).exists():
                try:
                    gdf = gpd.read_file(path)
                    self.provinces_gdfs[iso] = gdf
                    logger.info(f"Loaded {len(gdf)} admin boundaries for {iso} from {path}")
                except Exception as e:
                    logger.warning(f"Failed to load provinces for {iso}: {e}")

        self.provinces_enabled = len(self.provinces_gdfs) > 0

        # Legacy single-GDF attribute: use TH if available (backward compat for province_analyzer)
        self.provinces_gdf = self.provinces_gdfs.get('TH')

    def get_country_polygon(self, iso_code: str):
        """
        Get polygon geometry for a country.

        Args:
            iso_code: 2-letter ISO country code (e.g., 'TH', 'MM')

        Returns:
            GeoDataFrame with country polygon or None
        """
        if not self.enabled:
            return None

        try:
            # Filter by ISO code (the GeoJSON uses 'ISO' column)
            country_data = self.gdf[self.gdf['ISO'] == iso_code.upper()]

            if country_data.empty:
                logger.warning(f"Country polygon not found for {iso_code}")
                return None

            return country_data
        except Exception as e:
            logger.error(f"Error getting polygon for {iso_code}: {e}")
            return None

    def get_province_polygon(self, province_code: str, country_iso: str = 'TH'):
        """
        Get polygon geometry for a province.

        Args:
            province_code: Province code (e.g., 'BKK', 'TH-10')
            country_iso: Country ISO code (for scoping)

        Returns:
            Province geometry (Polygon or MultiPolygon) or None
        """
        if not self.provinces_enabled:
            logger.debug(f"Provinces not loaded, cannot filter for {province_code}")
            return None

        try:
            # Look up GeoDataFrame for the specific country
            gdf = self.provinces_gdfs.get(country_iso)
            if gdf is None:
                logger.warning(f"No province boundaries loaded for country {country_iso}")
                return None

            # Try matching by different code formats (geoBoundaries uses shapeISO, shapeID, shapeName)
            matches = gdf[
                (gdf['shapeISO'] == province_code) |
                (gdf['shapeID'] == province_code) |
                (gdf['shapeName'].str.contains(province_code, case=False, na=False, regex=False))
            ]

            if len(matches) == 0:
                logger.warning(f"Province {province_code} not found in {country_iso} GeoJSON")
                return None

            return matches.iloc[0].geometry
        except Exception as e:
            logger.error(f"Error getting province polygon for {province_code} ({country_iso}): {e}")
            return None

    def filter_grids_by_province(
        self,
        grids: List[Dict],
        province_code: str,
        country_iso: str = 'TH'
    ) -> List[Dict]:
        """
        Filter grids to only include those intersecting with province polygon.

        Args:
            grids: List of grid dictionaries with 'bbox' key
            province_code: Province code
            country_iso: Country ISO code

        Returns:
            Filtered list of grids that intersect province boundary
        """
        if not self.provinces_enabled:
            logger.debug("Province filtering disabled, returning all grids")
            return grids

        try:
            # Get province polygon
            province_geom = self.get_province_polygon(province_code, country_iso)
            if province_geom is None:
                logger.warning(f"No polygon for province {province_code}, returning all grids")
                return grids

            # Filter grids by intersection
            filtered_grids = []
            filtered_count = 0

            for grid in grids:
                # Parse bbox string "min_lon,min_lat,max_lon,max_lat"
                bbox_parts = grid['bbox'].split(',')
                min_lon, min_lat, max_lon, max_lat = map(float, bbox_parts)

                # Create box geometry for grid
                grid_box = box(min_lon, min_lat, max_lon, max_lat)

                # Check if grid intersects with province polygon
                if grid_box.intersects(province_geom):
                    filtered_grids.append(grid)
                else:
                    filtered_count += 1

            logger.debug(
                f"{province_code}: Filtered out {filtered_count}/{len(grids)} grids "
                f"(kept {len(filtered_grids)} grids)"
            )

            return filtered_grids

        except Exception as e:
            logger.error(f"Error filtering grids for province {province_code}: {e}, returning all grids")
            return grids

    def filter_grids(self, grids: List[Dict], iso_code: str) -> List[Dict]:
        """
        Filter grids to only include those that intersect with country polygon.

        Args:
            grids: List of grid dictionaries with 'bbox' key
            iso_code: 2-letter ISO country code

        Returns:
            Filtered list of grids that intersect with country polygon
        """
        if not self.enabled:
            logger.warning("Polygon filtering not enabled, returning all grids")
            return grids

        try:
            # Get country polygon
            country_polygon = self.get_country_polygon(iso_code)
            if country_polygon is None:
                logger.warning(f"No polygon for {iso_code}, returning all grids")
                return grids

            # Get the geometry (may be multipolygon)
            country_geom = country_polygon.geometry.iloc[0]

            # Filter grids
            filtered_grids = []
            filtered_count = 0

            for grid in grids:
                # Parse bbox string "min_lon,min_lat,max_lon,max_lat"
                bbox_parts = grid['bbox'].split(',')
                min_lon, min_lat, max_lon, max_lat = map(float, bbox_parts)

                # Create box geometry for grid
                grid_box = box(min_lon, min_lat, max_lon, max_lat)

                # Check if grid intersects with country polygon
                if grid_box.intersects(country_geom):
                    filtered_grids.append(grid)
                else:
                    filtered_count += 1

            logger.info(
                f"{iso_code}: Filtered out {filtered_count}/{len(grids)} grids "
                f"(kept {len(filtered_grids)} grids that intersect land)"
            )

            return filtered_grids

        except Exception as e:
            logger.error(f"Error filtering grids for {iso_code}: {e}, returning all grids")
            return grids
