"""US S&P 500 CFD wrapper — delegates to main.py --mode us.

Kept for backward compatibility. Prefer: python main.py --mode us
"""
import sys

sys.argv[1:1] = ["--mode", "us"]

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
