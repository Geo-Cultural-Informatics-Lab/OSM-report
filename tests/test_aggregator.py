"""
Tests for metrics aggregator.
"""
import pytest
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.aggregator import MetricsAggregator


@pytest.fixture
def aggregator():
    """Create aggregator instance."""
    return MetricsAggregator()


@pytest.fixture
def sample_grid_results():
    """Create sample grid results."""
    return [
        {
            'geometric': {
                'entity_count': 1000,
                'geometric_complexity': 0.42
            },
            'tags': {
                'unique_tags_count': 85,
                'richness_mean': 3.2,
                'richness_median': 3.0,
                'evenness': 0.87,
                'shannon_index': 2.91,
                'tag_details': [
                    {'tag_key': 'building', 'frequency': 950, 'proportion': 0.95, 'rank': 1, 'in_top5pct': True},
                    {'tag_key': 'amenity', 'frequency': 500, 'proportion': 0.50, 'rank': 2, 'in_top5pct': True}
                ]
            }
        },
        {
            'geometric': {
                'entity_count': 800,
                'geometric_complexity': 0.38
            },
            'tags': {
                'unique_tags_count': 85,
                'richness_mean': 3.1,
                'richness_median': 2.9,
                'evenness': 0.85,
                'shannon_index': 2.88,
                'tag_details': []
            }
        }
    ]


def test_aggregator_init(aggregator):
    """Test aggregator initialization."""
    assert aggregator is not None


def test_aggregate_grids_success(aggregator, sample_grid_results):
    """Test successful grid aggregation."""
    result = aggregator.aggregate_grids(
        sample_grid_results,
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert result['country'] == 'TH'
    assert result['year'] == 2020
    assert result['entity'] == 'building'

    # Check geometric complexity (weighted mean)
    # (1000 * 0.42 + 800 * 0.38) / 1800 = 0.4022
    expected_complexity = (1000 * 0.42 + 800 * 0.38) / 1800
    assert abs(result['geometric_complexity'] - expected_complexity) < 0.001

    # Check tag metrics
    assert result['unique_tags_count'] == 85
    assert result['richness_mean'] == 3.2
    assert result['evenness'] == 0.87


def test_aggregate_grids_empty_list(aggregator):
    """Test aggregation with empty grid list."""
    result = aggregator.aggregate_grids(
        [],
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert result['country'] == 'TH'
    assert result['geometric_complexity'] == 0.0
    assert result['unique_tags_count'] == 0


def test_aggregate_grids_all_none(aggregator):
    """Test aggregation when all grids are None."""
    result = aggregator.aggregate_grids(
        [None, None, None],
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert result['country'] == 'TH'
    assert result['geometric_complexity'] == 0.0


def test_aggregate_grids_mixed_none(aggregator, sample_grid_results):
    """Test aggregation with some None grids."""
    mixed_results = [None, sample_grid_results[0], None, sample_grid_results[1]]

    result = aggregator.aggregate_grids(
        mixed_results,
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert result['country'] == 'TH'
    # Should aggregate only non-None results
    assert result['geometric_complexity'] > 0


def test_extract_tag_details(aggregator, sample_grid_results):
    """Test extracting tag details."""
    rows = aggregator.extract_tag_details(
        sample_grid_results,
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert len(rows) == 2
    assert rows[0]['country'] == 'TH'
    assert rows[0]['year'] == 2020
    assert rows[0]['entity'] == 'building'
    assert rows[0]['tag_key'] == 'building'
    assert rows[0]['frequency'] == 950
    assert rows[0]['in_top5pct'] is True


def test_extract_tag_details_empty(aggregator):
    """Test extracting tag details from empty results."""
    rows = aggregator.extract_tag_details(
        [],
        iso_code='TH',
        year=2020,
        entity_type='building'
    )

    assert len(rows) == 0


def test_create_country_dataframe(aggregator):
    """Test creating country DataFrame."""
    country_rows = [
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'building',
            'geometric_complexity': 0.42,
            'unique_tags_count': 85,
            'richness_mean': 3.2,
            'richness_median': 3.0,
            'evenness': 0.87,
            'shannon_index': 2.91
        },
        {
            'country': 'TH',
            'year': 2021,
            'entity': 'building',
            'geometric_complexity': 0.43,
            'unique_tags_count': 88,
            'richness_mean': 3.3,
            'richness_median': 3.1,
            'evenness': 0.88,
            'shannon_index': 2.95
        }
    ]

    df = aggregator.create_country_dataframe(country_rows)

    assert len(df) == 2
    assert list(df.columns)[:3] == ['country', 'year', 'entity']
    assert df.iloc[0]['country'] == 'TH'
    assert df.iloc[0]['year'] == 2020
    assert df.iloc[1]['year'] == 2021


def test_create_tag_details_dataframe(aggregator):
    """Test creating tag details DataFrame."""
    tag_rows = [
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'building',
            'tag_key': 'building',
            'frequency': 1000,
            'proportion': 0.95,
            'rank': 1,
            'in_top5pct': True
        },
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'building',
            'tag_key': 'amenity',
            'frequency': 500,
            'proportion': 0.50,
            'rank': 2,
            'in_top5pct': True
        }
    ]

    df = aggregator.create_tag_details_dataframe(tag_rows)

    assert len(df) == 2
    assert list(df.columns) == [
        'country', 'year', 'entity',
        'tag_key', 'frequency', 'proportion',
        'rank', 'in_top5pct'
    ]
    assert df.iloc[0]['tag_key'] == 'building'


def test_create_tag_details_dataframe_empty(aggregator):
    """Test creating tag details DataFrame from empty list."""
    df = aggregator.create_tag_details_dataframe([])
    assert len(df) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
