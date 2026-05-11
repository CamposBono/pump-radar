import os,requests,time,schedule,threading
from datetime import datetime

TOKEN=os.environ.get("TELEGRAM_TOKEN")
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID")

SKIP={"usdt","usdc","busd","dai","wbtc","weth","steth","tusd","usdp","usdd","paxg","xaut","fdusd","usde","pyusd"}
SKIP_W=["usd","tether","wrapped","staked","pegged"]

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",json={"chat_id":CHAT_ID,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def ok(c):
    s=(c.get("symbol")or"").lower()
    n=(c.get("name")or"").lower()
    if s in SKIP:return False
    for w in SKIP_W:
        if w in n:return False
    try:n.encode("ascii")
    except:return False
    return(c.get("total_volume")or 0)>5000000 and(c.get("market_cap")or 0)>500000000

def get_data():
    r=[]
    for p in[1,2,3]:
        try:
            x=requests.get("https://api.coingecko.com/api/v3/coins/markets",params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":p,"price_change_percentage":"1h,24h,7d"},timeout=15)
            if x.ok:r.extend(x.json())
            time.sleep(2)
        except:pass
    return r

def fp(p):
    if not p:return"$0"
    if p>100:return f"${p:,.2f}"
    if p>1:return f"${p:,.3f}"
    if p>0.01:return f"${p:,.5f}"
    return f"${p:,.8f}"

def run():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando...")
    data=get_data()
    if not data:return
    long_sig=[]
    short_sig=[]

    for c in data:
        if not ok(c):continue
        m=c.get("market_cap")or 0
        v=c.get("total_volume")or 0
        h1=c.get("price_change_percentage_1h_in_currency")or 0
        h24=c.get("price_change_percentage_24h")or 0
        h7=c.get("price_change_percentage_7d_in_currency")or 0
        vr=v/max(m,1)
        sym=(c.get("symbol")or"").upper()
        name=c.get("name")or""
        price=c.get("current_price")or 0
        mcap=f"${m/1e9:.1f}B" if m>=1e9 else f"${m/1e6:.0f}M"

        # SEÑAL LONG — volumen sube, precio quieto
        ls=0;lsg=[]
        if vr>0.3 and abs(h1)<3:ls+=40;lsg.append("🎯 Acumulación detectada")
        if abs(h7)<8 and vr>0.15 and h24>3:ls+=25;lsg.append("😴 Dormida, despertó hoy")
        if 2<h1<8 and vr>0.1:ls+=20;lsg.append(f"🌱 Inicio +{h1:.1f}% en 1h")
        if 5<h24<20 and vr>0.08:ls+=15;lsg.append(f"📈 +{h24:.1f}% en 24h")
        if ls>=45:long_sig.append((ls,sym,name,price,mcap,h1,h24,lsg))

        # SEÑAL SHORT — subida fuerte que se frena
        ss=0;ssg=[]
        if h24>20:ss+=25;ssg.append(f"📈 Subió {h24:.1f}% en 24h")
        if h1<-1 and h24>15:ss+=35;ssg.append(f"⚠️ Se frena: {h1:.2f}% en 1h")
        if h24>15 and vr<0.06:ss+=25;ssg.append("📉 Volumen cayendo en máximos")
        if ss>=55:short_sig.append((ss,sym,name,price,mcap,h1,h24,ssg))

    long_sig.sort(key=lambda x:x[0],reverse=True)
    short_sig.sort(key=lambda x:x[0],reverse=True)
    top_l=long_sig[:2]
    top_s=short_sig[:1]

    if not top_l and not top_s:
        print("Sin señales suficientes");return

    hora=datetime.now().strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora}*\n_Cap mín $500M | Sin stables_\n\n"

    if top_l:
        msg+="🟢 *LONG — Spot o Futuros*\n\n"
        for sc,sym,name,price,mcap,h1,h24,sg in top_l:
            msg+=f"▶️ *{sym}* ({name})\n"
            msg+=f"Cap: `{mcap}` | Score: `{sc}/100`\n"
            msg+=f"Precio: `{fp(price)}`\n"
            msg+=f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg+=f"🎯 Obj: +15/25% | Stop: -8%\n"
            msg+=f"_{', '.join(sg)}_\n\n"

    if top_s:
        msg+="🔴 *SHORT — Futuros*\n\n"
        for sc,sym,name,price,mcap,h1,h24,sg in top_s:
            msg+=f"🔻 *{sym}* ({name})\n"
            msg+=f"Cap: `{mcap}` | Score: `{sc}/100`\n"
            msg+=f"Precio: `{fp(price)}`\n"
            msg+=f"1h: `{h1:+.2f}%` | 24h: `{h24:+.2f}%`\n"
            msg+=f"⚠️ Máx 3x | Stop: +5%\n"
            msg+=f"_{', '.join(sg)}_\n\n"

    msg+="⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)
    print(f"Enviado: {len(top_l)} long, {len(top_s)} short")

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"]
                    t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋 *Pump Radar activo*\n\n🟢 LONG — señales tempranas\n🔴 SHORT — correcciones\n\n/analizar — análisis ahora\n/ayuda — cómo operar")
                    elif t=="/analizar":send("🔍 Analizando mercado...");run()
                    elif t=="/ayuda":send("*Cómo operar:*\n\n🟢 *LONG*\nComprás spot o abrís long en futuros\nObjetivo: +15% a +25%\nStop loss: -8%\n\n🔴 *SHORT*\nSolo futuros — máximo 3x\nStop loss: +5%\nObjetivo: -10% a -20%\n\n_Verificá siempre en tu exchange antes de entrar._")
        except Exception as e:print(f"Err:{e}")
        time.sleep(2)

send("✅ *Pump Radar activo*\nEscribí /analizar para empezar.")
schedule.every(4).hours.do(run)
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
