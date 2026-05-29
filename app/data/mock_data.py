from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

_RNG = np.random.default_rng(42)
_GEO_DIR = Path(__file__).parent / "geo"


# ═════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIEL GÉOGRAPHIQUE
# ═════════════════════════════════════════════════════════════════════════

def get_geojson(niveau: str = "region", code_parent: str | None = None) -> list[dict]:
    """
    Contours GeoJSON d'un niveau géographique (pour les choroplèthes Folium).

    Retour : liste de features GeoJSON, chacune avec `properties.code` (= code de la
    zone, à utiliser comme clé de jointure) et `properties.nom`.

    En prod : remplacer par la lecture de la table PostGIS de David
    (`geojson_regions` / `geojson_departements`), filtrée par `code_parent`.
    Pour l'instant seul le niveau `region` (métropole) est fourni.
    """
    fichier = _GEO_DIR / f"{niveau}s.geojson"
    if not fichier.exists():
        return []
    features = json.loads(fichier.read_text(encoding="utf-8"))["features"]
    if code_parent:
        features = [f for f in features if f["properties"].get("code_parent") == code_parent]
    return features

def get_regions() -> pd.DataFrame:
    """Liste des régions métropolitaines + DOM."""
    return pd.DataFrame([
        {"code_region": "11", "nom": "Île-de-France"},
        {"code_region": "24", "nom": "Centre-Val de Loire"},
        {"code_region": "27", "nom": "Bourgogne-Franche-Comté"},
        {"code_region": "28", "nom": "Normandie"},
        {"code_region": "32", "nom": "Hauts-de-France"},
        {"code_region": "44", "nom": "Grand Est"},
        {"code_region": "52", "nom": "Pays de la Loire"},
        {"code_region": "53", "nom": "Bretagne"},
        {"code_region": "75", "nom": "Nouvelle-Aquitaine"},
        {"code_region": "76", "nom": "Occitanie"},
        {"code_region": "84", "nom": "Auvergne-Rhône-Alpes"},
        {"code_region": "93", "nom": "Provence-Alpes-Côte d'Azur"},
        {"code_region": "94", "nom": "Corse"},
    ])


def get_departements(code_region: str | None = None) -> pd.DataFrame:
    """Liste des départements, filtrés optionnellement par région."""
    data = [
        ("75", "11", "Paris"), ("77", "11", "Seine-et-Marne"),
        ("78", "11", "Yvelines"), ("91", "11", "Essonne"),
        ("92", "11", "Hauts-de-Seine"), ("93", "11", "Seine-Saint-Denis"),
        ("94", "11", "Val-de-Marne"), ("95", "11", "Val-d'Oise"),
        ("69", "84", "Rhône"), ("38", "84", "Isère"),
        ("73", "84", "Savoie"), ("74", "84", "Haute-Savoie"),
        ("13", "93", "Bouches-du-Rhône"), ("06", "93", "Alpes-Maritimes"),
        ("83", "93", "Var"),
        ("35", "53", "Ille-et-Vilaine"), ("29", "53", "Finistère"),
        ("22", "53", "Côtes-d'Armor"), ("56", "53", "Morbihan"),
        ("31", "76", "Haute-Garonne"), ("34", "76", "Hérault"),
        ("33", "75", "Gironde"), ("64", "75", "Pyrénées-Atlantiques"),
        ("44", "52", "Loire-Atlantique"), ("49", "52", "Maine-et-Loire"),
        ("59", "32", "Nord"), ("62", "32", "Pas-de-Calais"),
        ("67", "44", "Bas-Rhin"), ("68", "44", "Haut-Rhin"),
    ]
    df = pd.DataFrame(data, columns=["code_dept", "code_region", "nom"])
    if code_region:
        df = df[df["code_region"] == code_region]
        if df.empty:
            df = pd.DataFrame([{"code_dept": "00", "code_region": code_region, "nom": "(à compléter)"}])
    return df.reset_index(drop=True)


def get_communes(code_dept: str | None = None) -> pd.DataFrame:
    """Liste de communes, filtrées par département."""
    data = [
        # Paris (qui est aussi un département)
        ("75056", "75", "Paris", 48.8566, 2.3522, 2_165_000),
        # Seine-et-Marne
        ("77288", "77", "Meaux", 48.9606, 2.8782, 56_000),
        ("77284", "77", "Melun", 48.5407, 2.6601, 41_000),
        # Hauts-de-Seine
        ("92012", "92", "Boulogne-Billancourt", 48.8356, 2.2410, 124_000),
        ("92050", "92", "Nanterre", 48.8924, 2.2070, 96_000),
        # Rhône
        ("69123", "69", "Lyon", 45.7640, 4.8357, 522_000),
        ("69266", "69", "Villeurbanne", 45.7665, 4.8795, 153_000),
        # Bouches-du-Rhône
        ("13055", "13", "Marseille", 43.2965, 5.3698, 870_000),
        ("13001", "13", "Aix-en-Provence", 43.5297, 5.4474, 145_000),
        # Ille-et-Vilaine
        ("35238", "35", "Rennes", 48.1173, -1.6778, 220_000),
        # Haute-Garonne
        ("31555", "31", "Toulouse", 43.6047, 1.4442, 493_000),
        # Hérault
        ("34172", "34", "Montpellier", 43.6108, 3.8767, 295_000),
        # Gironde
        ("33063", "33", "Bordeaux", 44.8378, -0.5792, 260_000),
        # Loire-Atlantique
        ("44109", "44", "Nantes", 47.2184, -1.5536, 320_000),
        # Nord
        ("59350", "59", "Lille", 50.6292, 3.0573, 235_000),
        # Bas-Rhin
        ("67482", "67", "Strasbourg", 48.5734, 7.7521, 287_000),
    ]
    df = pd.DataFrame(data, columns=["code_insee", "code_dept", "nom", "latitude", "longitude", "population"])
    if code_dept:
        df = df[df["code_dept"] == code_dept]
        if df.empty:
            df = pd.DataFrame([{
                "code_insee": f"{code_dept}999", "code_dept": code_dept,
                "nom": "(à compléter)", "latitude": 46.5, "longitude": 2.5, "population": 0,
            }])
    return df.reset_index(drop=True)


def search_communes(query: str, limit: int = 10) -> pd.DataFrame:
    """
    Recherche fuzzy par nom de commune (feature M04).
    En prod : appel à api-adresse.data.gouv.fr OU index full-text PostgreSQL.
    """
    # Mock : on cherche dans la liste des communes mockées
    all_data = []
    for dept_code in ["75", "77", "92", "69", "13", "35", "31", "34", "33", "44", "59", "67"]:
        all_data.append(get_communes(dept_code))
    all_communes = pd.concat(all_data, ignore_index=True)
    q = query.lower().strip()
    if not q:
        return all_communes.head(limit)
    mask = all_communes["nom"].str.lower().str.contains(q, na=False)
    return all_communes[mask].head(limit).reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════
# KPIs NATIONAUX (pour la Vue nationale)
# ═════════════════════════════════════════════════════════════════════════

def get_kpis_nationaux() -> dict:
    """KPIs affichés en haut de la Vue nationale."""
    return {
        "prix_m2_median_national": 3142,
        "evolution_1an_national": -1.8,
        "nb_transactions_12mois": 987_543,
        "ville_la_plus_chere": ("Paris", 10_842),
        "ville_la_moins_chere": ("Saint-Étienne", 1_287),
        "departement_dynamique": ("Hérault", 4.2),
    }


def get_kpis_zone(niveau: str, code_zone: str) -> dict:
    """KPIs sur une zone donnée (commune/département/région)."""
    seed = sum(ord(c) for c in str(code_zone)) % 1000
    rng = np.random.default_rng(seed)
    base = {"region": 3500, "departement": 4200, "commune": 5500}[niveau]
    return {
        "prix_m2_median": int(base + rng.integers(-1500, 3000)),
        "evolution_1an": float(rng.normal(2.5, 3.0)),
        "nb_ventes": int(rng.integers(500, 50000)),
        "population": int(rng.integers(20_000, 2_000_000)),
        "score_attractivite": round(rng.uniform(5.5, 9.0), 1),
    }


# ═════════════════════════════════════════════════════════════════════════
# PRIX (séries temporelles, cartes, évolution)
# ═════════════════════════════════════════════════════════════════════════

def get_prix_serie_temporelle(
    niveau: str, code_zone: str,
    type_local: list[str] | None = None,
    annee_min: int = 2018, annee_max: int = 2025,
) -> pd.DataFrame:
    """Évolution annuelle du prix médian par type de bien."""
    if type_local is None:
        type_local = ["Maison", "Appartement"]
    seed = sum(ord(c) for c in str(code_zone)) % 1000
    rng = np.random.default_rng(seed)
    rows = []
    for t in type_local:
        base = rng.integers(2500, 6000)
        croissance = rng.normal(0.03, 0.015)
        for annee in range(annee_min, annee_max + 1):
            prix = base * ((1 + croissance) ** (annee - annee_min))
            rows.append({
                "annee": annee, "type_local": t,
                "prix_m2_median": round(prix, 0),
                "nb_ventes": int(rng.integers(50, 5000)),
            })
    return pd.DataFrame(rows)


def get_prix_carte(
    niveau: str, annee: int,
    type_local: str = "Appartement",
    code_parent: str | None = None,
) -> pd.DataFrame:
    """Données pour choropleth (1 ligne par zone)."""
    if niveau == "region":
        df = get_regions().rename(columns={"code_region": "code_zone"})
    elif niveau == "departement":
        df = get_departements(code_region=code_parent).rename(columns={"code_dept": "code_zone"})
    else:
        df = get_communes(code_dept=code_parent).rename(columns={"code_insee": "code_zone"})
        df = df[["code_zone", "nom", "latitude", "longitude"]]
    rng = np.random.default_rng(annee)
    df["prix_m2_median"] = rng.integers(1500, 8500, size=len(df))
    df["nb_ventes"] = rng.integers(10, 5000, size=len(df))
    df["annee"] = annee
    df["type_local"] = type_local
    return df


def get_evolution_prix(niveau: str, code_zone: str) -> dict:
    """Croissance du prix sur différents horizons (S02)."""
    seed = sum(ord(c) for c in str(code_zone)) % 1000
    rng = np.random.default_rng(seed)
    return {
        "croissance_1an": float(rng.normal(2, 4)),
        "croissance_3ans": float(rng.normal(8, 10)),
        "croissance_5ans": float(rng.normal(18, 15)),
    }


# ═════════════════════════════════════════════════════════════════════════
# FICHE COMMUNE — TOUT sur une commune (M05)
# ═════════════════════════════════════════════════════════════════════════

def get_fiche_commune(code_insee: str) -> dict:
    """
    Vue agrégée d'une commune : ce qu'on affiche sur la page Fiche commune.
    En prod : jointure de plusieurs tables Gold + enrichissement Mongo.
    """
    # Récupère le nom de la commune depuis le référentiel
    communes_df = pd.concat(
        [get_communes(d) for d in ["75","77","92","69","13","35","31","34","33","44","59","67"]],
        ignore_index=True,
    )
    row = communes_df[communes_df["code_insee"] == code_insee]
    if row.empty:
        nom, lat, lon, pop = "Commune inconnue", 46.5, 2.5, 0
    else:
        nom = row.iloc[0]["nom"]
        lat = row.iloc[0]["latitude"]
        lon = row.iloc[0]["longitude"]
        pop = row.iloc[0]["population"]

    seed = sum(ord(c) for c in code_insee) % 1000
    rng = np.random.default_rng(seed)
    return {
        "code_insee": code_insee,
        "nom": nom,
        "latitude": lat,
        "longitude": lon,
        # Démographie
        "population": pop,
        "densite": round(pop / max(rng.uniform(10, 200), 1), 0),
        "evolution_pop_5ans": round(rng.normal(0.5, 2.0), 1),
        # Économie
        "revenu_median": int(rng.integers(18_000, 35_000)),
        "taux_pauvrete": round(rng.uniform(8, 25), 1),
        "taux_chomage": round(rng.uniform(5, 15), 1),
        # Immobilier
        "prix_m2_appart": int(rng.integers(2000, 11000)),
        "prix_m2_maison": int(rng.integers(2200, 9500)),
        "loyer_predit_m2": round(rng.uniform(8, 28), 1),
        "nb_transactions_2024": int(rng.integers(100, 5000)),
        # Équipements (depuis tables education et gares_sncf)
        "nb_ecoles_total": int(rng.integers(2, 60)),
        "nb_ecoles_publiques": int(rng.integers(2, 50)),
        "nb_ecoles_privees": int(rng.integers(0, 12)),
        "nb_gares": int(rng.integers(0, 8)),
        # Score qualité de vie composite
        "score_qualite_vie": round(rng.uniform(5.5, 9.2), 1),
        "note_habitants": round(rng.uniform(5.0, 8.5), 1),
    }


# ═════════════════════════════════════════════════════════════════════════
# CLASSEMENTS top/flop (M09)
# ═════════════════════════════════════════════════════════════════════════

CRITERES_CLASSEMENT = {
    "prix_m2_appart": "Prix au m² (appartement)",
    "prix_m2_maison": "Prix au m² (maison)",
    "croissance_5ans": "Croissance sur 5 ans (%)",
    "score_qualite_vie": "Score qualité de vie",
    "revenu_median": "Revenu médian (€)",
}


def get_top_flop(niveau: str, critere: str, n: int = 10, ordre: str = "desc") -> pd.DataFrame:
    """Top ou flop des zones selon un critère."""
    if niveau == "region":
        base_df = get_regions().rename(columns={"code_region": "code_zone"})
    elif niveau == "departement":
        # Toutes les départements
        all_depts = []
        for r in get_regions()["code_region"]:
            all_depts.append(get_departements(r))
        base_df = pd.concat(all_depts, ignore_index=True).rename(columns={"code_dept": "code_zone"})
    else:
        all_com = []
        for d in ["75","77","92","69","13","35","31","34","33","44","59","67"]:
            all_com.append(get_communes(d))
        base_df = pd.concat(all_com, ignore_index=True).rename(columns={"code_insee": "code_zone"})

    rng = np.random.default_rng(hash(critere) % (2**32))
    base_df["valeur"] = rng.uniform(1000, 12000, size=len(base_df))
    base_df["critere"] = critere
    return base_df.sort_values("valeur", ascending=(ordre != "desc")).head(n).reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════
# COMPARATEUR (M08)
# ═════════════════════════════════════════════════════════════════════════

def compare_zones(niveau: str, codes_zones: list[str]) -> pd.DataFrame:
    """
    Tableau comparatif côte à côte de 2-3 zones.
    Une ligne par indicateur, une colonne par zone.
    """
    if not codes_zones:
        return pd.DataFrame()

    indicateurs = [
        ("Prix m² appartement (€)", "prix_m2_appart"),
        ("Prix m² maison (€)", "prix_m2_maison"),
        ("Loyer médian (€/m²)", "loyer_predit_m2"),
        ("Population", "population"),
        ("Revenu médian (€)", "revenu_median"),
        ("Taux pauvreté (%)", "taux_pauvrete"),
        ("Taux chômage (%)", "taux_chomage"),
        ("Nb écoles", "nb_ecoles_total"),
        ("Nb gares SNCF", "nb_gares"),
        ("Score qualité de vie", "score_qualite_vie"),
        ("Note habitants /10", "note_habitants"),
    ]

    rows = []
    fiches = {code: get_fiche_commune(code) for code in codes_zones}
    for label, key in indicateurs:
        row = {"Indicateur": label}
        for code in codes_zones:
            row[fiches[code]["nom"]] = fiches[code].get(key, "—")
        rows.append(row)
    return pd.DataFrame(rows)


def get_radar_zones(niveau: str, codes_zones: list[str]) -> pd.DataFrame:
    """
    Données pour radar chart : score normalisé 0-100 sur plusieurs axes.
    Format long pour Plotly.
    """
    axes = ["Prix attractif", "Transports", "Éducation", "Sécurité", "Dynamisme éco", "Qualité de vie"]
    rows = []
    for code in codes_zones:
        seed = sum(ord(c) for c in code) % 1000
        rng = np.random.default_rng(seed)
        fiche = get_fiche_commune(code)
        scores = rng.uniform(30, 95, size=len(axes))
        for axe, score in zip(axes, scores):
            rows.append({"zone": fiche["nom"], "axe": axe, "score": round(score, 1)})
    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════════
# CORRÉLATIONS (S07)
# ═════════════════════════════════════════════════════════════════════════

def get_correlation(
    indicateur_x: str, indicateur_y: str,
    niveau: str = "departement",
) -> pd.DataFrame:
    """
    Scatter de corrélation entre 2 indicateurs sur l'ensemble des zones d'un niveau.
    """
    if niveau == "departement":
        all_depts = []
        for r in get_regions()["code_region"]:
            all_depts.append(get_departements(r))
        df = pd.concat(all_depts, ignore_index=True).rename(columns={"code_dept": "code_zone"})
    else:
        df = get_regions().rename(columns={"code_region": "code_zone"})

    rng = np.random.default_rng((hash(indicateur_x) ^ hash(indicateur_y)) % (2**32))
    # On simule une corrélation
    base = rng.uniform(0, 100, size=len(df))
    noise = rng.normal(0, 15, size=len(df))
    df[indicateur_x] = base * 50 + 1500
    df[indicateur_y] = base * 200 + noise * 50 + 20000
    return df


# ═════════════════════════════════════════════════════════════════════════
# POUVOIR D'ACHAT (S08) — feature différenciante
# ═════════════════════════════════════════════════════════════════════════

def get_zones_accessibles(
    budget: float,
    surface_min: float = 50,
    type_local: str = "Appartement",
    niveau: str = "departement",
) -> pd.DataFrame:
    """
    'Avec X€ et au moins Y m², dans quelles zones puis-je acheter ?'
    Retourne les zones où prix_m2 * surface_min <= budget.
    """
    if niveau == "departement":
        all_depts = []
        for r in get_regions()["code_region"]:
            all_depts.append(get_departements(r))
        df = pd.concat(all_depts, ignore_index=True).rename(columns={"code_dept": "code_zone"})
    else:
        df = get_regions().rename(columns={"code_region": "code_zone"})

    rng = np.random.default_rng(42)
    df["prix_m2_median"] = rng.integers(1200, 9000, size=len(df))
    df["cout_estime"] = df["prix_m2_median"] * surface_min
    df["accessible"] = df["cout_estime"] <= budget
    df["surface_max_achetable"] = (budget / df["prix_m2_median"]).round(0)
    return df.sort_values("prix_m2_median").reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════
# INDICATEURS génériques
# ═════════════════════════════════════════════════════════════════════════

INDICATEURS_DISPONIBLES = [
    {"code": "taux_chomage", "nom": "Taux de chômage", "categorie": "économie", "unite": "%"},
    {"code": "revenu_median", "nom": "Revenu médian", "categorie": "économie", "unite": "EUR"},
    {"code": "taux_pauvrete", "nom": "Taux de pauvreté", "categorie": "économie", "unite": "%"},
    {"code": "densite_pop", "nom": "Densité de population", "categorie": "démographie", "unite": "hab/km²"},
    {"code": "part_jeunes", "nom": "Part des moins de 25 ans", "categorie": "démographie", "unite": "%"},
    {"code": "nb_ecoles", "nom": "Nombre d'écoles", "categorie": "éducation", "unite": "unités"},
    {"code": "nb_gares", "nom": "Nombre de gares SNCF", "categorie": "transports", "unite": "unités"},
]


def get_indicateurs_disponibles() -> pd.DataFrame:
    return pd.DataFrame(INDICATEURS_DISPONIBLES)


def get_indicateur(niveau: str, code_zone: str, indicateur: str, annee: int | None = None) -> pd.DataFrame:
    seed = (sum(ord(c) for c in str(code_zone)) + sum(ord(c) for c in indicateur)) % 1000
    rng = np.random.default_rng(seed)
    annees = list(range(2018, 2026))
    base = rng.uniform(5, 50)
    valeurs = [base + rng.normal(0, base * 0.05) for _ in annees]
    return pd.DataFrame({"annee": annees, "valeur": valeurs, "indicateur": indicateur})


# ═════════════════════════════════════════════════════════════════════════
# ANALYSE TEXTUELLE (avis, sentiment, wordcloud)
# ═════════════════════════════════════════════════════════════════════════

def get_wordcloud(niveau: str, code_zone: str, theme: str = "global") -> list[dict]:
    mots_par_theme = {
        "global": [
            ("calme", 95, "positif"), ("agréable", 87, "positif"), ("vivant", 72, "positif"),
            ("bruyant", 64, "negatif"), ("cher", 58, "negatif"), ("propre", 52, "positif"),
            ("transports", 49, "neutre"), ("verdure", 44, "positif"), ("commerces", 41, "neutre"),
            ("insécurité", 38, "negatif"), ("écoles", 35, "neutre"), ("ambiance", 32, "positif"),
        ],
        "securite": [
            ("tranquille", 78, "positif"), ("incivilités", 56, "negatif"), ("police", 45, "neutre"),
            ("nuit", 41, "negatif"), ("voisinage", 38, "positif"), ("cambriolages", 28, "negatif"),
        ],
        "transports": [
            ("métro", 89, "positif"), ("bus", 67, "neutre"), ("vélo", 54, "positif"),
            ("embouteillages", 48, "negatif"), ("stationnement", 42, "negatif"), ("RER", 39, "neutre"),
        ],
        "education": [
            ("écoles", 82, "positif"), ("collège", 64, "neutre"), ("lycée", 58, "positif"),
            ("crèche", 47, "neutre"), ("université", 41, "positif"), ("manque", 33, "negatif"),
        ],
    }
    base = mots_par_theme.get(theme, mots_par_theme["global"])
    seed = sum(ord(c) for c in str(code_zone)) % 100
    rng = np.random.default_rng(seed)
    return [
        {"mot": m, "poids": max(10, p + int(rng.integers(-15, 15))), "sentiment": s}
        for m, p, s in base
    ]


def get_sentiment_aggrege(niveau: str, code_zone: str) -> dict:
    seed = sum(ord(c) for c in str(code_zone)) % 1000
    rng = np.random.default_rng(seed)
    pos = rng.uniform(0.35, 0.65)
    neg = rng.uniform(0.10, 0.30)
    neu = 1 - pos - neg
    return {"positif": pos, "neutre": neu, "negatif": neg}


def get_notes_categorielles(code_insee: str) -> dict:
    """Notes par catégorie (radar chart sur la page Fiche commune et Avis)."""
    seed = sum(ord(c) for c in code_insee) % 1000
    rng = np.random.default_rng(seed)
    return {
        "environnement": round(rng.uniform(4, 9), 1),
        "transports": round(rng.uniform(4, 9), 1),
        "securite": round(rng.uniform(3, 8), 1),
        "sante": round(rng.uniform(5, 9), 1),
        "sports_loisirs": round(rng.uniform(5, 9), 1),
        "culture": round(rng.uniform(4, 9), 1),
        "enseignement": round(rng.uniform(5, 9), 1),
        "commerces": round(rng.uniform(5, 9), 1),
        "qualite_vie": round(rng.uniform(5, 8.5), 1),
    }


def get_avis_recents(code_insee: str, n: int = 10) -> pd.DataFrame:
    textes = [
        "Quartier très calme, idéal pour les familles, mais les commerces sont rares.",
        "Bonne desserte en transports, ambiance vivante mais ça peut être bruyant le week-end.",
        "Cadre verdoyant, écoles correctes, mais on sent un manque d'investissement.",
        "Très satisfait·e de la qualité de vie ici, voisins agréables, marché du dimanche au top.",
        "Trop cher pour ce que c'est. La sécurité s'est dégradée ces dernières années.",
        "J'ai grandi ici, ville agréable, sportive, plein de choses pour les jeunes.",
        "Pas mal de bruit, surtout en été. Mais les espaces verts compensent.",
    ]
    rng = np.random.default_rng(sum(ord(c) for c in str(code_insee)))
    rows = []
    for _ in range(n):
        rows.append({
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 500))),
            "note": round(rng.uniform(4, 9), 1),
            "texte": rng.choice(textes),
            "sentiment": rng.choice(["positif", "neutre", "negatif"], p=[0.55, 0.30, 0.15]),
        })
    return pd.DataFrame(rows).sort_values("date", ascending=False)
