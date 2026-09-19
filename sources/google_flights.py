from playwright.sync_api import sync_playwright
from urllib.parse import quote
import re


def search(origin, destination, travel_date, passengers=2):
    date_value = str(travel_date)

    url = (
        "https://www.google.com/travel/flights"
        f"?q=Flights%20from%20{quote(origin)}"
        f"%20to%20{quote(destination)}"
        f"%20on%20{date_value}"
    )

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        try:
            print(f"[Google Flights] URL: {url}")

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(8000)

            print(
                "[Google Flights] TITLE:",
                page.title(),
            )

            print(
                "[Google Flights] FINAL URL:",
                page.url,
            )

            # Scroll several times to trigger lazy loading.
            for _ in range(4):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1500)

            body_text = page.locator("body").inner_text()

            print(
                "[Google Flights] BODY LENGTH:",
                len(body_text),
            )

            # Print first part of page so we can see
            # what Google actually returns to GitHub.
            print(
                "========== GOOGLE PAGE PREVIEW =========="
            )

            print(body_text[:12000])

            print(
                "========== END GOOGLE PAGE PREVIEW =========="
            )

            lines = [
                line.strip()
                for line in body_text.splitlines()
                if line.strip()
            ]

            for i, line in enumerate(lines):

                price_match = re.search(
                    r"([$€£])\s?([\d,]+(?:\.\d{1,2})?)",
                    line,
                )

                if not price_match:
                    continue

                symbol = price_match.group(1)

                price = float(
                    price_match.group(2).replace(",", "")
                )

                currency_map = {
                    "$": "USD",
                    "€": "EUR",
                    "£": "GBP",
                }

                currency = currency_map.get(
                    symbol,
                    "USD",
                )

                context = " ".join(
                    lines[
                        max(0, i - 10):
                        min(len(lines), i + 15)
                    ]
                )

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

                duration_minutes = 9999

                duration_match = re.search(
                    r"(\d+)\s*(?:hr|h)\s*"
                    r"(\d+)?\s*(?:min|m)?",
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
                        hours * 60 + minutes
                    )

                airline = "Unknown"

                airlines = [
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

                for name in airlines:
                    if name.lower() in context.lower():
                        airline = name
                        break

                baggage = "VERIFY"

                if re.search(
                    r"20\s*kg|20kg",
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
                        "currency": currency,
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
                "[Google Flights] ERROR:",
                repr(exc),
            )

        finally:
            browser.close()

    unique = []
    seen = set()

    for result in results:
        key = (
            result["date"],
            result["price"],
            result["currency"],
            result["airline"],
            result["stops"],
            result["duration_minutes"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(result)

    print(
        "[Google Flights] parsed offers:",
        len(unique),
    )

    return unique
