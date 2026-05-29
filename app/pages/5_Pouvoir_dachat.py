"""
Pouvoir d'achat (S08) : 'Avec X€, où puis-je acheter ?'
Feature différenciante identifiée dans le backlog comme MVP.
"""
import streamlit as st
import plotly.express as px
import folium
from streamlit_folium import st_folium

from components.sidebar import render_sidebar
from data.mock_data import get_zones_accessibles, get_geojson

render_sidebar()

st.title("Pouvoir d'achat")
st.caption("Avec un budget donné, identifie les zones où ton projet est réalisable.")

# ─── Paramètres ──────────────────────────────────────────────────────────
col_budget, col_surface, col_type = st.columns(3)

with col_budget:
    budget = st.number_input(
        "Budget total (€)",
        min_value=50_000, max_value=2_000_000,
        value=300_000, step=10_000,
    )

with col_surface:
    surface = st.slider(
        "Surface minimale (m²)",
        min_value=20, max_value=200, value=60, step=5,
    )

with col_type:
    type_bien = st.selectbox(
        "Type de bien",
        options=["Appartement", "Maison"],
    )

niveau_analyse = st.radio(
    "Niveau d'analyse",
    options=["departement", "region"],
    format_func=lambda x: x.capitalize(),
    horizontal=True,
)

st.divider()

# ─── Calcul des zones accessibles ────────────────────────────────────────
df = get_zones_accessibles(
    budget=budget, surface_min=surface,
    type_local=type_bien, niveau=niveau_analyse,
)

# ─── KPIs synthétiques ───────────────────────────────────────────────────
nb_accessibles = int(df["accessible"].sum())
nb_total = len(df)
pct = (nb_accessibles / nb_total * 100) if nb_total > 0 else 0

c1, c2, c3 = st.columns(3)
c1.metric(f"{niveau_analyse}s accessibles", f"{nb_accessibles} / {nb_total}", f"{pct:.0f}%")
c2.metric("Surface médiane achetable", f"{df['surface_max_achetable'].median():.0f} m²")
c3.metric("Coût médian zone", f"{df['cout_estime'].median():,.0f} €")

st.divider()

# ─── Carte / tableau ──────────────────────────────────────────────────────
tab_acc, tab_all, tab_carte = st.tabs(["Zones accessibles", "Toutes les zones", "Vue cartographique"])

with tab_acc:
    accessibles = df[df["accessible"]].sort_values("prix_m2_median")
    if accessibles.empty:
        st.error(
            f"Aucune zone accessible avec ce budget pour {surface} m². "
            "Essaie d'augmenter le budget ou de réduire la surface."
        )
    else:
        st.success(
            f"{len(accessibles)} {niveau_analyse}(s) accessible(s) — "
            f"prix médian de la zone la moins chère : {accessibles.iloc[0]['prix_m2_median']:,} €/m²"
        )
        st.dataframe(
            accessibles[["nom", "prix_m2_median", "cout_estime", "surface_max_achetable"]].rename(columns={
                "nom": niveau_analyse.capitalize(),
                "prix_m2_median": "Prix €/m²",
                "cout_estime": f"Coût pour {surface} m² (€)",
                "surface_max_achetable": "Surface max possible (m²)",
            }),
            width="stretch", hide_index=True,
        )

with tab_all:
    st.markdown(f"##### Toutes les {niveau_analyse}s, accessibles ou non")
    df_display = df.copy()
    df_display["statut"] = df_display["accessible"].map({True: "Accessible", False: "Hors budget"})
    fig = px.bar(
        df_display.sort_values("prix_m2_median"),
        x="prix_m2_median", y="nom", color="statut",
        orientation="h",
        color_discrete_map={"Accessible": "#4CAF50", "Hors budget": "#E0E0E0"},
        labels={"prix_m2_median": "Prix médian (€/m²)", "nom": niveau_analyse.capitalize(), "statut": ""},
    )
    # Ligne du budget /surface
    seuil = budget / surface
    fig.add_vline(
        x=seuil, line_dash="dash", line_color="red",
        annotation_text=f"Seuil : {seuil:,.0f} €/m²",
    )
    fig.update_layout(height=max(400, len(df) * 22), margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

with tab_carte:
    geojson_zones = get_geojson(niveau_analyse)
    if geojson_zones:
        acc_par_code = dict(zip(df["code_zone"], df["accessible"]))
        prix_par_code = dict(zip(df["code_zone"], df["prix_m2_median"]))
        surf_par_code = dict(zip(df["code_zone"], df["surface_max_achetable"]))
        for f in geojson_zones:
            code = f["properties"]["code"]
            f["properties"]["statut"] = "Accessible" if acc_par_code.get(code) else "Hors budget"
            f["properties"]["prix"] = int(prix_par_code.get(code, 0))
            f["properties"]["surface_max"] = int(surf_par_code.get(code, 0))
        gj = {"type": "FeatureCollection", "features": geojson_zones}

        def _style(feat):
            accessible = acc_par_code.get(feat["properties"]["code"], False)
            return {
                "fillColor": "#4CAF50" if accessible else "#E57373",
                "fillOpacity": 0.65, "color": "white", "weight": 1,
            }

        m = folium.Map(location=[46.6, 2.5], zoom_start=5, tiles="cartodbpositron")
        folium.GeoJson(
            gj, style_function=_style,
            tooltip=folium.GeoJsonTooltip(
                fields=["nom", "statut", "prix", "surface_max"],
                aliases=["", "", "Prix €/m² :", f"Surface max pour {budget:,.0f} € :"],
            ),
        ).add_to(m)
        m.fit_bounds(m.get_bounds())
        st_folium(m, height=520, use_container_width=True, returned_objects=[], key="map_pa")
        st.caption("Vert = accessible, rouge = hors budget. Survole une zone pour le détail.")
    else:
        st.info(
            f"Contours indisponibles pour ce niveau ({niveau_analyse}) ; "
            "les onglets tableau et graphe restent disponibles."
        )

