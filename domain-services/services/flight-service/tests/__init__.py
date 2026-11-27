"""Tests run from domain-services/services/flight-service/:  python3 -m unittest

The service code lives in src/; it is put on the import path here.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
