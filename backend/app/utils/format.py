from __future__ import annotations

from fractions import Fraction


def format_shutter(seconds: float | None) -> str | None:
    if not seconds:
        return None
    if seconds >= 0.3:
        return f'{seconds:g}"' if seconds >= 1 else f"{seconds:.1f}s"
    return f"1/{round(1 / seconds)}"


def format_ev(ev: float | None) -> str | None:
    """0.3333 -> '+1/3 EV', -1.0 -> '-1 EV', 0 -> '0 EV'."""
    if ev is None:
        return None
    if abs(ev) < 0.01:
        return "0 EV"
    frac = Fraction(ev).limit_denominator(3)
    sign = "+" if ev > 0 else "-"
    frac = abs(frac)
    whole, rem = divmod(frac.numerator, frac.denominator)
    if rem == 0:
        return f"{sign}{whole} EV"
    if whole:
        return f"{sign}{whole} {rem}/{frac.denominator} EV"
    return f"{sign}{rem}/{frac.denominator} EV"


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"
