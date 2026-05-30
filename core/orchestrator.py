"""
Main orchestrator for OSM country report generation.

Coordinates cache, adapters, async processing, and aggregation
to generate unified country reports.
"""

# Import bootstrap module FIRST to load editable packages
# This must happen before any other imports that depend on the packages
from core import _bootstrap  # noqa: F401

import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
from tqdm import tqdm

# Setup sys.path BEFORE any imports
report_path = str(Path(__file__).parent.parent)
geometric_complexity_path = str(Path(__file__).parent.parent.parent / "geometric_complexity")
tags_semantic_path = str(Path(__file__).parent.parent.parent / "tags_semantic_analysis")
innovation_path = str(Path(__file__).parent.parent.parent / "innovation")

# Add all paths: report first, then subprojects
# IMPORTANT: Remove report_path if it exists anywhere, then insert at position 0
# This is necessary because site-packages can be inserted before our path
while report_path in sys.path:
    sys.path.remove(report_path)
sys.path.insert(0, report_path)

if Path(geometric_complexity_path).exists() and geometric_complexity_path not in sys.path:
    sys.path.insert(1, geometric_complexity_path)
if Path(tags_semantic_path).exists() and tags_semantic_path not in sys.path:
    sys.path.insert(2, tags_semantic_path)
if Path(innovation_path).exists() and innovation_path not in sys.path:
    sys.path.insert(3, innovation_path)

# Now import all modules
from core.cache_manager import CacheManager
from core.aggregator import MetricsAggregator
from utils.async_runner import AsyncGridRunner
from utils.grid_utils import split_country_into_grids
from utils.polygon_filter import PolygonFilter
from integrations.completeness_adapter import CompletenessAdapter

# Note: Real adapters (GeometricComplexityAdapter, SemanticTagsAdapter) are imported
# lazily in the __init__ method after bootstrap has run

logger = logging.getLogger(__name__)


class CountryReportOrchestrator:
    """
    Orchestrates the generation of country reports.

    Coordinates grid processing, caching, and aggregation across
    multiple years and entity types.
    """

    def __init__(
        self,
        cache_dir: str = "./cache",
        results_dir: str = "./results",
        merge_from_dir: str = None,
        chunk_size_km: float = 50,
        max_concurrent: int = 10,
        api_timeout: int = 30,
        enabled_modules: set = None,
        provinces_geojson_path: str = None,   # legacy single-country path (kept for compat)
        provinces_geojson_paths: dict = None  # preferred: dict of ISO -> path
    ):
        """
        Initialize orchestrator.

        Args:
            cache_dir: Cache directory
            results_dir: Results output directory
            merge_from_dir: Directory containing existing CSVs to merge with when preserving
                            columns from modules not run this time. Defaults to results_dir.
            chunk_size_km: Grid chunk size in km
            max_concurrent: Max concurrent requests
            api_timeout: API request timeout in seconds (default: 30)
            enabled_modules: Set of enabled modules (default: {'geometric', 'tags'})
            provinces_geojson_path: Legacy single provinces GeoJSON path (Thailand only)
            provinces_geojson_paths: Dict mapping ISO code -> GeoJSON path for multiple countries
        """
        self.cache_dir = Path(cache_dir)
        self.results_dir = Path(results_dir)
        # Where to look for existing CSVs to merge from — defaults to results_dir
        self.merge_from_dir = Path(merge_from_dir) if merge_from_dir else self.results_dir
        self.chunk_size_km = chunk_size_km
        self.max_concurrent = max_concurrent
        self.api_timeout = api_timeout

        # Default to all modules if not specified
        self.enabled_modules = enabled_modules if enabled_modules else {'geometric', 'tags'}

        # Build provinces path dict (merge legacy single path into dict)
        self.provinces_geojson_paths = provinces_geojson_paths or {}
        if provinces_geojson_path and 'TH' not in self.provinces_geojson_paths:
            self.provinces_geojson_paths['TH'] = provinces_geojson_path

        # Create directories
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.cache = CacheManager(cache_dir=str(cache_dir))
        self.aggregator = MetricsAggregator()
        self.async_runner = AsyncGridRunner(max_concurrent=max_concurrent)
        self.polygon_filter = PolygonFilter(
            geojson_path=None,  # Auto-finds World_Countries.geojson
            provinces_geojson_paths=self.provinces_geojson_paths  # multi-country dict
        )

        # Initialize adapters
        # Import adapters here (after bootstrap has run) to ensure packages are available
        try:
            from integrations.geometric_complexity_adapter import GeometricComplexityAdapter
            self.geom_adapter = GeometricComplexityAdapter(timeout=api_timeout)
            logger.debug("GeometricComplexityAdapter initialized successfully")
        except ImportError as e:
            logger.error(f"FATAL: Could not import GeometricComplexityAdapter: {e}")
            raise RuntimeError(
                "GeometricComplexityAdapter is required but could not be imported. "
                "Please ensure all dependencies are installed."
            ) from e
        except Exception as e:
            logger.error(f"FATAL: GeometricComplexityAdapter initialization failed: {e}")
            raise RuntimeError(
                "GeometricComplexityAdapter is required but failed to initialize. "
                "Please check your configuration and dependencies."
            ) from e

        try:
            from integrations.semantic_tags_adapter import SemanticTagsAdapter
            self.tags_adapter = SemanticTagsAdapter(chunk_size_km=chunk_size_km, timeout=api_timeout)
            logger.debug("SemanticTagsAdapter initialized successfully")
        except ImportError as e:
            logger.error(f"FATAL: Could not import SemanticTagsAdapter: {e}")
            raise RuntimeError(
                "SemanticTagsAdapter is required but could not be imported. "
                "Please ensure all dependencies are installed."
            ) from e
        except Exception as e:
            logger.error(f"FATAL: SemanticTagsAdapter initialization failed: {e}")
            raise RuntimeError(
                "SemanticTagsAdapter is required but failed to initialize. "
                "Please check your configuration and dependencies."
            ) from e

        self.completeness_adapter = CompletenessAdapter()

        # Innovation adapter (optional — only when 'innovation' module is enabled)
        if 'innovation' in self.enabled_modules:
            try:
                from integrations.innovation_adapter import InnovationAdapter
                # Use a sub-directory of cache so innovation raw data stays separate
                innovation_cache = str(Path(cache_dir) / "innovation")
                self.innovation_adapter = InnovationAdapter(
                    chunk_size_km=chunk_size_km,
                    timeout=api_timeout,
                    cache_dir=innovation_cache
                )
                logger.debug("InnovationAdapter initialized successfully")
            except ImportError as e:
                logger.error(f"Could not import InnovationAdapter: {e}")
                raise RuntimeError(
                    "InnovationAdapter unavailable. Run: pip install -e ../innovation"
                ) from e
            except Exception as e:
                logger.error(f"InnovationAdapter initialization failed: {e}")
                raise RuntimeError(
                    "InnovationAdapter failed to initialize. Check dependencies."
                ) from e
        else:
            self.innovation_adapter = None

        logger.debug(f"Orchestrator initialized: cache={cache_dir}, results={results_dir}")

    async def generate_country_report(
        self,
        iso_code: str,
        years: List[int],
        entities: List[str]
    ) -> Dict[str, Any]:
        """
        Generate complete report for a country.

        Args:
            iso_code: Country ISO code
            years: List of years to analyze
            entities: List of entity types (building, road)

        Returns:
            Dictionary with report metadata and file paths
        """
        logger.info(
            f"Generating report for {iso_code}: "
            f"{len(years)} years × {len(entities)} entities"
        )

        all_rows = []
        all_tag_details = []

        # Create progress bar for year/entity combinations
        total_combinations = len(years) * len(entities)
        pbar = tqdm(
            total=total_combinations,
            desc=f"[{iso_code}] Report",
            unit="combo",
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        )

        for year in years:
            for entity in entities:
                # Update progress bar description - this is the main status indicator
                pbar.set_description(f"[{iso_code}] {year} {entity}")
                # Use print instead of logger to avoid timestamp clutter
                print(f"\n[{iso_code}] Starting {year} {entity}...")

                try:
                    # Process year/entity combination
                    metrics, tag_details = await self.process_country_year_entity(
                        iso_code, year, entity
                    )

                    all_rows.append(metrics)
                    all_tag_details.extend(tag_details)

                except Exception as e:
                    logger.error(
                        f"Failed to process {iso_code} {year} {entity}: {e}"
                    )
                    logger.error(f"Exception type: {type(e).__name__}")
                    logger.error(f"Exception details:", exc_info=True)
                    # Add empty row to maintain consistency
                    all_rows.append(
                        self.aggregator._empty_metrics(iso_code, year, entity)
                    )
                finally:
                    pbar.update(1)

        pbar.close()

        # Completeness analysis (post-loop, all years per entity at once).
        # Merges completeness_score back into all_rows before writing the primary CSV,
        # so a single th.csv accumulates completeness alongside other metrics.
        if 'completeness' in self.enabled_modules:
            for entity in entities:
                # Compute tight filtered bbox (same logic as the innovation block below)
                comp_grids = split_country_into_grids(iso_code, chunk_size_km=self.chunk_size_km)
                comp_grids = self.polygon_filter.filter_grids(comp_grids, iso_code)
                if not comp_grids:
                    logger.warning(f"{iso_code} {entity}: No grids for completeness analysis")
                    continue

                lons, lats = [], []
                for g in comp_grids:
                    parts = [float(x) for x in g['bbox'].split(',')]
                    lons.extend([parts[0], parts[2]])
                    lats.extend([parts[1], parts[3]])
                comp_bbox = f"{min(lons)},{min(lats)},{max(lons)},{max(lats)}"

                print(f"\n[{iso_code}] Starting completeness analysis for {entity} "
                      f"({len(years)} years)...")

                comp_rows = self.completeness_adapter.analyze_all_years(
                    bbox=comp_bbox,
                    entity_type=entity,
                    years=years,
                    iso_code=iso_code,
                )

                # Build lookup: (year, entity_key) → score
                comp_lookup = {
                    (r['year'], r['entity']): r['completeness_score']
                    for r in comp_rows
                }

                # Merge into all_rows (match by year + entity, normalising 'road'→'highway')
                entity_key = 'highway' if entity == 'road' else entity
                for row in all_rows:
                    row_entity = row.get('entity', '')
                    row_entity_norm = 'highway' if row_entity == 'road' else row_entity
                    if row_entity_norm == entity_key:
                        key = (row['year'], entity_key)
                        row['completeness_score'] = comp_lookup.get(key, None)

        # Write CSVs
        primary_file = self._write_primary_csv(iso_code, all_rows)
        detail_file = self._write_detail_csv(iso_code, all_tag_details)

        # Innovation analysis (post-loop, processes all years per entity at once)
        innovation_file = None
        if self.innovation_adapter:
            all_innovation_rows = []
            for entity in entities:
                # Recompute filtered grids (same logic as process_country_year_entity)
                inno_grids = split_country_into_grids(
                    iso_code, chunk_size_km=self.chunk_size_km
                )
                inno_grids = self.polygon_filter.filter_grids(inno_grids, iso_code)

                if not inno_grids:
                    logger.warning(
                        f"{iso_code} {entity}: No grids for innovation analysis"
                    )
                    continue

                # Compute tight bbox from filtered grids
                lons, lats = [], []
                for g in inno_grids:
                    parts = [float(x) for x in g['bbox'].split(',')]
                    lons.extend([parts[0], parts[2]])
                    lats.extend([parts[1], parts[3]])
                filtered_bbox = f"{min(lons)},{min(lats)},{max(lons)},{max(lats)}"

                print(f"\n[{iso_code}] Starting innovation analysis for {entity} "
                      f"({len(years)} years)...")

                inno_rows = self.innovation_adapter.analyze_all_years(
                    bbox=filtered_bbox,
                    entity_type=entity,
                    years=years,
                    iso_code=iso_code,
                    filtered_chunks=inno_grids
                )
                all_innovation_rows.extend(inno_rows)

            if all_innovation_rows:
                innovation_file = self._write_innovation_csv(
                    iso_code, all_innovation_rows
                )

        logger.info(
            f"Report complete for {iso_code}: "
            f"{len(all_rows)} rows, {len(all_tag_details)} tag details"
        )

        return {
            'country': iso_code,
            'total_rows': len(all_rows),
            'total_tag_details': len(all_tag_details),
            'primary_file': str(primary_file),
            'detail_file': str(detail_file),
            'innovation_file': str(innovation_file) if innovation_file else None
        }

    async def process_country_year_entity(
        self,
        iso_code: str,
        year: int,
        entity: str
    ) -> tuple:
        """
        Process a single country/year/entity combination.

        Args:
            iso_code: Country code
            year: Year
            entity: Entity type

        Returns:
            Tuple of (metrics dict, tag details list)
        """
        # Get grids for country
        grids = split_country_into_grids(
            iso_code,
            chunk_size_km=self.chunk_size_km
        )

        logger.debug(f"{iso_code} {year} {entity}: Split into {len(grids)} grids")

        # Filter grids to only those that intersect with country polygon
        grids = self.polygon_filter.filter_grids(grids, iso_code)

        logger.debug(f"{iso_code} {year} {entity}: Processing {len(grids)} grids after polygon filtering")

        # Compute tight bbox from filtered grids (covers only land, not ocean)
        # This ensures tag analysis doesn't waste API calls on ocean areas
        if grids:
            lons = []
            lats = []
            for g in grids:
                parts = [float(x) for x in g['bbox'].split(',')]
                lons.extend([parts[0], parts[2]])
                lats.extend([parts[1], parts[3]])
            filtered_bbox = f"{min(lons)},{min(lats)},{max(lons)},{max(lats)}"
        else:
            filtered_bbox = None

        # Process grids (check cache first, then analyze)
        grid_results = await self._process_grids_with_cache(
            iso_code, year, entity, grids,
            region_bbox=filtered_bbox
        )

        # Aggregate results
        metrics = self.aggregator.aggregate_grids(
            grid_results, iso_code, year, entity
        )

        tag_details = self.aggregator.extract_tag_details(
            grid_results, iso_code, year, entity
        )

        return metrics, tag_details

    async def _process_grids_with_cache(
        self,
        iso_code: str,
        year: int,
        entity: str,
        grids: List[Dict],
        region_bbox: Optional[str] = None
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Process grids with cache checking.

        Args:
            iso_code: Country code (or province cache key like "TH_BKK")
            year: Year
            entity: Entity type
            grids: List of grid dictionaries
            region_bbox: Optional bbox for region (province) analysis. If provided, used instead of country bbox.

        Returns:
            List of grid results
        """
        results = []
        # Track per-grid: which modules still need processing, and what's already cached
        modules_to_run_per_grid = {}   # chunk_id -> set of modules to run
        partial_cache_per_grid = {}    # chunk_id -> existing cached dict (None = full miss)

        for grid in grids:
            row = grid['row']
            col = grid['col']
            chunk_id = grid['chunk_id']

            cached = self._get_from_cache(iso_code, row, col, year, entity)
            missing = self._get_missing_modules(cached)

            if not missing:
                # Full hit: all enabled modules are already cached
                logger.debug(f"Cache hit (complete): {iso_code} grid {row}_{col} {year} {entity}")
                results.append(cached)
            else:
                # Partial hit (some modules missing) or full miss
                if cached:
                    logger.debug(
                        f"Cache hit (partial): {iso_code} grid {row}_{col} {year} {entity} "
                        f"— missing modules: {missing}"
                    )
                results.append(None)
                modules_to_run_per_grid[chunk_id] = missing
                partial_cache_per_grid[chunk_id] = cached  # None for a full miss

        # Find indices that need processing
        indices_to_process = [
            i for i, r in enumerate(results) if r is None
        ]

        if not indices_to_process:
            logger.debug("All grids cached, no API calls needed")
            return results

        logger.debug(
            f"Processing {len(indices_to_process)}/{len(grids)} grids "
            f"(rest fully cached)"
        )

        # Process uncached or partially-cached grids
        grids_to_process = [grids[i] for i in indices_to_process]

        # Reset tag cache for this country-year-entity run
        self._tags_cache_for_current_run = None

        # Create processing function with first_grid flag for tag analysis.
        # Only the first grid that needs 'tags' triggers the (once-per-region) tag analysis.
        first_grid_in_list = grids_to_process[0] if grids_to_process else None
        def process_single_grid(grid):
            is_first_grid = (first_grid_in_list and
                           grid['row'] == first_grid_in_list['row'] and
                           grid['col'] == first_grid_in_list['col'])
            modules_for_grid = modules_to_run_per_grid.get(grid['chunk_id'], self.enabled_modules)
            return self._analyze_grid(
                iso_code, year, entity, grid, is_first_grid, region_bbox,
                filtered_chunks=grids, modules_to_run=modules_for_grid
            )

        # Process async
        grid_ids = [g['chunk_id'] for g in grids_to_process]
        args_list = [(g,) for g in grids_to_process]

        processed = await self.async_runner.process_grids(
            process_single_grid,
            grid_ids,
            *args_list
        )

        # Merge processed results back, combining with any existing partial cache
        for idx, proc_idx in enumerate(indices_to_process):
            result = processed[idx]
            grid = grids[proc_idx]
            existing_cached = partial_cache_per_grid.get(grid['chunk_id'])

            if result is not None:
                # Merge new module results into existing cached data (if partial hit)
                if existing_cached is not None:
                    merged = dict(existing_cached)
                    merged.update(result)  # Only keys that were actually processed
                    result = merged

                results[proc_idx] = result
                self._store_in_cache(iso_code, grid['row'], grid['col'], year, entity, result)
            # If result is None (analysis failed), leave results[proc_idx] as None

        # Back-fill tag data into grids where tags ran but returned None (API failure).
        # Only backfill grids that have a 'tags' key explicitly set to None — grids whose
        # tags were already in the cache (partial hit) will have a non-None 'tags' value
        # and are intentionally skipped.
        if self._tags_cache_for_current_run:
            logger.info(f"Backfilling tag data to {len(indices_to_process)} grids")
            backfill_count = 0
            for idx, proc_idx in enumerate(indices_to_process):
                result = results[proc_idx]
                if result and 'tags' in result and result['tags'] is None:
                    result['tags'] = self._tags_cache_for_current_run
                    grid = grids[proc_idx]
                    self._store_in_cache(
                        iso_code, grid['row'], grid['col'], year, entity, result
                    )
                    backfill_count += 1
                    logger.debug(
                        f"Back-filled tags for {iso_code} grid {grid['row']}_{grid['col']} {year} {entity}"
                    )
            logger.info(f"Backfilled tags to {backfill_count} grids")

        return results

    def _analyze_grid(
        self,
        iso_code: str,
        year: int,
        entity: str,
        grid: Dict,
        is_first_grid: bool = False,
        region_bbox: Optional[str] = None,
        filtered_chunks: Optional[List[Dict]] = None,
        modules_to_run: Optional[set] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a single grid (sync function for async runner).

        Args:
            iso_code: Country code
            year: Year
            entity: Entity type
            grid: Grid dictionary
            is_first_grid: Whether this is the first grid in filtered list (for tag analysis)
            region_bbox: Optional bbox for region analysis
            filtered_chunks: Optional pre-filtered chunk list for tag analysis
            modules_to_run: Override which modules to run (defaults to self.enabled_modules).
                            Only keys for modules that actually ran are included in the result,
                            so callers can safely merge with existing cached data.

        Returns:
            Grid analysis result or None
        """
        run_modules = modules_to_run if modules_to_run is not None else self.enabled_modules

        try:
            from utils.grid_utils import get_country_bbox

            # Get bbox for analysis (use region_bbox if provided, otherwise lookup country bbox)
            if region_bbox:
                analysis_bbox = region_bbox
            else:
                # Extract base country code (handle province-level codes like "TH_BKK")
                base_country_code = iso_code.split('_')[0] if '_' in iso_code else iso_code
                analysis_bbox = get_country_bbox(base_country_code)

            result = {}

            # Geometric complexity (per grid) - only if in run_modules
            if self.geom_adapter and 'geometric' in run_modules:
                try:
                    geom_result = self.geom_adapter.analyze_grid(
                        grid['bbox'], entity, year, grid['chunk_id']
                    )
                    result['geometric'] = geom_result
                except Exception as e:
                    logger.error(f"Grid {grid['chunk_id']}: Geometric analysis failed: {e}")
                    result['geometric'] = None

            # Semantic tags (whole region, only on first grid to avoid duplication)
            # Only runs if 'tags' is in run_modules
            if 'tags' in run_modules:
                if self.tags_adapter and is_first_grid:
                    try:
                        region_type = "region" if region_bbox else "country"
                        logger.info(f"{iso_code} {year} {entity}: Starting tag analysis (once per {region_type})")
                        tags_result = self.tags_adapter.analyze_country(
                            analysis_bbox, entity, year, iso_code,
                            filtered_chunks=filtered_chunks
                        )
                        self._tags_cache_for_current_run = tags_result
                        result['tags'] = tags_result
                    except Exception as e:
                        logger.error(f"{iso_code}: Tag analysis failed: {e}")
                        self._tags_cache_for_current_run = None
                        result['tags'] = None
                else:
                    # Reuse tag result from first grid
                    result['tags'] = getattr(self, '_tags_cache_for_current_run', None)

            return result

        except Exception as e:
            logger.error(f"Grid analysis failed: {e}", exc_info=True)
            return None

    # Fields that must be non-zero for a module's result to be considered valid.
    # If all sentinel fields are zero/None, the module is treated as missing and re-run.
    _MODULE_SENTINELS = {
        'geometric': 'entity_count',
        'tags':      'unique_tags_count',  # entity_count is populated even on failed tag runs
    }

    def _get_missing_modules(self, cached: Optional[Dict]) -> set:
        """
        Return the subset of enabled_modules not yet present in cached data.

        A module is considered present if its key exists, is not None/empty, and
        its sentinel field is non-zero (guards against cached all-zero failure results).
        """
        if cached is None:
            return set(self.enabled_modules)

        missing = set()
        for m in self.enabled_modules:
            data = cached.get(m)
            if not data:
                missing.add(m)
                continue
            # Check sentinel: if the key field is 0 the result was a failed run
            sentinel = self._MODULE_SENTINELS.get(m)
            if sentinel and not data.get(sentinel):
                missing.add(m)
        return missing

    def _get_from_cache(
        self,
        iso_code: str,
        row: int,
        col: int,
        year: int,
        entity: str
    ) -> Optional[Dict]:
        """Get grid result from cache."""
        return self.cache.get(iso_code, row, col, year, entity, "combined", self.chunk_size_km)

    def _store_in_cache(
        self,
        iso_code: str,
        row: int,
        col: int,
        year: int,
        entity: str,
        data: Dict
    ):
        """Store grid result in cache."""
        self.cache.set(iso_code, row, col, year, entity, "combined", data, self.chunk_size_km)

    # Columns owned by each module in the primary CSV.
    # When a module is not in enabled_modules, its columns are preserved from
    # any existing CSV row rather than overwritten with zeros.
    _MODULE_COLUMNS = {
        'geometric':    {'entity_count', 'geometric_complexity', 'gps_road_count', 'gps_road_pct'},
        'tags':         {'unique_tags_count', 'richness_mean', 'richness_median', 'evenness', 'shannon_index'},
        'completeness': {'completeness_score'},
    }

    def _write_primary_csv(
        self,
        iso_code: str,
        rows: List[Dict]
    ) -> Path:
        """
        Write primary country CSV, merging with existing data if present.

        For rows with the same (country, year, entity) key, performs a column-level
        merge: columns owned by modules that were NOT run this time are preserved
        from the existing CSV rather than overwritten with zeros.
        """
        import pandas as pd

        new_df = self.aggregator.create_country_dataframe(rows)

        # Always write to the canonical filename (no module suffix).
        # Column-level merge preserves columns from modules not run this time,
        # so a single th.csv accumulates all module results safely.
        filepath = self.results_dir / f"{iso_code.lower()}.csv"

        # Look for existing data to merge from — may be a different directory than output
        merge_source = self.merge_from_dir / f"{iso_code.lower()}.csv"
        if not merge_source.exists() and filepath.exists():
            merge_source = filepath  # Fall back to the output file itself

        if merge_source.exists():
            logger.debug(f"Existing CSV found for merge: {merge_source}")
            try:
                existing_df = pd.read_csv(merge_source)
            except Exception as e:
                logger.error(f"Error reading existing CSV for merge: {e}")
                existing_df = pd.DataFrame()

            if not existing_df.empty and not new_df.empty:
                merge_keys = ['country', 'year', 'entity']

                # Columns from modules that did NOT run this time → preserve from existing
                preserve_cols = set()
                for module, cols in self._MODULE_COLUMNS.items():
                    if module not in self.enabled_modules:
                        preserve_cols.update(cols)

                existing_key_col = existing_df[merge_keys].apply(tuple, axis=1)
                new_key_col = new_df[merge_keys].apply(tuple, axis=1)

                # Rows in existing that are not touched by the new run → keep as-is
                rows_to_keep = existing_df[~existing_key_col.isin(new_key_col)]

                # For rows that exist in both, fill in preserved columns from existing
                if preserve_cols:
                    existing_overlap = (
                        existing_df[existing_key_col.isin(new_key_col)]
                        .set_index(merge_keys)
                    )
                    updated_rows = []
                    for _, new_row in new_df.iterrows():
                        key = tuple(new_row[k] for k in merge_keys)
                        if key in existing_overlap.index:
                            existing_row = existing_overlap.loc[key]
                            merged_row = new_row.copy()
                            for col in preserve_cols:
                                if col in existing_row.index and col in new_df.columns:
                                    existing_val = existing_row[col]
                                    if not pd.isna(existing_val):
                                        merged_row[col] = existing_val
                            updated_rows.append(merged_row)
                        else:
                            updated_rows.append(new_row)
                    updated_df = pd.DataFrame(updated_rows, columns=new_df.columns)
                else:
                    updated_df = new_df

                combined_df = pd.concat([rows_to_keep, updated_df], ignore_index=True)
            else:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)

            combined_df = combined_df.sort_values(['country', 'year', 'entity'])
            combined_df = combined_df.reset_index(drop=True)
            logger.debug(f"Merged CSV: {len(combined_df)} total rows")
        else:
            combined_df = new_df
            logger.debug(f"Creating new CSV: {filepath}")

        combined_df.to_csv(filepath, index=False)
        logger.debug(f"Wrote primary CSV: {filepath} ({len(combined_df)} rows)")
        return filepath

    def _write_detail_csv(
        self,
        iso_code: str,
        rows: List[Dict]
    ) -> Path:
        """
        Write tag details CSV, merging with existing data if present.

        Merges based on (country, year, entity, tag_key) key to avoid duplicates.
        """
        import pandas as pd

        new_df = self.aggregator.create_tag_details_dataframe(rows)

        # Generate suffix based on enabled modules
        filepath = self.results_dir / f"{iso_code.lower()}_tags_detail.csv"

        # Nothing new to write — tags module did not run this time.
        # Leave any existing file untouched rather than overwriting with an empty frame.
        if new_df.empty:
            logger.debug(f"No tag details produced for {iso_code} — skipping detail CSV write")
            return filepath

        merge_source = self.merge_from_dir / f"{iso_code.lower()}_tags_detail.csv"
        if not merge_source.exists() and filepath.exists():
            merge_source = filepath

        if merge_source.exists():
            logger.debug(f"Existing tag detail CSV found for merge: {merge_source}")
            try:
                existing_df = pd.read_csv(merge_source)
                # Guard against empty/corrupted files that parse with no columns
                if existing_df.empty or 'country' not in existing_df.columns:
                    logger.warning(f"Tag detail CSV appears empty or malformed, ignoring: {merge_source}")
                    existing_df = pd.DataFrame()
            except Exception as e:
                logger.error(f"Error reading tag detail CSV for merge: {e}")
                existing_df = pd.DataFrame()

            # Merge: new data overwrites existing for same keys
            merge_keys = ['country', 'year', 'entity', 'tag_key']

            if not existing_df.empty:
                existing_keys = existing_df[merge_keys].apply(tuple, axis=1)
                new_keys = new_df[merge_keys].apply(tuple, axis=1)
                mask = ~existing_keys.isin(new_keys)
                existing_df = existing_df[mask]

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(
                ['country', 'year', 'entity', 'rank']
            ).reset_index(drop=True)

            logger.debug(
                f"Merged tags: {len(existing_df)} existing + {len(new_df)} new = "
                f"{len(combined_df)} total rows"
            )
        else:
            combined_df = new_df
            logger.debug(f"Creating new tag detail CSV: {filepath}")

        combined_df.to_csv(filepath, index=False)
        logger.debug(f"Wrote detail CSV: {filepath} ({len(combined_df)} rows)")
        return filepath

    def _write_innovation_csv(
        self,
        iso_code: str,
        rows: List[Dict]
    ) -> Path:
        """
        Write innovation CSV, merging with existing data if present.

        Merges based on (country, year, entity) key to avoid duplicates.
        """
        import pandas as pd

        columns = [
            'country', 'year', 'entity', 'entity_count',
            'new_keys_this_year', 'new_tag_pairs_this_year',
            'cumulative_keys', 'cumulative_tag_pairs',
            'tag_pairs_top1pct_count', 'tag_pairs_top5pct_count'
        ]

        new_df = pd.DataFrame(rows)
        # Keep only known columns (gracefully handle any extras)
        new_df = new_df[[c for c in columns if c in new_df.columns]]

        filepath = self.results_dir / f"{iso_code.lower()}_innovation.csv"

        merge_source = self.merge_from_dir / f"{iso_code.lower()}_innovation.csv"
        if not merge_source.exists() and filepath.exists():
            merge_source = filepath

        if merge_source.exists():
            logger.debug(f"Existing innovation CSV found for merge: {merge_source}")
            try:
                existing_df = pd.read_csv(merge_source)
            except Exception as e:
                logger.error(f"Error reading existing innovation CSV: {e}")
                existing_df = pd.DataFrame()

            merge_keys = ['country', 'year', 'entity']
            if not existing_df.empty and not new_df.empty:
                existing_keys = existing_df[merge_keys].apply(tuple, axis=1)
                new_keys_ser = new_df[merge_keys].apply(tuple, axis=1)
                existing_df = existing_df[~existing_keys.isin(new_keys_ser)]

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(
                ['country', 'year', 'entity']
            ).reset_index(drop=True)

            logger.debug(
                f"Merged innovation: {len(existing_df)} existing + "
                f"{len(new_df)} new = {len(combined_df)} total rows"
            )
        else:
            combined_df = new_df.sort_values(
                ['country', 'year', 'entity']
            ).reset_index(drop=True)
            logger.debug(f"Creating new innovation CSV: {filepath}")

        combined_df.to_csv(filepath, index=False)
        logger.debug(f"Wrote innovation CSV: {filepath} ({len(combined_df)} rows)")
        return filepath
