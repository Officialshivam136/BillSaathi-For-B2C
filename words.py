"""Amount in words, Indian system (thousand, lakh, crore)."""
from decimal import Decimal, ROUND_HALF_UP

_ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen Sixteen Seventeen "
         "Eighteen Nineteen").split()
_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _below_100(n):
    return _ONES[n] if n < 20 else _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")


def _below_1000(n):
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(_ONES[hundreds] + " Hundred")
    if rest:
        parts.append(_below_100(rest))
    return " ".join(parts)


def number_words(n):
    """Whole number >= 0 in Indian grouping."""
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1000, "Thousand")):
        q, n = divmod(n, size)
        if q:
            parts.append(number_words(q) + " " + name)
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def rupees_in_words(amount):
    """Decimal(1417.50) -> 'Rupees One Thousand Four Hundred Seventeen and Fifty Paise Only'."""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees, paise = divmod(int(amount * 100), 100)
    out = "Rupees " + number_words(rupees)
    if paise:
        out += " and " + number_words(paise) + " Paise"
    return out + " Only"
