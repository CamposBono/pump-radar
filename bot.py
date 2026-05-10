import os
import requests
import time
import schedule
import threading

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def get_coins():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 80,
                "page": 1,
                "price_change_percentage": "1h,24h"
            },
            timeout=10
        )
        return r.json() if r.ok else []
    except:
        return []

def calc_score(coin):
    score = 0
    reasons = []

    vol_ratio = (coin.get("total_volume") or 0) / max(coin.get("market_cap") or 1, 1)
    if vol_ratio > 0.5:
        score += 30; reasons.append("🔥 Volumen extremo")
    elif vol_ratio > 0.2:
        score += 18; reasons.append("📊 Volumen muy alto")
    elif vol_ratio > 0.08:
        score += 8; reasons.append("📊 Volumen moderado")

    h1 = coin.get("price_change_percentage_1h_in_currency") or 0
    if h1 > 15:
        score += 25; reasons.append(f"+{h1:.1f}% en 1h")
    elif h1 > 7:
        score += 15; reasons.append(f"+{h1:.1f}% en 1h")
    elif h1 > 3:
        score += 7; reasons.append(f"+{h1:.1f}% en 1h")
    elif h1 < -10:
        score -= 10

    h24 = coin.get("price_change_percentage_24h") or 0
    if h24 > 30:
        score += 20; reasons.append(f"+{h24:.1f}% en 24h")
    elif h24 > 15:
        score += 12; reasons.append(f"+{h24:.1f}% en 24h")
    elif h24 > 5:
        score += 5; reasons.append(f"+{h24:.1f}% en 24h")

    mcap = coin.get("market_cap") or 0
    if mcap < 10_000_000:
        score += 15; reasons.append("💎 Micro cap")
    elif mcap < 100_000_000:
        score += 8; reasons.append("🔹 Small cap")

    score = max(0, min(100, score))
    return score, reasons

def analyze_market():
    print("Analizando mercado...")
    coins = get_coins()
    if not coins:
        print("No se pudo obtener datos")
        return

    results = []
    for coin in coins:
        score, reasons = calc_score(coin)
        if score >= 60:
            results.append((score, coin, reasons))

    results.sort(key=lambda x: x[0], reverse=True)

    if not results:
        print("Sin señales altas en este momento")
        return

    msg = "🚨 *PUMP RADAR — Alertas activas*\n\n"
    for score, coin, reasons in results[:5]:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        price = coin.get("current_price", 0)
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0

        emoji = "🔴" if score >= 75 else "🟠"
        msg += f"{emoji} *{symbol}* ({name})\n"
        msg += f"Score: *{score}/100*\n"
        msg += f"Precio: ${price:,.4f}\n"
        msg += f"1h: {h1:+.2f}% | 24h: {h24:+.2f}%\n"
        msg += f"Señales: {', '.join(reasons)}\n\n"

    msg += "⚠️ _Solo experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviadas {len(results)} alertas")

def handle_updates():
    last_update = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": last_update + 1, "timeout": 10}, timeout=15)
            if r.ok:
                data = r.json()
                for update in data.get("result", []):
                    last_update = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")

                    if text == "/start":
                        send_message(f"👋 ¡Hola! Soy tu *Pump Radar Bot*.\n\nTe voy a mandar alertas cada hora cuando detecte señales de pump.\n\nTu Chat ID es: `{chat_id}`\n\nGuardalo y ponelo en Railway como TELEGRAM_CHAT_ID.")
                    elif text == "/analizar":
                        send_message("🔍 Analizando mercado ahora mismo...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message("*Comandos disponibles:*\n\n/analizar — Analiza el mercado ahora\n/ayuda — Muestra esta ayuda\n\nLas alertas automáticas se mandan cada hora.")
        except Exception as e:
            print(f"Error updates: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar Bot iniciado")
    send_message("✅ *Pump Radar Bot activado*\nVoy a analizar el mercado cada hora y avisarte cuando detecte señales de pump.\n\nEscribí /analizar para un análisis inmediato.")

    # Análisis cada hora
    schedule.every(1).hours.do(analyze_market)

    # Análisis inicial
    analyze_market()

    # Hilo para recibir mensajes
    t = threading.Thread(target=handle_updates, daemon=True)
    t.start()

    # Loop principal
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
