"""
HOMEPEDIA — Application Streamlit
Vue nationale : KPIs France entière + carte régionale + top/flop.

Lancer : streamlit run app/main.py
"""
import streamlit as st
import plotly.express as px
import folium
import branca.colormap as cm
from streamlit_folium import st_folium

from components.sidebar import render_sidebar
from data.data_access import (
    get_kpis_nationaux,
    get_prix_carte,
    get_geojson,
    get_top_flop,
    CRITERES_CLASSEMENT,
)
from utils.config import APP_CONFIG

st.set_page_config(
    page_title=APP_CONFIG["app_name"],
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

selection = render_sidebar()

# ─── Header ───────────────────────────────────────────────────────────────
st.title("HOMEPEDIA")
st.caption("Exploration du marché immobilier français — analyse statistique, cartographique et textuelle")
st.divider()

st.subheader("Vue nationale")

# ─── KPIs nationaux ───────────────────────────────────────────────────────
kpis = get_kpis_nationaux()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Prix médian France", f"{kpis['prix_m2_median_national']:,} €/m²", f"{kpis['evolution_1an_national']:+.1f}%")
c2.metric("Transactions (12 mois)", f"{kpis['nb_transactions_12mois']:,}")
ville_chere, prix_chere = kpis["ville_la_plus_chere"]
c3.metric("Ville la plus chère", ville_chere, f"{prix_chere:,} €/m²")
ville_pas_chere, prix_pas_chere = kpis["ville_la_moins_chere"]
c4.metric("Ville la moins chère", ville_pas_chere, f"{prix_pas_chere:,} €/m²")

st.divider()

# ─── Carte choroplèthe nationale ──────────────────────────────────────────
col_map, col_classement = st.columns([3, 2])

with col_map:
    st.markdown("##### Prix au m² par région")
    annee_carte = st.slider("Année affichée", 2018, 2025, 2024, key="annee_nat")
    type_bien_carte = st.radio(
        "Type de bien",
        ["Appartement", "Maison"],
        horizontal=True,
        key="type_nat",
    )

    df_carte = get_prix_carte(niveau="region", annee=annee_carte, type_local=type_bien_carte)
    geojson_regions = get_geojson(niveau="region")

    if geojson_regions:
        prix_par_code = dict(zip(df_carte["code_zone"], df_carte["prix_m2_median"]))
        for f in geojson_regions:
            f["properties"]["prix"] = int(prix_par_code.get(f["properties"]["code"], 0))
        gj = {"type": "FeatureCollection", "features": geojson_regions}

        prix_vals = [v for v in prix_par_code.values() if v]
        colormap = cm.LinearColormap(
            ["#1A9850", "#FFFFBF", "#D73027"],
            vmin=min(prix_vals) if prix_vals else 0,
            vmax=max(prix_vals) if prix_vals else 1,
            caption=f"Prix médian {type_bien_carte.lower()} (€/m²) — {annee_carte}",
        )

        def _style(feat):
            p = feat["properties"].get("prix") or 0
            return {"fillColor": colormap(p) if p else "lightgray",
                    "fillOpacity": 0.7, "color": "white", "weight": 1}

        m = folium.Map(location=[46.6, 2.5], zoom_start=5, tiles="cartodbpositron")
        folium.GeoJson(
            gj, style_function=_style,
            highlight_function=lambda _: {"weight": 3, "color": "#1E3A8A"},
            tooltip=folium.GeoJsonTooltip(fields=["nom", "prix"], aliases=["Région", "Prix €/m² :"]),
        ).add_to(m)
        colormap.add_to(m)
        out = st_folium(m, height=500, use_container_width=True,
                        returned_objects=["last_active_drawing"], key="map_nat")
        st.caption("Clique une région pour l'explorer en détail.")

        drawing = (out or {}).get("last_active_drawing")
        props = drawing.get("properties") if drawing else None
        if props and props.get("code"):
            r_code = props["code"]
            r_nom = props.get("nom") or r_code
            st.info(f"**{r_nom}** — prix médian {props.get('prix', 0):,} €/m²")
            if st.button(f"Explorer {r_nom}", key="drill_region"):
                st.session_state["_drill"] = {"niveau": "region", "region": r_code}
                st.switch_page("pages/1_Explorer.py")
    else:
        # Filet de sécurité si le GeoJSON est absent
        fig = px.bar(
            df_carte.sort_values("prix_m2_median"),
            x="prix_m2_median", y="nom", orientation="h",
            color="prix_m2_median", color_continuous_scale="RdYlGn_r",
            labels={"prix_m2_median": "Prix médian (€/m²)", "nom": "Région"},
        )
        fig.update_layout(height=500, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

with col_classement:
    st.markdown("##### Top & flop")
    critere = st.selectbox(
        "Classer les départements par",
        options=list(CRITERES_CLASSEMENT.keys()),
        format_func=lambda c: CRITERES_CLASSEMENT[c],
        key="critere_nat",
    )

    tab_top, tab_flop = st.tabs(["Top 10", "Flop 10"])
    with tab_top:
        top = get_top_flop("departement", critere, n=10, ordre="desc")
        st.dataframe(
            top[["nom", "valeur"]].rename(columns={"nom": "Département", "valeur": CRITERES_CLASSEMENT[critere]}),
            width="stretch", hide_index=True,
        )
    with tab_flop:
        flop = get_top_flop("departement", critere, n=10, ordre="asc")
        st.dataframe(
            flop[["nom", "valeur"]].rename(columns={"nom": "Département", "valeur": CRITERES_CLASSEMENT[critere]}),
            width="stretch", hide_index=True,
        )

st.divider()

# ─── Footer / navigation ──────────────────────────────────────────────────
st.markdown("##### Pour aller plus loin")
nav_cols = st.columns(4)
nav_cols[0].page_link("pages/1_Explorer.py", label="Explorer une zone", width="stretch")
nav_cols[1].page_link("pages/2_Comparateur.py", label="Comparer des zones", width="stretch")
nav_cols[2].page_link("pages/3_Fiche_commune.py", label="Fiche commune", width="stretch")
nav_cols[3].page_link("pages/4_Avis_et_sentiment.py", label="Avis & sentiment", width="stretch")
