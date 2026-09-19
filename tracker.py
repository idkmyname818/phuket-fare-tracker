import os
import json
import hashlib
from datetime import datetime, date, timedelta

import requests
from dotenv import load_dotenv

from sources.google_flights import search as google_search
from sources.skyscanner import search as skyscanner_search
from sources.kiwi import search as kiwi_search
from sources.trip import search as trip_search


load_dotenv()

ORIGIN = "CXR"
DESTINATION = "HKT"

START_DATE = date(2026, 12, 21)
END_DATE = date(2026, 12, 31)

PASSENGERS = 2
MAX_STOPS = 2
MAX_DURATION_MINUTES = 600
MAX_PRICE_PER_PERSON = 110
BAGGAGE_KG = 20

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HISTORY_FILE = "data/history.json"
SEEN_FILE = "data/seen.json"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def date_range(start, end):
    current = start

    while current <= end:
        yield current
        current += timedelta(days=1)


def normalize_offer(offer, source):
    """
    Expected offer structure:

    {
        "date": "2026-12-15",
        "price": 89.50,
        "currency": "USD",
        "airline": "AirAsia",
        "stops": 1,
        "duration_minutes": 420,
        "baggage": "INCLUDED",
        "self_transfer": False,
        "url": "https://..."
    }
    """

    if not isinstance(offer, dict):
        return None

    try:
        price = float(offer.get("price", 0))
    except (TypeError, ValueError):
        return None

    try:
        stops = int(offer.get("stops", 99))
    except (TypeError, ValueError):
        stops = 99

    try:
        duration = int(offer.get("duration_minutes", 99999))
    except (TypeError, ValueError):
        duration = 99999

    return {
        "source": source,
        "date": str(offer.get("date", "")),
        "price": price,
        "currency": offer.get("currency", "USD"),
        "airline": offer.get("airline", "Unknown"),
        "stops": stops,
        "duration_minutes": duration,
        "baggage": offer.get("baggage", "VERIFY"),
        "self_transfer": bool(offer.get("self_transfer", False)),
        "url": offer.get("url", ""),
        "route": offer.get("route", ""),
    }


def is_valid_offer(offer):
    if not offer:
        return False

    if offer["currency"] != "USD":
        return False

    if offer["price"] <= 0:
        return False

    price_per_person = offer["price"] / PASSENGERS

    if price_per_person > MAX_PRICE_PER_PERSON:
        return False

    if offer["stops"] > MAX_STOPS:
        return False

    if offer["duration_minutes"] > MAX_DURATION_MINUTES:
        return False

    return True


def offer_key(offer):
    raw = "|".join(
        [
            offer["date"],
            offer["airline"],
            str(offer["stops"]),
            str(offer["duration_minutes"]),
            f'{offer["price"]:.2f}',
            str(offer["self_transfer"]),
        ]
    )

    return hashlib.sha256(raw.encode()).hexdigest()


def deal_level(price_per_person):
    if price_per_person <= 80:
        return "🔥 SUPER DEAL"

    if price_per_person <= 100:
        return "🎯 TARGET"

    return ""


def format_duration(minutes):
    hours = minutes // 60
    mins = minutes % 60

    if mins:
        return f"{hours}h {mins}m"

    return f"{hours}h"


def format_offer(offer):
    total_price = offer["price"]
    price_per_person = total_price / PASSENGERS

    level = deal_level(price_per_person)

    baggage = offer["baggage"]

    if baggage not in ("INCLUDED", "EXTRA", "VERIFY"):
        baggage = "VERIFY"

    transfer = "SELF-TRANSFER ⚠️" if offer["self_transfer"] else "Standard connection"

    lines = [
        f"{level}",
        "",
        f"📅 Date: {offer['date']}",
        f"✈️ Airline: {offer['airline']}",
        f"🛫 CXR → HKT",
        f"🔄 Stops: {offer['stops']}",
        f"⏱ Duration: {format_duration(offer['duration_minutes'])}",
        "",
        f"💰 Total for 2: ${total_price:.2f}",
        f"👤 Per person: ${price_per_person:.2f}",
        f"🧳 20kg baggage: {baggage}",
        f"🔀 Connection: {transfer}",
        f"🔎 Source: {offer['source']}",
    ]

    if offer.get("route"):
        lines.append(f"🗺 Route: {offer['route']}")

    if offer.get("url"):
        lines.extend(
            [
                "",
                f"🔗 Book/check: {offer['url']}",
            ]
        )

    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials are missing.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            print("Telegram error:", data)
            return False

        return True

    except requests.RequestException as exc:
        print("Telegram request failed:", exc)
        return False


def collect_source(source_name, search_function, travel_date):
    print(
        f"[{source_name}] Searching "
        f"{ORIGIN} -> {DESTINATION} "
        f"on {travel_date}"
    )

    try:
        results = search_function(
            origin=ORIGIN,
            destination=DESTINATION,
            travel_date=travel_date,
            passengers=PASSENGERS,
        )

        if not results:
            return []

        normalized = []

        for result in results:
            offer = normalize_offer(result, source_name)

            if offer and is_valid_offer(offer):
                normalized.append(offer)

        print(
            f"[{source_name}] "
            f"valid offers: {len(normalized)}"
        )

        return normalized

    except Exception as exc:
        print(
            f"[{source_name}] ERROR: {type(exc).__name__}: {exc}"
        )
        return []


def search_all_sources(travel_date):
    offers = []

    sources = [
        ("Google Flights", google_search),
        ("Skyscanner", skyscanner_search),
        ("Kiwi", kiwi_search),
        ("Trip.com", trip_search),
    ]

    for source_name, search_function in sources:
        offers.extend(
            collect_source(
                source_name,
                search_function,
                travel_date,
            )
        )

    return offers


def update_history(history, offers):
    timestamp = datetime.utcnow().isoformat()

    for offer in offers:
        key = offer_key(offer)

        if key not in history:
            history[key] = []

        history[key].append(
            {
                "timestamp": timestamp,
                "price": offer["price"],
                "source": offer["source"],
            }
        )

        # Keep only the latest 50 observations.
        history[key] = history[key][-50:]


def build_comparison(offers):
    """
    Group similar offers from different sources.
    This is intentionally simple: date + airline + stops.
    """

    groups = {}

    for offer in offers:
        key = (
            offer["date"],
            offer["airline"],
            offer["stops"],
        )

        groups.setdefault(key, []).append(offer)

    return groups


def comparison_text(offers):
    groups = build_comparison(offers)

    blocks = []

    for key, group in groups.items():
        if len(group) < 2:
            continue

        date_value, airline, stops = key

        lines = [
            "🔎 CROSS-SOURCE COMPARISON",
            "",
            f"📅 {date_value}",
            f"✈️ {airline}",
            f"🔄 {stops} stop(s)",
        ]

        for offer in sorted(group, key=lambda x: x["price"]):
            lines.append(
                f"• {offer['source']}: "
                f"${offer['price']:.2f} total"
            )

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def main():
    print("=" * 60)
    print("PHUKET FARE TRACKER")
    print("=" * 60)

    history = load_json(HISTORY_FILE, {})
    seen = load_json(SEEN_FILE, [])

    all_offers = []

    for travel_date in date_range(
        START_DATE,
        END_DATE,
    ):
        offers = search_all_sources(
            travel_date.isoformat()
        )

        all_offers.extend(offers)

    if not all_offers:
        print("No qualifying offers found.")
        return

    # Sort cheapest first.
    all_offers.sort(
        key=lambda offer: offer["price"]
    )

    print(
        f"Found {len(all_offers)} qualifying offers."
    )

    update_history(
        history,
        all_offers,
    )

    alerts = []

    for offer in all_offers:
        key = offer_key(offer)

        if key in seen:
            continue

        alerts.append(offer)
        seen.append(key)

    # Keep seen database reasonably small.
    seen = seen[-2000:]

    save_json(
        HISTORY_FILE,
        history,
    )

    save_json(
        SEEN_FILE,
        seen,
    )

    if not alerts:
        print("No new deals.")
        return

    # Only send the cheapest 10 new offers
    # during one run to avoid Telegram spam.
    alerts = alerts[:10]

    header = (
        "✈️ PHUKET FARE ALERT\n"
        "CXR → HKT\n"
        "12–18 DEC 2026\n"
        f"{PASSENGERS} passengers\n"
        f"Max 2 stops / max 10h\n"
        "────────────────────"
    )

    for offer in alerts:
        message = (
            header
            + "\n\n"
            + format_offer(offer)
        )

        send_telegram(message)

    comparison = comparison_text(
        all_offers
    )

    if comparison:
        send_telegram(comparison)

    print(
        f"Sent {len(alerts)} new alert(s)."
    )


if __name__ == "__main__":
    main()
