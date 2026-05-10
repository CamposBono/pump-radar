import os
import requests
import time
import schedule
import threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_MARKET_CAP = 100_000_000
MIN_VOLUME = 2_000_000
LARGE_CAP = 5_000_000_000

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

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
            time.sleep(1.5)
        except:
            pass
    return all_coins

def get_funding_rates():
    try:
        r = requests.get(
            "https://open-api.coinglass.com/public/v2/funding",
            timeout=10
        )
        if r.ok:
            data = r.json().get("data", [])
            rates = {}
            for item in data:
                symbol = item.get("symbol", "").upper()
                rate = item.get("fundingRate", 0)
                if isinstance(rate, str):
                    rate = float(rate) if rate else 0
                rates[symbol] = float(rate)
            return rates
    except:
        pass
    return {}

def fmt_price(price):
    if price > 100:
        return f"${price:,.2f}"
    elif price > 1:
        return f"${price:,.3f}"
    elif price > 0.01:
        return f"${price:,.5f}"
    else:
        return f"${price:,.8f}"

def fmt_mcap(mcap):
    if mcap >= 1_000_000_000:
        return f"${mcap/1_000_000_000:.1f}B"
    return f"${mcap/1_000_000:.0f}M"

def analyze_market():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando mercado completo...")
    coins = get_coins()
    funding_rates = get_funding_rates()

    if not coins:
        print("Sin datos de mercado")
        return

    spot_long = []
    pionex_grid = []
    futures_short = []
    market_alerts = []

    # Detectar movimiento fuerte de BTC/ETH/SOL
    for coin in coins:
        sym = coin.get("symbol", "").upper()
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        if sym in ["BTC", "ETH", "SOL"] and h1 > 3:
            market_alerts.append((sym, h1, coin.get("current_price", 0)))

    for coin in coins:
        mcap = coin.get("market_cap") or 0
        volume = coin.get("total_volume") or 0
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0
        h7d = coin.get("price_change_percentage_7d_in_currency") or 0
        symbol = coin.get("symbol", "").upper()

        if mcap < MIN_MARKET_CAP or volume < MIN_VOLUME:
            continue

        vol_ratio = volume / mcap
        funding = funding_rates.get(symbol, 0)

        # =====================
        # MÓDULO 1: SPOT LONG
        # =====================
        if h24 < 25:
            score = 0
            signals = []

            if vol_ratio > 0.3 and abs(h1) < 3:
                score += 40
                signals.append("🎯 Volumen alto, precio quieto")

            if vol_ratio > 0.5 and abs(h1) < 5:
                score += 15
                signals.append("⚡ Volumen extremo")

            if abs(h7d) < 8 and vol_ratio > 0.2 and h24 > 3:
                score += 20
                signals.append("😴 Dormida 7d, activa hoy")

            if 2 < h1 < 8 and vol_ratio > 0.15:
                score += 20
                signals.append(f"🌱 Inicio +{h1:.1f}% en 1h")

            if 5 < h24 < 20 and vol_ratio > 0.1:
                score += 15
                signals.append(f"📈 +{h24:.1f}% en 24h")

            if mcap < LARGE_CAP and score >= 40:
                spot_long.append((score, coin, signals))

        # =====================
        # MÓDULO 2: PIONEX GRID
        # =====================
        if mcap >= LARGE_CAP:
            lateral_score = 0
            grid_signals = []

            rango = abs(h24)
            if rango < 5 and vol_ratio > 0.05:
                lateral_score += 40
                grid_signals.append(f"↔️ Lateral {rango:.1f}% en 24h")

            if rango < 3:
                lateral_score += 20
                grid_signals.append("🎯 Rango muy ajustado — ideal grid")

            if abs(h7d) < 15 and vol_ratio > 0.03:
                lateral_score += 20
                grid_signals.append("📊 Consolidando 7 días")

            if vol_ratio > 0.05:
                lateral_score += 10
                grid_signals.append("✅ Volumen sostenido")

            if lateral_score >= 50:
                pionex_grid.append((lateral_score, coin, grid_signals))

        # =====================
        # MÓDULO 3: FUTUROS SHORT
        # =====================
        short_score = 0
        short_signals = []

        if h24 > 15:
            short_score += 20
            short_signals.append(f"📈 Subió {h24:.1f}% en 24h")

        if funding > 0.001:
            short_score += 35
            short_signals.append(f"💰 Funding rate alto: {funding*100:.3f}%")
        elif funding > 0.0005:
            short_score += 15
            short_signals.append(f"💰 Funding elevado: {funding*100:.3f}%")

        if h1 < 1 and h24 > 10:
            short_score += 25
            short_signals.append("⚠️ Precio estancado tras subida fuerte")

        if h24 > 20 and vol_ratio < 0.1:
            short_score += 20
            short_signals.append("📉 Volumen bajando en máximos")

        if short_score >= 45:
            futures_short.append((short_score, coin, short_signals))

    # Ordenar y tomar los mejores
    spot_long.sort(key=lambda x: x[0], reverse=True)
    pionex_grid.sort(key=lambda x: x[0], reverse=True)
    futures_short.sort(key=lambda x: x[0], reverse=True)

    top_spot = spot_long[:3]
    top_grid = pionex_grid[:2]
    top_short = futures_short[:2]

    if not top_spot and not top_grid and not top_short and not market_alerts:
        print("Mercado tranquilo, sin señales")
        return

    hora = datetime.now().strftime('%H:%M')
    msg = f"🔍 *PUMP RADAR — {hora}*\n\n"

    # Alerta de mercado general
    if market_alerts:
        msg += "🟡 *ALERTA DE MERCADO*\n"
        for sym, h1, price in market_alerts:
            msg += f"• *{sym}* subió `+{h1:.1f}%` en 1h — altcoins pueden seguir\n"
        msg += "\n"

    # Spot long
    if top_spot:
        msg += "🟢 *SPOT LONG — BingX / Bitget / Nexo*\n"
        msg += "_Señales tempranas de pump_\n\n"
        for score, coin, signals in top_spot:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"▶️ *{sym}* ({name})\n"
            msg += f"Score: *{score}/100* | Cap: `{fmt_mcap(mcap)}`\n"
            msg += f"Precio: `{fmt_price(price)}` | 1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"🎯 Objetivo: +15% a +25% | Stop: -8%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    # Pionex grid
    if top_grid:
        msg += "🔵 *PIONEX BOT — Grid trading*\n"
        msg += "_Mercado lateral detectado_\n\n"
        for score, coin, signals in top_grid:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"↔️ *{sym}* ({name})\n"
            msg += f"Score: `{score}/100` | Cap: `{fmt_mcap(mcap)}`\n"
            msg += f"Precio: `{fmt_price(price)}` | Rango 24h: `{h24:+.2f}%`\n"
            msg += f"🤖 Activar grid bot neutral en Pionex\n"
            msg += f"_{', '.join(signals)}_\n\n"

    # Futuros short
    if top_short:
        msg += "🔴 *FUTUROS SHORT — BingX / Bitget*\n"
        msg += "_Posible corrección detectada_\n\n"
        for score, coin, signals in top_short:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            msg += f"🔻 *{sym}* ({name})\n"
            msg += f"Score: *{score}/100*\n"
            msg += f"Precio: `{fmt_price(price)}` | 1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"⚠️ Apalancamiento máx 3x | Stop: +5%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviado: {len(top_spot)} spot, {len(top_grid)} grid, {len(top_short)} short, {len(market_alerts)} alertas")

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
                            "👋 *Pump Radar — Bot completo*\n\n"
                            "🟢 *SPOT LONG* — señales tempranas de pump\n"
                            "_BingX / Bitget / Nexo_\n\n"
                            "🔵 *PIONEX GRID* — mercado lateral\n"
                            "_Neutral, compra y vende en rango_\n\n"
                            "🔴 *FUTUROS SHORT* — corrección esperada\n"
                            "_BingX / Bitget — máx 3x_\n\n"
                            "🟡 *ALERTA MERCADO* — BTC/ETH/SOL en movimiento\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo operar cada señal"
                        )
                    elif text == "/analizar":
                        send_message("🔍 Analizando mercado completo...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message(
                            "*Cómo operar cada señal:*\n\n"
                            "🟢 *SPOT LONG*\n"
                            "1. Verificá disponibilidad en tu exchange\n"
                            "2. Comprás spot con el monto elegido\n"
                            "3. Orden de venta en +15% a +25%\n"
                            "4. Stop loss en -8%\n\n"
                            "🔵 *PIONEX GRID*\n"
                            "1. Abrís grid bot neutral en Pionex\n"
                            "2. Configurás el rango detectado\n"
                            "3. El bot opera solo comprando abajo y vendiendo arriba\n"
                            "4. Funciona mejor mientras más lateral esté\n\n"
                            "🔴 *FUTUROS SHORT*\n"
                            "1. Abrís posición short en BingX o Bitget\n"
                            "2. Máximo 2x-3x de apalancamiento\n"
                            "3. Stop loss en +5% sobre tu entrada\n"
                            "4. Objetivo: -10% a -20%\n\n"
                            "🟡 *ALERTA MERCADO*\n"
                            "Cuando BTC/ETH/SOL sube fuerte, las altcoins suelen seguir en 1-2hs.\n"
                            "Momento para revisar posiciones spot.\n\n"
                            "⚠️ _Empezá con montos pequeños mientras probás._"
                        )
        except Exception as e:
            print(f"Error updates: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar completo iniciado")
    send_message(
        "✅ *Pump Radar actualizado — 4 módulos activos*\n\n"
        "🟢 Spot Long — señales tempranas\n"
        "🔵 Pionex Grid — lateralización\n"
        "🔴 Futuros Short — corrección\n"
        "🟡 Alerta Mercado — BTC/ETH/SOL\n\n"
        "Cap mínimo $100M | Top 300\n\n"
        "Escribí /analizar para el primer análisis."
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
