"""
Aggregation logic for grid results.

Combines grid-level metrics into country-level aggregates.
"""

import pandas as pd
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MetricsAggregator:
    """
    Aggregates grid-level metrics into country-level metrics.
    """

    def __init__(self):
        """Initialize metrics aggregator."""
        pass

    def aggregate_grids(
        self,
        grid_results: List[Dict[str, Any]],
        iso_code: str,
        year: int,
        entity_type: str
    ) -> Dict[str, Any]:
        """
        Aggregate grid results into country-level metrics.

        Args:
            grid_results: List of grid result dictionaries
            iso_code: Country code
            year: Year
            entity_type: Entity type

        Returns:
            Aggregated country metrics
        """
        if not grid_results:
            logger.warning(f"No grid results for {iso_code} {year} {entity_type}")
            return self._empty_metrics(iso_code, year, entity_type)

        # Filter out None results
        valid_results = [r for r in grid_results if r is not None]

        if not valid_results:
            logger.warning(f"All grids failed for {iso_code} {year} {entity_type}")
            return self._empty_metrics(iso_code, year, entity_type)

        # Aggregate geometric complexity (weighted mean)
        total_entities = sum(
            r.get('geometric', {}).get('entity_count', 0)
            for r in valid_results
        )

        if total_entities > 0:
            weighted_complexity = sum(
                r.get('geometric', {}).get('geometric_complexity', 0) *
                r.get('geometric', {}).get('entity_count', 0)
                for r in valid_results
            ) / total_entities
        else:
            weighted_complexity = 0.0

        # Get tag metrics from first valid result (already aggregated)
        # The semantic adapter should have aggregated across chunks
        tag_metrics = valid_results[0].get('tags', {})

        logger.info(
            f"{iso_code} {year} {entity_type}: Aggregated {len(valid_results)} grids, "
            f"total {total_entities:,} entities, complexity={weighted_complexity:.4f}"
        )

        return {
            'country': iso_code,
            'year': year,
            'entity': entity_type,
            'geometric_complexity': weighted_complexity,
            'unique_tags_count': tag_metrics.get('unique_tags_count', 0),
            'richness_mean': tag_metrics.get('richness_mean', 0.0),
            'richness_median': tag_metrics.get('richness_median', 0.0),
            'evenness': tag_metrics.get('evenness', 0.0),
            'shannon_index': tag_metrics.get('shannon_index', 0.0)
        }

    def extract_tag_details(
        self,
        grid_results: List[Dict[str, Any]],
        iso_code: str,
        year: int,
        entity_type: str
    ) -> List[Dict[str, Any]]:
        """
        Extract tag details for detailed CSV.

        Args:
            grid_results: List of grid result dictionaries
            iso_code: Country code
            year: Year
            entity_type: Entity type

        Returns:
            List of tag detail rows
        """
        valid_results = [r for r in grid_results if r is not None]

        if not valid_results:
            return []

        # Get tag details from first valid result
        # (semantic adapter already aggregated)
        tag_details = valid_results[0].get('tags', {}).get('tag_details', [])

        # Format for CSV
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

    def _empty_metrics(
        self,
        iso_code: str,
        year: int,
        entity_type: str
    ) -> Dict[str, Any]:
        """Return empty metrics for failed analysis."""
        return {
            'country': iso_code,
            'year': year,
            'entity': entity_type,
            'geometric_complexity': 0.0,
            'unique_tags_count': 0,
            'richness_mean': 0.0,
            'richness_median': 0.0,
            'evenness': 0.0,
            'shannon_index': 0.0
        }

    def create_country_dataframe(
        self,
        country_rows: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """
        Create DataFrame from country rows.

        Args:
            country_rows: List of country metric dictionaries

        Returns:
            DataFrame with country metrics
        """
        df = pd.DataFrame(country_rows)

        # Ensure column order
        columns = [
            'country', 'year', 'entity',
            'geometric_complexity',
            'unique_tags_count',
            'richness_mean', 'richness_median',
            'evenness', 'shannon_index'
        ]

        # Add future columns if they exist
        for col in df.columns:
            if col not in columns:
                columns.append(col)

        return df[columns]

    def create_tag_details_dataframe(
        self,
        tag_rows: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """
        Create DataFrame from tag detail rows.

        Args:
            tag_rows: List of tag detail dictionaries

        Returns:
            DataFrame with tag details
        """
        df = pd.DataFrame(tag_rows)

        # Ensure column order
        columns = [
            'country', 'year', 'entity',
            'tag_key', 'frequency', 'proportion',
            'rank', 'in_top5pct'
        ]

        return df[columns] if not df.empty else df
