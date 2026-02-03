"""
Adapter for geometric_complexity project.

Wraps geometric_complexity analysis for use in unified report generation.

NOTE: This adapter requires geometric_complexity to be in sys.path.
The orchestrator should add it before importing this module.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Import from geometric_complexity package (installed with pip install -e .)
from geometric_complexity.core import analyzer
from geometric_complexity.core.ohsome_client import OhsomeClient


class GeometricComplexityAdapter:
    """
    Adapter for geometric_complexity analysis.
    """

    def __init__(self):
        """Initialize geometric complexity adapter."""
        self.client = OhsomeClient()
        logger.info("GeometricComplexityAdapter initialized successfully")

    def analyze_grid(
        self,
        bbox: str,
        entity_type: str,
        year: int,
        grid_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze geometric complexity for a grid.

        Args:
            bbox: Bounding box string
            entity_type: Entity type (building/highway)
            year: Year
            grid_id: Grid identifier

        Returns:
            Dictionary with metrics or None if failed
        """
        try:
            # Convert entity_type to filter
            entity_map = {
                'building': 'buildings',
                'highway': 'highways',
                'road': 'highways'
            }

            entity_key = entity_map.get(entity_type, entity_type)

            # Format timestamp
            timestamp = f"{year}-01-01"

            logger.info(f"Grid {grid_id}: Starting {entity_key} analysis for {year} (bbox: {bbox})")

            # Use analyze_region_buildings/roads functions
            if entity_key == 'buildings':
                logger.info(f"Grid {grid_id}: Fetching building geometries from API...")
                results = analyzer.analyze_region_buildings(
                    region_name=grid_id,
                    bounds=bbox,
                    timestamp=timestamp,
                    resume=False
                )
            else:
                # For roads
                logger.info(f"Grid {grid_id}: Fetching road geometries from API...")
                results = analyzer.analyze_region_roads(
                    region_name=grid_id,
                    bounds=bbox,
                    timestamp=timestamp,
                    resume=False
                )

            if results is None or results.empty:
                logger.warning(f"Grid {grid_id}: No results returned from API")
                return None

            # Extract mean complexity ratio
            mean_ratio = results['mean_ratio'].iloc[0] if 'mean_ratio' in results.columns else 0.0
            entity_count = results['building_count'].iloc[0] if 'building_count' in results.columns else 0

            logger.info(f"Grid {grid_id}: Processed {int(entity_count)} {entity_key}, complexity={mean_ratio:.4f}")

            return {
                'grid_id': grid_id,
                'entity_count': int(entity_count),
                'geometric_complexity': float(mean_ratio),
                'raw_results': results.to_dict('records')[0] if len(results) > 0 else {}
            }

        except Exception as e:
            logger.error(f"Grid {grid_id}: Geometric complexity analysis failed: {e}")
            return None
