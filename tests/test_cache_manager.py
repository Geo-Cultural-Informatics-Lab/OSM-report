"""
Tests for cache manager.
"""
import json
import pytest
import tempfile
import shutil
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.cache_manager import CacheManager


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create cache manager with temp directory."""
    return CacheManager(cache_dir=temp_cache_dir)


def test_cache_manager_init(temp_cache_dir):
    """Test cache manager initialization."""
    cache_mgr = CacheManager(cache_dir=temp_cache_dir)
    assert cache_mgr.cache_dir.exists()
    assert cache_mgr.cache_dir.is_dir()


def test_cache_key_generation(cache_manager):
    """Test cache key generation."""
    key = cache_manager._get_cache_key(
        iso="TH",
        grid_row=0,
        grid_col=1,
        year=2020,
        entity="building",
        metric_type="geom"
    )
    assert key == "TH_grid_0_1_2020_building_geom.json"


def test_cache_set_and_get(cache_manager):
    """Test storing and retrieving cache."""
    test_data = {
        "entity_count": 1000,
        "mean_complexity": 0.42,
        "tags": ["building", "amenity"]
    }

    # Store data
    cache_manager.set(
        iso="TH",
        grid_row=0,
        grid_col=0,
        year=2020,
        entity="building",
        metric_type="metrics",
        data=test_data
    )

    # Retrieve data
    retrieved = cache_manager.get(
        iso="TH",
        grid_row=0,
        grid_col=0,
        year=2020,
        entity="building",
        metric_type="metrics"
    )

    assert retrieved is not None
    assert retrieved["entity_count"] == 1000
    assert retrieved["mean_complexity"] == 0.42
    assert retrieved["tags"] == ["building", "amenity"]


def test_cache_exists(cache_manager):
    """Test cache existence check."""
    # Should not exist initially
    assert not cache_manager.exists(
        iso="TH",
        grid_row=0,
        grid_col=0,
        year=2020,
        entity="building",
        metric_type="geom"
    )

    # Store data
    cache_manager.set(
        iso="TH",
        grid_row=0,
        grid_col=0,
        year=2020,
        entity="building",
        metric_type="geom",
        data={"test": "data"}
    )

    # Should exist now
    assert cache_manager.exists(
        iso="TH",
        grid_row=0,
        grid_col=0,
        year=2020,
        entity="building",
        metric_type="geom"
    )


def test_cache_get_nonexistent(cache_manager):
    """Test retrieving non-existent cache."""
    result = cache_manager.get(
        iso="XX",
        grid_row=99,
        grid_col=99,
        year=2099,
        entity="unknown",
        metric_type="test"
    )
    assert result is None


def test_cache_clear_all(cache_manager):
    """Test clearing all cache."""
    # Store multiple cache entries
    for i in range(3):
        cache_manager.set(
            iso="TH",
            grid_row=i,
            grid_col=0,
            year=2020,
            entity="building",
            metric_type="metrics",
            data={"index": i}
        )

    # Clear all
    deleted = cache_manager.clear()
    assert deleted == 3

    # Verify all deleted
    for i in range(3):
        assert not cache_manager.exists(
            iso="TH",
            grid_row=i,
            grid_col=0,
            year=2020,
            entity="building",
            metric_type="metrics"
        )


def test_cache_clear_filtered(cache_manager):
    """Test clearing cache with filters."""
    # Store entries for different countries and years
    cache_manager.set("TH", 0, 0, 2020, "building", "metrics", {"a": 1})
    cache_manager.set("TH", 0, 1, 2021, "building", "metrics", {"b": 2})
    cache_manager.set("MM", 0, 0, 2020, "building", "metrics", {"c": 3})
    cache_manager.set("TH", 0, 0, 2020, "road", "metrics", {"d": 4})

    # Clear only TH 2020 building
    deleted = cache_manager.clear(iso="TH", year=2020, entity="building")
    assert deleted == 1

    # Verify correct ones remain
    assert cache_manager.exists("TH", 0, 1, 2021, "building", "metrics")
    assert cache_manager.exists("MM", 0, 0, 2020, "building", "metrics")
    assert cache_manager.exists("TH", 0, 0, 2020, "road", "metrics")
    assert not cache_manager.exists("TH", 0, 0, 2020, "building", "metrics")


def test_cache_stats(cache_manager):
    """Test cache statistics."""
    # Store some data
    for i in range(5):
        cache_manager.set(
            iso="TH",
            grid_row=i,
            grid_col=0,
            year=2020,
            entity="building",
            metric_type="metrics",
            data={"index": i, "data": "x" * 100}
        )

    stats = cache_manager.get_cache_stats()
    assert stats["total_files"] == 5
    assert stats["total_size_mb"] > 0
    assert "cache_dir" in stats


def test_cache_corrupted_file(cache_manager, temp_cache_dir):
    """Test handling of corrupted cache file."""
    # Create corrupted cache file
    cache_path = Path(temp_cache_dir) / "TH_grid_0_0_2020_building_metrics.json"
    with open(cache_path, 'w') as f:
        f.write("invalid json {{{")

    # Should return None for corrupted file
    result = cache_manager.get("TH", 0, 0, 2020, "building", "metrics")
    assert result is None


def test_cache_multiple_metric_types(cache_manager):
    """Test caching different metric types for same grid."""
    geom_data = {"type": "geometry", "features": []}
    tags_data = {"type": "tags", "richness": 3.2}
    metrics_data = {"type": "metrics", "complexity": 0.42}

    # Store all three types
    cache_manager.set("TH", 0, 0, 2020, "building", "geom", geom_data)
    cache_manager.set("TH", 0, 0, 2020, "building", "tags", tags_data)
    cache_manager.set("TH", 0, 0, 2020, "building", "metrics", metrics_data)

    # Retrieve and verify each type
    assert cache_manager.get("TH", 0, 0, 2020, "building", "geom")["type"] == "geometry"
    assert cache_manager.get("TH", 0, 0, 2020, "building", "tags")["type"] == "tags"
    assert cache_manager.get("TH", 0, 0, 2020, "building", "metrics")["type"] == "metrics"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
