# Whisky & Champagne — from scraping to report

**Elite-Dashboard**: auction intelligence per whisky e champagne da investimento su Catawiki.

Sistema automatico di **raccolta, pulizia e analisi dei prezzi d'asta** di whisky e champagne da investimento, con Catawiki come mercato di riferimento.

Progetto finale del corso **EPICODE — Data Analysis** · Autore: **Andrea Negretti**

Il progetto copre l'intera filiera del dato:

1. **Raccolta.** Due scraper Python (uno per lo champagne, uno per il whisky) leggono le aste chiuse e in corso di Catawiki due volte al giorno.
2. **Archiviazione.** I lotti finiscono in un database SQLite per categoria, con uno storico in Excel mese per mese.
3. **Dashboard web locale.** Una dashboard React + FastAPI serve per la consultazione quotidiana: inventario, analisi per bottiglia, nazionalità degli acquirenti, previsione di prezzo.
4. **Export per Power BI.** Uno script pulisce e tipizza i dati e li esporta in CSV pronti per il modello.
5. **Report Power BI** (`power-bi/CAPSTONE POWER BI.pbix`): è il prodotto finale del progetto, con KPI, trend, Top 5 e analisi geografica degli acquirenti.

---

## Architettura

```
                     ┌──────────────────────────── Catawiki.com ───────────────────────────┐
                     │  pagine categoria (961-champagne, 437-whisky) · pagine lotto · API offerte │
                     └───────────────┬───────────────────────────────┬─────────────────────┘
                                     │ curl_cffi + BeautifulSoup      │
              ┌──────────────────────▼───────┐        ┌──────────────▼───────────────┐
              │ scraper/scraper.py           │        │ backend/services/            │
              │ scheduler 03:00 e 17:00      │        │ scraper_service.py (async)   │
              │ → data/database <mese>.xlsx  │        │ → SQLite (aiosqlite)         │
              └──────────────────────────────┘        └──────────────┬───────────────┘
                                                                     │
       ┌──────────────────────────────┬──────────────────────────────┼─────────────────────┐
       │                              │                              │                     │
┌──────▼──────────┐   ┌───────────────▼──────────┐   ┌───────────────▼──────┐   ┌──────────▼─────────┐
│ FastAPI backend │   │ telegram_bot.py           │   │ check_bargains.py    │   │ export_powerbi.py  │
│ /api/lots       │   │ /update /file /dashboard  │   │ avvisi "affare" su   │   │ pulizia + CSV      │
│ /api/analysis   │   └──────────────────────────┘   │ Telegram             │   └──────────┬─────────┘
│ /api/scraper    │                                   └──────────────────────┘              │
└──────┬──────────┘                                                              ┌──────────▼─────────┐
┌──────▼──────────┐   tunnel SSH (localhost.run)                                 │ CAPSTONE POWER BI  │
│ React + Vite    │ ─────────────────────────► accesso remoto alla dashboard     │ .pbix              │
│ dashboard       │                                                              └────────────────────┘
└─────────────────┘
```

| Progetto | Backend (FastAPI) | Frontend (Vite) | Database SQLite |
|---|---|---|---|
| Champagne | `http://127.0.0.1:8001` | `http://localhost:3000` | `champagne-auctions-database/backend/Data SQLite Marzo.db` |
| Whisky | `http://127.0.0.1:8080` | `http://localhost:3001` | `whisky-auctions-database/backend/Whisky SQLite.db` |

---

## Struttura del repository

```
Whisky-Champagne-from-scraping-to-report/
├── README.md
├── requirements.txt                dipendenze Python unificate
├── .gitignore                      esclude credenziali, database, venv, node_modules, CSV di dati
├── imposta_credenziali_telegram.esempio.bat   modello per impostare i token Telegram
├── START_ALL_DASHBOARDS.bat        avvia entrambi i progetti (whisky + champagne)
├── correggi_prezzi.py / .bat       correzione una tantum di prezzi ed esiti già salvati
├── power-bi/
│   └── CAPSTONE POWER BI.pbix      report finale (Home · Champagne · Whisky · Geo)
├── champagne-auctions-database/
│   ├── run_all.bat                 avvia backend, frontend, tunnel, bot e scheduler
│   ├── backend/
│   │   ├── main.py                 app FastAPI (+ endpoint dashboard)
│   │   ├── database.py             engine SQLAlchemy async + tabella lotti
│   │   ├── models.py               schemi Pydantic delle risposte API
│   │   ├── api/routes/             lots.py · analysis.py · dashboard.py · scraper.py
│   │   ├── services/scraper_service.py   scraper asincrono che scrive su SQLite
│   │   ├── html_compat.py          parser HTML Python puro con API di selectolax
│   │   ├── lot_status.py           stato del lotto (OPEN/CLOSED/EXPIRED), vincitore, data chiusura
│   │   ├── bidding_api.py          esito ufficiale e offerta massima dall'API offerte Catawiki
│   │   ├── lotti_ritirati.py       gestione lotti rimossi da Catawiki (404 confermato)
│   │   ├── backfill_nazionalita.py recupero nazionalità del vincitore
│   │   ├── parsers.py              estrazione di box, formato e altri attributi dal titolo
│   │   ├── scrape_lock.py          lock per evitare due scraping in contemporanea
│   │   ├── run_scraper_cli.py      una sessione di scraping da riga di comando
│   │   └── requirements.txt
│   ├── scraper/
│   │   ├── scraper.py              scheduler (03:00 / 17:00) + Excel mensile con analisi
│   │   ├── scraper_historic_async.py  recupero dello storico
│   │   ├── telegram_bot.py         bot di controllo
│   │   └── check_bargains.py       avvisi su lotti sotto il prezzo medio
│   ├── frontend/                   React 18 + Vite 5 + ECharts/Recharts
│   │   ├── src/App.jsx, src/components/   Dashboard · Inventory · Analysis · BottleDetail ·
│   │   │                                  NationalityDrillThrough · Settings
│   │   └── start_tunnel.js         tunnel SSH verso localhost.run
│   └── .github/workflows/scraper.yml   scraping automatico su GitHub Actions (vedi nota sotto)
├── whisky-auctions-database/       stessa architettura (+ vocabolario distillerie, imbottigliatori)
└── export_powerbi/
    ├── export_powerbi.py           SQLite → CSV puliti per Power BI
    ├── pulizia_maison.py           normalizzazione maison champagne
    ├── pulizia_distilleria.py      normalizzazione distillerie whisky
    ├── mappa_maison.csv, mappa_distillerie.csv, maison_da_verificare.csv
    ├── PowerQuery_Elite.txt        query M di riferimento
    └── esporta_powerbi.bat
```

---

## Requisiti di sistema

### Hardware e sistema operativo

| Requisito | Minimo | Note |
|---|---|---|
| Sistema operativo | **Windows 10/11 a 64 bit** | Gli script di avvio sono `.bat` e PowerShell. Il codice Python gira anche su macOS e Linux (c'è `run_all_mac.sh`, e il workflow GitHub usa Ubuntu). |
| RAM | 8 GB (16 GB consigliati) | Con entrambi i progetti accesi girano circa 10 processi tra Python e Node. Gli script impostano `OPENBLAS_NUM_THREADS=1` per evitare l'errore *OpenBLAS: Memory allocation*. |
| Spazio su disco | circa 2 GB | Dipendenze (venv + `node_modules`), circa 30 MB per database più i backup `.bak_*` creati dagli script di correzione. |
| Rete | Connessione stabile | Lo scraping dura parecchio perché tra una richiesta e l'altra c'è una pausa casuale di 1,5–3,5 s. |
| PC acceso | Alle 03:00 e alle 17:00 | Per le sessioni programmate. In alternativa c'è il workflow GitHub Actions. |

### Software

| Software | Versione | A cosa serve |
|---|---|---|
| **Python** | **3.14** (usata in sviluppo). Il workflow GitHub usa la 3.11, quindi ≥ 3.11 funziona | Backend, scraper, bot, export |
| **Node.js** + npm | **≥ 18** (richiesto da Vite 5). Consigliata la 20 LTS o successive | Frontend React |
| **OpenSSH Client** | Quello incluso in Windows 10/11 (*Funzionalità facoltative*) | `start_tunnel.js` apre il tunnel con `ssh -R 80:localhost:3000 nokey@localhost.run` |
| **Git** | Qualsiasi versione recente | Endpoint `/api/scraper/pull` (`git pull origin main`) e workflow GitHub |
| **Power BI Desktop** | Versione recente, settembre 2026 o successive | Il `.pbix` è salvato in formato **PBIR** (`Report/definition/…`) con tema Fluent 2, quindi le versioni vecchie non lo aprono |
| Visual **Azure Maps** | Attivo in Power BI | Pagina *Geo* del report. In Power BI Service serve che l'amministratore del tenant lo abiliti |
| Telegram | Facoltativo | Bot di controllo e avvisi "affare" |

### Librerie Python (`requirements.txt` unificato nella cartella principale, identico a `backend/requirements.txt` dei due progetti)

| Pacchetto | Uso |
|---|---|
| `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic-settings` | API backend |
| `sqlalchemy[asyncio]`, `aiosqlite` | Database SQLite asincrono |
| `curl_cffi` | Richieste HTTP con impronta TLS di un browser vero, così Catawiki non le blocca |
| `beautifulsoup4` | Parsing HTML (tramite `html_compat.py`) |
| `pandas`, `numpy`, `openpyxl`, `xlsxwriter` | Elaborazione dati ed Excel mensili |
| `scikit-learn` | Regressione lineare per la previsione del prezzo |
| `python-telegram-bot` (**≥ 20**, usa `ApplicationBuilder`) | Bot Telegram |
| `requests`, `schedule` | Avvisi Telegram e scheduler 03:00/17:00 |

Opzionali:
- `selectolax`: lo usa solo `scraper_historic_async.py`. Il resto del codice usa `html_compat.py`.
- `lxml`: viene installato dal workflow GitHub.

`export_powerbi.py` usa **solo la libreria standard**. Per `pulizia_maison.py` e `pulizia_distilleria.py` basta la stessa venv del backend.

### Librerie Node (`frontend/package.json`)

- Runtime: `react` 18, `react-dom`, `axios`, `echarts` + `echarts-for-react`, `recharts`, `lucide-react`, `localtunnel`
- Sviluppo: `vite` 5, `@vitejs/plugin-react`, `eslint` + plugin React

---

## Installazione

```powershell
git clone https://github.com/andreanegrez-arch/Whisky-Champagne-from-scraping-to-report.git
cd Whisky-Champagne-from-scraping-to-report

# 1. Champagne: la venv sta nella cartella del progetto (.venv)
cd champagne-auctions-database
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..\..

# 2. Whisky: la venv sta in backend\venv
cd whisky-auctions-database
python -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..\..
```

In alternativa, per installare tutte le librerie Python in un colpo solo: `pip install -r requirements.txt`.

I database SQLite non sono nel repository: vengono creati vuoti al primo avvio del backend e si riempiono con il primo scraping.

### Credenziali Telegram

Token e chat ID non stanno nel codice: i bot e `check_bargains.py` li leggono dalle variabili d'ambiente.

| Variabile | Contenuto |
|---|---|
| `TELEGRAM_TOKEN_CHAMPAGNE` | token del bot champagne (da @BotFather) |
| `TELEGRAM_TOKEN_WHISKY` | token del bot whisky |
| `TELEGRAM_TOKEN` | alternativa generica, usata se manca quella specifica (es. su GitHub Actions) |
| `TELEGRAM_CHAT_ID` | il tuo ID Telegram, che il bot ti dice con `/id` |

Per impostarle sul PC una volta sola, copia `imposta_credenziali_telegram.esempio.bat` come `imposta_credenziali_telegram.bat` (è escluso da git), inserisci i tuoi valori e lancialo. Oppure da PowerShell:

```powershell
setx TELEGRAM_TOKEN_CHAMPAGNE "<token bot champagne>"
setx TELEGRAM_TOKEN_WHISKY    "<token bot whisky>"
setx TELEGRAM_CHAT_ID         "<il tuo chat id>"
```

Dopo `setx` vanno riaperte le finestre di `run_all.bat`. Per GitHub Actions, crea i secret `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` in *Settings → Secrets and variables → Actions*: il workflow li passa già allo scraper.

---

## Avvio

| Cosa | Come |
|---|---|
| Tutto (whisky + champagne) | doppio clic su `START_ALL_DASHBOARDS.bat` |
| Un solo progetto | `run_all.bat` nella cartella del progetto |
| Una sessione di scraping manuale | `cd backend` → `python run_scraper_cli.py` |
| Export per Power BI | `export_powerbi\esporta_powerbi.bat` (prima chiudi i CSV in Excel) |
| Correzione prezzi ed esiti | `correggi_prezzi.bat` (backend e scheduler **spenti**; con `--prova` scrive solo il report) |

Ogni `run_all.bat` apre cinque finestre:
1. backend FastAPI (`uvicorn --reload`);
2. frontend Vite;
3. tunnel SSH, che salva l'URL pubblico in `frontend/tunnel.txt`;
4. bot Telegram;
5. scheduler dello scraping.

Gli script lanciano anche `Unblock-File` su tutta la cartella, per prevenire i blocchi di Windows Smart App Control.

### Comandi del bot Telegram

| Comando | Cosa fa |
|---|---|
| `/start` | Messaggio di benvenuto |
| `/id` | Mostra il tuo chat ID |
| `/update` | Lancia una sessione di scraping |
| `/file` | Invia l'ultimo Excel mensile |
| `/dashboard` | Invia il link pubblico del tunnel |

### API principali (documentazione interattiva su `/docs`)

| Endpoint | Descrizione |
|---|---|
| `GET /api/lots`, `GET /api/lots/count` | Elenco e conteggio dei lotti |
| `GET /api/analysis/summary`, `/metrics`, `/bottle` | KPI e analisi per singola bottiglia |
| `GET /api/analysis/hierarchy`, `/stats`, `/predict` | Gerarchia maison/distilleria, statistiche, previsione del prezzo (regressione lineare) |
| `GET /api/analysis/nationalities`, `/top-nationalities`, `/nationality-lots` | Nazionalità degli acquirenti |
| `POST /api/scraper/start`, `GET /api/scraper/status` | Avvio e avanzamento dello scraping |
| `POST /api/scraper/pull` | `git pull` dei dati aggiornati da GitHub Actions |

---

## Pipeline Power BI

1. **Export.** `export_powerbi.py` apre i due database SQLite **in sola lettura**, quindi si può lanciare anche con il backend acceso, e scrive:
   - `lotti_champagne.csv`, `lotti_whisky.csv` (tabelle dei fatti);
   - `lotti_ritirati_champagne.csv`, `lotti_ritirati_whisky.csv`;
   - `DimCountry.csv` (dimensione paese, ISO a 2 lettere);
   - `Calendario.csv` (dimensione data).
2. **Pulizia applicata durante l'export** (il database non viene toccato):
   - maison normalizzate (`mappa_maison.csv`; i casi dubbi vanno in `maison_da_verificare.csv`);
   - distillerie normalizzate;
   - formato in litri preso dal titolo;
   - nazionalità del vincitore esportata solo se verificata;
   - nuove colonne `esito` (venduto / invenduto / in corso / non verificabile) e `offerta_massima`;
   - lotti misti esclusi.
3. **Formati garantiti.**
   - Date in `AAAA-MM-GG`, decimali con il punto, celle vuote al posto di `nan`/`None`.
   - File in UTF-8 con BOM.
   - Con `--formato-italiano` il separatore diventa `;` e i decimali usano la virgola.
4. **Modello.** È uno star schema con `lotti_champagne` e `lotti_whisky` come fatti, collegati a `Calendario[Data]` e `DimCountry[nazionalita_codice]` con relazioni 1 a molti. Le misure DAX stanno nella tabella `Misure`.

### Aprire e aggiornare il report

Il file `power-bi/CAPSTONE POWER BI.pbix` contiene già un'istantanea dei dati, quindi si apre e si consulta subito con Power BI Desktop. Per aggiornarlo con dati nuovi:
1. lancia `export_powerbi\esporta_powerbi.bat`;
2. in Power BI: *Trasforma dati → Impostazioni origine dati → Cambia origine* e punta ai CSV nella cartella `export_powerbi` del tuo PC (i percorsi salvati sono quelli del PC di sviluppo, come in `PowerQuery_Elite.txt`);
3. clicca *Aggiorna*.

### Pagine del report `CAPSTONE POWER BI.pbix`

| Pagina | Contenuto |
|---|---|
| **Home** | Copertina con pulsanti di navigazione verso Champagne e Whisky |
| **Champagne** | 11 card KPI: lotti processati e venduti, valore venduto, prezzo min/max/ultimo, media del mese, trend %, previsione, lotti con/senza box. Top 5 maison per lotti e per valore, andamento del prezzo, ciambella per tipologia. Filtri: data, maison, tipologia, formato, vintage |
| **Whisky** | Stessa struttura, per distilleria, stile, età e formato |
| **Geo** | Mappa Azure Maps dei paesi dei vincitori, classifica dei paesi per lotti vinti, confronto mensile (luglio–ottobre), selettore Champagne/Whisky |

---

## Scelte tecniche e problemi risolti

- **Windows Smart App Control.** Blocca a livello di kernel la DLL nativa di `selectolax` (lexbor), e né le esclusioni di Defender né `Unblock-File` lo aggirano. Per questo `html_compat.py` riproduce la stessa API (`css_first`, `css`, `.text()`, `.html`, `.attributes`) con BeautifulSoup + `html.parser`, che è Python puro. La fedeltà è verificata con test differenziali (`test_scraper.py`).
- **Anti-ban.** `curl_cffi` presenta l'impronta TLS di un browser vero. Tra le richieste c'è una pausa casuale; sugli errori 429/503 ci sono retry con backoff esponenziale; gli errori 5xx vengono ritentati a fine sessione. `scrape_lock.py` impedisce due scraping in contemporanea.
- **Storico prezzi.** La deduplica è su `(url, timestamp)` e non sul solo url. I lotti OPEN più vecchi di 45 giorni vengono marcati `EXPIRED`.
- **Esito d'asta ufficiale.** `bidding_api.py` chiede a Catawiki l'esito reale e l'offerta massima. Così si evita di registrare come prezzo la stima del perito per i lotti invenduti.
- **Lotti ritirati.** Un lotto viene tolto dallo storico solo dopo due 404 consecutivi e finisce in un report separato.
- **Backup prima di ogni correzione.** I database vengono copiati come `.bak_<motivo>_<data>` prima di ogni intervento massivo.

---

## Scraping automatico con GitHub Actions

`champagne-auctions-database/.github/workflows/scraper.yml` lancia lo scraper ogni giorno alle 03:00 e alle 17:00 UTC, invia gli avvisi Telegram e salva il database aggiornato. GitHub esegue solo i workflow che stanno nella cartella `.github` alla **radice** di un repository: qui il file è incluso come riferimento, mentre l'esecuzione automatica gira nel repository dedicato dello scraper champagne. Per usarlo serve creare i secret `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` (*Settings → Secrets and variables → Actions*).

## Dati e credenziali

- Nel repository non ci sono database, Excel né CSV con i dati raccolti: il `.gitignore` li esclude. Restano solo le tabelle di configurazione della pulizia (`mappa_maison.csv`, `mappa_distillerie.csv`, `maison_da_verificare.csv`, `distillerie_vocabolario.json`).
- Nessun token è scritto nel codice: le credenziali Telegram si leggono dalle variabili d'ambiente.

---

*Dati raccolti da pagine pubbliche di Catawiki per uso personale e di studio. Il progetto non è affiliato a Catawiki.*
