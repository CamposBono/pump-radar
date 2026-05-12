import os,requests,time,schedule,threading
from datetime import datetime,timedelta
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

FEES=0.001
senales_hoy={"long":0,"short":0,"fecha":""}
ultima_senal={}  # {simbolo_tipo: datetime}

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

def tendencia_4h(par):
    """Retorna 'alcista', 'bajista' o 'neutral'"""
    velas=get_ohlc(par,240)
    if len(velas)<6:return"neutral"
    closes=[float(v[4])for v in velas[-6:]]
    highs=[float(v[2])for v in velas[-6:]]
    lows=[float(v[3])for v in velas[-6:]]
    # Tendencia alcista: HH y HL
    hh=highs[-1]>highs[-3]
    hl=lows[-1]>lows[-3]
    # Tendencia bajista: LH y LL
    lh=highs[-1]<highs[-3]
    ll=lows[-1]<lows[-3]
    if hh and hl:return"alcista"
    if lh and ll:return"bajista"
    return"neutral"

def calcular_tp_dinamico(closes,tipo):
    """TP basado en volatilidad promedio de las ultimas 10 velas"""
    rangos=[abs(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(1,min(10,len(closes)))]
    vol_prom=sum(rangos)/len(rangos) if rangos else 1.5
    # TP = 2x la volatilidad promedio, minimo 5%, maximo 15%
    tp_pct=max(5,min(15,vol_prom*2))
    sl_pct=max(3,min(6,vol_prom_precio*0.8))
    return tp_pct,sl_pct

def ya_alertado(simbolo,tipo):
    """Evita duplicados en menos de 2 horas"""
    key=f"{simbolo}_{tipo}"
    if key in ultima_senal:
        diff=datetime.now(ARG)-ultima_senal[key]
        if diff<timedelta(hours=2):return True
    return False

def registrar_senal(simbolo,tipo):
    key=f"{simbolo}_{tipo}"
    ultima_senal[key]=datetime.now(ARG)

def calcular_señal(par_kraken,simbolo):
    # Verificar filtro de duplicados
    # (se verifica antes de hacer consultas para ahorrar tiempo)

    velas=get_ohlc(par_kraken,60)
    if len(velas)<20:return None

    opens=[float(v[1])for v in velas[-21:]]
    highs=[float(v[2])for v in velas[-21:]]
    lows=[float(v[3])for v in velas[-21:]]
    closes=[float(v[4])for v in velas[-21:]]
    volumes=[float(v[6])for v in velas[-21:]]

    # Vela actual en formacion (ultima) + velas cerradas
    precio=closes[-1]
    vol_actual=volumes[-1]
    vol_prom=sum(volumes[-11:-1])/10
    vol_ratio=vol_actual/max(vol_prom,0.0001)

    c1h=(closes[-1]-closes[-2])/max(closes[-2],0.0001)*100
    c4h=(closes[-1]-closes[-5])/max(closes[-5],0.0001)*100

    # Confirmacion de 2 velas consecutivas
    velas_alc=closes[-1]>opens[-1] and closes[-2]>opens[-2]
    velas_baj=closes[-1]<opens[-1] and closes[-2]<opens[-2]

    # SMC
    max_prev=max(highs[-10:-2])
    min_prev=min(lows[-10:-2])
    bos_l=highs[-1]>max_prev and highs[-2]>max_prev  # 2 velas rompiendo
    bos_s=lows[-1]<min_prev and lows[-2]<min_prev

    choch_l=closes[-1]>closes[-3] and closes[-3]>closes[-5] and closes[-5]<closes[-7]
    choch_s=closes[-1]<closes[-3] and closes[-3]<closes[-5] and closes[-5]>closes[-7]

    fvg_l=len(lows)>=3 and lows[-1]>highs[-3]
    fvg_s=len(highs)>=3 and highs[-1]<lows[-3]

    fp=lambda p:(f"${p:,.2f}" if p>100 else f"${p:,.4f}" if p>1 else f"${p:,.6f}")

    # TP dinamico
    rangos=[abs(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(1,10)]
    vol_prom_precio=sum(rangos)/len(rangos) if rangos else 1.5
    tp_pct=max(5,min(15,vol_prom_precio*2.5))
    sl_pct=max(3,min(6,vol_prom_precio*0.9))

    # LONG
    ls=0;lsg=[]
    conf=0
    if bos_l and velas_alc:ls+=40;lsg.append("📈 BOS alcista (2 velas)");conf+=1
    if choch_l:ls+=30;lsg.append("🔄 CHoCH alcista");conf+=1
    if fvg_l:ls+=20;lsg.append("⬜ FVG alcista");conf+=1
    if vol_ratio>0.8 and velas_alc:ls+=15;lsg.append(f"💪 Vol {vol_ratio:.1f}x")
    if c4h>0.5:ls+=10;lsg.append(f"🌱 +{c4h:.1f}% en 4h")

    if ls>=55 and conf>=2 and vol_ratio>=0.8 and not ya_alertado(simbolo,"long"):
        tend=tendencia_4h(par_kraken)
        if tend in["alcista","neutral"]:
            tp1=precio*(1+tp_pct/100)
            sl=precio*(1-sl_pct/100)
            ganancia_neta=tp_pct-FEES*100
            apal=5 if ls>=80 else 3
            registrar_senal(simbolo,"long")
            return{"sym":simbolo,"precio":fp(precio),"score":ls,"sig":lsg,
                   "c1h":c1h,"c4h":c4h,"vr":vol_ratio,"tipo":"long","tend4h":tend,
                   "tp1":fp(tp1),"sl":fp(sl),"tp_pct":tp_pct,"sl_pct":sl_pct,
                   "ganancia":ganancia_neta,"apal":apal}

    # SHORT
    ss=0;ssg=[]
    conf_s=0
    if bos_s and velas_baj:ss+=40;ssg.append("📉 BOS bajista (2 velas)");conf_s+=1
    if choch_s:ss+=30;ssg.append("🔄 CHoCH bajista");conf_s+=1
    if fvg_s:ss+=20;ssg.append("⬜ FVG bajista");conf_s+=1
    if vol_ratio>0.8 and velas_baj:ss+=15;ssg.append(f"💪 Vol {vol_ratio:.1f}x")
    if c4h<-0.5:ss+=10;ssg.append(f"🔻 {c4h:.1f}% en 4h")

    if ss>=55 and conf_s>=2 and vol_ratio>=0.8 and not ya_alertado(simbolo,"short"):
        tend=tendencia_4h(par_kraken)
        if tend in["bajista","neutral"]:
            tp1=precio*(1-tp_pct/100)
            sl=precio*(1+sl_pct/100)
            ganancia_neta=tp_pct-FEES*100
            apal=3 if ss>=75 else 2
            registrar_senal(simbolo,"short")
            return{"sym":simbolo,"precio":fp(precio),"score":ss,"sig":ssg,
                   "c1h":c1h,"c4h":c4h,"vr":vol_ratio,"tipo":"short","tend4h":tend,
                   "tp1":fp(tp1),"sl":fp(sl),"tp_pct":tp_pct,"sl_pct":sl_pct,
                   "ganancia":ganancia_neta,"apal":apal}
    return None

def run():
    global senales_hoy
    now=datetime.now(ARG)
    fecha_hoy=now.strftime("%d/%m")

    if senales_hoy["fecha"]!=fecha_hoy:
        senales_hoy={"long":0,"short":0,"fecha":fecha_hoy}

    if senales_hoy["long"]>=3 and senales_hoy["short"]>=2:
        print("Limite diario alcanzado");return

    print(f"[{now.strftime('%H:%M')}] Analizando {len(PARES)} pares H1+4h SMC...")
    longs,shorts=[],[]

    for par,sym in PARES:
        r=calcular_señal(par,sym)
        if r:
            if r["tipo"]=="long" and senales_hoy["long"]<3:longs.append(r)
            elif r["tipo"]=="short" and senales_hoy["short"]<2:shorts.append(r)
        time.sleep(1.5)

    longs.sort(key=lambda x:x["score"],reverse=True)
    shorts.sort(key=lambda x:x["score"],reverse=True)
    tl=longs[:2];ts=shorts[:1]

    if not tl and not ts:
        print("Sin senales");return

    hora=now.strftime("%H:%M")
    msg=f"📡 *PUMP RADAR — {hora} ARG*\n_SMC H1 confirmado por 4h_\n\n"

    for r in tl:
        tend_emoji="🟢" if r["tend4h"]=="alcista" else "⚪"
        msg+=f"🟢 *LONG — {r['sym']}*\n"
        msg+=f"Score: `{r['score']}/100` | Vol: `{r['vr']:.1f}x` | 4h: {tend_emoji} {r['tend4h']}\n"
        msg+=f"📍 Entrada: `{r['precio']}`\n"
        msg+=f"🎯 TP1: `{r['tp1']}` (+{r['tp_pct']:.1f}%)\n"
        msg+=f"🛑 SL: `{r['sl']}` (-{r['sl_pct']:.1f}%)\n"
        msg+=f"⚡ Apalancamiento: `{r['apal']}x`\n"
        msg+=f"💰 Ganancia neta est: `+{r['ganancia']:.1f}%`\n"
        msg+=f"1h: `{r['c1h']:+.2f}%` | 4h: `{r['c4h']:+.2f}%`\n"
        msg+=f"_{', '.join(r['sig'])}_\n\n"
        senales_hoy["long"]+=1

    for r in ts:
        tend_emoji="🔴" if r["tend4h"]=="bajista" else "⚪"
        msg+=f"🔴 *SHORT — {r['sym']}*\n"
        msg+=f"Score: `{r['score']}/100` | Vol: `{r['vr']:.1f}x` | 4h: {tend_emoji} {r['tend4h']}\n"
        msg+=f"📍 Entrada: `{r['precio']}`\n"
        msg+=f"🎯 TP1: `{r['tp1']}` (-{r['tp_pct']:.1f}%)\n"
        msg+=f"🛑 SL: `{r['sl']}` (+{r['sl_pct']:.1f}%)\n"
        msg+=f"⚡ Apalancamiento: `{r['apal']}x`\n"
        msg+=f"💰 Ganancia neta est: `+{r['ganancia']:.1f}%`\n"
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
                        send("👋 *Pump Radar H1 — SMC avanzado*\n\nH1 confirmado por 4h\nTP dinámico según volatilidad\nSin señales duplicadas\n\n/analizar — análisis ahora\n/resumen — señales de hoy\n/ayuda — cómo operar")
                    elif t=="/analizar":
                        send("🔍 Analizando H1 + confirmando 4h...");run()
                    elif t=="/resumen":
                        send(f"📊 *Señales de hoy:*\n🟢 Long: {senales_hoy['long']}/3\n🔴 Short: {senales_hoy['short']}/2\nFecha: {senales_hoy['fecha']}")
                    elif t=="/ayuda":
                        send("*Cómo operar:*\n\n📍 *Entrada* — precio al recibir señal\n🎯 *TP1* — objetivo dinámico según volatilidad\n🛑 *SL* — salís sin dudar si llega acá\n⚡ *Apal* — sugerido según score\n4h confirma la dirección de H1\n\n*Regla de oro:*\nSi el precio no se mueve en 2-3 velas H1, revisá la señal.\n\n_Verificá en tu exchange antes de entrar._")
        except Exception as e:
            print(f"Err:{e}")
        time.sleep(2)

schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)

send("✅ *Pump Radar actualizado*\nH1 + 4h | TP dinámico | Sin duplicados\nHorarios: 9am, 3pm y 8pm ARG")
run()
threading.Thread(target=listen,daemon=True).start()
while True:schedule.run_pending();time.sleep(30)
