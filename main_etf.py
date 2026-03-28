import argparse
import logging
import time

import yaml

from shared.data import prefetch_all
from shared.indicators import check_adx_regime, check_vix_regime
from shared.telegram import send_etf_report
from validator_etf.indicators import check_bench_health, check_correlations
from validator_etf.report import print_report, save_csv
from validator_etf.scorer import score_ticker

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
        description="Multiday CFD Trading Validator v2.1 — ETF Sector Strategy"
    )
    parser.add_argument(
        "--config", default="config_etf.yaml",
        help="Path to ETF config file (default: config_etf.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    tickers = config["tickers"]
    benchmark = config.get("benchmark", "CSSPX.MI")

    logger.info(
        "Validating %d sector ETFs: %s (benchmark: %s)",
        len(tickers), ", ".join(tickers), benchmark,
    )
    start = time.time()

    # --- Batch-download all data upfront (1-3 HTTP calls instead of N*3) ---
    prefetch_all(tickers, config)

    # --- Compute gates (shared across all tickers) ---
    vix_ok, vix_value = check_vix_regime(config)
    bench_ok, _ = check_bench_health(config)
    adx_ok, adx_value = check_adx_regime(config)
    correlations = check_correlations(tickers, config)

    # Per-ticker correlation flag: is THIS ticker part of a correlated pair?
    correlated_tickers = set()
    for t1, t2, _ in correlations["correlated_pairs"]:
        correlated_tickers.add(t1)
        correlated_tickers.add(t2)

    # --- Score each ticker ---
    results = []
    for ticker in tickers:
        gates = {
            "vix_ok": vix_ok,
            "vix_value": vix_value,
            "bench_ok": bench_ok,
            "adx_ok": adx_ok,
            "adx_value": adx_value,
            "is_correlated": ticker in correlated_tickers,
        }
        logger.info("Scoring %s vs %s", ticker, benchmark)
        result = score_ticker(ticker, config, gates)
        results.append(result)

    # --- Output ---
    print_report(results, config, correlations)
    save_csv(results, config, correlations)
    send_etf_report(results, config, correlations)

    elapsed = time.time() - start
    logger.info("Done in %.1f seconds", elapsed)


if __name__ == "__main__":
    main()
