"""Unified entry point for all three trading strategies.

Usage:
    python main.py --mode ita                              # ITA — all FTSE MIB stocks
    python main.py --mode ita --tickers "ISP.MI,UCG.MI"    # ITA — specific tickers
    python main.py --mode us                               # US — top 100 S&P 500
    python main.py --mode us --tickers "AAPL,MSFT,NVDA"    # US — specific tickers
    python main.py --mode etf                              # ETF — sector ETFs
"""

import argparse
import logging
import time

import yaml

from shared.data import prefetch_all
from shared.indicators import check_adx_regime, check_vix_regime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Mode configuration ───────────────────────────────────────────────────

MODE_CONFIG = {
    "ita": {
        "config_default": "config_ita.yaml",
        "description": "Multiday CFD Trading Validator — Italian Stocks",
        "benchmark_default": "ETFMIB.MI",
        "has_tickers_override": True,
        "has_ranking": False,
        "has_etf_gates": False,
        "dedup_tickers": False,
    },
    "us": {
        "config_default": "config_us.yaml",
        "description": "Multiday CFD Trading Validator — US S&P 500",
        "benchmark_default": "SPY",
        "has_tickers_override": True,
        "has_ranking": True,
        "has_etf_gates": False,
        "dedup_tickers": True,
    },
    "etf": {
        "config_default": "config_etf.yaml",
        "description": "Multiday CFD Trading Validator — ETF Sector Strategy",
        "benchmark_default": "CSSPX.MI",
        "has_tickers_override": False,
        "has_ranking": False,
        "has_etf_gates": True,
        "dedup_tickers": False,
    },
}


def _get_mode_modules(mode: str):
    """Lazy-import mode-specific scorer, report, and telegram modules."""
    if mode == "ita":
        from validator_ita.scorer import score_ticker
        from validator_ita.report import print_report, save_csv
        from shared.telegram import send_ita_report as send_report
        return score_ticker, None, print_report, save_csv, send_report
    elif mode == "us":
        from validator_us.scorer import score_ticker, rank_results
        from validator_us.report import print_report, save_csv
        from shared.telegram import send_us_report as send_report
        return score_ticker, rank_results, print_report, save_csv, send_report
    elif mode == "etf":
        from validator_etf.scorer import score_ticker
        from validator_etf.report import print_report, save_csv
        from shared.telegram import send_etf_report as send_report
        return score_ticker, None, print_report, save_csv, send_report
    else:
        raise ValueError(f"Unknown mode: {mode}")


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Multiday Trading Validator")
    parser.add_argument(
        "--mode", required=True, choices=list(MODE_CONFIG.keys()),
        help="Strategy mode: ita, us, or etf",
    )
    parser.add_argument(
        "--config",
        help="Path to config file (default: auto from mode)",
    )
    parser.add_argument(
        "--tickers",
        help="Override config tickers (comma-separated, ITA/US only)",
    )
    args = parser.parse_args()

    mode = args.mode
    mcfg = MODE_CONFIG[mode]

    # ── Config ────────────────────────────────────────────────────────
    config_path = args.config or mcfg["config_default"]
    config = load_config(config_path)

    # ── Tickers ───────────────────────────────────────────────────────
    if args.tickers and mcfg["has_tickers_override"]:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = config["tickers"]

    if mcfg["dedup_tickers"]:
        seen = set()
        unique = []
        for t in tickers:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        tickers = unique

    benchmark = config.get("benchmark", mcfg["benchmark_default"])

    logger.info(
        "[%s] Validating %d tickers (benchmark: %s)",
        mode.upper(), len(tickers), benchmark,
    )
    start = time.time()

    # ── Modules ───────────────────────────────────────────────────────
    score_ticker, rank_results, print_report, save_csv, send_report = (
        _get_mode_modules(mode)
    )

    # ── Data prefetch ─────────────────────────────────────────────────
    prefetch_all(tickers, config)

    # ── Gates ─────────────────────────────────────────────────────────
    vix_ok, vix_value = check_vix_regime(config)
    adx_ok, adx_value = check_adx_regime(config)

    correlations = None
    bench_ok = True
    correlated_tickers: set[str] = set()

    if mcfg["has_etf_gates"]:
        from validator_etf.indicators import check_bench_health, check_correlations
        bench_ok, _ = check_bench_health(config)
        correlations = check_correlations(tickers, config)
        for t1, t2, _ in correlations["correlated_pairs"]:
            correlated_tickers.add(t1)
            correlated_tickers.add(t2)

    # ── Score each ticker ─────────────────────────────────────────────
    results = []
    for i, ticker in enumerate(tickers, 1):
        gates = {
            "vix_ok": vix_ok,
            "vix_value": vix_value,
            "adx_ok": adx_ok,
            "adx_value": adx_value,
        }
        if mcfg["has_etf_gates"]:
            gates["bench_ok"] = bench_ok
            gates["is_correlated"] = ticker in correlated_tickers

        logger.info("[%d/%d] Scoring %s vs %s", i, len(tickers), ticker, benchmark)
        result = score_ticker(ticker, config, gates)
        results.append(result)

    # ── Ranking (US only) ─────────────────────────────────────────────
    if mcfg["has_ranking"] and rank_results is not None:
        top_n = config.get("alerts", {}).get("top_n", 5)
        results = rank_results(results, top_n=top_n)

    # ── Output ────────────────────────────────────────────────────────
    if mode == "etf":
        print_report(results, config, correlations)
        save_csv(results, config, correlations)
        send_report(results, config, correlations)
    else:
        print_report(results, config)
        save_csv(results, config)
        send_report(results, config)

    elapsed = time.time() - start
    logger.info("Done in %.1f seconds (%d tickers)", elapsed, len(tickers))


if __name__ == "__main__":
    main()
