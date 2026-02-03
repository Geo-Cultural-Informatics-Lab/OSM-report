"""
Cache manager for grid-level results.

Handles caching of Ohsome API responses and calculated metrics
to avoid redundant API calls and computations.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import hashlib


class CacheManager:
    """Manages disk-based caching for grid analysis results."""

    def __init__(self, cache_dir: str = "./cache"):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(
        self,
        iso: str,
        grid_row: int,
        grid_col: int,
        year: int,
        entity: str,
        metric_type: str
    ) -> str:
        """
        Generate cache key for a grid result.

        Args:
            iso: Country ISO code
            grid_row: Grid row index
            grid_col: Grid column index
            year: Year
            entity: Entity type (building/road)
            metric_type: Type of metric (geom/tags/metrics)

        Returns:
            Cache key string
        """
        return f"{iso}_grid_{grid_row}_{grid_col}_{year}_{entity}_{metric_type}.json"

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get full path for cache file."""
        return self.cache_dir / cache_key

    def get(
        self,
        iso: str,
        grid_row: int,
        grid_col: int,
        year: int,
        entity: str,
        metric_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached data.

        Args:
            iso: Country ISO code
            grid_row: Grid row index
            grid_col: Grid column index
            year: Year
            entity: Entity type
            metric_type: Type of metric

        Returns:
            Cached data or None if not found
        """
        cache_key = self._get_cache_key(iso, grid_row, grid_col, year, entity, metric_type)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load cache {cache_key}: {e}")
            return None

    def set(
        self,
        iso: str,
        grid_row: int,
        grid_col: int,
        year: int,
        entity: str,
        metric_type: str,
        data: Dict[str, Any]
    ) -> None:
        """
        Store data in cache.

        Args:
            iso: Country ISO code
            grid_row: Grid row index
            grid_col: Grid column index
            year: Year
            entity: Entity type
            metric_type: Type of metric
            data: Data to cache
        """
        cache_key = self._get_cache_key(iso, grid_row, grid_col, year, entity, metric_type)
        cache_path = self._get_cache_path(cache_key)

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Failed to write cache {cache_key}: {e}")

    def exists(
        self,
        iso: str,
        grid_row: int,
        grid_col: int,
        year: int,
        entity: str,
        metric_type: str
    ) -> bool:
        """
        Check if cached data exists.

        Args:
            iso: Country ISO code
            grid_row: Grid row index
            grid_col: Grid column index
            year: Year
            entity: Entity type
            metric_type: Type of metric

        Returns:
            True if cache exists
        """
        cache_key = self._get_cache_key(iso, grid_row, grid_col, year, entity, metric_type)
        cache_path = self._get_cache_path(cache_key)
        return cache_path.exists()

    def clear(
        self,
        iso: Optional[str] = None,
        year: Optional[int] = None,
        entity: Optional[str] = None
    ) -> int:
        """
        Clear cache files matching criteria.

        Args:
            iso: Optional country filter
            year: Optional year filter
            entity: Optional entity filter

        Returns:
            Number of files deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            parts = cache_file.stem.split('_')
            # Format: {iso}_grid_{row}_{col}_{year}_{entity}_{metric_type}
            if len(parts) >= 6:
                file_iso = parts[0]
                file_year = int(parts[4]) if parts[4].isdigit() else None
                file_entity = parts[5]

                # Check filters
                if iso and file_iso != iso:
                    continue
                if year and file_year != year:
                    continue
                if entity and file_entity != entity:
                    continue

                cache_file.unlink()
                count += 1

        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "total_files": len(cache_files),
            "total_size_mb": total_size / (1024 * 1024),
            "cache_dir": str(self.cache_dir)
        }
