import os,requests,time,schedule,threading
from datetime import datetime,timedelta
import pytz

T=os.environ.get("TELEGRAM_TOKEN")
C=os.environ.get("TELEGRAM_CHAT_ID")
Z=pytz.timezone("America/Argentina/Buenos_Aires")
P=[("XXBTZUSD","BTC"),("XETHZUSD","ETH"),("SOLUSDT","SOL"),("XRPUSDT","XRP"),("ADAUSDT","ADA")]
D={"l":0,"s":0,"f":""}
H={}

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{T}/sendMessage",json={"chat_id":C,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def ohlc(par,iv=15):
    try:
        r=requests.get("https://api.kraken.com/0/public/OHLC",params={"pair":par,"interval":iv},timeout=8)
        if r.ok and not r.json().get("error"):
            k=list(r.json()["result"].keys())[0];return r.json()["result"][k]
    except:pass
    return[]

def dir_1h(par):
    v=ohlc(par,60)
    if len(v)<6:return"n"
    Hi=[float(x[2])for x in v[-6:]];Lo=[float(x[3])for x in v[-6:]]
    hh=Hi[-1]>Hi[-2]>Hi[-3];hl=Lo[-1]>Lo[-2]>Lo[-3]
    lh=Hi[-1]<Hi[-2]<Hi[-3];ll=Lo[-1]<Lo[-2]<Lo[-3]
    return"a"if hh and hl else"b"if lh and ll else"n"

def btc_ctx():
    v=ohlc("XXBTZUSD",60)
    if len(v)<6:return"n"
    c=[float(x[4])for x in v[-6:]];a,b=sum(c[:3])/3,sum(c[3:])/3
    return"b"if b<a*0.998 else"a"if b>a*1.002 else"n"

def estructura(Hi,Lo,C):
    n=len(C)
    if n<10:return"n"
    sh=[i for i in range(2,n-2)if Hi[i]==max(Hi[max(0,i-2):i+3])]
    sl=[i for i in range(2,n-2)if Lo[i]==min(Lo[max(0,i-2):i+3])]
    if len(sh)<2 or len(sl)<2:return"n"
    hh=Hi[sh[-1]]>Hi[sh[-2]];hl=Lo[sl[-1]]>Lo[sl[-2]]
    lh=Hi[sh[-1]]<Hi[sh[-2]];ll=Lo[sl[-1]]<Lo[sl[-2]]
    return"a"if hh and hl else"b"if lh and ll else"n"

def regime(C,p=14):
    if len(C)<p:return"r"
    s=C[-p:];mv=abs(s[-1]-s[0]);path=sum(abs(s[i]-s[i-1])for i in range(1,len(s)))
    ef=mv/max(path,0.0001)
    return("u"if s[-1]>s[0]else"d")if ef>0.45 else"r"

def compresion(Hi,Lo,V):
    ra=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-5,-1))/4
    rh=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-20,-5))/15
    if rh<0.001:return 0,ra,rh
    r=ra/rh;sc=100 if r<0.4 else 80 if r<0.55 else 60 if r<0.7 else 40 if r<0.85 else 0
    if len(V)>=4 and V[-2]<V[-3]<V[-4]:sc=min(sc+10,100)
    return sc,ra,rh

def fibonacci(Hi,Lo,Cl,tipo):
    n=len(Cl)
    if n<20:return False
    if tipo=="long":
        swing_lo=min(Lo[-20:]);idx_lo=Lo[-20:].index(swing_lo)
        swing_hi=max(Hi[idx_lo:])
        if swing_hi<=swing_lo:return False
        rango=swing_hi-swing_lo
        f618=swing_hi-rango*0.618;f705=swing_hi-rango*0.705
        return f705<=Cl[-1]<=f618
    else:
        swing_hi=max(Hi[-20:]);idx_hi=Hi[-20:].index(swing_hi)
        swing_lo=min(Lo[idx_hi:])
        if swing_lo>=swing_hi:return False
        rango=swing_hi-swing_lo
        f618=swing_lo+rango*0.618;f705=swing_lo+rango*0.705
        return f618<=Cl[-1]<=f705

def fp(x):return f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}"

def ana(par,sym):
    v=ohlc(par,15)
    if len(v)<22:return None
    Hi=[float(x[2])for x in v[-22:]];Lo=[float(x[3])for x in v[-22:]]
    Cl=[float(x[4])for x in v[-22:]];V=[float(x[6])for x in v[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    est=estructura(Hi,Lo,Cl);reg=regime(Cl);h1=dir_1h(par)
    b="n"if sym=="BTC"else btc_ctx()
    sc_c,ra,rh=compresion(Hi,Lo,V)
    vp=sum(abs(Cl[i]-Cl[i-1])/Cl[i-1]*100 for i in range(1,8))/7
    tpp=max(3,min(8,vp*2));slp=max(1.5,min(3,vp*0.7))
    for tipo in["long","short"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=2):continue
        if tipo=="long" and est=="b":continue
        if tipo=="short" and est=="a":continue
        if sym!="BTC":
            if tipo=="long" and b=="b":continue
            if tipo=="short" and b=="a":continue
        if tipo=="long" and c1<0 and c4<0:continue
        if tipo=="short" and c1>0 and c4>0:continue
        if sc_c<40:continue
        if tipo=="long" and h1=="b":continue
        if tipo=="short" and h1=="a":continue
        zd=min(Lo[-15:]);zo=max(Hi[-15:])
        dd=(p-zd)/max(zd,0.001)*100;do=(zo-p)/max(p,0.001)*100
        if tipo=="long" and not(0<=dd<=4):continue
        if tipo=="short" and not(0<=do<=4):continue
        if tipo=="long" and c4>3:continue
        if tipo=="short" and c4<-3:continue
        sc=30+int(sc_c*0.35)
        sc+=25 if(est=="a"and tipo=="long")or(est=="b"and tipo=="short")else 8
        sc+=10 if(h1=="a"and tipo=="long")or(h1=="b"and tipo=="short")else-5 if h1=="n"else 0
        dz=dd if tipo=="long"else do
        sc+=20 if dz<1 else 12 if dz<2.5 else 4
        sc+=10 if(reg=="u"and tipo=="long")or(reg=="d"and tipo=="short")else 3 if reg=="r"else 0
        sc+=5 if vr>2 else 3 if vr>1.5 else 1 if vr>0.5 else 0
        sc+=5 if tipo=="long"and 0<c4<=3 else 5 if tipo=="short"and-3<=c4<0 else 0
        fib=fibonacci(Hi,Lo,Cl,tipo)
        if fib:sc+=10
        if vr<1:sc=int(sc*0.90)
        sc=min(sc,100)
        if sc<65:continue
        tp1=p*(1+tpp/100)if tipo=="long"else p*(1-tpp/100)
        sl1=p*(1-slp/100)if tipo=="long"else p*(1+slp/100)
        H[k]=datetime.now(Z)
        em="🟢"if tipo=="long"else"🔴"
        rt={"u":"Trend↑","d":"Trend↓","r":"Ranging"}.get(reg,"")
        et={"a":"Alc✅","b":"Baj✅","n":"Neu⚠️"}.get(est,"")
        h1t={"a":"1H Alc✅","b":"1H Baj✅","n":"1H Rng⚠️"}.get(h1,"")
        fibt="Fib✅"if fib else""
        apal=5 if sc>=85 else 3
        tags=[f"🔇Comp:{sc_c}pts",f"🏗{et}|{rt}",h1t]
        if fibt:tags.append(fibt)
        tags.append(f"₿{'baja'if b=='b'else'sube'if b=='a'else'neu'}")
        return{"sym":sym,"p":fp(p),"sc":sc,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,
               "tp":fp(tp1),"sl":fp(sl1),"tpp":tpp,"slp":slp,"apal":apal,"em":em,"tags":tags}
    return None

def dbg(par,sym):
    v=ohlc(par,15)
    if not v or len(v)<22:return f"⚠️{sym}:sin datos"
    Hi=[float(x[2])for x in v[-22:]];Lo=[float(x[3])for x in v[-22:]]
    Cl=[float(x[4])for x in v[-22:]];V=[float(x[6])for x in v[-22:]]
    p=Cl[-1];vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1);vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100;c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    est=estructura(Hi,Lo,Cl);reg=regime(Cl);h1=dir_1h(par)
    sc_c,ra,rh=compresion(Hi,Lo,V)
    zd=min(Lo[-15:]);zo=max(Hi[-15:])
    dd=(p-zd)/max(zd,0.001)*100;do=(zo-p)/max(p,0.001)*100
    fib_l=fibonacci(Hi,Lo,Cl,"long");fib_s=fibonacci(Hi,Lo,Cl,"short")
    en={"a":"alc","b":"baj","n":"neu"}.get(est,"?")
    rn={"u":"↑","d":"↓","r":"rng"}.get(reg,"?")
    h1n={"a":"alc","b":"baj","n":"rng"}.get(h1,"?")
    fibt=f"Fib:{'L✅'if fib_l else'S✅'if fib_s else'❌'}"
    return(f"📊*{sym}*`{fp(p)}`\n"
           f"15M:`{en}` 1H:`{h1n}` Reg:`{rn}`\n"
           f"Comp:`{sc_c}pts` Vol:`{vr:.1f}x` {fibt}\n"
           f"1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`\n"
           f"Sop:`{dd:.1f}%` Res:`{do:.1f}%`")

def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=5 and D["s"]>=3:return
    ls,ss=[],[]
    for par,sym in P:
        r=ana(par,sym)
        if r:
            if r["tipo"]=="long"and D["l"]<5:ls.append(r)
            elif r["tipo"]=="short"and D["s"]<3:ss.append(r)
        time.sleep(0.4)
    ls.sort(key=lambda x:x["sc"],reverse=True);ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:return
    msg=f"⚡*PUMP RADAR v6—{now.strftime('%H:%M')}ARG*\n_15M+1H|Fib activo_\n\n"
    for r in tl+ts:
        s="+";sl="-"
        if r["tipo"]=="short":s="-";sl="+"
        msg+=(f"{r['em']}*{r['tipo'].upper()}—{r['sym']}*|`{r['sc']}/100`\n"
              f"📍`{r['p']}`|Vol:`{r['vr']:.1f}x`|1h:`{r['c1']:+.1f}%`\n"
              f"🎯`{r['tp']}`({s}{r['tpp']:.1f}%)|🛑`{r['sl']}`({sl}{r['slp']:.1f}%)|⚡`{r['apal']}x`\n"
              f"_{', '.join(r['tags'])}_\n\n")
        if r["tipo"]=="long":D["l"]+=1
        else:D["s"]+=1
    msg+=f"📊{D['l']}L {D['s']}S|⚠️Experimental"
    send(msg)

def run():threading.Thread(target=run_bg,daemon=True).start()

def run_debug():
    send("🔬*DEBUG v6—15M+1H+Fib*")
    for par,sym in P:send(dbg(par,sym));time.sleep(0.3)
    send("✅Debug completo")

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{T}/getUpdates",params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"];t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋*Pump Radar v6*\n/analizar /resumen /debug /ayuda")
                    elif t=="/analizar":run()
                    elif t=="/resumen":send(f"📊Hoy:{D['l']}L {D['s']}S")
                    elif t=="/debug":threading.Thread(target=run_debug,daemon=True).start()
                    elif t=="/ayuda":send("⏰Corre cada 30min\n15M señal|1H contexto|Fib bonus\n/debug diagnóstico")
        except:pass
        time.sleep(2)

schedule.every(30).minutes.do(run)
send("✅*Pump Radar v6*|5 pares|15M+1H+Fib|cada 30min")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
