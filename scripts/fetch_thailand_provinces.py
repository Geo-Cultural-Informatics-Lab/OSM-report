"""
Fetch Thailand province boundaries from Overpass API and cache to disk.

This script queries Overpass API once to get all admin_level=4 regions
(provinces) for Thailand, then saves them as GeoJSON for reuse.
"""

import requests
import json
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def query_overpass_admin_boundaries(country='Thailand', admin_level=4, timeout=180):
    """
    Query Overpass API for admin boundaries.

    Args:
        country: Country name
        admin_level: Admin level (4 = provinces in Thailand)
        timeout: Query timeout in seconds

    Returns:
        GeoJSON FeatureCollection
    """
    overpass_url = "https://overpass-api.de/api/interpreter"

    # Overpass QL query for admin boundaries
    query = f"""
    [out:json][timeout:{timeout}];
    area["name:en"="{country}"]->.country;
    (
      relation["admin_level"="{admin_level}"]["boundary"="administrative"](area.country);
    );
    out geom;
    """

    logger.info(f"Querying Overpass API for {country} admin_level={admin_level}...")
    logger.info(f"Query: {query.strip()}")

    response = requests.post(overpass_url, data={'data': query}, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    logger.info(f"Received {len(data.get('elements', []))} elements from Overpass")

    # Convert to GeoJSON FeatureCollection
    features = []
    for element in data.get('elements', []):
        if element['type'] != 'relation':
            continue

        # Extract properties
        tags = element.get('tags', {})

        # Filter out non-Thai provinces (check ISO code starts with TH-)
        iso_code = tags.get('ISO3166-2', '')
        if iso_code and not iso_code.startswith('TH-'):
            logger.debug(f"Skipping non-Thai province: {tags.get('name', 'Unknown')} ({iso_code})")
            continue

        properties = {
            'osm_id': element['id'],
            'name': tags.get('name', ''),
            'name_en': tags.get('name:en', tags.get('name', '')),
            'name_th': tags.get('name:th', ''),
            'admin_level': tags.get('admin_level'),
            'iso_code': iso_code,
            'ref': tags.get('ref', ''),
            'wikipedia': tags.get('wikipedia', ''),
        }

        # Extract geometry (Overpass returns geometry in 'members' for relations)
        # For simplicity, we'll extract the bbox from bounds
        bounds = element.get('bounds', {})
        if bounds:
            min_lon = bounds.get('minlon')
            min_lat = bounds.get('minlat')
            max_lon = bounds.get('maxlon')
            max_lat = bounds.get('maxlat')

            # Create bbox as a property (actual polygon geometry from Overpass is complex)
            properties['bbox'] = f"{min_lon},{min_lat},{max_lon},{max_lat}"
            properties['bbox_array'] = [min_lon, min_lat, max_lon, max_lat]

            # For GeoJSON, create a simple bbox polygon
            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat]
                ]]
            }
        else:
            logger.warning(f"No bounds for {properties['name']}, skipping")
            continue

        feature = {
            "type": "Feature",
            "properties": properties,
            "geometry": geometry
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    logger.info(f"Created GeoJSON with {len(features)} provinces")
    return geojson


def save_geojson(geojson, filepath):
    """Save GeoJSON to file."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved GeoJSON to {filepath}")


def main():
    """Main function to fetch and save Thailand provinces."""
    output_path = Path(__file__).parent.parent / 'data' / 'thailand_provinces_admin4.geojson'

    # Query Overpass API
    geojson = query_overpass_admin_boundaries(
        country='Thailand',
        admin_level=4,
        timeout=180
    )

    # Save to disk
    save_geojson(geojson, output_path)

    # Print summary
    print(f"\n{'='*60}")
    print(f"[OK] Successfully fetched {len(geojson['features'])} provinces")
    print(f"[OK] Saved to: {output_path}")
    print(f"{'='*60}\n")

    # Print sample
    if geojson['features']:
        sample = geojson['features'][0]
        print("Sample province:")
        print(f"  Name: {sample['properties']['name_en']}")
        print(f"  Bbox: {sample['properties']['bbox']}")
        print(f"  OSM ID: {sample['properties']['osm_id']}")


if __name__ == '__main__':
    main()
