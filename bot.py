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
    ("XLM/USDT","XLM"),("BCH/USDT","BCH"),
]

FEES=0.001  # 0.1% ida y vuelta aprox
senales_hoy={"long":0,"short":0,"fecha":""}

def send(t):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id":CHAT_ID,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def get_ohlc(par,intervalo=60):
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

def calcular_señal(par_kraken,simbolo):
    velas=get_ohlc(par_kraken,60)
    if len(velas)<20:return None

    opens=[float(v[1])for v in velas[-20:]]
    highs=[float(v[2])for v in velas[-20:]]
    lows=[float(v[3])for v in velas[-20:]]
    closes=[float(v[4])for v in velas[-20:]]
    volumes=[float(v[6])for v in velas[-20:]]

    precio=closes[-1]
    vol_actual=volumes[-1]
    vol_prom=sum(volumes[-10:-1])/9
    vol_ratio=vol_actual/max(vol_prom,0.0001)

    c1h=(closes[-1]-closes[-2])/max(closes[-2],0.0001)*100
    c4h=(closes[-1]-closes[-5])/max(closes[-5],0.0001)*100
    c24h=(closes[-1]-closes[-25])/max(closes[-25],0.0001)*100 if len(closes)>=25 else c4h*3

    velas_alc=closes[-1]>opens[-1] and closes[-2]>opens[-2]
    velas_baj=closes[-1]<opens[-1] and closes[-2]<opens[-2]

    # BOS
    max_prev=max(highs[-10:-2])
    min_prev=min(lows[-10:-2])
    bos_l=highs[-1]>max_prev
    bos_s=lows[-1]<min_prev

    # CHoCH
    choch_l=closes[-1]>closes[-3] and closes[-3]>closes[-5] and closes[-5]<closes[-7]
    choch_s=closes[-1]<closes[-3] and closes[-3]<closes[-5] and closes[-5]>closes[-7]

    # FVG
    fvg_l=len(lows)>=3 and lows[-1]>highs[-3]
    fvg_s=len(highs)>=3 and highs[-1]<lows[-3]

    fp=lambda p:(f"${p:,.2f}" if p>100 else f"${p:,.4f}" if p>1 else f"${p:,.6f}")

    def calcular_trade(entrada,tipo,score):
        if tipo=="long":
            sl_pct=0.05 if score>=75 else 0.07
            tp1_pct=0.10
            tp2_pct=0.18
            sl=entrada*(1-sl_pct)
            tp1=entrada*(1+tp1_pct)
            tp2=entrada*(1+tp2_pct)
            ganancia_neta=tp1_pct-FEES
            apal=5 if score>=80 else 3
        else:
            sl_pct=0.04 if score>=75 else 0.06
            tp1_pct=0.08
            tp2_pct=0.15
            sl=entrada*(1+sl_pct)
            tp1=entrada*(1-tp1_pct)
            tp2=entrada*(1-tp2_pct)
            ganancia_neta=tp1_pct-FEES
            apal=3 if score>=75 else 2

        rentable=ganancia_neta>sl_pct*0.5
        return{
            "sl":fp(sl),"tp1":fp(tp1),"tp2":fp(tp2),
            "sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,
            "ganancia_neta":ganancia_neta*100,
            "apal":apal,"rentable":rentable
        }

    # LONG
    ls=0;lsg=[]
    confirmaciones=0
    if bos_l and velas_alc:ls+=40;lsg.append("📈 BOS alcista");confirmaciones+=1
    if choch_l:ls+=30;lsg.append("🔄 CHoCH alcista");confirmaciones+=1
    if fvg_l:ls+=20;lsg.append("⬜ FVG alcista");confirmaciones+=1
    if vol_ratio>0.8 and velas_alc:ls+=15;lsg.append(f"💪 Vol {vol_ratio:.1f}x")
    if c4h>1 and c1h>0.2:ls+=10;lsg.append(f"🌱 +{c4h:.1f}% en 4h")

    if ls>=55 and confirmaciones>=2 and vol_ratio>=0.8:
        t=calcular_trade(precio,"long",ls)
        if t["rentable"]:
            return{"sym":simbolo,"precio":fp(precio),"score":ls,"sig":lsg,
                   "c1h":c1h,"c4h":c4h,"vr":vol_ratio,"tipo":"long","trade":t}

    # SHORT
    ss=0;ssg=[]
    conf_s=0
    if bos_s and velas_baj:ss+=40;ssg.append("📉 BOS bajista");conf_s+=1
    if choch_s:ss+=30;ssg.append("🔄 CHoCH bajista");conf_s+=1
    if fvg_s:ss+=20;ssg.append("⬜ FVG bajista");conf_s+=1
    if vol_ratio>0.8 and velas_baj:ss+=15;ssg.append(f"💪 Vol {vol_ratio:.1f}x")
    if c4h<-1 and c1h<-0.2:ss+=10;ssg.append(f"🔻 {c4h:.1f}% en 4h")

    if ss>=55 and conf_s>=2 and vol_ratio>=0.8:
        t=calcular_trade(precio,"short",ss)
        if t["rentable"]:
            return{"sym":simbolo,"precio":fp(precio),"score":ss,"sig":ssg,
                   "c1h":c1h,"c4h":c4h,"vr":vol_ratio,"tipo":"short","trade":t}
    return None

def run():
    global senales_hoy
    now=datetime.now(ARG)
    fecha_hoy=now.strftime("%d/%m")

    if senales_hoy["fecha"]!=fecha_hoy:
        senales_hoy={"long":0,"short":0,"fecha":fecha_hoy}

    if senales_hoy["long"]>=3 and senales_hoy["short"]>=2:
        print("Limite diario alcanzado");return

    print(f"[{now.strftime('%H:%M')}] Analizando {len(PARES)} pares H1 SMC...")
    longs,shorts=[],[]

    for par,sym in PARES:
        r=calcular_señal(par,sym)
        if r:
            if r["tipo"]=="long" and senales_hoy["long"]<3:longs.append(r)
            elif r["tipo"]=="short" and senales_hoy["short"]<2:shorts.append(r)
        time.sleep(1)

    longs.sort(key=lambda x:x["score"],reverse=True)
    shorts.sort(key=lambda x:x["score"],reverse=True)
    tl=longs[:2];ts=shorts[:1]

    if not tl and not ts:
        print("Sin senales");return

    hora=now.strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora} ARG*\n_SMC H1 | BOS · CHoCH · FVG_\n\n"

    for r in tl:
        t=r["trade"]
        msg+=f"🟢 *LONG — {r['sym']}*\n"
        msg+=f"Score: `{r['score']}/100` | Vol: `{r['vr']:.1f}x`\n"
        msg+=f"📍 Entrada: `{r['precio']}`\n"
        msg+=f"🎯 TP1: `{t['tp1']}` (+{t['tp1_pct']:.0f}%)\n"
        msg+=f"🎯 TP2: `{t['tp2']}` (+{t['tp2_pct']:.0f}%)\n" if 'tp2_pct' in t else ""
        msg+=f"🛑 SL: `{t['sl']}` (-{t['sl_pct']:.0f}%)\n"
        msg+=f"⚡ Apalancamiento: `{t['apal']}x`\n"
        msg+=f"💰 Ganancia neta est: `+{t['ganancia_neta']:.1f}%`\n"
        msg+=f"1h: `{r['c1h']:+.2f}%` | 4h: `{r['c4h']:+.2f}%`\n"
        msg+=f"_{', '.join(r['sig'])}_\n\n"
        senales_hoy["long"]+=1

    for r in ts:
        t=r["trade"]
        msg+=f"🔴 *SHORT — {r['sym']}*\n"
        msg+=f"Score: `{r['score']}/100` | Vol: `{r['vr']:.1f}x`\n"
        msg+=f"📍 Entrada: `{r['precio']}`\n"
        msg+=f"🎯 TP1: `{t['tp1']}` (-{t['tp1_pct']:.0f}%)\n"
        msg+=f"🛑 SL: `{t['sl']}` (+{t['sl_pct']:.0f}%)\n"
        msg+=f"⚡ Apalancamiento: `{t['apal']}x`\n"
        msg+=f"💰 Ganancia neta est: `+{t['ganancia_neta']:.1f}%`\n"
        msg+=f"1h: `{r['c1h']:+.2f}%` | 4h: `{r['c4h']:+.2f}%`\n"
        msg+=f"_{', '.join(r['sig'])}_\n\n"
        senales_hoy["short"]+=1

    msg+=f"📊 Señales hoy: {senales_hoy['long']} long | {senales_hoy['short']} short\n"
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
                        send("👋 *Pump Radar Futuros H1*\n\nSMC en H1 — BOS, CHoCH, FVG\nTop 20 pares | Long y Short\nHorarios: 9am, 3pm, 8pm ARG\n\n/analizar — análisis ahora\n/resumen — señales de hoy\n/ayuda — cómo operar")
                    elif t=="/analizar":
                        send("🔍 Analizando 20 pares en H1...");run()
                    elif t=="/resumen":
                        send(f"📊 *Señales de hoy:*\n🟢 Long: {senales_hoy['long']}/3\n🔴 Short: {senales_hoy['short']}/2\nFecha: {senales_hoy['fecha']}")
                    elif t=="/ayuda":
                        send("*Cómo operar:*\n\n📍 *Entrada* — precio actual al recibir señal\n🎯 *TP1/TP2* — objetivos de ganancia\n🛑 *SL* — stop loss, salís si llega ahí\n⚡ *Apalancamiento* — sugerido según score\n\n*Regla de oro:*\nSi el precio se mueve -50% del SL sin llegar, revisá la señal.\n\n_Verificá siempre en tu exchange antes de entrar._")
        except Exception as e:
            print(f"Err:{e}")
        time.sleep(2)

schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)

send("✅ *Pump Radar Futuros H1 activo*\nSMC | TP · SL · Apalancamiento incluidos\nHorarios: 9am, 3pm y 8pm ARG")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
