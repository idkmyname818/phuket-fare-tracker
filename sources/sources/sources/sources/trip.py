from playwright.sync_api import sync_playwright
import re


def search(origin, destination, travel_date, passengers=2):
    date_value = str(travel_date)

    url = (
        "https://www.trip.com/flights/"
        f"{origin.lower()}-to-{destination.lower()}/"
        f"tickets-{origin.lower()}-{destination.lower()}/"
        f"?date={date_value}"
    )

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(8000)

            page.mouse.wheel(0, 3500)
            page.wait_for_timeout(2000)

            text = page.locator("body").inner_text()

            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]

            for i, line in enumerate(lines):
                match = re.search(
                    r"\$\s?([\d,]+(?:\.\d{1,2})?)",
                    line,
                )

                if not match:
                    continue

                price = float(
                    match.group(1).replace(",", "")
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
                    r"(\d+)\s*hr\s*(\d+)?\s*min",
                    context,
                    re.IGNORECASE,
                )

                if duration_match:
                    duration_minutes = (
                        int(duration_match.group(1)) * 60
                        + int(
                            duration_match.group(2)
                            or 0
                        )
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
                "Trip.com scraper error:",
                exc,
            )

        finally:
            browser.close()

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
