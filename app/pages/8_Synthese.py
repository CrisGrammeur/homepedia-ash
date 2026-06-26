"""
Synthèse — ce que les données révèlent.
Conclusions de l'analyse, présentées en enseignements clés (page de documentation).
"""
import streamlit as st

from components.disclaimer import render_disclaimer

st.title("Synthèse — ce que les données révèlent")
st.caption("Les grands enseignements tirés de l'analyse du marché immobilier français.")
render_disclaimer()

st.divider()

INSIGHTS = [
    ("blue", "1 — Un marché extrêmement inégal",
     "L'écart est de **26×** entre Sin-le-Noble (566 €/m²) et Paris 6ᵉ (14 998 €/m²). "
     "Pourtant **56 % des communes** ont des appartements à moins de **2 500 €/m²**. "
     "Paris est une exception, pas la norme."),
    ("green", "2 — Un marché plus accessible qu'il n'y paraît",
     "Médiane nationale de **6,7 ans** d'effort immobilier. **63 % des communes** ont un effort "
     "inférieur à **8 ans** — finançable pour un ménage avec un bon dossier bancaire."),
    ("orange", "3 — Les revenus amplifient les inégalités",
     "Corrélation de **Pearson de 0,56** entre prix et revenus. Entre zones modestes et aisées, "
     "les revenus augmentent de **1,6×** mais les prix de **2,2×** — phénomène d'amplification immobilière."),
    ("red", "4 — Le retournement post-Covid est confirmé",
     "Boom 2021-2022 (**+9,5 %**), plateau 2023, correction depuis 2024 (**-2,7 %**). "
     "Volume de transactions **-40 %**. Des communes bretonnes ont doublé pendant que des banlieues "
     "parisiennes perdaient 40 %."),
    ("green", "5 — La rentabilité favorise les villes moyennes",
     "**69 % des communes** ont une rentabilité brute supérieure à **5 %**. Les stations de ski "
     "(1,3 %) et le littoral huppé sont les moins rentables. Médiane nationale : **5,8 % brut**."),
    ("blue", "6 — Il n'existe pas de commune parfaite",
     "Aucune commune n'atteint **70/100** au score qualité de vie. La distribution est concentrée "
     "autour de **42** : quand le prix est accessible, le revenu est faible ; quand le revenu est "
     "élevé, le prix l'est aussi."),
]

for couleur, titre, texte in INSIGHTS:
    with st.container(border=True):
        st.markdown(f":{couleur}[**{titre}**]")
        st.markdown(texte)

st.divider()
st.caption(
    "Ces enseignements résument des tendances d'ensemble : ils ne préjugent pas de cas particuliers. "
    "Méthodes de calcul et limites détaillées sur la page **Méthodologie**."
)
