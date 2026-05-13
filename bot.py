import os,requests,time,schedule,threading
from datetime import datetime,timedelta
import pytz

TOKEN=os.environ.get("TELEGRAM_TOKEN")
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID")
ARG=pytz.timezone("America/Argentina/Buenos_Aires")
FEES=0.001
PARES=[("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),("XRP/USDT","XRP"),("ADA/USDT","ADA"),("LINK/USDT","LINK"),("AVAX/USDT","AVAX"),("LTC/USDT","LTC"),("SUI/USDT","SUI"),("BCH/USDT","BCH"),("DOT/USDT","DOT"),("NEAR/USDT","NEAR"),("INJ/USDT","INJ"),("ARB/USDT","ARB"),("OP/USDT","OP")]
dia={"l":0,"s":0,"f":""}
hist={}

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",json={"chat_id":CHAT_ID,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def ohlc(par):
    try:
        r=requests.get("https://api.kraken.com/0/public/OHLC",params={"pair":par,"interval":60},timeout=8)
        if r.ok:
            d=r.json()
            if not d.get("error"):
                k=list(d["result"].keys())[0]
                return d["result"][k]
    except:pass
    return[]

def btc_dir():
    v=ohlc("XBT/USDT")
    if len(v)<3:return"neu"
    c=[float(x[4])for x in v[-3:]]
    return"baj"if c[-1]<c[-2]<c[-3]else"alc"if c[-1]>c[-2]>c[-3]else"neu"

def analizar(par,sym):
    if sym=="BTC":return None
    v=ohlc(par)
    if len(v)<15:return None
    o=[float(x[1])for x in v[-15:]]
    h=[float(x[2])for x in v[-15:]]
    l=[float(x[3])for x in v[-15:]]
    c=[float(x[4])for x in v[-15:]]
    vol=[float(x[6])for x in v[-15:]]

    p=c[-1]
    vol_actual=vol[-1]
    vol_prom=sum(vol[-11:-1])/10
    vr=vol_actual/max(vol_prom,0.0001)

    # Vela actual en formacion
    vela_roja=c[-1]<o[-1]
    vela_verde=c[-1]>o[-1]
    cuerpo=abs(c[-1]-o[-1])/max(o[-1],0.0001)*100

    # Maximos y minimos recientes (excluye vela actual)
    max_rec=max(h[-10:-1])
    min_rec=min(l[-10:-1])

    # Distancia al breakout
    dist_short=(p-min_rec)/max(min_rec,0.0001)*100
    dist_long=(max_rec-p)/max(p,0.0001)*100

    # Volumen creciendo (no explosivo)
    vol_creciendo=vol[-1]>vol[-2]*1.2 and vr>1.2

    # Momentum en formacion
    c1=(c[-1]-c[-2])/max(c[-2],0.0001)*100
    c4=(c[-1]-c[-5])/max(c[-5],0.0001)*100

    fp=lambda x:(f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}")

    rng=[abs(c[i]-c[i-1])/c[i-1]*100 for i in range(1,10)]
    vp=sum(rng)/len(rng)if rng else 1.5
    tp=max(4,min(10,vp*2))
    sl=max(2,min(4,vp*0.7))

    btc=btc_dir()

    for tipo in["short","long"]:
        k=f"{sym}_{tipo}"
        if k in hist and datetime.now(ARG)-hist[k]<timedelta(hours=3):continue

        if tipo=="short":
            # Pre-breakout bajista: cerca del minimo, volumen creciendo, vela roja
            if not(0<=dist_short<=0.8 and vela_roja and vol_creciendo and cuerpo>0.1):continue
            if btc=="alc":continue  # BTC subiendo = no shortear
            sc=60
            if dist_short<0.3:sc+=20
            if vr>2:sc+=10
            if btc=="baj":sc+=15
            if c4<-1:sc+=10
            sc=min(sc,100)
            sigs=[f"⚡ Pre-breakout bajista ({dist_short:.2f}% del min)",f"📊 Vol {vr:.1f}x creciendo",f"🕯️ Vela roja formándose"]
            if btc=="baj":sigs.append("₿ BTC confirma bajista")
            tp1=p*(1-tp/100);sl1=p*(1+sl/100)

        else:
            # Pre-breakout alcista: cerca del maximo, volumen creciendo, vela verde
            if not(0<=dist_long<=0.8 and vela_verde and vol_creciendo and cuerpo>0.1):continue
            if btc=="baj":continue  # BTC bajando = no ir long
            sc=60
            if dist_long<0.3:sc+=20
            if vr>2:sc+=10
            if btc=="alc":sc+=15
            if c4>1:sc+=10
            sc=min(sc,100)
            sigs=[f"⚡ Pre-breakout alcista ({dist_long:.2f}% del max)",f"📊 Vol {vr:.1f}x creciendo",f"🕯️ Vela verde formándose"]
            if btc=="alc":sigs.append("₿ BTC confirma alcista")
            tp1=p*(1+tp/100);sl1=p*(1-sl/100)

        apal=5 if sc>=85 else 3
        hist[k]=datetime.now(ARG)
        return{"sym":sym,"p":fp(p),"sc":sc,"sigs":sigs,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,"tp":fp(tp1),"sl":fp(sl1),"tp_pct":tp,"sl_pct":sl,"gan":tp-FEES*100,"apal":apal}
    return None

def run_bg():
    global dia
    now=datetime.now(ARG)
    hoy=now.strftime("%d/%m")
    if dia["f"]!=hoy:dia={"l":0,"s":0,"f":hoy}
    if dia["l"]>=3 and dia["s"]>=2:send("ℹ️ Límite diario alcanzado.");return
    ls,ss=[],[]
    for par,sym in PARES:
        r=analizar(par,sym)
        if r:
            if r["tipo"]=="long" and dia["l"]<3:ls.append(r)
            elif r["tipo"]=="short" and dia["s"]<2:ss.append(r)
        time.sleep(0.5)
    ls.sort(key=lambda x:x["sc"],reverse=True)
    ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:send("🔍 Sin pre-breakouts detectados. Mercado sin señales claras.");return
    hora=now.strftime("%H:%M")
    msg=f"⚡ *PUMP RADAR — {hora} ARG*\n_Pre-breakout H1 | Alerta temprana_\n\n"
    for r in tl:
        msg+=f"🟢 *LONG — {r['sym']}* | Score:`{r['sc']}/100`\n📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n🎯 TP:`{r['tp']}` (+{r['tp_pct']:.1f}%) | 🛑 SL:`{r['sl']}` (-{r['sl_pct']:.1f}%)\n⚡`{r['apal']}x` | 💰`+{r['gan']:.1f}%` neto\n_{', '.join(r['sigs'])}_\n\n"
        dia["l"]+=1
    for r in ts:
        msg+=f"🔴 *SHORT — {r['sym']}* | Score:`{r['sc']}/100`\n📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n🎯 TP:`{r['tp']}` (-{r['tp_pct']:.1f}%) | 🛑 SL:`{r['sl']}` (+{r['sl_pct']:.1f}%)\n⚡`{r['apal']}x` | 💰`+{r['gan']:.1f}%` neto\n_{', '.join(r['sigs'])}_\n\n"
        dia["s"]+=1
    msg+=f"📊 Hoy: {dia['l']} long | {dia['s']} short\n⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)

def run():threading.Thread(target=run_bg,daemon=True).start()

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"]
                    t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋 *Pump Radar — Alerta Temprana*\nPre-breakout H1 | BTC como filtro\n9am · 3pm · 8pm ARG\n\n/analizar\n/resumen\n/ayuda")
                    elif t=="/analizar":send("⚡ Buscando pre-breakouts...");run()
                    elif t=="/resumen":send(f"📊 Hoy: {dia['l']} long | {dia['s']} short")
                    elif t=="/ayuda":send("⚡ *Alerta temprana*\nDetecto ANTES de que rompa\n\n📍 Entrada al recibir señal\n🎯 TP dinámico\n🛑 SL ajustado\n₿ BTC filtra la dirección\n\nVerificá en BingX/Bitget antes de entrar.")
        except:pass
        time.sleep(2)

schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)
send("✅ *Pump Radar — Alerta Temprana activo*\nPre-breakout H1 | Sin confirmaciones tardías")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
