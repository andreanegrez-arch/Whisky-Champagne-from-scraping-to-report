"""
Advanced parsing logic for champagne lot titles
Extracts: maison, tipologia, annata (vintage), and special editions
"""
import re
from typing import Dict, Optional

# Known champagne houses
KNOWN_MAISONS = {
    "dom perignon": "Dom Pérignon",
    "dom pérignon": "Dom Pérignon",
    "ruinart": "Ruinart",
    "moet": "Moët & Chandon",
    "moet & chandon": "Moët & Chandon",
    "veuve": "Veuve Clicquot",
    "veuve clicquot": "Veuve Clicquot",
    "krug": "Krug",
    "bollinger": "Bollinger",
    "louis roederer": "Louis Roederer",
    "roederer": "Louis Roederer",
    "cristal": "Luis Roederer Cristal",
    "jacquesson": "Jacquesson",
    "laurent perrier": "Laurent Perrier",
    "perrier jouet": "Perrier-Jouët",
    "taittinger": "Taittinger",
    "salon": "Salon",
    "pol roger": "Pol Roger",
    "g.h. mumm": "G.H. Mumm",
    "mumm": "G.H. Mumm",
    "lanson": "Lanson",
    "piper": "Piper-Heidsieck",
    "rogelot": "Rogelot",
    "deutz": "Deutz",
    "billecart": "Billecart-Salmon",
    "charles heidsieck": "Charles Heidsieck",
}

# Tipologie detection
TIPOLOGIA_PATTERNS = {
    r"\bp\s*3\b|\bp3\b": "P3",
    r"\bp\s*2\b|\bp2\b": "P2",
    r"\bp\s*1\b|\bp1\b": "P1",
    r"\boenoth[eé]que\b": "Oenothèque",
    r"\bpink\b|\brosé\b|\brose\b": "Rosé",
    r"\bvineyards\b|\bvineyard\b": "Vineyard",
    r"\bluxe\b": "Luxe",
    r"\bsalon\b": "Salon",
}

# Special editions and limited releases
SPECIAL_KEYWORDS = {
    "lady gaga": "Lady Gaga",
    "lenny kravitz": "Lenny Kravitz",
    "luminous": "Luminous",
    "gold": "Gold",
    "silver": "Silver",
    "platinum": "Platinum",
    "exclusive": "Exclusive",
    "limited": "Limited Edition",
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison"""
    text = text.lower().strip()
    text = text.replace("pérignon", "perignon")
    text = text.replace("rosé", "rose")
    text = text.replace("é", "e")
    text = text.replace("ê", "e")
    text = text.replace("à", "a")
    return text


def detect_maison(title: str) -> Optional[str]:
    """Detect champagne house from title"""
    normalized = normalize_text(title)
    
    # Sort by length (longest first) to avoid partial matches
    sorted_maisons = sorted(KNOWN_MAISONS.keys(), key=len, reverse=True)
    
    for pattern in sorted_maisons:
        if pattern in normalized:
            return KNOWN_MAISONS[pattern]
    
    # Try to detect Mixed Lot
    all_maisons = list(KNOWN_MAISONS.values())
    detected = [m for m in all_maisons if normalize_text(m) in normalized]
    if len(detected) > 1:
        return "Mixed Lot"
    
    return None


def detect_tipologia(title: str) -> str:
    """Detect champagne type (brut, rosé, P2, P3, etc.)"""
    normalized = normalize_text(title)
    
    # Check patterns
    for pattern, tipo in TIPOLOGIA_PATTERNS.items():
        if re.search(pattern, normalized):
            return tipo
    
    # Default to Brut
    return "Brut"


def detect_vintage(title: str) -> Optional[int]:
    """Extract vintage year from title"""
    # Look for 4-digit years
    matches = re.findall(r'\b(19|20)\d{2}\b', title)
    if matches:
        # Return the most recent vintage found
        return int(matches[-1])
    return None


def detect_special_edition(title: str) -> Optional[str]:
    """Detect special editions and limited releases"""
    normalized = normalize_text(title)
    
    for keyword, name in SPECIAL_KEYWORDS.items():
        if keyword in normalized:
            return name
    
    return None
    
def detect_box(title: str) -> bool:
    """
    Detect if the lot includes an original box or case
    Patterns: OVP, Original Box, Case, Wooden Case, Cassetta, Scatola, Coffret
    """
    box_patterns = [
        r'\bovp\b',
        r'original\s*box',
        r'original\s*case',
        r'original\s*wooden\s*case',
        r'owc',
        r'scatola\s*originale',
        r'cassetta\s*originale',
        r'con\s*scatola',
        r'\bbox\b',
        r'\bcase\b',
        r'coffret',
        r'con\s*confezione'
    ]
    normalized = title.lower()
    for pattern in box_patterns:
        if re.search(pattern, normalized):
            return True
    return False


def parse_lot_title(title: str) -> Dict:
    """
    Main parsing function
    Returns dict with: maison, tipologia, vintage, special, title
    """
    if not title or not isinstance(title, str):
        return {
            "maison": "Unknown",
            "tipologia": "Brut",
            "vintage": None,
            "special": None,
            "has_box": False,
            "title": str(title) if title else "Unknown"
        }
    
    maison = detect_maison(title)
    if not maison:
        maison = "Unknown"
    
    tipologia = detect_tipologia(title)
    vintage = detect_vintage(title)
    special = detect_special_edition(title)
    has_box = detect_box(title)
    
    return {
        "maison": maison,
        "tipologia": tipologia,
        "vintage": vintage,
        "special": special,
        "has_box": has_box,
        "title": title.strip()
    }


def parse_titles_batch(titles):
    """Parse multiple titles at once"""
    import pandas as pd
    parsed = [parse_lot_title(t) for t in titles]
    return pd.DataFrame(parsed)
