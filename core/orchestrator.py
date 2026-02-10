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
        chunk_size_km: float = 50,
        max_concurrent: int = 10,
        api_timeout: int = 30
    ):
        """
        Initialize orchestrator.

        Args:
            cache_dir: Cache directory
            results_dir: Results output directory
            chunk_size_km: Grid chunk size in km
            max_concurrent: Max concurrent requests
            api_timeout: API request timeout in seconds (default: 30)
        """
        self.cache_dir = Path(cache_dir)
        self.results_dir = Path(results_dir)
        self.chunk_size_km = chunk_size_km
        self.max_concurrent = max_concurrent
        self.api_timeout = api_timeout

        # Create directories
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.cache = CacheManager(cache_dir=str(cache_dir))
        self.aggregator = MetricsAggregator()
        self.async_runner = AsyncGridRunner(max_concurrent=max_concurrent)
        self.polygon_filter = PolygonFilter()  # Auto-finds World_Countries.geojson

        # Initialize adapters
        # Import adapters here (after bootstrap has run) to ensure packages are available
        try:
            from integrations.geometric_complexity_adapter import GeometricComplexityAdapter
            self.geom_adapter = GeometricComplexityAdapter(timeout=api_timeout)
            logger.info("GeometricComplexityAdapter initialized successfully")
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
            logger.info("SemanticTagsAdapter initialized successfully")
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

        logger.info(f"Orchestrator initialized: cache={cache_dir}, results={results_dir}")

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
                pbar.set_description(f"[{iso_code}] {year} {entity}")
                logger.info(f"Processing {iso_code} {year} {entity}")

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
                    # Add empty row to maintain consistency
                    all_rows.append(
                        self.aggregator._empty_metrics(iso_code, year, entity)
                    )
                finally:
                    pbar.update(1)

        pbar.close()

        # Write CSVs
        primary_file = self._write_primary_csv(iso_code, all_rows)
        detail_file = self._write_detail_csv(iso_code, all_tag_details)

        logger.info(
            f"Report complete for {iso_code}: "
            f"{len(all_rows)} rows, {len(all_tag_details)} tag details"
        )

        return {
            'country': iso_code,
            'total_rows': len(all_rows),
            'total_tag_details': len(all_tag_details),
            'primary_file': str(primary_file),
            'detail_file': str(detail_file)
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

        logger.info(f"{iso_code} {year} {entity}: Split into {len(grids)} grids")

        # Filter grids to only those that intersect with country polygon
        grids = self.polygon_filter.filter_grids(grids, iso_code)

        logger.info(f"{iso_code} {year} {entity}: Processing {len(grids)} grids after polygon filtering")

        # Process grids (check cache first, then analyze)
        grid_results = await self._process_grids_with_cache(
            iso_code, year, entity, grids
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
        grids: List[Dict]
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Process grids with cache checking.

        Args:
            iso_code: Country code
            year: Year
            entity: Entity type
            grids: List of grid dictionaries

        Returns:
            List of grid results
        """
        results = []

        for grid in grids:
            row = grid['row']
            col = grid['col']

            # Check cache (include chunk size for correct cache lookup)
            cached = self._get_from_cache(iso_code, row, col, year, entity)

            if cached:
                logger.debug(f"Cache hit: {iso_code} grid {row}_{col} {year} {entity}")
                results.append(cached)
            else:
                # Mark for processing
                results.append(None)

        # Find indices that need processing
        indices_to_process = [
            i for i, r in enumerate(results) if r is None
        ]

        if not indices_to_process:
            logger.info("All grids cached, no API calls needed")
            return results

        logger.info(
            f"Processing {len(indices_to_process)}/{len(grids)} grids "
            f"(rest cached)"
        )

        # Process uncached grids
        grids_to_process = [grids[i] for i in indices_to_process]

        # Create processing function
        def process_single_grid(grid):
            return self._analyze_grid(iso_code, year, entity, grid)

        # Process async
        grid_ids = [g['chunk_id'] for g in grids_to_process]
        args_list = [(g,) for g in grids_to_process]

        processed = await self.async_runner.process_grids(
            process_single_grid,
            grid_ids,
            *args_list
        )

        # Merge processed results back
        for idx, proc_idx in enumerate(indices_to_process):
            result = processed[idx]
            results[proc_idx] = result

            # Cache successful results
            if result:
                grid = grids[proc_idx]
                self._store_in_cache(
                    iso_code, grid['row'], grid['col'], year, entity, result
                )

        return results

    def _analyze_grid(
        self,
        iso_code: str,
        year: int,
        entity: str,
        grid: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a single grid (sync function for async runner).

        Args:
            iso_code: Country code
            year: Year
            entity: Entity type
            grid: Grid dictionary

        Returns:
            Grid analysis result or None
        """
        try:
            from utils.grid_utils import get_country_bbox

            # Get country bbox for semantic analysis
            country_bbox = get_country_bbox(iso_code)

            result = {}

            # Geometric complexity (per grid)
            if self.geom_adapter:
                try:
                    geom_result = self.geom_adapter.analyze_grid(
                        grid['bbox'], entity, year, grid['chunk_id']
                    )
                    result['geometric'] = geom_result
                except Exception as e:
                    logger.error(f"Grid {grid['chunk_id']}: Geometric analysis failed: {e}")
                    result['geometric'] = None
            else:
                result['geometric'] = None

            # Semantic tags (whole country, only on first grid to avoid duplication)
            if self.tags_adapter and grid['row'] == 0 and grid['col'] == 0:
                try:
                    logger.info(f"{iso_code} {year} {entity}: Starting tag analysis (once per country)")
                    tags_result = self.tags_adapter.analyze_country(
                        country_bbox, entity, year, iso_code
                    )
                    result['tags'] = tags_result
                except Exception as e:
                    logger.error(f"{iso_code}: Tag analysis failed: {e}")
                    result['tags'] = None
            else:
                result['tags'] = None
            return result

        except Exception as e:
            logger.error(f"Grid analysis failed: {e}", exc_info=True)
            return None

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

    def _write_primary_csv(
        self,
        iso_code: str,
        rows: List[Dict]
    ) -> Path:
        """
        Write primary country CSV, merging with existing data if present.

        Merges based on (country, year, entity) key to avoid duplicates.
        """
        import pandas as pd

        new_df = self.aggregator.create_country_dataframe(rows)
        filepath = self.results_dir / f"{iso_code.lower()}.csv"

        # Check if file exists
        if filepath.exists():
            logger.info(f"Existing CSV found, merging data: {filepath}")
            existing_df = pd.read_csv(filepath)

            # Merge: new data overwrites existing for same (country, year, entity)
            # Remove rows from existing that match new data
            merge_keys = ['country', 'year', 'entity']

            # Create a key for matching
            if not existing_df.empty and not new_df.empty:
                # Remove existing rows that will be replaced
                existing_keys = existing_df[merge_keys].apply(tuple, axis=1)
                new_keys = new_df[merge_keys].apply(tuple, axis=1)
                mask = ~existing_keys.isin(new_keys)
                existing_df = existing_df[mask]

            # Combine
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)

            # Sort by country, year, entity
            combined_df = combined_df.sort_values(['country', 'year', 'entity'])
            combined_df = combined_df.reset_index(drop=True)

            logger.info(
                f"Merged: {len(existing_df)} existing + {len(new_df)} new = "
                f"{len(combined_df)} total rows"
            )
        else:
            combined_df = new_df
            logger.info(f"Creating new CSV: {filepath}")

        combined_df.to_csv(filepath, index=False)
        logger.info(f"Wrote primary CSV: {filepath} ({len(combined_df)} rows)")
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
        filepath = self.results_dir / f"{iso_code.lower()}_tags_detail.csv"

        # Check if file exists
        if filepath.exists():
            logger.info(f"Existing tag detail CSV found, merging: {filepath}")
            existing_df = pd.read_csv(filepath)

            # Merge: new data overwrites existing for same keys
            merge_keys = ['country', 'year', 'entity', 'tag_key']

            if not existing_df.empty and not new_df.empty:
                # Remove existing rows that will be replaced
                existing_keys = existing_df[merge_keys].apply(tuple, axis=1)
                new_keys = new_df[merge_keys].apply(tuple, axis=1)
                mask = ~existing_keys.isin(new_keys)
                existing_df = existing_df[mask]

            # Combine
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)

            # Sort by country, year, entity, rank
            combined_df = combined_df.sort_values(
                ['country', 'year', 'entity', 'rank']
            )
            combined_df = combined_df.reset_index(drop=True)

            logger.info(
                f"Merged tags: {len(existing_df)} existing + {len(new_df)} new = "
                f"{len(combined_df)} total rows"
            )
        else:
            combined_df = new_df
            logger.info(f"Creating new tag detail CSV: {filepath}")

        combined_df.to_csv(filepath, index=False)
        logger.info(f"Wrote detail CSV: {filepath} ({len(combined_df)} rows)")
        return filepath
