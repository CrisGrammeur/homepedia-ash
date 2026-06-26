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
    "Prix de marché observé (source **DVF**), par commune (ou département), par année et par type de bien "
    "(appartement / maison). Pour chaque transaction on calcule le prix au m², puis on en prend la "
    "**médiane** (`percentile_approx(…, 0.5)`)."
)
st.latex(r"\text{prix\_m2} = \frac{\text{valeur\_foncière}}{\text{surface réelle bâtie}} \quad;\quad \text{prix médian} = \text{médiane des prix\_m2}")
st.info(
    "La **médiane** (et non la moyenne) est utilisée car la distribution des prix est très **asymétrique** "
    "(coefficient d'asymétrie ≈ 5,8) : la moyenne serait tirée vers le haut par quelques biens très chers."
)
st.warning(
    "**Filtre des aberrants** : seules les transactions avec **100 € < prix/m² < 50 000 €** sont retenues.\n\n"
    "**Prix de repli** : pour les communes **sans transaction DVF (~18 150 communes)**, le prix affiché est "
    "celui du **département** (colonne `source_prix = 'departement'`).\n\n"
    "**Petits volumes** : à faible nombre de ventes, la médiane reste peu fiable (cf. le **nombre de ventes** affiché).\n\n"
    "**Paris / Lyon / Marseille** : transactions rattachées aux **arrondissements** — l'app les réagrège vers la commune-mère."
)

st.markdown("#### Évolution des prix (1, 3, 5 ans)")
st.markdown("Croissance du prix médian sur l'horizon choisi, à partir des prix annuels.")
st.latex(r"\text{croissance}_{n\text{ ans}} = \left(\frac{\text{prix}_{\text{année}}}{\text{prix}_{\text{année}-n}} - 1\right)\times 100")
st.warning("Historique limité à **2021–2025** : la croissance « 5 ans » n'est calculable que si les deux années existent, sinon elle vaut 0.")

st.markdown("#### Loyer au m²")
st.markdown("Loyer **prédit** au m² (logement type), issu du modèle national « Carte des loyers ».")
st.warning("C'est une **estimation modélisée**, pas un loyer réellement observé pour un bien donné. À considérer comme un ordre de grandeur.")

st.markdown("#### Effort immobilier")
st.markdown(
    "Indicateur standard **INSEE / FNAIM** : nombre d'**années de revenu médian** nécessaires pour acheter "
    "un logement de référence de **70 m²** (surface type INSEE). Médiane nationale ≈ **6,7 ans**."
)
st.latex(r"\text{effort} = \frac{\text{prix\_m2}\times 70}{\text{revenu médian annuel}}")
st.markdown("Interprétation indicative : *Très accessible* (~3) · *Accessible* (~6) · *Modéré* (~8) · *Élevé / Très élevé* (>15).")

st.markdown("#### Rentabilité locative brute")
st.markdown(
    "Rendement brut annuel d'un investissement locatif. Le seuil de **5 %** est le **consensus professionnel "
    "(FNAIM)** au-delà duquel l'achat est favorable à la location. Médiane nationale ≈ **5,8 %**."
)
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
    "Indice **composite** combinant cinq dimensions, chacune **normalisée min-max entre 0 et 1** "
    "sur l'ensemble des communes, pondérée puis ramenée sur 100. Les pondérations sont issues de la "
    "**littérature académique** en économie immobilière."
)
st.latex(r"n_x = \frac{x - x_{min}}{x_{max} - x_{min}} \quad;\quad \text{score} = 100 \times (0.30\,n_{prix} + 0.25\,n_{revenu} + 0.20\,n_{transport} + 0.15\,n_{\text{éduc}} + 0.10\,n_{social})")
st.markdown("""
| Dimension | Poids | Calculée à partir de |
|---|---|---|
| Prix | **30 %** | prix médian au m² (normalisé) |
| Revenu | **25 %** | revenu médian des ménages |
| Transport | **20 %** | desserte (nombre de gares) |
| Éducation | **15 %** | nombre d'établissements scolaires |
| Social | **10 %** | indicateur social |

Catégories : **Faible** (< 30) · **Moyen** (30–50) · **Bon** (≥ 50).
""")
st.warning(
    "**Composite** : un score unique masque des réalités contrastées (une commune peut être bien notée "
    "en transport mais mal en éducation).\n\n"
    "**Normalisation relative** : les sous-scores sont min-max sur toutes les communes — un score "
    "mesure donc une position *relative*, pas une valeur absolue.\n\n"
    "**Transformation `log1p`** appliquée aux dimensions transport et éducation avant normalisation, "
    "pour atténuer l'effet des très grandes villes (Paris).\n\n"
    "**Prix de repli** : pour les communes sans prix communal fiable, le sous-score prix s'appuie sur "
    "le **prix départemental** (`source_prix = 'departement'`)."
)

st.markdown("#### Profil de commune (cluster)")
st.markdown(
    "Classification non supervisée par **K-means** en **5 profils** (k=5 retenu par la **méthode du coude** "
    "et le score de **silhouette** ≈ 0,38). Variables : prix m², revenu médian, nb de gares, nb d'établissements, "
    "taux de pauvreté — toutes **standardisées** (`StandardScaler`, centrage-réduction) avant le clustering."
)
st.markdown(
    "Profils obtenus : *Commune rurale*, *Bourg avec services*, *Territoire rural privilégié*, "
    "*Zone résidentielle aisée*, *Ville-centre urbaine*."
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
