import os
import requests
import time
import schedule
import threading
from datetime import datetime

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
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "1h,24h,7d"
            },
            timeout=15
        )
        return r.json() if r.ok else []
    except:
        return []

def calc_early_signal(coin):
    score = 0
    signals = []
    early = False

    mcap = coin.get("market_cap") or 1
    volume = coin.get("total_volume") or 0
    h1 = coin.get("price_change_percentage_1h_in_currency") or 0
    h24 = coin.get("price_change_percentage_24h") or 0
    h7d = coin.get("price_change_percentage_7d_in_currency") or 0

    vol_ratio = volume / mcap

    # SEÑAL TEMPRANA: volumen sube pero precio quieto
    if vol_ratio > 0.3 and abs(h1) < 3:
        score += 40
        signals.append("🎯 Volumen alto con precio quieto")
        early = True

    if vol_ratio > 0.5 and abs(h1) < 5:
        score += 20
        signals.append("⚡ Volumen extremo sin movimiento")
        early = True

    # Moneda dormida que despertó
    if abs(h7d) < 10 and vol_ratio > 0.2:
        score += 15
        signals.append("😴 Dormida 7d pero activa hoy")
        early = True

    # Inicio de movimiento moderado
    if h1 > 2 and h1 < 8 and vol_ratio > 0.15:
        score += 20
        signals.append(f"🌱 Inicio +{h1:.1f}% en 1h")

    if h24 > 5 and h24 < 20 and vol_ratio > 0.1:
        score += 15
        signals.append(f"📈 +{h24:.1f}% en 24h")

    # Penalizar si ya subió demasiado
    if h24 > 30:
        score -= 25
        signals.append(f"⚠️ Ya subió {h24:.1f}% puede ser tarde")

    if h1 > 15:
        score -= 20
        signals.append(f"⚠️ Ya subió {h1:.1f}% en 1h")

    # Tamaño del activo
    if mcap < 10_000_000:
        score += 10
        signals.append("💎 Micro cap")
    elif mcap < 100_000_000:
        score += 8
        signals.append("🔹 Small cap")
    elif mcap > 1_000_000_000:
        score += 5
        signals.append("🏦 Large cap")

    score = max(0, min(100, score))
    return score, signals, early

def analyze_market():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    coins = get_coins()
    if not coins:
        return

    results = []
    for coin in coins:
        score, signals, early = calc_early_signal(coin)
        if score >= 45:
            results.append((score, coin, signals, early))

    results.sort(key=lambda x: (x[3], x[0]), reverse=True)
    top = results[:3]

    if not top:
        print("Sin señales suficientes")
        return

    hora = datetime.now().strftime('%H:%M')
    msg = f"🔍 *PUMP RADAR — {hora}*\n_Top {len(top)} señales tempranas_\n\n"

    for score, coin, signals, early in top:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        price = coin.get("current_price", 0)
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0

        emoji = "🎯" if early else ("🔴" if score >= 60 else "🟠")
        tipo = "SEÑAL TEMPRANA" if early else ("SEÑAL FUERTE" if score >= 60 else "SEÑAL MODERADA")

        msg += f"{emoji} *{symbol}* ({name}) — {tipo}\n"
        msg += f"Score: *{score}/100* | Precio: `${price:,.6f}`\n"
        msg += f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
        msg += f"_{', '.join(signals)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviadas {len(top)} alertas")

def handle_updates():
    last_update = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": last_update + 1, "timeout": 10}, timeout=15)
            if r.ok:
                for update in r.json().get("result", []):
                    last_update = update["update_id"]
                    text = update.get("message", {}).get("text", "")
                    if text == "/start":
                        send_message("👋 *Pump Radar activo*\nDetecto señales tempranas antes de que suban.\n\n/analizar — análisis ahora\n/ayuda — cómo interpretar")
                    elif text == "/analizar":
                        send_message("🔍 Analizando...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message("🎯 *SEÑAL TEMPRANA* — volumen sube pero precio quieto. Mejor momento.\n\n🔴 *SEÑAL FUERTE* — movimiento iniciado.\n\n🟠 *SEÑAL MODERADA* — actividad interesante.\n\n⚠️ Si ya subió +30% puede ser tarde.\n\n_Verificá siempre en CoinMarketCap antes de invertir._")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado")
    send_message("✅ *Bot actualizado*\nAhora detecto señales tempranas — volumen subiendo antes que el precio.\nMáximo 3 alertas por hora.\n\nEscribí /analizar para empezar.")
    schedule.every(1).hours.do(analyze_market)
    analyze_market()
    t = threading.Thread(target=handle_updates, daemon=True)
    t.start()
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
