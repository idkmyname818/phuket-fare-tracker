from playwright.sync_api import sync_playwright
import re
import json


AIRLINES = [
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


def parse_price(text):
    patterns = [
        r"\$\s?([\d,]+(?:\.\d{1,2})?)",
        r"USD\s?([\d,]+(?:\.\d{1,2})?)",
        r"US\$\s?([\d,]+(?:\.\d{1,2})?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass

    return None


def parse_duration(text):
    patterns = [
        r"(\d+)\s*h\s*(\d+)\s*m",
        r"(\d+)\s*hr\s*(\d+)\s*min",
        r"(\d+)\s*hours?\s*(\d+)?\s*minutes?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2) or 0)
            return hours * 60 + minutes

    return 9999


def parse_stops(text):
    match = re.search(
        r"(\d+)\s+stops?",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    if re.search(r"nonstop|direct", text, re.IGNORECASE):
        return 0

    return 0


def parse_airline(text):
    text_lower = text.lower()

    for airline in AIRLINES:
        if airline.lower() in text_lower:
            return airline

    return "Unknown"


def search(origin, destination, travel_date, passengers=2):

    date_value = str(travel_date)

    url = (
        "https://www.kiwi.com/en/search/results/"
        f"{origin}/{destination}/"
        f"{date_value}/{date_value}"
        f"?adults={passengers}"
    )

    results = []

    print("\n=== KIWI ===")
    print("URL:", url)

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(10000)

            for _ in range(5):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1500)

            print("Final URL:", page.url)
            print("Title:", page.title())

            text = page.locator("body").inner_text()

            print("Body length:", len(text))
            print("Body preview:")
            print(text[:5000])

            # -------------------------------------------------
            # 1. Try visible text
            # -------------------------------------------------

            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]

            for i, line in enumerate(lines):

                price = parse_price(line)

                if price is None:
                    continue

                context = " ".join(
                    lines[
                        max(0, i - 12):
                        min(len(lines), i + 18)
                    ]
                )

                duration = parse_duration(context)
                stops = parse_stops(context)
                airline = parse_airline(context)

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
                        "duration_minutes": duration,
                        "baggage": baggage,
                        "self_transfer": self_transfer,
                        "url": page.url,
                        "route": f"{origin} → {destination}",
                    }
                )

            # -------------------------------------------------
            # 2. Search HTML for prices
            # -------------------------------------------------

            html = page.content()

            html_prices = re.findall(
                r"(?:US\$|\$|USD)\s?[\d,]+(?:\.\d{1,2})?",
                html,
                re.IGNORECASE,
            )

            print(
                "Prices detected in HTML:",
                len(html_prices),
            )

            if html_prices:
                print(
                    "HTML price examples:",
                    html_prices[:20],
                )

            # -------------------------------------------------
            # 3. Search script tags / JSON
            # -------------------------------------------------

            scripts = page.locator("script")

            script_count = scripts.count()

            print(
                "Script tags:",
                script_count,
            )

            for index in range(
                min(script_count, 100)
            ):

                try:
                    script_text = scripts.nth(index).inner_text()

                    if not script_text:
                        continue

                    if not re.search(
                        r"price|amount|currency",
                        script_text,
                        re.IGNORECASE,
                    ):
                        continue

                    prices = re.findall(
                        r"(?:price|amount)[^0-9]{0,30}"
                        r"(\d{2,6}(?:\.\d+)?)",
                        script_text,
                        re.IGNORECASE,
                    )

                    if prices:
                        print(
                            "Script price examples:",
                            prices[:10],
                        )

                except Exception:
                    continue

        except Exception as exc:

            print(
                "Kiwi scraper error:",
                repr(exc),
            )

        finally:
            browser.close()

    # -------------------------------------------------
    # Remove duplicates
    # -------------------------------------------------

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

    print(
        "Kiwi parsed offers:",
        len(unique),
    )

    return unique
