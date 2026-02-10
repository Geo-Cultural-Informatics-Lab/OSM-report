# OSM Country Report Generator

Unified report generator for OpenStreetMap country-level quality metrics, integrating geometric complexity, tag semantic analysis, and completeness metrics.

## Features

- **Geometric Complexity Analysis**: Per-grid building/road geometry complexity metrics
- **Tag Semantic Analysis**: Country-level tag richness, diversity, and Shannon index
- **Smart Caching**: Grid-level caching with chunk-size awareness
- **Polygon Filtering**: Automatically filters out ocean/border grids
- **Async Processing**: Concurrent API calls with configurable limits
- **Progress Tracking**: Real-time progress bars and detailed logging

## Dependencies

**REQUIRED:** This project requires two companion packages to function:
- `geometric_complexity`: Building/road geometry analysis (REQUIRED - no mock fallback)
- `tags_semantic_analysis`: OSM tag semantic analysis (REQUIRED - no mock fallback)

**Note:** As of 2026-02-10, mock adapters have been removed. The system will fail immediately if these dependencies are not installed, ensuring 100% real data in every run.

## Installation

### Option 1: Development Setup (Editable Install - Recommended)

Assuming the directory structure is:
```
OSM/
├── geometric_complexity/
├── tags_semantic_analysis/
└── report/
```

From the `report` directory:
```bash
cd C:\Users\user\code\OSM\report
pip install -e ../geometric_complexity
pip install -e ../tags_semantic_analysis
pip install -r requirements.txt
```

Or from the OSM root directory:
```bash
cd C:\Users\user\code\OSM
pip install -e geometric_complexity
pip install -e tags_semantic_analysis
cd report
pip install -r requirements.txt
```

### Option 2: Production Setup (Package Install)

```bash
pip install git+https://github.com/yourusername/geometric_complexity.git
pip install git+https://github.com/yourusername/tags_semantic_analysis.git
git clone https://github.com/yourusername/osm-report.git
cd osm-report
pip install -r requirements.txt
```

## Quick Start

### Basic Usage

```bash
# Generate report for Thailand, 2024, buildings only
python main.py --countries TH --years 2024 --entities building

# Multiple countries and years
python main.py --countries TH MM --years 2020-2025 --entities building highway

# Test mode (faster, for testing)
python main.py --countries TH --years 2024 --entities building --test-mode
```

### Advanced Options

```bash
python main.py \
  --countries TH MM \
  --years 2015-2025 \
  --entities building highway \
  --chunk-size 25 \
  --max-concurrent 5 \
  --api-timeout 30 \
  --cache ./cache \
  --output ./results
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--countries` | Country ISO codes (e.g., TH MM) | Required |
| `--years` | Years to analyze (e.g., "2015-2025" or "2020 2022 2024") | Required |
| `--entities` | Entity types: building, highway | Required |
| `--chunk-size` | Grid chunk size in km | 50 |
| `--max-concurrent` | Max concurrent API requests | 10 |
| `--api-timeout` | API timeout in seconds | 30 |
| `--cache` | Cache directory | ./cache |
| `--output` | Output directory | ./results |
| `--test-mode` | Test mode (smaller chunks, fewer grids) | False |
| `--clear-cache` | Clear cache before running | False |
| `--verbose` | Verbose logging | False |

## Output

### CSV Files

The generator creates two CSV files per country:

**Primary CSV** (`th.csv`):
```csv
country,year,entity,geometric_complexity,unique_tags_count,richness_mean,richness_median,evenness,shannon_index
TH,2024,building,0.4523,42,3.25,2.80,0.75,2.45
```

**Detail CSV** (`th_tags_detail.csv`):
```csv
country,year,entity,tag_key,frequency,proportion,rank,in_top5pct
TH,2024,building,building,0.833,0.833,1,True
TH,2024,building,addr:street,0.421,0.421,2,True
```

## Performance Tuning

### Recommended Settings by Use Case

**Quick Test (Single Year)**
```bash
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 25 --max-concurrent 5 --test-mode
```

**Production (All Years)**
```bash
python main.py --countries TH MM --years 2015-2025 --entities building highway \
  --chunk-size 25 --max-concurrent 5 --api-timeout 30
```

**Dense Urban Areas**
```bash
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 15 --max-concurrent 3 --api-timeout 45
```

### Performance Tips

1. **Smaller chunks** = fewer timeouts but more API calls
2. **Lower concurrency** = more reliable but slower
3. **Cache accumulates** - subsequent runs are much faster
4. **Polygon filtering** saves 50-60% of API calls

## Architecture

```
report/
├── core/
│   ├── orchestrator.py      # Main coordination
│   ├── aggregator.py         # Metrics aggregation
│   ├── cache_manager.py      # Grid-level caching
│   └── _bootstrap.py         # Package loader
├── integrations/
│   ├── geometric_complexity_adapter.py
│   ├── semantic_tags_adapter.py
│   └── completeness_adapter.py
├── utils/
│   ├── grid_utils.py         # Grid splitting
│   ├── polygon_filter.py     # Country polygon filtering
│   └── async_runner.py       # Async processing
└── main.py
```

## Troubleshooting

### Import Errors

If you see "No module named 'geometric_complexity'":
1. Check packages are installed: `pip list | grep geometric`
2. Reinstall: `pip install -e /path/to/geometric_complexity/`
3. See [ADAPTER_FIX.md](ADAPTER_FIX.md) for details

### Timeouts

If many grids timeout:
1. Reduce chunk size: `--chunk-size 15`
2. Increase timeout: `--api-timeout 60`
3. Lower concurrency: `--max-concurrent 3`

See [TIMEOUT_GUIDE.md](TIMEOUT_GUIDE.md) for details.

### Cache Issues

If cache seems wrong:
1. Check chunk size matches cached data
2. Clear cache: `--clear-cache`
3. See [CACHE_GUIDE.md](CACHE_GUIDE.md) for details

## Documentation

- [ADAPTER_FIX.md](ADAPTER_FIX.md) - How the real adapters work
- [CACHE_GUIDE.md](CACHE_GUIDE.md) - Cache system explained
- [LOGGING_GUIDE.md](LOGGING_GUIDE.md) - Understanding log messages
- [TIMEOUT_GUIDE.md](TIMEOUT_GUIDE.md) - Timeout configuration

## License

[Your License Here]

## Contributing

[Contributing guidelines]

## Citation

If you use this tool in research, please cite:
[Your citation]
