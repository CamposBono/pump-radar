import os,requests,time,schedule,threading
from datetime import datetime,timedelta
import pytz

T=os.environ.get("TELEGRAM_TOKEN")
C=os.environ.get("TELEGRAM_CHAT_ID")
Z=pytz.timezone("America/Argentina/Buenos_Aires")
P=[("BTC-USD","BTC"),("ETH-USD","ETH"),("SOL-USD","SOL"),("XRP-USD","XRP"),("ADA-USD","ADA")]
D={"l":0,"s":0,"f":""}
H={}

def send(t):
    try:requests.post(f"https://api.telegram.org/bot{T}/sendMessage",json={"chat_id":C,"text":t,"parse_mode":"Markdown"},timeout=10)
    except:pass

def ohlc(par,iv=15):
    try:
        seg={15:900,60:3600,240:14400,1440:86400}.get(iv,900)
        r=requests.get(f"https://api.exchange.coinbase.com/products/{par}/candles",
            params={"granularity":seg,"limit":50},timeout=8)
        if r.ok:return list(reversed(r.json()))
    except:pass
    return[]

def sesgo_diario(par):
    v=ohlc(par,1440)
    if len(v)<10:return"n"
    Cl=[float(x[4])for x in v[-10:]]
    Hi=[float(x[2])for x in v[-10:]]
    Lo=[float(x[3])for x in v[-10:]]
    hh=Hi[-1]>Hi[-3];hl=Lo[-1]>Lo[-3]
    lh=Hi[-1]<Hi[-3];ll=Lo[-1]<Lo[-3]
    ma=sum(Cl)/len(Cl)
    if lh and ll and Cl[-1]<ma:return"b"
    if hh and hl and Cl[-1]>ma:return"a"
    return"n"

def bos_h4(par,tipo):
    v=ohlc(par,240)
    if len(v)<10:return False
    Hi=[float(x[2])for x in v[-10:]]
    Lo=[float(x[3])for x in v[-10:]]
    Cl=[float(x[4])for x in v[-10:]]
    if tipo=="long":
        prev_hi=max(Hi[:5])
        return Cl[-1]>prev_hi and Lo[-1]>min(Lo[:5])
    else:
        prev_lo=min(Lo[:5])
        return Cl[-1]<prev_lo and Hi[-1]<max(Hi[:5])

def choch_h1(par,tipo):
    v=ohlc(par,60)
    if len(v)<10:return False
    Hi=[float(x[2])for x in v[-10:]]
    Lo=[float(x[3])for x in v[-10:]]
    if tipo=="long":
        return Hi[-1]>Hi[-2]>Hi[-3] and Lo[-1]>Lo[-2]>Lo[-3]
    else:
        return Hi[-1]<Hi[-2]<Hi[-3] and Lo[-1]<Lo[-2]<Lo[-3]

def compresion(Hi,Lo,V):
    ra=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-5,-1))/4
    rh=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-20,-5))/15
    if rh<0.001:return 0,ra,rh
    r=ra/rh
    sc=100 if r<0.4 else 80 if r<0.55 else 60 if r<0.7 else 40 if r<0.85 else 0
    if len(V)>=4 and V[-2]<V[-3]<V[-4]:sc=min(sc+10,100)
    return sc,ra,rh

def fibonacci(Hi,Lo,Cl,tipo):
    if len(Cl)<20:return False
    if tipo=="long":
        sw_lo=min(Lo[-20:]);idx=Lo[-20:].index(sw_lo)
        sw_hi=max(Hi[idx:])
        if sw_hi<=sw_lo:return False
        rng=sw_hi-sw_lo
        return sw_hi-rng*0.705<=Cl[-1]<=sw_hi-rng*0.618
    else:
        sw_hi=max(Hi[-20:]);idx=Hi[-20:].index(sw_hi)
        sw_lo=min(Lo[idx:])
        if sw_lo>=sw_hi:return False
        rng=sw_hi-sw_lo
        return sw_lo+rng*0.618<=Cl[-1]<=sw_lo+rng*0.705

def btc_ctx():
    v=ohlc("BTC-USD",60)
    if len(v)<6:return"n"
    c=[float(x[4])for x in v[-6:]]
    a,b=sum(c[:3])/3,sum(c[3:])/3
    return"b"if b<a*0.998 else"a"if b>a*1.002 else"n"

def regime(C,p=14):
    if len(C)<p:return"r"
    s=C[-p:];mv=abs(s[-1]-s[0])
    path=sum(abs(s[i]-s[i-1])for i in range(1,len(s)))
    ef=mv/max(path,0.0001)
    return("u"if s[-1]>s[0]else"d")if ef>0.45 else"r"

def fp(x):return f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}"

def ana(par,sym):
    v=ohlc(par,15)
    if len(v)<22:return None
    Hi=[float(x[2])for x in v[-22:]]
    Lo=[float(x[3])for x in v[-22:]]
    Cl=[float(x[4])for x in v[-22:]]
    V=[float(x[5])for x in v[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    sd=sesgo_diario(par)
    reg=regime(Cl)
    b="n"if sym=="BTC"else btc_ctx()
    sc_c,ra,rh=compresion(Hi,Lo,V)
    vp=sum(abs(Cl[i]-Cl[i-1])/Cl[i-1]*100 for i in range(1,8))/7
    tpp=max(3,min(8,vp*2));slp=max(1.5,min(3,vp*0.7))

    for tipo in["long","short"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=4):continue

        # CHoCH H1 obligatorio
        if not choch_h1(par,tipo):continue

        # BOS H4 requerido
        bos=bos_h4(par,tipo)

        # Filtro BTC contexto
        if sym!="BTC":
            if tipo=="long" and b=="b":continue
            if tipo=="short" and b=="a":continue

        # Momentum
        if tipo=="long" and c1<0 and c4<0:continue
        if tipo=="short" and c1>0 and c4>0:continue

        # Compresion minima
        if sc_c<40:continue

        # Zona
        zd=min(Lo[-15:]);zo=max(Hi[-15:])
        dd=(p-zd)/max(zd,0.001)*100
        do=(zo-p)/max(p,0.001)*100
        if tipo=="long" and not(0<=dd<=4):continue
        if tipo=="short" and not(0<=do<=4):continue

        # Anti entrada tardia
        if tipo=="long" and c4>3:continue
        if tipo=="short" and c4<-3:continue

        # Fibonacci
        fib=fibonacci(Hi,Lo,Cl,tipo)

        # Determinar umbral segun sesgo
        a_favor=(sd=="b"and tipo=="short")or(sd=="a"and tipo=="long")
        contra=(sd=="b"and tipo=="long")or(sd=="a"and tipo=="short")

        # Contra tendencia — Fibonacci obligatorio
        if contra and not fib:continue

        # SCORE
        sc=30+int(sc_c*0.35)
        sc+=20 if choch_h1(par,tipo)else 0
        sc+=15 if bos else 0
        sc+=10 if a_favor else-15 if contra else 0
        dz=dd if tipo=="long"else do
        sc+=15 if dz<1 else 10 if dz<2.5 else 3
        sc+=10 if(reg=="u"and tipo=="long")or(reg=="d"and tipo=="short")else 3 if reg=="r"else 0
        sc+=10 if fib else 0
        sc+=5 if vr>2 else 3 if vr>1.5 else 1 if vr>0.5 else 0
        sc+=5 if tipo=="long"and 0<c4<=3 else 5 if tipo=="short"and-3<=c4<0 else 0
        if vr<1:sc=int(sc*0.90)
        sc=min(sc,100)

        # Umbral diferenciado
        umbral=65 if a_favor or sd=="n" else 80
        if sc<umbral:continue

        tp1=p*(1+tpp/100)if tipo=="long"else p*(1-tpp/100)
        sl1=p*(1-slp/100)if tipo=="long"else p*(1+slp/100)
        H[k]=datetime.now(Z)
        em="🟢"if tipo=="long"else"🔴"
        sdt={"a":"Diario Alc📈","b":"Diario Baj📉","n":"Diario Neu"}.get(sd,"")
        bost="BOS✅"if bos else"BOS❌"
        fibt="Fib✅"if fib else""
        rt={"u":"Trend↑","d":"Trend↓","r":"Rng"}.get(reg,"")
        apal=5 if sc>=85 else 3
        tags=[sdt,bost]
        if fibt:tags.append(fibt)
        tags.append(f"Vol:{vr:.1f}x|{rt}")
        return{"sym":sym,"p":fp(p),"sc":sc,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,
               "tp":fp(tp1),"sl":fp(sl1),"tpp":tpp,"slp":slp,"apal":apal,"em":em,"tags":tags}
    return None

def dbg(par,sym):
    v=ohlc(par,15)
    if not v or len(v)<22:return f"⚠️{sym}:sin datos"
    Hi=[float(x[2])for x in v[-22:]]
    Lo=[float(x[3])for x in v[-22:]]
    Cl=[float(x[4])for x in v[-22:]]
    V=[float(x[5])for x in v[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    sd=sesgo_diario(par)
    reg=regime(Cl)
    sc_c,ra,rh=compresion(Hi,Lo,V)
    zd=min(Lo[-15:]);zo=max(Hi[-15:])
    dd=(p-zd)/max(zd,0.001)*100
    do=(zo-p)/max(p,0.001)*100
    fib_l=fibonacci(Hi,Lo,Cl,"long")
    fib_s=fibonacci(Hi,Lo,Cl,"short")
    ch_l=choch_h1(par,"long")
    ch_s=choch_h1(par,"short")
    bos_l=bos_h4(par,"long")
    bos_s=bos_h4(par,"short")
    sdn={"a":"alc","b":"baj","n":"neu"}.get(sd,"?")
    rn={"u":"↑","d":"↓","r":"rng"}.get(reg,"?")
    return(f"📊*{sym}*`{fp(p)}`\n"
           f"Diario:`{sdn}` Reg:`{rn}`\n"
           f"CHoCH:{'L✅'if ch_l else''}{'S✅'if ch_s else''}{'❌'if not ch_l and not ch_s else''}\n"
           f"BOS:{'L✅'if bos_l else''}{'S✅'if bos_s else''}{'❌'if not bos_l and not bos_s else''}\n"
           f"Fib:{'L✅'if fib_l else''}{'S✅'if fib_s else''}{'❌'if not fib_l and not fib_s else''}\n"
           f"Comp:`{sc_c}pts` Vol:`{vr:.1f}x`\n"
           f"1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`\n"
           f"Sop:`{dd:.1f}%` Res:`{do:.1f}%`")

def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=4 and D["s"]>=3:return
    ls,ss=[],[]
    for par,sym in P:
        r=ana(par,sym)
        if r:
            if r["tipo"]=="long"and D["l"]<4:ls.append(r)
            elif r["tipo"]=="short"and D["s"]<3:ss.append(r)
        time.sleep(0.5)
    ls.sort(key=lambda x:x["sc"],reverse=True)
    ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:return
    msg=f"⚡*PUMP RADAR v6.2—{now.strftime('%H:%M')}ARG*\n_Coinbase|Diario+H4+H1+Fib_\n\n"
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
    send("🔬*DEBUG v6.2—Coinbase|Diario+BOS+CHoCH+Fib*")
    for par,sym in P:send(dbg(par,sym));time.sleep(0.5)
    send("✅Debug completo")

def listen():
    last=0
    while True:
        try:
            r=requests.get(f"https://api.telegram.org/bot{T}/getUpdates",
                params={"offset":last+1,"timeout":10},timeout=15)
            if r.ok:
                for u in r.json().get("result",[]):
                    last=u["update_id"];t=(u.get("message")or{}).get("text")or""
                    if t=="/start":send("👋*Pump Radar v6.2*\n/analizar /resumen /debug /ayuda")
                    elif t=="/analizar":run()
                    elif t=="/resumen":send(f"📊Hoy:{D['l']}L {D['s']}S")
                    elif t=="/debug":threading.Thread(target=run_debug,daemon=True).start()
                    elif t=="/ayuda":send("⏰10:00|13:30|20:30 ARG\nCoinbase|Diario+H4+H1+Fib\n/debug diagnóstico")
        except:pass
        time.sleep(2)

# 3 horarios alineados a sesiones reales
schedule.every().day.at("13:00").do(run)  # 10:00 ARG
schedule.every().day.at("16:30").do(run)  # 13:30 ARG
schedule.every().day.at("23:30").do(run)  # 20:30 ARG

send("✅*Pump Radar v6.2*|Coinbase|Diario+BOS+CHoCH+Fib|3 sesiones")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)