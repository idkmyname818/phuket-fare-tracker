from playwright.sync_api import sync_playwright
from urllib.parse import quote
import re
import time


def search(origin, destination, travel_date, passengers=2):
    """
    Best-effort Google Flights scraper.

    Returns a list of dictionaries compatible with tracker.py.
    """

    date_value = str(travel_date)

    url = (
        "https://www.google.com/travel/flights"
        f"?q=Flights%20from%20{quote(origin)}"
        f"%20to%20{quote(destination)}"
        f"%20on%20{date_value}"
    )

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="en-US",
        )

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            # Scroll a little so flight cards load.
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(2000)

            body_text = page.locator(
                "body"
            ).inner_text()

            lines = [
                line.strip()
                for line in body_text.splitlines()
                if line.strip()
            ]

            for i, line in enumerate(lines):
                price_match = re.search(
                    r"\$\s?([\d,]+(?:\.\d{1,2})?)",
                    line,
                )

                if not price_match:
                    continue

                price = float(
                    price_match.group(1)
                    .replace(",", "")
                )

                # Look around the price for useful information.
                context = " ".join(
                    lines[
                        max(0, i - 8):
                        min(len(lines), i + 12)
                    ]
                )

                # Stops.
                stops = 0

                stop_match = re.search(
                    r"(\d+)\s+stop",
                    context,
                    re.IGNORECASE,
                )

                if stop_match:
                    stops = int(
                        stop_match.group(1)
                    )
                elif re.search(
                    r"nonstop|direct",
                    context,
                    re.IGNORECASE,
                ):
                    stops = 0

                # Duration.
                duration_minutes = 9999

                duration_match = re.search(
                    r"(\d+)\s*hr\s*(\d+)?\s*min",
                    context,
                    re.IGNORECASE,
                )

                if duration_match:
                    hours = int(
                        duration_match.group(1)
                    )

                    minutes = int(
                        duration_match.group(2)
                        or 0
                    )

                    duration_minutes = (
                        hours * 60
                        + minutes
                    )

                else:
                    short_duration = re.search(
                        r"(\d+)h\s*(\d+)?m?",
                        context,
                        re.IGNORECASE,
                    )

                    if short_duration:
                        hours = int(
                            short_duration.group(1)
                        )

                        minutes = int(
                            short_duration.group(2)
                            or 0
                        )

                        duration_minutes = (
                            hours * 60
                            + minutes
                        )

                # Airline.
                airline = "Unknown"

                airline_patterns = [
                    "AirAsia",
                    "Thai AirAsia",
                    "VietJet Air",
                    "Vietnam Airlines",
                    "Thai VietJet",
                    "Thai Airways",
                    "Scoot",
                    "Malaysia Airlines",
                    "Singapore Airlines",
                    "Batik Air",
                    "Thai Lion Air",
                    "Bangkok Airways",
                    "Hong Kong Airlines",
                    "China Southern",
                    "China Eastern",
                    "Spring Airlines",
                ]

                for name in airline_patterns:
                    if name.lower() in context.lower():
                        airline = name
                        break

                # Baggage is intentionally conservative.
                baggage = "VERIFY"

                if re.search(
                    r"20\s*kg.*bag|bag.*20\s*kg|20kg",
                    context,
                    re.IGNORECASE,
                ):
                    baggage = "INCLUDED"

                self_transfer = bool(
                    re.search(
                        r"self.?transfer|separate tickets",
                        context,
                        re.IGNORECASE,
                    )
                )

                results.append(
                    {
                        "date": date_value,
                        "price": price,
                        "currency": "USD",
                        "airline": airline,
                        "stops": stops,
                        "duration_minutes": duration_minutes,
                        "baggage": baggage,
                        "self_transfer": self_transfer,
                        "url": page.url,
                        "route": (
                            f"{origin} → {destination}"
                        ),
                    }
                )

        except Exception as exc:
            print(
                "Google Flights scraper error:",
                exc,
            )

        finally:
            browser.close()

    # Remove obvious duplicates.
    unique = []
    seen = set()

    for result in results:
        key = (
            result["date"],
            result["price"],
            result["airline"],
            result["stops"],
            result["duration_minutes"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(result)

    return unique
