"""Backward-compatible entry point for the complete reviewer demonstration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reviewer_demo import main  # noqa: E402

if __name__ == "__main__":
    main()
