import os
import asyncio
import logging
import sys
import socket
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Aggiungiamo il percorso radice per importare lo scraper
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from scraper.scraper import CatawikiScraper, DATA_PATH
except ImportError:
    # Fallback se eseguito direttamente dalla cartella scraper
    from scraper import CatawikiScraper, DATA_PATH

# --- CONFIGURAZIONE ---
# Token e chat ID NON stanno nel codice: si leggono dalle variabili d'ambiente.
# Su questo PC si impostano una volta sola con imposta_credenziali_telegram.bat
# (cartella Elite-Dashboard). Su GitHub Actions: secret TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.
#   TELEGRAM_TOKEN_CHAMPAGNE   token del bot champagne (da @BotFather)
#   TELEGRAM_TOKEN             alternativa generica (usata se manca quella sopra)
#   TELEGRAM_CHAT_ID           il tuo ID Telegram (scrivi /id al bot per saperlo)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_CHAMPAGNE") or os.environ.get("TELEGRAM_TOKEN", "")
_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
AUTHORIZED_CHAT_ID = int(_chat_id) if _chat_id.lstrip("-").isdigit() else None

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Il bot resta in ascolto ma "dorme": nel log finiscono solo i comandi che gli
# mandi da Telegram. Prima ogni controllo dei messaggi (uno ogni ~10 secondi,
# giorno e notte) scriveva una riga "getUpdates" nel log dello scheduler.
for _nome in ("httpx", "httpcore", "telegram", "apscheduler"):
    logging.getLogger(_nome).setLevel(logging.WARNING)

def restricted(func):
    """Decorator per limitare l'accesso solo all'utente autorizzato"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user = update.effective_user.username or update.effective_user.first_name
        text = update.message.text if update.message else "Nuovo evento"
        logging.info(f"Ricevuto comando '{text}' da {user} (ID: {chat_id})")
        if AUTHORIZED_CHAT_ID is None:
            # Caso speciale per il primo avvio: permettiamo /id a tutti
            if update.message.text == "/id":
                return await func(update, context)
            await update.message.reply_text("⚠️ Bot non ancora configurato. Scrivi /id e comunica l'ID allo sviluppatore.")
            return

        if chat_id != AUTHORIZED_CHAT_ID:
            logging.warning(f"Accesso non autorizzato da parte di: {chat_id}")
            # Non rispondiamo nulla agli sconosciuti per massima privacy (il bot sembra 'morto')
            return
        return await func(update, context)
    return wrapper

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Messaggio iniziale"""
    msg = (
        "🍾 **Champagne Auctions Bot** 🍾\n\n"
        "Comandi:\n"
        "🚀 /update - Avvia una scansione completa e invia il report\n"
        "📊 /file   - Invia l'ultimo report Excel salvato\n"
        "🌐 /dashboard - Ricevi il link alla Dashboard via Wi-Fi\n"
        "🆔 /id     - Mostra il tuo Chat ID"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra l'ID dell'utente (sempre accessibile se AUTHORIZED_CHAT_ID è None)"""
    user = update.effective_user.username or update.effective_user.first_name
    logging.info(f"Ricevuto comando '/id' da {user} (ID: {update.effective_chat.id})")
    await update.message.reply_text(f"Il tuo Chat ID è: `{update.effective_chat.id}`", parse_mode='Markdown')

@restricted
async def send_latest_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia il file Excel più recente"""
    if os.path.exists(DATA_PATH):
        await update.message.reply_chat_action("upload_document")
        with open(DATA_PATH, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(DATA_PATH),
                caption="Ecco l'ultimo report generato."
            )
    else:
        await update.message.reply_text("❌ Nessun file trovato. Usa /update per generarlo.")

@restricted
async def run_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esegue lo scraper e invia il risultato"""
    await update.message.reply_text("⏳ Avvio scraping in corso... Riceverai il file al termine.")
    
    try:
        scraper = CatawikiScraper()
        # Usa asyncio.to_thread (Python 3.9+) per eseguire il metodo bloccante
        await asyncio.to_thread(scraper.run_session)
        
        # Aggiorna il percorso del file (potrebbe essere cambiato il mese)
        from scraper.scraper import get_monthly_paths
        current_data_path, _ = get_monthly_paths()
        
        await update.message.reply_text("✅ Scraping completato!")
        
        # Invia il file aggiornato
        if os.path.exists(current_data_path):
            await update.message.reply_chat_action("upload_document")
            with open(current_data_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(current_data_path),
                    caption="📊 Ecco il report aggiornato."
                )
        else:
            await update.message.reply_text("⚠️ Scraping completato ma nessun file generato.")
    except Exception as e:
        logging.error(f"Errore bot update: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Errore durante lo scraping: {e}")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@restricted
async def send_dashboard_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link alla Dashboard (Rete Locale + Accesso Globale 4G)"""
    ip = get_local_ip()
    msg = (
        f"🖥️ **Dashboard Catawiki Elite**\n\n"
        f"🏠 **Accesso da Casa (Sotto copertura Wi-Fi):**\n"
        f"👉 http://{ip}:3000\n\n"
    )
    
    # Check if a public tunnel is active
    tunnel_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "tunnel.txt")
    if os.path.exists(tunnel_file):
        try:
            with open(tunnel_file, "r") as f:
                tunnel_url = f.read().strip()
            if tunnel_url:
                msg += (
                    f"🌍 **Accesso Globale (Da Rete 4G / Fuori Casa):**\n"
                    f"👉 {tunnel_url}\n"
                    f"_(Nota: Questo link è segreto e accessibile solo da te. Se ti chiede una password al primo accesso, scrivi semplicemente il tuo IP mostrato sulla pagina!)_\n\n"
                )
        except Exception as e:
            logging.error(f"Failed to read tunnel file: {e}")
            
    msg += f"\n*(Ricorda: Affinché i link funzionino, il file `run_all.bat` sul PC deve essere in esecuzione! Se lo riavvii, richiedi un nuovo link col comando /dashboard)*"

    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("ERRORE: token Telegram mancante. Imposta la variabile d'ambiente TELEGRAM_TOKEN_CHAMPAGNE")
        print("(lancia imposta_credenziali_telegram.bat e poi riapri questa finestra).")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("file", send_latest_file))
    app.add_handler(CommandHandler("update", run_update))
    app.add_handler(CommandHandler("dashboard", send_dashboard_link))
    
    print("Bot in ascolto... Premi Ctrl+C per fermare.")
    # Ascolto "lungo": una sola richiesta a Telegram ogni 50 secondi circa (prima ogni 10).
    # I comandi arrivano comunque subito: Telegram risponde appena gli scrivi.
    app.run_polling(timeout=50)
