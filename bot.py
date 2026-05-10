import os
import requests
import time
import schedule
import threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_MARKET_CAP = 100_000_000     # Mínimo $100M
MIN_VOLUME = 2_000_000           # Mínimo $2M volumen diario
MAX_24H_CHANGE = 30              # Descarta si ya subió +30%

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def get_coins():
    all_coins = []
    for page in [1, 2, 3]:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": page,
                    "price_change_percentage": "1h,24h,7d"
                },
                timeout=15
            )
            if r.ok:
                all_coins.extend(r.json())
            time.sleep(1)
        except:
            pass
    return all_coins

def calc_signal(coin):
    score = 0
    signals = []

    mcap = coin.get("market_cap") or 0
    volume = coin.get("total_volume") or 0
    h1 = coin.get("price_change_percentage_1h_in_currency") or 0
    h24 = coin.get("price_change_percentage_24h") or 0
    h7d = coin.get("price_change_percentage_7d_in_currency") or 0

    # Filtros de calidad
    if mcap < MIN_MARKET_CAP:
        return 0, [], "none"
    if volume < MIN_VOLUME:
        return 0, [], "none"
    if h24 > MAX_24H_CHANGE:
        return 0, [], "none"

    vol_ratio = volume / mcap

    # Determinar estrategia recomendada
    if mcap > 5_000_000_000:
        estrategia = "pionex"   # Large cap → bot Pionex
    else:
        estrategia = "spot"     # Mid/Small cap → spot manual

    # SEÑAL TEMPRANA: volumen sube, precio quieto
    early = False
    if vol_ratio > 0.3 and abs(h1) < 3:
        score += 40
        signals.append("🎯 Volumen alto, precio quieto")
        early = True

    if vol_ratio > 0.5 and abs(h1) < 5:
        score += 15
        signals.append("⚡ Volumen extremo")
        early = True

    # Moneda dormida que despertó
    if abs(h7d) < 8 and vol_ratio > 0.2 and h24 > 3:
        score += 20
        signals.append("😴 Dormida 7d, activa hoy")
        early = True

    # Inicio de movimiento moderado
    if 2 < h1 < 8 and vol_ratio > 0.15:
        score += 20
        signals.append(f"🌱 Inicio +{h1:.1f}% en 1h")

    if 5 < h24 < 25 and vol_ratio > 0.1:
        score += 15
        signals.append(f"📈 +{h24:.1f}% en 24h")

    # Bonus por tamaño
    if mcap > 5_000_000_000:
        score += 8
        signals.append("🏦 Large cap — muy líquido")
    elif mcap > 500_000_000:
        score += 5
        signals.append("🔹 Mid cap sólido")

    score = max(0, min(100, score))
    return score, signals, estrategia

def analyze_market():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando top 300...")
    coins = get_coins()
    if not coins:
        print("Sin datos")
        return

    pionex_results = []
    spot_results = []

    for coin in coins:
        score, signals, estrategia = calc_signal(coin)
        if score >= 40:
            if estrategia == "pionex":
                pionex_results.append((score, coin, signals))
            elif estrategia == "spot":
                spot_results.append((score, coin, signals))

    pionex_results.sort(key=lambda x: x[0], reverse=True)
    spot_results.sort(key=lambda x: x[0], reverse=True)

    top_pionex = pionex_results[:2]
    top_spot = spot_results[:3]

    if not top_pionex and not top_spot:
        print("Sin señales suficientes")
        return

    hora = datetime.now().strftime('%H:%M')
    msg = f"🔍 *PUMP RADAR — {hora}*\n_Cap mín $100M | Top 300_\n\n"

    if top_spot:
        msg += "📈 *SPOT — Compra manual*\n"
        msg += "_BingX / Bitget / Nexo_\n\n"
        for score, coin, signals in top_spot:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            mcap_str = f"${mcap/1_000_000:.0f}M" if mcap < 1_000_000_000 else f"${mcap/1_000_000_000:.1f}B"

            if price > 1:
                price_str = f"${price:,.3f}"
            elif price > 0.01:
                price_str = f"${price:,.5f}"
            else:
                price_str = f"${price:,.8f}"

            msg += f"🟢 *{symbol}* ({name})\n"
            msg += f"Score: *{score}/100* | Cap: `{mcap_str}`\n"
            msg += f"Precio: `{price_str}` | 1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"_{', '.join(signals)}_\n\n"

    if top_pionex:
        msg += "🤖 *PIONEX BOT — Grid trading*\n"
        msg += "_Large cap estables_\n\n"
        for score, coin, signals in top_pionex:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            mcap_str = f"${mcap/1_000_000_000:.1f}B"

            msg += f"🔵 *{symbol}* ({name})\n"
            msg += f"Score: *{score}/100* | Cap: `{mcap_str}`\n"
            msg += f"Precio: `${price:,.4f}` | 1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"_{', '.join(signals)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviadas: {len(top_spot)} spot, {len(top_pionex)} pionex")

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
                            "Analizo el top 300 con cap mínimo $100M.\n\n"
                            "🟢 *SPOT* — para BingX, Bitget, Nexo\n"
                            "🔵 *PIONEX BOT* — large caps para grid trading\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo operar"
                        )
                    elif text == "/analizar":
                        send_message("🔍 Analizando top 300...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message(
                            "*Cómo operar con las señales:*\n\n"
                            "🟢 *SPOT en BingX/Bitget/Nexo*\n"
                            "1. Verificá que la moneda está disponible\n"
                            "2. Entrás con el monto que querés arriesgar\n"
                            "3. Ponés orden de venta en +15% a +25%\n"
                            "4. Stop loss en -8% para protegerte\n\n"
                            "🔵 *PIONEX BOT*\n"
                            "1. Abrís grid bot en Pionex\n"
                            "2. Elegís la moneda detectada\n"
                            "3. El bot compra y vende solo en el rango\n\n"
                            "⚠️ _Empezá con montos pequeños mientras probás._"
                        )
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado — top 300, cap mín $100M")
    send_message(
        "✅ *Pump Radar actualizado*\n\n"
        "• Analizo top 300 por market cap\n"
        "• Cap mínimo $100M\n"
        "• Volumen mínimo $2M\n"
        "• Separado: Spot vs Pionex Bot\n\n"
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
