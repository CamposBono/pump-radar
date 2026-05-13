import os,requests,time,schedule,threading
from datetime import datetime,timedelta
import pytz
T=os.environ.get("TELEGRAM_TOKEN")
C=os.environ.get("TELEGRAM_CHAT_ID")
Z=pytz.timezone("America/Argentina/Buenos_Aires")
P=[("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),("XRP/USDT","XRP"),("ADA/USDT","ADA"),("LINK/USDT","LINK"),("AVAX/USDT","AVAX"),("LTC/USDT","LTC"),("SUI/USDT","SUI"),("BCH/USDT","BCH"),("DOT/USDT","DOT"),("NEAR/USDT","NEAR"),("INJ/USDT","INJ"),("ARB/USDT","ARB"),("OP/USDT","OP")]
D={"l":0,"s":0,"f":""}
H={}
def send(t):
    try:requests.post(f"https://api.telegram.org/bot{T}/sendMessage",json={"chat_id":C,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass
def get(par):
    try:
        r=requests.get("https://api.kraken.com/0/public/OHLC",params={"pair":par,"interval":60},timeout=8)
        if r.ok:
            d=r.json()
            if not d.get("error"):
                k=list(d["result"].keys())[0];return d["result"][k]
    except:pass
    return[]
def btc():
    v=get("XBT/USDT")
    if len(v)<3:return"n"
    c=[float(x[4])for x in v[-3:]]
    return"b"if c[-1]<c[-2]else"a"if c[-1]>c[-2]else"n"
def ana(par,sym):
    if sym=="BTC":return None
    v=get(par)
    if len(v)<12:return None
    o=[float(x[1])for x in v[-12:]];h=[float(x[2])for x in v[-12:]]
    l=[float(x[3])for x in v[-12:]];c=[float(x[4])for x in v[-12:]]
    vol=[float(x[6])for x in v[-12:]]
    p=c[-1];vr=vol[-1]/max(sum(vol[-11:-1])/10,0.001)
    c1=(c[-1]-c[-2])/max(c[-2],0.001)*100;c4=(c[-1]-c[-5])/max(c[-5],0.001)*100
    mx=max(h[-10:-1]);mn=min(l[-10:-1])
    ds=(p-mn)/max(mn,0.001)*100;dl=(mx-p)/max(p,0.001)*100
    vv=vr>1.2 and vol[-1]>vol[-2]*1.1
    roja=c[-1]<o[-1];verde=c[-1]>o[-1]
    b=btc()
    fp=lambda x:(f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}")
    rng=[abs(c[i]-c[i-1])/c[i-1]*100 for i in range(1,8)]
    vp=sum(rng)/len(rng)if rng else 1.5
    tp=max(4,min(10,vp*2));sl=max(2,min(4,vp*0.7))
    for tipo in["short","long"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=3):continue
        if tipo=="short" and b=="a":continue
        if tipo=="long" and b=="b":continue
        ok_s=0<=ds<=1.5 and roja and vv
        ok_l=0<=dl<=1.5 and verde and vv
        if tipo=="short" and not ok_s:continue
        if tipo=="long" and not ok_l:continue
        sc=60+(20 if(ds<0.5 if tipo=="short"else dl<0.5)else 0)+(15 if b==("b"if tipo=="short"else"a")else 0)+(10 if vr>2 else 0)+(10 if(c4<-1 if tipo=="short"else c4>1)else 0)
        sc=min(sc,100)
        tp1=p*(1-tp/100)if tipo=="short"else p*(1+tp/100)
        sl1=p*(1+sl/100)if tipo=="short"else p*(1-sl/100)
        H[k]=datetime.now(Z)
        emoji="🔴"if tipo=="short"else"🟢"
        dir_="short"if tipo=="short"else"long"
        sg=[f"⚡ Pre-breakout {dir_}",f"📊 Vol {vr:.1f}x",f"₿ BTC {'baja'if b=='b'else'sube'if b=='a'else'neutral'}"]
        return{"sym":sym,"p":fp(p),"sc":sc,"sg":sg,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,"tp":fp(tp1),"sl":fp(sl1),"tp_pct":tp,"sl_pct":sl,"gan":tp-0.1,"apal":5 if sc>=85 else 3,"em":emoji}
    return None
def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=3 and D["s"]>=2:send("ℹ️ Límite diario alcanzado.");return
    ls,ss=[],[]
    for par,sym in P:
        r=ana(par,sym)
        if r:
            if r["tipo"]=="long" and D["l"]<3:ls.append(r)
            elif r["tipo"]=="short" and D["s"]<2:ss.append(r)
        time.sleep(0.5)
    ls.sort(key=lambda x:x["sc"],reverse=True);ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:send("🔍 Sin pre-breakouts. Mercado sin señales.");return
    hora=now.strftime("%H:%M");msg=f"⚡ *PUMP RADAR — {hora} ARG*\n_Pre-breakout H1_\n\n"
    for r in tl+ts:
        msg+=f"{r['em']} *{r['tipo'].upper()} — {r['sym']}* | Score:`{r['sc']}/100`\n📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n🎯`{r['tp']}` ({'+' if r['tipo']=='long' else '-'}{r['tp_pct']:.1f}%) | 🛑`{r['sl']}` ({'+' if r['tipo']=='short' else '-'}{r['sl_pct']:.1f}%) | ⚡`{r['apal']}x`\n_{', '.join(r['sg'])}_\n\n"
        if r["tipo"]=="long":D["l"]+=1
        else:D["s"]+=1
    msg+=f"📊 Hoy:{D['l']}L {D['s']}S\n⚠️_Experimental._"
    send(msg)
def run():threading.Thread(target=run_bg,daemon=True).start()
def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{T}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"];t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋 *Pump Radar*\nPre-breakout H1\n9am·3pm·8pm ARG\n/analizar /resumen /ayuda")
                    elif t=="/analizar":send("⚡ Buscando pre-breakouts...");run()
                    elif t=="/resumen":send(f"📊 Hoy:{D['l']}L {D['s']}S")
                    elif t=="/ayuda":send("📍 Entrada al recibir\n🎯 TP dinámico\n🛑 SL ajustado\n₿ BTC filtra dirección\nVerificá en BingX/Bitget.")
        except:pass
        time.sleep(2)
schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)
send("✅ *Pump Radar activo*\nPre-breakout H1 | 15 pares")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
