"""
Couche d'accès aux données — VERSION PRODUCTION (Databricks, catalogue `workspace`).

Agrégats : schéma `gold` (prix_par_commune, score_qualite_vie, …).
Référentiel + GPS : schéma `silver` (communes, transactions_dvf).

Mêmes signatures et formats de retour que la couche mock : les pages ne changent pas.

Connexion : variables d'env (ou st.secrets) — aucun secret dans le dépôt :
    DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN

Champs sans source dans Databricks (renvoyés 0/vide) : taux de chômage, densité,
évolution population, note des habitants, et tout le NLP (avis/sentiment/wordcloud).
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

SEUIL_TRANSACTIONS = 5

ARRONDISSEMENTS = {
    "75056": [f"751{i:02d}" for i in range(1, 21)],
    "69123": [f"6938{i}" for i in range(1, 10)],
    "13055": [f"132{i:02d}" for i in range(1, 17)],
}


def _codes_commune(code: str) -> list[str]:
    return [code] + ARRONDISSEMENTS.get(code, [])


# ═════════════════════════════════════════════════════════════════════════
# CONNEXION DATABRICKS (lazy + cache session)
# ═════════════════════════════════════════════════════════════════════════

def _conf(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return DATA_SOURCES.get("databricks", {}).get(key.replace("DATABRICKS_", "").lower(), default)


@st.cache_resource
def _engine() -> sa.Engine:
    url = sa.URL.create(
        "databricks",
        username="token",
        password=_conf("DATABRICKS_TOKEN"),
        host=_conf("DATABRICKS_HOST"),
        query={
            "http_path": _conf("DATABRICKS_HTTP_PATH"),
            "catalog": "workspace",
            "schema": "gold",
        },
    )
    return sa.create_engine(url)


def _df(sql: str, **params) -> pd.DataFrame:
    stmt = sa.text(sql)
    expanding = [sa.bindparam(k, expanding=True) for k, v in params.items()
                 if isinstance(v, (list, tuple))]
    if expanding:
        stmt = stmt.bindparams(*expanding)
    with _engine().connect() as conn:
        return pd.read_sql(stmt, conn, params=params)


def _scalar(sql: str, default=0, **params):
    d = _df(sql, **params)
    if d.empty or pd.isna(d.iloc[0, 0]):
        return default
    return d.iloc[0, 0]


@st.cache_data(ttl=3600)
def _dept_noms() -> dict:
    f = _GEO_DIR / "departements.geojson"
    if not f.exists():
        return {}
    feats = json.loads(f.read_text(encoding="utf-8"))["features"]
    return {x["properties"]["code"]: x["properties"]["nom"] for x in feats}


def _nom_zone(niveau: str, code: str) -> str:
    if niveau == "region":
        return REGIONS_NOMS.get(code, code)
    if niveau == "departement":
        return _dept_noms().get(code, code)
    return str(code)


@st.cache_data(ttl=3600)
def _commune_gps() -> dict:
    """Centroïde GPS par commune (moyenne des transactions DVF). Lourd → caché 1h."""
    df = _df("SELECT code_commune, AVG(try_cast(latitude AS DOUBLE)) lat, "
             "AVG(try_cast(longitude AS DOUBLE)) lon FROM silver.transactions_dvf "
             "WHERE latitude IS NOT NULL GROUP BY code_commune")
    return {r["code_commune"]: (r["lat"], r["lon"])
            for _, r in df.iterrows() if pd.notna(r["lat"]) and pd.notna(r["lon"])}


def _gps(code: str):
    g = _commune_gps()
    if code in g:
        return g[code]
    # Paris/Lyon/Marseille : moyenne des arrondissements.
    pts = [g[c] for c in _codes_commune(code) if c in g]
    if pts:
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return (None, None)


# ═════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIEL GÉOGRAPHIQUE (silver.communes)
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_regions() -> pd.DataFrame:
    df = _df("SELECT DISTINCT `codeRegion` AS code_region FROM silver.communes "
             "WHERE `codeRegion` IS NOT NULL ORDER BY 1")
    df["nom"] = df["code_region"].map(lambda c: REGIONS_NOMS.get(c, c))
    return df


@st.cache_data(ttl=3600)
def get_departements(code_region: str | None = None) -> pd.DataFrame:
    sql = ("SELECT DISTINCT `codeDepartement` AS code_dept, `codeRegion` AS code_region "
           "FROM silver.communes WHERE `codeDepartement` IS NOT NULL")
    df = _df(sql + " AND `codeRegion` = :reg ORDER BY 1", reg=code_region) if code_region \
        else _df(sql + " ORDER BY 1")
    noms = _dept_noms()
    df["nom"] = df["code_dept"].map(lambda c: noms.get(c, c))
    return df


@st.cache_data(ttl=3600)
def get_communes(code_dept: str | None = None) -> pd.DataFrame:
    sql = ("SELECT code AS code_insee, `codeDepartement` AS code_dept, nom, "
           "try_cast(population AS DOUBLE) AS population FROM silver.communes")
    df = _df(sql + " WHERE `codeDepartement` = :dept ORDER BY nom", dept=code_dept) if code_dept \
        else _df(sql + " ORDER BY nom")
    df["population"] = df["population"].fillna(0).astype(int)
    gps = _commune_gps()
    df["latitude"] = df["code_insee"].map(lambda c: gps.get(c, (None, None))[0])
    df["longitude"] = df["code_insee"].map(lambda c: gps.get(c, (None, None))[1])
    return df


@st.cache_data(ttl=3600)
def search_communes(query: str, limit: int = 10) -> pd.DataFrame:
    q = (query or "").strip()
    sql = "SELECT code AS code_insee, `codeDepartement` AS code_dept, nom FROM silver.communes"
    if not q:
        return _df(sql + " ORDER BY nom LIMIT :lim", lim=limit)
    return _df(sql + " WHERE lower(nom) LIKE :pat ORDER BY nom LIMIT :lim",
               pat=f"%{q.lower()}%", lim=limit)


# ═════════════════════════════════════════════════════════════════════════
# PRIX (gold.prix_par_commune / gold.prix_par_departement)
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
        sql = ("SELECT CAST(annee AS INT) AS annee, type_local, "
               "ROUND(SUM(prix_median_m2*nb_transactions)/NULLIF(SUM(nb_transactions),0)) AS prix_m2_median, "
               "SUM(nb_transactions) AS nb_ventes FROM gold.prix_par_commune "
               "WHERE code_commune IN :codes AND type_local IN :types "
               "AND CAST(annee AS INT) BETWEEN :amin AND :amax GROUP BY annee, type_local ORDER BY annee")
        df = _df(sql, codes=_codes_commune(code_zone), types=list(type_local), amin=annee_min, amax=annee_max)
    elif niveau == "departement":
        sql = ("SELECT CAST(annee AS INT) AS annee, type_local, ROUND(prix_median_m2) AS prix_m2_median, "
               "nb_transactions AS nb_ventes FROM gold.prix_par_departement "
               "WHERE code_departement = :code AND type_local IN :types "
               "AND CAST(annee AS INT) BETWEEN :amin AND :amax ORDER BY annee")
        df = _df(sql, code=code_zone, types=list(type_local), amin=annee_min, amax=annee_max)
    else:
        sql = ("SELECT CAST(p.annee AS INT) AS annee, p.type_local, "
               "ROUND(AVG(p.prix_median_m2)) AS prix_m2_median, SUM(p.nb_transactions) AS nb_ventes "
               "FROM gold.prix_par_commune p JOIN silver.communes c ON c.code = p.code_commune "
               "WHERE c.`codeRegion` = :code AND p.type_local IN :types "
               "AND CAST(p.annee AS INT) BETWEEN :amin AND :amax GROUP BY p.annee, p.type_local ORDER BY p.annee")
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
        df = _df("SELECT c.`codeRegion` AS code_zone, ROUND(AVG(p.prix_median_m2)) AS prix_m2_median, "
                 "SUM(p.nb_transactions) AS nb_ventes FROM gold.prix_par_commune p "
                 "JOIN silver.communes c ON c.code = p.code_commune "
                 "WHERE p.annee = :annee AND p.type_local = :type GROUP BY c.`codeRegion`",
                 annee=str(annee), type=type_local)
        df["nom"] = df["code_zone"].map(lambda c: _nom_zone("region", c))
    elif niveau == "departement":
        sql = ("SELECT code_departement AS code_zone, ROUND(prix_median_m2) AS prix_m2_median, "
               "nb_transactions AS nb_ventes FROM gold.prix_par_departement "
               "WHERE annee = :annee AND type_local = :type")
        if code_parent:
            sql += (" AND code_departement IN (SELECT DISTINCT `codeDepartement` "
                    "FROM silver.communes WHERE `codeRegion` = :parent)")
            df = _df(sql, annee=str(annee), type=type_local, parent=code_parent)
        else:
            df = _df(sql, annee=str(annee), type=type_local)
        df["nom"] = df["code_zone"].map(lambda c: _nom_zone("departement", c))
    else:
        sql = ("SELECT code_commune AS code_zone, nom_commune AS nom, "
               "ROUND(prix_median_m2) AS prix_m2_median, nb_transactions AS nb_ventes "
               "FROM gold.prix_par_commune WHERE annee = :annee AND type_local = :type")
        if code_parent:
            sql += (" AND code_commune IN (SELECT code FROM silver.communes "
                    "WHERE `codeDepartement` = :parent)")
            df = _df(sql, annee=str(annee), type=type_local, parent=code_parent)
        else:
            df = _df(sql, annee=str(annee), type=type_local)
        gps = _commune_gps()
        df["latitude"] = df["code_zone"].map(lambda c: gps.get(c, (None, None))[0])
        df["longitude"] = df["code_zone"].map(lambda c: gps.get(c, (None, None))[1])
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
    annee = _scalar("SELECT MAX(annee) FROM gold.prix_par_commune", default=None)
    out = {"prix_m2_median_national": 0, "evolution_1an_national": 0.0,
           "nb_transactions_12mois": 0, "ville_la_plus_chere": ("—", 0),
           "ville_la_moins_chere": ("—", 0), "departement_dynamique": ("—", 0.0)}
    if annee is None:
        return out
    out["prix_m2_median_national"] = int(_scalar(
        "SELECT ROUND(AVG(prix_median_m2)) FROM gold.prix_par_commune WHERE annee = :a", a=annee))
    out["nb_transactions_12mois"] = int(_scalar(
        "SELECT SUM(nb_transactions) FROM gold.prix_par_commune WHERE annee = :a", a=annee))
    villes = _df("SELECT nom_commune AS nom, ROUND(AVG(prix_median_m2)) AS prix "
                 "FROM gold.prix_par_commune WHERE annee = :a GROUP BY nom_commune "
                 "HAVING SUM(nb_transactions) >= 50 ORDER BY prix DESC", a=annee)
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
        col = "code"
    else:
        col = "`codeRegion`" if niveau == "region" else "`codeDepartement`"
    out["population"] = int(_scalar(
        f"SELECT SUM(try_cast(population AS DOUBLE)) FROM silver.communes WHERE {col} = :c", c=code_zone))
    if niveau == "commune":
        out["score_attractivite"] = round(float(_scalar(
            "SELECT score_qualite_vie FROM gold.score_qualite_vie WHERE code_commune = :c", c=code_zone)), 1)
    else:
        jcol = "`codeRegion`" if niveau == "region" else "`codeDepartement`"
        out["score_attractivite"] = round(float(_scalar(
            f"SELECT AVG(q.score_qualite_vie) FROM gold.score_qualite_vie q "
            f"JOIN silver.communes c ON c.code = q.code_commune WHERE c.{jcol} = :c", c=code_zone)), 1)
    return out


# ═════════════════════════════════════════════════════════════════════════
# FICHE COMMUNE
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_fiche_commune(code_insee: str) -> dict:
    dim = _df("SELECT nom, `codeDepartement` AS code_dept, `codeRegion` AS code_region, "
              "try_cast(population AS DOUBLE) AS population FROM silver.communes WHERE code = :c", c=code_insee)
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
    lat, lon = _gps(code_insee)

    def prix_nb(tl):
        d = _df("SELECT ROUND(SUM(prix_median_m2*nb_transactions)/NULLIF(SUM(nb_transactions),0)) AS prix, "
                "COALESCE(SUM(nb_transactions),0) AS nb FROM gold.prix_par_commune "
                "WHERE code_commune IN :codes AND type_local = :tl AND annee = "
                "(SELECT MAX(annee) FROM gold.prix_par_commune WHERE code_commune IN :codes AND type_local = :tl)",
                codes=codes, tl=tl)
        if d.empty or pd.isna(d.iloc[0]["prix"]):
            return 0, 0
        return int(d.iloc[0]["prix"]), int(d.iloc[0]["nb"])
    pa, na = prix_nb("Appartement")
    pm, nm = prix_nb("Maison")

    rev = _df("SELECT CAST(revenu_median AS DOUBLE) AS revenu_median, "
              "CAST(taux_pauvrete_dept AS DOUBLE) AS taux_pauvrete_dept FROM gold.revenus_par_commune "
              "WHERE code_insee = :c ORDER BY annee DESC LIMIT 1", c=code_insee)
    annee_max = _scalar("SELECT MAX(annee) FROM gold.prix_par_commune", default=None)
    nb_ecoles = int(_scalar("SELECT SUM(nb_etablissements) FROM gold.education_par_commune "
                            "WHERE Code_commune IN :codes", codes=codes))
    return {
        "code_insee": code_insee,
        "nom": dim.iloc[0]["nom"],
        "latitude": lat, "longitude": lon,
        "population": pop,
        "densite": 0, "evolution_pop_5ans": 0.0,
        "revenu_median": int(rev.iloc[0]["revenu_median"]) if not rev.empty and pd.notna(rev.iloc[0]["revenu_median"]) else 0,
        "taux_pauvrete": float(rev.iloc[0]["taux_pauvrete_dept"]) if not rev.empty and pd.notna(rev.iloc[0]["taux_pauvrete_dept"]) else 0.0,
        "taux_chomage": 0.0,
        "prix_m2_appart": pa, "prix_m2_maison": pm,
        "nb_ventes_appart": na, "nb_ventes_maison": nm,
        "loyer_predit_m2": round(float(_scalar("SELECT AVG(try_cast(replace(loyer_median_m2, ',', '.') AS DOUBLE)) FROM gold.loyers_par_commune WHERE code_insee IN :codes", codes=codes)), 1),
        "nb_transactions_2024": int(_scalar("SELECT SUM(nb_transactions) FROM gold.prix_par_commune WHERE code_commune IN :codes AND annee = :a", codes=codes, a=annee_max)),
        "nb_ecoles_total": nb_ecoles,
        "nb_ecoles_publiques": 0, "nb_ecoles_privees": 0,
        "ecoles_pour_1000hab": round(nb_ecoles / pop * 1000, 2) if pop else 0.0,
        "nb_gares": int(_scalar("SELECT SUM(nb_gares) FROM gold.score_transport WHERE code_commune IN :codes", codes=codes)),
        "score_qualite_vie": round(float(_scalar("SELECT score_qualite_vie FROM gold.score_qualite_vie WHERE code_commune = :c", c=code_insee)), 1),
        "note_habitants": 0.0,
    }


# ═════════════════════════════════════════════════════════════════════════
# INDICATEURS PAR ZONE (classements, corrélations, radar) — gold.score_qualite_vie
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _zone_indicateurs(niveau: str) -> pd.DataFrame:
    if niveau == "commune":
        df = _df("SELECT code_commune AS code_zone, nom, prix_m2_final AS prix_m2, revenu_median, "
                 "taux_pauvrete, nb_gares, nb_etablissements AS nb_ecoles, loyer_m2, score_qualite_vie "
                 "FROM gold.score_qualite_vie")
    else:
        col = "`codeRegion`" if niveau == "region" else "`codeDepartement`"
        df = _df(f"SELECT c.{col} AS code_zone, AVG(q.prix_m2_final) AS prix_m2, "
                 "AVG(q.revenu_median) AS revenu_median, AVG(q.taux_pauvrete) AS taux_pauvrete, "
                 "AVG(q.nb_gares) AS nb_gares, AVG(q.nb_etablissements) AS nb_ecoles, "
                 "AVG(q.loyer_m2) AS loyer_m2, AVG(q.score_qualite_vie) AS score_qualite_vie "
                 "FROM gold.score_qualite_vie q JOIN silver.communes c ON c.code = q.code_commune "
                 f"WHERE c.{col} IS NOT NULL GROUP BY c.{col}")
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
        df = _df("SELECT c.`codeRegion` AS code_zone, ROUND(AVG(p.prix_median_m2)) AS prix_m2_median "
                 "FROM gold.prix_par_commune p JOIN silver.communes c ON c.code = p.code_commune "
                 "WHERE p.type_local = :type AND p.annee = (SELECT MAX(annee) FROM gold.prix_par_commune) "
                 "GROUP BY c.`codeRegion`", type=type_local)
    else:
        df = _df("SELECT code_departement AS code_zone, ROUND(prix_median_m2) AS prix_m2_median "
                 "FROM gold.prix_par_departement WHERE type_local = :type "
                 "AND annee = (SELECT MAX(annee) FROM gold.prix_par_departement)", type=type_local)
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
    {"code": "taux_pauvrete", "nom": "Taux de pauvreté (dépt.)", "categorie": "économie", "unite": "%"},
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
# ANALYSE TEXTUELLE (non branché : retours vides)
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
