"""
Test CSV merge behavior for incremental runs.
"""
import pytest
import pandas as pd
import tempfile
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import CountryReportOrchestrator


@pytest.fixture
def temp_results_dir():
    """Create temporary results directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_primary_csv_merge(temp_results_dir):
    """Test that running multiple times merges data correctly."""
    orchestrator = CountryReportOrchestrator(
        cache_dir=tempfile.mkdtemp(),
        results_dir=temp_results_dir
    )

    # First run: buildings only
    building_rows = [
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

    filepath = orchestrator._write_primary_csv('TH', building_rows)
    assert filepath.exists()

    # Check first run
    df1 = pd.read_csv(filepath)
    assert len(df1) == 2
    assert all(df1['entity'] == 'building')

    # Second run: roads only
    road_rows = [
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'road',
            'geometric_complexity': 0.31,
            'unique_tags_count': 45,
            'richness_mean': 2.8,
            'richness_median': 2.0,
            'evenness': 0.79,
            'shannon_index': 2.34
        },
        {
            'country': 'TH',
            'year': 2021,
            'entity': 'road',
            'geometric_complexity': 0.32,
            'unique_tags_count': 47,
            'richness_mean': 2.9,
            'richness_median': 2.1,
            'evenness': 0.80,
            'shannon_index': 2.38
        }
    ]

    filepath = orchestrator._write_primary_csv('TH', road_rows)

    # Check merged result
    df2 = pd.read_csv(filepath)
    assert len(df2) == 4  # 2 buildings + 2 roads
    assert len(df2[df2['entity'] == 'building']) == 2
    assert len(df2[df2['entity'] == 'road']) == 2

    # Verify data is sorted by country, year, entity
    # Order should be: 2020 building, 2020 road, 2021 building, 2021 road
    # (sorted by year first, then entity alphabetically)
    assert df2.iloc[0]['year'] == 2020
    assert df2.iloc[0]['entity'] == 'building'
    assert df2.iloc[1]['year'] == 2020
    assert df2.iloc[1]['entity'] == 'road'
    assert df2.iloc[2]['year'] == 2021
    assert df2.iloc[2]['entity'] == 'building'
    assert df2.iloc[3]['year'] == 2021
    assert df2.iloc[3]['entity'] == 'road'


def test_primary_csv_overwrite_same_entity(temp_results_dir):
    """Test that re-running same entity overwrites old data."""
    orchestrator = CountryReportOrchestrator(
        cache_dir=tempfile.mkdtemp(),
        results_dir=temp_results_dir
    )

    # First run: building 2020
    rows1 = [
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
        }
    ]

    filepath = orchestrator._write_primary_csv('TH', rows1)
    df1 = pd.read_csv(filepath)
    assert df1.iloc[0]['geometric_complexity'] == 0.42

    # Second run: building 2020 with updated value
    rows2 = [
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'building',
            'geometric_complexity': 0.50,  # Updated value
            'unique_tags_count': 90,
            'richness_mean': 3.5,
            'richness_median': 3.2,
            'evenness': 0.90,
            'shannon_index': 3.00
        }
    ]

    filepath = orchestrator._write_primary_csv('TH', rows2)
    df2 = pd.read_csv(filepath)

    # Should still be 1 row (not 2)
    assert len(df2) == 1

    # Should have new value
    assert df2.iloc[0]['geometric_complexity'] == 0.50
    assert df2.iloc[0]['unique_tags_count'] == 90


def test_tag_detail_csv_merge(temp_results_dir):
    """Test that tag detail CSV merges correctly."""
    orchestrator = CountryReportOrchestrator(
        cache_dir=tempfile.mkdtemp(),
        results_dir=temp_results_dir
    )

    # First run: building tags
    building_tags = [
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

    filepath = orchestrator._write_detail_csv('TH', building_tags)
    df1 = pd.read_csv(filepath)
    assert len(df1) == 2

    # Second run: road tags
    road_tags = [
        {
            'country': 'TH',
            'year': 2020,
            'entity': 'road',
            'tag_key': 'highway',
            'frequency': 2000,
            'proportion': 0.98,
            'rank': 1,
            'in_top5pct': True
        }
    ]

    filepath = orchestrator._write_detail_csv('TH', road_tags)
    df2 = pd.read_csv(filepath)

    # Should have merged
    assert len(df2) == 3  # 2 building + 1 road
    assert len(df2[df2['entity'] == 'building']) == 2
    assert len(df2[df2['entity'] == 'road']) == 1


def test_empty_csv_handling(temp_results_dir):
    """Test handling of empty DataFrames."""
    orchestrator = CountryReportOrchestrator(
        cache_dir=tempfile.mkdtemp(),
        results_dir=temp_results_dir
    )

    # Write empty tags (happens when analysis fails)
    filepath = orchestrator._write_detail_csv('TH', [])
    assert filepath.exists()

    # Empty CSV will have no columns, pandas will raise error
    # This is expected behavior - we just check file was created
    # In practice, empty results won't be written if no data exists


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
