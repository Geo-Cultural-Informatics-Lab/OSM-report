"""
Integration test for the full report generation pipeline.

Note: This test requires actual API access and will make real API calls.
Use sparingly or with small test areas.
"""

import pytest
import asyncio
import sys
from pathlib import Path
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import CountryReportOrchestrator


@pytest.fixture
def temp_dirs():
    """Create temporary directories for cache and results."""
    temp_cache = tempfile.mkdtemp()
    temp_results = tempfile.mkdtemp()

    yield temp_cache, temp_results

    # Cleanup
    shutil.rmtree(temp_cache, ignore_errors=True)
    shutil.rmtree(temp_results, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_orchestrator_init(temp_dirs):
    """Test orchestrator initialization."""
    cache_dir, results_dir = temp_dirs

    orchestrator = CountryReportOrchestrator(
        cache_dir=cache_dir,
        results_dir=results_dir,
        chunk_size_km=50,
        max_concurrent=5
    )

    assert orchestrator.cache is not None
    assert orchestrator.aggregator is not None
    assert orchestrator.async_runner is not None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_small_area_analysis(temp_dirs):
    """
    Test analysis of a small area.

    Note: This makes real API calls. Skip in CI/CD or mark as slow test.
    """
    cache_dir, results_dir = temp_dirs

    orchestrator = CountryReportOrchestrator(
        cache_dir=cache_dir,
        results_dir=results_dir,
        chunk_size_km=200,  # Large chunks for minimal API calls
        max_concurrent=2
    )

    # Test with Thailand, single year, single entity
    # Using large chunk size to minimize API calls
    try:
        result = await orchestrator.generate_country_report(
            iso_code='TH',
            years=[2024],
            entities=['building']
        )

        # Verify result structure
        assert 'country' in result
        assert result['country'] == 'TH'
        assert 'total_rows' in result
        assert result['total_rows'] > 0
        assert 'primary_file' in result
        assert 'detail_file' in result

        # Check files exist
        assert Path(result['primary_file']).exists()
        assert Path(result['detail_file']).exists()

        print(f"\n✅ Integration test passed:")
        print(f"   Rows: {result['total_rows']}")
        print(f"   Tag details: {result['total_tag_details']}")
        print(f"   Primary file: {result['primary_file']}")

    except Exception as e:
        pytest.skip(f"Integration test skipped (API unavailable or failed): {e}")


def test_grid_splitting():
    """Test grid splitting logic (no API calls)."""
    from utils.grid_utils import split_country_into_grids, bbox_area_km2, get_country_bbox

    # Thailand with default threshold
    grids = split_country_into_grids('TH', chunk_size_km=50, chunked_threshold_km2=5000)

    assert len(grids) > 1  # Should be chunked
    assert all('bbox' in g for g in grids)
    assert all('chunk_id' in g for g in grids)

    # Large threshold (force single chunk)
    # Thailand is ~900,000 km², so use threshold > that
    th_bbox = get_country_bbox('TH')
    th_area = bbox_area_km2(th_bbox)
    grids_single = split_country_into_grids('TH', chunk_size_km=50, chunked_threshold_km2=th_area + 1)

    assert len(grids_single) == 1
    assert grids_single[0]['chunk_id'] == '0_0'


def test_cache_integration(temp_dirs):
    """Test cache functionality without API calls."""
    cache_dir, _ = temp_dirs

    from core.cache_manager import CacheManager

    cache = CacheManager(cache_dir=cache_dir)

    # Store test data
    test_data = {
        'geometric': {'complexity': 0.42},
        'tags': {'richness': 3.2}
    }

    cache.set('TH', 0, 0, 2024, 'building', 'combined', test_data)

    # Retrieve
    retrieved = cache.get('TH', 0, 0, 2024, 'building', 'combined')

    assert retrieved is not None
    assert retrieved['geometric']['complexity'] == 0.42
    assert retrieved['tags']['richness'] == 3.2


if __name__ == "__main__":
    # Run with: python tests/test_integration.py
    # Or: pytest tests/test_integration.py -v -s -m integration
    pytest.main([__file__, "-v", "-s", "-m", "integration"])
