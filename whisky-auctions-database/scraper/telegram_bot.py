import os
import asyncio
import logging
import sys
import socket
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Aggiungiamo il percorso radice per importare il backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

# --- CONFIGURAZIONE ---
# Token e chat ID NON stanno nel codice: si leggono dalle variabili d'ambiente.
# Su questo PC si impostano una volta sola con imposta_credenziali_telegram.bat
# (cartella Elite-Dashboard). Su GitHub Actions: secret TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.
#   TELEGRAM_TOKEN_WHISKY   token del bot whisky (da @BotFather)
#   TELEGRAM_TOKEN          alternativa generica (usata se manca quella sopra)
#   TELEGRAM_CHAT_ID        il tuo ID Telegram (scrivi /id al bot per saperlo)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_WHISKY") or os.environ.get("TELEGRAM_TOKEN", "")
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
            if update.message.text == "/id":
                return await func(update, context)
            await update.message.reply_text("⚠️ Bot non ancora configurato. Scrivi /id e comunica l'ID allo sviluppatore.")
            return

        if chat_id != AUTHORIZED_CHAT_ID:
            logging.warning(f"Accesso non autorizzato da parte di: {chat_id}")
            return
        return await func(update, context)
    return wrapper

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Messaggio iniziale"""
    msg = (
        "🥃 **Whisky Auctions Bot** 🥃\n\n"
        "Comandi:\n"
        "🚀 /update    - Avvia una scansione completa del database\n"
        "🌐 /dashboard - Ricevi il link alla Dashboard via Wi-Fi e 4G\n"
        "📈 /grafico   - Grafico prezzi con link alle aste (es. lagavulin 16)\n"
        "🆔 /id        - Mostra il tuo Chat ID"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra l'ID dell'utente (sempre accessibile se AUTHORIZED_CHAT_ID è None)"""
    user = update.effective_user.username or update.effective_user.first_name
    logging.info(f"Ricevuto comando '/id' da {user} (ID: {update.effective_chat.id})")
    await update.message.reply_text(f"Il tuo Chat ID è: `{update.effective_chat.id}`", parse_mode='Markdown')

@restricted
async def run_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esegue lo scraper in background (nuova architettura async)"""
    await update.message.reply_text("⏳ Avvio scraping dei Whisky in corso... Consulta la dashboard per vedere i risultati aggiornati.")
    
    try:
        from services.scraper_service import scraper_instance
        from database import init_db
        
        # Inizializza DB prima di partire col scrape
        await init_db()
        
        # Esegue scraping asincrono
        await scraper_instance.run_scrape()
        
        await update.message.reply_text("✅ Scraping Whisky completato e database aggiornato! 🎉\n(I controlli automatici sugli affari ti invieranno eventuali notifiche se abilitati)")

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
        f"🖥️ **Dashboard Catawiki Elite - WHISKY**\n\n"
        f"🏠 **Accesso da Casa (Sotto copertura Wi-Fi):**\n"
        f"👉 http://{ip}:3001\n\n" # Assuming Whisky dashboard is at port 3001
    )
    
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

    await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)

# --- GRAFICO PREZZI CON LINK ALLE ASTE ---
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "Whisky SQLite.db")
COLONNE_RICERCA = ("distilleria", "imbottigliatore", "stile", "eta")

@restricted
async def send_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/grafico [ricerca] [NNg] - grafico prezzi con un link all'asta per ogni punto"""
    import grafico_aste as ga

    filtro, giorni = ga.analizza_argomenti(context.args)
    if not os.path.exists(DB_PATH):
        await update.message.reply_text("❌ Database non trovato. Usa /update per crearlo.")
        return
    await update.message.reply_chat_action("upload_photo")
    try:
        punti = await asyncio.to_thread(ga.carica_punti, DB_PATH, COLONNE_RICERCA, filtro, giorni)
    except Exception as e:
        logging.error(f"Errore lettura dati grafico: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Errore nella lettura del database: {e}")
        return
    if not punti:
        await update.message.reply_text(
            "🔍 Nessun lotto con prezzo trovato" + (f" per «{filtro}»" if filtro else "") + ".\n"
            "Esempio: /grafico lagavulin 16  (aggiungi 90g per gli ultimi 90 giorni)")
        return

    titolo = ga.titolo_grafico("🥃 Whisky", filtro, giorni, punti)
    tastiera = InlineKeyboardMarkup(
        [[InlineKeyboardButton(etichetta, url=url) for etichetta, url in riga]
         for riga in ga.pulsanti(punti)])
    png = await asyncio.to_thread(ga.crea_png, punti, titolo)
    didascalia = titolo + "\nTocca un pulsante per aprire l'asta col numero indicato sul grafico (○ = asta aperta)."
    if png:
        await update.message.reply_photo(photo=png, caption=didascalia, reply_markup=tastiera)
    else:
        await update.message.reply_text(didascalia, reply_markup=tastiera)

    nome = "grafico_" + ("".join(ch if ch.isalnum() else "_" for ch in filtro)[:40] or "ultimi") + ".html"
    await update.message.reply_document(
        document=ga.crea_html(punti, titolo), filename=nome,
        caption="📈 Grafico interattivo: aprilo e tocca un punto per andare all'asta.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("ERRORE: token Telegram mancante. Imposta la variabile d'ambiente TELEGRAM_TOKEN_WHISKY")
        print("(lancia imposta_credenziali_telegram.bat e poi riapri questa finestra).")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("update", run_update))
    app.add_handler(CommandHandler("dashboard", send_dashboard_link))
    app.add_handler(CommandHandler("grafico", send_chart))
    
    print("Bot Whisky in ascolto... Premi Ctrl+C per fermare.")
    # Ascolto "lungo": una sola richiesta a Telegram ogni 50 secondi circa (prima ogni 10).
    # I comandi arrivano comunque subito: Telegram risponde appena gli scrivi.
    app.run_polling(timeout=50)
