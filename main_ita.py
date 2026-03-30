"""ITA CFD wrapper — delegates to main.py --mode ita.

Kept for backward compatibility. Prefer: python main.py --mode ita
"""
import sys

sys.argv[1:1] = ["--mode", "ita"]

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
