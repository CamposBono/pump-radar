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
    ma=sum(Cl)/len(Cl)
    hh=Hi[-1]>Hi[-3];hl=Lo[-1]>Lo[-3]
    lh=Hi[-1]<Hi[-3];ll=Lo[-1]<Lo[-3]
    if lh and ll and Cl[-1]<ma:return"b"
    if hh and hl and Cl[-1]>ma:return"a"
    return"n"

def choch_h1(par,tipo,sc_c=0):
    v=ohlc(par,60)
    if len(v)<8:return False
    Hi=[float(x[2])for x in v[-8:]]
    Lo=[float(x[3])for x in v[-8:]]
    Cl=[float(x[4])for x in v[-8:]]
    # Ventana reducida cuando hay compresion alta
    ventana=3 if sc_c>=70 else 5
    tol=1.001 if sc_c>=70 else 1.0
    if tipo=="long":
        nivel=max(Hi[-8:-ventana])
        return Cl[-1]>nivel*tol
    else:
        nivel=min(Lo[-8:-ventana])
        return Cl[-1]<nivel/tol

def bos_h4(par,tipo,sc_c=0):
    v=ohlc(par,240)
    if len(v)<8:return False,0
    Hi=[float(x[2])for x in v[-8:]]
    Lo=[float(x[3])for x in v[-8:]]
    Cl=[float(x[4])for x in v[-8:]]
    V=[float(x[5])for x in v[-8:]]
    vol_avg=sum(V[:-1])/max(len(V[:-1]),1)
    vol_ruptura=V[-1]/max(vol_avg,0.0001)
    ventana=3 if sc_c>=70 else 5
    tol=1.002 if sc_c>=70 else 1.0
    if tipo=="long":
        nivel=max(Hi[-8:-ventana])
        return Cl[-1]>nivel*tol,vol_ruptura
    else:
        nivel=min(Lo[-8:-ventana])
        return Cl[-1]<nivel/tol,vol_ruptura

def fibonacci_h4(par,tipo):
    # Fibonacci calculado en H4 — más historia
    v=ohlc(par,240)
    if len(v)<30:return False
    Hi=[float(x[2])for x in v[-30:]]
    Lo=[float(x[3])for x in v[-30:]]
    Cl=[float(x[4])for x in v[-30:]]
    if tipo=="long":
        sw_lo=min(Lo);idx=Lo.index(sw_lo)
        sw_hi=max(Hi[idx:])
        if sw_hi<=sw_lo:return False
        rng=sw_hi-sw_lo
        if rng/sw_lo*100<1:return False  # swing demasiado pequeño
        return sw_hi-rng*0.705<=Cl[-1]<=sw_hi-rng*0.618
    else:
        sw_hi=max(Hi);idx=Hi.index(sw_hi)
        sw_lo=min(Lo[idx:])
        if sw_lo>=sw_hi:return False
        rng=sw_hi-sw_lo
        if rng/sw_hi*100<1:return False
        return sw_lo+rng*0.618<=Cl[-1]<=sw_lo+rng*0.705

def alerta_previa(par,sym,sc_c,liq):
    # Aviso cuando hay compresion alta y liquidez pero sin señal
    if sc_c>=80 and liq:
        return True
    return False

def zona_liquidez(Hi,Lo,p):
    max_prev=max(Hi[-20:-3])
    min_prev=min(Lo[-20:-3])
    cerca_max=abs(p-max_prev)/max(p,0.001)*100<2.0
    cerca_min=abs(p-min_prev)/max(p,0.001)*100<2.0
    return cerca_max or cerca_min

def sl_estructural(Hi,Lo,tipo):
    if tipo=="long":return min(Lo[-10:])
    else:return max(Hi[-10:])

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

def compresion(Hi,Lo,V):
    ra=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-5,-1))/4
    rh=sum((Hi[i]-Lo[i])/max(Lo[i],0.001)*100 for i in range(-20,-5))/15
    if rh<0.001:return 0,ra,rh
    r=ra/rh
    sc=100 if r<0.4 else 80 if r<0.55 else 60 if r<0.7 else 40 if r<0.85 else 0
    if len(V)>=4 and V[-2]<V[-3]<V[-4]:sc=min(sc+10,100)
    return sc,ra,rh

def sesion_actual():
    now=datetime.now(Z).hour
    if 10<=now<14:return"ny"
    if 5<=now<10:return"eu"
    if 20<=now or now<2:return"asia"
    return"off"

def fp(x):return f"${x:,.2f}"if x>100 else f"${x:,.4f}"if x>1 else f"${x:,.6f}"

def ana(par,sym):
    v15=ohlc(par,15)
    if len(v15)<22:return None
    Hi=[float(x[2])for x in v15[-22:]]
    Lo=[float(x[3])for x in v15[-22:]]
    Cl=[float(x[4])for x in v15[-22:]]
    V=[float(x[5])for x in v15[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    if abs(c1)>1.5:return None
    sd=sesgo_diario(par)
    reg=regime(Cl)
    b="n"if sym=="BTC"else btc_ctx()
    sc_c,ra,rh=compresion(Hi,Lo,V)
    ses=sesion_actual()
    liq=zona_liquidez(Hi,Lo,p)
    zd=min(Lo[-15:]);zo=max(Hi[-15:])
    dd=(p-zd)/max(zd,0.001)*100
    do=(zo-p)/max(p,0.001)*100

    for tipo in["long","short"]:
        k=f"{sym}_{tipo}"
        if k in H and datetime.now(Z)-H[k]<timedelta(hours=4):continue
        ch=choch_h1(par,tipo,sc_c)
        if not ch:continue
        bos,vol_bos=bos_h4(par,tipo,sc_c)
        if sym!="BTC":
            if tipo=="long" and b=="b":continue
            if tipo=="short" and b=="a":continue
        if tipo=="long" and c1<0 and c4<0:continue
        if tipo=="short" and c1>0 and c4>0:continue
        if sc_c<40:continue
        if tipo=="long" and dd<0.3:continue
        if tipo=="short" and do<0.3:continue
        if tipo=="long" and dd>4:continue
        if tipo=="short" and do>4:continue
        if tipo=="long" and c4>3:continue
        if tipo=="short" and c4<-3:continue
        fib=fibonacci_h4(par,tipo)
        a_favor=(sd=="b"and tipo=="short")or(sd=="a"and tipo=="long")
        contra=(sd=="b"and tipo=="long")or(sd=="a"and tipo=="short")
        if contra and not fib:continue
        sl_est=sl_estructural(Hi,Lo,tipo)
        sl_pct=abs(p-sl_est)/max(p,0.001)*100
        if sl_pct<0.3 or sl_pct>5:continue
        # Ratio diferenciado
        ratio=2.5 if(sd=="b"and tipo=="short")or(sd=="a"and tipo=="long")else 1.8
        tp_pct=sl_pct*ratio
        tp1=p*(1+tp_pct/100)if tipo=="long"else p*(1-tp_pct/100)
        sc=30+int(sc_c*0.35)
        sc+=20 if ch else 0
        sc+=15 if bos else 0
        sc+=10 if a_favor else-15 if contra else 0
        dz=dd if tipo=="long"else do
        sc+=15 if dz>2 else 10 if dz>1 else 5
        sc+=10 if(reg=="u"and tipo=="long")or(reg=="d"and tipo=="short")else 3 if reg=="r"else 0
        sc+=10 if fib else 0
        sc+=10 if liq else 0
        sc+=5 if vol_bos>1.5 else-5 if bos and vol_bos<0.5 else 0
        sc+=5 if vr>2 else 3 if vr>1.5 else 1 if vr>0.5 else 0
        if vr<1:sc=int(sc*0.90)
        sc=min(sc,100)
        if ses=="asia":umbral=75
        elif ses=="eu":umbral=70
        elif contra:umbral=80
        else:umbral=65
        if sc<umbral:continue
        H[k]=datetime.now(Z)
        em="🟢"if tipo=="long"else"🔴"
        sdt={"a":"Diario📈","b":"Diario📉","n":"Diario➡️"}.get(sd,"")
        bost="BOS✅"if bos else"BOS❌"
        fibt="Fib✅"if fib else""
        liqt="Liq✅"if liq else""
        rt={"u":"↑","d":"↓","r":"rng"}.get(reg,"")
        apal=5 if sc>=85 else 3
        tags=[sdt,bost]
        if fibt:tags.append(fibt)
        if liqt:tags.append(liqt)
        tags.append(f"Vol:{vr:.1f}x|{rt}|{ses.upper()}")
        return{"sym":sym,"p":fp(p),"sc":sc,"tipo":tipo,"c1":c1,"c4":c4,"vr":vr,
               "tp":fp(tp1),"sl":fp(sl_est),"tpp":round(tp_pct,1),"slp":round(sl_pct,1),
               "apal":apal,"em":em,"tags":tags}
    return None

def dbg(par,sym):
    v15=ohlc(par,15)
    if not v15 or len(v15)<22:return f"⚠️{sym}:sin datos"
    Hi=[float(x[2])for x in v15[-22:]]
    Lo=[float(x[3])for x in v15[-22:]]
    Cl=[float(x[4])for x in v15[-22:]]
    V=[float(x[5])for x in v15[-22:]]
    p=Cl[-1]
    vol_avg=sum(V[-21:-1])/max(len(V[-21:-1]),1)
    vr=V[-1]/max(vol_avg,0.0001)
    c1=(Cl[-1]-Cl[-2])/max(Cl[-2],0.001)*100
    c4=(Cl[-1]-Cl[-5])/max(Cl[-5],0.001)*100
    sd=sesgo_diario(par)
    reg=regime(Cl)
    sc_c,ra,rh=compresion(Hi,Lo,V)
    liq=zona_liquidez(Hi,Lo,p)
    ch_l=choch_h1(par,"long",sc_c)
    ch_s=choch_h1(par,"short",sc_c)
    bos_l,vbl=bos_h4(par,"long",sc_c)
    bos_s,vbs=bos_h4(par,"short",sc_c)
    fib_l=fibonacci_h4(par,"long")
    fib_s=fibonacci_h4(par,"short")
    zd=min(Lo[-15:]);zo=max(Hi[-15:])
    dd=(p-zd)/max(zd,0.001)*100
    do=(zo-p)/max(p,0.001)*100
    sdn={"a":"alc","b":"baj","n":"neu"}.get(sd,"?")
    rn={"u":"↑","d":"↓","r":"rng"}.get(reg,"?")
    alerta=alerta_previa(par,sym,sc_c,liq)
    return(f"📊*{sym}*`{fp(p)}`\n"
           f"Diario:`{sdn}` Reg:`{rn}` Ses:`{sesion_actual()}`\n"
           f"CHoCH:{'L✅'if ch_l else''}{'S✅'if ch_s else''}{'❌'if not ch_l and not ch_s else''}\n"
           f"BOS:{'L✅'if bos_l else''}{'S✅'if bos_s else''}{'❌'if not bos_l and not bos_s else''}\n"
           f"Fib:{'L✅'if fib_l else''}{'S✅'if fib_s else''}{'❌'if not fib_l and not fib_s else''}\n"
           f"Liq:{'✅'if liq else'❌'} Comp:`{sc_c}pts` Vol:`{vr:.1f}x`\n"
           f"1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`\n"
           f"Sop:`{dd:.1f}%` Res:`{do:.1f}%`\n"
           f"{'⚠️Pre-señal activa'if alerta else''}")

def run_bg():
    global D
    now=datetime.now(Z);hoy=now.strftime("%d/%m")
    if D["f"]!=hoy:D={"l":0,"s":0,"f":hoy}
    if D["l"]>=4 and D["s"]>=3:return
    alertas=[]
    ls,ss=[],[]
    for par,sym in P:
        v15=ohlc(par,15)
        if len(v15)<22:continue
        Hi=[float(x[2])for x in v15[-22:]]
        Lo=[float(x[3])for x in v15[-22:]]
        Cl=[float(x[4])for x in v15[-22:]]
        V=[float(x[5])for x in v15[-22:]]
        p=Cl[-1]
        sc_c,ra,rh=compresion(Hi,Lo,V)
        liq=zona_liquidez(Hi,Lo,p)
        if alerta_previa(par,sym,sc_c,liq):
            alertas.append(f"⚠️*{sym}*`{fp(p)}`Comp:{sc_c}pts+Liq — vigilar ruptura")
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
            msg="🔍*Sin señales — Pre-alertas activas:*\n"+"\n".join(alertas)
            send(msg)
        return
    msg=f"⚡*PUMP RADAR v6.4—{now.strftime('%H:%M')}ARG*\n_H4 Fib|CHoCH flex|SL est_\n\n"
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
    send("🔬*DEBUG v6.4—H4 Fib|CHoCH flex|Pre-alerta*")
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
                    if t=="/start":send("👋*Pump Radar v6.4*\n/analizar /resumen /debug /ayuda")
                    elif t=="/analizar":run()
                    elif t=="/resumen":send(f"📊Hoy:{D['l']}L {D['s']}S")
                    elif t=="/debug":threading.Thread(target=run_debug,daemon=True).start()
                    elif t=="/ayuda":send("⏰10:00|13:30|20:30 ARG\nH4 Fib|CHoCH flex|Pre-alertas\n/debug diagnóstico")
        except:pass
        time.sleep(2)

schedule.every().day.at("13:00").do(run)
schedule.every().day.at("16:30").do(run)
schedule.every().day.at("23:30").do(run)

send("✅*Pump Radar v6.4*|Coinbase|H4 Fib|CHoCH flex|Pre-alertas")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)