"""Shared fixtures for tests."""

import sys
from pathlib import Path

# Make `src` importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
