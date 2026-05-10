import os
import requests
import time
import schedule
import threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# FILTROS DE CALIDAD
MIN_MARKET_CAP = 50_000_000      # Mínimo $50M de capitalización
MIN_VOLUME = 1_000_000           # Mínimo $1M de volumen diario
MAX_24H_CHANGE = 25              # Si ya subió más de 25% en 24h, descartamos

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
                "per_page": 150,
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

    mcap = coin.get("market_cap") or 0
    volume = coin.get("total_volume") or 0
    h1 = coin.get("price_change_percentage_1h_in_currency") or 0
    h24 = coin.get("price_change_percentage_24h") or 0
    h7d = coin.get("price_change_percentage_7d_in_currency") or 0

    # FILTROS DE CALIDAD — descartar monedas dudosas
    if mcap < MIN_MARKET_CAP:
        return 0, [], False
    if volume < MIN_VOLUME:
        return 0, [], False
    if h24 > MAX_24H_CHANGE:
        return 0, [], False

    vol_ratio = volume / mcap

    # SEÑAL TEMPRANA: volumen sube pero precio quieto (acumulación)
    early = False
    if vol_ratio > 0.3 and abs(h1) < 3:
        score += 40
        signals.append("🎯 Volumen alto, precio quieto")
        early = True

    if vol_ratio > 0.5 and abs(h1) < 5:
        score += 20
        signals.append("⚡ Volumen extremo sin movimiento")
        early = True

    # Moneda dormida que despertó esta semana
    if abs(h7d) < 8 and vol_ratio > 0.2 and h24 > 3:
        score += 20
        signals.append("😴 Dormida 7d, activa hoy")
        early = True

    # Inicio de movimiento moderado (no demasiado tarde)
    if h1 > 2 and h1 < 7 and vol_ratio > 0.15:
        score += 20
        signals.append(f"🌱 Inicio +{h1:.1f}% en 1h")

    if h24 > 5 and h24 < 20 and vol_ratio > 0.1:
        score += 15
        signals.append(f"📈 +{h24:.1f}% en 24h")

    # Bonus por tamaño (más seguro)
    if mcap > 500_000_000:
        score += 8
        signals.append("🏦 Mid/Large cap")
    elif mcap > 100_000_000:
        score += 5
        signals.append("🔹 Small cap sólido")

    score = max(0, min(100, score))
    return score, signals, early

def analyze_market():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    coins = get_coins()
    if not coins:
        print("Sin datos")
        return

    results = []
    for coin in coins:
        score, signals, early = calc_early_signal(coin)
        if score >= 45:
            results.append((score, coin, signals, early))

    # Ordenar: primero señales tempranas, luego por score
    results.sort(key=lambda x: (x[3], x[0]), reverse=True)
    top = results[:3]

    if not top:
        print("Sin señales suficientes")
        return

    hora = datetime.now().strftime('%H:%M')
    msg = f"🔍 *PUMP RADAR — {hora}*\n_Top {len(top)} señales — cap mín $50M_\n\n"

    for score, coin, signals, early in top:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        price = coin.get("current_price", 0)
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0
        mcap = coin.get("market_cap") or 0

        emoji = "🎯" if early else ("🔴" if score >= 60 else "🟠")
        tipo = "SEÑAL TEMPRANA" if early else ("SEÑAL FUERTE" if score >= 60 else "SEÑAL MODERADA")

        if price > 1:
            price_str = f"${price:,.4f}"
        elif price > 0.01:
            price_str = f"${price:,.6f}"
        else:
            price_str = f"${price:,.8f}"

        mcap_str = f"${mcap/1_000_000:.0f}M" if mcap < 1_000_000_000 else f"${mcap/1_000_000_000:.1f}B"

        msg += f"{emoji} *{symbol}* ({name}) — {tipo}\n"
        msg += f"Score: *{score}/100* | Cap: `{mcap_str}`\n"
        msg += f"Precio: `{price_str}`\n"
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
                        send_message(
                            "👋 *Pump Radar activo*\n\n"
                            "Detecto señales tempranas en monedas con cap mínimo $50M.\n"
                            "Sin shitcoins, sin monedas dudosas.\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo interpretar las señales"
                        )
                    elif text == "/analizar":
                        send_message("🔍 Analizando mercado...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message(
                            "*Cómo interpretar:*\n\n"
                            "🎯 *SEÑAL TEMPRANA*\n"
                            "Volumen subiendo pero precio quieto.\n"
                            "Alguien está comprando antes del movimiento.\n"
                            "→ Mejor momento para entrar\n\n"
                            "🔴 *SEÑAL FUERTE*\n"
                            "Movimiento iniciado con fuerza.\n"
                            "→ Todavía puede tener recorrido\n\n"
                            "🟠 *SEÑAL MODERADA*\n"
                            "Actividad interesante, seguir de cerca.\n\n"
                            "*Filtros activos:*\n"
                            "✅ Cap mínimo $50M\n"
                            "✅ Volumen mínimo $1M\n"
                            "✅ Descarta monedas que ya subieron +25%\n\n"
                            "_Verificá siempre en CoinMarketCap antes de invertir._"
                        )
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado — filtro $50M activado")
    send_message(
        "✅ *Bot actualizado — Filtro de calidad activo*\n\n"
        "Ahora solo analizo monedas con:\n"
        "• Cap mínimo $50M\n"
        "• Volumen mínimo $1M\n"
        "• Sin monedas que ya subieron +25%\n\n"
        "Escribí /analizar para ver las primeras señales."
    )
    schedule.every(1).hours.do(analyze_market)
    analyze_market()
    t = threading.Thread(target=handle_updates, daemon=True)
    t.start()
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
