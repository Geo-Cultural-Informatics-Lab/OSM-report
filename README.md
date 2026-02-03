# OSM Country Report Generator

Master repository for generating comprehensive OpenStreetMap quality reports across multiple countries, years, and entity types.

## Overview

This tool integrates multiple OSM quality metrics into unified CSV reports:
- **Geometric Complexity**: Mean complexity ratio (building shape quality)
- **Semantic Tagging**: Tag richness, diversity (Shannon index), evenness
- **Future**: Feature completeness, innovation metrics

## Features

- ✅ **Grid-based chunking**: Handles large countries (Thailand, Myanmar) without timeouts
- ✅ **Async processing**: Concurrent API requests with rate limiting
- ✅ **Smart caching**: Disk-based cache to avoid redundant API calls
- ✅ **Rate limit handling**: Exponential backoff with graceful degradation
- ✅ **Dual CSV output**: Primary metrics + detailed tag-level data
- ✅ **Progress tracking**: Real-time progress bars showing year/entity and grid processing
- ✅ **Incremental runs**: Merge data when running entities separately

## Installation

```bash
cd report
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Generate report for Thailand, all years 2015-2025, buildings only
python main.py --countries TH --years 2015-2025 --entities building

# Multiple countries and entities (recommended - runs in one go)
python main.py --countries TH MM --years 2015-2025 --entities building road

# Specific years only
python main.py --countries TH --years "2015 2020 2025" --entities building
```

### Incremental Runs (Separate Entities)

**✨ NEW**: You can now run entities separately and data will be merged:

```bash
# First run: buildings only
python main.py --countries TH --years 2015-2025 --entities building

# Second run: roads (will merge with existing buildings data)
python main.py --countries TH --years 2015-2025 --entities road

# Result: thailand.csv contains both buildings AND roads
```

**How it works**:
- The tool checks if CSV exists
- Merges new data with existing based on `(country, year, entity)` key
- Overwrites duplicate entries (useful for re-running failed entities)
- Sorts final output by country, year, entity

### Test Mode

Quick test with larger chunks (fewer API calls):

```bash
python main.py --countries TH --years 2024 --entities building --test-mode
```

### Options

```
--countries TH MM          Country ISO codes
--years 2015-2025          Year range or specific years
--entities building road   Entity types to analyze
--output ./results         Output directory (default: ./results)
--cache ./cache            Cache directory (default: ./cache)
--chunk-size 50            Grid chunk size in km (default: 50)
--max-concurrent 10        Max concurrent requests (default: 10)
--test-mode                Use larger chunks for quick testing
--clear-cache              Clear cache before running
--verbose                  Verbose logging
```

## Output

### Primary Report: `{country}.csv`

One CSV per country with multiple rows (year × entity combinations):

```csv
country,year,entity,geometric_complexity,unique_tags_count,richness_mean,...
TH,2015,building,0.38,72,3.1,3.0,0.85,2.87
TH,2015,road,0.31,45,2.8,2.0,0.79,2.34
TH,2016,building,0.39,75,3.2,3.0,0.86,2.91
...
```

### Tag Detail Report: `{country}_tags_detail.csv`

Detailed tag-level data (top 5% tags):

```csv
country,year,entity,tag_key,frequency,proportion,rank,in_top5pct
TH,2015,building,building,1500000,0.98,1,True
TH,2015,building,addr:housenumber,450000,0.29,2,True
...
```

## Architecture

```
report/
├── main.py                  # CLI entry point
├── core/
│   ├── orchestrator.py      # Main workflow coordinator
│   ├── cache_manager.py     # Disk cache
│   └── aggregator.py        # Metrics aggregation
├── integrations/
│   ├── geometric_complexity_adapter.py
│   ├── semantic_tags_adapter.py
│   └── completeness_adapter.py
├── utils/
│   ├── async_runner.py      # Async processing with rate limiting
│   └── grid_utils.py        # Grid chunking utilities
└── tests/
    ├── test_cache_manager.py
    ├── test_async_runner.py
    └── test_aggregator.py
```

## Integration with Subprojects

This master repository integrates:

1. **geometric_complexity**: Building/road shape complexity analysis
2. **tags_semantic_analysis**: Tag richness and Shannon diversity (with new chunking support)
3. **Feature_completeness**: (Future) Completeness metrics

## Caching

The tool caches results at the grid level:
- **Cache key format**: `{iso}_grid_{row}_{col}_{year}_{entity}_{type}.json`
- **Benefits**: Second run with same parameters = zero API calls
- **Management**: Use `--clear-cache` to force re-analysis

## Rate Limiting

Built-in protection against API rate limits:
- **Semaphore throttling**: Limits concurrent requests (default: 10)
- **Exponential backoff**: 5s → 10s → 20s on 429 errors
- **Graceful degradation**: Failed grids logged, processing continues
- **Dynamic concurrency**: Reduces load if too many rate limits

## Testing

```bash
# Run all tests
cd report
python -m pytest tests/ -v

# Run specific test suite
python -m pytest tests/test_cache_manager.py -v
python -m pytest tests/test_async_runner.py -v
python -m pytest tests/test_aggregator.py -v
```

**Test Coverage**: 32 tests, all passing ✅

## Examples

### Full Thailand Analysis (2015-2025)

```bash
python main.py \
  --countries TH \
  --years 2015-2025 \
  --entities building road \
  --max-concurrent 15
```

Expected:
- ~300 grids × 11 years × 2 entities = ~6,600 API calls
- With cache: Second run = 0 API calls
- Runtime: ~30-45 minutes (depending on API speed)

### Quick Test

```bash
python main.py \
  --countries TH \
  --years 2024 \
  --entities building \
  --test-mode
```

Expected:
- ~10-20 grids (larger chunk size)
- Runtime: ~2-5 minutes

## Troubleshooting

### API Timeouts

If seeing timeouts, reduce concurrency:
```bash
python main.py --countries TH --years 2024 --entities building --max-concurrent 5
```

### Rate Limits

The tool automatically handles rate limits with backoff. If persistent:
- Reduce `--max-concurrent` (try 5 or 3)
- The tool will log rate limit events

### Out of Memory

For very large countries, increase chunk size:
```bash
python main.py --countries TH --years 2024 --entities building --chunk-size 100
```

## Future Enhancements

- [ ] Innovation metrics (new tags, top 1%/5% new tags)
- [ ] Feature completeness integration
- [ ] Support for more countries
- [ ] Web dashboard for results
- [ ] Comparison visualizations

## Contributing

Subproject modifications (e.g., adding chunking to tags_semantic_analysis) should be committed to their respective repositories with proper git workflow.

## License

Same as parent OSM analysis projects.
