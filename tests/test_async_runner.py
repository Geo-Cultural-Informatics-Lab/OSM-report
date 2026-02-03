"""
Tests for async grid runner.
"""
import pytest
import asyncio
import aiohttp
from pathlib import Path
import sys
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.async_runner import AsyncGridRunner, run_async


# Mock functions for testing
async def mock_chunk_success(grid_id):
    """Mock successful chunk processing."""
    await asyncio.sleep(0.01)  # Simulate API call
    return {"grid_id": grid_id, "result": "success", "count": 100}


async def mock_chunk_timeout(grid_id):
    """Mock chunk that times out."""
    await asyncio.sleep(10)  # Will timeout
    return {"grid_id": grid_id}


async def mock_chunk_rate_limit(grid_id, fail_count=2):
    """Mock chunk that hits rate limit then succeeds."""
    if not hasattr(mock_chunk_rate_limit, 'calls'):
        mock_chunk_rate_limit.calls = {}

    grid_calls = mock_chunk_rate_limit.calls.get(grid_id, 0)
    mock_chunk_rate_limit.calls[grid_id] = grid_calls + 1

    if grid_calls < fail_count:
        raise aiohttp.ClientError("429 Too Many Requests")

    await asyncio.sleep(0.01)
    return {"grid_id": grid_id, "result": "success"}


async def mock_chunk_permanent_fail(grid_id):
    """Mock chunk that always fails."""
    raise aiohttp.ClientError("500 Internal Server Error")


def sync_chunk_success(grid_id):
    """Synchronous mock chunk processing."""
    time.sleep(0.01)
    return {"grid_id": grid_id, "result": "sync_success"}


@pytest.fixture
def async_runner():
    """Create async runner."""
    return AsyncGridRunner(max_concurrent=5, retry_delay=0.1, max_retries=3)


@pytest.mark.asyncio
async def test_async_runner_init():
    """Test async runner initialization."""
    runner = AsyncGridRunner(max_concurrent=10, retry_delay=2.0)
    assert runner.max_concurrent == 10
    assert runner.retry_delay == 2.0
    assert runner.max_retries == 3
    assert runner.total_requests == 0


@pytest.mark.asyncio
async def test_single_grid_success(async_runner):
    """Test processing single grid successfully."""
    result = await async_runner.process_grid_chunk(
        mock_chunk_success,
        "grid_0_0",
        "grid_0_0"
    )

    assert result is not None
    assert result["grid_id"] == "grid_0_0"
    assert result["result"] == "success"
    assert async_runner.total_requests == 1
    assert async_runner.failed_requests == 0


@pytest.mark.asyncio
async def test_single_grid_rate_limit_retry(async_runner):
    """Test grid processing with rate limit retry."""
    # Reset mock call counter
    if hasattr(mock_chunk_rate_limit, 'calls'):
        mock_chunk_rate_limit.calls = {}

    result = await async_runner.process_grid_chunk(
        mock_chunk_rate_limit,
        "grid_0_0",
        "grid_0_0",
        fail_count=2
    )

    assert result is not None
    assert result["grid_id"] == "grid_0_0"
    assert async_runner.rate_limit_count >= 2  # Hit rate limit at least twice


@pytest.mark.asyncio
async def test_single_grid_permanent_failure(async_runner):
    """Test grid processing with permanent failure."""
    result = await async_runner.process_grid_chunk(
        mock_chunk_permanent_fail,
        "grid_0_0",
        "grid_0_0"
    )

    assert result is None
    assert async_runner.failed_requests == 1


@pytest.mark.asyncio
async def test_multiple_grids_success(async_runner):
    """Test processing multiple grids successfully."""
    grid_ids = [f"grid_0_{i}" for i in range(10)]
    args_list = [(gid,) for gid in grid_ids]

    results = await async_runner.process_grids(
        mock_chunk_success,
        grid_ids,
        *args_list
    )

    assert len(results) == 10
    assert all(r is not None for r in results)
    assert async_runner.total_requests == 10
    assert async_runner.failed_requests == 0

    # Check all grids processed
    processed_ids = {r["grid_id"] for r in results}
    assert processed_ids == set(grid_ids)


@pytest.mark.asyncio
async def test_multiple_grids_mixed_results(async_runner):
    """Test processing with mixed success/failure."""
    # Reset mock counters
    if hasattr(mock_chunk_rate_limit, 'calls'):
        mock_chunk_rate_limit.calls = {}

    # Create varied grid processing functions
    async def mixed_chunk(grid_id):
        if "fail" in grid_id:
            raise aiohttp.ClientError("Error")
        else:
            await asyncio.sleep(0.01)
            return {"grid_id": grid_id, "result": "success"}

    grid_ids = ["grid_0_0", "grid_fail_1", "grid_0_2", "grid_fail_3"]
    args_list = [(gid,) for gid in grid_ids]

    results = await async_runner.process_grids(
        mixed_chunk,
        grid_ids,
        *args_list
    )

    assert len(results) == 4
    successful = [r for r in results if r is not None]
    failed = [r for r in results if r is None]

    assert len(successful) == 2
    assert len(failed) == 2


@pytest.mark.asyncio
async def test_sync_function_execution(async_runner):
    """Test that sync functions are executed in executor."""
    result = await async_runner.process_grid_chunk(
        sync_chunk_success,
        "grid_0_0",
        "grid_0_0"
    )

    assert result is not None
    assert result["grid_id"] == "grid_0_0"
    assert result["result"] == "sync_success"


@pytest.mark.asyncio
async def test_concurrency_limit(async_runner):
    """Test that concurrency is limited."""
    start_time = time.time()

    # Process 20 grids with max_concurrent=5
    grid_ids = [f"grid_{i}" for i in range(20)]
    args_list = [(gid,) for gid in grid_ids]

    results = await async_runner.process_grids(
        mock_chunk_success,
        grid_ids,
        *args_list
    )

    elapsed = time.time() - start_time

    assert len(results) == 20
    assert all(r is not None for r in results)

    # With concurrency=5 and 0.01s per request, should take ~0.04s minimum
    # (4 batches of 5)
    # Allow some overhead
    assert elapsed >= 0.02  # Very conservative lower bound


def test_stats_tracking(async_runner):
    """Test statistics tracking."""
    async def test_run():
        # Process some grids
        grid_ids = ["g1", "g2", "g3"]
        args_list = [(gid,) for gid in grid_ids]

        await async_runner.process_grids(
            mock_chunk_success,
            grid_ids,
            *args_list
        )

        stats = async_runner.get_stats()
        assert stats['total_requests'] == 3
        assert stats['failed_requests'] == 0
        assert stats['success_rate'] == 1.0

        # Reset
        async_runner.reset_stats()
        stats = async_runner.get_stats()
        assert stats['total_requests'] == 0

    run_async(test_run())


def test_run_async_helper():
    """Test run_async helper function."""
    async def sample_coro():
        await asyncio.sleep(0.01)
        return "result"

    result = run_async(sample_coro())
    assert result == "result"


@pytest.mark.asyncio
async def test_exponential_backoff():
    """Test that exponential backoff is applied on rate limits."""
    # Reset mock counter
    if hasattr(mock_chunk_rate_limit, 'calls'):
        mock_chunk_rate_limit.calls = {}

    runner = AsyncGridRunner(max_concurrent=1, retry_delay=0.1, max_retries=3)

    start_time = time.time()
    result = await runner.process_grid_chunk(
        mock_chunk_rate_limit,
        "grid_0_0",
        "grid_0_0",
        fail_count=2
    )
    elapsed = time.time() - start_time

    assert result is not None
    # Should have backoffs: 0.1s, 0.2s = 0.3s minimum
    assert elapsed >= 0.2  # Conservative check


@pytest.mark.asyncio
async def test_error_in_gather():
    """Test that exceptions in gather are handled."""
    async def error_chunk(grid_id):
        raise ValueError("Test error")

    runner = AsyncGridRunner()

    results = await runner.process_grids(
        error_chunk,
        ["g1", "g2"],
        ("g1",),
        ("g2",)
    )

    assert len(results) == 2
    assert all(r is None for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
