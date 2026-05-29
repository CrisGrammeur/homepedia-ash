"""
Corrélations (S07) : relation statistique entre deux indicateurs
sur l'ensemble des zones d'un niveau géographique.
"""
import streamlit as st
import numpy as np
import plotly.express as px

from components.sidebar import render_sidebar
from data.mock_data import get_correlation, get_indicateurs_disponibles

render_sidebar()

st.title("Corrélations entre indicateurs")
st.caption(
    "Croise deux indicateurs sur toutes les zones d'un niveau pour repérer "
    "un lien statistique (ex : revenu médian vs taux de pauvreté)."
)

# ─── Sélection des indicateurs ───────────────────────────────────────────
indic = get_indicateurs_disponibles()
codes = indic["code"].tolist()
labels = dict(zip(indic["code"], indic["nom"]))
unites = dict(zip(indic["code"], indic["unite"]))

col_x, col_y, col_niv = st.columns(3)
with col_x:
    ind_x = st.selectbox("Indicateur X", codes, index=1, format_func=lambda c: labels[c])
with col_y:
    ind_y = st.selectbox("Indicateur Y", codes, index=2, format_func=lambda c: labels[c])
with col_niv:
    niveau = st.radio(
        "Niveau", ["departement", "region"],
        format_func=lambda x: x.capitalize(), horizontal=True,
    )

if ind_x == ind_y:
    st.warning("Choisis deux indicateurs différents pour calculer une corrélation.")
    st.stop()

# ─── Calcul ──────────────────────────────────────────────────────────────
df = get_correlation(ind_x, ind_y, niveau=niveau)
r = float(df[ind_x].corr(df[ind_y]))

# Interprétation textuelle du coefficient de Pearson
a = abs(r)
force = (
    "très faible" if a < 0.2 else
    "faible" if a < 0.4 else
    "modéré" if a < 0.6 else
    "fort" if a < 0.8 else
    "très fort"
)
sens = "positif" if r >= 0 else "négatif"

c1, c2, c3 = st.columns(3)
c1.metric("Coefficient de Pearson (r)", f"{r:+.2f}")
c2.metric("Force du lien", force.capitalize())
c3.metric("Nombre de zones", len(df))

st.divider()

# ─── Nuage de points + tendance ──────────────────────────────────────────
lbl_x = f"{labels[ind_x]} ({unites[ind_x]})"
lbl_y = f"{labels[ind_y]} ({unites[ind_y]})"

fig = px.scatter(
    df, x=ind_x, y=ind_y, hover_name="nom",
    labels={ind_x: lbl_x, ind_y: lbl_y},
    color_discrete_sequence=["#1E3A8A"],
)

# Ligne de régression linéaire (np.polyfit — pas de dépendance statsmodels)
pente, ordonnee = np.polyfit(df[ind_x], df[ind_y], 1)
xs = np.array([df[ind_x].min(), df[ind_x].max()])
fig.add_scatter(
    x=xs, y=pente * xs + ordonnee,
    mode="lines", name="Tendance",
    line=dict(color="#F59E0B", dash="dash"),
)
fig.update_layout(height=460, margin=dict(l=10, r=10, t=10, b=10),
                  legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

st.info(
    f"Lien **{force}** et **{sens}** entre « {labels[ind_x]} » et « {labels[ind_y]} » "
    f"(r = {r:+.2f}) sur {len(df)} {niveau}(s). "
    "Corrélation n'implique pas causalité."
)

