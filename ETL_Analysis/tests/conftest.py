"""Make the repository root importable so `from ETL_Analysis import ...` works
when pytest is run from either the repo root or this folder.

Remove this once the sprint's packaging metadata (pyproject.toml) is in place
and the project is installed with `pip install -e`.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
