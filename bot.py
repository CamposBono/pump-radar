import os, requests, time, schedule, threading
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SKIP = {"usdt","usdc","busd","dai","wbtc","weth","steth","tusd","usdp","usdd","paxg","xaut"}
SKIP_WORDS = ["usd","tether","wrapped","staked","binancelife"]

def send(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id":CHAT_ID,"text":text,"parse_mode":"Markdown"},timeout=10)
    except: pass

def valid(c):
    s = (c.get("symbol") or "").lower()
    n = (c.get("name") or "").lower()
    if s in SKIP: return False
    for w in SKIP_WORDS:
        if w in n: return False
    try: n.encode("ascii")
    except: return False
    return (c.get("total_volume") or 0) > 3000000

def coins():
    r = []
    for p in [1,2,3]:
        try:
            x = requests.get("https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,
                        "page":p,"price_change_percentage":"1h,24h,7d"},timeout=15)
            if x.ok: r.extend(x.json())
            time.sleep(2)
        except: pass
    return r

def fp(p):
    if not p: return "$0"
    if p>100: return f"${p:,.2f}"
    if p>1: return f"${p:,.3f}"
    if p>0.01: return f"${p:,.5f}"
    return f"${p:,.8f}"

def fc(m):
    return f"${m/1e9:.1f}B" if m>=1e9 else f"${m/1e6:.0f}M"

def analyze():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    data = coins()
    if not data: return
    spot, grid, short, alerts = [], [], [], []

    for c in data:
        sym = (c.get("symbol") or "").upper()
        h1 = c.get("price_change_percentage_1h_in_currency") or 0
        if sym in ["BTC","ETH","SOL"] and abs(h1) > 3:
            alerts.append((sym, h1, c.get("current_price",0)))

    for c in data:
        if not valid(c): continue
        m = c.get("market_cap") or 0
        v = c.get("total_volume") or 0
        h1 = c.get("price_change_percentage_1h_in_currency") or 0
        h24 = c.get("price_change_percentage_24h") or 0
        h7 = c.get("price_change_percentage_7d_in_currency") or 0
        vr = v / max(m,1)

        if 300e6 <= m < 5e9 and h24 < 25:
            s,sg = 0,[]
            if vr>0.3 and abs(h1)<3: s+=40; sg.append("🎯 Volumen alto precio quieto")
            if vr>0.5 and abs(h1)<5: s+=15; sg.append("⚡ Volumen extremo")
            if abs(h7)<8 and vr>0.2 and h24>3: s+=20; sg.append("😴 Dormida, despertó hoy")
            if 2<h1<8 and vr>0.15: s+=20; sg.append(f"🌱 Inicio +{h1:.1f}% 1h")
            if 5<h24<20 and vr>0.1: s+=15; sg.append(f"📈 +{h24:.1f}% 24h")
            if s>=40: spot.append((s,c,sg))

        if m >= 5e9:
            s,sg = 0,[]
            r = abs(h24)
            if r<5 and vr>0.05: s+=40; sg.append(f"↔️ Lateral {r:.1f}% 24h")
            if r<3: s+=20; sg.append("🎯 Rango ajustado")
            if abs(h7)<15 and vr>0.03: s+=20; sg.append("📊 Consolidando 7d")
            if vr>0.05: s+=10; sg.append("✅ Volumen sostenido")
            if s>=50: grid.append((s,c,sg))

        if m >= 500e6:
            s,sg = 0,[]
            if h24>20: s+=25; sg.append(f"📈 Subió {h24:.1f}% 24h")
            elif h24>15: s+=15; sg.append(f"📈 Subió {h24:.1f}% 24h")
            if h1<0 and h24>15: s+=30; sg.append(f"⚠️ Frena 1h: {h1:.2f}%")
            if h24>15 and vr<0.08: s+=25; sg.append("📉 Volumen se agota")
            if s>=50: short.append((s,c,sg))

    spot.sort(key=lambda x:x[0],reverse=True)
    grid.sort(key=lambda x:x[0],reverse=True)
    short.sort(key=lambda x:x[0],reverse=True)
    ts,tg,th = spot[:3],grid[:2],short[:2]

    if not ts and not tg and not th and not alerts:
        print("Sin señales"); return

    hora = datetime.now().strftime("%H:%M")
    msg = f"🔍 *PUMP RADAR — {hora}*\n\n"

    if alerts:
        msg += "🟡 *ALERTA MERCADO*\n"
        for sym,h1,p in alerts:
            d = "subió" if h1>0 else "cayó"
            msg += f"• *{sym}* {d} `{h1:+.1f}%` en 1h\n"
        msg += "\n"

    if ts:
        msg += "🟢 *SPOT LONG — BingX/Bitget/Nexo*\n\n"
        for s,c,sg in ts:
            sym=(c.get("symbol") or "").upper()
            h1=c.get("price_change_percentage_1h_in_currency") or 0
            h24=c.get("price_change_percentage_24h") or 0
            msg += f"▶️ *{sym}* | Cap:{fc(c.get('market_cap',0))} | Score:{s}\n"
            msg += f"`{fp(c.get('current_price',0))}` | 1h:`{h1:+.2f}%` 24h:`{h24:+.2f}%`\n"
            msg += f"🎯 Obj:+15/25% Stop:-8%\n_{', '.join(sg)}_\n\n"

    if tg:
        msg += "🔵 *PIONEX GRID — Bot neutral*\n\n"
        for s,c,sg in tg:
            sym=(c.get("symbol") or "").upper()
            h24=c.get("price_change_percentage_24h") or 0
            msg += f"↔️ *{sym}* | Cap:{fc(c.get('market_cap',0))} | Score:{s}\n"
            msg += f"`{fp(c.get('current_price',0))}` | Rango 24h:`{h24:+.2f}%`\n"
            msg += f"🤖 Grid neutral en Pionex\n_{', '.join(sg)}_\n\n"

    if th:
        msg += "🔴 *FUTUROS SHORT — BingX/Bitget*\n\n"
        for s,c,sg in th:
            sym=(c.get("symbol") or "").upper()
            h1=c.get("price_change_percentage_1h_in_currency") or 0
            h24=c.get("price_change_percentage_24h") or 0
            msg += f"🔻 *{sym}* | Score:{s}\n"
            msg += f"`{fp(c.get('current_price',0))}` | 1h:`{h1:+.2f}%` 24h:`{h24:+.2f}%`\n"
            msg += f"⚠️ Máx 3x | Stop:+5% Obj:-10/20%\n_{', '.join(sg)}_\n\n"

    msg += "⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)
    print(f"Listo: {len(ts)} spot {len(tg)} grid {len(th)} short")

def updates():
    last = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last = u["update_id"]
                    t = (u.get("message") or {}).get("text") or ""
                    if t=="/start": send("👋 *Pump Radar activo*\n/analizar — análisis ahora\n/ayuda — cómo operar")
                    elif t=="/analizar": send("🔍 Analizando..."); analyze()
                    elif t=="/ayuda": send("🟢 *SPOT*: obj +15/25% stop -8%\n🔵 *GRID*: bot neutral Pionex\n🔴 *SHORT*: máx 3x stop +5%\n🟡 *ALERTA*: BTC/ETH/SOL +3% en 1h")
        except Exception as e: print(f"Error:{e}")
        time.sleep(2)

send("✅ *Pump Radar iniciado*\nEscribí /analizar para empezar.")
schedule.every(1).hours.do(analyze)
analyze()
threading.Thread(target=updates,daemon=True).start()
while True: schedule.run_pending(); time.sleep(30)
