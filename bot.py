```python
import os,requests,time,schedule,threading
from datetime import datetime,timedelta
import pytz

T=os.environ.get("TELEGRAM_TOKEN")
C=os.environ.get("TELEGRAM_CHAT_ID")
Z=pytz.timezone("America/Argentina/Buenos_Aires")
P=[("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),("XRP/USDT","XRP"),("LINK/USDT","LINK"),("AVAX/USDT","AVAX")]
D={"l":0,"s":0,"f":""}
H={}

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{T}/sendMessage",json={"chat_id":C,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def ohlc(par):
    try:
        r=requests.get("https://api.kraken.com/0/public/OHLC",params={"pair":par,"interval":60},timeout=8)
        if r.ok and not r.json().get("error"):
            k=list(r.json()["result"].keys())[0]
            return r.json()["result"][k]
    except:pass
    return[]

def btc():
    v=ohlc("XBT/USDT")
    if len(v)<6:return"n"
    c=[float(x[4])for x in v[-6:]]
    a,b=sum(c[:3])/3,sum(c[3:])/3
    return"b"if b<a*0.998 else"a"if b>a*1.002 else"n"

def estructura(Hi,Lo,C):
    n=len(C)
    if n<10:return"n"
    sh=[i for i in range(2,n-2)if Hi[i]==max(Hi[max(0,i-2):i+3])]
    sl=[i for i in range(2,n-2)if Lo[i]==min(Lo[max(0,i-2):i+3])]
    if len(sh)<2 or len(sl)<2:return"n"
    hh=Hi[sh[-1]]>Hi[sh[-2]];hl=Lo[sl[-1]]>Lo[sl[-2]]
    lh=Hi[sh[-1]]<Hi[sh[-2]];ll=Lo[sl[-1]]<Lo[sl[-2]]
    if hh and hl:return"a"
    if lh and ll:return"b"
    return"n"

def regime(C,p=14):
    if len(C)<p:return"r"
    s=C[-p:];mv=abs(s[-1]-s[0]);path=sum(abs(s[i]-s[i-1])for i in range(1,len(s)))
    ef=mv/max(path,0.0001)
    if ef>0.45:return"u"if s[-1]>s[0]else"d"
    return"r"

def compresion(Hi,Lo,C,V):
    rangos=[(Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-5,-1)]
    rango_act=sum(rangos)/len(rangos)
    rango_hist=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-14,-5))/9
    if rango_hist<0.001:return 0,rango_act,rango_hist
    ratio=rango_act/rango_hist
    if ratio<0.4:sc=100
    elif ratio<0.55:sc=80
    elif ratio<0.7:sc=60
    elif ratio<0.85:sc=40
    else:sc=0
    if len(V)>=4 and V[-2]<V[-3] and V[-3]<V[-4]:sc=min(sc+10,100)
    return sc,rango_act,rango_hist

def fp(x):return f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}"

def ana(par,sym):
    if sym=="BTC":return None
    v=ohlc(par)
    if len(v)<22:return None
    O=[float(x[1])for x in v[-22:]];Hi=[float(x[2])for x in v[-22:]]
    Lo=[float(x[3])for x in v[-22:]];C=[float(x[4])for x in v[-22:]]
    V=[float(x[6])for x in v[-22:]]
    p=C[-1];vr=V[-1]/max(sum(V[-11:-1])/10,0.001)
    c1=(C[-1]-C[-2])/max(C[-2],0.001)*100
    c4=(C[-1]-C[-5])/max(C[-5],0.001)*100
    est=estructura(Hi,Lo,C);reg=regime(C);b=btc()
    sc_comp,rango_act,rango_hist=compresion(Hi,Lo,C,V)
    rng=[abs(C[i]-C[i-1])/C[i-1]*100 for i in range(1,8)]
    vp=sum(rng)/len(rng)if rng else 1.5
    tpp=max(4,min(10,vp*2));slp=max(2,min(4,vp*0.7))
    for tipo in["long","short"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=4):continue
        if vr<0.8:continue
        if tipo=="long" and est=="b":continue
        if tipo=="short" and est=="a":continue
        if tipo=="long" and b=="b":continue
        if tipo=="short" and b=="a":continue
        if tipo=="long" and c1<0 and c4<0:continue
        if tipo=="short" and c1>0 and c4>0:continue
        if sc_comp<40:continue
        zd=min(Lo[-15:]);zo=max(Hi[-15:])
        dd=(p-zd)/max(zd,0.001)*100;do=(zo-p)/max(p,0.001)*100
        if tipo=="long" and not(0<=dd<=4.0):continue
        if tipo=="short" and not(0<=do<=4.0):continue
        if tipo=="long" and c4>3.0:continue
        if tipo=="short" and c4<-3.0:continue
        sc=30
        sc+=int(sc_comp*0.35)
        if est=="a" and tipo=="long":sc+=25
        elif est=="b" and tipo=="short":sc+=25
        else:sc+=8
        dz=dd if tipo=="long"else do
        sc+=20 if dz<1.0 else 12 if dz<2.5 else 4
        if(reg=="u"and tipo=="long")or(reg=="d"and tipo=="short"):sc+=10
        elif reg=="r":sc+=3
        sc+=5 if vr>2.0 else 3 if vr>1.5 else 1
        if tipo=="long" and 0<c4<=3:sc+=5
        elif tipo=="short" and -3<=c4<0:sc+=5
        if vr<1.0:sc=int(sc*0.85)
        sc=min(sc,100)
        if sc<68:continue
        tp1=p*(1+tpp/100)if tipo=="long"else p*(1-tpp/100)
        sl1=p*(1-slp/100)if tipo=="long"else p*(1+slp/100)
        H[k]=datetime.now(Z)
        em="🟢"if tipo=="long"else"🔴"
        rt={"u":"Trending↑","d":"Trending↓","r":"Ranging"}.get(reg,"—")
        et={"a":"Alcista✅","b":"Bajista✅","n":"Neutral⚠️"}.get(est,"—")
        comp_txt=f"🔇 Comp:{sc_comp}pts Rango:{rango_act:.2f}% Hist:{rango_hist:.2f}%"
        apal=3 if reg=="r"else 5 if sc>=88 else 3
        return{"sym":sym,"p":fp(p),"sc":sc,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,"tp":fp(tp1),"sl":fp(sl1),"tpp":tpp,"slp":slp,"apal":apal,"em":em,"sg":[comp_txt,f"🏗 {et} | {rt}",f"₿ BTC {'baja'if b=='b'else'sube'if b=='a'else'neutral'}"]}
    return None

def debug_par(par,sym):
    v=ohlc(par)
    if not v or len(v)<22:return f"⚠️ {sym}: sin datos ({len(v)if v else 0} velas)"
    O=[float(x[1])for x in v[-22:]];Hi=[float(x[2])for x in v[-22:]]
    Lo=[float(x[3])for x in v[-22:]];C=[float(x[4])for x in v[-22:]]
    V=[float(x[6])for x in v[-22:]]
    p=C[-1];vr=V[-1]/max(sum(V[-11:-1])/10,0.001)
    c1=(C[-1]-C[-2])/max(C[-2],0.001)*100;c4=(C[-1]-C[-5])/max(C[-5],0.001)*100
    est=estructura(Hi,Lo,C);reg=regime(C);b=btc()
    sc_comp,rango_act,rango_hist=compresion(Hi,Lo,C,V)
    zd=min(Lo[-15:]);zo=max(Hi[-15:])
    dd=(p-zd)/max(zd,0.001)*100;do=(zo-p)/max(p,0.001)*100
    en={"a":"alcista","b":"bajista","n":"neutral"}.get(est,"?")
    rn={"u":"trend↑","d":"trend↓","r":"ranging"}.get(reg,"?")
    return(f"📊 *{sym}* `{fp(p)}`\n"
           f"  Est:`{en}` Reg:`{rn}` BTC:`{'b'if b=='b'else'a'if b=='a'else'n'}`\n"
           f"  Comp:`{sc_comp}pts` Rango:`{rango_act:.2f}%` Hist:`{rango_hist:.2f}%`\n"
           f"  Vol:`{vr:.1f}x` 1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`\n"
           f"  DistSop:`{dd:.1f}%` DistRes:`{do:.1f}%`")

def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=3 and D["s"]>=2:send("ℹ️ Limite diario alcanzado.");return
    ls,ss=[],[]
    for par,sym in P:
        r=ana(par,sym)
        if r:
            if r["tipo"]=="long" and D["l"]<3:ls.append(r)
            elif r["tipo"]=="short" and D["s"]<2:ss.append(r)
        time.sleep(0.5)
    ls.sort(key=lambda x:x["sc"],reverse=True);ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:send("🔍 Sin compresiones validas.");return
    hora=now.strftime("%H:%M");msg=f"⚡ *PUMP RADAR v3 — {hora} ARG*\n_Pre-breakout por compresion_\n\n"
    for r in tl+ts:
        stp="+"if r["tipo"]=="long"else"-";ssl="-"if r["tipo"]=="long"else"+"
        msg+=(f"{r['em']} *{r['tipo'].upper()} — {r['sym']}* | Score:`{r['sc']}/100`\n"
              f"📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n"
              f"🎯`{r['tp']}` ({stp}{r['tpp']:.1f}%) | 🛑`{r['sl']}` ({ssl}{r['slp']:.1f}%) | ⚡`{r['apal']}x`\n"
              f"_{', '.join(r['sg'])}_\n\n")
        if r["tipo"]=="long":D["l"]+=1
        else:D["s"]+=1
    msg+=f"📊 Hoy:{D['l']}L {D['s']}S\n⚠️_Experimental._"
    send(msg)

def run():threading.Thread(target=run_bg,daemon=True).start()

def run_debug():
    send("🔬 *DEBUG v3 Kraken*")
    for par,sym in P:
        if sym!="BTC":send(debug_par(par,sym));time.sleep(0.3)
    send("✅ Debug completo")

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{T}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"];t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋 *Pump Radar v3*\n/analizar /resumen /debug /ayuda")
                    elif t=="/analizar":send("⚡ Buscando compresiones...");run()
                    elif t=="/resumen":send(f"📊 Hoy:{D['l']}L {D['s']}S")
                    elif t=="/debug":threading.Thread(target=run_debug,daemon=True).start()
                    elif t=="/ayuda":send("🔇 Compresion pre-movimiento\n📍 Zona clave obligatoria\n🏗 Estructura filtrada\n₿ BTC filtro\n/debug diagnostico")
        except:pass
        time.sleep(2)

schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)
send("✅ *Pump Radar v3 activo* | Kraken | 6 pares")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
```
