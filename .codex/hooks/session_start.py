from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import safe_main


if __name__ == "__main__":
    raise SystemExit(safe_main("SessionStart"))
