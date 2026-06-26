"""
Explorer une zone : drill-down région → département → commune.
Carte + évolution des prix + classement local.
"""
import streamlit as st
import plotly.express as px
import folium
import branca.colormap as cm
from streamlit_folium import st_folium

from components.sidebar import render_sidebar
from data.data_access import (
    get_kpis_zone,
    get_prix_serie_temporelle,
    get_prix_carte,
    get_geojson,
    get_evolution_prix,
)

st.title("Explorer une zone")

selection = render_sidebar()

niveau = selection["niveau"]
code_zone = selection["code_zone"]
zone_label = selection["zone_label"]
types = selection["type_local"]

st.markdown(f"### {zone_label} \n*niveau : {niveau}*")

# ─── KPIs zone ────────────────────────────────────────────────────────────
kpis = get_kpis_zone(niveau, code_zone)
evol = get_evolution_prix(niveau, code_zone)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Prix médian €/m²", f"{kpis['prix_m2_median']:,}", f"{kpis['evolution_1an']:+.1f}%")
c2.metric("Croissance 5 ans", f"{evol['croissance_5ans']:+.1f}%")
c3.metric("Transactions (12 mois)", f"{kpis['nb_ventes']:,}")
c4.metric("Population", f"{kpis['population']:,}")

st.divider()

# ─── Évolution temporelle ─────────────────────────────────────────────────
st.markdown("##### Évolution des prix")

serie = get_prix_serie_temporelle(
    niveau, code_zone, type_local=types,
    annee_min=selection["annee_min"], annee_max=selection["annee_max"],
)

fig_serie = px.line(
    serie, x="annee", y="prix_m2_median", color="type_local",
    markers=True,
    labels={"annee": "Année", "prix_m2_median": "Prix médian (€/m²)", "type_local": "Type"},
)
fig_serie.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_serie, use_container_width=True)

st.divider()

# ─── Carte des sous-zones ─────────────────────────────────────────────────
st.markdown("##### Détail dans la zone")


sous_niveau = {"region": "departement", "departement": "commune", "commune": None}[niveau]

if sous_niveau is None:
    st.info(
        "Vous êtes au niveau le plus fin (commune). "
        "Passez à la page **Fiche commune** pour voir tous les détails."
    )
    if st.button("Voir la fiche complète"):
        st.session_state["selected_commune"] = code_zone
        st.session_state["selected_commune_nom"] = zone_label
        st.switch_page("pages/3_Fiche_commune.py")
else:
    annee = st.slider("Année", 2018, 2025, 2024, key="annee_zone")
    type_bien = st.radio("Type", ["Appartement", "Maison"], horizontal=True, key="type_zone")

    df = get_prix_carte(
        niveau=sous_niveau, annee=annee,
        type_local=type_bien, code_parent=code_zone,
    )
    geojson_sous = get_geojson(sous_niveau, code_parent=code_zone)

    if sous_niveau == "commune" and {"latitude", "longitude"}.issubset(df.columns):
        # Communes : pas de contours → pastilles ponctuelles colorées par prix au m².
        vmin, vmax = float(df["prix_m2_median"].min()), float(df["prix_m2_median"].max())
        colormap = cm.LinearColormap(
            ["#1A9850", "#FFFFBF", "#D73027"], # vert → jaune → rouge
            vmin=vmin, vmax=vmax,
            caption="Prix médian (€/m²)",
        )
        centre = [df["latitude"].mean(), df["longitude"].mean()]
        m = folium.Map(location=centre, zoom_start=9, tiles="cartodbpositron")
        for _, r in df.iterrows():
            folium.CircleMarker(
                location=[r["latitude"], r["longitude"]],
                radius=10,
                color=colormap(r["prix_m2_median"]),
                fill=True, fill_opacity=0.85, weight=1,
                tooltip=f"{r['nom']} — {r['prix_m2_median']:,} €/m² · {r['nb_ventes']:,} ventes",
            ).add_to(m)
        colormap.add_to(m)
        st_folium(m, height=520, use_container_width=True, returned_objects=[], key="map_explorer")
        st.caption(
            f"{len(df)} commune(s) du département. Taille des pastilles fixe ; "
            "couleur = prix médian au m²."
        )
    elif geojson_sous:
        # Départements : vraie choroplèthe sur les contours du niveau inférieur.
        prix_par_code = dict(zip(df["code_zone"], df["prix_m2_median"]))
        for f in geojson_sous:
            f["properties"]["prix"] = int(prix_par_code.get(f["properties"]["code"], 0))
        gj = {"type": "FeatureCollection", "features": geojson_sous}

        m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles="cartodbpositron")
        folium.Choropleth(
            geo_data=gj, data=df,
            columns=["code_zone", "prix_m2_median"],
            key_on="feature.properties.code",
            fill_color="YlOrRd", fill_opacity=0.7, line_opacity=0.4,
            nan_fill_color="lightgray",
            legend_name="Prix médian (€/m²)",
        ).add_to(m)
        folium.GeoJson(
            gj,
            style_function=lambda _: {"fillOpacity": 0, "weight": 0},
            tooltip=folium.GeoJsonTooltip(fields=["nom", "prix"], aliases=["", "Prix €/m² :"]),
        ).add_to(m)
        m.fit_bounds(m.get_bounds())
        st_folium(m, height=520, use_container_width=True, returned_objects=[], key="map_explorer")
        st.caption(f"{len(geojson_sous)} département(s) — couleur = prix médian au m².")
    else:
        # Filet de sécurité (ex : région sans contours dispo) → bar chart.
        df_sorted = df.sort_values("prix_m2_median", ascending=True)
        fig = px.bar(
            df_sorted, x="prix_m2_median", y="nom", orientation="h",
            color="prix_m2_median",
            color_continuous_scale="RdYlGn_r",
            labels={"prix_m2_median": "Prix médian (€/m²)", "nom": sous_niveau.capitalize()},
            hover_data=["nb_ventes"],
        )
        fig.update_layout(height=max(300, len(df) * 25), showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Contours indisponibles pour cette zone ({sous_niveau}).")
