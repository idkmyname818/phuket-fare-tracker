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


# ============================================================
# SEARCH SETTINGS
# ============================================================

ORIGIN = "CXR"
DESTINATION = "HKT"

START_DATE = date(2026, 12, 21)
END_DATE = date(2026, 12, 31)

PASSENGERS = 2

MAX_STOPS = 2
MAX_DURATION_MINUTES = 600

MAX_PRICE_PER_PERSON = 110

BAGGAGE_KG = 20


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# FILES
# ============================================================

HISTORY_FILE = "data/history.json"
SEEN_FILE = "data/seen.json"


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# DATE RANGE
# ============================================================

def date_range(start, end):
    current = start

    while current <= end:
        yield current
        current += timedelta(days=1)


# ============================================================
# NORMALIZE OFFER
# ============================================================

def normalize_offer(offer, source):
    """
    Convert source-specific offer into one standard structure.
    """

    if not isinstance(offer, dict):
        return None

    try:
        price = float(
            offer.get("price", 0)
        )

    except (TypeError, ValueError):
        return None

    try:
        stops = int(
            offer.get("stops", 99)
        )

    except (TypeError, ValueError):
        stops = 99

    try:
        duration = int(
            offer.get(
                "duration_minutes",
                99999,
            )
        )

    except (TypeError, ValueError):
        duration = 99999

    baggage = offer.get(
        "baggage",
        "VERIFY",
    )

    if baggage not in (
        "INCLUDED",
        "EXTRA",
        "VERIFY",
    ):
        baggage = "VERIFY"

    return {
        "source": source,

        "date": str(
            offer.get("date", "")
        ),

        "price": price,

        "currency": offer.get(
            "currency",
            "USD",
        ),

        "airline": offer.get(
            "airline",
            "Unknown",
        ),

        "stops": stops,

        "duration_minutes": duration,

        "baggage": baggage,

        "self_transfer": bool(
            offer.get(
                "self_transfer",
                False,
            )
        ),

        "url": offer.get(
            "url",
            "",
        ),

        "route": offer.get(
            "route",
            f"{ORIGIN} → {DESTINATION}",
        ),
    }


# ============================================================
# VALIDATE OFFER
# ============================================================

def is_valid_offer(offer):
    if not offer:
        return False

    # Currency must be USD.
    if offer["currency"] != "USD":
        return False

    # Price must be positive.
    if offer["price"] <= 0:
        return False

    # Google / sources return total price for all passengers.
    price_per_person = (
        offer["price"] / PASSENGERS
    )

    # Maximum $110 per person.
    if price_per_person > MAX_PRICE_PER_PERSON:
        return False

    # Maximum 2 stops.
    if offer["stops"] > MAX_STOPS:
        return False

    # Maximum 10 hours.
    if (
        offer["duration_minutes"]
        > MAX_DURATION_MINUTES
    ):
        return False

    # IMPORTANT:
    # Only accept flights where the source
    # explicitly detected included baggage.
    if offer["baggage"] != "INCLUDED":
        return False

    return True


# ============================================================
# OFFER KEY
# ============================================================

def offer_key(offer):
    raw = "|".join(
        [
            offer["date"],
            offer["airline"],
            str(offer["stops"]),
            str(
                offer["duration_minutes"]
            ),
            f'{offer["price"]:.2f}',
            offer["baggage"],
            str(
                offer["self_transfer"]
            ),
        ]
    )

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()


# ============================================================
# DEAL LEVEL
# ============================================================

def deal_level(price_per_person):
    if price_per_person <= 80:
        return "🔥 SUPER DEAL"

    if price_per_person <= 110:
        return "🎯 TARGET"

    return ""


# ============================================================
# DURATION
# ============================================================

def format_duration(minutes):
    hours = minutes // 60
    mins = minutes % 60

    if mins:
        return f"{hours}h {mins}m"

    return f"{hours}h"


# ============================================================
# FORMAT TELEGRAM OFFER
# ============================================================

def format_offer(offer):
    total_price = offer["price"]

    price_per_person = (
        total_price / PASSENGERS
    )

    level = deal_level(
        price_per_person
    )

    baggage = offer["baggage"]

    if baggage not in (
        "INCLUDED",
        "EXTRA",
        "VERIFY",
    ):
        baggage = "VERIFY"

    if offer["self_transfer"]:
        transfer = (
            "SELF-TRANSFER ⚠️"
        )
    else:
        transfer = (
            "Standard connection"
        )

    lines = [
        level,
        "",

        f"📅 Date: {offer['date']}",

        f"✈️ Airline: "
        f"{offer['airline']}",

        "🛫 CXR → HKT",

        f"🔄 Stops: "
        f"{offer['stops']}",

        f"⏱ Duration: "
        f"{format_duration(offer['duration_minutes'])}",

        "",

        f"💰 Total for 2: "
        f"${total_price:.2f}",

        f"👤 Per person: "
        f"${price_per_person:.2f}",

        f"🧳 {BAGGAGE_KG}kg baggage: "
        f"{baggage}",

        f"🔀 Connection: "
        f"{transfer}",

        f"🔎 Source: "
        f"{offer['source']}",
    ]

    if offer.get("route"):
        lines.append(
            f"🗺 Route: "
            f"{offer['route']}"
        )

    if offer.get("url"):
        lines.extend(
            [
                "",
                f"🔗 Book/check: "
                f"{offer['url']}",
            ]
        )

    return "\n".join(lines)


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        print(
            "Telegram credentials are missing."
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
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
            print(
                "Telegram error:",
                data,
            )

            return False

        return True

    except requests.RequestException as exc:
        print(
            "Telegram request failed:",
            exc,
        )

        return False


# ============================================================
# SOURCE COLLECTION
# ============================================================

def collect_source(
    source_name,
    search_function,
    travel_date,
):
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
            print(
                f"[{source_name}] "
                "raw offers: 0"
            )

            return []

        print(
            f"[{source_name}] "
            f"raw offers: {len(results)}"
        )

        normalized = []

        for result in results:

            offer = normalize_offer(
                result,
                source_name,
            )

            if not offer:
                continue

            if is_valid_offer(offer):
                normalized.append(
                    offer
                )

        print(
            f"[{source_name}] "
            f"valid offers: "
            f"{len(normalized)}"
        )

        return normalized

    except Exception as exc:
        print(
            f"[{source_name}] ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        return []


# ============================================================
# SEARCH ALL SOURCES
# ============================================================

def search_all_sources(travel_date):

    offers = []

    sources = [
        (
            "Google Flights",
            google_search,
        ),

        (
            "Skyscanner",
            skyscanner_search,
        ),

        (
            "Kiwi",
            kiwi_search,
        ),

        (
            "Trip.com",
            trip_search,
        ),
    ]

    for (
        source_name,
        search_function,
    ) in sources:

        offers.extend(
            collect_source(
                source_name,
                search_function,
                travel_date,
            )
        )

    return offers


# ============================================================
# PRICE HISTORY
# ============================================================

def update_history(
    history,
    offers,
):
    timestamp = (
        datetime.utcnow()
        .isoformat()
    )

    for offer in offers:

        key = offer_key(
            offer
        )

        if key not in history:
            history[key] = []

        history[key].append(
            {
                "timestamp": timestamp,
                "price": offer[
                    "price"
                ],
                "source": offer[
                    "source"
                ],
            }
        )

        # Keep latest 50 observations.
        history[key] = (
            history[key][-50:]
        )


# ============================================================
# CROSS-SOURCE COMPARISON
# ============================================================

def build_comparison(offers):
    """
    Group similar offers:
    date + airline + stops.
    """

    groups = {}

    for offer in offers:

        key = (
            offer["date"],
            offer["airline"],
            offer["stops"],
        )

        groups.setdefault(
            key,
            [],
        ).append(offer)

    return groups


def comparison_text(offers):

    groups = build_comparison(
        offers
    )

    blocks = []

    for key, group in groups.items():

        if len(group) < 2:
            continue

        (
            date_value,
            airline,
            stops,
        ) = key

        lines = [
            "🔎 CROSS-SOURCE COMPARISON",
            "",
            f"📅 {date_value}",
            f"✈️ {airline}",
            f"🔄 {stops} stop(s)",
        ]

        for offer in sorted(
            group,
            key=lambda x: x["price"],
        ):

            price_per_person = (
                offer["price"]
                / PASSENGERS
            )

            lines.append(
                f"• {offer['source']}: "
                f"${offer['price']:.2f} total "
                f"(${price_per_person:.2f}/person)"
            )

        blocks.append(
            "\n".join(lines)
        )

    return "\n\n".join(
        blocks
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "PHUKET FARE TRACKER"
    )

    print("=" * 60)

    print(
        f"Route: "
        f"{ORIGIN} → {DESTINATION}"
    )

    print(
        f"Dates: "
        f"{START_DATE} → {END_DATE}"
    )

    print(
        f"Passengers: "
        f"{PASSENGERS}"
    )

    print(
        f"Max price: "
        f"${MAX_PRICE_PER_PERSON}/person"
    )

    print(
        f"Baggage: "
        f"{BAGGAGE_KG}kg included"
    )

    print(
        f"Max stops: "
        f"{MAX_STOPS}"
    )

    print(
        f"Max duration: "
        f"{MAX_DURATION_MINUTES} minutes"
    )

    print("=" * 60)


    # --------------------------------------------------------
    # LOAD DATABASES
    # --------------------------------------------------------

    history = load_json(
        HISTORY_FILE,
        {},
    )

    seen = load_json(
        SEEN_FILE,
        [],
    )


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    all_offers = []

    for travel_date in date_range(
        START_DATE,
        END_DATE,
    ):

        offers = search_all_sources(
            travel_date.isoformat()
        )

        all_offers.extend(
            offers
        )


    # --------------------------------------------------------
    # NO OFFERS
    # --------------------------------------------------------

    if not all_offers:

        print(
            "No qualifying offers found."
        )

        return


    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    all_offers.sort(
        key=lambda offer: (
            offer["price"]
            / PASSENGERS
        )
    )


    print(
        f"Found "
        f"{len(all_offers)} "
        f"qualifying offers."
    )


    # --------------------------------------------------------
    # UPDATE HISTORY
    # --------------------------------------------------------

    update_history(
        history,
        all_offers,
    )


    # --------------------------------------------------------
    # FIND NEW ALERTS
    # --------------------------------------------------------

    alerts = []

    for offer in all_offers:

        key = offer_key(
            offer
        )

        if key in seen:
            continue

        alerts.append(
            offer
        )

        seen.append(
            key
        )


    # Keep database reasonably small.
    seen = seen[-2000:]


    # --------------------------------------------------------
    # SAVE DATABASES
    # --------------------------------------------------------

    save_json(
        HISTORY_FILE,
        history,
    )

    save_json(
        SEEN_FILE,
        seen,
    )


    # --------------------------------------------------------
    # NO NEW DEALS
    # --------------------------------------------------------

    if not alerts:

        print(
            "No new deals."
        )

        return


    # --------------------------------------------------------
    # MAX 10 ALERTS
    # --------------------------------------------------------

    alerts = alerts[:10]


    # --------------------------------------------------------
    # TELEGRAM HEADER
    # --------------------------------------------------------

    header = (
        "✈️ PHUKET FARE ALERT\n"
        "CXR → HKT\n"
        "21–31 DEC 2026\n"
        f"{PASSENGERS} passengers\n"
        f"≤ ${MAX_PRICE_PER_PERSON}/person "
        f"+ {BAGGAGE_KG}kg baggage\n"
        f"Max {MAX_STOPS} stops / "
        f"max 10h\n"
        "────────────────────"
    )


    # --------------------------------------------------------
    # SEND DEALS
    # --------------------------------------------------------

    sent_count = 0

    for offer in alerts:

        message = (
            header
            + "\n\n"
            + format_offer(
                offer
            )
        )

        if send_telegram(
            message
        ):
            sent_count += 1


    # --------------------------------------------------------
    # CROSS-SOURCE COMPARISON
    # --------------------------------------------------------

    comparison = (
        comparison_text(
            all_offers
        )
    )

    if comparison:

        send_telegram(
            comparison
        )


    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    print(
        f"Sent "
        f"{sent_count} "
        f"new alert(s)."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
