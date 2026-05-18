import os, requests, time, threading
from datetime import datetime, timedelta
from flask import Flask
import pytz

T = os.environ.get("TELEGRAM_TOKEN")
C = os.environ.get("TELEGRAM_CHAT_ID")
Z = pytz.timezone("America/Argentina/Buenos_Aires")
P = [("BTC-USD","BTC"),("ETH-USD","ETH"),("SOL-USD","SOL"),("XRP-USD","XRP"),("ADA-USD","ADA")]
D = {"l":0,"s":0,"f":""}
H = {}
app = Flask(__name__)

@app.route("/")
def home():
    return "Pump Radar v9 activo", 200

def send(t):
    try:
        requests.post(
            f"https://api.telegram.org/bot{T}/sendMessage",
            json={"chat_id": C, "text": t, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def ohlc(par, iv=60, limite=210):
    try:
        seg = {15:900, 60:3600, 240:14400, 1440:86400}.get(iv, 3600)
        r = requests.get(
            f"https://api.exchange.coinbase.com/products/{par}/candles",
            params={"granularity": seg, "limit": limite},
            timeout=8
        )
        if r.ok:
            return list(reversed(r.json()))
    except:
        pass
    return []

def fp(x):
    return f"${x:,.2f}" if x > 100 else f"${x:,.4f}" if x > 1 else f"${x:,.6f}"

# SESION
# NY abre 9:30 ET = 10:30 ARG
# Scheduler avisa: 10:00 (preNY), 15:30 (mitad NY), 21:00 (preAsia)
def sesion():
    h  = datetime.now(Z).hour
    m  = datetime.now(Z).minute
    hm = h * 60 + m
    if 10*60+30 <= hm < 17*60:  return "ny",   65
    if 4*60     <= hm < 10*60+30: return "eu",  62
    if hm >= 21*60 or hm < 3*60: return "asia", 68
    return "off", 65

# SESGO DIARIO
# Mira los ultimos 10 dias. Si hace maximos y minimos mas bajos = bajista. Al reves = alcista.
def sesgo_diario(par):
    v = ohlc(par, 1440, 15)
    if len(v) < 10: return "n"
    Hi = [float(x[2]) for x in v[-10:]]
    Lo = [float(x[3]) for x in v[-10:]]
    Cl = [float(x[4]) for x in v[-10:]]
    ma = sum(Cl) / len(Cl)
    if Hi[-1] < Hi[-3] and Lo[-1] < Lo[-3] and Cl[-1] < ma: return "b"
    if Hi[-1] > Hi[-3] and Lo[-1] > Lo[-3] and Cl[-1] > ma: return "a"
    return "n"

# EMA — calculo estandar
def ema(valores, periodo):
    if len(valores) < periodo: return None
    k  = 2 / (periodo + 1)
    e  = sum(valores[:periodo]) / periodo
    for v in valores[periodo:]:
        e = v * k + e * (1 - k)
    return e

# EMA 50/200 EN H4
# Si EMA50 > EMA200 = tendencia alcista del par
# Si EMA50 < EMA200 = tendencia bajista del par
# Necesita 200 velas H4 — le pedimos 210 a Coinbase para tener margen
def tendencia_ema(par):
    v = ohlc(par, 240, 210)
    if len(v) < 200: return "n"
    Cl    = [float(x[4]) for x in v]
    e50   = ema(Cl, 50)
    e200  = ema(Cl, 200)
    if e50 is None or e200 is None: return "n"
    if e50 > e200 * 1.001: return "a"   # 50 claramente sobre 200 = alcista
    if e50 < e200 * 0.999: return "b"   # 50 claramente bajo 200  = bajista
    return "n"                           # muy juntas = sin tendencia clara

# ATR EN H1
# Mide el rango promedio de las ultimas 14 velas
# Si el ATR viene cayendo varios periodos = mercado quieto = buena condicion
# Retorna: atr_actual, atr_promedio, esta_quieto (bool)
def atr_h1(par, periodo=14):
    v = ohlc(par, 60, 30)
    if len(v) < periodo + 2: return 0, 0, False
    trs = []
    for i in range(1, len(v)):
        hi  = float(v[i][2])
        lo  = float(v[i][3])
        pc  = float(v[i-1][4])
        tr  = max(hi - lo, abs(hi - pc), abs(lo - pc))
        trs.append(tr)
    atr_actual   = sum(trs[-periodo:])   / periodo
    atr_promedio = sum(trs[-periodo*2:-periodo]) / periodo if len(trs) >= periodo*2 else atr_actual
    # Quieto = ATR actual menor al promedio reciente (se esta comprimiendo)
    quieto = atr_actual < atr_promedio * 0.85
    return round(atr_actual, 6), round(atr_promedio, 6), quieto

# ZONAS 24H — reemplaza Fibonacci
# Maximo y minimo de las ultimas 24 horas
# Si el precio esta cerca (menos de 1.5%) = zona clave con ordenes acumuladas
def zonas_24h(par, p):
    v = ohlc(par, 60, 26)
    if len(v) < 24: return False, "ninguna", 0.0
    Hi      = [float(x[2]) for x in v[-24:-2]]
    Lo      = [float(x[3]) for x in v[-24:-2]]
    max_24h = max(Hi)
    min_24h = min(Lo)
    d_max   = abs(p - max_24h) / max(p, 0.001) * 100
    d_min   = abs(p - min_24h) / max(p, 0.001) * 100
    if d_max < 1.5: return True, "max24", round(d_max, 2)
    if d_min < 1.5: return True, "min24", round(d_min, 2)
    return False, "ninguna", 0.0

# SL ESTRUCTURAL
# Stop loss en el minimo (long) o maximo (short) de las ultimas 10 velas H1
def sl_estructural(par, tipo):
    v = ohlc(par, 60, 12)
    if len(v) < 10: return 0
    Hi = [float(x[2]) for x in v[-10:]]
    Lo = [float(x[3]) for x in v[-10:]]
    return min(Lo) if tipo == "long" else max(Hi)

# ANALISIS PRINCIPAL
def ana(par, sym, forzar=False):
    ses, umbral_ses = sesion()
    if ses == "off" and not forzar: return None

    # Datos H1
    v1h = ohlc(par, 60, 30)
    if len(v1h) < 25: return None

    Cl  = [float(x[4]) for x in v1h[-25:]]
    Vv  = [float(x[5]) for x in v1h[-25:]]
    p   = Cl[-1]

    # Volumen — fix vela recien abierta sin volumen
    vol_avg = sum(Vv[-21:-1]) / max(len(Vv[-21:-1]), 1)
    vr      = Vv[-1] / max(vol_avg, 0.0001)
    if vr < 0.1:
        vr = Vv[-2] / max(vol_avg, 0.0001)
        if vr < 0.1: return None

    c1 = (Cl[-1] - Cl[-2]) / max(Cl[-2], 0.001) * 100
    c4 = (Cl[-1] - Cl[-5]) / max(Cl[-5], 0.001) * 100

    # Si ya se movio mucho, llegamos tarde
    if abs(c1) > 1.5: return None

    # Indicadores
    sd                       = sesgo_diario(par)
    tend                     = tendencia_ema(par)
    atr_act, atr_avg, quieto = atr_h1(par)
    zona_cerca, zona_tipo, zona_dist = zonas_24h(par, p)

    # ATR: si no esta quieto, no hay setup
    if not quieto: return None

    for tipo in ["long", "short"]:
        k = f"{sym}_{tipo}"
        if k in H and datetime.now(Z) - H[k] < timedelta(hours=4): continue

        # EMA 50/200: solo operar a favor de la tendencia
        # Si tendencia es alcista, solo longs. Si bajista, solo shorts.
        # Si neutral, permitir pero con umbral mas alto.
        if tend == "a" and tipo == "short": continue
        if tend == "b" and tipo == "long":  continue

        # Filtro momentum
        if tipo == "long"  and c1 < 0 and c4 < 0: continue
        if tipo == "short" and c1 > 0 and c4 > 0: continue
        if tipo == "long"  and c4 > 3:  continue
        if tipo == "short" and c4 < -3: continue

        # Sesgo diario
        a_favor = (sd == "b" and tipo == "short") or (sd == "a" and tipo == "long")
        contra  = (sd == "b" and tipo == "long")  or (sd == "a" and tipo == "short")

        # SL y TP
        sl_est = sl_estructural(par, tipo)
        if sl_est == 0: continue
        sl_pct = abs(p - sl_est) / max(p, 0.001) * 100
        if sl_pct < 0.3 or sl_pct > 5: continue

        tp_ratio = 2.5 if a_favor else 1.8
        tp_pct   = sl_pct * tp_ratio
        tp1      = p * (1 + tp_pct/100) if tipo == "long" else p * (1 - tp_pct/100)

        # SCORE
        sc = 40  # base mas alta porque ya filtramos con ATR y EMA

        # EMA alineada con la trade
        if tend == "a" and tipo == "long":  sc += 20
        if tend == "b" and tipo == "short": sc += 20
        if tend == "n": sc += 0  # neutral, ni suma ni resta

        # Sesgo diario
        sc += 15 if a_favor else -15 if contra else 0

        # Zona 24h
        if zona_cerca:
            if (zona_tipo == "min24" and tipo == "long") or (zona_tipo == "max24" and tipo == "short"):
                sc += 15  # zona coincide con direccion = muy buena entrada
            else:
                sc += 5

        # Volumen
        sc += 12 if vr > 1.5 else 5 if vr > 0.8 else -12 if vr < 0.3 else 0

        # Momentum suave a favor
        sc += 5 if tipo == "long" and 0 < c4 <= 3 else 5 if tipo == "short" and -3 <= c4 < 0 else 0

        # Sesion
        sc += 5 if ses == "ny" else 3 if ses == "eu" else 1 if ses == "asia" else 0

        if vr < 1: sc = int(sc * 0.92)
        sc = min(sc, 100)

        umbral = umbral_ses if not forzar else 58
        if contra:  umbral = max(umbral, 78)
        if tend == "n": umbral = max(umbral, 75)  # sin tendencia clara, exigir mas
        if sc < umbral: continue

        H[k] = datetime.now(Z)

        em   = "🟢" if tipo == "long" else "🔴"
        sdt  = {"a":"📈Alc","b":"📉Baj","n":"➡️Neu"}.get(sd, "")
        tdt  = {"a":"EMA↑","b":"EMA↓","n":"EMA→"}.get(tend, "")
        zona_tag = f"Zona:{zona_tipo}({zona_dist}%)" if zona_cerca else ""
        atr_tag  = f"ATR:{round(atr_act/atr_avg*100)}%avg"
        apal     = 5 if sc >= 85 else 3

        tags = [sdt, tdt, atr_tag]
        if zona_tag: tags.append(zona_tag)
        tags.append(f"Vol:{vr:.1f}x|{ses.upper()}")

        return {
            "sym": sym, "p": fp(p), "sc": sc, "tipo": tipo,
            "c1": c1, "c4": c4, "vr": vr,
            "tp": fp(tp1), "sl": fp(sl_est),
            "tpp": round(tp_pct, 1), "slp": round(sl_pct, 1),
            "apal": apal, "em": em, "tags": tags
        }

    return None

# DEBUG — muestra todos los indicadores de cada par
def dbg(par, sym):
    v1h = ohlc(par, 60, 30)
    if not v1h or len(v1h) < 25: return f"⚠️{sym}:sin datos"

    Cl  = [float(x[4]) for x in v1h[-25:]]
    Vv  = [float(x[5]) for x in v1h[-25:]]
    p   = Cl[-1]
    vol_avg = sum(Vv[-21:-1]) / max(len(Vv[-21:-1]), 1)
    vr_act  = Vv[-1] / max(vol_avg, 0.0001)
    vr_prev = Vv[-2] / max(vol_avg, 0.0001)
    c1 = (Cl[-1] - Cl[-2]) / max(Cl[-2], 0.001) * 100
    c4 = (Cl[-1] - Cl[-5]) / max(Cl[-5], 0.001) * 100

    sd                       = sesgo_diario(par)
    tend                     = tendencia_ema(par)
    atr_act, atr_avg, quieto = atr_h1(par)
    zona_cerca, zona_tipo, zona_dist = zonas_24h(par, p)
    ses, _ = sesion()

    sdn  = {"a":"alc","b":"baj","n":"neu"}.get(sd,   "?")
    tdn  = {"a":"alcista (EMA50>200)","b":"bajista (EMA50<200)","n":"neutral"}.get(tend, "?")
    atrn = "QUIETO ✅" if quieto else "moviendose ❌"

    return (f"📊*{sym}*`{fp(p)}`\n"
            f"Tendencia H4:`{tdn}`\n"
            f"Diario:`{sdn}` Ses:`{ses}`\n"
            f"ATR H1:`{atrn}`\n"
            f"ATR actual:`{atr_act}` avg:`{atr_avg}`\n"
            f"Zona24h:`{zona_tipo}` dist:`{zona_dist}%`\n"
            f"Vol actual:`{vr_act:.1f}x` prev:`{vr_prev:.1f}x`\n"
            f"1h:`{c1:+.1f}%` 4h:`{c4:+.1f}%`")

def run_bg(forzar=False):
    global D
    now = datetime.now(Z)
    hoy = now.strftime("%d/%m")
    if D["f"] != hoy: D = {"l":0,"s":0,"f":hoy}
    if D["l"] >= 4 and D["s"] >= 3: return

    alertas = []
    ls, ss  = [], []

    for par, sym in P:
        v1h = ohlc(par, 60, 30)
        if v1h and len(v1h) >= 25:
            Cl  = [float(x[4]) for x in v1h[-25:]]
            p   = Cl[-1]
            atr_act, atr_avg, quieto = atr_h1(par)
            tend = tendencia_ema(par)
            sd   = sesgo_diario(par)
            zona_cerca, zona_tipo, _ = zonas_24h(par, p)
            # Pre-alerta: mercado quieto + tendencia clara
            if quieto and tend != "n":
                dir_txt  = "SHORT" if tend == "b" else "LONG"
                zona_t   = f"Zona:{zona_tipo}" if zona_cerca else ""
                sdt      = {"a":"📈","b":"📉"}.get(sd, "")
                alertas.append(f"⚠️*{sym}*`{fp(p)}` EMA:{dir_txt} ATR:quieto {zona_t} {sdt}")

        r = ana(par, sym, forzar)
        if r:
            if r["tipo"] == "long"  and D["l"] < 4: ls.append(r)
            elif r["tipo"] == "short" and D["s"] < 3: ss.append(r)
        time.sleep(0.5)

    ls.sort(key=lambda x: x["sc"], reverse=True)
    ss.sort(key=lambda x: x["sc"], reverse=True)
    tl, ts = ls[:2], ss[:1]

    if not tl and not ts:
        if alertas:
            send("🔍*Sin señales — Pre-alertas:*\n" + "\n".join(alertas))
        else:
            ses, _ = sesion()
            send(f"🔍Sin condiciones | Ses:`{ses}`")
        return

    msg = f"⚡*PUMP RADAR v9—{now.strftime('%H:%M')}ARG*\n_EMA 50/200 | ATR | Zonas24h_\n\n"
    for r in tl + ts:
        signo = "+" if r["tipo"] == "long" else "-"
        msg += (f"{r['em']}*{r['tipo'].upper()}—{r['sym']}*|`{r['sc']}/100`\n"
                f"📍`{r['p']}`|Vol:`{r['vr']:.1f}x`|1h:`{r['c1']:+.1f}%`\n"
                f"🎯`{r['tp']}`({signo}{r['tpp']}%)|🛑`{r['sl']}`(-{r['slp']}%)|⚡`{r['apal']}x`\n"
                f"_{', '.join(r['tags'])}_\n\n")
        if r["tipo"] == "long": D["l"] += 1
        else:                   D["s"] += 1

    msg += f"📊{D['l']}L {D['s']}S|⚠️Experimental"
    send(msg)

def run(forzar=False):
    threading.Thread(target=lambda: run_bg(forzar), daemon=True).start()

def run_debug():
    send("🔬*DEBUG v9 — EMA 50/200 | ATR | Zonas24h*")
    for par, sym in P:
        send(dbg(par, sym))
        time.sleep(0.5)
    send("✅Debug completo")

def listen():
    last = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{T}/getUpdates",
                params={"offset": last+1, "timeout": 10},
                timeout=15
            )
            if r.ok:
                for u in r.json().get("result", []):
                    last = u["update_id"]
                    t = (u.get("message") or {}).get("text") or ""
                    if t == "/start":
                        send("👋*Pump Radar v9*\n/analizar /resumen /debug /ayuda")
                    elif t == "/analizar":
                        run(forzar=True)
                    elif t == "/resumen":
                        send(f"📊Hoy:{D['l']}L {D['s']}S")
                    elif t == "/debug":
                        threading.Thread(target=run_debug, daemon=True).start()
                    elif t == "/ayuda":
                        send("⏰10:00(preNY)|15:30(NY)|21:00(preAsia)\n/analizar fuerza\n/debug diagnostico")
        except:
            pass
        time.sleep(2)

def servidor():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

# SCHEDULER
# 10:00 ARG = 30 min antes de NY
# 15:30 ARG = mitad sesion NY
# 21:00 ARG = antes de Asia
def scheduler():
    ultima = ""
    while True:
        hora = datetime.now(Z).strftime("%H:%M")
        if hora in ["10:00", "15:30", "21:00"] and hora != ultima:
            ultima = hora
            run()
        time.sleep(30)

send("✅*Pump Radar v9*|EMA 50/200|ATR H1|Zonas24h|Horarios ARG")
run(forzar=True)
threading.Thread(target=listen,    daemon=True).start()
threading.Thread(target=scheduler, daemon=True).start()
threading.Thread(target=servidor,  daemon=True).start()
while True:
    time.sleep(60)
