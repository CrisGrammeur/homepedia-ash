"""
Disclaimer affiché sur chaque page : transparence sur le calcul des indicateurs.
"""
import streamlit as st


def render_disclaimer():
    st.caption(
        "Indicateurs et scores calculés à partir de données ouvertes (DVF, INSEE, "
        "Éducation nationale, SNCF). Le **détail des calculs, des sources et des limites** "
        "est sur la page **Méthodologie**. Certaines valeurs sont des estimations, "
        "des agrégats départementaux ou peuvent être incomplètes."
    )
