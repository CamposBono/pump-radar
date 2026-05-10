import schedule
import threading
import time
import requests
import os
from bot import send_message, analyze_market

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def handle_updates():
    last = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset": last + 1, "timeout": 10},
                timeout=15
            )
            if r.ok:
                for u in r.json().get("result", []):
                    last = u["update_id"]
                    text = (u.get("message") or {}).get("text") or ""
                    if text == "/start":
                        send_message(
                            "👋 *Pump Radar activo*\n\n"
                            "🟢 *SPOT LONG* | $300M+ | BingX/Bitget/Nexo\n"
                            "🔵 *PIONEX GRID* | $5B+ | Bot neutral\n"
                            "🔴 *FUTUROS SHORT* | $500M+ | BingX/Bitget\n"
                            "🟡 *ALERTA MERCADO* | BTC/ETH/SOL\n\n"
                            "/analizar — análisis ahora\n"
                            "/ayuda — cómo operar"
                        )
                    elif text == "/analizar":
                        send_message("🔍 Analizando mercado...")
                        analyze_market()
                    elif text == "/ayuda":
                        send_message(
                            "*Cómo operar:*\n\n"
                            "🟢 *SPOT LONG*\n"
                            "• Verificá en tu exchange\n"
                            "• Venta en +15% a +25%\n"
                            "• Stop loss en -8%\n\n"
                            "🔵 *PIONEX GRID*\n"
                            "• Grid bot neutral en Pionex\n"
                            "• Cerrá si gana +5/10% o pierde -2/3%\n\n"
                            "🔴 *FUTUROS SHORT*\n"
                            "• Máximo 2x-3x apalancamiento\n"
                            "• Stop loss +5% | Objetivo -10/20%\n\n"
                            "🟡 *ALERTA MERCADO*\n"
                            "• BTC/ETH/SOL mueve +3% en 1h\n"
                            "• Altcoins suelen seguir en 1-2hs\n\n"
                            "⚠️ _Empezá con montos pequeños._"
                        )
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

def main():
    print("🚀 Pump Radar iniciado")
    send_message(
        "✅ *Pump Radar actualizado*\n\n"
        "Sin stables, sin shitcoins.\n"
        "Escribí /analizar para empezar."
    )
    schedule.every(1).hours.do(analyze_market)
    analyze_market()
    t = threading.Thread(target=handle_updates, daemon=True)
    t.start()
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
