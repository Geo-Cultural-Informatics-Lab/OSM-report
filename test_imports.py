#!/usr/bin/env python
"""Test if packages are importable."""

import sys
print("Python:", sys.executable)
print("sys.path:", sys.path[:3])

try:
    from geometric_complexity.core import analyzer
    print("✓ geometric_complexity imported successfully")
except ImportError as e:
    print(f"✗ geometric_complexity import failed: {e}")

try:
    from tags_semantic_analysis.analysis.chunked_analysis import ChunkedTagAnalyzer
    print("✓ tags_semantic_analysis imported successfully")
except ImportError as e:
    print(f"✗ tags_semantic_analysis import failed: {e}")

# Now try the adapters
sys.path.insert(0, '.')

try:
    from integrations.geometric_complexity_adapter import GeometricComplexityAdapter
    print("✓ GeometricComplexityAdapter imported successfully")
except ImportError as e:
    print(f"✗ GeometricComplexityAdapter import failed: {e}")

try:
    from integrations.semantic_tags_adapter import SemanticTagsAdapter
    print("✓ SemanticTagsAdapter imported successfully")
except ImportError as e:
    print(f"✗ SemanticTagsAdapter import failed: {e}")
