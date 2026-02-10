"""
Adapter for tags_semantic_analysis project.

Wraps chunked tag analysis for unified report generation.

NOTE: This adapter requires tags_semantic_analysis to be in sys.path.
The orchestrator should add it before importing this module.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def suppress_stdout():
    """Context manager to suppress stdout (print statements)."""
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

# Import from tags_semantic_analysis package (installed with pip install -e .)
from tags_semantic_analysis.analysis.chunked_analysis import ChunkedTagAnalyzer
from tags_semantic_analysis.core.ohsome_client import OhsomeClient


class SemanticTagsAdapter:
    """
    Adapter for tags_semantic_analysis with chunking support.
    """

    def __init__(self, chunk_size_km: float = 50, timeout: int = 30):
        """
        Initialize semantic tags adapter.

        Args:
            chunk_size_km: Grid chunk size in km
            timeout: API request timeout in seconds (default: 30)
        """
        self.client = OhsomeClient(timeout=timeout)
        self.analyzer = ChunkedTagAnalyzer(
            ohsome_client=self.client,
            chunk_size_km=chunk_size_km
        )

        logger.info(f"SemanticTagsAdapter initialized with {timeout}s timeout")

    def analyze_country(
        self,
        bbox: str,
        entity_type: str,
        year: int,
        iso_code: str
    ) -> Dict[str, Any]:
        """
        Analyze tag richness and diversity for a country.

        Args:
            bbox: Country bounding box
            entity_type: Entity type (building/highway)
            year: Year
            iso_code: Country ISO code for logging

        Returns:
            Dictionary with aggregate metrics and tag details
        """
        try:
            # Map entity types
            entity_map = {
                'building': 'building',
                'road': 'highway',
                'highway': 'highway'
            }

            entity_key = entity_map.get(entity_type, entity_type)

            # Format timestamp
            timestamp = f"{year}-01-01"

            logger.debug(
                f"{iso_code} {year} {entity_type}: Starting tag semantic analysis (bbox: {bbox})"
            )

            # Run chunked analysis
            # Suppress print() statements from sub-project
            logger.debug(f"{iso_code} {year} {entity_type}: Fetching tag data from API...")
            with suppress_stdout():
                results = self.analyzer.run_chunked_analysis(
                    bbox=bbox,
                    entity_type=entity_key,
                    timestamp=timestamp,
                    top_tags_set=None,  # Will identify automatically
                    percentile=95  # Top 5%
                )

            entity_count = results.get('entity_count', 0)
            unique_tags = results.get('unique_tags_count', 0)
            richness_mean = results.get('richness_mean', 0.0)

            logger.debug(
                f"{iso_code} {year} {entity_type}: Processed {entity_count} entities, "
                f"{unique_tags} unique tags, richness={richness_mean:.2f}"
            )

            return {
                'entity_count': entity_count,
                'unique_tags_count': unique_tags,
                'richness_mean': richness_mean,
                'richness_median': results.get('richness_median', 0.0),
                'evenness': results.get('evenness', 0.0),
                'shannon_index': results.get('shannon_index', 0.0),
                'tag_details': results.get('tag_details', [])
            }

        except Exception as e:
            logger.error(
                f"Tag semantic analysis failed for {iso_code} {entity_type} {year}: {e}",
                exc_info=True
            )
            return {
                'entity_count': 0,
                'unique_tags_count': 0,
                'richness_mean': 0.0,
                'richness_median': 0.0,
                'evenness': 0.0,
                'shannon_index': 0.0,
                'tag_details': []
            }

    def get_tag_details_for_csv(
        self,
        tag_details: List[Dict],
        iso_code: str,
        year: int,
        entity_type: str
    ) -> List[Dict[str, Any]]:
        """
        Format tag details for CSV output.

        Args:
            tag_details: List of tag detail dictionaries
            iso_code: Country code
            year: Year
            entity_type: Entity type

        Returns:
            List of formatted tag detail rows
        """
        rows = []
        for tag in tag_details:
            rows.append({
                'country': iso_code,
                'year': year,
                'entity': entity_type,
                'tag_key': tag['tag_key'],
                'frequency': tag['frequency'],
                'proportion': tag['proportion'],
                'rank': tag['rank'],
                'in_top5pct': tag.get('in_top5pct', False)
            })
        return rows
