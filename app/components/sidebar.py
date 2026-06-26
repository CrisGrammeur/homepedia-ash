"""
Sidebar : recherche par nom + sélecteurs en cascade.
Stocke la sélection dans st.session_state pour partage entre pages.
"""
import streamlit as st
from data.data_access import get_regions, get_departements, get_communes, search_communes


def render_sidebar() -> dict:
    st.sidebar.title("Navigation")

    # ─── Recherche par nom (M04) ────────────────────────────────────────
    st.sidebar.markdown("##### Recherche rapide")
    query = st.sidebar.text_input(
        "Nom d'une commune",
        placeholder="Ex: Lyon, Bordeaux...",
        label_visibility="collapsed",
        key="sb_query",
    )
    if query:
        resultats = search_communes(query, limit=8)
        if not resultats.empty:
            st.sidebar.caption(f"{len(resultats)} résultat(s) :")
            for _, r in resultats.iterrows():
                if st.sidebar.button(
                    f"{r['nom']} ({r['code_dept']})",
                    key=f"search_{r['code_insee']}",
                    width="stretch",
                ):
                    st.session_state["selected_commune"] = r["code_insee"]
                    st.session_state["selected_commune_nom"] = r["nom"]
                    st.switch_page("pages/3_Fiche_commune.py")
        else:
            st.sidebar.caption("Aucun résultat.")

    st.sidebar.divider()

    # ─── Sélecteurs en cascade ──────────────────────────────────────────
    st.sidebar.markdown("##### Zone d'analyse")

    niveau = st.sidebar.radio(
        "Niveau",
        options=["region", "departement", "commune"],
        format_func=lambda x: {"region": "Région", "departement": "Département", "commune": "Commune"}[x],
        horizontal=True,
        label_visibility="collapsed",
        key="sb_niveau",
    )

    try:
        regions = get_regions()
    except Exception:
        st.sidebar.error("Connexion impossible.")
        st.error(
            "Connexion à Databricks échouée. À vérifier : le secret **DATABRICKS_TOKEN** "
            "(scope BI Tools), que le **SQL Warehouse** est bien démarré, et la **version de "
            "Python** (3.12 recommandé — 3.14 est trop récent pour le connecteur Databricks)."
        )
        st.stop()
    if regions.empty:
        st.sidebar.error("Aucune zone disponible.")
        st.error("Base de données accessible mais vide (aucune commune retournée).")
        st.stop()

    region_choisie = st.sidebar.selectbox(
        "Région",
        options=regions["code_region"].tolist(),
        format_func=lambda c: regions.loc[regions["code_region"] == c, "nom"].iloc[0],
        key="sb_region",
    )
    code_zone = region_choisie
    zone_label = regions.loc[regions["code_region"] == region_choisie, "nom"].iloc[0]

    if niveau in ("departement", "commune"):
        depts = get_departements(code_region=region_choisie)
        dept_choisi = st.sidebar.selectbox(
            "Département",
            options=depts["code_dept"].tolist(),
            format_func=lambda c: f"{c} — {depts.loc[depts['code_dept'] == c, 'nom'].iloc[0]}",
            key="sb_dept",
        )
        code_zone = dept_choisi
        zone_label = depts.loc[depts["code_dept"] == dept_choisi, "nom"].iloc[0]

        if niveau == "commune":
            communes = get_communes(code_dept=dept_choisi)
            commune_choisie = st.sidebar.selectbox(
                "Commune",
                options=communes["code_insee"].tolist(),
                format_func=lambda c: communes.loc[communes["code_insee"] == c, "nom"].iloc[0],
                key="sb_commune",
            )
            code_zone = commune_choisie
            zone_label = communes.loc[communes["code_insee"] == commune_choisie, "nom"].iloc[0]

    # ─── Filtres globaux ────────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.markdown("##### Filtres")

    type_local = st.sidebar.multiselect(
        "Type de bien",
        options=["Maison", "Appartement", "Local commercial", "Terrain"],
        default=["Maison", "Appartement"],
        key="sb_type",
    )

    annee_range = st.sidebar.slider("Période", 2018, 2025, (2020, 2025), 1, key="sb_annee")

    selection = {
        "niveau": niveau,
        "code_zone": code_zone,
        "zone_label": zone_label,
        "type_local": type_local,
        "annee_min": annee_range[0],
        "annee_max": annee_range[1],
    }
    st.session_state["selection"] = selection
    return selection
