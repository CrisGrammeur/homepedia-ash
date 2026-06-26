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
from components.disclaimer import render_disclaimer
from data.data_access import (
    get_kpis_zone,
    get_prix_serie_temporelle,
    get_prix_carte,
    get_geojson,
    get_evolution_prix,
)

st.title("Explorer une zone")

# Drill-down demandé via un clic sur la carte : on pré-sélectionne la zone
# AVANT que la sidebar n'instancie ses widgets (sinon Streamlit refuse la modif).
_drill = st.session_state.pop("_drill", None)
if _drill:
    st.session_state["sb_niveau"] = _drill["niveau"]
    if _drill.get("region"):
        st.session_state["sb_region"] = _drill["region"]
    if _drill.get("dept"):
        st.session_state["sb_dept"] = _drill["dept"]

selection = render_sidebar()

niveau = selection["niveau"]
code_zone = selection["code_zone"]
zone_label = selection["zone_label"]
types = selection["type_local"]

st.markdown(f"### {zone_label} \n*niveau : {niveau}*")
render_disclaimer()

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

    # Communes géolocalisées (certaines n'ont pas de GPS → exclues de la carte à points).
    if {"latitude", "longitude"}.issubset(df.columns):
        df_geo = df.dropna(subset=["latitude", "longitude"])
    else:
        df_geo = df.iloc[0:0]

    if sous_niveau == "commune" and not df_geo.empty:
        # Communes : pas de contours → pastilles ponctuelles colorées par prix au m².
        vmin = float(df_geo["prix_m2_median"].min())
        vmax = float(df_geo["prix_m2_median"].max())
        if vmax == vmin:
            vmax = vmin + 1
        colormap = cm.LinearColormap(
            ["#1A9850", "#FFFFBF", "#D73027"], # vert → jaune → rouge
            vmin=vmin, vmax=vmax,
            caption="Prix médian (€/m²)",
        )
        centre = [df_geo["latitude"].mean(), df_geo["longitude"].mean()]
        m = folium.Map(location=centre, zoom_start=9, tiles="cartodbpositron")
        for _, r in df_geo.iterrows():
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
            f"{len(df_geo)} commune(s) géolocalisée(s) du département. "
            "Couleur = prix médian au m²."
        )
    elif geojson_sous:
        # Départements : choroplèthe CLIQUABLE (clic = drill vers les communes).
        prix_par_code = dict(zip(df["code_zone"], df["prix_m2_median"]))
        for f in geojson_sous:
            f["properties"]["prix"] = int(prix_par_code.get(f["properties"]["code"], 0))
        gj = {"type": "FeatureCollection", "features": geojson_sous}

        prix_vals = [v for v in prix_par_code.values() if v]
        colormap = cm.LinearColormap(
            ["#1A9850", "#FFFFBF", "#D73027"],
            vmin=min(prix_vals) if prix_vals else 0,
            vmax=max(prix_vals) if prix_vals else 1,
            caption="Prix médian (€/m²)",
        )

        def _style(feat):
            p = feat["properties"].get("prix") or 0
            return {"fillColor": colormap(p) if p else "lightgray",
                    "fillOpacity": 0.7, "color": "white", "weight": 1}

        m = folium.Map(location=[46.6, 2.5], zoom_start=6, tiles="cartodbpositron")
        folium.GeoJson(
            gj, style_function=_style,
            highlight_function=lambda _: {"weight": 3, "color": "#1E3A8A"},
            tooltip=folium.GeoJsonTooltip(fields=["nom", "prix"], aliases=["Département", "Prix €/m² :"]),
        ).add_to(m)
        colormap.add_to(m)
        m.fit_bounds(m.get_bounds())
        out = st_folium(m, height=520, use_container_width=True,
                        returned_objects=["last_active_drawing"], key="map_explorer")
        st.caption(f"{len(geojson_sous)} département(s) — clique un département pour explorer ses communes.")

        drawing = (out or {}).get("last_active_drawing")
        props = drawing.get("properties") if drawing else None
        if props and props.get("code"):
            d_code = props["code"]
            d_nom = props.get("nom") or d_code
            st.info(f"**{d_nom}** ({d_code}) — prix médian {props.get('prix', 0):,} €/m²")
            if st.button(f"Explorer {d_nom} et ses communes", key="drill_dept"):
                st.session_state["_drill"] = {"niveau": "departement",
                                              "region": props.get("code_parent"), "dept": d_code}
                st.rerun()
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
