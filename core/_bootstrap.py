"""
Bootstrap module to load editable packages before any other imports.

This must be imported FIRST to ensure geometric_complexity and tags_semantic_analysis
packages are available when adapters try to import them.
"""

import sys
import site

# Add site-packages to sys.path if not already there
site_packages = site.getusersitepackages()
if site_packages not in sys.path:
    sys.path.insert(0, site_packages)

# Import and install the finder modules for editable packages
# This is required for Windows Store Python which doesn't auto-process .pth files
try:
    import __editable___geometric_complexity_0_1_0_finder
    __editable___geometric_complexity_0_1_0_finder.install()
except ImportError:
    # Module doesn't exist, package not installed
    pass

try:
    import __editable___tags_semantic_analysis_0_1_0_finder
    __editable___tags_semantic_analysis_0_1_0_finder.install()
except ImportError:
    # Module doesn't exist, package not installed
    pass
