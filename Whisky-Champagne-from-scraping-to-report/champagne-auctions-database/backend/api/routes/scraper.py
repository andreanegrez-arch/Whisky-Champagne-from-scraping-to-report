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
        repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        result = subprocess.run(
            ["git", "pull", "origin", "main"], 
            cwd=repo_dir,
            capture_output=True, 
            text=True, 
            check=True
        )
        return {"message": "Sincronizzazione completata con successo!", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"message": "Errore durante la sincronizzazione con GitHub.", "error": e.stderr}
    except Exception as e:
        return {"message": "Errore di configurazione Git locale.", "error": str(e)}
