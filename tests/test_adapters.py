"""
Tests for project adapters.

Note: These are basic unit tests. Full integration tests would require
actual API access and are better suited for end-to-end testing.
"""
import pytest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.completeness_adapter import CompletenessAdapter
from integrations.semantic_tags_adapter import SemanticTagsAdapter
from utils.grid_utils import get_country_bbox, split_country_into_grids


def test_completeness_adapter_init():
    """Test completeness adapter initialization."""
    adapter = CompletenessAdapter()
    assert adapter is not None


def test_completeness_adapter_placeholder():
    """Test completeness adapter returns placeholder."""
    adapter = CompletenessAdapter()
    result = adapter.analyze_country(
        bbox="97.3,5.6,105.6,20.5",
        entity_type="building",
        year=2020,
        iso_code="TH"
    )

    assert 'feature_completeness' in result
    assert result['feature_completeness'] is None


def test_get_country_bbox_thailand():
    """Test getting bbox for Thailand."""
    bbox = get_country_bbox('TH')
    assert bbox == '97.3,5.6,105.6,20.5'


def test_get_country_bbox_myanmar():
    """Test getting bbox for Myanmar."""
    bbox = get_country_bbox('MM')
    assert bbox == '92.2,9.8,101.2,28.5'


def test_get_country_bbox_unknown():
    """Test error for unknown country."""
    with pytest.raises(ValueError):
        get_country_bbox('XX')


def test_split_country_small_no_chunking():
    """Test that small countries don't get chunked."""
    # Mock a tiny bbox (will be < 5000 km²)
    # Override by passing huge threshold
    grids = split_country_into_grids('TH', chunk_size_km=50, chunked_threshold_km2=999999)

    # Should return single grid
    assert len(grids) == 1
    assert grids[0]['chunk_id'] == '0_0'


def test_split_country_large_chunking():
    """Test that large countries get chunked."""
    # Thailand is large enough to be chunked
    grids = split_country_into_grids('TH', chunk_size_km=50, chunked_threshold_km2=1000)

    # Should return multiple grids
    assert len(grids) > 1

    # Check grid structure
    assert 'bbox' in grids[0]
    assert 'chunk_id' in grids[0]
    assert 'row' in grids[0]
    assert 'col' in grids[0]


def test_semantic_tags_adapter_init():
    """Test semantic tags adapter initialization."""
    # This will import the chunked analyzer
    try:
        adapter = SemanticTagsAdapter()
        assert adapter is not None
        assert adapter.chunk_size_km == 50
    except Exception as e:
        # If dependencies not available, skip
        pytest.skip(f"Dependencies not available: {e}")


def test_semantic_tags_adapter_get_tag_details_for_csv():
    """Test formatting tag details for CSV."""
    adapter = SemanticTagsAdapter()

    tag_details = [
        {'tag_key': 'building', 'frequency': 1000, 'proportion': 0.9, 'rank': 1, 'in_top5pct': True},
        {'tag_key': 'amenity', 'frequency': 500, 'proportion': 0.45, 'rank': 2, 'in_top5pct': True},
    ]

    rows = adapter.get_tag_details_for_csv(
        tag_details,
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert len(rows) == 2
    assert rows[0]['country'] == 'TH'
    assert rows[0]['year'] == 2020
    assert rows[0]['entity'] == 'building'
    assert rows[0]['tag_key'] == 'building'
    assert rows[0]['in_top5pct'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
