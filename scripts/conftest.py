"""Pytest configuration for scripts/ tests.

Adds the scripts/ directory to sys.path so that test files can import
ai_review and other top-level scripts directly (e.g. ``import ai_review``).
No package installation or __init__.py files are required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
