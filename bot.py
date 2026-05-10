import os
import requests
import time
from datetime import datetime
from config import MIN_CAP_SPOT, MIN_CAP_GRID, MIN_CAP_SHORT, MIN_VOL, MAX_24H, BLACKLIST, BAD_WORDS

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_message(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Error mensaje: {e}")

def is_valid(coin):
    sym = (coin.get("symbol") or "").lower()
    name = (coin.get("name") or "").lower()
    if sym in BLACKLIST:
        return False
    for w in BAD_WORDS:
        if w in name:
            return False
    try:
        name.encode('ascii')
    except UnicodeEncodeError:
        return False
    return (coin.get("total_volume") or 0) >= MIN_VOL

def get_coins():
    coins = []
    for page in [1, 2, 3]:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":page,"price_change_percentage":"1h,24h,7d"},
                timeout=15
            )
            if r.ok:
                coins.extend(r.json())
            time.sleep(2)
        except:
            pass
    return coins

def fmt(price):
    if not price: return "$0"
    if price > 100: return f"${price:,.2f}"
    if price > 1: return f"${price:,.3f}"
    if price > 0.01: return f"${price:,.5f}"
    return f"${price:,.8f}"

def fmt_cap(m):
    if m >= 1e9: return f"${m/1e9:.1f}B"
    return f"${m/1e6:.0f}M"

def analyze_market():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    coins = get_coins()
    if not coins:
        return

    spot, grid, short, alerts = [], [], [], []

    for c in coins:
        sym = (c.get("symbol") or "").upper()
        h1 = c.get("price_change_percentage_1h_in_currency") or 0
        if sym in ["BTC","ETH","SOL"] and abs(h1) > 3:
            d = "subió" if h1 > 0 else "cayó"
            alerts.append((sym, h1, c.get("current_price",0), d))

    for c in coins:
        if not is_valid(c): continue
        m = c.get("market_cap") or 0
        v = c.get("total_volume") or 0
        h1 = c.get("price_change_percentage_1h_in_currency") or 0
        h24 = c.get("price_change_percentage_24h") or 0
        h7 = c.get("price_change_percentage_7d_in_currency") or 0
        vr = v / max(m, 1)

        if MIN_CAP_SPOT <= m < MIN_CAP_GRID and h24 < MAX_24H:
            s, sg = 0, []
            if vr > 0.3 and abs(h1) < 3: s += 40; sg.append("🎯 Volumen alto, precio quieto")
            if vr > 0.5 and abs(h1) < 5: s += 15; sg.append("⚡ Volumen extremo")
            if abs(h7) < 8 and vr > 0.2 and h24 > 3: s += 20; sg.append("😴 Dormida 7d, activa hoy")
            if 2 < h1 < 8 and vr > 0.15: s += 20; sg.append(f"🌱 Inicio +{h1:.1f}% en 1h")
            if 5 < h24 < 20 and vr > 0.1: s += 15; sg.append(f"📈 +{h24:.1f}% en 24h")
            if s >= 40: spot.append((s, c, sg))

        if m >= MIN_CAP_GRID:
            s, sg = 0, []
            r = abs(h24)
            if r < 5 and vr > 0.05: s += 40; sg.append(f"↔️ Lateral {r:.1f}% 24h")
            if r < 3: s += 20; sg.append("🎯 Rango ajustado")
            if abs(h7) < 15 and vr > 0.03: s += 20; sg.append("📊 Consolidando 7d")
            if vr > 0.05: s += 10; sg.append("✅ Volumen sostenido")
            if s >= 50: grid.append((s, c, sg))

        if m >= MIN_CAP_SHORT:
            s, sg = 0, []
            if h24 > 20: s += 25; sg.append(f"📈 Subió {h24:.1f}% en 24h")
            elif h24 > 15: s += 15; sg.append(f"📈 Subió {h24:.1f}% en 24h")
            if h1 < 0 and h24 > 15: s += 30; sg.append(f"⚠️ Frena en 1h: {h1:.2f}%")
            if h24 > 15 and vr < 0.08: s += 25; sg.append("📉 Volumen se agota")
            if h24 > 10 and vr < 0.05: s += 20; sg.append("💨 Pump débil")
            if s >= 50: short.append((s, c, sg))

    spot.sort(key=lambda x: x[0], reverse=True)
    grid.sort(key=lambda x: x[0], reverse=True)
    short.sort(key=lambda x: x[0], reverse=True)

    ts, tg, th = spot[:3], grid[:2], short[:2]
    if not ts and not tg and not th and not alerts:
        print("Sin señales")
        return

    hora = datetime.now().strftime('%H:%M')
    msg = f"🔍 *PUMP RADAR — {hora}*\n\n"

    if alerts:
        msg += "🟡 *ALERTA MERCADO*\n"
        for sym, h1, p, d in alerts:
            msg += f"• *{sym}* {d} `{h1:+.1f}%` en 1h → `{fmt(p)}`\n"
        msg += "\n"

    if ts:
        msg += "🟢 *SPOT LONG — BingX/Bitget/Nexo*\n_Cap $300M-$5B_\n\n"
        for s, c, sg in ts:
            sym = (c.get("symbol") or "").upper()
            msg += f"▶️ *{sym}* ({c.get('name')}) | `{fmt_cap(c.get('market_cap',0))}`\n"
            msg += f"Score: *{s}/100* | `{fmt(c.get('current_price',0))}`\n"
            msg += f"1h: `{(c.get('price_change_percentage_1h_in_currency') or 0):+.2f}%` | 24h: `{(c.get('price_change_percentage_24h') or 0):+.2f}%`\n"
            msg += f"🎯 Objetivo: +15/25% | Stop: -8%\n_{', '.join(sg)}_\n\n"

    if tg:
        msg += "🔵 *PIONEX GRID — Bot neutral*\n_Cap +$5B_\n\n"
        for s, c, sg in tg:
            sym = (c.get("symbol") or "").upper()
            msg += f"↔️ *{sym}* ({c.get('name')}) | `{fmt_cap(c.get('market_cap',0))}`\n"
            msg += f"Score: `{s}/100` | `{fmt(c.get('current_price',0))}`\n"
            msg += f"Rango 24h: `{(c.get('price_change_percentage_24h') or 0):+.2f}%`\n"
            msg += f"🤖 Activar grid neutral en Pionex\n_{', '.join(sg)}_\n\n"

    if th:
        msg += "🔴 *FUTUROS SHORT — BingX/Bitget*\n_Cap +$500M_\n\n"
        for s, c, sg in th:
            sym = (c.get("symbol") or "").upper()
            msg += f"🔻 *{sym}* ({c.get('name')})\n"
            msg += f"Score: *{s}/100* | `{fmt(c.get('current_price',0))}`\n"
            msg += f"1h: `{(c.get('price_change_percentage_1h_in_currency') or 0):+.2f}%` | 24h: `{(c.get('price_change_percentage_24h') or 0):+.2f}%`\n"
            msg += f"⚠️ Máx 3x | Stop: +5% | Obj: -10/20%\n_{', '.join(sg)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send_message(msg)
    print(f"Listo: {len(ts)} spot, {len(tg)} grid, {len(th)} short")
