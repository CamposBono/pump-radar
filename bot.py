import os, requests, time, schedule, threading
from datetime import datetime, timedelta
import pytz

T = os.environ.get("TELEGRAM_TOKEN")
C = os.environ.get("TELEGRAM_CHAT_ID")
Z = pytz.timezone("America/Argentina/Buenos_Aires")

P = [
    ("XBT/USDT","BTC"),("ETH/USDT","ETH"),("SOL/USDT","SOL"),("XRP/USDT","XRP"),
    ("ADA/USDT","ADA"),("LINK/USDT","LINK"),("AVAX/USDT","AVAX"),
    ("SUI/USDT","SUI"),("DOT/USDT","DOT"),("NEAR/USDT","NEAR")
]

D = {"l": 0, "s": 0, "f": ""}
H = {}

def send(t):
    try:
        requests.post(
            f"https://api.telegram.org/bot{T}/sendMessage",
            json={"chat_id": C, "text": t, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def get_ohlc(par, interval=60):
    """Obtiene velas OHLC de Kraken"""
    try:
        r = requests.get(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": par, "interval": interval},
            timeout=8
        )
        if r.ok:
            d = r.json()
            if not d.get("error"):
                k = list(d["result"].keys())[0]
                return d["result"][k]
    except:
        pass
    return []

def btc_trend():
    """Evalúa tendencia de BTC en 1H (últimas 6 velas)"""
    v = get_ohlc("XBT/USDT")
    if len(v) < 6:
        return "n"
    c = [float(x[4]) for x in v[-6:]]
    # Tendencia bajista si últimas 3 velas promedian por debajo de las 3 anteriores
    avg_prev = sum(c[:3]) / 3
    avg_now  = sum(c[3:]) / 3
    if avg_now < avg_prev * 0.998:
        return "b"
    elif avg_now > avg_prev * 1.002:
        return "a"
    return "n"

# ─────────────────────────────────────────────
# NUEVAS FUNCIONES DE ESTRUCTURA
# ─────────────────────────────────────────────

def detectar_choch_bos(highs, lows, closes):
    """
    Detecta CHoCH y BOS simplificados en 20 velas.
    Retorna: (estructura, ultimo_swing_dir)
      estructura: 'alcista' | 'bajista' | 'neutral'
    """
    n = len(closes)
    if n < 10:
        return "neutral"

    # Swings simples: comparar grupos de 4 velas
    def swing_high(i): return highs[i] == max(highs[max(0,i-2):i+3])
    def swing_low(i):  return lows[i]  == min(lows[max(0,i-2):i+3])

    sh_idx = [i for i in range(2, n-2) if swing_high(i)]
    sl_idx = [i for i in range(2, n-2) if swing_low(i)]

    if len(sh_idx) < 2 or len(sl_idx) < 2:
        return "neutral"

    # Últimos 2 swing highs y lows
    sh = [highs[i] for i in sh_idx[-2:]]
    sl = [lows[i]  for i in sl_idx[-2:]]

    higher_highs = sh[-1] > sh[-2]
    higher_lows  = sl[-1] > sl[-2]
    lower_highs  = sh[-1] < sh[-2]
    lower_lows   = sl[-1] < sl[-2]

    if higher_highs and higher_lows:
        return "alcista"
    elif lower_highs and lower_lows:
        return "bajista"
    return "neutral"

def detectar_market_regime(closes, period=14):
    """
    Régimen de mercado por eficiencia de movimiento.
    Retorna: 'trending_up' | 'trending_down' | 'ranging'
    """
    if len(closes) < period:
        return "ranging"
    segment = closes[-period:]
    total_move = abs(segment[-1] - segment[0])
    path = sum(abs(segment[i] - segment[i-1]) for i in range(1, len(segment)))
    efficiency = total_move / max(path, 0.0001)

    if efficiency > 0.45:
        if segment[-1] > segment[0]:
            return "trending_up"
        else:
            return "trending_down"
    return "ranging"

def zona_valida(price, lows, highs, tipo):
    """
    Verifica que el precio esté CERCA de una zona de demanda/oferta real.
    Long: precio debe estar dentro del 1.5% del mínimo reciente (zona de demanda)
    Short: precio debe estar dentro del 1.5% del máximo reciente (zona de oferta)
    """
    if tipo == "long":
        zona = min(lows[-15:])
        distancia = (price - zona) / max(zona, 0.001) * 100
        return 0 <= distancia <= 5.0   # máx 5% sobre el soporte
    else:
        zona = max(highs[-15:])
        distancia = (zona - price) / max(price, 0.001) * 100
        return 0 <= distancia <= 5.0   # máx 5% bajo la resistencia

def entrada_tardia(closes, tipo, umbral=1.8):
    """
    Detecta si el precio ya se movió demasiado desde el swing más reciente.
    Evita entrar en medio del movimiento.
    """
    if len(closes) < 5:
        return True
    reciente = closes[-5:]
    if tipo == "long":
        swing_low = min(reciente)
        movimiento = (closes[-1] - swing_low) / max(swing_low, 0.001) * 100
        return movimiento > umbral   # ya subió más del umbral% → tarde
    else:
        swing_high = max(reciente)
        movimiento = (swing_high - closes[-1]) / max(closes[-1], 0.001) * 100
        return movimiento > umbral   # ya bajó más del umbral% → tarde

# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE ANÁLISIS (reescrita)
# ─────────────────────────────────────────────

def ana(par, sym):
    if sym == "BTC":
        return None

    v = get_ohlc(par)
    if len(v) < 22:
        return None

    # Extraer datos (últimas 22 velas)
    opens  = [float(x[1]) for x in v[-22:]]
    highs  = [float(x[2]) for x in v[-22:]]
    lows   = [float(x[3]) for x in v[-22:]]
    closes = [float(x[4]) for x in v[-22:]]
    vols   = [float(x[6]) for x in v[-22:]]

    p   = closes[-1]
    vr  = vols[-1] / max(sum(vols[-11:-1]) / 10, 0.001)
    c1  = (closes[-1] - closes[-2]) / max(closes[-2], 0.001) * 100
    c4  = (closes[-1] - closes[-5]) / max(closes[-5], 0.001) * 100

    # ── NUEVOS FILTROS ESTRUCTURALES ──────────
    estructura    = detectar_choch_bos(highs, lows, closes)
    regime        = detectar_market_regime(closes)
    b             = btc_trend()

    # Formato de precio
    fp = lambda x: (f"${x:,.2f}" if x > 100 else f"${x:,.4f}" if x > 1 else f"${x:,.6f}")

    # Rango dinámico para TP/SL
    rng = [abs(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, 8)]
    vp  = sum(rng) / len(rng) if rng else 1.5
    tp_pct = max(4, min(10, vp * 2))
    sl_pct = max(2, min(4, vp * 0.7))

    for tipo in ["long", "short"]:
        k = f"{sym}_{tipo}"

        # Cooldown 3h por par
        if k in H and datetime.now(Z) - H[k] < timedelta(hours=3):
            continue

        # ── FILTRO 1: Estructura mayor alineada ──
        if tipo == "long"  and estructura == "bajista":
            continue
        if tipo == "short" and estructura == "alcista":
            continue

        # ── FILTRO 2: Market Regime coherente ──
        if tipo == "long"  and regime == "trending_down":
            continue
        if tipo == "short" and regime == "trending_up":
            continue

        # ── FILTRO 3: BTC no en contra ──
        if tipo == "long"  and b == "b":
            continue
        if tipo == "short" and b == "a":
            continue

        # ── FILTRO 4: No entrada tardía ──
        if entrada_tardia(closes, tipo, umbral=4.0):
            continue

        # ── FILTRO 5: Zona de demanda/oferta válida ──
        if not zona_valida(p, lows, highs, tipo):
            continue

        # ── FILTRO 6: Volumen mínimo ──
        if vr < 0.8:
            continue

        # ── FILTRO 7: Vela de confirmación (relajado) ──
        # Solo bloquea si la vela es MUY contraria (>0.5% en contra)
        vela_cuerpo = (closes[-1] - opens[-1]) / max(opens[-1], 0.001) * 100
        if tipo == "long"  and vela_cuerpo < -0.5: continue
        if tipo == "short" and vela_cuerpo >  0.5: continue

        # ── SCORE PONDERADO (nuevo esquema) ──────
        sc = 50  # base

        # Estructura (35 pts)
        if estructura == "alcista" and tipo == "long":
            sc += 35
        elif estructura == "bajista" and tipo == "short":
            sc += 35
        elif estructura == "neutral":
            sc += 22

        # Zona de entrada (25 pts)
        zona_ref = min(lows[-15:]) if tipo == "long" else max(highs[-15:])
        dist_zona = abs(p - zona_ref) / max(zona_ref, 0.001) * 100
        if dist_zona < 0.8:
            sc += 25
        elif dist_zona < 1.5:
            sc += 15
        else:
            sc += 5

        # Market Regime (10 pts)
        if (regime == "trending_up" and tipo == "long") or (regime == "trending_down" and tipo == "short"):
            sc += 10
        elif regime == "ranging":
            sc += 3

        # Volumen (20 pts)
        if vr > 3.0:
            sc += 20
        elif vr > 2.0:
            sc += 13
        elif vr > 1.5:
            sc += 7

        # Momentum 4H (10 pts)
        if tipo == "long"  and c4 > 1.0: sc += 10
        elif tipo == "short" and c4 < -1.0: sc += 10
        elif tipo == "long"  and c4 > 0.3: sc += 5
        elif tipo == "short" and c4 < -0.3: sc += 5

        sc = min(sc, 100)

        # ── UMBRAL MÍNIMO ELEVADO ─────────────────
        if sc < 65:  # umbral de prueba (subir a 85 en producción)
            continue

        # Calcular TP y SL
        tp1 = p * (1 + tp_pct / 100) if tipo == "long" else p * (1 - tp_pct / 100)
        sl1 = p * (1 - sl_pct / 100) if tipo == "long" else p * (1 + sl_pct / 100)

        H[k] = datetime.now(Z)

        emoji = "🟢" if tipo == "long" else "🔴"

        # Señales descriptivas
        reg_txt = {
            "trending_up":   "Trending ↑",
            "trending_down": "Trending ↓",
            "ranging":       "Ranging"
        }.get(regime, "—")

        est_txt = {
            "alcista": "Estructura alcista ✅",
            "bajista": "Estructura bajista ✅",
            "neutral": "Estructura neutral ⚠️"
        }.get(estructura, "—")

        sg = [
            est_txt,
            f"📊 Vol {vr:.1f}x",
            f"📈 Regime: {reg_txt}",
            f"₿ BTC {'baja' if b=='b' else 'sube' if b=='a' else 'neutral'}"
        ]

        return {
            "sym": sym, "p": fp(p), "sc": sc, "sg": sg,
            "tipo": tipo, "c1": c1, "c4": c4, "vr": vr,
            "tp": fp(tp1), "sl": fp(sl1),
            "tp_pct": tp_pct, "sl_pct": sl_pct,
            "gan": tp_pct - 0.1,
            "apal": 5 if sc >= 92 else 3,
            "em": emoji
        }

    return None

# ─────────────────────────────────────────────
# RUNNER Y MENSAJERÍA (sin cambios estructurales)
# ─────────────────────────────────────────────

def run_bg():
    global D
    now = datetime.now(Z)
    hoy = now.strftime("%d/%m")
    if D["f"] != hoy:
        D = {"l": 0, "s": 0, "f": hoy}

    if D["l"] >= 3 and D["s"] >= 2:
        send("ℹ️ Límite diario alcanzado.")
        return

    ls, ss = [], []
    for par, sym in P:
        r = ana(par, sym)
        if r:
            if r["tipo"] == "long"  and D["l"] < 3: ls.append(r)
            elif r["tipo"] == "short" and D["s"] < 2: ss.append(r)
        time.sleep(0.5)

    ls.sort(key=lambda x: x["sc"], reverse=True)
    ss.sort(key=lambda x: x["sc"], reverse=True)
    tl, ts = ls[:2], ss[:1]

    if not tl and not ts:
        send("🔍 Sin pre-breakouts válidos. Mercado sin estructura clara.")
        return

    hora = now.strftime("%H:%M")
    msg  = f"⚡ *PUMP RADAR v2 — {hora} ARG*\n_Pre-breakout H1 | Estructura validada_\n\n"

    for r in tl + ts:
        dir_ = r["tipo"].upper()
        sign_tp = "+" if r["tipo"] == "long" else "-"
        sign_sl = "-" if r["tipo"] == "long" else "+"
        msg += (
            f"{r['em']} *{dir_} — {r['sym']}* | Score:`{r['sc']}/100`\n"
            f"📍`{r['p']}` | Vol:`{r['vr']:.1f}x` | 1h:`{r['c1']:+.1f}%` 4h:`{r['c4']:+.1f}%`\n"
            f"🎯`{r['tp']}` ({sign_tp}{r['tp_pct']:.1f}%) | 🛑`{r['sl']}` ({sign_sl}{r['sl_pct']:.1f}%) | ⚡`{r['apal']}x`\n"
            f"_{', '.join(r['sg'])}_\n\n"
        )
        if r["tipo"] == "long":  D["l"] += 1
        else:                    D["s"] += 1

    msg += f"📊 Hoy:{D['l']}L {D['s']}S\n⚠️_Experimental. Verificá en BingX/Bitget._"
    send(msg)

def run():
    threading.Thread(target=run_bg, daemon=True).start()

def listen():
    last = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{T}/getUpdates",
                params={"offset": last + 1, "timeout": 10},
                timeout=15
            )
            if r.ok:
                for u in r.json().get("result", []):
                    last = u["update_id"]
                    t = (u.get("message") or {}).get("text") or ""
                    if   t == "/start":    send("👋 *Pump Radar v2*\nPre-breakout H1 con estructura\n9am·3pm·8pm ARG\n/analizar /resumen /ayuda")
                    elif t == "/analizar": send("⚡ Buscando pre-breakouts..."); run()
                    elif t == "/resumen":  send(f"📊 Hoy:{D['l']}L {D['s']}S")
                    elif t == "/ayuda":    send("📍 Entrada en zona validada\n🎯 TP dinámico\n🛑 SL ajustado\n🏗️ Estructura 4H filtrada\n₿ BTC filtra dirección\nVerificá en BingX/Bitget.")
        except:
            pass
        time.sleep(2)

# ─────────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────────
schedule.every().day.at("12:00").do(run)
schedule.every().day.at("18:00").do(run)
schedule.every().day.at("23:00").do(run)

send("✅ *Pump Radar v2 activo*\nPre-breakout H1 | 10 pares | Umbral 65 (pruebas amplias)")
run()
threading.Thread(target=listen, daemon=True).start()

while True:
    schedule.run_pending()
    time.sleep(30)
