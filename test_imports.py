#!/usr/bin/env python
"""
Diagnostic script to test all imports.
Run this from the report directory: python test_imports.py
"""

import sys
from pathlib import Path

print("=" * 70)
print("IMPORT DIAGNOSTIC TEST")
print("=" * 70)
print()

# Show environment info
print(f"Python executable: {sys.executable}")
print(f"Current directory: {Path.cwd()}")
print(f"Script location: {Path(__file__).parent.resolve()}")
print()
print("Python path (first 5 entries):")
for i, p in enumerate(sys.path[:5], 1):
    print(f"  {i}. {p}")
print()

# Test 1: Core dependencies
print("=" * 70)
print("TEST 1: Core Dependencies")
print("=" * 70)
tests_passed = 0
tests_failed = 0

deps = ['pandas', 'numpy', 'geopandas', 'shapely', 'requests', 'aiohttp', 'tqdm']
for dep in deps:
    try:
        __import__(dep)
        print(f"  ✓ {dep}")
        tests_passed += 1
    except ImportError as e:
        print(f"  ✗ {dep}: {e}")
        tests_failed += 1
print()

# Test 2: Local utils module
print("=" * 70)
print("TEST 2: Local Modules (utils, core, integrations)")
print("=" * 70)
try:
    from utils.async_runner import AsyncGridRunner
    print("  ✓ utils.async_runner.AsyncGridRunner")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ utils.async_runner: {e}")
    tests_failed += 1

try:
    from core.cache_manager import CacheManager
    print("  ✓ core.cache_manager.CacheManager")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ core.cache_manager: {e}")
    tests_failed += 1

try:
    from integrations.completeness_adapter import CompletenessAdapter
    print("  ✓ integrations.completeness_adapter.CompletenessAdapter")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ integrations.completeness_adapter: {e}")
    tests_failed += 1
print()

# Test 3: Editable packages
print("=" * 70)
print("TEST 3: Editable Packages (geometric_complexity, tags_semantic_analysis)")
print("=" * 70)
try:
    from geometric_complexity.core import analyzer
    print("  ✓ geometric_complexity.core.analyzer")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ geometric_complexity: {e}")
    print("     Run: pip install -e ../geometric_complexity")
    tests_failed += 1

try:
    from tags_semantic_analysis.analysis.chunked_analysis import ChunkedTagAnalyzer
    print("  ✓ tags_semantic_analysis.analysis.chunked_analysis.ChunkedTagAnalyzer")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ tags_semantic_analysis: {e}")
    print("     Run: pip install -e ../tags_semantic_analysis")
    tests_failed += 1
print()

# Test 4: Adapters (require editable packages)
print("=" * 70)
print("TEST 4: Adapter Integration")
print("=" * 70)
try:
    from integrations.geometric_complexity_adapter import GeometricComplexityAdapter
    print("  ✓ integrations.geometric_complexity_adapter.GeometricComplexityAdapter")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ GeometricComplexityAdapter: {e}")
    tests_failed += 1

try:
    from integrations.semantic_tags_adapter import SemanticTagsAdapter
    print("  ✓ integrations.semantic_tags_adapter.SemanticTagsAdapter")
    tests_passed += 1
except ImportError as e:
    print(f"  ✗ SemanticTagsAdapter: {e}")
    tests_failed += 1
print()

# Test 5: Full orchestrator import
print("=" * 70)
print("TEST 5: Full Orchestrator")
print("=" * 70)
try:
    from core.orchestrator import CountryReportOrchestrator
    print("  ✓ core.orchestrator.CountryReportOrchestrator")
    tests_passed += 1
except Exception as e:
    print(f"  ✗ CountryReportOrchestrator: {e}")
    tests_failed += 1
print()

# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Tests passed: {tests_passed}")
print(f"Tests failed: {tests_failed}")
print()

if tests_failed == 0:
    print("✓ ALL TESTS PASSED - Your environment is correctly configured!")
    print()
    print("You can now run:")
    print("  python main.py --countries TH --years 2024 --entities building --test-mode")
    sys.exit(0)
else:
    print("✗ SOME TESTS FAILED - Please fix the issues above")
    print()
    print("If core dependencies failed, run:")
    print("  pip install -r requirements.txt")
    print()
    print("If editable packages failed, run:")
    print("  pip install -e ../geometric_complexity")
    print("  pip install -e ../tags_semantic_analysis")
    sys.exit(1)
