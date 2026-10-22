import sys
import os
import asyncio

# Ensure Python can find the backend modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.scraper_service import scraper_instance

async def main():
    print("=== Avvio Catawiki Elite Scraper (CLI Mode) ===")
    
    # Importiamo e avviamo il database prima di scaricare
    # Questo assicura che eventuali tabelle mancanti in cloud vengano rigenerate
    from database import init_db
    await init_db()
    
    await scraper_instance.run_scrape()
    print("=== Scraping Completato! Dati salvati nel Database ===")
    
    # check_bargains.py è già richiamato internamente da scraper_instance.run_scrape()

if __name__ == "__main__":
    asyncio.run(main())
