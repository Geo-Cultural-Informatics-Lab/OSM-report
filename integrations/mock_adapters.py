"""
Mock adapters for testing - returns fake but realistic data.

Use these while debugging import issues with real adapters.
"""

import logging
import random

logger = logging.getLogger(__name__)


class MockGeometricAdapter:
    """
    Mock geometric complexity adapter - returns fake data.
    """

    def analyze_grid(self, bbox, entity_type, year, grid_id):
        """Return mock geometric complexity data."""
        logger.debug(f"MOCK: Analyzing grid {grid_id}")

        return {
            'grid_id': grid_id,
            'entity_count': random.randint(100, 10000),
            'geometric_complexity': round(random.uniform(0.3, 0.6), 3),
            'raw_results': {}
        }


class MockTagsAdapter:
    """
    Mock semantic tags adapter - returns fake data.
    """

    def analyze_country(self, bbox, entity_type, year, iso_code):
        """Return mock tag semantics data."""
        logger.debug(f"MOCK: Analyzing tags for {iso_code}")

        # Generate fake tag details
        tag_keys = ['building', 'addr:housenumber', 'name', 'amenity', 'shop', 'height']
        tag_details = []
        total_entities = 1000000

        for i, key in enumerate(tag_keys):
            freq = int(total_entities * random.uniform(0.05, 0.9) / (i + 1))
            tag_details.append({
                'tag_key': key,
                'frequency': freq,
                'proportion': freq / total_entities,
                'rank': i + 1,
                'in_top5pct': i < 3
            })

        return {
            'entity_count': total_entities,
            'unique_tags_count': len(tag_keys),
            'richness_mean': round(random.uniform(2.5, 4.5), 2),
            'richness_median': round(random.uniform(2.0, 4.0), 2),
            'evenness': round(random.uniform(0.7, 0.9), 3),
            'shannon_index': round(random.uniform(2.0, 3.5), 3),
            'tag_details': tag_details
        }
