import csv
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from shared.report_utils import check_cell as _check_cell
from shared.report_utils import status_text as _status_text

console = Console()


def print_report(results: list[dict], config: dict, correlations: dict) -> None:
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    console.print()
    console.print(
        f"\U0001f4ca Multiday ETF Validator v2.1 \u2014 {now.strftime('%Y-%m-%d %H:%M %Z')}",
        style="bold",
    )

    # --- Gates banner ---
    if results:
        gates = results[0].get("gates", {})

        vix_ok = gates.get("vix_ok", True)
        vix_val = gates.get("vix_value", 0)
        if vix_ok:
            console.print(f"[green]VIX: {vix_val} \u2705 Low volatility[/green]")
        else:
            console.print(
                f"[bold red]VIX: {vix_val} \u274c High volatility "
                "\u2014 GO signals downgraded[/bold red]"
            )

        bench_ok = gates.get("bench_ok", True)
        bench = config.get("benchmark", "CSSPX.MI")
        if bench_ok:
            console.print(f"[green]{bench}: \u2705 Uptrend (EMA20 > EMA50)[/green]")
        else:
            console.print(
                f"[bold red]{bench}: \u274c Downtrend "
                "\u2014 GO signals downgraded[/bold red]"
            )

        adx_ok = gates.get("adx_ok", True)
        adx_val = gates.get("adx_value", 0)
        if adx_ok:
            console.print(f"[green]ADX: {adx_val} \u2705 Trending market[/green]")
        else:
            console.print(
                f"[bold red]ADX: {adx_val} \u274c Range-bound "
                "\u2014 momentum signals unreliable[/bold red]"
            )

        if correlations.get("any_correlated"):
            for t1, t2, corr in correlations["correlated_pairs"]:
                console.print(
                    f"[bold yellow]\u26a0\ufe0f  CORRELATION: {t1} / {t2} = {corr} "
                    "\u2014 halve combined size[/bold yellow]"
                )
        else:
            console.print("[green]Correlation: \u2705 No overlap detected[/green]")

    console.print()

    # --- Position sizing info ---
    ps = config.get("position_sizing", {})
    capital = ps.get("capital", 4000)
    risk_pct = ps.get("risk_per_trade", 0.015)
    commission = ps.get("commission", 2.95)
    max_cap_pct = ps.get("max_capital_pct", 0.40)
    console.print(
        f"[dim]Capital: \u20ac{capital:,.0f} | Risk/trade: {risk_pct*100:.1f}% "
        f"(\u20ac{capital*risk_pct:,.0f}) | Commission: \u20ac{commission:.2f}/trade "
        f"| Max/position: {max_cap_pct*100:.0f}% (\u20ac{capital*max_cap_pct:,.0f})[/dim]"
    )
    console.print()

    # --- Main table ---
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("ETF", style="bold", no_wrap=True)
    table.add_column("Score", justify="center", no_wrap=True)
    table.add_column("EMA D", justify="center", no_wrap=True)
    table.add_column("EMA W", justify="center", no_wrap=True)
    table.add_column("MACD", justify="center", no_wrap=True)
    table.add_column("RSI", justify="center", no_wrap=True)
    table.add_column("MFI", justify="center", no_wrap=True)
    table.add_column("RS", justify="center", no_wrap=True)
    table.add_column("Premkt", justify="right", no_wrap=True)
    table.add_column("Stop", justify="right", no_wrap=True)
    table.add_column("TP1", justify="right", no_wrap=True)
    table.add_column("Trail", justify="right", no_wrap=True)
    table.add_column("Size", justify="right", no_wrap=True)
    table.add_column("GO?", justify="center", no_wrap=True)

    for r in results:
        checks = r["checks"]
        pm = f"{r['premarket_pct']:+.2f}%"
        pm_text = Text(pm, style="green" if r["premarket_pct"] >= 0 else "red")
        stop_str = f"\u20ac{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A"
        tp1_str = f"\u20ac{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A"
        chand_str = f"\u20ac{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A"
        size_str = str(r["position_size"]) if r["position_size"] > 0 else "N/A"

        table.add_row(
            r["ticker"],
            f"{r['score']}/{r['max_score']}",
            _check_cell(checks["EMA D"]),
            _check_cell(checks["EMA W"]),
            _check_cell(checks["MACD"]),
            _check_cell(checks["RSI"]),
            _check_cell(checks["MFI"]),
            _check_cell(checks["RS"]),
            pm_text,
            stop_str,
            tp1_str,
            chand_str,
            size_str,
            _status_text(r),
        )

    console.print(table)

    go_count = sum(1 for r in results if r["status"] == "GO")
    watch_count = sum(1 for r in results if r["status"] == "WATCH")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    summary = Text()
    summary.append(f"{go_count} GO", style="bold green")
    summary.append("  |  ")
    summary.append(f"{watch_count} WATCH", style="bold yellow")
    summary.append("  |  ")
    summary.append(f"{skip_count} SKIP", style="bold red")
    console.print(summary)
    console.print()

    # --- Broker action plan ---
    go_etfs = [r for r in results if r["status"] == "GO"]
    watch_etfs = [r for r in results if r["status"] == "WATCH"]

    if go_etfs:
        console.print("[bold]ETF \u2014 Ordini da impostare (buy a mercato 14:30-16:30 CET):[/bold]")
        console.print()
        for r in go_etfs:
            console.print(f"[bold green]{r['ticker']} \u2014 BUY[/bold green]")

            close_price = r.get("last_close", 0)
            if close_price > 0:
                console.print(f"  Ultimo close:    \u20ac{close_price:.2f}")

            console.print(f"  Stop Loss:       \u20ac{r['stop_loss']:.2f}  (inserire subito dopo entry)")
            console.print(f"  TP1 (50%):       \u20ac{r['tp1_price']:.2f}  (ordine limite)")
            console.print(f"  Trailing Stop:   \u20ac{r['chandelier_stop']:.2f}  (aggiornare ogni sera)")
            notional = r["position_size"] * close_price
            comm = config.get("position_sizing", {}).get("commission", 2.95)
            round_trip = comm * 2
            console.print(f"  Size:            {r['position_size']} shares (\u20ac{notional:,.0f})")
            console.print(f"  [dim]Commissioni: \u20ac{round_trip:.2f} round-trip[/dim]")
            console.print()

    if watch_etfs:
        tickers_watch = ", ".join(r["ticker"] for r in watch_etfs)
        console.print(f"[bold yellow]{tickers_watch}: WATCH \u2014 score o gate insufficiente, non operare[/bold yellow]")
        console.print()

    if not go_etfs and not watch_etfs:
        console.print("[dim]Nessun ETF operabile oggi.[/dim]")
        console.print()


def save_csv(results: list[dict], config: dict, correlations: dict) -> None:
    if not config["output"].get("save_csv", True):
        return

    csv_dir = config["output"].get("csv_dir", "output/reports_etf")
    os.makedirs(csv_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d") + ".csv"
    filepath = os.path.join(csv_dir, filename)

    fieldnames = [
        "ETF", "Score", "EMA D", "EMA W", "MACD", "RSI", "MFI",
        "RS", "VIX Gate", "Bench Gate", "ADX Gate", "Corr Gate",
        "Premarket %", "Stop Loss", "TP1", "Chandelier Stop", "Position Size",
        "Status", "Gate Reasons",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            checks = r["checks"]
            gates = r.get("gates", {})
            writer.writerow({
                "ETF": r["ticker"],
                "Score": f"{r['score']}/{r['max_score']}",
                "EMA D": "PASS" if checks["EMA D"]["passed"] else "FAIL",
                "EMA W": "PASS" if checks["EMA W"]["passed"] else "FAIL",
                "MACD": "PASS" if checks["MACD"]["passed"] else "FAIL",
                "RSI": f"{'PASS' if checks['RSI']['passed'] else 'FAIL'}"
                       + (f" ({checks['RSI']['display']})" if checks["RSI"]["display"] else ""),
                "MFI": f"{'PASS' if checks['MFI']['passed'] else 'FAIL'}"
                       + (f" ({checks['MFI']['display']})" if checks["MFI"]["display"] else ""),
                "RS": "PASS" if checks["RS"]["passed"] else "FAIL",
                "VIX Gate": "OK" if gates.get("vix_ok", True) else "HIGH",
                "Bench Gate": "OK" if gates.get("bench_ok", True) else "DOWN",
                "ADX Gate": "OK" if gates.get("adx_ok", True) else "RANGE",
                "Corr Gate": "OK" if not gates.get("is_correlated") else "WARN",
                "Premarket %": f"{r['premarket_pct']:+.2f}%",
                "Stop Loss": f"{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A",
                "TP1": f"{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A",
                "Chandelier Stop": f"{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A",
                "Position Size": r["position_size"],
                "Status": r["status"],
                "Gate Reasons": ",".join(r.get("gate_reasons", [])),
            })

    console.print(f"[dim]CSV saved to {filepath}[/dim]")
