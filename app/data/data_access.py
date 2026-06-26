"""
Couche d'accès aux données — VERSION PRODUCTION (schéma Gold en étoile, PostgreSQL/Neon).

Tables : dim_communes + fact_prix, fact_prix_dept, fact_evolution, fact_loyers,
fact_revenus, fact_education, fact_transport, fact_qualite_vie, fact_effort,
fact_rentabilite, fact_clusters.

Mêmes signatures et formats de retour que la couche mock : les pages ne changent pas.

Connexion : variable d'env DATABASE_URL (URL Postgres complète, ex. Neon), sinon
st.secrets["DATABASE_URL"] (Streamlit Cloud), sinon repli sur utils.config (local).
Aucun secret n'est stocké dans le dépôt.

Champs sans source dans ce schéma (renvoyés 0/vide) : note des habitants, taux de
chômage, densité, évolution population, coordonnées GPS (cartes communales par points
dégradées), et tout le NLP (avis/sentiment/wordcloud — MongoDB non branché).
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import sqlalchemy as sa

from utils.config import DATA_SOURCES

_GEO_DIR = Path(__file__).parent / "geo"

REGIONS_NOMS = {
    "11": "Île-de-France", "24": "Centre-Val de Loire", "27": "Bourgogne-Franche-Comté",
    "28": "Normandie", "32": "Hauts-de-France", "44": "Grand Est", "52": "Pays de la Loire",
    "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie",
    "84": "Auvergne-Rhône-Alpes", "93": "Provence-Alpes-Côte d'Azur", "94": "Corse",
    "01": "Guadeloupe", "02": "Martinique", "03": "Guyane", "04": "La Réunion", "06": "Mayotte",
}

# Sous le seuil de transactions, une médiane de prix est jugée peu fiable.
SEUIL_TRANSACTIONS = 5

# Paris / Lyon / Marseille : prix & équipements rattachés aux arrondissements.
# On réagrège vers la commune-mère.
ARRONDISSEMENTS = {
    "75056": [f"751{i:02d}" for i in range(1, 21)],   # Paris 75101..75120
    "69123": [f"6938{i}" for i in range(1, 10)],        # Lyon  69381..69389
    "13055": [f"132{i:02d}" for i in range(1, 17)],     # Marseille 13201..13216
}


def _codes_commune(code: str) -> list[str]:
    """Code commune + ses arrondissements éventuels (Paris/Lyon/Marseille)."""
    return [code] + ARRONDISSEMENTS.get(code, [])


# ═════════════════════════════════════════════════════════════════════════
# CONNEXION (lazy + cache session)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _engine() -> sa.Engine:
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["DATABASE_URL"]
        except Exception:
            url = None
    if not url:
        pg = DATA_SOURCES["postgres"]
        pwd = os.getenv("HOMEPEDIA_PG_PWD", "")
        url = f"postgresql://{pg['user']}:{pwd}@{pg['host']}:{pg['port']}/{pg['database']}"
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return sa.create_engine(url, pool_pre_ping=True)


def _df(sql: str, **params) -> pd.DataFrame:
    with _engine().connect() as conn:
        return pd.read_sql(sa.text(sql), conn, params=params)


def _scalar(sql: str, default=0, **params):
    d = _df(sql, **params)
    if d.empty or pd.isna(d.iloc[0, 0]):
        return default
    return d.iloc[0, 0]


def _nom_zone(niveau: str, code: str) -> str:
    return REGIONS_NOMS.get(code, code) if niveau == "region" else str(code)


# ═════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIEL GÉOGRAPHIQUE (dim_communes)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_regions() -> pd.DataFrame:
    df = _df('SELECT DISTINCT "codeRegion" AS code_region FROM dim_communes '
             'WHERE "codeRegion" IS NOT NULL ORDER BY 1')
    df["nom"] = df["code_region"].map(lambda c: REGIONS_NOMS.get(c, c))
    return df


@st.cache_data(ttl=3600)
def get_departements(code_region: str | None = None) -> pd.DataFrame:
    sql = ('SELECT DISTINCT "codeDepartement" AS code_dept, "codeRegion" AS code_region '
           'FROM dim_communes WHERE "codeDepartement" IS NOT NULL')
    df = _df(sql + ' AND "codeRegion" = :reg ORDER BY 1', reg=code_region) if code_region \
        else _df(sql + " ORDER BY 1")
    df["nom"] = df["code_dept"]
    return df


@st.cache_data(ttl=3600)
def get_communes(code_dept: str | None = None) -> pd.DataFrame:
    sql = ('SELECT code AS code_insee, "codeDepartement" AS code_dept, nom, '
           "CAST(NULLIF(population,'') AS DOUBLE PRECISION) AS population FROM dim_communes")
    df = _df(sql + ' WHERE "codeDepartement" = :dept ORDER BY nom', dept=code_dept) if code_dept \
        else _df(sql + " ORDER BY nom")
    df["population"] = df["population"].fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def search_communes(query: str, limit: int = 10) -> pd.DataFrame:
    q = (query or "").strip()
    sql = 'SELECT code AS code_insee, "codeDepartement" AS code_dept, nom FROM dim_communes'
    if not q:
        return _df(sql + " ORDER BY nom LIMIT :lim", lim=limit)
    return _df(sql + " WHERE nom ILIKE :pat ORDER BY nom LIMIT :lim", pat=f"%{q}%", lim=limit)


# ═════════════════════════════════════════════════════════════════════════
# PRIX
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_prix_serie_temporelle(
    niveau: str, code_zone: str,
    type_local: list[str] | None = None,
    annee_min: int = 2018, annee_max: int = 2025,
) -> pd.DataFrame:
    if type_local is None:
        type_local = ["Maison", "Appartement"]
    if niveau == "commune":
        # ANY(:codes) réagrège les arrondissements ; moyenne pondérée par le nb de ventes.
        sql = ("SELECT annee::int AS annee, type_local, "
               "ROUND(SUM(prix_median_m2*nb_transactions)/NULLIF(SUM(nb_transactions),0)) AS prix_m2_median, "
               "SUM(nb_transactions) AS nb_ventes FROM fact_prix "
               "WHERE code_commune = ANY(:codes) AND type_local = ANY(:types) "
               "AND annee::int BETWEEN :amin AND :amax GROUP BY annee, type_local ORDER BY annee")
        df = _df(sql, codes=_codes_commune(code_zone), types=list(type_local), amin=annee_min, amax=annee_max)
    elif niveau == "departement":
        sql = ("SELECT annee::int AS annee, type_local, ROUND(prix_median_m2) AS prix_m2_median, "
               "nb_transactions AS nb_ventes FROM fact_prix_dept "
               "WHERE code_departement = :code AND type_local = ANY(:types) "
               "AND annee::int BETWEEN :amin AND :amax ORDER BY annee")
        df = _df(sql, code=code_zone, types=list(type_local), amin=annee_min, amax=annee_max)
    else:
        sql = ('SELECT annee::int AS annee, type_local, ROUND(AVG(prix_median_m2)) AS prix_m2_median, '
               'SUM(nb_transactions) AS nb_ventes FROM fact_prix p '
               'JOIN dim_communes d ON d.code = p.code_commune '
               'WHERE d."codeRegion" = :code AND type_local = ANY(:types) '
               'AND annee::int BETWEEN :amin AND :amax GROUP BY annee, type_local ORDER BY annee')
        df = _df(sql, code=code_zone, types=list(type_local), amin=annee_min, amax=annee_max)
    if not df.empty:
        df["fiable"] = df["nb_ventes"] >= SEUIL_TRANSACTIONS
    return df


@st.cache_data(ttl=3600)
def get_prix_carte(
    niveau: str, annee: int,
    type_local: str = "Appartement",
    code_parent: str | None = None,
) -> pd.DataFrame:
    if niveau == "region":
        df = _df('SELECT d."codeRegion" AS code_zone, ROUND(AVG(p.prix_median_m2)) AS prix_m2_median, '
                 'SUM(p.nb_transactions) AS nb_ventes FROM fact_prix p '
                 'JOIN dim_communes d ON d.code = p.code_commune '
                 'WHERE p.annee = :annee AND p.type_local = :type GROUP BY d."codeRegion"',
                 annee=str(annee), type=type_local)
        df["nom"] = df["code_zone"].map(lambda c: _nom_zone("region", c))
    elif niveau == "departement":
        sql = ("SELECT code_departement AS code_zone, ROUND(prix_median_m2) AS prix_m2_median, "
               "nb_transactions AS nb_ventes FROM fact_prix_dept "
               "WHERE annee = :annee AND type_local = :type")
        if code_parent:
            sql += (' AND code_departement IN (SELECT DISTINCT "codeDepartement" '
                    'FROM dim_communes WHERE "codeRegion" = :parent)')
            df = _df(sql, annee=str(annee), type=type_local, parent=code_parent)
        else:
            df = _df(sql, annee=str(annee), type=type_local)
        df["nom"] = df["code_zone"]
    else:
        sql = ("SELECT code_commune AS code_zone, nom_commune AS nom, "
               "ROUND(prix_median_m2) AS prix_m2_median, nb_transactions AS nb_ventes "
               "FROM fact_prix WHERE annee = :annee AND type_local = :type")
        if code_parent:
            sql += (' AND code_commune IN (SELECT code FROM dim_communes '
                    'WHERE "codeDepartement" = :parent)')
            df = _df(sql, annee=str(annee), type=type_local, parent=code_parent)
        else:
            df = _df(sql, annee=str(annee), type=type_local)
    df["annee"] = annee
    df["type_local"] = type_local
    return df


@st.cache_data(ttl=3600)
def get_evolution_prix(niveau: str, code_zone: str) -> dict:
    serie = get_prix_serie_temporelle(niveau, code_zone, ["Maison", "Appartement"], 2018, 2025)
    out = {"croissance_1an": 0.0, "croissance_3ans": 0.0, "croissance_5ans": 0.0}
    if serie.empty:
        return out
    yearly = serie.groupby("annee")["prix_m2_median"].mean()
    dernier = yearly.index.max()
    for h, k in ((1, "croissance_1an"), (3, "croissance_3ans"), (5, "croissance_5ans")):
        if (dernier - h) in yearly.index and yearly[dernier - h]:
            out[k] = round((yearly[dernier] / yearly[dernier - h] - 1) * 100, 1)
    return out


# ═════════════════════════════════════════════════════════════════════════
# KPIs
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_kpis_nationaux() -> dict:
    annee = _scalar("SELECT MAX(annee) FROM fact_prix", default=None)
    out = {"prix_m2_median_national": 0, "evolution_1an_national": 0.0,
           "nb_transactions_12mois": 0, "ville_la_plus_chere": ("—", 0),
           "ville_la_moins_chere": ("—", 0), "departement_dynamique": ("—", 0.0)}
    if annee is None:
        return out
    out["prix_m2_median_national"] = int(_scalar(
        "SELECT ROUND(AVG(prix_median_m2)) FROM fact_prix WHERE annee = :a", a=annee))
    out["nb_transactions_12mois"] = int(_scalar(
        "SELECT SUM(nb_transactions) FROM fact_prix WHERE annee = :a", a=annee))
    villes = _df("SELECT nom_commune AS nom, ROUND(AVG(prix_median_m2)) AS prix FROM fact_prix "
                 "WHERE annee = :a GROUP BY nom_commune HAVING SUM(nb_transactions) >= 50 "
                 "ORDER BY prix DESC", a=annee)
    if not villes.empty:
        out["ville_la_plus_chere"] = (villes.iloc[0]["nom"], int(villes.iloc[0]["prix"]))
        out["ville_la_moins_chere"] = (villes.iloc[-1]["nom"], int(villes.iloc[-1]["prix"]))
    return out


@st.cache_data(ttl=3600)
def get_kpis_zone(niveau: str, code_zone: str) -> dict:
    out = {"prix_m2_median": 0, "evolution_1an": 0.0, "nb_ventes": 0,
           "population": 0, "score_attractivite": 0.0}
    serie = get_prix_serie_temporelle(niveau, code_zone, ["Maison", "Appartement"], 2018, 2025)
    if not serie.empty:
        dernier = serie["annee"].max()
        last = serie[serie["annee"] == dernier]
        out["prix_m2_median"] = int(last["prix_m2_median"].mean())
        out["nb_ventes"] = int(last["nb_ventes"].sum())
    out["evolution_1an"] = get_evolution_prix(niveau, code_zone)["croissance_1an"]
    if niveau == "commune":
        out["population"] = int(_scalar(
            "SELECT CAST(NULLIF(population,'') AS DOUBLE PRECISION) FROM dim_communes WHERE code=:c", c=code_zone))
        out["score_attractivite"] = round(float(_scalar(
            "SELECT score_qualite_vie FROM fact_qualite_vie WHERE code_commune=:c", c=code_zone)), 1)
    else:
        col = "codeRegion" if niveau == "region" else "codeDepartement"
        out["population"] = int(_scalar(
            f'SELECT SUM(CAST(NULLIF(population,\'\') AS DOUBLE PRECISION)) FROM dim_communes WHERE "{col}"=:c', c=code_zone))
        out["score_attractivite"] = round(float(_scalar(
            f'SELECT AVG(q.score_qualite_vie) FROM fact_qualite_vie q '
            f'JOIN dim_communes d ON d.code=q.code_commune WHERE d."{col}"=:c', c=code_zone)), 1)
    return out


# ═════════════════════════════════════════════════════════════════════════
# FICHE COMMUNE
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_fiche_commune(code_insee: str) -> dict:
    dim = _df('SELECT nom, "codeDepartement" AS code_dept, "codeRegion" AS code_region, '
              "CAST(NULLIF(population,'') AS DOUBLE PRECISION) AS population "
              "FROM dim_communes WHERE code = :c", c=code_insee)
    if dim.empty:
        return {"code_insee": code_insee, "nom": "Commune inconnue", "latitude": None,
                "longitude": None, "population": 0, "densite": 0, "evolution_pop_5ans": 0.0,
                "revenu_median": 0, "taux_pauvrete": 0.0, "taux_chomage": 0.0,
                "prix_m2_appart": 0, "prix_m2_maison": 0, "nb_ventes_appart": 0, "nb_ventes_maison": 0,
                "loyer_predit_m2": 0.0, "nb_transactions_2024": 0, "nb_ecoles_total": 0,
                "nb_ecoles_publiques": 0, "nb_ecoles_privees": 0, "ecoles_pour_1000hab": 0.0,
                "nb_gares": 0, "score_qualite_vie": 0.0, "note_habitants": 0.0}

    codes = _codes_commune(code_insee)
    pop = int(dim.iloc[0]["population"]) if pd.notna(dim.iloc[0]["population"]) else 0

    def prix_nb(tl):
        # Prix de la dernière année dispo, agrégé sur les arrondissements (pondéré par nb ventes).
        d = _df("SELECT ROUND(SUM(prix_median_m2*nb_transactions)/NULLIF(SUM(nb_transactions),0)) AS prix, "
                "COALESCE(SUM(nb_transactions),0) AS nb FROM fact_prix "
                "WHERE code_commune = ANY(:codes) AND type_local = :tl AND annee = "
                "(SELECT MAX(annee) FROM fact_prix WHERE code_commune = ANY(:codes) AND type_local = :tl)",
                codes=codes, tl=tl)
        if d.empty or pd.isna(d.iloc[0]["prix"]):
            return 0, 0
        return int(d.iloc[0]["prix"]), int(d.iloc[0]["nb"])
    pa, na = prix_nb("Appartement")
    pm, nm = prix_nb("Maison")

    rev = _df("SELECT revenu_median, taux_pauvrete_dept FROM fact_revenus "
              "WHERE code_insee=:c ORDER BY annee DESC LIMIT 1", c=code_insee)
    annee_max = _scalar("SELECT MAX(annee) FROM fact_prix", default=None)
    nb_ecoles = int(_scalar('SELECT SUM(nb_etablissements) FROM fact_education WHERE "Code_commune" = ANY(:codes)', codes=codes))
    return {
        "code_insee": code_insee,
        "nom": dim.iloc[0]["nom"],
        "latitude": None, "longitude": None,
        "population": pop,
        "densite": 0, "evolution_pop_5ans": 0.0,
        "revenu_median": int(rev.iloc[0]["revenu_median"]) if not rev.empty and pd.notna(rev.iloc[0]["revenu_median"]) else 0,
        "taux_pauvrete": float(rev.iloc[0]["taux_pauvrete_dept"]) if not rev.empty and pd.notna(rev.iloc[0]["taux_pauvrete_dept"]) else 0.0,
        "taux_chomage": 0.0,
        "prix_m2_appart": pa, "prix_m2_maison": pm,
        "nb_ventes_appart": na, "nb_ventes_maison": nm,
        "loyer_predit_m2": round(float(_scalar("SELECT AVG(loyer_median_m2) FROM fact_loyers WHERE code_insee = ANY(:codes)", codes=codes)), 1),
        "nb_transactions_2024": int(_scalar("SELECT SUM(nb_transactions) FROM fact_prix WHERE code_commune = ANY(:codes) AND annee=:a", codes=codes, a=annee_max)),
        "nb_ecoles_total": nb_ecoles,
        "nb_ecoles_publiques": 0, "nb_ecoles_privees": 0,
        "ecoles_pour_1000hab": round(nb_ecoles / pop * 1000, 2) if pop else 0.0,
        "nb_gares": int(_scalar("SELECT SUM(nb_gares) FROM fact_transport WHERE code_commune = ANY(:codes)", codes=codes)),
        "score_qualite_vie": round(float(_scalar("SELECT score_qualite_vie FROM fact_qualite_vie WHERE code_commune=:c", c=code_insee)), 1),
        "note_habitants": 0.0,
    }


# ═════════════════════════════════════════════════════════════════════════
# INDICATEURS PAR ZONE (classements, corrélations, radar)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _zone_indicateurs(niveau: str) -> pd.DataFrame:
    base = ("q.prix_m2_final AS prix_m2, q.revenu_median, q.taux_pauvrete, q.nb_gares, "
            "q.nb_etablissements AS nb_ecoles, q.loyer_m2, q.score_qualite_vie")
    if niveau == "commune":
        df = _df(f"SELECT code_commune AS code_zone, nom, {base.replace('q.','')} FROM fact_qualite_vie")
    else:
        col = "codeRegion" if niveau == "region" else "codeDepartement"
        df = _df(f'SELECT d."{col}" AS code_zone, AVG(q.prix_m2_final) AS prix_m2, '
                 f"AVG(q.revenu_median) AS revenu_median, AVG(q.taux_pauvrete) AS taux_pauvrete, "
                 f"AVG(q.nb_gares) AS nb_gares, AVG(q.nb_etablissements) AS nb_ecoles, "
                 f"AVG(q.loyer_m2) AS loyer_m2, AVG(q.score_qualite_vie) AS score_qualite_vie "
                 f'FROM fact_qualite_vie q JOIN dim_communes d ON d.code = q.code_commune '
                 f'WHERE d."{col}" IS NOT NULL GROUP BY d."{col}"')
        df["nom"] = df["code_zone"].map(lambda c: _nom_zone(niveau, c))
    return df.fillna(0)


CRITERES_CLASSEMENT = {
    "prix_m2": "Prix au m² (€)",
    "score_qualite_vie": "Score qualité de vie",
    "revenu_median": "Revenu médian (€)",
    "loyer_m2": "Loyer au m² (€)",
    "nb_ecoles": "Nombre d'écoles",
}


@st.cache_data(ttl=3600)
def get_top_flop(niveau: str, critere: str, n: int = 10, ordre: str = "desc") -> pd.DataFrame:
    df = _zone_indicateurs(niveau)
    if df.empty or critere not in df.columns:
        return pd.DataFrame(columns=["code_zone", "nom", "valeur", "critere"])
    out = df[["code_zone", "nom", critere]].rename(columns={critere: "valeur"})
    out["critere"] = critere
    return out.sort_values("valeur", ascending=(ordre != "desc")).head(n).reset_index(drop=True)


@st.cache_data(ttl=3600)
def compare_zones(niveau: str, codes_zones: list[str]) -> pd.DataFrame:
    if not codes_zones:
        return pd.DataFrame()
    indicateurs = [
        ("Prix m² appartement (€)", "prix_m2_appart"),
        ("Prix m² maison (€)", "prix_m2_maison"),
        ("Loyer médian (€/m²)", "loyer_predit_m2"),
        ("Population", "population"),
        ("Revenu médian (€)", "revenu_median"),
        ("Taux pauvreté dépt. (%)", "taux_pauvrete"),
        ("Nb écoles", "nb_ecoles_total"),
        ("Nb gares SNCF", "nb_gares"),
        ("Score qualité de vie", "score_qualite_vie"),
    ]
    fiches = {c: get_fiche_commune(c) for c in codes_zones}
    rows = []
    for label, k in indicateurs:
        row = {"Indicateur": label}
        for c in codes_zones:
            row[fiches[c]["nom"]] = fiches[c].get(k, "—")
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def get_radar_zones(niveau: str, codes_zones: list[str]) -> pd.DataFrame:
    if not codes_zones:
        return pd.DataFrame(columns=["zone", "axe", "score"])
    df = _zone_indicateurs(niveau)
    df = df[df["code_zone"].isin([str(c) for c in codes_zones])]
    if df.empty:
        return pd.DataFrame(columns=["zone", "axe", "score"])
    axes = {"Prix attractif": "prix_m2", "Revenu": "revenu_median",
            "Éducation": "nb_ecoles", "Transports": "nb_gares", "Qualité de vie": "score_qualite_vie"}
    rows = []
    for label, col in axes.items():
        vmin, vmax = df[col].min(), df[col].max()
        for _, r in df.iterrows():
            if vmax == vmin:
                score = 50.0
            else:
                norm = (r[col] - vmin) / (vmax - vmin) * 100
                score = 100 - norm if col == "prix_m2" else norm
            rows.append({"zone": r["nom"], "axe": label, "score": round(float(score), 1)})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def get_correlation(indicateur_x: str, indicateur_y: str, niveau: str = "departement") -> pd.DataFrame:
    df = _zone_indicateurs(niveau)
    if df.empty or not {indicateur_x, indicateur_y}.issubset(df.columns):
        return pd.DataFrame(columns=["code_zone", "nom", indicateur_x, indicateur_y])
    return df[["code_zone", "nom", indicateur_x, indicateur_y]]


# ═════════════════════════════════════════════════════════════════════════
# POUVOIR D'ACHAT
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_zones_accessibles(
    budget: float, surface_min: float = 50,
    type_local: str = "Appartement", niveau: str = "departement",
) -> pd.DataFrame:
    if niveau == "region":
        df = _df('SELECT d."codeRegion" AS code_zone, ROUND(AVG(p.prix_median_m2)) AS prix_m2_median '
                 'FROM fact_prix p JOIN dim_communes d ON d.code = p.code_commune '
                 'WHERE p.type_local = :type AND p.annee = (SELECT MAX(annee) FROM fact_prix) '
                 'GROUP BY d."codeRegion"', type=type_local)
    else:
        df = _df("SELECT code_departement AS code_zone, ROUND(prix_median_m2) AS prix_m2_median "
                 "FROM fact_prix_dept WHERE type_local = :type "
                 "AND annee = (SELECT MAX(annee) FROM fact_prix_dept)", type=type_local)
    if df.empty:
        return pd.DataFrame(columns=["code_zone", "nom", "prix_m2_median",
                                     "cout_estime", "accessible", "surface_max_achetable"])
    df["nom"] = df["code_zone"].map(lambda c: _nom_zone(niveau, c))
    df["cout_estime"] = df["prix_m2_median"] * surface_min
    df["accessible"] = df["cout_estime"] <= budget
    df["surface_max_achetable"] = (budget / df["prix_m2_median"]).round(0)
    return df.sort_values("prix_m2_median").reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════
# INDICATEURS génériques
# ═════════════════════════════════════════════════════════════════════════

INDICATEURS_DISPONIBLES = [
    {"code": "revenu_median", "nom": "Revenu médian", "categorie": "économie", "unite": "EUR"},
    {"code": "prix_m2", "nom": "Prix au m²", "categorie": "immobilier", "unite": "EUR"},
    {"code": "score_qualite_vie", "nom": "Score qualité de vie", "categorie": "qualité de vie", "unite": "/100"},
    {"code": "taux_pauvrete", "nom": "Taux de pauvreté (départemental)", "categorie": "économie", "unite": "%"},
    {"code": "loyer_m2", "nom": "Loyer au m²", "categorie": "immobilier", "unite": "EUR"},
    {"code": "nb_ecoles", "nom": "Nombre d'écoles", "categorie": "éducation", "unite": "unités"},
    {"code": "nb_gares", "nom": "Nombre de gares", "categorie": "transports", "unite": "unités"},
]


def get_indicateurs_disponibles() -> pd.DataFrame:
    return pd.DataFrame(INDICATEURS_DISPONIBLES)


@st.cache_data(ttl=3600)
def get_indicateur(niveau: str, code_zone: str, indicateur: str, annee: int | None = None) -> pd.DataFrame:
    df = _zone_indicateurs(niveau)
    val = 0.0
    if not df.empty and indicateur in df.columns:
        row = df[df["code_zone"] == str(code_zone)]
        if not row.empty:
            val = float(row.iloc[0][indicateur])
    return pd.DataFrame({"annee": [2025], "valeur": [val], "indicateur": [indicateur]})


# ═════════════════════════════════════════════════════════════════════════
# CONTOURS GEOJSON (statiques, depuis data/geo)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_geojson(niveau: str = "region", code_parent: str | None = None) -> list[dict]:
    fichier = _GEO_DIR / f"{niveau}s.geojson"
    if not fichier.exists():
        return []
    features = json.loads(fichier.read_text(encoding="utf-8"))["features"]
    if code_parent:
        features = [f for f in features if f["properties"].get("code_parent") == code_parent]
    return features


# ═════════════════════════════════════════════════════════════════════════
# ANALYSE TEXTUELLE (MongoDB non branché : retours vides)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_wordcloud(niveau: str, code_zone: str, theme: str = "global") -> list[dict]:
    return []


@st.cache_data(ttl=3600)
def get_sentiment_aggrege(niveau: str, code_zone: str) -> dict:
    return {"positif": 0.0, "neutre": 0.0, "negatif": 0.0}


@st.cache_data(ttl=3600)
def get_notes_categorielles(code_insee: str) -> dict:
    return {}


@st.cache_data(ttl=3600)
def get_avis_recents(code_insee: str, n: int = 10) -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "note", "texte", "sentiment"])
