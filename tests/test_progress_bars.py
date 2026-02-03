"""
Test progress bars (visual verification).

Run manually to see progress bars in action.
"""
import asyncio
import time
from tqdm import tqdm


async def mock_grid_processing(grid_id):
    """Mock grid processing with delay."""
    await asyncio.sleep(0.1)  # Simulate API call
    return {"grid_id": grid_id, "result": "success"}


async def test_async_progress():
    """Test async progress bar."""
    from tqdm.asyncio import tqdm as async_tqdm

    # Create mock tasks
    tasks = [mock_grid_processing(f"grid_{i}") for i in range(20)]

    # Process with progress bar
    results = await async_tqdm.gather(
        *tasks,
        desc="Processing grids",
        unit="grid"
    )

    print(f"[OK] Processed {len(results)} grids")
    assert len(results) == 20


def test_sync_progress():
    """Test sync progress bar."""
    years = [2020, 2021, 2022]
    entities = ['building', 'road']

    total = len(years) * len(entities)

    pbar = tqdm(
        total=total,
        desc="Processing",
        unit="combo",
        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
    )

    for year in years:
        for entity in entities:
            pbar.set_description(f"Processing {year} {entity}")
            time.sleep(0.2)  # Simulate work
            pbar.update(1)

    pbar.close()
    print("[OK] Sync progress complete")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Progress Bars")
    print("=" * 60)
    print()

    print("1. Testing sync progress bar...")
    test_sync_progress()
    print()

    print("2. Testing async progress bar...")
    asyncio.run(test_async_progress())
    print()

    print("[SUCCESS] All progress bar tests complete!")
