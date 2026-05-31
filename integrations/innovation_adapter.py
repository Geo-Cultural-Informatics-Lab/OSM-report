"""
Adapter for the innovation package.

Wraps ChunkedInnovationAnalyzer for use by the report orchestrator.

Unlike the geometric/tags adapters (which are called independently per year),
InnovationAdapter.analyze_all_years() receives the full list of years at once
because innovation metrics are inherently cross-year (cumulative tracking).

NOTE: Requires the innovation package to be installed:
    pip install -e ../innovation
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def suppress_stdout():
    """Context manager to suppress stdout (mirrors SemanticTagsAdapter)."""
    root_logger = logging.getLogger()
    if root_logger.level <= logging.DEBUG:
        yield
    else:
        old_stdout = sys.stdout
        devnull = None
        try:
            devnull = open(os.devnull, 'w')
            sys.stdout = devnull
            yield
        finally:
            sys.stdout = old_stdout
            if devnull is not None:
                try:
                    devnull.close()
                except Exception:
                    pass


# Import from innovation package (installed with pip install -e .)
from innovation.analysis.chunked_innovation_analysis import ChunkedInnovationAnalyzer
from innovation.core.ohsome_client import OhsomeClient


class InnovationAdapter:
    """
    Adapter wrapping ChunkedInnovationAnalyzer for the report orchestrator.

    Call analyze_all_years() once per country/entity with the full year list.
    Returns one metrics dict per year in chronological order.
    """

    # Maps report entity names to Ohsome filter keys
    _ENTITY_MAP = {
        'building': 'building',
        'road': 'highway',
        'highway': 'highway',
    }

    def __init__(
        self,
        chunk_size_km: float = 50,
        timeout: int = 30,
        cache_dir: Optional[str] = None
    ):
        """
        Args:
            chunk_size_km: Grid chunk size passed to ChunkedInnovationAnalyzer
            timeout: Ohsome API timeout in seconds
            cache_dir: Directory for innovation raw-data cache (separate from main cache)
        """
        with suppress_stdout():
            client = OhsomeClient(timeout=timeout)
            self.analyzer = ChunkedInnovationAnalyzer(
                ohsome_client=client,
                chunk_size_km=chunk_size_km,
                cache_dir=cache_dir
            )
        logger.debug(
            f"InnovationAdapter initialized (chunk_size={chunk_size_km}km, "
            f"timeout={timeout}s, cache_dir={cache_dir})"
        )

    def analyze_all_years(
        self,
        bbox: str,
        entity_type: str,
        years: List[int],
        iso_code: str,
        filtered_chunks: Optional[List[Dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run innovation analysis for all years for a given country/entity.

        Args:
            bbox:             Bounding box "min_lon,min_lat,max_lon,max_lat"
            entity_type:      Entity type ('building', 'road', or 'highway')
            years:            List of years (sorted internally)
            iso_code:         Country ISO code (for cache key and logging)
            filtered_chunks:  Optional pre-filtered land-area chunk list from PolygonFilter

        Returns:
            List of dicts, one per year (sorted ascending):
            {
                'country': str, 'year': int, 'entity': str,
                'entity_count': int,
                'new_keys_this_year': int,
                'new_tag_pairs_this_year': int,
                'cumulative_keys': int,
                'cumulative_tag_pairs': int,
                'tag_pairs_top1pct_count': int,
                'tag_pairs_top5pct_count': int
            }
        """
        entity_key = self._ENTITY_MAP.get(entity_type, entity_type)

        logger.info(
            f"{iso_code} {entity_type}: Innovation analysis "
            f"for {len(years)} years: {sorted(years)}"
        )

        try:
            with suppress_stdout():
                results = self.analyzer.analyze_all_years(
                    bbox=bbox,
                    entity_type=entity_key,
                    years=years,
                    iso_code=iso_code,
                    pre_filtered_chunks=filtered_chunks
                )

            logger.info(
                f"{iso_code} {entity_type}: Innovation analysis complete "
                f"({len(results)} year rows)"
            )
            return results

        except Exception as e:
            logger.error(
                f"Innovation analysis failed for {iso_code} {entity_type}: {e}",
                exc_info=True
            )
            # Return empty rows for each year rather than crashing the whole report
            return [
                {
                    'country': iso_code,
                    'year': year,
                    'entity': entity_key,
                    'entity_count': 0,
                    'new_keys_this_year': 0,
                    'new_tag_pairs_this_year': 0,
                    'cumulative_keys': 0,
                    'cumulative_tag_pairs': 0,
                    'tag_pairs_top1pct_count': 0,
                    'tag_pairs_top5pct_count': 0,
                }
                for year in sorted(years)
            ]
