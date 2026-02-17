"""
Province-level analysis for any country with geoBoundaries GeoJSON data.

Analyzes each province/admin-1 region separately using geoBoundaries GeoJSON
files, and combines results into a unified report.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ProvinceAnalyzer:
    """Analyzes countries at province level using geoBoundaries admin boundaries."""

    def __init__(self, orchestrator, geojson_path):
        """
        Initialize province analyzer.

        Args:
            orchestrator: CountryReportOrchestrator instance
            geojson_path: Path to geoBoundaries GeoJSON file (ADM1 level)
        """
        self.orchestrator = orchestrator
        self.polygon_filter = orchestrator.polygon_filter
        self.provinces = self._load_provinces(geojson_path)
        logger.info(f"Loaded {len(self.provinces)} provinces from {geojson_path}")

    def _load_provinces(self, geojson_path) -> List[Dict]:
        """
        Load provinces from a geoBoundaries GeoJSON file.

        Supports:
          - geoBoundaries schema: shapeISO, shapeName, shapeID fields
          - Legacy Overpass schema: iso_code, name_en, name_th, osm_id fields
        """
        try:
            import geopandas as gpd
            from shapely.geometry import mapping
        except ImportError:
            raise ImportError(
                "geopandas and shapely are required for province analysis. "
                "Run: pip install geopandas shapely"
            )

        gdf = gpd.read_file(str(geojson_path))
        logger.info(f"Read {len(gdf)} features from {geojson_path}")

        # Detect schema by checking column names
        is_geoboundaries = 'shapeISO' in gdf.columns or 'shapeName' in gdf.columns

        provinces = []
        skipped = 0
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                skipped += 1
                continue

            # Compute bbox from actual geometry bounds: (minx, miny, maxx, maxy)
            bounds = geom.bounds
            bbox = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"

            if is_geoboundaries:
                # geoBoundaries schema
                code = (
                    row.get('shapeISO')
                    or row.get('shapeID', '')
                )
                name = row.get('shapeName', code)
                name_local = row.get('shapeName', '')
            else:
                # Legacy Overpass schema (Thailand admin4 file)
                code = (
                    row.get('iso_code')
                    or row.get('ref')
                    or str(row.get('osm_id', ''))
                )
                name = row.get('name_en') or row.get('name', code)
                name_local = (
                    row.get('name_th')
                    or row.get('name_local', '')
                )

            provinces.append({
                'code': str(code),
                'name': str(name),
                'name_local': str(name_local),
                'bbox': bbox,
                'geometry': mapping(geom),   # GeoJSON-serialisable dict
            })

        if skipped:
            logger.warning(f"Skipped {skipped} features with missing/empty geometry")

        return provinces

    async def analyze_provinces(
        self,
        country_iso: str,
        years: List[int],
        entities: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Analyze all provinces for given years and entities.

        Args:
            country_iso: Country ISO code (e.g., 'TH', 'ID')
            years: List of years
            entities: List of entity types

        Returns:
            List of row dictionaries (one per province-year-entity combination)
        """
        all_rows = []

        total = len(self.provinces) * len(years) * len(entities)
        logger.info(
            f"Analyzing {len(self.provinces)} provinces × "
            f"{len(years)} years × {len(entities)} entities = {total} combinations"
        )

        for province in self.provinces:
            logger.info(f"Processing province: {province['name']} ({province['code']})")

            for year in years:
                for entity in entities:
                    logger.info(f"  {year} {entity}...")

                    try:
                        metrics, _ = await self._analyze_province_year_entity(
                            country_iso, province, year, entity
                        )
                        all_rows.append(metrics)

                    except Exception as e:
                        logger.error(
                            f"Failed {province['name']} {year} {entity}: {e}",
                            exc_info=True
                        )
                        # Add empty row so the output shape stays consistent
                        all_rows.append({
                            'country': country_iso,
                            'province_code': province['code'],
                            'province_name': province['name'],
                            'province_name_local': province['name_local'],
                            'year': year,
                            'entity': entity,
                            'bbox': province['bbox'],
                            'geometry_geojson': None,
                            'entity_count': 0,
                            'geometric_complexity': None,
                            'unique_tags_count': 0,
                            'richness_mean': 0.0,
                            'richness_median': 0.0,
                            'evenness': 0.0,
                            'shannon_index': 0.0,
                        })

        return all_rows

    async def _analyze_province_year_entity(
        self,
        country_iso: str,
        province: Dict,
        year: int,
        entity: str
    ) -> tuple:
        """
        Analyze a single province-year-entity combination.

        Uses the existing orchestrator infrastructure but treats
        the province bbox as a "mini-country".

        Returns:
            Tuple of (metrics dict, tag_details list)
        """
        from utils.grid_utils import split_bbox_into_grid

        province_bbox = province['bbox']
        grids = split_bbox_into_grid(
            province_bbox,
            chunk_size_km=self.orchestrator.chunk_size_km
        )

        logger.debug(
            f"{province['name']}: Split into {len(grids)} grids "
            f"({self.orchestrator.chunk_size_km}km chunks)"
        )

        # Filter grids to only those intersecting the actual province polygon
        if self.polygon_filter and self.polygon_filter.provinces_enabled:
            original_count = len(grids)
            grids = self.polygon_filter.filter_grids_by_province(
                grids,
                province['code'],
                country_iso
            )
            logger.debug(
                f"{province['name']}: Filtered out {original_count - len(grids)} grids "
                f"(kept {len(grids)} that intersect province)"
            )

        # Use a unique cache key per province so results don't bleed across regions
        cache_key_iso = f"{country_iso}_{province['code']}"

        # Process grids using the orchestrator's full pipeline
        grid_results = await self.orchestrator._process_grids_with_cache(
            iso_code=cache_key_iso,
            year=year,
            entity=entity,
            grids=grids,
            region_bbox=province_bbox
        )

        # Aggregate grid results for this province
        metrics = self.orchestrator.aggregator.aggregate_grids(
            grid_results,
            iso_code=country_iso,
            year=year,
            entity_type=entity
        )

        # Attach province-specific fields
        metrics['province_code'] = province['code']
        metrics['province_name'] = province['name']
        metrics['province_name_local'] = province['name_local']
        metrics['bbox'] = province['bbox']

        # Serialize province geometry as GeoJSON string
        metrics['geometry_geojson'] = json.dumps(province['geometry'])

        # Extract tag details for this province
        tag_details = self.orchestrator.aggregator.extract_tag_details(
            grid_results, country_iso, year, entity
        )

        return metrics, tag_details
