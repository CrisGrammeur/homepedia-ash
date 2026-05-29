"""
Configuration centrale de l'application.
"""
from pathlib import Path

APP_CONFIG = {
    "app_name": "HOMEPEDIA",
    "tagline": "Exploration du marché immobilier français",
    "version": "0.2.0",
}

ROOT_DIR = Path(__file__).parent.parent.parent
APP_DIR = ROOT_DIR / "app"
DATA_DIR = APP_DIR / "data"

# Palette cohérente entre pages
THEME = {
    "primary": "#1E3A8A",
    "accent": "#F59E0B",
    "positive": "#4CAF50",
    "negative": "#F44336",
    "neutral": "#9E9E9E",
}

# Sources de données — valeurs par défaut neutres.
# En production, tout se surcharge par variables d'env (cf. data_access.py) :
#   HOMEPEDIA_PG_HOST, HOMEPEDIA_PG_PORT, HOMEPEDIA_PG_PWD, HOMEPEDIA_MONGO_URI
# Aucun secret n'est stocké dans ce fichier.
DATA_SOURCES = {
    "postgres": {
        "host": "localhost", "port": 5432,
        "database": "homepediadb",
        "user": "homepedia",
        # Mot de passe : variable d'env HOMEPEDIA_PG_PWD uniquement.
    },
    "mongodb": {
        "uri": "mongodb://localhost:27017",
        "database": "homepediadb",
    },
}
