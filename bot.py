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

def analizar(par,sym):
    v=ohlc(par)
    if len(v)<20:return None
    o=[float(x[1])for x in v[-20:]]
    h=[float(x[2])for x in v[-20:]]
    l=[float(x[3])for x in v[-20:]]
    c=[float(x[4])for x in v[-20:]]
    vol=[float(x[6])for x in v[-20:]]
    p=c[-1]
    vr=vol[-1]/max(sum(vol[-11:-1])/10,0.0001)
    c1=(c[-1]-c[-2])/max(c[-2],0.0001)*100
    c4=(c[-1]-c[-5])/max(c[-5],0.0001)*100
    alc=c[-1]>o[-1] and c[-2]>o[-2]
    baj=c[-1]<o[-1] and c[-2]<o[-2]
    bos_l=h[-1]>max(h[-10:-2]) and alc
    bos_s=l[-1]<min(l[-10:-2]) and baj
    choch_l=c[-1]>c[-3]>c[-5] and c[-5]<c[-7]
    choch_s=c[-1]<c[-3]<c[-5] and c[-5]>c[-7]
    fvg_l=l[-1]>h[-3]
    fvg_s=h[-1]<l[-3]
    rng=[abs(c[i]-c[i-1])/c[i-1]*100 for i in range(1,10)]
    vp=sum(rng)/len(rng) if rng else 1.5
    tp=max(5,min(12,vp*2.5))
    sl=max(3,min(5,vp*0.9))
    fp=lambda x:(f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}")
    tend="alc"if c[-1]>c[-10]else"baj"if c[-1]<c[-10]else"neu"
    for tipo,cond,cl in[("long",alc and vr>=0.8,[bos_l,choch_l,fvg_l]),("short",baj and vr>=0.8,[bos_s,choch_s,fvg_s])]:
        confs=sum(cl)
        if confs<2:continue
        sc=min(confs*30+int(vr*10),100)
        if sc<55:continue
        k=f"{sym}_{tipo}"
        if k in hist and datetime.now(ARG)-hist[k]<timedelta(hours=2):continue
        if tipo=="long" and tend=="baj":continue
        if tipo=="short" and tend=="alc":continue
        sigs=[]
        if cl[0]:sigs.append("📈 BOS"if tipo=="long"else"📉 BOS")
        if cl[1]:sigs.append("🔄 CHoCH")
        if cl[2]:sigs.append("⬜ FVG")
        sigs.append(f"💪 Vol {vr:.1f}x")
        tp1=p*(1+tp/100)if tipo=="long"else p*(1-tp/100)
        sl1=p*(1-sl/100)if tipo=="long"else p*(1+sl/100)
        apal=5 if sc>=80 else 3
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
    if not tl and not ts:send("🔍 Sin señales SMC en este momento. Mercado sin estructura clara.");return
    hora=now.strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora} ARG*\n_SMC H1 | BOS · CHoCH · FVG_\n\n"
    for r in tl:
        msg+=f"🟢 *LONG — {r['sym']}* | Score:`{r['sc']}/100`\n📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n🎯 TP:`{r['tp']}` (+{r['tp_pct']:.1f}%) | 🛑 SL:`{r['sl']}` (-{r['sl_pct']:.1f}%)\n⚡`{r['apal']}x` | 💰`+{r['gan']:.1f}%` neto\n_{', '.join(r['sigs'])}_\n\n"
        dia["l"]+=1
    for r in ts:
        msg+=f"🔴 *SHORT — {r['sym']}* | Score:`{r['sc']}/100`\n📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n🎯 TP:`{r['tp']}` (-{r['tp_pct']:.1f}%) | 🛑 SL:`{r['sl']}` (+{r['sl_pct']:.1f}%)\n⚡`{r['apal']}x` | 💰`+{r['gan']:.1f}%` neto\n_{', '.join(r['sigs'])}_\n\n"
        dia["s"]+=1
    msg+=f"📊 Hoy: {dia['l']} long | {dia['s']} short\n⚠️ _Experimental. No es asesoramiento financiero._"
    send(msg)

def run():
    threading.Thread(target=run_bg,daemon=True).start()

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"]
                    t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋 *Pump Radar SMC H1*\nBOS · CHoCH · FVG\n9am · 3pm · 8pm ARG\n\n/analizar — análisis ahora\n/resumen — señales de hoy\n/ayuda — cómo operar")
                    elif t=="/analizar":send("🔍 Analizando 15 pares... Resultado en 1-2 min.");run()
                    elif t=="/resumen":send(f"📊 Hoy: {dia['l']} long | {dia['s']} short")
                    elif t=="/ayuda":send("📍 Entrada al recibir señal\n🎯 TP dinámico por volatilidad\n🛑 SL — salís sin dudar\n⚡ Apalancamiento sugerido\n\nVerificá en BingX/Bitget antes de entrar.")
        except:pass
        time.sleep(2)

schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)
send("✅ *Pump Radar SMC H1*\n15 pares | Resultado en 1-2 min tras /analizar")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
