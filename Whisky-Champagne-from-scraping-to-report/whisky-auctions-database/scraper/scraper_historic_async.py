import pandas as pd
import asyncio
from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser
import json
import os
import logging
import time
import re
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------
CATEGORY_URL = "https://www.catawiki.com/en/c/961-champagne"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS_ITA = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}

def get_monthly_paths():
    now = datetime.now()
    mese_nome = MONTHS_ITA[now.month]
    csv_name = f"auctions_detailed_{mese_nome}.csv"
    excel_name = f"database champagne {mese_nome}.xlsx"
    summary_name = f"auctions_summary_{mese_nome}.xlsx"
    
    csv_path = os.path.join(ROOT_DIR, "data", csv_name)
    excel_path = os.path.join(ROOT_DIR, "data", excel_name)
    summary_path = os.path.join(ROOT_DIR, "data", summary_name)
    return csv_path, excel_path, summary_path

DATA_PATH, EXCEL_PATH, SUMMARY_PATH = get_monthly_paths()
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "scraper_historic_async.log")
SCRAPE_INTERVAL = 3600  # 1 ora
MAX_PAGES_SAFETY = 70  # Limite di sicurezza per la scansione totale
MAX_CONCURRENT_PAGES = 8  # Numero massimo di pagine aperte in parallelo

os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True)
os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)

def normalize_url(url):
    """Rimuove parametri query e slash finali per evitare duplicati"""
    if not url: return url
    url = url.split("?")[0]
    if url.endswith("/"):
        url = url[:-1]
    return url

# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)

# ----------------------------
# PREZZO ASTA
# ----------------------------
def extract_price(tree):
    # Prova selettori diretti
    selectors = [
        '[data-testid="lot-price"]',
        '[data-test="final-price"]',
        '[data-test="current-bid"]',
        '.be-lot-bid-status-section__bid-amount',
        'span.price-amount'
    ]
    for sel in selectors:
        node = tree.css_first(sel)
        if node:
            return node.text().strip()
    
    # Selettore fallback basato su contenitori conosciuti
    bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
    if bid_section:
        text = bid_section.text().strip()
        # Cerca pattern tipo " 65" o "65 "
        matches = re.findall(r'(\d+[\d.,]*)', text)
        if matches:
            # Spesso il primo numero dopo "Current bid" o simili è il prezzo
            return matches[0]
            
    return None

# ----------------------------
# STATUS ASTA
# ----------------------------
def detect_status(tree):
    # 1. Sezione bid-status
    bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
    if bid_section:
        if "closed" in bid_section.html.lower():
            return "CLOSED"
        text = bid_section.text().lower()
        if any(x in text for x in ["final bid", "winning bid", "sold for", "asta conclusa", "closed"]):
            return "CLOSED"
            
    # 2. Controllo active counter
    counter = tree.css_first('[data-testid="lot-bidding-counter"]')
    if counter:
        t = counter.text().strip().replace(" ", "")
        if t and not all(c == '0' for c in t if c.isdigit()):
            return "OPEN"

    # 3. Controllo "closed-at" o testo globale
    if tree.css_first('[class*="LotBidStatusSection_closed-at"]'):
        return "CLOSED"
        
    body_text = tree.body.text().lower() if tree.body else ""
    if any(x in body_text for x in ["asta chiusa", "lot has ended", "final bid"]):
        return "CLOSED"
        
    return "OPEN"

def clean_maison_name(name):
    """Rimuove l'annata iniziale dal nome della Maison (es. 1990 Dom Perignon -> Dom Perignon)"""
    if not name or not isinstance(name, str):
        return name
    # Rimuove 4 cifre seguite da spazio all'inizio della stringa
    return re.sub(r'^\d{4}\s+', '', name).strip()

def save_advanced_excel(df, path):
    """Salva Excel con fogli separati per bidders, grafici e pivot automatici"""
    try:
        # Assicurati che Numero Bottiglie e Numero Offerte siano numerici
        df['Numero Bottiglie'] = pd.to_numeric(df['Numero Bottiglie'], errors='coerce').fillna(0)
        df['Numero Offerte'] = pd.to_numeric(df['Numero Offerte'], errors='coerce').fillna(0)
        
        # Split dei dati: 
        # Dati (Almeno 1 offerta E Nazionalità conosciuta)
        # Lotti non chiusi (0 offerte O Nazionalità Unknown)
        df_active = df[(df['Numero Offerte'] > 0) & (df['Nazionalita'] != "Unknown")].copy()
        df_inactive = df[(df['Numero Offerte'] == 0) | (df['Nazionalita'] == "Unknown")].copy()
        
        # Ordinamento alfabetico per Maison
        if 'Maison' in df_active.columns:
            df_active.sort_values(by='Maison', inplace=True)
        if 'Maison' in df_inactive.columns:
            df_inactive.sort_values(by='Maison', inplace=True)

        with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
            # 1. Foglio Dati (Solo con bidders)
            df_active.to_excel(writer, sheet_name='Dati', index=False)
            
            # 2. Foglio Lotti non chiusi (0 bidders)
            df_inactive.to_excel(writer, sheet_name='Lotti non chiusi', index=False)
            
            workbook = writer.book
            
            # 3. Analisi Nazionalità (Pie Chart) - Basata solo su df_active
            if 'Nazionalita' in df_active.columns:
                df_nat = df_active['Nazionalita'].value_counts().reset_index()
                df_nat.columns = ['Nazionalita', 'Lotti']
                df_nat.to_excel(writer, sheet_name='Analisi Nazionalita', index=False)
                
                sh_nat = writer.sheets['Analisi Nazionalita']
                chart_nat = workbook.add_chart({'type': 'pie'})
                chart_nat.add_series({
                    'name': 'Nazionalità Offerenti Migliori',
                    'categories': ['Analisi Nazionalita', 1, 0, len(df_nat), 0],
                    'values':     ['Analisi Nazionalita', 1, 1, len(df_nat), 1],
                    'data_labels': {'percentage': True, 'category': True, 'position': 'outside_end'},
                })
                chart_nat.set_title({'name': 'Distribuzione % Nazionalità Best Bidders'})
                sh_nat.insert_chart('D2', chart_nat)

            # 3. Analisi Volume Maison (Bar Chart)
            if 'Maison' in df.columns and 'Numero Bottiglie' in df.columns:
                df_copy = df.copy()
                df_copy['Numero Bottiglie'] = pd.to_numeric(df_copy['Numero Bottiglie'], errors='coerce').fillna(1)
                
                group_cols = ['Maison']
                if 'Tipologia' in df.columns:
                    group_cols.append('Tipologia')
                
                df_vol = df_copy.groupby(group_cols)['Numero Bottiglie'].sum().sort_values(ascending=False).reset_index()
                df_vol.to_excel(writer, sheet_name='Analisi Volume Maison', index=False)
                
                sh_vol = writer.sheets['Analisi Volume Maison']
                chart_vol = workbook.add_chart({'type': 'column'})
                
                if 'Tipologia' in df.columns:
                    df_vol['Etichetta'] = df_vol['Maison'] + " (" + df_vol['Tipologia'].astype(str) + ")"
                    df_vol[['Etichetta']].to_excel(writer, sheet_name='Analisi Volume Maison', startcol=len(group_cols)+1, index=False)
                    cat_col = len(group_cols)+1
                else:
                    cat_col = 0

                chart_vol.add_series({
                    'name': 'Bottiglie Totali',
                    'categories': ['Analisi Volume Maison', 1, cat_col, len(df_vol), cat_col],
                    'values':     ['Analisi Volume Maison', 1, len(group_cols), len(df_vol), len(group_cols)],
                    'data_labels': {'value': True, 'font': {'size': 8, 'bold': True}},
                })
                chart_vol.set_title({'name': 'Volume Vendite (Maison & Tipologia) - Solo Lotti con Bidders'})
                chart_vol.set_x_axis({'name': 'Maison (Tipologia)', 'label_position': 'low'})
                chart_vol.set_y_axis({'name': 'Q.tà Bottiglie'})
                chart_vol.set_size({'width': 1000, 'height': 500})
                sh_vol.insert_chart('E2', chart_vol)

            # 5. Analisi Rendimento (Performance Chart)
            sh_perf = workbook.add_worksheet('Analisi Rendimento')
            total_lots = len(df)
            active_count = len(df_active)
            inactive_count = len(df_inactive)
            
            perf_data = [
                ['Categoria', 'Lotti'],
                ['Con Offerte', active_count],
                ['Senza Offerte/Unknown', inactive_count]
            ]
            for r_idx, row in enumerate(perf_data):
                sh_perf.write_row(r_idx, 0, row)
            
            chart_perf = workbook.add_chart({'type': 'pie'})
            chart_perf.add_series({
                'name': 'Rendimento Aste del Mese',
                'categories': ['Analisi Rendimento', 1, 0, 2, 0],
                'values':     ['Analisi Rendimento', 1, 1, 2, 1],
                'data_labels': {'percentage': True, 'category': True, 'position': 'outside_end'},
            })
            chart_perf.set_title({'name': f'Success Rate Champagne - Totale {total_lots} Lotti'})
            sh_perf.insert_chart('D2', chart_perf)

            # 6. Analisi Prezzi Maison (Prezzo Unitario & Trend)
            if not df_active.empty:
                sh_price = workbook.add_worksheet('Analisi Prezzi Maison')
                
                # Calcolo Prezzo Unitario
                df_active['Prezzo Finale'] = pd.to_numeric(df_active['Prezzo Finale'], errors='coerce').fillna(0)
                df_active['Numero Bottiglie'] = pd.to_numeric(df_active['Numero Bottiglie'], errors='coerce').fillna(1)
                df_active['Prezzo Unitario'] = df_active['Prezzo Finale'] / df_active['Numero Bottiglie']
                
                # Tabella Riassuntiva: Gruppo per Maison-Tipologia-Vintage
                df_stats = df_active.groupby(['Maison', 'Tipologia', 'Vintage']).agg(
                    Min_Unitario=('Prezzo Unitario', 'min'),
                    Media_Unitaria=('Prezzo Unitario', 'mean'),
                    Max_Unitario=('Prezzo Unitario', 'max'),
                    Lotti=('Prezzo Unitario', 'count')
                ).reset_index()
                df_stats.sort_values(by=['Maison', 'Lotti'], ascending=[True, False], inplace=True)
                
                # Scrivi Tabella Riassuntiva
                headers_stats = list(df_stats.columns)
                sh_price.write_row(0, 0, headers_stats)
                for r_idx, row_data in enumerate(df_stats.values):
                    sh_price.write_row(r_idx + 1, 0, row_data)
                    
                # Tabella per Grafico Temporale (Top 5 combinazioni più frequenti per leggibilità)
                top_combos = df_stats.head(5)[['Maison', 'Tipologia', 'Vintage']]
                
                # Log temporale filtrato per il grafico
                df_trend = df_active.copy()
                df_trend['Data'] = pd.to_datetime(df_trend['Data Chiusura'], errors='coerce').dt.date
                df_trend = df_trend.sort_values('Data')
                
                # Scrittura log temporale per riferimento grafico
                start_col_trend = 8
                sh_price.write(0, start_col_trend, "Log Temporale (Top Combinazioni)")
                sh_price.write_row(1, start_col_trend, ["Data", "Identificativo", "Prezzo Unitario"])
                
                row_ptr = 2
                for _, combo in top_combos.iterrows():
                    m, t, v = combo['Maison'], combo['Tipologia'], combo['Vintage']
                    label = f"{m} {t} {v}"
                    subset = df_trend[(df_trend['Maison'] == m) & (df_trend['Tipologia'] == t) & (df_trend['Vintage'] == v)]
                    for _, r in subset.iterrows():
                        sh_price.write_row(row_ptr, start_col_trend, [str(r['Data']), label, r['Prezzo Unitario']])
                        row_ptr += 1
                
                # Inserimento Grafico Temporale
                if row_ptr > 2:
                    chart_trend = workbook.add_chart({'type': 'column'})
                    chart_trend.add_series({
                        'name': 'Andamento Prezzo Unitario',
                        'categories': ['Analisi Prezzi Maison', 2, start_col_trend, row_ptr-1, start_col_trend],
                        'values':     ['Analisi Prezzi Maison', 2, start_col_trend+2, row_ptr-1, start_col_trend+2],
                    })
                    chart_trend.set_title({'name': 'Andamento Prezzo Unitario (Top 5 Prodotti)'})
                    chart_trend.set_x_axis({'name': 'Data di Chiusura'})
                    chart_trend.set_y_axis({'name': 'Prezzo per Bottiglia (€)'})
                    chart_trend.set_size({'width': 900, 'height': 500})
                    sh_price.insert_chart('N2', chart_trend)

        # 7. Analisi Strategica (Riserva vs Successo)
        sh_strat = workbook.add_worksheet('Analisi Strategica')
        
        # Filtriamo i dati per l'analisi
        # Successo = Numero Offerte > 0
        df_strat = df.copy()
        df_strat['Numero Offerte'] = pd.to_numeric(df_strat['Numero Offerte'], errors='coerce').fillna(0)
        df_strat['Con_Offerte'] = df_strat['Numero Offerte'] > 0
        
        # Raggruppamento per Prezzo Riserva (Y/N)
        if 'Prezzo Riserva' in df_strat.columns:
            res_analysis = df_strat.groupby('Prezzo Riserva').agg(
                Totale=('url', 'count'),
                Venduti=('Con_Offerte', 'sum'),
                Media_Offerte=('Numero Offerte', 'mean')
            ).reset_index()
            
            res_analysis['Tasso_Successo_Perc'] = (res_analysis['Venduti'] / res_analysis['Totale']) * 100
            
            # Scrittura dati
            sh_strat.write(0, 0, "Analisi Impatto Prezzo di Riserva")
            res_headers = ["Prezzo Riserva", "Lotti Totali", "Lotti con Offerte", "Media Offerte", "Tasso Successo %"]
            sh_strat.write_row(1, 0, res_headers)
            for r_idx, row_data in enumerate(res_analysis.values):
                sh_strat.write_row(r_idx + 2, 0, row_data)
            
            # Grafico 1: Tasso di Successo
            chart_succ = workbook.add_chart({'type': 'column'})
            chart_succ.add_series({
                'name': 'Tasso di Successo %',
                'categories': ['Analisi Strategica', 2, 0, 1 + len(res_analysis), 0],
                'values':     ['Analisi Strategica', 2, 4, 1 + len(res_analysis), 4],
            })
            chart_succ.set_title({'name': 'Impatto Riserva su Tasso di Successo (Aste con Offerte)'})
            chart_succ.set_y_axis({'name': '% Successo'})
            sh_strat.insert_chart('G2', chart_succ)
            
            # Grafico 2: Numero Medio Offerte
            chart_bids = workbook.add_chart({'type': 'column'})
            chart_bids.add_series({
                'name': 'Media Offerte per Lotto',
                'categories': ['Analisi Strategica', 2, 0, 1 + len(res_analysis), 0],
                'values':     ['Analisi Strategica', 2, 3, 1 + len(res_analysis), 3],
            })
            chart_bids.set_title({'name': 'Impatto Riserva su Numero Medio di Offerte'})
            chart_bids.set_y_axis({'name': 'Media Offerte'})
            sh_strat.insert_chart('G18', chart_bids)

        # 8. Dashboard Prezzi (Dinamica)
        sh_dash = workbook.add_worksheet('Dashboard Prezzi')
        sh_hidden = workbook.add_worksheet('Data_Trend_Hidden')
        
        # Prepariamo i dati per il foglio nascosto
        df_trend_all = df.copy()
        df_trend_all['ID_Prodotto'] = df_trend_all['Maison'].astype(str) + " " + df_trend_all['Tipologia'].astype(str) + " " + df_trend_all['Vintage'].astype(str)
        df_trend_all['Data_Chiusura'] = pd.to_datetime(df_trend_all['Data Chiusura'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_trend_all['Prezzo_Unitario'] = pd.to_numeric(df_trend_all['Prezzo Finale'], errors='coerce') / pd.to_numeric(df_trend_all['Numero Bottiglie'], errors='coerce').fillna(1)
        
        # Scrittura dati nel foglio nascosto
        sh_hidden.write_row(0, 0, ["Data", "ID_Prodotto", "Prezzo_Unitario"])
        for i, row in enumerate(df_trend_all[['Data_Chiusura', 'ID_Prodotto', 'Prezzo_Unitario']].values):
            sh_hidden.write_row(i + 1, 0, row)
        
        # Lista unica prodotti per dropdown
        unique_ids = sorted([str(x) for x in df_trend_all['ID_Prodotto'].unique() if x])
        sh_hidden.write_column(0, 5, ["LISTA_PRODOTTI"] + unique_ids)
        
        # Configurazione Dashboard
        sh_dash.set_column('A:A', 20)
        sh_dash.set_column('B:B', 40)
        sh_dash.write('A2', 'Seleziona Prodotto:', workbook.add_format({'bold': True}))
        
        # Dropdown in B2
        sh_dash.data_validation('B2', {
            'validate': 'list',
            'source': f'=Data_Trend_Hidden!$F$2:$F${1+len(unique_ids)}',
            'input_message': 'Scegli una Maison e Annata',
        })
        sh_dash.write('B2', unique_ids[0] if unique_ids else "")
        
        # Formule dinamiche per estrarre i dati del grafico (E5:F100)
        sh_dash.write('E4', 'Data', workbook.add_format({'bold': True}))
        sh_dash.write('F4', 'Prezzo', workbook.add_format({'bold': True}))
        
        for r in range(5, 105):
            formula_date = f'=IFERROR(INDEX(Data_Trend_Hidden!$A$2:$A$5000, AGGREGATE(15, 6, ROW(Data_Trend_Hidden!$B$2:$B$5000)/(Data_Trend_Hidden!$B$2:$B$5000=$B$2), ROW(A{r-4}))), "")'
            formula_price = f'=IFERROR(INDEX(Data_Trend_Hidden!$C$2:$C$5000, AGGREGATE(15, 6, ROW(Data_Trend_Hidden!$B$2:$B$5000)/(Data_Trend_Hidden!$B$2:$B$5000=$B$2), ROW(A{r-4}))), "")'
            sh_dash.write_formula(r-1, 4, formula_date)
            sh_dash.write_formula(r-1, 5, formula_price)
        
        # Grafico dinamico
        chart_dash = workbook.add_chart({'type': 'column'})
        chart_dash.add_series({
            'name': 'Andamento Valore Unitario (€)',
            'categories': ['Dashboard Prezzi', 4, 4, 104, 4],
            'values':     ['Dashboard Prezzi', 4, 5, 104, 5],
            'data_labels': {'value': True},
        })
        chart_dash.set_title({'name': '= "Andamento Prezzi: " & B2'})
        chart_dash.set_x_axis({'name': 'Data di Chiusura'})
        chart_dash.set_y_axis({'name': 'Prezzo per Bottiglia (€)'})
        chart_dash.set_size({'width': 800, 'height': 450})
        sh_dash.insert_chart('A4', chart_dash)
        
        # Nascondiamo le colonne di appoggio E:F
        sh_dash.set_column('E:F', None, None, {'hidden': True})
        # Nascondiamo il foglio dei dati trend
        sh_hidden.hide()

        logging.info(f"File Excel avanzato salvato in: {path} (Dati: {len(df_active)}, Non chiusi: {len(df_inactive)})")
    except Exception as e:
        logging.error(f"Errore generazione Excel avanzato: {e}")

# ----------------------------
# PROCESSA UN LOTTO
# ----------------------------
async def process_lotto(url, session):
    try:
        r = await session.get(url, timeout=30)
        if r.status_code != 200:
            logging.error(f"Errore {r.status_code} lotto {url}")
            return None

        tree = HTMLParser(r.text)
        
        # 1. Metadati Base
        title_node = tree.css_first("h1")
        title = title_node.text().strip() if title_node else "Unknown"
        
        # 2. JSON-LD per Maison
        maison = "NV"
        scripts = tree.css("script[type='application/ld+json']")
        for s in scripts:
            try:
                data = json.loads(s.text())
                if data.get("@type") == "Product":
                    maison = data.get("brand", {}).get("name", "Unknown")
                    break
            except: pass
        if maison == "Unknown" or maison == "NV":
            # Fallback dal titolo (primo termine prima della virgola)
            maison = title.split(",")[0].strip()
        
        maison = clean_maison_name(maison) # <-- Pulizia Maison

        # 3. Analisi Titolo (Vintage, Count, Format, Type)
        vintage = "NV"
        year_match = re.search(r'\b(19|20)\d{2}\b', title)
        if year_match:
            vintage = year_match.group(0)
            
        count = "1"
        # Regex migliorata: cerca un numero piccolo (1-99) seguito da bottle/bottiglie
        # Abbiamo aggiunto un limite di cifre per evitare ID di sistema (max 2 cifre: 1-99)
        count_match = re.search(r'(?:\s|^|\-)\s*([1-9]\d{0,1})\s*(?:bottles|bottiglie|magnums|magnum|bottiglia|bottle)\b', title, re.I)
        if count_match:
            count = count_match.group(1)
            
        format_val = "0.75"
        if "Magnum" in title or "1.5L" in title or "1,5L" in title:
            format_val = "Magnum 1.5 L"
        elif "Jeroboam" in title or "3L" in title or "3.0L" in title:
            format_val = "Jeroboam 3 L"
        elif "0.75" in title or "75cl" in title:
            format_val = "0.75"
            
        champagne_type = "Brut"
        if "Rosé" in title or "Rose" in title:
            champagne_type = "Brut Rosé"
        elif "P2" in title:
            champagne_type = "P2"
        elif "Oenotheque" in title or "oenotheque" in title:
            champagne_type = "Oenotheque"
        elif "Extra Brut" in title:
            champagne_type = "Extra Brut"
        elif "Blanc de Blancs" in title:
            champagne_type = "Blanc de Blancs"

        # 4. Asta (Price, Status, Reserve, Bids, Nationality)
        price_raw = extract_price(tree)
        if not price_raw:
            return None
            
        currency = "".join([c for c in price_raw if not c.isdigit() and c not in ",."])
        price = price_raw.replace(currency, "").strip()
        status = detect_status(tree)
        
        bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
        reserve = "N"
        if bid_section and "reserve price" in bid_section.text().lower():
            if "no reserve" not in bid_section.text().lower():
                reserve = "Y"
        
        bid_count = "0"
        # Cerchiamo specificamente "See all bids (X)"
        for node in tree.css("span, div, button"):
            if "all bids" in node.text().lower():
                m = re.search(r'\((\d+)\)', node.text())
                if m:
                    bid_count = m.group(1)
                    break
                    
        nationality = "Unknown"
        # Cerchiamo l'alt dell'immagine della bandiera vicino al bidder migliore
        flag_img = tree.css_first("img[alt][class*='Flag'], img[alt][class*='flag']")
        if flag_img:
            nationality = flag_img.attributes.get("alt", "Unknown")

        # 5. Spedizione (Best effort)
        shipping = "N/A"
        # Cerchiamo info spedizione nel testo
        for node in tree.css("div"):
            if "shipping" in node.text().lower()[:20] and re.search(r'\d+', node.text()):
                # Esempio: "ITA 15.00"
                shipping = node.text().strip()[:30]
                break

        # 6. Data Chiusura precisa da dataLayer
        closing_date = "N/A"
        try:
            # Cerca il blocco script che contiene BiddingEndTime
            scripts = tree.css("script")
            for s in scripts:
                if "BiddingEndTime" in s.text():
                    # Estraggo con regex per sicurezza se non è un JSON puro
                    m = re.search(r'"BiddingEndTime":"([^"]+)"', s.text())
                    if m:
                        raw_date = m.group(1) # es: 2026-03-15T19:00:00Z
                        # Formattazione leggibile
                        try:
                            # Togliamo 'Z' per strptime o gestiamola
                            dt_str = raw_date.replace("Z", "")
                            # Usiamo solo la parte prima dei millisecondi se presenti
                            dt = datetime.strptime(dt_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                            closing_date = dt.strftime("%Y-%m-%d %H:%M")
                        except:
                            closing_date = raw_date
                    break
        except: pass

        return {
            "Maison": maison,
            "Tipologia": champagne_type,
            "Numero Bottiglie": count,
            "Formato": format_val,
            "Vintage": vintage,
            "Data Chiusura": closing_date,
            "Prezzo Riserva": reserve,
            "Numero Offerte": bid_count,
            "Nazionalita": nationality,
            "Prezzo Finale": price,
            "Costi Spedizione": shipping,
            "title": title,
            "currency": currency,
            "status": status,
            "url": url,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        logging.error(f"Errore lotto {url}: {e}")
        return None

# ----------------------------
# SCRAPE TUTTI I LOTTI
# ----------------------------
async def scrape_auctions():
    columns = [
        "Maison", "Tipologia", "Numero Bottiglie", "Formato", "Vintage",
        "Data Chiusura", "Prezzo Riserva", "Numero Offerte", "Nazionalita",
        "Prezzo Finale", "Costi Spedizione", "title", "currency", "status", "url", "timestamp"
    ]
    if os.path.exists(EXCEL_PATH):
        try:
            # Tenta caricamento da più fogli
            xls = pd.ExcelFile(EXCEL_PATH)
            dfs = []
            for sname in ['Dati', 'Lotti non chiusi']:
                if sname in xls.sheet_names:
                    dfs.append(pd.read_excel(xls, sheet_name=sname))
            
            if not dfs:
                df = pd.read_excel(EXCEL_PATH)
            else:
                df = pd.concat(dfs, ignore_index=True)
        except Exception as e:
            logging.warning(f"Errore caricamento Excel: {e}")
            df = pd.read_excel(EXCEL_PATH)
    elif os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH)
    else:
        df = pd.DataFrame(columns=columns)
    
    # Pulizia al volo dei dati esistenti
    if 'Maison' in df.columns:
        df['Maison'] = df['Maison'].apply(clean_maison_name)

    # Pass 1: Raccogli URL con curl_cffi da tutte le pagine disponibili
    urls = []
    p_idx = 1
    
    async with AsyncSession(impersonate="chrome120") as session:
        while p_idx <= MAX_PAGES_SAFETY:
            url = f"{CATEGORY_URL}?page={p_idx}" if p_idx > 1 else CATEGORY_URL
            logging.info(f"Scansione categoria pagina {p_idx}: {url}")
            
            try:
                r = await session.get(url, timeout=30)
                if r.status_code != 200:
                    logging.error(f"Errore {r.status_code} su pagina {p_idx}")
                    break
                
                tree = HTMLParser(r.text)
                links = tree.css("a[href*='/l/']")
                
                
                page_urls = []
                for a in tree.css("a.c-lot-card"):
                    href = a.attributes.get("href")
                    if href and "/l/" in href:
                        if not href.startswith("http"):
                            href = "https://www.catawiki.com" + href
                        
                        # Normalizzazione URL
                        href = normalize_url(href)
                        page_urls.append(href)
                
                if not page_urls: # Check if any URLs were found after parsing
                    logging.info(f"Nessun altro lotto trovato alla pagina {p_idx}. Fine scansione.")
                    break
                    
                # Rimuovi duplicati pagina
                unique_page_urls = list(dict.fromkeys(page_urls))
                urls.extend(unique_page_urls)
                logging.info(f"Trovati {len(unique_page_urls)} lotti nella pagina {p_idx}")
                
                p_idx += 1
                await asyncio.sleep(1) # Delay tra le pagine
            except Exception as e:
                logging.error(f"Errore durante fetch categoria {p_idx}: {e}")
                break

    # Rimuovi duplicati totali
    urls = list(dict.fromkeys(urls))
    logging.info(f"Totale aste uniche trovate: {len(urls)}")

    if not urls:
        logging.warning("Nessuna asta trovata, controllo log...")
        return

    # Pass 2: Processa lotti con curl_cffi in parallelo
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

    async def sem_task(url, session):
        async with semaphore:
            return await process_lotto(url, session)

    async with AsyncSession(impersonate="chrome120") as session:
        tasks = [sem_task(url, session) for url in urls]
        results = await asyncio.gather(*tasks)

    # Salva risultati validi
    new_rows = [r for r in results if r is not None]
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df = pd.concat([df, df_new], ignore_index=True)
        # Rimuovi duplicati url mantenendo l'ultima versione
        df.drop_duplicates(subset=["url"], keep="last", inplace=True)
        
        # Ordina per Maison
        df = df.sort_values(by="Maison")
        
        # Salva CSV e Excel (Report Avanzato)
        df.to_csv(DATA_PATH, index=False)
        save_advanced_excel(df, EXCEL_PATH)
        logging.info(f"Database salvato: {len(df)} righe (CSV & Excel)")

        # Analisi prezzi
        if not df.empty:
            df["Prezzo Finale"] = pd.to_numeric(df["Prezzo Finale"], errors="coerce")
            summary = df.groupby("Maison").agg(
                prezzo_min=("Prezzo Finale", "min"),
                prezzo_max=("Prezzo Finale", "max"),
                prezzo_medio=("Prezzo Finale", "mean"),
                lotti_totali=("url", "count"),
                ultimo_stato=("status", "last")
            ).reset_index()
            summary.to_csv(SUMMARY_PATH, index=False)
            logging.info(f"Analisi prezzi salvata ({len(summary)} lotti)")


# ----------------------------
# LOOP CONTINUO
# ----------------------------
async def main_loop():
    while True:
        try:
            # Aggiorna percorsi mensili globali
            global DATA_PATH, EXCEL_PATH, SUMMARY_PATH
            DATA_PATH, EXCEL_PATH, SUMMARY_PATH = get_monthly_paths()
            
            await scrape_auctions()
        except Exception as e:
            logging.error(f"Errore generale: {e}")
        logging.info(f"Attesa {SCRAPE_INTERVAL/60} minuti...")
        await asyncio.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())