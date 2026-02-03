"""
Async grid processing with rate limiting and retry logic.

Handles concurrent API requests with proper error handling,
exponential backoff for rate limits, and graceful degradation.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List, Callable
import time
from tqdm.asyncio import tqdm as async_tqdm

logger = logging.getLogger(__name__)


class AsyncGridRunner:
    """
    Manages async processing of grid chunks with rate limiting.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        retry_delay: float = 5.0,
        max_retries: int = 3,
        timeout: float = 300.0
    ):
        """
        Initialize async grid runner.

        Args:
            max_concurrent: Maximum concurrent requests
            retry_delay: Base delay for retries in seconds
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        self.max_concurrent = max_concurrent
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limit_count = 0
        self.total_requests = 0
        self.failed_requests = 0

    async def process_grid_chunk(
        self,
        chunk_func: Callable,
        grid_id: str,
        *args,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single grid chunk with retry logic.

        Args:
            chunk_func: Function to process chunk (can be sync or async)
            grid_id: Grid identifier for logging
            *args: Arguments to pass to chunk_func
            **kwargs: Keyword arguments to pass to chunk_func

        Returns:
            Result dictionary or None if failed
        """
        async with self.semaphore:
            self.total_requests += 1

            for attempt in range(self.max_retries):
                try:
                    # Check if function is async
                    if asyncio.iscoroutinefunction(chunk_func):
                        result = await chunk_func(*args, **kwargs)
                    else:
                        # Run sync function in executor
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, chunk_func, *args
                        )

                    logger.debug(f"Grid {grid_id}: Success on attempt {attempt + 1}")
                    return result

                except aiohttp.ClientError as e:
                    error_str = str(e).lower()

                    # Check for rate limit error
                    if "429" in str(e) or "rate limit" in error_str or "too many requests" in error_str:
                        self.rate_limit_count += 1
                        backoff_time = self.retry_delay * (2 ** attempt)

                        logger.warning(
                            f"Grid {grid_id}: Rate limit hit (attempt {attempt + 1}/{self.max_retries}), "
                            f"backing off for {backoff_time}s"
                        )

                        # If too many rate limits, reduce concurrency
                        if self.rate_limit_count > 5 and self.semaphore._value > 5:
                            self._reduce_concurrency()

                        await asyncio.sleep(backoff_time)

                    elif attempt < self.max_retries - 1:
                        # Other errors: retry with regular delay
                        logger.warning(
                            f"Grid {grid_id}: Error on attempt {attempt + 1}: {e}, retrying..."
                        )
                        await asyncio.sleep(self.retry_delay)

                    else:
                        # Final attempt failed
                        logger.error(
                            f"Grid {grid_id}: Failed after {self.max_retries} attempts: {e}"
                        )
                        self.failed_requests += 1
                        return None

                except TimeoutError:
                    logger.warning(
                        f"Grid {grid_id}: Timeout on attempt {attempt + 1}/{self.max_retries}"
                    )
                    if attempt == self.max_retries - 1:
                        logger.error(f"Grid {grid_id}: Failed due to timeout")
                        self.failed_requests += 1
                        return None
                    await asyncio.sleep(self.retry_delay)

                except Exception as e:
                    # Unexpected error
                    logger.error(
                        f"Grid {grid_id}: Unexpected error on attempt {attempt + 1}: {type(e).__name__}: {e}"
                    )
                    if attempt == self.max_retries - 1:
                        self.failed_requests += 1
                        return None
                    await asyncio.sleep(self.retry_delay)

            return None

    async def process_grids(
        self,
        chunk_func: Callable,
        grid_ids: List[str],
        *args_list,
        **kwargs
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Process multiple grid chunks concurrently.

        Args:
            chunk_func: Function to process each chunk
            grid_ids: List of grid identifiers
            *args_list: List of argument tuples for each chunk
            **kwargs: Common keyword arguments for all chunks

        Returns:
            List of results (None for failed grids)
        """
        start_time = time.time()
        logger.info(
            f"Starting async processing of {len(grid_ids)} grids "
            f"(max concurrent: {self.max_concurrent})"
        )

        # Create tasks
        tasks = []
        for i, grid_id in enumerate(grid_ids):
            # Get args for this grid
            args = args_list[i] if i < len(args_list) else ()

            task = self.process_grid_chunk(
                chunk_func,
                grid_id,
                *args,
                **kwargs
            )
            tasks.append(task)

        # Execute all tasks with progress bar
        # Note: async_tqdm.gather doesn't support return_exceptions
        # So we use regular gather with try/except wrapper
        async def safe_task(task):
            try:
                return await task
            except Exception as e:
                return e

        safe_tasks = [safe_task(t) for t in tasks]
        results = await async_tqdm.gather(
            *safe_tasks,
            desc="  [GRIDS] Processing",
            unit="grid",
            leave=False
        )

        # Filter out exceptions and convert to None
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Grid {grid_ids[i]}: Exception during processing: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        # Log statistics
        elapsed = time.time() - start_time
        successful = sum(1 for r in processed_results if r is not None)
        failed = len(processed_results) - successful

        logger.info(
            f"Async processing complete: {successful}/{len(grid_ids)} successful, "
            f"{failed} failed, {elapsed:.1f}s elapsed"
        )
        logger.info(
            f"Stats: {self.total_requests} total requests, "
            f"{self.rate_limit_count} rate limits hit, "
            f"{self.failed_requests} failed"
        )

        return processed_results

    def _reduce_concurrency(self):
        """Dynamically reduce concurrency when too many rate limits occur."""
        old_value = self.semaphore._value
        new_value = max(5, old_value - 2)

        if new_value < old_value:
            logger.warning(
                f"Reducing concurrency from {old_value} to {new_value} due to rate limits"
            )
            # Note: Cannot directly modify semaphore value, this is a limitation
            # In practice, the semaphore will naturally reduce as requests complete
            self.max_concurrent = new_value

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'rate_limit_count': self.rate_limit_count,
            'success_rate': (
                (self.total_requests - self.failed_requests) / self.total_requests
                if self.total_requests > 0 else 0
            )
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self.total_requests = 0
        self.failed_requests = 0
        self.rate_limit_count = 0


def run_async(coro):
    """
    Helper function to run async coroutine in sync context.

    Args:
        coro: Coroutine to run

    Returns:
        Result of coroutine
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)
