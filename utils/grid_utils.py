"""
Grid utilities for splitting countries into chunks.

Simplified version with core chunking logic inlined.
"""

import math
from math import cos, radians
from typing import List, Dict, Tuple


def bbox_to_coords(bbox: str) -> Tuple[float, float, float, float]:
    """Convert bbox string to coordinate tuple."""
    coords = bbox.split(',')
    return float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])


def coords_to_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    """Convert coordinates to bbox string."""
    return f"{min_lon},{min_lat},{max_lon},{max_lat}"


def bbox_area_km2(bbox: str) -> float:
    """Calculate bounding box area in square kilometers."""
    min_lon, min_lat, max_lon, max_lat = bbox_to_coords(bbox)

    center_lat = (min_lat + max_lat) / 2
    lat_degree_km = 111.0
    lon_degree_km = 111.0 * cos(radians(center_lat))

    height_km = (max_lat - min_lat) * lat_degree_km
    width_km = (max_lon - min_lon) * lon_degree_km

    return width_km * height_km


def split_bbox_into_grid(bbox: str, chunk_size_km: float = 50) -> List[Dict[str, any]]:
    """
    Split a large bounding box into grid chunks.

    Args:
        bbox: Bounding box string "min_lon,min_lat,max_lon,max_lat"
        chunk_size_km: Target size of each chunk in kilometers

    Returns:
        List of chunk dictionaries
    """
    min_lon, min_lat, max_lon, max_lat = bbox_to_coords(bbox)

    center_lat = (min_lat + max_lat) / 2

    lat_degree_km = 111.0
    lon_degree_km = 111.0 * cos(radians(center_lat))

    lat_chunk_degrees = chunk_size_km / lat_degree_km
    lon_chunk_degrees = chunk_size_km / lon_degree_km

    num_rows = math.ceil((max_lat - min_lat) / lat_chunk_degrees)
    num_cols = math.ceil((max_lon - min_lon) / lon_chunk_degrees)

    chunks = []
    for row in range(num_rows):
        for col in range(num_cols):
            chunk_min_lat = min_lat + row * lat_chunk_degrees
            chunk_max_lat = min(chunk_min_lat + lat_chunk_degrees, max_lat)

            chunk_min_lon = min_lon + col * lon_chunk_degrees
            chunk_max_lon = min(chunk_min_lon + lon_chunk_degrees, max_lon)

            chunk_center_lat = (chunk_min_lat + chunk_max_lat) / 2
            chunk_center_lon = (chunk_min_lon + chunk_max_lon) / 2

            chunks.append({
                'bbox': coords_to_bbox(chunk_min_lon, chunk_min_lat, chunk_max_lon, chunk_max_lat),
                'chunk_id': f"{row}_{col}",
                'row': row,
                'col': col,
                'center_lat': chunk_center_lat,
                'center_lon': chunk_center_lon
            })

    return chunks


def get_country_bbox(iso_code: str) -> str:
    """
    Get bounding box for a country from ISO code.

    Args:
        iso_code: 2-letter ISO country code

    Returns:
        Bounding box string "min_lon,min_lat,max_lon,max_lat"
    """
    country_bboxes = {
        'TH': '97.3,5.6,105.6,20.5',    # Thailand
        'MM': '92.2,9.8,101.2,28.5',    # Myanmar/Burma
        'IL': '31.806021,29.688941,37.636742,33.521382',  # Israel
        'ID': '95.0,-11.0,141.0,6.0',   # Indonesia (archipelago: Sumatra to Papua)
        'PH': '116.9,4.6,126.6,21.1',   # Philippines
        'PG': '140.8,-11.7,155.9,-1.3', # Papua New Guinea
        'MY': '99.6,0.8,119.3,7.4',     # Malaysia (Peninsular + East Malaysia/Borneo)
    }

    if iso_code not in country_bboxes:
        raise ValueError(f"Unknown country ISO code: {iso_code}")

    return country_bboxes[iso_code]


def split_country_into_grids(
    iso_code: str,
    chunk_size_km: float = 50,
    chunked_threshold_km2: float = 5000
) -> List[Dict]:
    """
    Split country into grid chunks if needed.

    Args:
        iso_code: Country ISO code
        chunk_size_km: Grid chunk size in km
        chunked_threshold_km2: Area threshold for chunking

    Returns:
        List of grid chunk dictionaries (or single entry if no chunking needed)
    """
    bbox = get_country_bbox(iso_code)
    area = bbox_area_km2(bbox)

    if area < chunked_threshold_km2:
        # Return single "chunk" for the whole country
        return [{
            'bbox': bbox,
            'chunk_id': '0_0',
            'row': 0,
            'col': 0
        }]

    # Split into grid
    return split_bbox_into_grid(bbox, chunk_size_km)
