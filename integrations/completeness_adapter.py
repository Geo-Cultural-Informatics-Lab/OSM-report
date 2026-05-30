"""
Completeness adapter for the OSM report pipeline.

Implements feature completeness scoring using the assess_feature_completeness
algorithm from Feature_completeness/functions.py (3-condition version).

For each (country, entity), runs a single full time-series query (2008 → max_year+1)
and extracts a per-year score representing how much of the eventual stable mapping
level existed at the start of each year.
"""

import logging
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

_OHSOME_BASE = "https://api.ohsome.org/v1"

# Filters per entity type
_ENTITY_FILTERS = {
    'building': ('type:way and building=*', 'area'),
    'highway':  ('type:way and highway=*',  'length'),
    'road':     ('type:way and highway=*',  'length'),
}


# ---------------------------------------------------------------------------
# Ohsome helpers (lightweight, no dependency on geometric_complexity package)
# ---------------------------------------------------------------------------

def _ohsome_get(endpoint: str, bbox: str, filter_q: str, time_str: str,
                timeout: int = 120) -> Optional[pd.DataFrame]:
    """Call Ohsome aggregation endpoint; return DataFrame with timestamp+value."""
    url = f"{_OHSOME_BASE}/elements/{endpoint}"
    params = {"bboxes": bbox, "filter": filter_q, "time": time_str, "format": "json"}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            logger.error(f"Ohsome {endpoint} error {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        if "result" not in data or not data["result"]:
            return None
        return pd.json_normalize(data["result"])
    except Exception as e:
        logger.error(f"Ohsome {endpoint} request failed: {e}")
        return None


# ---------------------------------------------------------------------------
# assess_feature_completeness — copied from Feature_completeness/functions.py
# (3-condition version).  print() replaced with logger.debug().
# ---------------------------------------------------------------------------

def _assess_feature_completeness(
    count_gdf: pd.DataFrame,
    size_gdf: pd.DataFrame,
    alpha: float = 0.1,
    time_thresh: int = 2,
    saturation_thresh: float = 1.5,
    abs_thresh: float = 1.5,
    return_full: bool = False,
) -> pd.DataFrame:
    """
    Assess feature completeness from cumulative count and size time series.

    Returns a DataFrame that always contains at least:
        timestamp, count, size, cumulative_percentage, normalized_cum_per, test

    If the data is judged saturated, also adds:
        percentage_until_saturation  (count / saturation_count, reaches 1.0 at saturation)
    """
    count_gdf = count_gdf.copy()
    size_gdf = size_gdf.copy()

    count_gdf['timestamp'] = pd.to_datetime(count_gdf['timestamp'])
    size_gdf['timestamp'] = pd.to_datetime(size_gdf['timestamp'])

    count_gdf = count_gdf.sort_values('timestamp').reset_index(drop=True)
    size_gdf = size_gdf.sort_values('timestamp').reset_index(drop=True)

    gdf = count_gdf.rename(columns={'value': 'count'})
    gdf['size'] = size_gdf['value']

    gdf['cumulative_percentage'] = gdf['size'] / gdf['count']
    gdf['cumulative_percentage'] = gdf['cumulative_percentage'].fillna(0)
    max_cum = gdf['cumulative_percentage'].max()
    gdf['normalized_cum_per'] = gdf['cumulative_percentage'] / max_cum if max_cum > 0 else 0.0

    # Adjust alpha for "small to large" mapping case
    adjusted_alpha = alpha
    if gdf['cumulative_percentage'].idxmax() >= (len(gdf) * 0.75):
        adjusted_alpha = 1 - alpha

    gdf['test'] = gdf['normalized_cum_per'] < adjusted_alpha

    # Condition 1: find stable period (backward scan)
    i = -1
    while gdf['test'].iat[i]:
        try:
            i -= 1
            _ = gdf['test'].iat[i]
        except IndexError:
            break

    if i == -1:
        logger.debug(f"Completeness: no stable period found")
        return gdf

    stable = gdf.iloc[i + 1:].copy()

    if (stable['timestamp'].max() - stable['timestamp'].min()) < pd.Timedelta(days=time_thresh * 365):
        logger.debug(f"Completeness: stable period shorter than {time_thresh} years")
        return gdf

    # Condition 2/3
    saturation_point = stable.iloc[0]
    gdf['percentage_until_saturation'] = gdf['count'] / saturation_point['count']
    real_max = gdf.iloc[-1]

    if real_max['percentage_until_saturation'] >= saturation_thresh:
        stable['count_change'] = stable['count'] / stable['count'].max()
        if (stable['count_change'] >= abs_thresh).any():
            abs_add_index = stable['count_change'].idxmax()
            if (stable['timestamp'].max() - stable.loc[abs_add_index, 'timestamp']) < pd.Timedelta(days=time_thresh * 365):
                logger.debug(f"Completeness: no stable absolute addition period")

            saturation_point = stable.iloc[stable['count_change'].argmax()]
            gdf['percentage_until_saturation'] = gdf['count'] / saturation_point['count']
            real_max = gdf.iloc[-1]

            if real_max['percentage_until_saturation'] >= saturation_thresh:
                logger.debug(f"Completeness: stable absolute addition larger than threshold")
                gdf = gdf.drop(columns=['percentage_until_saturation'], errors='ignore')
                return gdf
        else:
            logger.debug(f"Completeness: stable relative addition larger than threshold")
            gdf = gdf.drop(columns=['percentage_until_saturation'], errors='ignore')
            return gdf

    sat80_rows = gdf[gdf['percentage_until_saturation'] >= 0.8]
    sat_time = sat80_rows['timestamp'].iloc[0] if not sat80_rows.empty else None
    logger.debug(f"Completeness: 80% saturation at {sat_time}")

    if return_full:
        return gdf

    # Compact: data up to stable start + last row
    saturated = gdf.iloc[: i + 1].copy()
    saturated = pd.concat([saturated, pd.DataFrame([real_max])], ignore_index=True)
    return saturated


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------

class CompletenessAdapter:
    """
    Wraps _assess_feature_completeness for use by the report orchestrator.

    Call analyze_all_years() once per country/entity with the full year list.
    Returns one metrics dict per year.
    """

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        logger.debug(f"CompletenessAdapter initialized (timeout={timeout}s)")

    def analyze_all_years(
        self,
        bbox: str,
        entity_type: str,
        years: List[int],
        iso_code: str,
    ) -> List[Dict[str, Any]]:
        """
        Run completeness analysis for all years for a given country/entity.

        Args:
            bbox:        Country (or region) bounding box "min_lon,min_lat,max_lon,max_lat"
            entity_type: 'building', 'highway', or 'road'
            years:       List of analysis years (one output row each)
            iso_code:    Country ISO code (for logging)

        Returns:
            List of dicts, one per year (sorted ascending):
            {
                'country': str, 'year': int, 'entity': str,
                'completeness_score': float | None
            }
        """
        sorted_years = sorted(years)
        entity_key = 'highway' if entity_type == 'road' else entity_type

        def _empty_rows():
            return [
                {'country': iso_code, 'year': y, 'entity': entity_key, 'completeness_score': None}
                for y in sorted_years
            ]

        if entity_key not in _ENTITY_FILTERS:
            logger.warning(f"CompletenessAdapter: unknown entity type '{entity_key}'")
            return _empty_rows()

        filter_q, size_endpoint = _ENTITY_FILTERS[entity_key]
        max_year = sorted_years[-1]
        time_str = f"2008-01-01/{max_year + 1}-01-01/P1M"

        logger.info(
            f"{iso_code} {entity_key}: Fetching completeness time series "
            f"2008–{max_year + 1} ({size_endpoint})"
        )

        count_df = _ohsome_get('count',        bbox, filter_q, time_str, self.timeout)
        size_df  = _ohsome_get(size_endpoint,  bbox, filter_q, time_str, self.timeout)

        if count_df is None or size_df is None or count_df.empty or size_df.empty:
            logger.warning(f"{iso_code} {entity_key}: completeness API query returned no data")
            return _empty_rows()

        try:
            gdf = _assess_feature_completeness(
                count_df, size_df,
                alpha=0.1, time_thresh=2, saturation_thresh=1.5, abs_thresh=1.5,
                return_full=True,
            )
        except Exception as e:
            logger.error(f"{iso_code} {entity_key}: completeness computation failed: {e}", exc_info=True)
            return _empty_rows()

        results = []
        for year in sorted_years:
            score = self._extract_score(gdf, year)
            results.append({
                'country': iso_code,
                'year': year,
                'entity': entity_key,
                'completeness_score': score,
            })

        logger.info(f"{iso_code} {entity_key}: Completeness done — {len(results)} year rows")
        return results

    @staticmethod
    def _extract_score(gdf: pd.DataFrame, year: int) -> Optional[float]:
        """Extract completeness score at January 1 of the given year."""
        if gdf is None or gdf.empty:
            return None

        target = pd.Timestamp(f"{year}-01-01")
        future = gdf[gdf['timestamp'] >= target]
        row = future.iloc[0] if not future.empty else gdf.iloc[-1]

        if 'percentage_until_saturation' in gdf.columns:
            val = row.get('percentage_until_saturation')
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                return float(val)

        val = row.get('normalized_cum_per')
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)

        return None

    # Legacy single-year interface (kept for backward compatibility)
    def analyze_country(
        self,
        bbox: str,
        entity_type: str,
        year: int,
        iso_code: str,
    ) -> Dict[str, Any]:
        """
        Single-year wrapper around analyze_all_years.

        Returns dict with 'feature_completeness' key (legacy) and 'completeness_score'.
        """
        rows = self.analyze_all_years(bbox, entity_type, [year], iso_code)
        score = rows[0]['completeness_score'] if rows else None
        return {'feature_completeness': score, 'completeness_score': score}
