"""
Comparateur : 2 à 3 zones mises en regard.
Tableau + radar chart.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components.sidebar import render_sidebar
from components.disclaimer import render_disclaimer
from data.data_access import (
    get_communes,
    get_departements,
    get_regions,
    compare_zones,
    get_radar_zones,
)

render_sidebar()

st.title("Comparateur de zones")
st.caption("Compare 2 à 3 zones côte à côte sur les indicateurs clés.")
render_disclaimer()

# ─── Sélection des zones à comparer ──────────────────────────────────────
st.markdown("##### Sélectionne les zones à comparer")

niveau = st.radio(
    "Niveau de comparaison",
    options=["commune", "departement"],
    format_func=lambda x: x.capitalize(),
    horizontal=True,
)

if niveau == "commune":
    all_codes = []
    for d in ["75", "77", "92", "69", "13", "35", "31", "34", "33", "44", "59", "67"]:
        all_codes.append(get_communes(d))
    pool = pd.concat(all_codes, ignore_index=True)
    options = pool["code_insee"].tolist()
    label_fn = lambda c: pool.loc[pool["code_insee"] == c, "nom"].iloc[0]
else:
    all_depts = []
    for r in get_regions()["code_region"]:
        all_depts.append(get_departements(r))
    pool = pd.concat(all_depts, ignore_index=True)
    options = pool["code_dept"].tolist()
    label_fn = lambda c: f"{c} — {pool.loc[pool['code_dept'] == c, 'nom'].iloc[0]}"

choix = st.multiselect(
    "Choisis 2 ou 3 zones",
    options=options,
    format_func=label_fn,
    max_selections=3,
    default=options[:2] if len(options) >= 2 else options,
)

if len(choix) < 2:
    st.info("Sélectionne au moins 2 zones pour lancer la comparaison.")
    st.stop()

st.divider()

# ─── Tableau comparatif ──────────────────────────────────────────────────
st.markdown("##### Tableau comparatif")
df_compare = compare_zones(niveau, choix)
st.dataframe(df_compare, width="stretch", hide_index=True)

st.divider()

# ─── Radar chart ─────────────────────────────────────────────────────────
st.markdown("##### Radar des scores")
df_radar = get_radar_zones(niveau, choix)

fig = go.Figure()
for zone in df_radar["zone"].unique():
    sub = df_radar[df_radar["zone"] == zone]
    fig.add_trace(go.Scatterpolar(
        r=sub["score"].tolist() + [sub["score"].iloc[0]],
        theta=sub["axe"].tolist() + [sub["axe"].iloc[0]],
        fill="toself",
        name=zone,
    ))
fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    height=480,
    margin=dict(l=40, r=40, t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)
