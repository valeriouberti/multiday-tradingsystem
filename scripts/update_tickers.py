"""Update tickers in a config YAML file.

Usage:
    python scripts/update_tickers.py config/ita.yaml "STLAM.MI,FCT.MI,ENI.MI"
    python scripts/update_tickers.py config/etf.yaml "XDW0.MI,DFND.MI,XDWI.MI"
"""

import sys

import yaml


def update_tickers(config_path: str, tickers_csv: str) -> None:
    tickers = [t.strip() for t in tickers_csv.split(",") if t.strip()]
    if not tickers:
        print("No tickers provided, skipping update")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    config["tickers"] = tickers

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Updated {config_path} with tickers: {tickers}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <config.yaml> <TICK1,TICK2,TICK3>")
        sys.exit(1)
    update_tickers(sys.argv[1], sys.argv[2])
