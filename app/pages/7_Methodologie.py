"""
Méthodologie & référence des indicateurs.
Page de documentation : décrit chaque métrique, sa source, son calcul et ses limites.
Volontairement sans dépendance à la base (consultable même si la BDD est indisponible).
"""
import streamlit as st

st.title("Méthodologie & indicateurs")
st.caption("Comment chaque métrique est collectée, calculée, et ce qu'il faut savoir avant de l'interpréter.")

st.warning(
    "**À lire avant tout.** Les indicateurs proviennent de sources ouvertes agrégées par "
    "commune sur la période **2021–2025**. Certains sont des **estimations** ou des **composites** "
    "(détaillés ci-dessous). Plusieurs ont une **granularité ou une fiabilité limitée** : lisez les "
    "avertissements propres à chaque indicateur."
)

# ─── Sources ──────────────────────────────────────────────────────────────
st.markdown("### Sources de données")
st.markdown("""
| Source | Fournit | Table |
|---|---|---|
| **DVF** — Demandes de valeurs foncières (data.gouv.fr) | Transactions immobilières, prix | `fact_prix`, `fact_prix_dept`, `fact_evolution` |
| **INSEE Filosofi** | Revenu médian, taux de pauvreté | `fact_revenus` |
| **Carte des loyers** (ANIL / data.gouv.fr) | Loyer prédit au m² | `fact_loyers` |
| **Annuaire de l'Éducation nationale** | Établissements scolaires | `fact_education` |
| **SNCF Open Data** | Gares | `fact_transport` |
| **Référentiel INSEE** | Communes, population, codes | `dim_communes` |
| **Composites internes** | Score qualité de vie, effort, rentabilité, clusters | `fact_qualite_vie`, `fact_effort`, `fact_rentabilite`, `fact_clusters` |
""")

st.divider()

# ─── Immobilier ───────────────────────────────────────────────────────────
st.markdown("### Immobilier")

st.markdown("#### Prix médian au m²")
st.markdown(
    "Prix de marché observé, par commune (ou département), par année et par type de bien "
    "(appartement / maison). On calcule, pour chaque transaction, le prix au m², puis on en prend la **médiane**."
)
st.latex(r"\text{prix\_m2} = \frac{\text{valeur\_foncière}}{\text{surface}} \quad;\quad \text{prix médian} = \text{médiane des prix\_m2}")
st.info("La **médiane** (et non la moyenne) est utilisée : elle est robuste aux ventes atypiques (très chères ou très basses).")
st.warning(
    "**Petits volumes** : dans les communes à faible nombre de transactions, la médiane est "
    "peu fiable. Vérifiez le **nombre de ventes** affiché.\n\n"
    "**Paris / Lyon / Marseille** : les transactions sont rattachées aux **arrondissements** "
    "(75101…, 69381…, 13201…), pas à la commune-mère. La fiche de Paris/Lyon/Marseille « entière » "
    "peut donc afficher un prix à 0."
)

st.markdown("#### Évolution des prix (1, 3, 5 ans)")
st.markdown("Croissance du prix médian sur l'horizon choisi, à partir des prix annuels.")
st.latex(r"\text{croissance}_{n\text{ ans}} = \left(\frac{\text{prix}_{\text{année}}}{\text{prix}_{\text{année}-n}} - 1\right)\times 100")
st.warning("Historique limité à **2021–2025** : la croissance « 5 ans » n'est calculable que si les deux années existent, sinon elle vaut 0.")

st.markdown("#### Loyer au m²")
st.markdown("Loyer **prédit** au m² (logement type), issu du modèle national « Carte des loyers ».")
st.warning("C'est une **estimation modélisée**, pas un loyer réellement observé pour un bien donné. À considérer comme un ordre de grandeur.")

st.markdown("#### Effort immobilier")
st.markdown("Nombre d'**années de revenu médian** nécessaires pour acheter un logement de référence de **70 m²**.")
st.latex(r"\text{effort} = \frac{\text{prix\_m2}\times 70}{\text{revenu médian annuel}}")
st.markdown("Interprétation indicative : *Très accessible* (~3) · *Accessible* (~6) · *Modéré* (~8) · *Élevé / Très élevé* (>15).")

st.markdown("#### Rentabilité locative brute")
st.markdown("Rendement brut annuel d'un investissement locatif (avant charges et fiscalité).")
st.latex(r"\text{rentabilité brute (\%)} = \frac{\text{loyer\_m2}\times 12}{\text{prix\_m2}}\times 100")
st.warning("**Brute** : ne déduit ni charges, ni taxe foncière, ni vacance, ni fiscalité. Le rendement net réel est inférieur.")

st.divider()

# ─── Socio-économique ─────────────────────────────────────────────────────
st.markdown("### Socio-économique")

st.markdown("#### Revenu médian")
st.markdown("Revenu disponible médian des ménages (INSEE Filosofi), par commune et par année.")
st.warning("Pour préserver le **secret statistique**, l'INSEE ne publie pas le revenu des très petites communes : la valeur peut être manquante.")

st.markdown("#### Taux de pauvreté")
st.error(
    "**Indicateur DÉPARTEMENTAL.** Le taux de pauvreté disponible ici est celui du **département**, "
    "appliqué à toutes les communes qui en font partie — ce n'est **pas** une mesure communale. "
    "À interpréter comme un contexte départemental, pas comme une caractéristique propre à la commune."
)

st.divider()

# ─── Équipements ──────────────────────────────────────────────────────────
st.markdown("### Équipements & services")
st.markdown(
    "- **Nombre d'écoles / établissements** : décompte des établissements de l'Annuaire de l'Éducation "
    "nationale rattachés à la commune (tous niveaux confondus).\n"
    "- **Nombre de gares** : décompte des gares SNCF rattachées à la commune."
)
st.warning("Ce sont des **décomptes bruts**, non rapportés à la population. Une grande ville aura mécaniquement plus d'équipements qu'un village.")

st.divider()

# ─── Synthèse ─────────────────────────────────────────────────────────────
st.markdown("### Indicateurs de synthèse")

st.markdown("#### Score qualité de vie (sur 100)")
st.markdown(
    "Indice **composite** combinant cinq dimensions, chacune normalisée entre 0 et 1 "
    "(prix, revenu, transport, éducation, social), puis ramenée sur 100."
)
st.latex(r"\text{score} \approx 100 \times \big(\text{combinaison pondérée de } n_{\text{prix}}, n_{\text{revenu}}, n_{\text{transport}}, n_{\text{éducation}}, n_{\text{social}}\big)")
st.markdown("Catégories : **Faible** (< 30) · **Moyen** (30–50) · **Bon** (≥ 50).")
st.warning(
    "**Composite** : un score unique masque des réalités contrastées (une commune peut être bien notée "
    "en transport mais mal en éducation).\n\n"
    "**Pondération à confirmer** : la combinaison exacte des sous-scores est définie dans le pipeline "
    "amont et n'est pas redocumentée ici.\n\n"
    "**Prix de repli** : pour les communes sans prix communal fiable (dont Paris/Lyon/Marseille), "
    "le sous-score prix s'appuie sur le **prix départemental** (`source_prix = 'departement'`)."
)

st.markdown("#### Profil de commune (cluster)")
st.markdown(
    "Classification non supervisée des communes en **5 profils** types à partir de leurs indicateurs : "
    "*Commune rurale*, *Bourg avec services*, *Territoire rural privilégié*, *Zone résidentielle aisée*, "
    "*Ville-centre urbaine*."
)
st.warning("Un cluster est une **catégorie descriptive**, pas un classement de qualité.")

st.divider()

# ─── Pouvoir d'achat ──────────────────────────────────────────────────────
st.markdown("### Pouvoir d'achat")
st.markdown("Pour un budget et une surface donnés, une zone est dite **accessible** si :")
st.latex(r"\text{prix\_m2}\times \text{surface} \le \text{budget} \qquad ; \qquad \text{surface max} = \frac{\text{budget}}{\text{prix\_m2}}")
st.warning("Calcul basé sur le **prix médian** de la zone : c'est un ordre de grandeur, pas le prix d'un bien réel. Frais de notaire, travaux et apport ne sont pas inclus.")

st.divider()

# ─── Limites globales ─────────────────────────────────────────────────────
st.markdown("### Limites & données non disponibles")
st.markdown("""
Pour transparence, voici ce que cette base **ne couvre pas** (les champs concernés sont affichés à 0 ou masqués) :

- **Avis & sentiment des habitants** : nécessite la couche NLP (MongoDB) — non branchée. La page *Avis & sentiment* est inactive.
- **Coordonnées GPS** des communes : absentes → les cartes par **points** (niveau commune) sont remplacées par des graphiques ; les **choroplèthes** région/département fonctionnent.
- **Taux de chômage, densité, évolution de la population** : non présents dans cette base.
- **Note des habitants** : dépend des avis (NLP) — non disponible.
""")

st.divider()

# ─── Revue d'expert ───────────────────────────────────────────────────────
st.markdown("### Revue d'expert — pistes d'amélioration")
st.markdown("""
Recommandations pour fiabiliser l'interprétation :

1. **Distinguer clairement le taux de pauvreté départemental** du niveau communal (déjà signalé partout où il apparaît).
2. **Pondérer les équipements par la population** (écoles / 1 000 habitants, accès aux gares) pour comparer des communes de tailles différentes.
3. **Afficher un seuil de fiabilité** sur les prix : masquer ou marquer les médianes calculées sur un trop faible nombre de transactions.
4. **Consolider Paris/Lyon/Marseille** en réagrégeant les arrondissements vers la commune-mère.
5. **Documenter la pondération exacte** du score qualité de vie côté pipeline pour une transparence totale.
""")
