"""
Adapter for geometric_complexity project.

Wraps geometric_complexity analysis for use in unified report generation.

NOTE: This adapter requires geometric_complexity to be in sys.path.
The orchestrator should add it before importing this module.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def suppress_stdout():
    """Context manager to suppress stdout (print statements)."""
    # Check if verbose logging is enabled by checking root logger level
    root_logger = logging.getLogger()
    if root_logger.level <= logging.DEBUG:
        # Verbose mode - don't suppress
        yield
    else:
        # Normal mode - suppress stdout
        old_stdout = sys.stdout
        devnull = None
        try:
            devnull = open(os.devnull, 'w')
            sys.stdout = devnull
            yield
        finally:
            # Restore stdout first
            sys.stdout = old_stdout
            # Then close devnull
            if devnull is not None:
                try:
                    devnull.close()
                except:
                    pass


# Import from geometric_complexity package (installed with pip install -e .)
from geometric_complexity.core import analyzer
from geometric_complexity.core.ohsome_client import OhsomeClient


class GeometricComplexityAdapter:
    """
    Adapter for geometric_complexity analysis.
    """

    def __init__(self, timeout: int = 30):
        """
        Initialize geometric complexity adapter.

        Args:
            timeout: API request timeout in seconds (default: 30)
        """
        # Suppress stdout during initialization to avoid print() statements
        with suppress_stdout():
            self.client = OhsomeClient(timeout=timeout)
        logger.debug(f"GeometricComplexityAdapter initialized with {timeout}s timeout")

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

            logger.debug(f"Grid {grid_id}: Starting {entity_key} analysis for {year} (bbox: {bbox})")

            # Use analyze_region_buildings/roads functions
            # Suppress print() statements from sub-project
            with suppress_stdout():
                if entity_key == 'buildings':
                    logger.debug(f"Grid {grid_id}: Fetching building geometries from API...")
                    results = analyzer.analyze_region_buildings(
                        region_name=grid_id,
                        bounds=bbox,
                        timestamp=timestamp,
                        resume=False
                    )
                else:
                    # For roads - use 'bbox' parameter and no 'resume' parameter
                    logger.debug(f"Grid {grid_id}: Fetching road geometries from API...")
                    results = analyzer.analyze_region_roads(
                        region_name=grid_id,
                        bbox=bbox,
                        timestamp=timestamp
                    )

            if results is None or results.empty:
                logger.warning(f"Grid {grid_id}: No results returned from API")
                return None

            # Extract mean complexity ratio
            mean_ratio = results['mean_ratio'].iloc[0] if 'mean_ratio' in results.columns else 0.0
            entity_count = results['building_count'].iloc[0] if 'building_count' in results.columns else 0

            logger.debug(f"Grid {grid_id}: Processed {int(entity_count)} {entity_key}, complexity={mean_ratio:.4f}")

            return {
                'grid_id': grid_id,
                'entity_count': int(entity_count),
                'geometric_complexity': float(mean_ratio),
                'raw_results': results.to_dict('records')[0] if len(results) > 0 else {}
            }

        except Exception as e:
            logger.error(f"Grid {grid_id}: Geometric complexity analysis failed: {e}")
            return None
