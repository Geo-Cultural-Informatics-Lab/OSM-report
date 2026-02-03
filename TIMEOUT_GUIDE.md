# API Timeout Configuration Guide

## Overview

The timeout has been reduced from **300 seconds (5 minutes)** to **30 seconds** to fail fast on grids with too much data.

## Why Lower the Timeout?

**Before (300s timeout):**
- Dense grids would take 5+ minutes before timing out
- Blocked other grids from processing
- Wasted time on grids that will likely never complete

**After (30s timeout):**
- Quick failure on problematic grids
- Other grids can process faster
- Skip dense areas, focus on completable grids
- Overall faster completion time

## How to Use

### Default Timeout (30 seconds)

```bash
# Uses 30s timeout automatically
python main.py --countries TH --years 2024 --entities building --chunk-size 25
```

### Custom Timeout

```bash
# Increase to 60 seconds for denser areas
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 25 --api-timeout 60

# Very aggressive: 15 seconds
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 25 --api-timeout 15
```

## What Happens on Timeout?

When a grid times out:

1. **Error logged:**
   ```
   ERROR: API request timed out for endpoint geometry (>30s)
   Grid 5_5: No results returned from API
   ```

2. **Grid is skipped** - returns None

3. **Processing continues** - next grid starts immediately

4. **Aggregation handles it** - skipped grids don't contribute to metrics

This is **acceptable** for large-scale analysis. A few dense grids timing out won't significantly affect country-level statistics.

## Recommended Timeouts by Chunk Size

| Chunk Size | Recommended Timeout | Rationale |
|------------|---------------------|-----------|
| 15km | 15-20s | Small areas, should be fast |
| 20km | 20-30s | Medium areas, default is good |
| 25km | 30s (default) | Balanced timeout |
| 50km | 45-60s | Larger areas need more time |
| 100km+ | 90-120s | Very large areas |

## Timeout vs. Chunk Size Trade-offs

### Smaller Chunks + Lower Timeout (Recommended)
```bash
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 20 --api-timeout 30 --max-concurrent 5
```
**Pros:**
- ✓ Fewer timeouts (smaller data per grid)
- ✓ Faster failure on dense grids
- ✓ More grids complete successfully

**Cons:**
- More total grids to process
- More API calls

### Larger Chunks + Higher Timeout
```bash
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 50 --api-timeout 90 --max-concurrent 3
```
**Pros:**
- ✓ Fewer total grids
- ✓ Fewer API calls

**Cons:**
- More timeouts on dense grids
- Longer wait times when timeouts occur
- Lower overall throughput

## Monitoring Timeouts

Watch the logs for timeout patterns:

```bash
# Run and watch for timeouts
python main.py ... 2>&1 | grep -i timeout

# Count how many grids timed out
grep "timed out" logfile.txt | wc -l
```

If you see many timeouts (>10% of grids):
1. **Reduce chunk size** to 20km or 15km
2. **Increase timeout** to 45s or 60s
3. **Lower concurrency** to 3 to reduce API load

## Examples

### Dense Urban Area (Bangkok, Manila)
```bash
# Small chunks, moderate timeout
python main.py --countries TH --years 2024 --entities building \
  --chunk-size 15 --api-timeout 30 --max-concurrent 3
```

### Rural Area
```bash
# Can use larger chunks and lower timeout
python main.py --countries MM --years 2024 --entities building \
  --chunk-size 30 --api-timeout 25 --max-concurrent 5
```

### Production Run (All Years)
```bash
# Balanced settings
python main.py --countries TH MM --years 2015-2025 --entities building highway \
  --chunk-size 25 --api-timeout 30 --max-concurrent 5
```

### Testing (Quick Feedback)
```bash
# Aggressive timeout for quick testing
python main.py --countries TH --years 2024 --entities building \
  --test-mode --api-timeout 20
```

## Troubleshooting

### Too Many Timeouts

**Symptom:**
```
ERROR: API request timed out for endpoint geometry (>30s)
ERROR: API request timed out for endpoint geometry (>30s)
ERROR: API request timed out for endpoint geometry (>30s)
```

**Solutions:**
1. Reduce chunk size: `--chunk-size 15`
2. Increase timeout: `--api-timeout 60`
3. Lower concurrency: `--max-concurrent 3`

### Grids Complete Too Slowly

**Symptom:** Each grid takes 25-30s but doesn't timeout

**Solutions:**
1. Use smaller chunks: `--chunk-size 20`
2. Increase concurrency: `--max-concurrent 7`
3. Lower timeout: `--api-timeout 20` (fail faster on slow grids)

### Some Grids Never Complete

**Symptom:** Certain grids always timeout at any timeout value

**Solution:** This is expected for very dense urban cores (downtown Bangkok, etc.)
- Accept that some grids will timeout
- These areas have too much data for single API call
- The system handles this gracefully by skipping them

## Performance Impact

### Timeout: 300s → 30s

**Before:**
- Dense grid takes 5 minutes → times out
- Total wasted time: 5 minutes per dense grid
- 10 dense grids = 50 minutes wasted

**After:**
- Dense grid takes 30 seconds → times out
- Total wasted time: 30 seconds per dense grid
- 10 dense grids = 5 minutes wasted

**Time saved: 45 minutes** on a run with 10 dense grids!

## Best Practices

1. **Start with defaults** (25km chunks, 30s timeout)
2. **Monitor timeout rate** in first few grids
3. **Adjust if needed** based on timeout frequency
4. **Accept some timeouts** (5-10% is normal for dense areas)
5. **Use cache** - subsequent runs skip timed-out grids automatically

The new timeout system helps you fail fast on problematic grids and focus processing power on grids that will actually complete!
