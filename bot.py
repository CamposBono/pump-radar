import os
import requests
import time
import schedule
import threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_MARKET_CAP_SPOT = 300_000_000    # $300M mínimo para spot
MIN_MARKET_CAP_GRID = 5_000_000_000  # $5B para Pionex grid
MIN_MARKET_CAP_SHORT = 500_000_000   # $500M para futuros short
MIN_VOLUME = 5_000_000               # $5M volumen mínimo

# Stablecoins y tokens no deseados
BLACKLIST_SYMBOLS = {
    # Stablecoins
    "usdt", "usdc", "busd", "dai", "tusd", "usdp", "usdd", "gusd", "frax",
    "lusd", "susd", "cusd", "husd", "eurs", "rusd", "pyusd", "fdusd",
    "usde", "usdx", "crvusd", "gho", "mim", "usdn", "ousd", "alusd",
    "dola", "usd+", "buidl",
    # Wrapped tokens
    "wbtc", "tbtc", "steth", "weth", "cbeth", "reth", "sfrxeth", "weeth",
    "ezeth", "rseth", "wsteth", "heth",
    # Tokens de oro
    "paxg", "xaut",
    # Tokens problemáticos detectados
    "bill", "binancelife",
}

# Palabras prohibidas en el nombre
BLACKLIST_WORDS = [
    "usd", "tether", "wrapped", "staked", "bridged", "liquid staking",
    "binancelife", "币安", "人生", "inu", "elon", "baby", "safe",
    "moon", "doge2", "shib2", "pepe2"
]

def is_valid_coin(coin):
    symbol = (coin.get("symbol") or "").lower().strip()
    name = (coin.get("name") or "").lower().strip()
    mcap = coin.get("market_cap") or 0
    volume = coin.get("total_volume") or 0

    # Filtrar por símbolo en blacklist
    if symbol in BLACKLIST_SYMBOLS:
        return False

    # Filtrar por palabras en nombre
    for word in BLACKLIST_WORDS:
        if word in name:
            return False

    # Filtrar caracteres no latinos (chino, árabe, etc.)
    try:
        name.encode('ascii')
    except UnicodeEncodeError:
        return False

    # Filtrar volumen mínimo
    if volume < MIN_VOLUME:
        return False

    return True

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

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
            time.sleep(2)
        except Exception as e:
            print(f"Error obteniendo datos página {page}: {e}")
    return all_coins

def fmt_price(price):
    if not price:
        return "$0"
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
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando mercado...")
    coins = get_coins()

    if not coins:
        print("Sin datos de mercado")
        return

    spot_long = []
    pionex_grid = []
    futures_short = []
    market_alerts = []

    # Alerta mercado general — BTC/ETH/SOL
    for coin in coins:
        sym = (coin.get("symbol") or "").upper()
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        if sym in ["BTC", "ETH", "SOL"] and abs(h1) > 3:
            direction = "🟢 subió" if h1 > 0 else "🔴 cayó"
            market_alerts.append((sym, h1, coin.get("current_price", 0), direction))

    for coin in coins:
        if not is_valid_coin(coin):
            continue

        mcap = coin.get("market_cap") or 0
        volume = coin.get("total_volume") or 0
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0
        h7d = coin.get("price_change_percentage_7d_in_currency") or 0
        vol_ratio = volume / max(mcap, 1)

        # ========================
        # SPOT LONG — $300M a $5B
        # ========================
        if MIN_MARKET_CAP_SPOT <= mcap < MIN_MARKET_CAP_GRID and h24 < 25:
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

            if score >= 40:
                spot_long.append((score, coin, signals))

        # ========================
        # PIONEX GRID — +$5B
        # ========================
        if mcap >= MIN_MARKET_CAP_GRID:
            lateral_score = 0
            grid_signals = []
            rango = abs(h24)

            if rango < 5 and vol_ratio > 0.05:
                lateral_score += 40
                grid_signals.append(f"↔️ Lateral {rango:.1f}% en 24h")

            if rango < 3:
                lateral_score += 20
                grid_signals.append("🎯 Rango ajustado — ideal grid")

            if abs(h7d) < 15 and vol_ratio > 0.03:
                lateral_score += 20
                grid_signals.append("📊 Consolidando 7 días")

            if vol_ratio > 0.05:
                lateral_score += 10
                grid_signals.append("✅ Volumen sostenido")

            if lateral_score >= 50:
                pionex_grid.append((lateral_score, coin, grid_signals))

        # ========================
        # FUTUROS SHORT — +$500M
        # Sin Coinglass — lógica propia
        # ========================
        if mcap >= MIN_MARKET_CAP_SHORT:
            short_score = 0
            short_signals = []

            # Subida fuerte en 24h
            if h24 > 20:
                short_score += 25
                short_signals.append(f"📈 Subió {h24:.1f}% en 24h")
            elif h24 > 15:
                short_score += 15
                short_signals.append(f"📈 Subió {h24:.1f}% en 24h")

            # Precio se frenó después de subir
            if h1 < 0 and h24 > 15:
                short_score += 30
                short_signals.append(f"⚠️ Frena en 1h: {h1:.2f}%")

            # Volumen bajando en máximos
            if h24 > 15 and vol_ratio < 0.08:
                short_score += 25
                short_signals.append("📉 Volumen se agota en máximos")

            # Subida sin volumen fuerte — pump débil
            if h24 > 10 and vol_ratio < 0.05:
                short_score += 20
                short_signals.append("💨 Subida sin volumen — pump débil")

            if short_score >= 50:
                futures_short.append((short_score, coin, short_signals))

    # Ordenar y seleccionar mejores
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

    # Alerta mercado
    if market_alerts:
        msg += "🟡 *ALERTA DE MERCADO*\n"
        for sym, h1, price, direction in market_alerts:
            msg += f"• *{sym}* {direction} `{h1:+.1f}%` en 1h → `{fmt_price(price)}`\n"
        if any(h1 > 0 for _, h1, _, _ in market_alerts):
            msg += "_Altcoins suelen seguir en 1-2hs_\n"
        msg += "\n"

    # Spot long
    if top_spot:
        msg += "🟢 *SPOT LONG — BingX / Bitget / Nexo*\n"
        msg += "_Señales tempranas | Cap $300M-$5B_\n\n"
        for score, coin, signals in top_spot:
            sym = (coin.get("symbol") or "").upper()
            name = coin.get("name") or ""
            price = coin.get("current_price") or 0
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"▶️ *{sym}* ({name}) | `{fmt_mcap(mcap)}`\n"
            msg += f"Score: *{score}/100* | `{fmt_price(price)}`\n"
            msg += f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"🎯 Objetivo: +15/25% | Stop: -8%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    # Pionex grid
    if top_grid:
        msg += "🔵 *PIONEX GRID — Bot neutral*\n"
        msg += "_Large caps laterales | Cap +$5B_\n\n"
        for score, coin, signals in top_grid:
            sym = (coin.get("symbol") or "").upper()
            name = coin.get("name") or ""
            price = coin.get("current_price") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"↔️ *{sym}* ({name}) | `{fmt_mcap(mcap)}`\n"
            msg += f"Score: `{score}/100` | `{fmt_price(price)}`\n"
            msg += f"Rango 24h: `{h24:+.2f}%`\n"
            msg += f"🤖 Activar grid bot neutral en Pionex\n"
            msg += f"_{', '.join(signals)}_\n\n"

    # Futuros short
    if top_short:
        msg += "🔴 *FUTUROS SHORT — BingX / Bitget*\n"
        msg += "_Posible corrección | Cap +$500M_\n\n"
        for score, coin, signals in top_short:
            sym = (coin.get("symbol") or "").upper()
            name = coin.get("name") or ""
            price = coin.get("current_price") or 0
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            msg += f"🔻 *{sym}* ({name})\n"
            msg += f"Score: *{score}/100* | `{fmt_price(price)}`\n"
            msg += f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"⚠️ Máx 3x | Stop: +5% | Objetivo: -10/20%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviado: {len(top_spot)} spot, {len(top_grid)} grid, {len(top_short)} short")

def handle_updates():
    last_update = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            r = requests.get(url, params={
                "offset": last_update + 1,
                "timeout": 10
            }, timeout=15)
            if r.ok:
                for update in r.json().get("result", []):
                    last_update = update["update_id"]
                    text = (update.get("message") or {}).get("text") or ""

                    if text == "/start":
                        send_message(
                            "👋 *Pump Radar — 4 módulos activos*\n\n"
                            "🟢 *SPOT LONG* | Cap $300M+ | BingX/Bitget/Nexo\n"
                            "🔵 *PIONEX GRID* | Cap $5B+ | Bot neutral\n"
                            "🔴 *FUTUROS SHORT* | Cap $500M+ | BingX/Bitget\n"
                            "🟡 *ALERTA MERCADO* | BTC/ETH/SOL\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo operar cada señal"
                        )
                    elif text == "/analizar":
                        send_message("🔍 Analizando mercado...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message(
                            "*Cómo operar:*\n\n"
                            "🟢 *SPOT LONG*\n"
                            "• Verificá en tu exchange\n"
                            "• Comprás spot\n"
                            "• Venta en +15% a +25%\n"
                            "• Stop loss en -8%\n\n"
                            "🔵 *PIONEX GRID*\n"
                            "• Grid bot neutral en Pionex\n"
                            "• Ideal cuando el activo está lateral\n"
                            "• Cerrá si gana +5/10% o pierde -2/3%\n\n"
                            "🔴 *FUTUROS SHORT*\n"
                            "• Short en BingX o Bitget\n"
                            "• Máximo 2x-3x apalancamiento\n"
                            "• Stop loss +5% | Objetivo -10/20%\n\n"
                            "🟡 *ALERTA MERCADO*\n"
                            "• BTC/ETH/SOL mueve +3% en 1h\n"
                            "• Altcoins suelen seguir en 1-2hs\n\n"
                            "⚠️ _Empezá con montos pequeños._"
                        )
        except Exception as e:
            print(f"Error updates: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado — versión corregida")
    send_message(
        "✅ *Bot corregido y actualizado*\n\n"
        "Mejoras:\n"
        "• Blacklist robusta — sin shitcoins ni caracteres raros\n"
        "• Cap mínimo spot: $300M\n"
        "• Cap mínimo short: $500M\n"
        "• Short sin depender de Coinglass\n"
        "• Volumen mínimo: $5M\n\n"
        "Escribí /analizar para empezar."
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
