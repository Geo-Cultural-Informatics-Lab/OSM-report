"""
Province-level analysis for Thailand.

Analyzes each province separately and combines into a unified report.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ProvinceAnalyzer:
    """Analyzes countries at province level using cached admin boundaries."""

    def __init__(self, orchestrator, provinces_geojson_path):
        """
        Initialize province analyzer.

        Args:
            orchestrator: CountryReportOrchestrator instance
            provinces_geojson_path: Path to cached provinces GeoJSON file
        """
        self.orchestrator = orchestrator
        self.polygon_filter = orchestrator.polygon_filter  # Store reference for filtering
        self.provinces = self._load_provinces(provinces_geojson_path)
        logger.info(f"Loaded {len(self.provinces)} provinces from {provinces_geojson_path}")

    def _load_provinces(self, geojson_path):
        """Load provinces from GeoJSON file."""
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson = json.load(f)

        provinces = []
        for feature in geojson['features']:
            props = feature['properties']

            # Get code with proper fallback (prefer iso_code for matching with geoBoundaries)
            # iso_code format: TH-10, TH-15, etc. (matches geoBoundaries shapeISO)
            code = props.get('iso_code') or props.get('ref') or f"TH-{props['osm_id']}"

            provinces.append({
                'osm_id': props['osm_id'],
                'name': props['name_en'],
                'name_th': props.get('name_th', ''),
                'code': code,
                'bbox': props['bbox'],
                'geometry': feature['geometry']  # GeoJSON geometry
            })

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
            country_iso: Country ISO code (e.g., 'TH')
            years: List of years
            entities: List of entity types

        Returns:
            List of row dictionaries (one per province-year-entity combination)
        """
        all_rows = []

        total = len(self.provinces) * len(years) * len(entities)
        logger.info(f"Analyzing {len(self.provinces)} provinces × {len(years)} years × {len(entities)} entities = {total} combinations")

        for province in self.provinces:
            logger.info(f"Processing province: {province['name']} ({province['code']})")

            for year in years:
                for entity in entities:
                    logger.info(f"  {year} {entity}...")

                    try:
                        # Analyze this province-year-entity combination
                        metrics, tag_details = await self._analyze_province_year_entity(
                            country_iso, province, year, entity
                        )

                        all_rows.append(metrics)

                    except Exception as e:
                        logger.error(
                            f"Failed {province['name']} {year} {entity}: {e}"
                        )
                        # Add empty row
                        all_rows.append({
                            'country': country_iso,
                            'province_code': province['code'],
                            'province_name': province['name'],
                            'province_name_th': province['name_th'],
                            'year': year,
                            'entity': entity,
                            'geometry_wkt': None,
                            'geometry_geojson': None,
                            'bbox': province['bbox'],
                            'geometric_complexity': None,
                            'unique_tags_count': None,
                            'richness_mean': None,
                            'richness_median': None,
                            'evenness': None,
                            'shannon_index': None,
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
        # Convert province bbox to grid chunks
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

        # Filter grids by province polygon (if polygon filtering enabled)
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

        # Process grids using orchestrator's infrastructure
        # (reuses cache, async processing, adapters)
        grid_results = await self.orchestrator._process_grids_with_cache(
            iso_code=f"{country_iso}_{province['code']}",  # Unique cache key per province
            year=year,
            entity=entity,
            grids=grids,
            region_bbox=province_bbox  # Pass province bbox for tag analysis
        )

        # Aggregate results for this province
        metrics = self.orchestrator.aggregator.aggregate_grids(
            grid_results,
            iso_code=country_iso,  # Still TH for final report
            year=year,
            entity_type=entity
        )

        # Add province-specific fields
        metrics['province_code'] = province['code']
        metrics['province_name'] = province['name']
        metrics['province_name_th'] = province['name_th']
        metrics['bbox'] = province['bbox']

        # Add geometry as WKT and GeoJSON
        geometry = province['geometry']
        metrics['geometry_geojson'] = json.dumps(geometry)

        # Convert GeoJSON to WKT (simple bbox polygon)
        coords = geometry['coordinates'][0]
        wkt_coords = ', '.join([f"{lon} {lat}" for lon, lat in coords])
        metrics['geometry_wkt'] = f"POLYGON(({wkt_coords}))"

        # Extract tag details
        tag_details = self.orchestrator.aggregator.extract_tag_details(
            grid_results, country_iso, year, entity
        )

        return metrics, tag_details
