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

# Sources de données. Le TOKEN se met en variable d'env / secret (jamais ici) :
#   DATABRICKS_TOKEN   (host / http_path sont surchargeables par DATABRICKS_HOST / DATABRICKS_HTTP_PATH)
# Aucun secret n'est stocké dans ce fichier.
DATA_SOURCES = {
    "databricks": {
        "host": "dbc-4c1d15ca-34b7.cloud.databricks.com",
        "http_path": "/sql/1.0/warehouses/8ca7219b9546df28",
        # Token : variable d'env DATABRICKS_TOKEN uniquement.
    },
    "postgres": {
        "host": "localhost", "port": 5432,
        "database": "homepediadb",
        "user": "homepedia",
    },
    "mongodb": {
        "uri": "mongodb://localhost:27017",
        "database": "homepediadb",
    },
}
