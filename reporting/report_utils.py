from rich.text import Text


def check_cell(check: dict) -> Text:
    """Format a check result as a Rich Text cell with checkmark/X."""
    if check["passed"]:
        icon, style = "\u2705", "green"
    else:
        icon, style = "\u274c", "red"
    display = check.get("display", "")
    text = f"{icon} {display}" if display else icon
    return Text(text, style=style)


def status_text(result: dict) -> Text:
    """Format GO/WATCH/SKIP status as Rich Text."""
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
