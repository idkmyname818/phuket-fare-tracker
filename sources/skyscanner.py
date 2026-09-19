from playwright.sync_api import sync_playwright
import re


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
        r"US\$\s?([\d,]+(?:\.\d{1,2})?)",
        r"USD\s?([\d,]+(?:\.\d{1,2})?)",
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
        r"(\d+)\s*hr\s*(\d+)?\s*min",
        r"(\d+)\s*h\s*(\d+)?\s*m",
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
    match = re.search(r"(\d+)\s+stop", text, re.IGNORECASE)

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
        "https://www.skyscanner.net/transport/flights/"
        f"{origin.lower()}/{destination.lower()}/"
        f"{date_value.replace('-', '')}/"
        f"?adultsv2={passengers}&currency=USD"
    )

    results = []

    print("\n=== SKYSCANNER ===")
    print("URL:", url)

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

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

            print("\n--- BODY PREVIEW ---")
            print(text[:6000])

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
                        max(0, i - 15):
                        min(len(lines), i + 25)
                    ]
                )

                duration = parse_duration(context)

                stops = parse_stops(context)

                airline = parse_airline(context)

                baggage = "VERIFY"

                if re.search(
                    r"20\s*kg|20kg|checked baggage|hold baggage",
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

                result = {
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

                results.append(result)

            print("\nPrices detected:", len(results))

        except Exception as exc:

            print(
                "Skyscanner scraper error:",
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
            result["airline"],
            result["stops"],
            result["duration_minutes"],
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(result)

    print("Skyscanner parsed offers:", len(unique))

    for offer in unique[:20]:

        print(
            "OFFER:",
            offer["date"],
            "|",
            offer["price"],
            offer["currency"],
            "|",
            offer["airline"],
            "|",
            offer["stops"],
            "stops",
            "|",
            offer["duration_minutes"],
            "min",
            "| baggage:",
            offer["baggage"],
        )

    return unique
