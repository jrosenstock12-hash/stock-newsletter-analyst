import re

TICKER_PATTERN = re.compile(
    r"""
    (?:
        \$(?P<dollar>[A-Z]{1,5})\b
      | \((?:NYSE|NASDAQ|AMEX|OTC):\s*(?P<exchange>[A-Z]{1,5})\)
      | \b(?P<plain>[A-Z]{2,5})\s+(?:stock|shares|equity)\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

COMMON_WORDS = {
    "A", "I", "AI", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "PM", "SO", "TO",
    "UP", "US", "WE", "CEO", "CFO", "COO", "CTO", "EPS", "ETF", "FAQ", "GDP",
    "IPO", "LLC", "LTD", "NYSE", "OTC", "PDF", "PMI", "SEC", "USA", "VIP",
    "YOY", "QOQ", "MOM", "YTD", "ATH", "ATL", "RSI", "MACD", "PE", "EV",
    "API", "URL", "HTML", "HTTP", "USAGE", "THE", "AND", "FOR", "ARE", "BUT", "NOT",
    "YOU", "ALL", "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET",
    "HAS", "HIM", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW", "OLD", "SEE",
    "TWO", "WAY", "WHO", "BOY", "DID", "LET", "PUT", "SAY", "SHE", "TOO",
    "USE", "DOW", "FED", "GDP",
}


def detect_tickers(text: str) -> list[str]:
    found: set[str] = set()
    for match in TICKER_PATTERN.finditer(text):
        ticker = (
            match.group("dollar")
            or match.group("exchange")
            or match.group("plain")
        )
        if ticker and ticker.upper() not in COMMON_WORDS:
            found.add(ticker.upper())
    return sorted(found)
