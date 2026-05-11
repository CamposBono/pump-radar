import os,requests,time,schedule,threading
from datetime import datetime

TOKEN=os.environ.get("TELEGRAM_TOKEN")
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID")

PARES=[
    ("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),
    ("ADA/USDT","ADA"),("XRP/USDT","XRP"),("DOT/USDT","DOT"),
    ("LINK/USDT","LINK"),("AVAX/USDT","AVAX"),("MATIC/USDT","MATIC"),
    ("ATOM/USDT","ATOM"),("NEAR/USDT","NEAR"),("LTC/USDT","LTC"),
    ("UNI/USDT","UNI"),("AAVE/USDT","AAVE"),("APT/USDT","APT"),
    ("SUI/USDT","SUI"),("ARB/USDT","ARB"),("OP/USDT","OP"),
    ("INJ/USDT","INJ"),("TIA/USDT","TIA"),("FTM/USDT","FTM"),
    ("ALGO/USDT","ALGO"),("ICP/USDT","ICP"),("FIL/USDT","FIL"),
]

def send(t):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id":CHAT_ID,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def get_ohlc(par,intervalo=15):
    try:
        r=requests.get("https://api.kraken.com/0/public/OHLC",
            params={"pair":par,"interval":intervalo},timeout=10)
        if r.ok:
            data=r.json()
            if not data.get("error"):
                key=list(data["result"].keys())[0]
                return data["result"][key]
    except:pass
    return[]

def analizar(par_kraken,simbolo):
    velas=get_ohlc(par_kraken)
    if len(velas)<16:return None

    closes=[float(v[4])for v in velas[-17:]]
    volumes=[float(v[6])for v in velas[-17:]]

    precio=closes[-1]
    vol_actual=volumes[-1]
    vol_prom=sum(volumes[-10:-1])/9
    vol_ratio=vol_actual/max(vol_prom,0.0001)

    c15=(closes[-1]-closes[-2])/max(closes[-2],0.0001)*100
    c1h=(closes[-1]-closes[-5])/max(closes[-5],0.0001)*100
    c4h=(closes[-1]-closes[-17])/max(closes[-17],0.0001)*100

    ls=0;lsg=[]
    if vol_ratio>2.0 and abs(c15)<0.8:ls+=40;lsg.append("🎯 Acumulación: volumen 2x precio quieto")
    if vol_ratio>1.5 and 0.3<c15<2:ls+=30;lsg.append(f"🌱 Inicio +{c15:.2f}% con volumen")
    if 1<c1h<6 and vol_ratio>1.3:ls+=20;lsg.append(f"📈 +{c1h:.2f}% en 1h con volumen")
    if abs(c4h)<3 and vol_ratio>1.5:ls+=15;lsg.append("😴 Lateral 4h, despertó ahora")

    ss=0;ssg=[]
    if c4h>8:ss+=25;ssg.append(f"📈 Subió {c4h:.1f}% en 4h")
    if c15<-0.8 and c1h>3:ss+=35;ssg.append(f"⚠️ Frena {c15:.2f}% en 15m")
    if c4h>6 and vol_ratio<0.5:ss+=25;ssg.append("📉 Volumen cae en máximos")

    fp=lambda p:(f"${p:,.2f}" if p>100 else f"${p:,.4f}" if p>1 else f"${p:,.6f}")

    if ls>=45:
        return{"sym":simbolo,"precio":fp(precio),"score":ls,"sig":lsg,
               "c15":c15,"c1h":c1h,"vr":vol_ratio,"tipo":"long"}
    if ss>=55:
        return{"sym":simbolo,"precio":fp(precio),"score":ss,"sig":ssg,
               "c15":c15,"c1h":c1h,"vr":vol_ratio,"tipo":"short"}
    return None

def run():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando {len(PARES)} pares Kraken...")
    longs,shorts=[],[]
    for par,sym in PARES:
        r=analizar(par,sym)
        if r:
            if r["tipo"]=="long":longs.append(r)
            else:shorts.append(r)
        time.sleep(0.5)

    longs.sort(key=lambda x:x["score"],reverse=True)
    shorts.sort(key=lambda x:x["score"],reverse=True)
    tl=longs[:2];ts=shorts[:1]

    if not tl and not ts:
        print("Sin señales");return

    hora=datetime.now().strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora}*\n_Datos 15m | Kraken_\n\n"

    if tl:
        msg+="🟢 *LONG — Spot o Futuros*\n\n"
        for r in tl:
            msg+=f"▶️ *{r['sym']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['c15']:+.2f}%` | 1h: `{r['c1h']:+.2f}%`\n"
            msg+=f"Volumen: `{r['vr']:.1f}x` el promedio\n"
            msg+=f"🎯 Obj: +10/20% | Stop: -5%\n"
            msg+=f"_{', '.join(r['sig'])}_\n\n"

    if ts:
        msg+="🔴 *SHORT — Futuros*\n\n"
        for r in ts:
            msg+=f"🔻 *{r['sym']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['c15']:+.2f}%` | 1h: `{r['c1h']:+.2f}%`\n"
            msg+=f"Volumen: `{r['vr']:.1f}x` el promedio\n"
            msg+=f"⚠️ Máx 3x | Stop: +3%\n"
            msg+=f"_{', '.join(r['sig'])}_\n\n"

    msg+="⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)
    print(f"Enviado: {len(tl)} long {len(ts)} short")

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"]
                    t=(u.get("message")or{}).get("text")or""
                    if t=="/start":
                        send("👋 *Pump Radar activo*\nDatos 15m via Kraken\n\n/analizar — análisis ahora\n/ayuda — cómo operar")
                    elif t=="/analizar":
                        send("🔍 Analizando 24 pares en 15m...");run()
                    elif t=="/ayuda":
                        send("*Cómo operar:*\n\n🟢 *LONG*\nObj: +10% a +20%\nStop: -5%\n\n🔴 *SHORT*\nSolo futuros — máx 3x\nStop: +3% | Obj: -10/15%\n\n_Verificá siempre en tu exchange antes de entrar._")
        except Exception as e:
            print(f"Err:{e}")
        time.sleep(2)

send("✅ *Pump Radar — Kraken 15m activo*\nEscribí /analizar para empezar.")
schedule.every(4).hours.do(run)
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
