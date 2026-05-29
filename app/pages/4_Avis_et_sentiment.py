"""
Avis & sentiment : analyse NLP des avis ville-ideale.fr.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components.sidebar import render_sidebar
from data.mock_data import (
    get_sentiment_aggrege,
    get_wordcloud,
    get_avis_recents,
    get_notes_categorielles,
)

st.title("Avis & sentiment")

selection = render_sidebar()
code_insee = st.session_state.get("selected_commune")

if not code_insee and selection and selection.get("niveau") == "commune":
    code_insee = selection["code_zone"]

if not code_insee:
    st.warning(
        "Cette page s'applique à une commune. "
        "Sélectionne une commune via la barre latérale ou la page Fiche commune."
    )
    st.stop()

# Récupère le nom
nom_commune = st.session_state.get("selected_commune_nom") or selection.get("zone_label", code_insee)
st.markdown(f"### Avis sur **{nom_commune}**")
st.caption(f"Source : ville-ideale.fr · Analyse NLP réalisée par le pipeline Spark de Peace")

# ─── Vue d'ensemble : sentiment + score ──────────────────────────────────
sent = get_sentiment_aggrege("commune", code_insee)
notes = get_notes_categorielles(code_insee)

col_donut, col_radar = st.columns(2)

with col_donut:
    st.markdown("##### Distribution du sentiment")
    fig_donut = go.Figure(go.Pie(
        labels=["Positif", "Neutre", "Négatif"],
        values=[sent["positif"], sent["neutre"], sent["negatif"]],
        hole=0.55,
        marker_colors=["#4CAF50", "#FFC107", "#F44336"],
    ))
    fig_donut.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_donut, use_container_width=True)

with col_radar:
    st.markdown("##### Notes par catégorie")
    labels = list(notes.keys())
    values = list(notes.values())
    fig_radar = go.Figure(go.Scatterpolar(
        r=values + [values[0]],
        theta=labels + [labels[0]],
        fill="toself",
        line_color="#1E3A8A",
    ))
    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        height=380, margin=dict(l=20, r=20, t=20, b=20), showlegend=False,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# ─── Word cloud par thème ────────────────────────────────────────────────
st.markdown("##### Nuage de mots")
theme = st.selectbox(
    "Thème",
    options=["global", "securite", "transports", "education"],
    format_func=lambda x: {
        "global": "Global", "securite": "Sécurité",
        "transports": "Transports", "education": "Éducation",
    }[x],
)

mots = get_wordcloud("commune", code_insee, theme=theme)
df_mots = pd.DataFrame(mots).sort_values("poids", ascending=True)
color_map = {"positif": "#4CAF50", "neutre": "#9E9E9E", "negatif": "#F44336"}
fig_wc = px.bar(
    df_mots, x="poids", y="mot",
    color="sentiment", color_discrete_map=color_map, orientation="h",
    labels={"poids": "Fréquence pondérée", "mot": ""},
)
fig_wc.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_wc, use_container_width=True)

st.divider()

# ─── Avis individuels ────────────────────────────────────────────────────
st.markdown("##### Avis récents")

filtre_sentiment = st.radio(
    "Filtrer par sentiment",
    options=["tous", "positif", "neutre", "negatif"],
    format_func=lambda x: {"tous": "Tous", "positif": "Positifs", "neutre": "Neutres", "negatif": "Négatifs"}[x],
    horizontal=True,
)

avis = get_avis_recents(code_insee, n=15)
if filtre_sentiment != "tous":
    avis = avis[avis["sentiment"] == filtre_sentiment]

if avis.empty:
    st.info("Aucun avis correspondant au filtre.")
else:
    for _, av in avis.iterrows():
        col_a, col_b = st.columns([1, 6])
        with col_a:
            st.markdown(f"**{av['note']}/10**")
            st.caption(av["date"].strftime("%d/%m/%Y"))
        with col_b:
            st.markdown(f"> {av['texte']}")
        st.divider()
