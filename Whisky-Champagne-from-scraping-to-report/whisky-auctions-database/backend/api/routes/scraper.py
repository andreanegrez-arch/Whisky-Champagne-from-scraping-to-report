from fastapi import APIRouter, BackgroundTasks
from services.scraper_service import scraper_instance
from models import ScrapeStatus
import subprocess
import os

router = APIRouter()

@router.post("/start")
async def start_scraper(background_tasks: BackgroundTasks):
    if scraper_instance.is_running:
        return {"message": "Scraper is already running"}
    
    background_tasks.add_task(scraper_instance.run_scrape)
    return {"message": "Scraper started in background"}

@router.get("/status", response_model=ScrapeStatus)
async def get_scraper_status():
    return {
        "is_running": scraper_instance.is_running,
        "last_run": scraper_instance.last_run,
        "progress": scraper_instance.progress,
        "message": scraper_instance.message
    }

@router.post("/pull")
async def pull_from_github():
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            return {
                "message": "Cartella locale non configurata come repository Git.",
                "error": "Per rimediare: nella cartella whisky apri il terminale e scrivi 'git init'"
            }
            
        # Check if origin exists
        remotes = subprocess.run(
            ["git", "remote"], cwd=repo_dir, capture_output=True, text=True
        ).stdout.lower()
        
        if "origin" not in remotes:
            return {
                "message": "Repository sincronizzata localmente, ma manca il collegamento al Cloud (GitHub).",
                "error": "Esegui nel terminale: git remote add origin https://github.com/tuo-utente/tuo-repo.git"
            }

        result = subprocess.run(
            ["git", "pull", "origin", "main"], 
            cwd=repo_dir,
            capture_output=True, 
            text=True, 
            check=True
        )
        return {"message": "Sincronizzazione completata con successo!", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        return {
            "message": "Errore durante la sincronizzazione con GitHub.", 
            "error": e.stderr or str(e)
        }
    except Exception as e:
        return {
            "message": "Errore imprevisto durante la sincronizzazione.", 
            "error": str(e)
        }
