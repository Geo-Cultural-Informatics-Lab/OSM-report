"""
OSM Country Report Generator - Main CLI

Generates comprehensive quality reports for OSM countries by integrating
geometric complexity, semantic tagging, and future completeness metrics.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Manually load editable packages (workaround for Windows Store Python .pth issue)
try:
    import site
    site_packages = site.getusersitepackages()
    pth_geometric = Path(site_packages) / "__editable__.geometric_complexity-0.1.0.pth"
    pth_tags = Path(site_packages) / "__editable__.tags_semantic_analysis-0.1.0.pth"

    if pth_geometric.exists():
        exec(pth_geometric.read_text())
    if pth_tags.exists():
        exec(pth_tags.read_text())
except Exception as e:
    # If loading fails, the orchestrator will raise an error
    logging.error(f"Could not load editable packages: {e}")
    logging.error("Please ensure all dependencies are installed correctly")
    raise RuntimeError(
        "Failed to load required packages. Please run:\n"
        "  pip install -e ../geometric_complexity\n"
        "  pip install -e ../tags_semantic_analysis\n"
        "from the report directory, or from the OSM root directory run:\n"
        "  pip install -e geometric_complexity\n"
        "  pip install -e tags_semantic_analysis"
    ) from e


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger with DEBUG level so it doesn't filter messages
    # Individual loggers will control their own levels
    logging.basicConfig(
        level=logging.DEBUG,  # Root logger accepts all levels
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Silence sub-project loggers to reduce noise
    # IMPORTANT: Set propagate=False BEFORE importing to prevent messages from reaching root logger
    for logger_name in ['geometric_complexity', 'geometrical_complexity_analysis',
                       'tags_semantic_analysis', 'tag_semantic_analysis', 'ohsome',
                       'urllib3', 'urllib3.connectionpool', 'asyncio']:
        sub_logger = logging.getLogger(logger_name)
        sub_logger.propagate = False  # Don't propagate to root logger
        sub_logger.setLevel(logging.ERROR)  # Only show errors from these modules

    # Keep report-level loggers at configured level
    logging.getLogger('core').setLevel(level)
    logging.getLogger('utils').setLevel(level)
    logging.getLogger('integrations').setLevel(level)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate OSM quality reports for countries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate report for Thailand, all years, buildings only
  python main.py --countries TH --years 2015-2025 --entities building

  # Generate for Thailand and Myanmar, specific years
  python main.py --countries TH MM --years 2020 2022 2024 --entities building road

  # Test mode: single year, single entity
  python main.py --countries TH --years 2024 --entities building --test-mode

  # Specify output directory
  python main.py --countries TH --years 2024 --entities building --output ./my_results
        """
    )

    parser.add_argument(
        '--countries',
        nargs='+',
        required=True,
        help='Country ISO codes (e.g., TH MM)'
    )

    parser.add_argument(
        '--years',
        required=True,
        help='Years to analyze (e.g., "2015-2025" or "2020 2022 2024")'
    )

    parser.add_argument(
        '--entities',
        nargs='+',
        required=True,
        choices=['building', 'road', 'highway'],
        help='Entity types to analyze'
    )

    parser.add_argument(
        '--output',
        default='./results',
        help='Output directory for results (default: ./results)'
    )

    parser.add_argument(
        '--cache',
        default='./cache',
        help='Cache directory (default: ./cache)'
    )

    parser.add_argument(
        '--chunk-size',
        type=float,
        default=50,
        help='Grid chunk size in km (default: 50)'
    )

    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=10,
        help='Max concurrent API requests (default: 10)'
    )

    parser.add_argument(
        '--api-timeout',
        type=int,
        default=30,
        help='API request timeout in seconds (default: 30)'
    )

    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Test mode: uses larger chunks, fewer grids for quick testing'
    )

    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear cache before running'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    return parser.parse_args()


def parse_years(years_str: str) -> list:
    """
    Parse years argument.

    Args:
        years_str: Year string (e.g., "2015-2025" or "2020 2022 2024")

    Returns:
        List of years
    """
    # Check if it's a range
    if '-' in years_str:
        parts = years_str.split('-')
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            return list(range(start, end + 1))

    # Otherwise, split by space
    return [int(y) for y in years_str.split()]


async def main_async(args):
    """Main async function."""
    # Import orchestrator here (after logging is configured)
    from core.orchestrator import CountryReportOrchestrator

    # Parse years
    years = parse_years(args.years)

    # Normalize entity names
    entities = [
        'highway' if e == 'road' else e
        for e in args.entities
    ]

    # Test mode adjustments
    if args.test_mode:
        chunk_size = args.chunk_size if args.chunk_size != 50 else 25  # Use smaller chunks to avoid timeouts
        max_concurrent = 5
        print(f"[TEST MODE] Using {chunk_size}km chunks and {max_concurrent} concurrent requests")
    else:
        chunk_size = args.chunk_size
        max_concurrent = args.max_concurrent

    # Initialize orchestrator
    orchestrator = CountryReportOrchestrator(
        cache_dir=args.cache,
        results_dir=args.output,
        chunk_size_km=chunk_size,
        max_concurrent=max_concurrent,
        api_timeout=args.api_timeout
    )

    # Clear cache if requested
    if args.clear_cache:
        print("Clearing cache...")
        count = orchestrator.cache.clear()
        print(f"   Deleted {count} cache files")

    # Process each country
    for country in args.countries:
        print(f"\n{'='*60}")
        print(f"Processing {country}")
        print(f"{'='*60}")
        print(f"Years: {years}")
        print(f"Entities: {entities}")
        print()

        try:
            result = await orchestrator.generate_country_report(
                iso_code=country,
                years=years,
                entities=entities
            )

            print(f"\n[SUCCESS] {country} report complete:")
            print(f"   Primary CSV: {result['primary_file']}")
            print(f"   Detail CSV: {result['detail_file']}")
            print(f"   Rows: {result['total_rows']}")
            print(f"   Tag details: {result['total_tag_details']}")

        except Exception as e:
            print(f"\n[ERROR] Failed to process {country}: {e}")
            import traceback
            traceback.print_exc()

    # Print cache stats
    stats = orchestrator.cache.get_cache_stats()
    print(f"\n[CACHE] Statistics:")
    print(f"   Total files: {stats['total_files']}")
    print(f"   Total size: {stats['total_size_mb']:.2f} MB")

    # Print async stats
    async_stats = orchestrator.async_runner.get_stats()
    print(f"\n[API] Statistics:")
    print(f"   Total requests: {async_stats['total_requests']}")
    print(f"   Failed requests: {async_stats['failed_requests']}")
    print(f"   Rate limits hit: {async_stats['rate_limit_count']}")
    print(f"   Success rate: {async_stats['success_rate']:.1%}")


def main():
    """Main entry point."""
    # Import run_async here (lightweight utility, no heavy imports)
    from utils.async_runner import run_async

    # Parse args first to get verbosity level (before imports)
    args = parse_args()

    # Setup logging BEFORE importing orchestrator to suppress sub-project loggers
    setup_logging(args.verbose)

    # Print header
    print("=" * 60)
    print("OSM Country Report Generator")
    print("=" * 60)
    print()

    # Run async main
    try:
        run_async(main_async(args))
        print("\n[DONE] All complete!")
    except KeyboardInterrupt:
        print("\n[WARNING] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
