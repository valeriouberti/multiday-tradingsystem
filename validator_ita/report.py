import csv
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def _check_cell(check: dict) -> Text:
    if check["passed"]:
        icon, style = "\u2705", "green"
    else:
        icon, style = "\u274c", "red"
    display = check.get("display", "")
    text = f"{icon} {display}" if display else icon
    return Text(text, style=style)


def _status_text(result: dict) -> Text:
    status = result["status"]
    gate_reasons = result.get("gate_reasons", [])
    if status == "GO":
        return Text("\u2705 GO", style="bold green")
    elif status == "WATCH":
        label = "WATCH"
        if gate_reasons:
            label += f" ({','.join(gate_reasons)})"
        return Text(f"\u26a0\ufe0f  {label}", style="bold yellow")
    else:
        return Text("\u274c SKIP", style="bold red")


def print_report(results: list[dict], config: dict) -> None:
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    console.print()
    console.print(
        f"\U0001f1ee\U0001f1f9 Italian Stock CFD Validator v1.0 \u2014 {now.strftime('%Y-%m-%d %H:%M %Z')}",
        style="bold",
    )

    # --- Gates banner ---
    if results:
        gates = results[0].get("gates", {})
        benchmark = config.get("benchmark", "ETFMIB.MI")

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
    leverage = ps.get("leverage", 5)
    max_cap_pct = ps.get("max_capital_pct", 0.40)
    console.print(
        f"[dim]Capital: \u20ac{capital:,.0f} | Risk/trade: {risk_pct*100:.1f}% "
        f"(\u20ac{capital*risk_pct:,.0f}) | Leverage: {leverage}:1 | "
        f"Max/position: {max_cap_pct*100:.0f}% margin "
        f"(\u20ac{capital*max_cap_pct*leverage:,.0f} notional)[/dim]"
    )
    console.print()

    # --- Main table ---
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Stock", style="bold", no_wrap=True)
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

    # --- Fineco CFD action plan ---
    actionable = [r for r in results if r["status"] in ("GO", "WATCH") and r["entry_method"] != "WAIT"]
    if actionable:
        console.print("[bold]FINECO CFD — Ordini da impostare:[/bold]")
        console.print()
        for r in actionable:
            entry = r["entry_method"]
            style = "bold green" if r["status"] == "GO" else "bold yellow"
            console.print(f"[{style}]{r['ticker']} \u2014 {entry}[/{style}]")

            close_price = r.get("last_close", 0)
            if close_price > 0:
                console.print(f"  Prezzo attuale:  \u20ac{close_price:.2f}")

            notional = r["position_size"] * close_price
            leverage = config.get("position_sizing", {}).get("leverage", 5)
            margin = notional / leverage if leverage > 0 else notional
            console.print(f"  Stop Loss:       \u20ac{r['stop_loss']:.2f}  (inserire subito)")
            console.print(f"  TP1 (50%):       \u20ac{r['tp1_price']:.2f}  (ordine limite)")
            console.print(f"  Trailing Stop:   \u20ac{r['chandelier_stop']:.2f}  (aggiornare ogni sera)")
            console.print(f"  Size:            {r['position_size']} shares (\u20ac{notional:,.0f} notional, \u20ac{margin:,.0f} margin)")

            if entry == "GAP_UP":
                console.print("  [dim]Finestra: 09:00-09:15 CET \u2014 entry a mercato su apertura[/dim]")
            elif entry == "ORB":
                console.print("  [dim]Finestra: 09:15+ CET \u2014 entry dopo breakout Opening Range[/dim]")
            elif entry == "PULLBACK":
                console.print("  [dim]Finestra: 09:15+ CET \u2014 entry su rimbalzo EMA20[/dim]")
            elif entry == "BONE_ZONE":
                console.print("  [dim]Finestra: 09:15+ CET \u2014 entry su recovery da zona EMA 9-20[/dim]")
            console.print()

    no_entry = [r for r in results if r["status"] in ("GO", "WATCH") and r["entry_method"] == "WAIT"]
    if no_entry:
        tickers_wait = ", ".join(r["ticker"] for r in no_entry)
        console.print(f"[dim]{tickers_wait}: nessun setup entry \u2014 monitorare su Fineco[/dim]")
        console.print()

    if not actionable and not no_entry:
        console.print("[dim]Nessun titolo italiano operabile oggi.[/dim]")
        console.print()


def save_csv(results: list[dict], config: dict) -> None:
    if not config["output"].get("save_csv", True):
        return

    csv_dir = config["output"].get("csv_dir", "output/reports_ita")
    os.makedirs(csv_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d") + ".csv"
    filepath = os.path.join(csv_dir, filename)

    fieldnames = [
        "Stock", "Score", "EMA D", "EMA W", "MACD", "RSI", "MFI",
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
                "Stock": r["ticker"],
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
