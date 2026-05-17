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

def ohlc(par,iv=60):
    try:
        seg={60:3600,240:14400,1440:86400}.get(iv,3600)
        r=requests.get(f"https://api.exchange.coinbase.com/products/{par}/candles",
            params={"granularity":seg,"limit":50},timeout=8)
        if r.ok:return list(reversed(r.json()))
    except:pass
    return[]

def sesgo_diario(par):
    v=ohlc(par,1440)
    if len(v)<10:return"n"
    Hi=[float(x[2])for x in v[-10:]]
    Lo=[float(x[3])for x in v[-10:]]
    Cl=[float(x[4])for x in v[-10:]]
    ma=sum(Cl)/len(Cl)
    hh=Hi[-1]>Hi[-3];hl=Lo[-1]>Lo[-3]
    lh=Hi[-1]<Hi[-3];ll=Lo[-1]<Lo[-3]
    if lh and ll and Cl[-1]<ma:return"b"
    if hh and hl and Cl[-1]>ma:return"a"
    return"n"

def fibonacci_h4(par,tipo):
    v=ohlc(par,240)
    if len(v)<30:return False,0,0
    Hi=[float(x[2])for x in v[-40:]]
    Lo=[float(x[3])for x in v[-40:]]
    Cl=[float(x[4])for x in v[-40:]]
    p=Cl[-1]
    if tipo=="long":
        sw_lo=min(Lo);idx=Lo.index(sw_lo)
        sw_hi=max(Hi[idx:])
        if sw_hi<=sw_lo:return False,0,0
        rng=sw_hi-sw_lo
        if rng/sw_lo*100<1.5:return False,0,0
        f618=sw_hi-rng*0.618
        f705=sw_hi-rng*0.705
        en_zona=f705<=p<=f618
        distancia=abs(p-f618)/max(p,0.001)*100
        return en_zona,f618,f705
    else:
        sw_hi=max(Hi);idx=Hi.index(sw_hi)
        sw_lo=min(Lo[idx:])
        if sw_lo>=sw_hi:return False,0,0
        rng=sw_hi-sw_lo
        if rng/sw_hi*100<1.5:return False,0,0
        f618=sw_lo+rng*0.618
        f705=sw_lo+rng*0.705
        en_zona=f618<=p<=f705
        distancia=abs(p-f618)/max(p,0.001)*100
        return en_zona,f618,f705

def fib_cercano(par,tipo,umbral=3.0):
    # Detecta si el precio se está acercando a zona Fibonacci
    v=ohlc(par,240)
    if len(v)<30:return False
    Hi=[float(x[2])for x in v[-40:]]
    Lo=[float(x[3])for x in v[-40:]]
    Cl=[float(x[4])for x in v[-40:]]
    p=Cl[-1]
    if tipo=="long":
        sw_lo=min(Lo);idx=Lo.index(sw_lo)
        sw_hi=max(Hi[idx:])
        if sw_hi<=sw_lo:return False
        rng=sw_hi-sw_lo
        if rng/sw_lo*100<1.5:return False
        f618=sw_hi-rng*0.618
        return abs(p-f618)/max(p,0.001)*100<umbral
    else:
        sw_hi=max(Hi);idx=Hi.index(sw_hi)
        sw_lo=min(Lo[idx:])
        if sw_lo>=sw_hi:return False
        rng=sw_hi-sw_lo
        if rng/sw_hi*100<1.5:return False
        f618=sw_lo+rng*0.618
        return abs(p-f618)/max(p,0.001)*100<umbral

def compresion_h1(par):
    v=ohlc(par,60)
    if len(v)<22:return 0,0,0
    Hi=[float(x[2])for x in v[-22:]]
    Lo=[float(x[3])for x in v[-22:]]
    V=[float(x[5])for x in v[-22:]]
    ra=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-5,-1))/4
    rh=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-20,-5))/15
    if rh<0.001:return 0,ra,rh
    r=ra/rh
    sc=100 if r<0.4 else 80 if r<0.55 else 60 if r<0.7 else 40 if r<0.85 else 0
    vol_dec=V[-2]<V[-3]<V[-4]
    if vol_dec:sc=min(sc+10,100)
    return sc,ra,rh

def zona_liquidez_h1(par,p):
    v=ohlc(par,60)
    if len(v)<20:return False
    Hi=[float(x[2])for x in v[-20:]]
    Lo=[float(x[3])for x in v[-20:]]
    max_prev=max(Hi[-20:-3])
    min_prev=min(Lo[-20:-3])
    return(abs(p-max_prev)/max(p,0.001)*100<2.0 or
           abs(p-min_prev)/max(p,0.001)*100<2.0)

def sl_estructural(par,tipo):
    v=ohlc(par,60)
    if len(v)<10:return 0
    Hi=[float(x[2])for x in v[-10:]]
    Lo=[float(x[3])for x in v[-10:]]
    return min(Lo)if tipo=="long"else max(Hi)

def btc_ctx():
    v=ohlc("BTC-USD",60)
    if len(v)<6:return"n"
    c=[float(x[4])for x in v[-6:]]
    a,b=sum(c[:3])/3,sum(c[3:])/3
    return"b"if b<a*0.998 else"a"if b>a*1.002 else"n"

def sesion():
    h=datetime.now(Z).hour
    if 10<=h<14:return"ny",65
    if 5<=h<10:return"eu",70
    if h>=20 or h<2:return"asia",75
    return"off",99

def fp(x):return f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}"

def ana(par,sym):
    ses,umbral_ses=sesion()
    if ses=="off":return None

    v1h=ohlc(par,60)
    if len(v1h)<22:return None
    Cl=[float(x[4])for x in v1h[-22:]]
    V=[float(x[5])for x in v1h[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100

    # Filtro entrada tardia
    if abs(c1)>1.5:return None

    sd=sesgo_diario(par)
    b="n"if sym=="BTC"else btc_ctx()
    sc_c,ra,rh=compresion_h1(par)
    liq=zona_liquidez_h1(par,p)

    for tipo in["long","short"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=4):continue

        # Compresion minima
        if sc_c<40:continue

        # BTC contexto
        if sym!="BTC":
            if tipo=="long" and b=="b":continue
            if tipo=="short" and b=="a":continue

        # Momentum
        if tipo=="long" and c1<0 and c4<0:continue
        if tipo=="short" and c1>0 and c4>0:continue

        # Anti entrada tardia
        if tipo=="long" and c4>3:continue
        if tipo=="short" and c4<-3:continue

        # Fibonacci H4 — filtro principal
        fib,f618,f705=fibonacci_h4(par,tipo)
        a_favor=(sd=="b"and tipo=="short")or(sd=="a"and tipo=="long")
        contra=(sd=="b"and tipo=="long")or(sd=="a"and tipo=="short")

        # Contra tendencia — Fibonacci obligatorio
        if contra and not fib:continue

        # SL estructural
        sl_est=sl_estructural(par,tipo)
        if sl_est==0:continue
        sl_pct=abs(p-sl_est)/max(p,0.001)*100
        if sl_pct<0.3 or sl_pct>5:continue

        # TP con ratio diferenciado
        ratio=2.5 if a_favor else 1.8
        tp_pct=sl_pct*ratio
        tp1=p*(1+tp_pct/100)if tipo=="long"else p*(1-tp_pct/100)

        # SCORE
        sc=30+int(sc_c*0.35)
        sc+=25 if fib else 0
        sc+=15 if a_favor else-15 if contra else 0
        sc+=10 if liq else 0
        sc+=10 if vr>1.5 else 5 if vr>0.8 else-10 if vr<0.3 else 0
        sc+=5 if tipo=="long"and 0<c4<=3 else 5 if tipo=="short"and-3<=c4<0 else 0
        sc+=5 if ses=="ny"else 3 if ses=="eu"else 1
        if vr<1:sc=int(sc*0.92)
        sc=min(sc,100)

        umbral=max(umbral_ses,80 if contra else 65)
        if sc<umbral:continue

        H[k]=datetime.now(Z)
        em="🟢"if tipo=="long"else"🔴"
        sdt={"a":"📈Alc","b":"📉Baj","n":"➡️Neu"}.get(sd,"")
        fibt=f"Fib✅{fp(f618)}"if fib else"Fib❌"
        liqt="Liq✅"if liq else""
        apal=5 if sc>=85 else 3
        tags=[sdt,fibt]
        if liqt:tags.append(liqt)
        tags.append(f"Vol:{vr:.1f}x|{ses.upper()}")
        return{"sym":sym,"p":fp(p),"sc":sc,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,
               "tp":fp(tp1),"sl":fp(sl_est),"tpp":round(tp_pct,1),"slp":round(sl_pct,1),
               "apal":apal,"em":em,"tags":tags}
    return None

def dbg(par,sym):
    v1h=ohlc(par,60)
    if not v1h or len(v1h)<22:return f"⚠️{sym}:sin datos"
    Cl=[float(x[4])for x in v1h[-22:]]
    V=[float(x[5])for x in v1h[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    sd=sesgo_diario(par)
    sc_c,ra,rh=compresion_h1(par)
    liq=zona_liquidez_h1(par,p)
    fib_l,f618l,f705l=fibonacci_h4(par,"long")
    fib_s,f618s,f705s=fibonacci_h4(par,"short")
    cerca_l=fib_cercano(par,"long")
    cerca_s=fib_cercano(par,"short")
    ses,_=sesion()
    sdn={"a":"alc","b":"baj","n":"neu"}.get(sd,"?")
    return(f"📊*{sym}*`{fp(p)}`\n"
           f"Diario:`{sdn}` Ses:`{ses}`\n"
           f"Comp H1:`{sc_c}pts` Vol:`{vr:.1f}x`\n"
           f"Fib L:{'✅'if fib_l else'cerca✅'if cerca_l else'❌'}"
           f" S:{'✅'if fib_s else'cerca✅'if cerca_s else'❌'}\n"
           f"Liq:{'✅'if liq else'❌'}\n"
           f"1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`")

def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=4 and D["s"]>=3:return
    alertas=[]
    ls,ss=[],[]
    for par,sym in P:
        # Pre-alertas
        v1h=ohlc(par,60)
        if v1h and len(v1h)>=22:
            Cl=[float(x[4])for x in v1h[-22:]]
            p=Cl[-1]
            sc_c,_,_=compresion_h1(par)
            cerca_l=fib_cercano(par,"long")
            cerca_s=fib_cercano(par,"short")
            if sc_c>=70 and(cerca_l or cerca_s):
                dir="LONG"if cerca_l else"SHORT"
                alertas.append(f"⚠️*{sym}*`{fp(p)}`Comp:{sc_c}pts+Fib cercano→{dir}")
        r=ana(par,sym)
        if r:
            if r["tipo"]=="long"and D["l"]<4:ls.append(r)
            elif r["tipo"]=="short"and D["s"]<3:ss.append(r)
        time.sleep(0.5)
    ls.sort(key=lambda x:x["sc"],reverse=True)
    ss.sort(key=lambda x:x["sc"],reverse=True)
    tl,ts=ls[:2],ss[:1]
    if not tl and not ts:
        if alertas:
            send("🔍*Sin señales — Pre-alertas:*\n"+"\n".join(alertas))
        return
    msg=f"⚡*PUMP RADAR v7—{now.strftime('%H:%M')}ARG*\n_H1+H4 Fib|Diario_\n\n"
    for r in tl+ts:
        s="+";sl="-"
        if r["tipo"]=="short":s="-";sl="+"
        msg+=(f"{r['em']}*{r['tipo'].upper()}—{r['sym']}*|`{r['sc']}/100`\n"
              f"📍`{r['p']}`|Vol:`{r['vr']:.1f}x`|1h:`{r['c1']:+.1f}%`\n"
              f"🎯`{r['tp']}`({s}{r['tpp']}%)|🛑`{r['sl']}`(-{r['slp']}%)|⚡`{r['apal']}x`\n"
              f"_{', '.join(r['tags'])}_\n\n")
        if r["tipo"]=="long":D["l"]+=1
        else:D["s"]+=1
    msg+=f"📊{D['l']}L {D['s']}S|⚠️Experimental"
    send(msg)

def run():threading.Thread(target=run_bg,daemon=True).start()

def run_debug():
    send("🔬*DEBUG v7—H1 compresión|H4 Fibonacci|Diario*")
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
                    if t=="/start":send("👋*Pump Radar v7*\n/analizar /resumen /debug /ayuda")
                    elif t=="/analizar":run()
                    elif t=="/resumen":send(f"📊Hoy:{D['l']}L {D['s']}S")
                    elif t=="/debug":threading.Thread(target=run_debug,daemon=True).start()
                    elif t=="/ayuda":send("⏰10:00|13:30|20:30 ARG\nH1 compresión|H4 Fibonacci|Diario sesgo\n/debug diagnóstico")
        except:pass
        time.sleep(2)

schedule.every().day.at("13:00").do(run)
schedule.every().day.at("16:30").do(run)
schedule.every().day.at("23:30").do(run)

send("✅*Pump Radar v7*|Coinbase|H1+H4 Fib|Diario|3 sesiones")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)