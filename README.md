# OSM Country Report Generator

Generates multi-year, multi-country OpenStreetMap quality reports measuring geometric complexity and tag semantic richness for buildings and roads. Part of the *"Impacts of Corporate Editors on Collective Intelligence in OpenStreetMap"* project.

**Authors:** Yair Grinberger (PI), Tomer Vagenfeld, Alexander Shapira
**Affiliation:** Department of Geography, The Hebrew University of Jerusalem
**Commissioned by:** Digital Infrastructure Insights Fund (D//F), February 2026

## Installation

This project depends on two companion packages that must be installed first.

**Option A** -- Install from GitHub (recommended):
```bash
pip install git+https://github.com/Geo-Cultural-Informatics-Lab/OSM-geometrical_complexity.git
pip install git+https://github.com/Geo-Cultural-Informatics-Lab/OSM-tags_semantic_analysis.git
git clone https://github.com/Geo-Cultural-Informatics-Lab/OSM-report.git
cd OSM-report
pip install -r requirements.txt
```

**Option B** -- Clone all repos locally (for development):
```bash
git clone https://github.com/Geo-Cultural-Informatics-Lab/OSM-geometrical_complexity.git
git clone https://github.com/Geo-Cultural-Informatics-Lab/OSM-tags_semantic_analysis.git
git clone https://github.com/Geo-Cultural-Informatics-Lab/OSM-report.git

pip install -e OSM-geometrical_complexity
pip install -e OSM-tags_semantic_analysis
cd OSM-report
pip install -r requirements.txt
```

**Requirements:** Python 3.8+, see `requirements.txt` for full dependency list.

## Quick Start

```bash
# Single country, single year
python main.py --countries TH --years 2024 --entities building

# Multiple countries and years
python main.py --countries TH MM MY --years 2015-2025 --entities building highway

# Province-level analysis (requires geoBoundaries GeoJSON in data/)
python main.py --countries TH --years 2015-2025 --entities building --province-level

# Run only tag analysis module
python main.py --countries TH --years 2024 --entities building --modules tags
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--countries` | Country ISO codes (e.g., `TH MM ID MY PH PG`) | Required |
| `--years` | Years: `"2015-2025"` or `"2020 2022 2024"` | Required |
| `--entities` | Entity types: `building`, `highway` | Required |
| `--modules` | Analysis modules: `geometric`, `tags`, `completeness` | `geometric tags` |
| `--province-level` | Analyze at province/state level (ADM1) | Off |
| `--chunk-size` | Grid chunk size in km | 50 |
| `--max-concurrent` | Max concurrent API requests | 10 |
| `--api-timeout` | API request timeout in seconds | 30 |
| `--cache` | Cache directory | `./cache` |
| `--output` | Output directory | `./results` |
| `--clear-cache` | Clear cache before running | Off |
| `--test-mode` | Smaller chunks for quick testing | Off |
| `--verbose` | Verbose logging | Off |

## Province-Level Analysis

Use `--province-level` to analyze each province/state separately. Requires a [geoBoundaries](https://www.geoboundaries.org/) ADM1 GeoJSON file in the `data/` directory. Supported countries (add more by editing `COUNTRY_PROVINCES_GEOJSON` in `main.py`):

| Country | File |
|---------|------|
| Thailand | `data/thailand_provinces_geoboundaries.geojson` |
| Indonesia | `data/geoBoundaries-IDN-ADM1.geojson` |
| Malaysia | `data/geoBoundaries-MYS-ADM1.geojson` |
| Philippines | `data/geoBoundaries-PHL-ADM1.geojson` |
| Papua New Guinea | `data/geoBoundaries-PNG-ADM1.geojson` |
| Myanmar | `data/geoBoundaries-MMR-ADM1.geojson` |

Province results are saved as `{country}_provinces.csv` and merge safely with existing data on partial reruns.

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/find_and_fix_missing.py` | Scans result CSVs for failed rows (`entity_count=0` or `unique_tags_count=0`), deletes their bad cache files, and prints ready-to-run fill-in commands. Use `--dry-run` to preview. |
| `scripts/fetch_thailand_provinces.py` | Fetches Thailand province boundaries from Overpass API |
| `scripts/validate_province_coverage.py` | Validates that grid filtering covers 100% of a province |

### Filling Missing Data

After a large run, some data points may fail due to API timeouts or network issues. To find and fix them:

```bash
cd results
python ../scripts/find_and_fix_missing.py --dry-run   # preview
python ../scripts/find_and_fix_missing.py              # delete bad cache + print commands
# Then run the printed fill-in commands
```

## Output Format

**Primary CSV** (`th.csv`) -- one row per country-year-entity:
```
country, year, entity, entity_count, geometric_complexity, unique_tags_count,
richness_mean, richness_median, evenness, shannon_index
```

**Detail CSV** (`th_tags_detail.csv`) -- per-tag breakdown:
```
country, year, entity, tag_key, frequency, proportion, rank, in_top5pct
```

**Province CSV** (`th_provinces.csv`) -- one row per province-year-entity:
```
country, province_code, province_name, province_name_local, year, entity,
entity_count, geometric_complexity, unique_tags_count, richness_mean, ...
```

## Architecture

```
report/
├── main.py                          # CLI entry point
├── core/
│   ├── orchestrator.py              # Main coordination + caching
│   ├── aggregator.py                # Grid-level metric aggregation
│   └── cache_manager.py             # Disk-based grid cache
├── analysis/
│   └── province_analyzer.py         # Province-level analysis via geoBoundaries
├── integrations/
│   ├── geometric_complexity_adapter.py  # Bridges to geometric_complexity package
│   └── semantic_tags_adapter.py         # Bridges to tags_semantic_analysis package
├── utils/
│   ├── grid_utils.py                # Bounding box → grid splitting
│   ├── polygon_filter.py            # Country/province polygon filtering
│   └── async_runner.py              # Async API request manager
└── scripts/
    └── find_and_fix_missing.py      # Missing data scanner
```

## Troubleshooting

**Import errors** (`No module named 'geometric_complexity'`): Reinstall the companion packages with `pip install -e ../OSM-geometrical_complexity`.

**API timeouts**: Reduce chunk size (`--chunk-size 25`), increase timeout (`--api-timeout 60`), or lower concurrency (`--max-concurrent 3`).

**Stale cache**: Use `--clear-cache` to start fresh, or run `find_and_fix_missing.py` to selectively clear failed entries.

## License

MIT License. See [LICENSE](LICENSE).

## Citation

If you use this tool in research, please cite:

> Grinberger, Y., Vagenfeld, T., & Shapira, A. (2026). *Impacts of Corporate Editors on Collective Intelligence in OpenStreetMap*. Department of Geography, The Hebrew University of Jerusalem. Commissioned by the Digital Infrastructure Insights Fund (D//F).
