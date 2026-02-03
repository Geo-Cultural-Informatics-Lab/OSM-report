# Cache System Guide

## How the Cache Works

The OSM Country Report Generator caches grid-level results to avoid redundant API calls.

### Cache Timing

**✓ Cache is saved IMMEDIATELY while running** (not at the end)

Each grid result is written to disk as soon as it completes:
1. Grid processes → API call completes
2. Result returned from adapter
3. **Immediately cached to disk**
4. Next grid starts

This means:
- ✓ Safe to interrupt (Ctrl+C) - completed grids are already cached
- ✓ Resume capability - restart will skip cached grids
- ✓ Progress never lost

### Cache File Format

Each grid gets its own JSON file:
```
cache/TH_grid_0_0_2024_building_25km_combined.json
cache/TH_grid_0_1_2024_building_25km_combined.json
...
```

**Naming pattern:**
```
{country}_grid_{row}_{col}_{year}_{entity}_{chunk_size}km_combined.json
```

## Chunk Size and Cache

**IMPORTANT:** Cache is now chunk-size aware (as of latest update).

### Before the Fix

If you ran with different chunk sizes, the cache would give **incorrect results**:
- Run with 50km → Grid `0_0` caches large area
- Run with 25km → Grid `0_0` uses wrong cached data (50km data)

### After the Fix

Cache keys now include chunk size:
- 25km chunks: `TH_grid_0_0_2024_building_25km_combined.json`
- 50km chunks: `TH_grid_0_0_2024_building_50km_combined.json`

These are **separate cache files** - no collision!

### What This Means

✓ **Can safely change chunk sizes** - each size has its own cache
✓ **No need to clear cache** when experimenting with chunk sizes
✓ **Backward compatible** - old cache files without chunk size still work

## Cache Operations

### Check Cache Status

```bash
# Count cached grids
ls cache/ | wc -l

# See cache for Thailand 2024 buildings with 25km chunks
ls cache/TH_grid_*_2024_building_25km_combined.json | wc -l

# Check cache size
du -sh cache/
```

### Clear Cache

```bash
# Clear all cache
rm -rf cache/*

# Clear cache for specific country
rm -f cache/TH_*

# Clear cache for specific chunk size
rm -f cache/*_25km_*

# Clear cache for specific year
rm -f cache/*_2024_*
```

### When to Clear Cache

You typically **don't need to clear cache**, but you may want to if:

1. **Subproject code changed** - geometric_complexity or tags_semantic_analysis updated
2. **Testing** - want to force fresh API calls
3. **Disk space** - cache is taking too much space
4. **Data issues** - suspect cached data is corrupted

## Cache Efficiency Examples

### Thailand with 25km chunks

**First run (no cache):**
- 996 grids to process
- Each takes ~30 seconds
- With 5 concurrent: ~1.6 hours

**Second run (fully cached):**
- 996 grids cached
- 0 API calls needed
- **Complete in ~10 seconds**

### Adding a New Year

If you have 2015-2023 cached and add 2024:
- Old years: instant (cached)
- New year 2024: ~1.6 hours
- **Total: ~1.6 hours** (not 10 hours)

### Changing Chunk Size

If you switch from 50km to 25km:
- Old 50km cache: still valid for 50km runs
- New 25km run: builds new cache
- **No interference between the two**

## Cache Inspection

To see what's in a cache file:

```bash
# Pretty-print a cache file
cat cache/TH_grid_0_0_2024_building_25km_combined.json | python -m json.tool | head -n 30
```

Cache file contains:
```json
{
  "geometric": {
    "grid_id": "0_0",
    "entity_count": 1234,
    "geometric_complexity": 0.4523,
    "raw_results": {...}
  },
  "tags": {
    "entity_count": 5678,
    "unique_tags_count": 42,
    "richness_mean": 3.25,
    "tag_details": [...]
  }
}
```

## Troubleshooting

### Cache Not Being Used

If you see "Processing X/X grids" (all grids) when you expect cache hits:

1. **Check chunk size** - did you change it?
   - Old cache: 50km chunks
   - Current run: 25km chunks
   - Solution: This is fine, it will build new cache

2. **Check file names** - do they match?
   ```bash
   # See what's cached for Thailand 2024 buildings
   ls cache/TH_grid_*_2024_building_*
   ```

3. **Permissions** - can the process read cache files?
   ```bash
   ls -la cache/ | head
   ```

### Cache Files Growing Too Large

```bash
# Check cache directory size
du -sh cache/

# Count files
ls cache/ | wc -l
```

For full analysis (TH + MM, 2015-2025, 2 entities, 25km chunks):
- ~2,000-3,000 cache files
- ~50-100 MB total size

This is acceptable. If much larger, consider clearing old cache.

## Best Practices

1. **Let cache accumulate** - don't clear unless needed
2. **Use consistent chunk sizes** - pick one for production
3. **Back up cache** (optional) - before major changes
4. **Monitor disk space** - cache shouldn't exceed 500MB
5. **Document chunk size** - remember what you used

## Performance Tips

1. **First run takes longest** - no cache yet
2. **Incremental runs are fast** - most data cached
3. **Smaller chunks = more cache files** - but better reliability
4. **Larger chunks = fewer cache files** - but more timeouts

The cache system is designed to be:
- ✓ Transparent - works automatically
- ✓ Robust - handles interruptions
- ✓ Efficient - saves API calls
- ✓ Safe - chunk-size aware
