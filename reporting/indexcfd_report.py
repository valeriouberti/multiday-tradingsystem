import csv
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from reporting.report_utils import check_cell as _check_cell
from reporting.report_utils import status_text as _status_text

console = Console()

# CFD entry windows (CET/CEST) — enter during the underlying cash session.
# US index CFDs are live from ~08:00 CET on most brokers, but the daily signal
# is based on the US cash close (22:00 CET). Entering before US cash open risks
# an intraday reversal at 15:30 when the real volume arrives.
# Rule: enter each index during its OWN cash session open.
_SESSION_WINDOWS = {
    "SPY": "15:45-16:15 CET (dopo apertura cash US)",
    "QQQ": "15:45-16:15 CET (dopo apertura cash US)",
    "DIA": "15:45-16:15 CET (dopo apertura cash US)",
    "IWM": "15:45-16:15 CET (dopo apertura cash US)",
    "FEZ": "09:00-09:45 CET (EU cash open)",
    "EWG": "09:00-09:45 CET (EU cash open)",
    "EWU": "09:00-09:45 CET (EU/UK cash open)",
    "EWJ": "09:00-09:45 CET (CFD attivo, JP gia chiuso)",
}


def print_report(results: list[dict], config: dict) -> None:
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    console.print()
    console.print(
        f"\U0001f4c8 Index CFD Validator v1.0 \u2014 {now.strftime('%Y-%m-%d %H:%M %Z')}",
        style="bold",
    )

    # --- Gates banner ---
    if results:
        gates = results[0].get("gates", {})
        benchmark = config.get("benchmark", "SPY")

        vix_ok = gates.get("vix_ok", True)
        vix_val = gates.get("vix_value", 0)
        if vix_ok:
            console.print(f"[green]VIX: {vix_val} \u2705 Low volatility[/green]")
        else:
            console.print(
                f"[bold red]VIX: {vix_val} \u274c High volatility "
                "\u2014 GO signals downgraded[/bold red]"
            )

        adx_ok = gates.get("adx_ok", True)
        adx_val = gates.get("adx_value", 0)
        if adx_ok:
            console.print(f"[green]ADX ({benchmark}): {adx_val} \u2705 Trending market[/green]")
        else:
            console.print(
                f"[bold red]ADX ({benchmark}): {adx_val} \u274c Range-bound "
                "\u2014 momentum signals unreliable[/bold red]"
            )

    console.print()

    # --- Position sizing info ---
    ps = config.get("position_sizing", {})
    capital = ps.get("capital", 1000)
    risk_pct = ps.get("risk_per_trade", 0.02)
    leverage = ps.get("leverage", 20)
    max_cap_pct = ps.get("max_capital_pct", 0.40)
    console.print(
        f"[dim]Capital: ${capital:,.0f} | Risk/trade: {risk_pct*100:.1f}% "
        f"(${capital*risk_pct:,.0f}) | Leverage: {leverage}:1 | "
        f"Max/position: {max_cap_pct*100:.0f}% margin "
        f"(${capital*max_cap_pct*leverage:,.0f} notional)[/dim]"
    )
    console.print()

    # --- Sort results: GO first, then WATCH, then SKIP (by score desc) ---
    status_order = {"GO": 0, "WATCH": 1, "SKIP": 2}
    results = sorted(
        results,
        key=lambda r: (status_order.get(r["status"], 9), -r["score"]),
    )

    # --- Main table ---
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Index", style="bold", no_wrap=True)
    table.add_column("Proxy", no_wrap=True)
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
    table.add_column("Entry", justify="center", no_wrap=True)
    table.add_column("GO?", justify="center", no_wrap=True)

    for r in results:
        checks = r["checks"]
        pm = f"{r['premarket_pct']:+.2f}%"
        pm_text = Text(pm, style="green" if r["premarket_pct"] >= 0 else "red")
        stop_str = f"${r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A"
        tp1_str = f"${r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A"
        chand_str = f"${r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A"
        size_str = str(r["position_size"]) if r["position_size"] > 0 else "N/A"

        table.add_row(
            r.get("index_label", r["ticker"]),
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
            r["entry_method"],
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

    # --- CFD action plan ---
    actionable = [r for r in results if r["status"] in ("GO", "WATCH") and r["entry_method"] != "WAIT"]
    if actionable:
        console.print("[bold]Index CFD \u2014 Ordini da impostare:[/bold]")
        console.print()
        for r in actionable:
            entry = r["entry_method"]
            label = r.get("index_label", r["ticker"])
            style = "bold green" if r["status"] == "GO" else "bold yellow"
            console.print(f"[{style}]{label} ({r['ticker']}) \u2014 {entry}[/{style}]")

            close_price = r.get("last_close", 0)
            if close_price > 0:
                console.print(f"  Proxy price:     ${close_price:.2f}")

            notional = r["position_size"] * close_price
            margin = notional / leverage if leverage > 0 else notional
            console.print(f"  Stop Loss:       ${r['stop_loss']:.2f}  (inserire subito)")
            console.print(f"  TP1 (50%):       ${r['tp1_price']:.2f}  (ordine limite)")
            console.print(f"  Trailing Stop:   ${r['chandelier_stop']:.2f}  (aggiornare ogni sera)")
            console.print(f"  Size:            {r['position_size']} units (${notional:,.0f} notional, ${margin:,.0f} margin)")

            session = _SESSION_WINDOWS.get(r["ticker"], "check broker")
            if entry == "GAP_UP":
                console.print(f"  [dim]Finestra: {session} \u2014 entry a mercato su apertura[/dim]")
            elif entry == "ORB":
                console.print(f"  [dim]Finestra: {session} \u2014 entry dopo breakout Opening Range[/dim]")
            elif entry == "PULLBACK":
                console.print(f"  [dim]Finestra: {session} \u2014 entry su rimbalzo EMA20[/dim]")
            elif entry == "BONE_ZONE":
                console.print(f"  [dim]Finestra: {session} \u2014 entry su recovery da zona EMA 9-20[/dim]")
            console.print()

    no_entry = [r for r in results if r["status"] in ("GO", "WATCH") and r["entry_method"] == "WAIT"]
    if no_entry:
        labels_wait = ", ".join(
            f"{r.get('index_label', r['ticker'])}" for r in no_entry
        )
        console.print(f"[dim]{labels_wait}: nessun setup entry \u2014 monitorare su broker[/dim]")
        console.print()

    if not actionable and not no_entry:
        console.print("[dim]Nessun indice operabile oggi.[/dim]")
        console.print()


def save_csv(results: list[dict], config: dict) -> None:
    if not config["output"].get("save_csv", True):
        return

    csv_dir = config["output"].get("csv_dir", "output/reports_indexcfd")
    os.makedirs(csv_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d") + ".csv"
    filepath = os.path.join(csv_dir, filename)

    fieldnames = [
        "Index", "Proxy", "Score", "EMA D", "EMA W", "MACD", "RSI", "MFI",
        "RS", "VIX Gate", "ADX Gate",
        "Premarket %", "Stop Loss", "TP1", "Chandelier Stop", "Position Size",
        "Entry Method", "Status", "Gate Reasons",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            checks = r["checks"]
            gates = r.get("gates", {})
            writer.writerow({
                "Index": r.get("index_label", r["ticker"]),
                "Proxy": r["ticker"],
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
                "ADX Gate": "OK" if gates.get("adx_ok", True) else "RANGE",
                "Premarket %": f"{r['premarket_pct']:+.2f}%",
                "Stop Loss": f"{r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A",
                "TP1": f"{r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A",
                "Chandelier Stop": f"{r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A",
                "Position Size": r["position_size"],
                "Entry Method": r["entry_method"],
                "Status": r["status"],
                "Gate Reasons": ",".join(r.get("gate_reasons", [])),
            })

    console.print(f"[dim]CSV saved to {filepath}[/dim]")
