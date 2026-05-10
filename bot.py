import os
import requests
import time
import schedule
import threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MIN_MARKET_CAP_SPOT = 100_000_000
MIN_MARKET_CAP_GRID = 5_000_000_000
MIN_MARKET_CAP_SHORT = 200_000_000
MIN_VOLUME = 2_000_000

# Filtro de stablecoins y tokens no deseados
STABLECOINS = {
    "usdt", "usdc", "busd", "dai", "tusd", "usdp", "usdd", "gusd", "frax",
    "lusd", "susd", "cusd", "husd", "eurs", "rusd", "pyusd", "fdusd",
    "usde", "usdx", "crvusd", "gho", "mkr", "mim", "usdn", "ousd",
    "alusd", "dola", "bean", "usd+", "tbtc", "wbtc", "steth", "weth",
    "cbeth", "reth", "sfrxeth", "weeth", "ezeth", "rseth", "paxg", "xaut"
}

def is_valid_coin(coin):
    symbol = coin.get("symbol", "").lower()
    name = coin.get("name", "").lower()
    mcap = coin.get("market_cap") or 0
    volume = coin.get("total_volume") or 0

    # Filtrar stablecoins
    if symbol in STABLECOINS:
        return False

    # Filtrar por nombre (wrapped tokens, stables)
    skip_words = ["usd", "tether", "wrapped", "staked", "bridged", "liquid"]
    for word in skip_words:
        if word in name and symbol not in ["bud", "studio"]:
            return False

    # Filtrar volumen mínimo
    if volume < MIN_VOLUME:
        return False

    return True

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
        r = requests.get("https://open-api.coinglass.com/public/v2/funding", timeout=10)
        if r.ok:
            rates = {}
            for item in r.json().get("data", []):
                symbol = item.get("symbol", "").upper()
                rate = item.get("fundingRate", 0)
                rates[symbol] = float(rate) if rate else 0
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
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    coins = get_coins()
    funding_rates = get_funding_rates()

    if not coins:
        print("Sin datos")
        return

    spot_long = []
    pionex_grid = []
    futures_short = []
    market_alerts = []

    # Alerta mercado general
    for coin in coins:
        sym = coin.get("symbol", "").upper()
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        if sym in ["BTC", "ETH", "SOL"] and h1 > 3:
            market_alerts.append((sym, h1, coin.get("current_price", 0)))

    for coin in coins:
        if not is_valid_coin(coin):
            continue

        mcap = coin.get("market_cap") or 0
        volume = coin.get("total_volume") or 0
        h1 = coin.get("price_change_percentage_1h_in_currency") or 0
        h24 = coin.get("price_change_percentage_24h") or 0
        h7d = coin.get("price_change_percentage_7d_in_currency") or 0
        symbol = coin.get("symbol", "").upper()
        vol_ratio = volume / max(mcap, 1)
        funding = funding_rates.get(symbol, 0)

        # SPOT LONG — cap mín $100M, no stables
        if mcap >= MIN_MARKET_CAP_SPOT and mcap < MIN_MARKET_CAP_GRID and h24 < 25:
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

        # PIONEX GRID — solo large caps reales +$5B
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

        # FUTUROS SHORT — cap mín $200M
        if mcap >= MIN_MARKET_CAP_SHORT:
            short_score = 0
            short_signals = []

            if h24 > 15:
                short_score += 20
                short_signals.append(f"📈 Subió {h24:.1f}% en 24h")

            if funding > 0.001:
                short_score += 35
                short_signals.append(f"💰 Funding alto: {funding*100:.3f}%")
            elif funding > 0.0005:
                short_score += 15
                short_signals.append(f"💰 Funding elevado: {funding*100:.3f}%")

            if h1 < 1 and h24 > 10:
                short_score += 25
                short_signals.append("⚠️ Precio estancado tras subida")

            if h24 > 20 and vol_ratio < 0.1:
                short_score += 20
                short_signals.append("📉 Volumen bajando en máximos")

            if short_score >= 45:
                futures_short.append((short_score, coin, short_signals))

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

    if market_alerts:
        msg += "🟡 *ALERTA DE MERCADO*\n"
        for sym, h1, price in market_alerts:
            msg += f"• *{sym}* +`{h1:.1f}%` en 1h — altcoins pueden seguir\n"
        msg += "\n"

    if top_spot:
        msg += "🟢 *SPOT LONG — BingX / Bitget / Nexo*\n"
        msg += "_Señales tempranas | Cap $100M-$5B_\n\n"
        for score, coin, signals in top_spot:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"▶️ *{sym}* ({name}) | Cap: `{fmt_mcap(mcap)}`\n"
            msg += f"Score: *{score}/100* | Precio: `{fmt_price(price)}`\n"
            msg += f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"🎯 Objetivo: +15/25% | Stop: -8%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    if top_grid:
        msg += "🔵 *PIONEX BOT — Grid neutral*\n"
        msg += "_Large caps laterales | Cap +$5B_\n\n"
        for score, coin, signals in top_grid:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h24 = coin.get("price_change_percentage_24h") or 0
            mcap = coin.get("market_cap") or 0
            msg += f"↔️ *{sym}* ({name}) | Cap: `{fmt_mcap(mcap)}`\n"
            msg += f"Score: `{score}/100` | Precio: `{fmt_price(price)}`\n"
            msg += f"Rango 24h: `{h24:+.2f}%`\n"
            msg += f"🤖 Activar grid bot neutral en Pionex\n"
            msg += f"_{', '.join(signals)}_\n\n"

    if top_short:
        msg += "🔴 *FUTUROS SHORT — BingX / Bitget*\n"
        msg += "_Posible corrección | Cap +$200M_\n\n"
        for score, coin, signals in top_short:
            sym = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            h1 = coin.get("price_change_percentage_1h_in_currency") or 0
            h24 = coin.get("price_change_percentage_24h") or 0
            msg += f"🔻 *{sym}* ({name})\n"
            msg += f"Score: *{score}/100* | Precio: `{fmt_price(price)}`\n"
            msg += f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg += f"⚠️ Máx 3x | Stop: +5%\n"
            msg += f"_{', '.join(signals)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Enviado: {len(top_spot)} spot, {len(top_grid)} grid, {len(top_short)} short")

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
                            "👋 *Pump Radar — 4 módulos activos*\n\n"
                            "🟢 *SPOT LONG* — señales tempranas\n"
                            "_BingX / Bitget / Nexo | Cap $100M+_\n\n"
                            "🔵 *PIONEX GRID* — mercado lateral\n"
                            "_Large caps +$5B | Bot neutral_\n\n"
                            "🔴 *FUTUROS SHORT* — corrección\n"
                            "_BingX / Bitget | Máx 3x_\n\n"
                            "🟡 *ALERTA MERCADO* — BTC/ETH/SOL\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo operar"
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
                            "• Abrís grid bot neutral\n"
                            "• Configurás el rango detectado\n"
                            "• Opera solo — ideal en lateral\n\n"
                            "🔴 *FUTUROS SHORT*\n"
                            "• Short en BingX o Bitget\n"
                            "• Máximo 2x-3x apalancamiento\n"
                            "• Stop loss +5%\n"
                            "• Objetivo -10% a -20%\n\n"
                            "🟡 *ALERTA MERCADO*\n"
                            "• BTC/ETH/SOL sube +3% en 1h\n"
                            "• Altcoins suelen seguir en 1-2hs\n\n"
                            "⚠️ _Empezá con montos pequeños._"
                        )
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado — sin stables, sin shitcoins")
    send_message(
        "✅ *Bot actualizado*\n\n"
        "Filtros activos:\n"
        "• Sin stablecoins\n"
        "• Sin tokens dudosos\n"
        "• Cap mín $100M spot\n"
        "• Cap mín $5B grid\n"
        "• Cap mín $200M short\n\n"
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
