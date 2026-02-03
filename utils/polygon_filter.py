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

    def __init__(self, geojson_path: Optional[str] = None):
        """
        Initialize polygon filter.

        Args:
            geojson_path: Path to World_Countries.geojson file.
                         If None, tries to find it in geometric_complexity project.
        """
        if geojson_path is None:
            # Try to find in geometric_complexity project
            possible_paths = [
                Path(__file__).parent.parent.parent / "geometric_complexity" / "countries_polygons" / "World_Countries.geojson",
                Path("C:/Users/user/code/OSM/geometric_complexity/countries_polygons/World_Countries.geojson"),
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
