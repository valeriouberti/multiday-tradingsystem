import csv
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.text import Text

from shared.report_utils import check_cell as _check_cell
from shared.report_utils import status_text as _status_text

console = Console()


def print_report(results: list[dict], config: dict) -> None:
    tz = config["session"]["timezone"]
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo(tz))
    except Exception:
        now = datetime.now()

    console.print()
    console.print(
        f"\U0001f1fa\U0001f1f8 US S&P 500 CFD Validator v1.0 \u2014 {now.strftime('%Y-%m-%d %H:%M %Z')}",
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
    leverage = ps.get("leverage", 5)
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
    table.add_column("#", justify="center", no_wrap=True)
    table.add_column("Stock", style="bold", no_wrap=True)
    table.add_column("Score", justify="center", no_wrap=True)
    table.add_column("EMA D", justify="center", no_wrap=True)
    table.add_column("EMA W", justify="center", no_wrap=True)
    table.add_column("MACD", justify="center", no_wrap=True)
    table.add_column("RSI", justify="center", no_wrap=True)
    table.add_column("MFI", justify="center", no_wrap=True)
    table.add_column("RS", justify="center", no_wrap=True)
    table.add_column("RS%", justify="right", no_wrap=True)
    table.add_column("Premkt", justify="right", no_wrap=True)
    table.add_column("Stop", justify="right", no_wrap=True)
    table.add_column("TP1", justify="right", no_wrap=True)
    table.add_column("Trail", justify="right", no_wrap=True)
    table.add_column("Size", justify="right", no_wrap=True)
    table.add_column("Entry", justify="center", no_wrap=True)
    table.add_column("GO?", justify="center", no_wrap=True)

    for r in results:
        rank = r.get("rank", 0)
        checks = r["checks"]
        pm = f"{r['premarket_pct']:+.2f}%"
        pm_text = Text(pm, style="green" if r["premarket_pct"] >= 0 else "red")
        stop_str = f"${r['stop_loss']:.2f}" if r["stop_loss"] > 0 else "N/A"
        tp1_str = f"${r['tp1_price']:.2f}" if r["tp1_price"] > 0 else "N/A"
        chand_str = f"${r['chandelier_stop']:.2f}" if r["chandelier_stop"] > 0 else "N/A"
        size_str = str(r["position_size"]) if r["position_size"] > 0 else "N/A"
        rs_pct = f"{r.get('rs_value', 0):+.1f}%" if r.get("rs_value") else ""
        rank_str = Text(str(rank), style="bold green") if rank else Text("")

        row_style = "on grey15" if rank else None
        table.add_row(
            rank_str,
            r["ticker"],
            f"{r['score']}/{r['max_score']}",
            _check_cell(checks["EMA D"]),
            _check_cell(checks["EMA W"]),
            _check_cell(checks["MACD"]),
            _check_cell(checks["RSI"]),
            _check_cell(checks["MFI"]),
            _check_cell(checks["RS"]),
            rs_pct,
            pm_text,
            stop_str,
            tp1_str,
            chand_str,
            size_str,
            r["entry_method"],
            _status_text(r),
            style=row_style,
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

    # --- Action plan (top-N only) ---
    top_n = config["alerts"].get("top_n", 5)
    actionable = [r for r in results if r.get("rank", 0) > 0 and r["entry_method"] != "WAIT"]
    if actionable:
        console.print(f"[bold]CFD \u2014 Top {top_n} Orders to place:[/bold]")
        console.print()
        for r in actionable:
            entry = r["entry_method"]
            style = "bold green" if r["status"] == "GO" else "bold yellow"
            console.print(f"[{style}]{r['ticker']} \u2014 {entry}[/{style}]")

            close_price = r.get("last_close", 0)
            if close_price > 0:
                console.print(f"  Price:          ${close_price:.2f}")

            notional = r["position_size"] * close_price
            leverage = config.get("position_sizing", {}).get("leverage", 5)
            margin = notional / leverage if leverage > 0 else notional
            console.print(f"  Stop Loss:      ${r['stop_loss']:.2f}")
            console.print(f"  TP1 (50%):      ${r['tp1_price']:.2f}")
            console.print(f"  Trailing Stop:  ${r['chandelier_stop']:.2f}")
            console.print(f"  Size:           {r['position_size']} shares (${notional:,.0f} notional, ${margin:,.0f} margin)")

            if entry == "GAP_UP":
                console.print("  [dim]Window: 09:30-09:45 ET \u2014 market entry on open[/dim]")
            elif entry == "ORB":
                console.print("  [dim]Window: 09:45+ ET \u2014 entry after Opening Range breakout[/dim]")
            elif entry == "PULLBACK":
                console.print("  [dim]Window: 09:45+ ET \u2014 entry on EMA20 bounce[/dim]")
            elif entry == "BONE_ZONE":
                console.print("  [dim]Window: 09:45+ ET \u2014 entry on recovery from EMA 9-20 zone[/dim]")
            console.print()

    no_entry = [r for r in results if r.get("rank", 0) > 0 and r["entry_method"] == "WAIT"]
    if no_entry:
        tickers_wait = ", ".join(r["ticker"] for r in no_entry)
        console.print(f"[dim]{tickers_wait}: ranked but no entry setup \u2014 monitor on broker[/dim]")
        console.print()

    if not actionable and not no_entry:
        console.print("[dim]No US stocks actionable today.[/dim]")
        console.print()

    # Show remaining GO/WATCH outside top-N as a compact list
    remaining = [r for r in results if r["status"] in ("GO", "WATCH") and r.get("rank", 0) == 0]
    if remaining:
        tickers_remaining = ", ".join(f"{r['ticker']}({r['score']})" for r in remaining)
        console.print(f"[dim]Also GO/WATCH (not in top {top_n}): {tickers_remaining}[/dim]")
        console.print()


def print_news_risk(news_risk: dict) -> None:
    """Print Perplexity news risk analysis below the action plan."""
    console.print("[bold cyan]NEWS RISK CHECK (Perplexity Sonar)[/bold cyan]")
    console.print()

    # Raw text fallback
    if "_raw" in news_risk:
        for line in news_risk["_raw"].strip().splitlines():
            console.print(f"  {line.strip()}")
        console.print()
        return

    # Macro context
    macro = news_risk.get("macro", "")
    if macro:
        console.print(f"  [dim]Macro: {macro}[/dim]")
        console.print()

    # Per-ticker results
    tickers = news_risk.get("tickers", [])
    for t in tickers:
        ticker = t.get("ticker", "???")
        verdict = t.get("verdict", "???").upper()
        reason = t.get("reason", "")

        if verdict == "SKIP":
            style = "bold red"
            icon = "\u274c"
        elif verdict == "WAIT":
            style = "bold yellow"
            icon = "\u26a0\ufe0f"
        else:
            style = "bold green"
            icon = "\u2705"

        console.print(f"  [{style}]{icon} {ticker} \u2014 {verdict}[/{style}]  {reason}")

        # Detail lines
        details = []
        earn = t.get("earnings", {})
        if earn.get("flag"):
            details.append(f"[red]Earnings: {earn.get('detail', 'YES')}[/red]")
        exdiv = t.get("ex_dividend", {})
        if exdiv.get("flag"):
            details.append(f"[yellow]Ex-div: {exdiv.get('detail', 'YES')}[/yellow]")
        cat = t.get("catalyst", {})
        cat_level = cat.get("level", "").upper()
        if cat_level and cat_level != "NONE":
            cat_style = "green" if cat_level == "ACTIVE" else "yellow"
            details.append(f"[{cat_style}]Catalyst: {cat.get('detail', cat_level)}[/{cat_style}]")
        event = t.get("event", {})
        if event.get("flag"):
            details.append(f"[red]Event: {event.get('detail', 'YES')}[/red]")
        sector = t.get("sector_risk", "")
        if sector:
            details.append(f"[dim]Sector: {sector}[/dim]")

        if details:
            console.print(f"    {' | '.join(details)}")

    # Citations
    citations = news_risk.get("_citations", [])
    if citations:
        console.print()
        console.print(f"  [dim]Sources: {len(citations)} articles consulted[/dim]")

    console.print()


def save_csv(results: list[dict], config: dict) -> None:
    if not config["output"].get("save_csv", True):
        return

    csv_dir = config["output"].get("csv_dir", "output/reports_us")
    os.makedirs(csv_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d") + ".csv"
    filepath = os.path.join(csv_dir, filename)

    fieldnames = [
        "Rank", "Stock", "Score", "EMA D", "EMA W", "MACD", "RSI", "MFI",
        "RS", "RS ROC %", "RSI Value", "MFI Value", "VIX Gate", "ADX Gate",
        "Premarket %", "Stop Loss", "TP1", "Chandelier Stop", "Position Size",
        "Entry Method", "Status", "Gate Reasons",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            checks = r["checks"]
            gates = r.get("gates", {})
            rank = r.get("rank", 0)
            writer.writerow({
                "Rank": rank if rank > 0 else "",
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
                "RS ROC %": f"{r.get('rs_value', 0):+.2f}",
                "RSI Value": r.get("rsi_value", ""),
                "MFI Value": r.get("mfi_value", ""),
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
