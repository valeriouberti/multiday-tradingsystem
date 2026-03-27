import argparse
import logging
import time

import yaml

from shared.indicators import check_adx_regime, check_vix_regime
from shared.telegram import send_ita_report
from validator_ita.report import print_report, save_csv
from validator_ita.scorer import score_ticker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Multiday CFD Trading Validator v1.0 — Italian Stocks"
    )
    parser.add_argument(
        "--config", default="config_ita.yaml",
        help="Path to Italian config file (default: config_ita.yaml)",
    )
    parser.add_argument(
        "--tickers",
        help="Override config tickers (comma-separated, e.g. ENI.MI,LDO.MI,PRY.MI)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else config["tickers"]
    benchmark = config.get("benchmark", "ETFMIB.MI")

    logger.info(
        "Validating %d Italian stocks: %s (benchmark: %s)",
        len(tickers), ", ".join(tickers), benchmark,
    )
    start = time.time()

    # --- Compute gates (shared across all tickers) ---
    vix_ok, vix_value = check_vix_regime(config)
    adx_ok, adx_value = check_adx_regime(config)

    # --- Score each ticker ---
    results = []
    for ticker in tickers:
        gates = {
            "vix_ok": vix_ok,
            "vix_value": vix_value,
            "adx_ok": adx_ok,
            "adx_value": adx_value,
        }
        logger.info("Scoring %s vs %s", ticker, benchmark)
        result = score_ticker(ticker, config, gates)
        results.append(result)

    # --- Output ---
    print_report(results, config)
    save_csv(results, config)
    send_ita_report(results, config)

    elapsed = time.time() - start
    logger.info("Done in %.1f seconds", elapsed)


if __name__ == "__main__":
    main()
