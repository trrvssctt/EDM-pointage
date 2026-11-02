# Livrables du projet — pointage biométrique multisite (EDM S.A.)

| Semaine | Livrable | Dossier | État |
|---|---|---|---|
| 1 | Analyse et conception | — | remis |
| **2** | **Base de données PostgreSQL et API centrale** | [`semaine-2-bdd-api/`](semaine-2-bdd-api/) | **prêt** |
| 3 | Interfaces (administration, bornes, application mobile), tests sur site, mémoire | [`semaine-3-preparation/`](semaine-3-preparation/) | éléments préparés (captures, diagrammes) |

## Livrable n° 2

- `Livrable_S2_Base_de_donnees_et_API.md` : document principal (source)
- `generer_pdf.sh` : produit `Livrable_S2_Base_de_donnees_et_API.pdf` (et une version HTML) avec pandoc et Chrome
- `annexes/` : dictionnaire de données, référence de l'API, résultats des tests, `schema.sql`, `openapi.json`
- `outils/` : `generer_annexes.py` (annexes régénérées depuis le code), `comparer_schema.py` (script SQL ↔ API), rapports JUnit

Mettre à jour après une modification du code :

```bash
.venv/bin/python -m pytest --junitxml=livrables/semaine-2-bdd-api/outils/resultats_tests_sqlite.xml
.venv/bin/python livrables/semaine-2-bdd-api/outils/generer_annexes.py
livrables/semaine-2-bdd-api/generer_pdf.sh
```
