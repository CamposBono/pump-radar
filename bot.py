import os,requests,time,schedule,threading
from datetime import datetime
import pytz

TOKEN=os.environ.get("TELEGRAM_TOKEN")
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID")
ARG=pytz.timezone("America/Argentina/Buenos_Aires")

PARES=[
    ("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),
    ("XRP/USDT","XRP"),("ADA/USDT","ADA"),("DOT/USDT","DOT"),
    ("LINK/USDT","LINK"),("AVAX/USDT","AVAX"),("ATOM/USDT","ATOM"),
    ("NEAR/USDT","NEAR"),("LTC/USDT","LTC"),("UNI/USDT","UNI"),
    ("AAVE/USDT","AAVE"),("APT/USDT","APT"),("SUI/USDT","SUI"),
    ("ARB/USDT","ARB"),("OP/USDT","OP"),("INJ/USDT","INJ"),
    ("FTM/USDT","FTM"),("ALGO/USDT","ALGO"),("ICP/USDT","ICP"),
    ("FIL/USDT","FIL"),("XLM/USDT","XLM"),("BCH/USDT","BCH"),
]

señales_hoy={"long":0,"short":0,"fecha":""}

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
            d=r.json()
            if not d.get("error"):
                k=list(d["result"].keys())[0]
                return d["result"][k]
    except:pass
    return[]

def detectar_bos(highs,lows):
    """Break of Structure — precio rompe máximo reciente"""
    if len(highs)<10:return False,False
    max_previo=max(highs[-10:-2])
    min_previo=min(lows[-10:-2])
    bos_long=highs[-1]>max_previo
    bos_short=lows[-1]<min_previo
    return bos_long,bos_short

def detectar_choch(closes):
    """Change of Character — cambio de estructura"""
    if len(closes)<8:return False,False
    # CHoCH alcista: después de bajar, hace HH (higher high)
    choch_long=closes[-1]>closes[-3] and closes[-3]>closes[-5] and closes[-5]<closes[-7]
    # CHoCH bajista: después de subir, hace LL (lower low)
    choch_short=closes[-1]<closes[-3] and closes[-3]<closes[-5] and closes[-5]>closes[-7]
    return choch_long,choch_short

def detectar_fvg(highs,lows):
    """Fair Value Gap — gap entre velas"""
    if len(highs)<3:return False,False
    fvg_long=lows[-1]>highs[-3]   # gap alcista
    fvg_short=highs[-1]<lows[-3]  # gap bajista
    return fvg_long,fvg_short

def analizar(par_kraken,simbolo):
    velas=get_ohlc(par_kraken)
    if len(velas)<20:return None

    opens=[float(v[1])for v in velas[-20:]]
    highs=[float(v[2])for v in velas[-20:]]
    lows=[float(v[3])for v in velas[-20:]]
    closes=[float(v[4])for v in velas[-20:]]
    volumes=[float(v[6])for v in velas[-20:]]

    precio=closes[-1]
    vol_actual=sum(volumes[-2:])  # últimas 2 velas
    vol_prom=sum(volumes[-12:-2])/10
    vol_ratio=vol_actual/max(vol_prom,0.0001)

    # Cambios de precio
    c15=(closes[-1]-closes[-2])/max(closes[-2],0.0001)*100
    c30=(closes[-1]-closes[-3])/max(closes[-3],0.0001)*100
    c1h=(closes[-1]-closes[-5])/max(closes[-5],0.0001)*100

    # Confirmación: 2 velas consecutivas en la misma dirección
    velas_alcistas=closes[-1]>opens[-1] and closes[-2]>opens[-2]
    velas_bajistas=closes[-1]<opens[-1] and closes[-2]<opens[-2]

    # SMC
    bos_l,bos_s=detectar_bos(highs,lows)
    choch_l,choch_s=detectar_choch(closes)
    fvg_l,fvg_s=detectar_fvg(highs,lows)

    fp=lambda p:(f"${p:,.2f}" if p>100 else f"${p:,.4f}" if p>1 else f"${p:,.6f}")

    # LONG
    ls=0;lsg=[]
    if bos_l and velas_alcistas:ls+=40;lsg.append("📈 BOS alcista confirmado")
    if choch_l:ls+=30;lsg.append("🔄 CHoCH — cambio a alcista")
    if fvg_l:ls+=20;lsg.append("⬜ FVG alcista detectado")
    if vol_ratio>1.8 and velas_alcistas:ls+=20;lsg.append(f"💪 Vol {vol_ratio:.1f}x en 2 velas")
    if c30>1 and c15>0.3:ls+=15;lsg.append(f"🌱 +{c30:.1f}% sostenido en 30m")

    if ls>=50:
        return{"sym":simbolo,"precio":fp(precio),"score":ls,"sig":lsg,
               "c15":c15,"c1h":c1h,"vr":vol_ratio,"tipo":"long"}

    # SHORT
    ss=0;ssg=[]
    if bos_s and velas_bajistas:ss+=40;ssg.append("📉 BOS bajista confirmado")
    if choch_s:ss+=30;ssg.append("🔄 CHoCH — cambio a bajista")
    if fvg_s:ss+=20;ssg.append("⬜ FVG bajista detectado")
    if vol_ratio>1.8 and velas_bajistas:ss+=20;ssg.append(f"💪 Vol {vol_ratio:.1f}x en 2 velas")
    if c30<-1 and c15<-0.3:ss+=15;ssg.append(f"🔻 {c30:.1f}% sostenido en 30m")

    if ss>=50:
        return{"sym":simbolo,"precio":fp(precio),"score":ss,"sig":ssg,
               "c15":c15,"c1h":c1h,"vr":vol_ratio,"tipo":"short"}
    return None

def run(limite_l=2,limite_s=1):
    global señales_hoy
    now=datetime.now(ARG)
    fecha_hoy=now.strftime("%d/%m")

    if señales_hoy["fecha"]!=fecha_hoy:
        señales_hoy={"long":0,"short":0,"fecha":fecha_hoy}

    if señales_hoy["long"]>=4 and señales_hoy["short"]>=2:
        print("Límite diario alcanzado");return

    print(f"[{now.strftime('%H:%M')}] Analizando {len(PARES)} pares SMC...")
    longs,shorts=[],[]

    for par,sym in PARES:
        r=analizar(par,sym)
        if r:
            if r["tipo"]=="long" and señales_hoy["long"]<4:longs.append(r)
            elif r["tipo"]=="short" and señales_hoy["short"]<2:shorts.append(r)
        time.sleep(0.5)

    longs.sort(key=lambda x:x["score"],reverse=True)
    shorts.sort(key=lambda x:x["score"],reverse=True)
    tl=longs[:limite_l];ts=shorts[:limite_s]

    if not tl and not ts:
        print("Sin señales SMC");return

    hora=now.strftime("%H:%M")
    msg=f"📡 *PUMP RADAR SMC — {hora} ARG*\n_BOS · CHoCH · FVG | Kraken 15m_\n\n"

    if tl:
        msg+="🟢 *LONG — Spot o Futuros*\n\n"
        for r in tl:
            msg+=f"▶️ *{r['sym']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['c15']:+.2f}%` | 1h: `{r['c1h']:+.2f}%`\n"
            msg+=f"Vol: `{r['vr']:.1f}x` el promedio\n"
            msg+=f"🎯 Obj: +10/20% | Stop: -5%\n"
            msg+=f"_{', '.join(r['sig'])}_\n\n"
        señales_hoy["long"]+=len(tl)

    if ts:
        msg+="🔴 *SHORT — Futuros*\n\n"
        for r in ts:
            msg+=f"🔻 *{r['sym']}* | Score: `{r['score']}/100`\n"
            msg+=f"Precio: `{r['precio']}`\n"
            msg+=f"15m: `{r['c15']:+.2f}%` | 1h: `{r['c1h']:+.2f}%`\n"
            msg+=f"Vol: `{r['vr']:.1f}x` el promedio\n"
            msg+=f"⚠️ Máx 3x | Stop: +3%\n"
            msg+=f"_{', '.join(r['sig'])}_\n\n"
        señales_hoy["short"]+=len(ts)

    msg+=f"📊 Señales hoy: {señales_hoy['long']} long | {señales_hoy['short']} short\n"
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
                        send("👋 *Pump Radar SMC activo*\n\nDetecto BOS, CHoCH y FVG en 15m\nHorarios: 9am, 3pm y 8pm ARG\n\n/analizar — análisis ahora\n/resumen — señales de hoy\n/ayuda — cómo operar")
                    elif t=="/analizar":
                        send("🔍 Analizando estructura SMC...");run()
                    elif t=="/resumen":
                        send(f"📊 *Señales de hoy:*\n🟢 Long: {señales_hoy['long']}/4\n🔴 Short: {señales_hoy['short']}/2\nFecha: {señales_hoy['fecha']}")
                    elif t=="/ayuda":
                        send("*Conceptos SMC:*\n\n📈 *BOS* — rompe estructura previa\n🔄 *CHoCH* — cambia dirección\n⬜ *FVG* — gap que el precio llenará\n\n🟢 *LONG*\nObj: +10% a +20% | Stop: -5%\n\n🔴 *SHORT*\nMáx 3x | Stop: +3% | Obj: -10/15%\n\n_Verificá siempre antes de entrar._")
        except Exception as e:
            print(f"Err:{e}")
        time.sleep(2)

# Horarios Argentina: 9am, 3pm, 8pm
schedule.every().day.at("12:00").do(run)  # 9am ARG = 12:00 UTC
schedule.every().day.at("18:00").do(run)  # 3pm ARG = 18:00 UTC
schedule.every().day.at("23:00").do(run)  # 8pm ARG = 23:00 UTC

send("✅ *Pump Radar SMC activo*\nBOS · CHoCH · FVG en 15m\nHorarios: 9am, 3pm y 8pm ARG")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
