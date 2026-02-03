# Logging Guide - Understanding What's Happening

## New Enhanced Logging Messages

### 1. Geometric Complexity Analysis (Per Grid)

```
Grid 0_0: Starting buildings analysis for 2024 (bbox: 97.3,5.6,97.8,6.1)
Grid 0_0: Fetching building geometries from API...
Grid 0_0: Processed 15,234 buildings, complexity=0.4523
```

**What this means:**
- Grid identifier (e.g., 0_0 = row 0, column 0)
- Bounding box coordinates being queried
- Number of buildings downloaded from Ohsome API
- Geometric complexity ratio (how complex the geometries are)

### 2. Tag Semantic Analysis (Once Per Country)

```
TH 2024 building: Starting tag semantic analysis (bbox: 97.3,5.6,105.6,20.4)
TH 2024 building: Fetching tag data from API...
TH 2024 building: Processed 2,456,789 entities, 42 unique tags, richness=3.25
```

**What this means:**
- Country code and year
- Total entities analyzed across entire country
- Number of unique tag keys found
- Tag richness (average tags per entity)

### 3. Aggregation Summary

```
TH 2024 building: Aggregated 45 grids, total 2,456,789 entities, complexity=0.4512
```

**What this means:**
- How many grids were combined
- Total entity count across all grids
- Final weighted average complexity

## Why Processing Takes Long

### Geometric Complexity (Most Time-Consuming)
Each grid requires:
1. **API Call** (~5-30 seconds): Download all building geometries
2. **Geometry Processing** (~10-60 seconds): Calculate complexity for each building
3. **Aggregation** (~1-2 seconds): Combine results

**Time per grid:** 15-90 seconds depending on building density

### Tag Semantic Analysis (Once Per Country)
Runs only once for entire country:
1. **Chunked API Calls** (~2-5 minutes): Download tag data in chunks
2. **Tag Analysis** (~1-2 minutes): Calculate richness, diversity, Shannon index
3. **Top Tags Identification** (~30 seconds): Find most common tags

**Time per country:** 3-7 minutes

## Progress Indicators

### What You'll See

```
Processing 45/45 grids (rest cached)
```
- Means 45 grids need API calls, 0 are cached

```
Processing 5/45 grids (rest cached)
```
- Means only 5 grids need processing, 40 are already cached
- Much faster!

### Concurrent Processing

With `--max-concurrent 5`, you'll see 5 grids processing simultaneously:

```
Grid 0_0: Starting buildings analysis...
Grid 0_1: Starting buildings analysis...
Grid 0_2: Starting buildings analysis...
Grid 0_3: Starting buildings analysis...
Grid 0_4: Starting buildings analysis...
```

As each finishes, the next one starts.

## Time Estimates

### For Thailand (45 grids with 25km chunks)

**First run (no cache):**
- 45 grids × ~30 seconds average = ~22 minutes for geometric
- 1 tag analysis = ~5 minutes
- **Total: ~27 minutes**

**With 5 concurrent:**
- 45 grids ÷ 5 concurrent × ~30 seconds = ~4.5 minutes for geometric
- Tag analysis = ~5 minutes
- **Total: ~10 minutes**

**Subsequent runs (cached):**
- All grids cached = ~5 seconds
- Tag analysis cached = ~1 second
- **Total: ~10 seconds**

### For Myanmar (similar size)

Similar timing to Thailand.

### For Full Production Run (2015-2025, both entities)

**TH + MM, 11 years, 2 entities = 44 combinations**

**First run:**
- ~10 minutes × 44 = ~440 minutes (~7.3 hours)

**With cache (adding one new year):**
- ~10 minutes × 2 (new year for both countries)
- **Total: ~20 minutes**

## Optimizing Speed

### 1. Reduce Chunk Size (Already at 25km - Good!)
Smaller chunks = less data per call = faster API responses

### 2. Lower Concurrency (Currently 5 - Reasonable)
Prevents API overload and timeouts

### 3. Use Cache
After first run, cached data is instant

### 4. Process Countries Separately
Run TH and MM in separate sessions if needed

### 5. Focus on Recent Years
If you only need recent data, use `--years 2020-2025` instead of full range

## Troubleshooting

### "API request timed out (>300s)"
- Grid has too much data
- Solution: Use smaller chunk size (--chunk-size 15 or 20)
- Or: Skip that grid (system handles this automatically)

### "No results returned"
- Empty grid (no buildings in that area)
- This is normal for grids over ocean/remote areas

### Process seems stuck
- Check the log messages - it's probably processing a dense urban grid
- Urban areas (Bangkok, Yangon) take much longer than rural areas
- Be patient - some grids can take 2-3 minutes each

## Monitoring Progress

Watch for these patterns:

**Good Progress:**
```
Grid 0_0: Processed 5,234 buildings, complexity=0.45
Grid 0_1: Processed 3,421 buildings, complexity=0.42
Grid 0_2: Processed 7,891 buildings, complexity=0.48
```

**Dense Urban Grid (Slow):**
```
Grid 5_5: Starting buildings analysis...
[2-3 minutes pass]
Grid 5_5: Processed 125,678 buildings, complexity=0.51
```

**Timeout (Skipped):**
```
Grid 7_3: Starting buildings analysis...
ERROR: API request timed out for endpoint geometry (>300s)
Grid 7_3: No results returned from API
```
Grid is skipped, process continues with next grid.
