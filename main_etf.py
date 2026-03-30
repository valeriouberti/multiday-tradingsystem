"""ETF Sector wrapper — delegates to main.py --mode etf.

Kept for backward compatibility. Prefer: python main.py --mode etf
"""
import sys

sys.argv[1:1] = ["--mode", "etf"]

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
