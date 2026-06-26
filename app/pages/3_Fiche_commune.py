"""
Fiche commune (M05) : tout sur une commune en une page.
Page accessible depuis la recherche ou la sidebar.
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import folium
from streamlit_folium import st_folium

from components.sidebar import render_sidebar
from data.data_access import (
    get_fiche_commune,
    get_prix_serie_temporelle,
    get_notes_categorielles,
    get_wordcloud,
    get_avis_recents,
    get_communes,
    search_communes,
)

selection = render_sidebar()

st.title("Fiche commune")

# ─── Sélection de la commune ─────────────────────────────────────────────
# Priorité : commune choisie via la recherche, sinon via sidebar, sinon sélecteur ici
code_insee = st.session_state.get("selected_commune")

if not code_insee and selection.get("niveau") == "commune":
    code_insee = selection["code_zone"]

if not code_insee:
    st.markdown("##### Choisis une commune")
    col_search, col_dept = st.columns(2)
    with col_search:
        q = st.text_input("Recherche par nom", placeholder="Lyon, Bordeaux...")
        if q:
            resultats = search_communes(q, limit=5)
            for _, r in resultats.iterrows():
                if st.button(f"{r['nom']} ({r['code_dept']})", key=f"fc_{r['code_insee']}"):
                    st.session_state["selected_commune"] = r["code_insee"]
                    st.rerun()
    with col_dept:
        st.caption("Ou choisis directement dans la sidebar (niveau = Commune)")
    st.stop()

# ─── Récupération des données ────────────────────────────────────────────
fiche = get_fiche_commune(code_insee)

# Code INSEE absent du référentiel → on évite d'afficher des chiffres factices
if fiche["nom"] == "Commune inconnue":
    st.error(
        f"Aucune commune ne correspond au code INSEE `{code_insee}`. "
        "Choisis-en une autre."
    )
    if st.button("Changer de commune"):
        st.session_state.pop("selected_commune", None)
        st.rerun()
    st.stop()

# ─── Header ──────────────────────────────────────────────────────────────
col_titre, col_score, col_map = st.columns([2, 1, 2])
with col_titre:
    st.markdown(f"## {fiche['nom']}")
    st.caption(f"Code INSEE : `{code_insee}` · Pop. {fiche['population']:,} hab. · Densité {fiche['densite']:,.0f} hab/km²")
with col_score:
    st.metric("Score qualité de vie", f"{fiche['score_qualite_vie']}/100")
with col_map:
    lat, lon = fiche["latitude"], fiche["longitude"]
    if lat is not None and lon is not None:
        m = folium.Map(location=[lat, lon], zoom_start=12, tiles="cartodbpositron")
        folium.Marker(
            [lat, lon],
            tooltip=fiche["nom"],
            popup=f"{fiche['nom']} — {fiche['prix_m2_appart']:,} €/m² (appart.)",
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(m)
        st_folium(m, height=200, use_container_width=True, returned_objects=[], key="map_fiche")
    else:
        st.caption("Localisation cartographique non disponible.")

st.divider()

# ─── Bloc 1 : indicateurs immobilier ─────────────────────────────────────
st.markdown("##### Immobilier")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prix m² appartement", f"{fiche['prix_m2_appart']:,} €")
c2.metric("Prix m² maison", f"{fiche['prix_m2_maison']:,} €")
c3.metric("Loyer prédit /m²", f"{fiche['loyer_predit_m2']} €")
c4.metric("Transactions 2024", f"{fiche['nb_transactions_2024']:,}")

if min(fiche["nb_ventes_appart"], fiche["nb_ventes_maison"]) < 5:
    st.caption(
        f"Prix à interpréter avec prudence : faible volume de ventes sur la dernière année "
        f"({fiche['nb_ventes_appart']} appartements, {fiche['nb_ventes_maison']} maisons)."
    )

# Mini graphe d'évolution
serie = get_prix_serie_temporelle("commune", code_insee, ["Maison", "Appartement"], 2018, 2025)
fig_evol = px.line(
    serie, x="annee", y="prix_m2_median", color="type_local", markers=True,
    labels={"annee": "", "prix_m2_median": "Prix médian (€/m²)", "type_local": ""},
)
fig_evol.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                       legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig_evol, use_container_width=True)

st.divider()

# ─── Bloc 2 : socio-éco ──────────────────────────────────────────────────
st.markdown("##### Socio-économique")
c1, c2 = st.columns(2)
c1.metric("Revenu médian", f"{fiche['revenu_median']:,} €")
c2.metric("Taux de pauvreté (dépt.)", f"{fiche['taux_pauvrete']}%")

st.divider()

# ─── Bloc 3 : équipements ────────────────────────────────────────────────
st.markdown("##### Équipements & services")
c1, c2, c3 = st.columns(3)
c1.metric("Écoles (total)", fiche["nb_ecoles_total"])
c2.metric("Écoles / 1 000 hab.", f"{fiche['ecoles_pour_1000hab']:.2f}")
c3.metric("Gares SNCF", fiche["nb_gares"])

st.caption("Sources : annuaire de l'éducation nationale et SNCF Open Data.")

st.divider()

# ─── Bloc 4 : avis des habitants (NLP) ───────────────────────────────────
st.markdown("##### Avis des habitants")

notes = get_notes_categorielles(code_insee)
mots = get_wordcloud("commune", code_insee, "global")
avis = get_avis_recents(code_insee, n=5)

if not notes and not mots and avis.empty:
    st.caption("Avis et analyse NLP non disponibles dans cette version.")
else:
    col_radar, col_wc = st.columns(2)
    with col_radar:
        if notes:
            labels, values = list(notes.keys()), list(notes.values())
            fig_radar = go.Figure(go.Scatterpolar(
                r=values + [values[0]], theta=labels + [labels[0]],
                fill="toself", line_color="#1E3A8A",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
                height=380, margin=dict(l=20, r=20, t=20, b=20), showlegend=False,
            )
            st.plotly_chart(fig_radar, use_container_width=True)
    with col_wc:
        if mots:
            df_mots = pd.DataFrame(mots).sort_values("poids", ascending=True).tail(10)
            color_map = {"positif": "#4CAF50", "neutre": "#9E9E9E", "negatif": "#F44336"}
            fig_mots = px.bar(
                df_mots, x="poids", y="mot",
                color="sentiment", color_discrete_map=color_map, orientation="h",
                labels={"poids": "", "mot": ""},
            )
            fig_mots.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_mots, use_container_width=True)
    if not avis.empty:
        with st.expander("Voir les avis récents"):
            for _, av in avis.iterrows():
                st.markdown(f"**{av['note']}/10** — *{av['date'].strftime('%d/%m/%Y')}*")
                st.markdown(f"> {av['texte']}")
                st.divider()

# ─── Actions ──────────────────────────────────────────────────────────────
st.divider()
col_a, col_b, col_c = st.columns(3)
with col_a:
    if st.button("Comparer avec d'autres", width="stretch"):
        st.switch_page("pages/2_Comparateur.py")
with col_b:
    if st.button("Voir tous les avis", width="stretch"):
        st.switch_page("pages/4_Avis_et_sentiment.py")
with col_c:
    if st.button("Changer de commune", width="stretch"):
        st.session_state.pop("selected_commune", None)
        st.rerun()
