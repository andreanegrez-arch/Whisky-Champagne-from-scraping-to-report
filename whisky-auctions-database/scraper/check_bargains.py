import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import requests
import numpy as np

# Add parent directory to path so we can import things if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Token e chat ID dalle variabili d'ambiente (vedi imposta_credenziali_telegram.bat).
# TELEGRAM_TOKEN_WHISKY ha la precedenza; TELEGRAM_TOKEN e' l'alternativa usata da GitHub Actions.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_WHISKY") or os.environ.get("TELEGRAM_TOKEN", "")
AUTHORIZED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "Whisky SQLite.db")

def send_telegram_alert(message: str):
    if not TELEGRAM_TOKEN or not AUTHORIZED_CHAT_ID:
        print("Telegram credentials missing. Skipping notification.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": AUTHORIZED_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
        print(f"Alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def get_prediction(distilleria, stile, db_conn):
    query = """
    SELECT prezzo_finale, data_chiusura 
    FROM lots 
    WHERE distilleria = ? AND stile = ? AND status = 'CLOSED' AND prezzo_finale > 0
    ORDER BY data_chiusura ASC
    """
    df = pd.read_sql(query, db_conn, params=(distilleria, stile))
    if len(df) < 3:
        return None, 0
    
    y = df['prezzo_finale'].values
    x = np.arange(1, len(y) + 1).reshape(-1, 1)
    
    from sklearn.linear_model import LinearRegression
    model = LinearRegression().fit(x, y)
    pred_price = model.predict([[len(y) + 1]])[0]
    score = model.score(x, y)
    
    return max(0.0, float(pred_price)), score

def check_bargains():
    print("Checking for bargains...")
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    
    query = "SELECT id, url, title, distilleria, stile, prezzo_finale, data_chiusura, prezzo_riserva FROM lots WHERE status = 'OPEN'"
    open_lots = pd.read_sql(query, conn)
    
    alerts = []
    
    for _, row in open_lots.iterrows():
        try:
            # Parse date
            chiusura = str(row['data_chiusura'])
            if chiusura == "None" or not chiusura:
                continue
            closing_date = datetime.strptime(chiusura.split(' ')[0], "%Y-%m-%d")
        except ValueError:
            continue
            
        current_price = float(row['prezzo_finale'] or 0)
        
        # We only care about active lots that actually have an estimated price
        if current_price <= 0:
            continue
            
        pred_price, confidence = get_prediction(row['distilleria'], row['stile'], conn)
        
        if pred_price and confidence > 0.4:  # At least moderate confidence
            # Threshold: Current price is at least 25% lower than predicted price
            if current_price < (pred_price * 0.75):
                margin = pred_price - current_price
                alerts.append({
                    "url": row['url'],
                    "descrizione": row['title'],
                    "attuale": current_price,
                    "predetto": round(pred_price, 2),
                    "scadenza": chiusura,
                    "margine": round(margin, 2),
                    "riserva": row['prezzo_riserva']
                })

    conn.close()
    
    # Sort by absolute margin
    alerts.sort(key=lambda x: x['margine'], reverse=True)
    
    if alerts:
        print(f"Found {len(alerts)} potential bargains!")
        message = "🚨 **CATAWIKI WHISKY BARGAIN ALERT** 🚨\n\n"
        for idx, a in enumerate(alerts[:5]): # Send top 5 to avoid spam
            riserva_text = "✅ Riserva superata" if a['riserva'] == 'Y' else "⚠️ Riserva NON superata"
            message += f"🥃 **{a['descrizione'][:40]}...**\n"
            message += f"💶 Prezzo Attuale: €{a['attuale']} | Stimato: ~€{a['predetto']}\n"
            message += f"📈 Margine Potenziale: +€{a['margine']}\n"
            message += f"⏳ Scadenza: {a['scadenza']}\n"
            message += f"🔒 {riserva_text}\n"
            message += f"🔗 [Vai all'asta]({a['url']})\n\n"
            
        if len(alerts) > 5:
            message += f"*(E altri {len(alerts)-5} lotti interessanti...)*"
            
        send_telegram_alert(message)
    else:
        print("No bargains found right now.")

if __name__ == "__main__":
    check_bargains()
