import argparse
import logging
import time

import yaml

from shared.data import prefetch_all
from shared.indicators import check_adx_regime, check_vix_regime
from shared.telegram import send_us_report, send_us_deepdive_prompt
from validator_us.report import print_report, save_csv
from validator_us.scorer import rank_results, score_ticker

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
        description="Multiday CFD Trading Validator v1.0 — US S&P 500"
    )
    parser.add_argument(
        "--config", default="config_us.yaml",
        help="Path to US config file (default: config_us.yaml)",
    )
    parser.add_argument(
        "--tickers",
        help="Override config tickers (comma-separated, e.g. AAPL,MSFT,NVDA)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else config["tickers"]
    # Deduplicate while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
    tickers = unique_tickers

    benchmark = config.get("benchmark", "SPY")

    logger.info(
        "Validating %d US stocks (benchmark: %s)",
        len(tickers), benchmark,
    )
    start = time.time()

    # --- Batch-download all data upfront (1-3 HTTP calls instead of N*3) ---
    prefetch_all(tickers, config)

    # --- Compute gates (shared across all tickers) ---
    vix_ok, vix_value = check_vix_regime(config)
    adx_ok, adx_value = check_adx_regime(config)

    # --- Score each ticker ---
    results = []
    for i, ticker in enumerate(tickers, 1):
        gates = {
            "vix_ok": vix_ok,
            "vix_value": vix_value,
            "adx_ok": adx_ok,
            "adx_value": adx_value,
        }
        logger.info("[%d/%d] Scoring %s vs %s", i, len(tickers), ticker, benchmark)
        result = score_ticker(ticker, config, gates)
        results.append(result)

    # --- Rank and select top N ---
    top_n = config["alerts"].get("top_n", 5)
    results = rank_results(results, top_n=top_n)

    # --- Output ---
    print_report(results, config)
    save_csv(results, config)
    send_us_report(results, config)
    send_us_deepdive_prompt(results, config)

    elapsed = time.time() - start
    logger.info("Done in %.1f seconds (%d tickers)", elapsed, len(tickers))


if __name__ == "__main__":
    main()
