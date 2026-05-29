# HOMEPEDIA — Interface


## Architecture cible

```
Sources (DVF · INSEE · ville-ideale.fr · GeoJSON · SNCF · OSM)
        ↓
BRONZE (tables en STRING)
        ↓ 
SILVER (typé, nettoyé, clés normalisées)
        ↓ Agrégats Spark
GOLD (PostgreSQL/PostGIS + MongoDB)
        ↓
INTERFACE Streamlit
```


## Structure

```
homepedia/
├── app/
│   ├── main.py                              # Vue nationale
│   ├── pages/
│   │   ├── 1_Explorer.py                  # Drill-down région→dept→commune
│   │   ├── 2_Comparateur.py               # 2-3 zones côte à côte (M08)
│   │   ├── 3_Fiche_commune.py             # Tout sur 1 commune (M05)
│   │   ├── 4_Avis_et_sentiment.py         # NLP, sentiment, wordcloud (M10)
│   │   └── 5_Pouvoir_dachat.py            # 'Avec X€, où ?' (S08)
│   ├── components/sidebar.py                # Recherche + sélecteurs cascade
│   ├── data/mock_data.py                    # Data_access.py
│   └── utils/config.py
├── requirements.txt
└── README.md
```

## Couverture des features (backlog)

| Feature backlog | Page | Statut |
|---|---|---|
| M01 Carte nationale | `main.py` | ✅ Folium (choroplèthe régions + départements) |
| M02 Prix m² par zone | `main.py` + `Explorer` | ✅ mock |
| M03 Changement niveau géo | sidebar | ✅ |
| M04 Recherche par ville | sidebar + Fiche commune | ✅ mock |
| M05 Fiche commune complète | `Fiche_commune` | ✅ mock |
| M06 Filtres dynamiques | sidebar | ✅ |
| M07 Évolution des prix | `Explorer` + `Fiche` | ✅ mock |
| M08 Comparaison zones | `Comparateur` | ✅ mock |
| M09 Classement top/flop | `main.py` | ✅ mock |
| M10 Avis & sentiment + word cloud | `Avis_et_sentiment` | ✅ mock |
| M11 Filtre type de bien | sidebar | ✅ |
| S07 Corrélations | `Correlations` | ✅ mock |
| S08 Pouvoir d'achat | `Pouvoir_dachat` | ✅ mock |

## Mapping mock → réel

Quand on aura les tables Gold prêtes :

1. Renommer `app/data/mock_data.py` → `app/data/data_access.py`
2. Remplacer chaque fonction par sa version SQL/Mongo (signatures inchangées)
3. Ajouter `@st.cache_data(ttl=3600)` sur les fonctions de lecture lourdes

Exemple de remplacement :

```python
# Avant (mock)
def get_prix_serie_temporelle(niveau, code_zone, ...):
    seed = ...
    return pd.DataFrame(...)

# Après (réel)
@st.cache_data(ttl=3600)
def get_prix_serie_temporelle(niveau, code_zone, type_local=None, ...):
    table = {"region": "prix_region_annuel",
             "departement": "prix_dept_annuel",
             "commune": "prix_commune_annuel"}[niveau]
    key = {"region": "code_region",
           "departement": "code_dept",
           "commune": "code_insee"}[niveau]
    query = f"""
        SELECT annee, type_local, prix_m2_median, nb_ventes
        FROM {table}
        WHERE {key} = %(zone)s
          AND annee BETWEEN %(min)s AND %(max)s
          AND type_local = ANY(%(types)s)
        ORDER BY annee
    """
    return pd.read_sql(query, conn, params={...})
```