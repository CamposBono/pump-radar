import os,requests,time,schedule,threading
from datetime import datetime

TOKEN=os.environ.get("TELEGRAM_TOKEN")
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID")

# Top pares de Binance con cap alto
PARES=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT",
       "DOTUSDT","LINKUSDT","MATICUSDT","UNIUSDT","ATOMUSDT","LTCUSDT","NEARUSDT",
       "AAVEUSDT","INJUSDT","ARBUSDT","OPUSDT","SUIUSDT","APTUSDT","SEIUSDT",
       "TIAUSDT","STXUSDT","RUNEUSDT","LDOUSDT","MKRUSDT","SNXUSDT","COMPUSDT",
       "GALAUSDT","SANDUSDT","MANAUSDT","FTMUSDT","ALGOUSDT","ICPUSDT","FILUSDT",
       "EGLDUSDT","FLOWUSDT","XTZUSDT","EOSUSDT","ZECUSDT","DASHUSDT","NEOUSDT"]

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id":CHAT_ID,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def get_velas(par,intervalo="15m",limit=20):
    try:
        r=requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol":par,"interval":intervalo,"limit":limit},timeout=10)
        if r.ok:return r.json()
    except:pass
    return[]

def analizar_par(par):
    velas=get_velas(par)
    if len(velas)<15:return None

    closes=[float(v[4])for v in velas]
    volumes=[float(v[5])for v in velas]
    highs=[float(v[2])for v in velas]
    lows=[float(v[3])for v in velas]

    precio=closes[-1]
    vol_actual=volumes[-1]
    vol_promedio=sum(volumes[-10:-1])/9
    vol_ratio=vol_actual/max(vol_promedio,0.001)

    cambio_15m=(closes[-1]-closes[-2])/max(closes[-2],0.001)*100
    cambio_1h=(closes[-1]-closes[-5])/max(closes[-5],0.001)*100
    cambio_4h=(closes[-1]-closes[-17])/max(closes[-17],0.001)*100 if len(closes)>=17 else 0

    score=0
    signals=[]
    tipo=None

    # LONG — acumulacion temprana
    if vol_ratio>2.5 and abs(cambio_15m)<0.5:
        score+=40;signals.append("🎯 Volumen 2.5x con precio quieto")
    if vol_ratio>1.8 and abs(cambio_15m)<1:
        score+=20;signals.append("📊 Volumen elevado")
    if 0.3<cambio_15m<2 and vol_ratio>1.5:
        score+=25;signals.append(f"🌱 Inicio +{cambio_15m:.2f}% en 15m")
    if 1<cambio_1h<5 and vol_ratio>1.3:
        score+=15;signals.append(f"📈 +{cambio_1h:.2f}% en 1h")
    if score>=45:tipo="long"

    # SHORT — subida que se frena
    ss=0;ssig=[]
    if cambio_4h>8:ss+=25;ssig.append(f"📈 Subió {cambio_4h:.1f}% en 4h")
    if cambio_15m<-0.5 and cambio_1h>3:ss+=35;ssig.append(f"⚠️ Frena: {cambio_15m:.2f}% en 15m")
    if cambio_4h>5 and vol_ratio<0.6:ss+=25;ssig.append("📉 Volumen cae en máximos")
    if ss>=55:
        score=ss;signals=ssig;tipo="short"

    if not tipo:return None

    fp=lambda p:(f"${p:,.2f}" if p>100 else f"${p:,.4f}" if p>1 else f"${p:,.6f}")
    return{"par":par.replace("USDT",""),"precio":fp(precio),"score":score,
           "signals":signals,"tipo":tipo,"cambio_15m":cambio_15m,
           "cambio_1h":cambio_1h,"vol_ratio":vol_ratio}

def run():
    print(f"[{datetime.now().strftime('%H:%M')}] Analizando {len(PARES)} pares...")
    longs,shorts=[],[]
    for par in PARES:
        r=analizar_par(par)
        if r:
            if r["tipo"]=="long":longs.append(r)
            else:shorts.append(r)
        time.sleep(0.3)

    longs.sort(key=lambda x:x["score"],reverse=True)
    shorts.sort(key=lambda x:x["score"],reverse=True)
    top_l=longs[:2]
    top_s=shorts[:1]

    if not top_l and not top_s:
        print("Sin señales");return

    hora=datetime.now().strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora}*\n_Datos 15m | Binance_\n\n"

    if top_l:
        msg+="🟢 *LONG — Spot o Futuros*\n\n"
        for r in top_l:
            msg+=f"▶️ *{r['par']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['cambio_15m']:+.2f}%` | 1h: `{r['cambio_1h']:+.2f}%`\n"
            msg+=f"Vol: `{r['vol_ratio']:.1f}x` el promedio\n"
            msg+=f"🎯 Obj: +10/20% | Stop: -5%\n"
            msg+=f"_{', '.join(r['signals'])}_\n\n"

    if top_s:
        msg+="🔴 *SHORT — Futuros*\n\n"
        for r in top_s:
            msg+=f"🔻 *{r['par']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['cambio_15m']:+.2f}%` | 1h: `{r['cambio_1h']:+.2f}%`\n"
            msg+=f"Vol: `{r['vol_ratio']:.1f}x` el promedio\n"
            msg+=f"⚠️ Máx 3x | Stop: +3%\n"
            msg+=f"_{', '.join(r['signals'])}_\n\n"

    msg+="⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)
    print(f"Enviado: {len(top_l)} long {len(top_s)} short")

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
                    if t=="/start":send("👋 *Pump Radar activo*\nDatos de 15m via Binance\n\n/analizar — análisis ahora\n/ayuda — cómo operar")
                    elif t=="/analizar":send("🔍 Analizando...");run()
                    elif t=="/ayuda":send("*Cómo operar:*\n\n🟢 *LONG*\nObj: +10% a +20%\nStop loss: -5%\n\n🔴 *SHORT*\nSolo futuros — máx 3x\nStop: +3% | Obj: -10/15%\n\n_Verificá siempre antes de entrar._")
        except Exception as e:print(f"Err:{e}")
        time.sleep(2)

send("✅ *Pump Radar — Datos 15m Binance*\nEscribí /analizar para empezar.")
schedule.every(4).hours.do(run)
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
