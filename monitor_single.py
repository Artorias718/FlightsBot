import requests
from datetime import datetime
import time
import re
import json
import os
from playwright.sync_api import sync_playwright

# =========================
# 🎛️ PARAMETERS
# =========================
ORIGIN = "CAG"
DESTINATION = "LIN"
DATE = "2026-08-22"
ADULTS = 1
CURRENCY = "EUR"

# =========================
# 🔔 GOTIFY
# =========================
GOTIFY_URL = "http://192.168.1.137:9000"
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN")
# =========================
# 🌐 API AND STATE
# =========================
URL = "https://aeroitalia-gateway.azure-api.net/dotrezprod/api/nsk/v4/availability/search/simple"
STATE_FILE = "flight_state.json"


def get_subscription_key():
    try:
        with open("subkey.txt", "r") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    print("⚠️ subkey.txt mancante o vuoto: le chiamate API daranno 401")
    return ""


SUBSCRIPTION_KEY = get_subscription_key()


# =========================
# 🔐 JWT HANDLING
# =========================
def get_jwt():
    try:
        with open("jwt.txt", "r") as f:
            return f.read().strip()
    except:
        return None


JWT_REGEX = re.compile(r"^eyJ")


def refresh_jwt():
    print("🔄 Aggiorno JWT...")

    jwt_token = {"value": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        def handle_request(request):
            headers = request.headers
            auth = headers.get("authorization") or headers.get("Authorization")

            if auth and JWT_REGEX.match(auth):
                jwt_token["value"] = auth

        page.on("request", handle_request)

        page.goto("https://www.aeroitalia.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        try:
            page.get_by_role("button", name="Accetta tutti i cookie").click(
                timeout=5000
            )
        except:
            pass

        page.get_by_role("textbox", name="Seleziona la partenza").click()
        page.get_by_role("textbox").first.fill("olb")
        page.locator("div").filter(has_text=re.compile(r"^Olbia$")).click()

        page.get_by_role("textbox").nth(1).click()
        page.get_by_role("textbox").nth(1).fill("lin")
        page.get_by_text("Milano Linate").click()

        page.locator(".sc-eeMvmM > svg").first.click()
        page.get_by_role("textbox").nth(2).click()

        page.wait_for_timeout(1000)

        if jwt_token["value"]:
            with open("jwt.txt", "w", encoding="utf-8") as f:
                f.write(jwt_token["value"])
            print("✅ JWT aggiornato")
        else:
            print("❌ JWT NON trovato")

        context.close()
        browser.close()


# =========================
# 🧠 FORMATTING & SUMMARY
# =========================
def format_date(dt_str):
    dt = datetime.fromisoformat(dt_str)
    mesi = [
        "Gennaio",
        "Febbraio",
        "Marzo",
        "Aprile",
        "Maggio",
        "Giugno",
        "Luglio",
        "Agosto",
        "Settembre",
        "Ottobre",
        "Novembre",
        "Dicembre",
    ]
    return f"{dt.day:02d} {mesi[dt.month - 1]}"


def format_time(dt_str):
    return datetime.fromisoformat(dt_str).strftime("%H:%M")


def get_detailed_summary(response_json):
    data = response_json.get("data", {})
    results = data.get("results", [])
    if not results:
        return "❌ Nessun volo trovato"

    output = []
    output.append("🚀 MONITORAGGIO AVVIATO")

    for block in results:
        for trip in block.get("trips", []):
            date_str = trip.get("date", "").split("T")[0]
            journeys = trip.get("journeysAvailableByMarket", {})

            for market, flights in journeys.items():
                output.append("\n" + "=" * 30)
                output.append(f"✈️ {market} | 📅 {date_str}")
                output.append("=" * 30)

                for flight in flights:
                    seg = flight["segments"][0]
                    leg = seg["legs"][0]["legInfo"]
                    carrier = seg["identifier"]["carrierCode"]
                    number = seg["identifier"]["identifier"]

                    dep_date_fmt = format_date(seg["designator"]["departure"])
                    dep_time = format_time(seg["designator"]["departure"])
                    arr_time = format_time(seg["designator"]["arrival"])

                    aircraft = leg.get("equipmentType")
                    sold = leg.get("sold")

                    available_count = "N/D"
                    fares = flight.get("fares", [])
                    if fares:
                        details = fares[0].get("details", [])
                        if details:
                            available_count = details[0].get("availableCount")

                    fare_price = "N/D"
                    fares_available = data.get("faresAvailable", {})
                    if fares:
                        fare_key = fares[0].get("fareAvailabilityKey")
                        if fare_key and fare_key in fares_available:
                            fare_price = (
                                f"{fares_available[fare_key]['totals']['fareTotal']} €"
                            )

                    f_info = (
                        f"🛫 Volo: {carrier}{number}\n"
                        f"⏰ {dep_date_fmt} {dep_time} -> {arr_time}\n"
                        f"✈️ Aereo: {aircraft}\n"
                        f"🎟 Venduti: {sold}\n"
                        f"💺 Disponibili: {available_count}\n"
                        f"💰 Prezzo: {fare_price}\n"
                        f"------------------------------"
                    )
                    output.append(f_info)

    return "\n".join(output)


def extract_flight_data(response_json):
    flights_set = set()
    results = response_json.get("data", {}).get("results", [])
    for block in results:
        for trip in block.get("trips", []):
            journeys = trip.get("journeysAvailableByMarket", {})
            for flights in journeys.values():
                for flight in flights:
                    seg = flight["segments"][0]
                    f_num = f"{seg['identifier']['carrierCode']}{seg['identifier']['identifier']}"
                    flights_set.add(f_num)
    return flights_set


# =========================
# 🔔 GOTIFY SEND
# =========================
def send_gotify(title, message, priority=5):
    try:
        requests.post(
            f"{GOTIFY_URL}/message",
            params={"token": GOTIFY_TOKEN},
            data={"title": title, "message": message, "priority": priority},
            timeout=10,
        )
    except Exception as e:
        print("❌ Errore Gotify:", e)


# =========================
# 🚀 FETCH FLIGHTS
# =========================
def fetch_flights():
    headers = {
        "Authorization": get_jwt(),
        "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
        "Content-Type": "application/json",
        "Origin": "https://book.aeroitalia.com",
        "Referer": "https://book.aeroitalia.com/",
        "User-Agent": "Mozilla/5.0",
    }

    payload = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "beginDate": DATE,
        "codes": {"currencyCode": CURRENCY, "promotionCode": ""},
        "passengers": {"types": [{"count": ADULTS, "type": "ADT"}]},
        "filters": {"maxConnections": 15},
    }

    resp = requests.post(URL, json=payload, headers=headers)

    if resp.status_code == 401:
        refresh_jwt()
        headers["Authorization"] = get_jwt()
        resp = requests.post(URL, json=payload, headers=headers)

    return resp.json() if resp.status_code == 200 else None


# =========================
# 🚀 MAIN
# =========================
def main():
    print(f"🚀 Avvio monitoraggio {ORIGIN}-{DESTINATION}...")
    first_run = True

    while True:
        data = fetch_flights()

        if data:
            current_summary = get_detailed_summary(data)
            current_flights_set = extract_flight_data(data)

            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    last_state = set(json.load(f))
            else:
                last_state = set()

            if first_run:
                print(current_summary)
                send_gotify("✈️ Report iniziale voli", current_summary, priority=1)
                first_run = False

            else:
                added = current_flights_set - last_state
                removed = last_state - current_flights_set

                if added:
                    msg = "🆕 Nuovi voli:\n" + "\n".join(sorted(added))
                    print(msg)
                    send_gotify("🆕 Nuovi voli", msg, priority=10)
                    send_gotify("🔄 Aggiornamento voli", current_summary, priority=10)

                if removed:
                    msg = "❌ Voli rimossi:\n" + "\n".join(sorted(removed))
                    print(msg)
                    send_gotify("❌ Voli rimossi", msg, priority=10)
                    send_gotify("🔄 Aggiornamento voli", current_summary, priority=10)

            with open(STATE_FILE, "w") as f:
                json.dump(list(current_flights_set), f)

        else:
            print("❌ Errore recupero dati API.")

        print(f"⏱️ Attendo 5 minuti... ({datetime.now().strftime('%H:%M:%S')})")
        time.sleep(300)


if __name__ == "__main__":
    main()
