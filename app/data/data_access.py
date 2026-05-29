"""
Couche d'accès aux données — VERSION PRODUCTION (schéma Silver PostgreSQL).

Les agrégats (prix médians, classements, corrélations) sont calculés à la volée
à partir des tables brutes chargées par le pipeline Spark :
    geo_lookup, transactions_dvf, revenus_commune, loyers,
    etablissements_education, gares_sncf

Mêmes signatures et formats de retour que l'ancienne couche mock : les pages
ne changent pas. Connexion : utils.config.DATA_SOURCES, surchargeable par
HOMEPEDIA_PG_HOST / HOMEPEDIA_PG_PORT / HOMEPEDIA_PG_PWD / HOMEPEDIA_MONGO_URI.

Champs sans source dans ce schéma (renvoyés à 0 / vide) : score qualité de vie,
note des habitants, taux de chômage, densité, avis & NLP (MongoDB non branché).
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

# Prix au m² d'une transaction DVF
_PRIX_M2 = "t.valeur_fonciere / NULLIF(t.surface_reelle_bati, 0)"
_DVF_OK = "t.surface_reelle_bati > 0 AND t.valeur_fonciere > 0"

# Noms de régions (geo_lookup ne stocke que les codes)
REGIONS_NOMS = {
    "11": "Île-de-France", "24": "Centre-Val de Loire", "27": "Bourgogne-Franche-Comté",
    "28": "Normandie", "32": "Hauts-de-France", "44": "Grand Est", "52": "Pays de la Loire",
    "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie",
    "84": "Auvergne-Rhône-Alpes", "93": "Provence-Alpes-Côte d'Azur", "94": "Corse",
    "01": "Guadeloupe", "02": "Martinique", "03": "Guyane", "04": "La Réunion", "06": "Mayotte",
}
_DEPT_KEY = {"region": "code_region", "departement": "code_departement", "commune": "code_geo"}


# ═════════════════════════════════════════════════════════════════════════
# CONNEXION (lazy + cache session)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _engine() -> sa.Engine:
    pg = DATA_SOURCES["postgres"]
    url = sa.URL.create(
        "postgresql+psycopg2",
        username=pg["user"],
        password=os.getenv("HOMEPEDIA_PG_PWD", pg.get("password", "")),
        host=os.getenv("HOMEPEDIA_PG_HOST", pg["host"]),
        port=int(os.getenv("HOMEPEDIA_PG_PORT", str(pg["port"]))),
        database=pg["database"],
    )
    return sa.create_engine(url, pool_pre_ping=True)


def _df(sql: str, **params) -> pd.DataFrame:
    with _engine().connect() as conn:
        return pd.read_sql(sa.text(sql), conn, params=params)


def _scalar(sql: str, default=0, **params):
    df = _df(sql, **params)
    if df.empty or pd.isna(df.iloc[0, 0]):
        return default
    return df.iloc[0, 0]


def _dvf_zone(niveau: str):
    """(jointure, filtre) pour transactions_dvf alias t / geo_lookup alias g."""
    if niveau == "commune":
        return "", "t.code_geo = :code"
    join = "JOIN geo_lookup g ON g.code_geo = t.code_geo"
    return join, f"g.{_DEPT_KEY[niveau]} = :code"


def _nom_zone(niveau: str, code: str) -> str:
    return REGIONS_NOMS.get(code, code) if niveau == "region" else str(code)


# ═════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIEL GÉOGRAPHIQUE
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_regions() -> pd.DataFrame:
    df = _df("SELECT DISTINCT code_region FROM geo_lookup "
             "WHERE code_region IS NOT NULL ORDER BY code_region")
    df["nom"] = df["code_region"].map(lambda c: REGIONS_NOMS.get(c, c))
    return df


@st.cache_data(ttl=3600)
def get_departements(code_region: str | None = None) -> pd.DataFrame:
    sql = ("SELECT DISTINCT code_departement AS code_dept, code_region FROM geo_lookup "
           "WHERE code_departement IS NOT NULL")
    if code_region:
        df = _df(sql + " AND code_region = :reg ORDER BY code_dept", reg=code_region)
    else:
        df = _df(sql + " ORDER BY code_dept")
    df["nom"] = df["code_dept"]
    return df


@st.cache_data(ttl=3600)
def get_communes(code_dept: str | None = None) -> pd.DataFrame:
    sql = (
        "SELECT g.code_geo AS code_insee, g.code_departement AS code_dept, g.nom, "
        "       d.latitude, d.longitude, COALESCE(r.population, 0) AS population "
        "FROM geo_lookup g "
        "LEFT JOIN (SELECT code_geo, AVG(latitude) latitude, AVG(longitude) longitude "
        "           FROM transactions_dvf GROUP BY code_geo) d ON d.code_geo = g.code_geo "
        "LEFT JOIN (SELECT code_geo, MAX(nb_personnes) population "
        "           FROM revenus_commune GROUP BY code_geo) r ON r.code_geo = g.code_geo "
        "WHERE g.type_geo = 'commune'"
    )
    if code_dept:
        return _df(sql + " AND g.code_departement = :dept ORDER BY g.nom", dept=code_dept)
    return _df(sql + " ORDER BY g.nom")


@st.cache_data(ttl=3600)
def search_communes(query: str, limit: int = 10) -> pd.DataFrame:
    q = (query or "").strip()
    sql = ("SELECT code_geo AS code_insee, code_departement AS code_dept, nom "
           "FROM geo_lookup WHERE type_geo = 'commune'")
    if not q:
        return _df(sql + " ORDER BY nom LIMIT :lim", lim=limit)
    return _df(sql + " AND nom ILIKE :pat ORDER BY nom LIMIT :lim", pat=f"%{q}%", lim=limit)


# ═════════════════════════════════════════════════════════════════════════
# PRIX (calculés depuis transactions_dvf)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_prix_serie_temporelle(
    niveau: str, code_zone: str,
    type_local: list[str] | None = None,
    annee_min: int = 2018, annee_max: int = 2025,
) -> pd.DataFrame:
    if type_local is None:
        type_local = ["Maison", "Appartement"]
    join, where = _dvf_zone(niveau)
    return _df(
        f"SELECT t.annee, t.type_local, "
        f"  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS prix_m2_median, "
        f"  COUNT(*) AS nb_ventes "
        f"FROM transactions_dvf t {join} "
        f"WHERE {where} AND {_DVF_OK} AND t.type_local = ANY(:types) "
        f"  AND t.annee BETWEEN :amin AND :amax "
        f"GROUP BY t.annee, t.type_local ORDER BY t.annee",
        code=code_zone, types=list(type_local), amin=annee_min, amax=annee_max,
    )


@st.cache_data(ttl=3600)
def get_prix_carte(
    niveau: str, annee: int,
    type_local: str = "Appartement",
    code_parent: str | None = None,
) -> pd.DataFrame:
    med = f"ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS prix_m2_median"
    if niveau == "commune":
        sql = (
            f"SELECT t.code_geo AS code_zone, g.nom, "
            f"  AVG(t.latitude) AS latitude, AVG(t.longitude) AS longitude, "
            f"  {med}, COUNT(*) AS nb_ventes "
            f"FROM transactions_dvf t JOIN geo_lookup g ON g.code_geo = t.code_geo "
            f"WHERE t.annee = :annee AND t.type_local = :type AND {_DVF_OK}"
        )
        if code_parent:
            sql += " AND g.code_departement = :parent"
        sql += " GROUP BY t.code_geo, g.nom"
        df = _df(sql, annee=annee, type=type_local, parent=code_parent) if code_parent \
            else _df(sql, annee=annee, type=type_local)
    else:
        key = _DEPT_KEY[niveau]
        sql = (
            f"SELECT g.{key} AS code_zone, {med}, COUNT(*) AS nb_ventes "
            f"FROM transactions_dvf t JOIN geo_lookup g ON g.code_geo = t.code_geo "
            f"WHERE t.annee = :annee AND t.type_local = :type AND {_DVF_OK}"
        )
        if niveau == "departement" and code_parent:
            sql += " AND g.code_region = :parent"
            df = _df(sql + f" GROUP BY g.{key}", annee=annee, type=type_local, parent=code_parent)
        else:
            df = _df(sql + f" GROUP BY g.{key}", annee=annee, type=type_local)
        df["nom"] = df["code_zone"].map(lambda c: _nom_zone(niveau, c))
    df["annee"] = annee
    df["type_local"] = type_local
    return df


@st.cache_data(ttl=3600)
def get_evolution_prix(niveau: str, code_zone: str) -> dict:
    join, where = _dvf_zone(niveau)
    df = _df(
        f"SELECT t.annee, "
        f"  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2}) AS med "
        f"FROM transactions_dvf t {join} WHERE {where} AND {_DVF_OK} "
        f"GROUP BY t.annee ORDER BY t.annee",
        code=code_zone,
    )
    out = {"croissance_1an": 0.0, "croissance_3ans": 0.0, "croissance_5ans": 0.0}
    if df.empty:
        return out
    s = df.set_index("annee")["med"]
    dernier = s.index.max()
    for horizon, k in ((1, "croissance_1an"), (3, "croissance_3ans"), (5, "croissance_5ans")):
        if (dernier - horizon) in s.index and s[dernier - horizon]:
            out[k] = round((s[dernier] / s[dernier - horizon] - 1) * 100, 1)
    return out


# ═════════════════════════════════════════════════════════════════════════
# KPIs
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_kpis_nationaux() -> dict:
    annee = _scalar("SELECT MAX(annee) FROM transactions_dvf", default=None)
    out = {
        "prix_m2_median_national": 0, "evolution_1an_national": 0.0,
        "nb_transactions_12mois": 0, "ville_la_plus_chere": ("—", 0),
        "ville_la_moins_chere": ("—", 0), "departement_dynamique": ("—", 0.0),
    }
    if annee is None:
        return out
    out["prix_m2_median_national"] = int(_scalar(
        f"SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) "
        f"FROM transactions_dvf t WHERE t.annee = :a AND {_DVF_OK}", a=annee))
    out["nb_transactions_12mois"] = int(_scalar(
        "SELECT COUNT(*) FROM transactions_dvf WHERE annee = :a", a=annee))
    villes = _df(
        f"SELECT g.nom, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS prix "
        f"FROM transactions_dvf t JOIN geo_lookup g ON g.code_geo = t.code_geo "
        f"WHERE t.annee = :a AND {_DVF_OK} GROUP BY g.nom HAVING COUNT(*) >= 20 "
        f"ORDER BY prix DESC", a=annee)
    if not villes.empty:
        out["ville_la_plus_chere"] = (villes.iloc[0]["nom"], int(villes.iloc[0]["prix"]))
        out["ville_la_moins_chere"] = (villes.iloc[-1]["nom"], int(villes.iloc[-1]["prix"]))
    return out


@st.cache_data(ttl=3600)
def get_kpis_zone(niveau: str, code_zone: str) -> dict:
    join, where = _dvf_zone(niveau)
    annee = _scalar(
        f"SELECT MAX(t.annee) FROM transactions_dvf t {join} WHERE {where}",
        default=None, code=code_zone)
    out = {"prix_m2_median": 0, "evolution_1an": 0.0, "nb_ventes": 0,
           "population": 0, "score_attractivite": 0.0}
    if annee is None:
        return out
    row = _df(
        f"SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS prix, "
        f"  COUNT(*) AS n FROM transactions_dvf t {join} "
        f"WHERE {where} AND {_DVF_OK} AND t.annee = :a", code=code_zone, a=annee)
    if not row.empty:
        out["prix_m2_median"] = int(row.iloc[0]["prix"] or 0)
        out["nb_ventes"] = int(row.iloc[0]["n"] or 0)
    out["evolution_1an"] = get_evolution_prix(niveau, code_zone)["croissance_1an"]
    rjoin = "" if niveau == "commune" else "JOIN geo_lookup g ON g.code_geo = r.code_geo"
    rwhere = "r.code_geo = :code" if niveau == "commune" else f"g.{_DEPT_KEY[niveau]} = :code"
    out["population"] = int(_scalar(
        f"SELECT SUM(pop) FROM (SELECT MAX(nb_personnes) pop FROM revenus_commune r {rjoin} "
        f"WHERE {rwhere} GROUP BY r.code_geo) s", code=code_zone))
    return out


# ═════════════════════════════════════════════════════════════════════════
# FICHE COMMUNE
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_fiche_commune(code_insee: str) -> dict:
    geo = _df("SELECT nom, code_departement, code_region FROM geo_lookup "
              "WHERE code_geo = :c AND type_geo = 'commune'", c=code_insee)
    if geo.empty:
        return {"code_insee": code_insee, "nom": "Commune inconnue", "latitude": 46.5,
                "longitude": 2.5, "population": 0, "densite": 0, "evolution_pop_5ans": 0.0,
                "revenu_median": 0, "taux_pauvrete": 0.0, "taux_chomage": 0.0,
                "prix_m2_appart": 0, "prix_m2_maison": 0, "loyer_predit_m2": 0.0,
                "nb_transactions_2024": 0, "nb_ecoles_total": 0, "nb_ecoles_publiques": 0,
                "nb_ecoles_privees": 0, "nb_gares": 0, "score_qualite_vie": 0.0,
                "note_habitants": 0.0}

    def prix(type_local):
        return _scalar(
            f"SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) "
            f"FROM transactions_dvf t WHERE t.code_geo = :c AND t.type_local = :tl AND {_DVF_OK}",
            c=code_insee, tl=type_local)
    annee_max = _scalar("SELECT MAX(annee) FROM transactions_dvf", default=0)
    rev = _df("SELECT revenu_median, taux_pauvrete FROM revenus_commune "
              "WHERE code_geo = :c ORDER BY annee DESC LIMIT 1", c=code_insee)
    return {
        "code_insee": code_insee,
        "nom": geo.iloc[0]["nom"],
        "latitude": float(_scalar("SELECT AVG(latitude) FROM transactions_dvf WHERE code_geo=:c", default=46.5, c=code_insee)),
        "longitude": float(_scalar("SELECT AVG(longitude) FROM transactions_dvf WHERE code_geo=:c", default=2.5, c=code_insee)),
        "population": int(_scalar("SELECT MAX(nb_personnes) FROM revenus_commune WHERE code_geo=:c", c=code_insee)),
        "densite": 0,
        "evolution_pop_5ans": 0.0,
        "revenu_median": int(rev.iloc[0]["revenu_median"]) if not rev.empty and pd.notna(rev.iloc[0]["revenu_median"]) else 0,
        "taux_pauvrete": float(rev.iloc[0]["taux_pauvrete"]) if not rev.empty and pd.notna(rev.iloc[0]["taux_pauvrete"]) else 0.0,
        "taux_chomage": 0.0,
        "prix_m2_appart": int(prix("Appartement")),
        "prix_m2_maison": int(prix("Maison")),
        "loyer_predit_m2": float(_scalar("SELECT AVG(loyer_pred_m2) FROM loyers WHERE code_geo=:c", default=0.0, c=code_insee)),
        "nb_transactions_2024": int(_scalar("SELECT COUNT(*) FROM transactions_dvf WHERE code_geo=:c AND annee=:a", c=code_insee, a=annee_max)),
        "nb_ecoles_total": int(_scalar("SELECT COUNT(*) FROM etablissements_education WHERE code_geo=:c", c=code_insee)),
        "nb_ecoles_publiques": int(_scalar("SELECT COUNT(*) FROM etablissements_education WHERE code_geo=:c AND statut_public_prive ILIKE 'public%'", c=code_insee)),
        "nb_ecoles_privees": int(_scalar("SELECT COUNT(*) FROM etablissements_education WHERE code_geo=:c AND statut_public_prive ILIKE 'priv%'", c=code_insee)),
        "nb_gares": int(_scalar("SELECT COUNT(*) FROM gares_sncf WHERE code_geo=:c", c=code_insee)),
        "score_qualite_vie": 0.0,
        "note_habitants": 0.0,
    }


# ═════════════════════════════════════════════════════════════════════════
# INDICATEURS PAR ZONE (mutualisé : classements, corrélations, radar)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _zone_indicateurs(niveau: str) -> pd.DataFrame:
    """Une ligne par zone avec les indicateurs disponibles dans le schéma."""
    key = _DEPT_KEY[niveau]
    prix = _df(
        f"SELECT g.{key} AS code_zone, "
        f"  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2}) "
        f"        FILTER (WHERE t.type_local='Appartement')) AS prix_m2_appart, "
        f"  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2}) "
        f"        FILTER (WHERE t.type_local='Maison')) AS prix_m2_maison "
        f"FROM transactions_dvf t JOIN geo_lookup g ON g.code_geo = t.code_geo "
        f"WHERE {_DVF_OK} GROUP BY g.{key}")
    rev = _df(
        f"SELECT g.{key} AS code_zone, AVG(r.revenu_median) AS revenu_median, "
        f"  AVG(r.taux_pauvrete) AS taux_pauvrete "
        f"FROM revenus_commune r JOIN geo_lookup g ON g.code_geo = r.code_geo "
        f"GROUP BY g.{key}")
    eco = _df(
        f"SELECT g.{key} AS code_zone, COUNT(*) AS nb_ecoles "
        f"FROM etablissements_education e JOIN geo_lookup g ON g.code_geo = e.code_geo "
        f"GROUP BY g.{key}")
    gar = _df(
        f"SELECT g.{key} AS code_zone, COUNT(*) AS nb_gares "
        f"FROM gares_sncf s JOIN geo_lookup g ON g.code_geo = s.code_geo "
        f"GROUP BY g.{key}")
    df = prix
    for autre in (rev, eco, gar):
        df = df.merge(autre, on="code_zone", how="outer")
    if df.empty:
        df = pd.DataFrame(columns=["code_zone", "prix_m2_appart", "prix_m2_maison",
                                   "revenu_median", "taux_pauvrete", "nb_ecoles", "nb_gares"])
    df["nom"] = df["code_zone"].map(lambda c: _nom_zone(niveau, c))
    return df.fillna(0)


CRITERES_CLASSEMENT = {
    "prix_m2_appart": "Prix au m² (appartement)",
    "prix_m2_maison": "Prix au m² (maison)",
    "revenu_median": "Revenu médian (€)",
    "nb_ecoles": "Nombre d'écoles",
    "nb_gares": "Nombre de gares SNCF",
}


@st.cache_data(ttl=3600)
def get_top_flop(niveau: str, critere: str, n: int = 10, ordre: str = "desc") -> pd.DataFrame:
    df = _zone_indicateurs(niveau)
    if df.empty or critere not in df.columns:
        return pd.DataFrame(columns=["code_zone", "nom", "valeur", "critere"])
    df = df[["code_zone", "nom", critere]].rename(columns={critere: "valeur"})
    df["critere"] = critere
    return df.sort_values("valeur", ascending=(ordre != "desc")).head(n).reset_index(drop=True)


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
        ("Taux pauvreté (%)", "taux_pauvrete"),
        ("Nb écoles", "nb_ecoles_total"),
        ("Nb gares SNCF", "nb_gares"),
    ]
    fiches = {code: get_fiche_commune(code) for code in codes_zones}
    rows = []
    for label, k in indicateurs:
        row = {"Indicateur": label}
        for code in codes_zones:
            row[fiches[code]["nom"]] = fiches[code].get(k, "—")
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def get_radar_zones(niveau: str, codes_zones: list[str]) -> pd.DataFrame:
    if not codes_zones:
        return pd.DataFrame(columns=["zone", "axe", "score"])
    df = _zone_indicateurs(niveau)
    df = df[df["code_zone"].isin(codes_zones)]
    if df.empty:
        return pd.DataFrame(columns=["zone", "axe", "score"])
    axes = {"Prix attractif": "prix_m2_appart", "Revenu": "revenu_median",
            "Éducation": "nb_ecoles", "Transports": "nb_gares"}
    rows = []
    for label, col in axes.items():
        vmin, vmax = df[col].min(), df[col].max()
        for _, r in df.iterrows():
            if vmax == vmin:
                score = 50.0
            else:
                norm = (r[col] - vmin) / (vmax - vmin) * 100
                score = 100 - norm if col == "prix_m2_appart" else norm  # prix bas = mieux
            rows.append({"zone": r["nom"], "axe": label, "score": round(float(score), 1)})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def get_correlation(indicateur_x: str, indicateur_y: str, niveau: str = "departement") -> pd.DataFrame:
    df = _zone_indicateurs(niveau)
    cols = {"code_zone", "nom", indicateur_x, indicateur_y}
    if df.empty or not cols.issubset(df.columns):
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
    key = _DEPT_KEY[niveau]
    df = _df(
        f"SELECT g.{key} AS code_zone, "
        f"  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS prix_m2_median "
        f"FROM transactions_dvf t JOIN geo_lookup g ON g.code_geo = t.code_geo "
        f"WHERE t.type_local = :type AND {_DVF_OK} "
        f"  AND t.annee = (SELECT MAX(annee) FROM transactions_dvf) "
        f"GROUP BY g.{key}", type=type_local)
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
    {"code": "taux_pauvrete", "nom": "Taux de pauvreté", "categorie": "économie", "unite": "%"},
    {"code": "prix_m2_appart", "nom": "Prix m² appartement", "categorie": "immobilier", "unite": "EUR"},
    {"code": "prix_m2_maison", "nom": "Prix m² maison", "categorie": "immobilier", "unite": "EUR"},
    {"code": "nb_ecoles", "nom": "Nombre d'écoles", "categorie": "éducation", "unite": "unités"},
    {"code": "nb_gares", "nom": "Nombre de gares SNCF", "categorie": "transports", "unite": "unités"},
]


def get_indicateurs_disponibles() -> pd.DataFrame:
    return pd.DataFrame(INDICATEURS_DISPONIBLES)


@st.cache_data(ttl=3600)
def get_indicateur(niveau: str, code_zone: str, indicateur: str, annee: int | None = None) -> pd.DataFrame:
    if indicateur in ("revenu_median", "taux_pauvrete"):
        rjoin = "" if niveau == "commune" else "JOIN geo_lookup g ON g.code_geo = r.code_geo"
        rwhere = "r.code_geo = :code" if niveau == "commune" else f"g.{_DEPT_KEY[niveau]} = :code"
        df = _df(f"SELECT annee, AVG({indicateur}) AS valeur FROM revenus_commune r {rjoin} "
                 f"WHERE {rwhere} GROUP BY annee ORDER BY annee", code=code_zone)
    else:
        join, where = _dvf_zone(niveau)
        df = _df(f"SELECT t.annee, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {_PRIX_M2})) AS valeur "
                 f"FROM transactions_dvf t {join} WHERE {where} AND {_DVF_OK} "
                 f"GROUP BY t.annee ORDER BY t.annee", code=code_zone)
    df["indicateur"] = indicateur
    return df


# ═════════════════════════════════════════════════════════════════════════
# CONTOURS GEOJSON (référentiel géométrique statique, servi depuis data/geo)
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
# ANALYSE TEXTUELLE (MongoDB — non branché dans ce schéma : retours vides)
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
