"""Génère les annexes du livrable « Base de données et API centrale » à partir du code réel.

  A — dictionnaire de données (modèle SQLAlchemy + commentaires de database/schema.sql)
  B — référence de l'API (schéma OpenAPI de FastAPI) + fichier openapi.json
  C — résultats des tests (rapports JUnit SQLite et PostgreSQL)

Usage (depuis la racine du projet) : .venv/bin/python livrables/semaine-2-bdd-api/outils/generer_annexes.py
"""
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from server.app.database import Base  # noqa: E402
from server.app import models  # noqa: E402,F401
from server.app.main import app  # noqa: E402

ANNEXES = DOSSIER / "annexes"
ANNEXES.mkdir(exist_ok=True)
schema_sql = (RACINE / "database" / "schema.sql").read_text(encoding="utf-8")


def commentaires() -> dict[tuple[str, str | None], str]:
    """Commentaires COMMENT ON TABLE / COLUMN du script SQL."""
    resultat = {}
    for m in re.finditer(r"COMMENT ON (TABLE|COLUMN) ([\w.]+) IS '((?:[^']|'')*)';", schema_sql):
        cible = m.group(2).split(".")
        cle = (cible[0], cible[1] if m.group(1) == "COLUMN" else None)
        resultat[cle] = m.group(3).replace("''", "'")
    return resultat


def type_sql(colonne) -> str:
    t = str(colonne.type)
    return {"DATETIME": "TIMESTAMP", "BLOB": "BYTEA", "FLOAT": "DOUBLE PRECISION"}.get(t, t)


# --- A. Dictionnaire de données ---------------------------------------------------------------
notes = commentaires()
lignes = ["# Annexe A — Dictionnaire de données", "",
          "Généré automatiquement à partir du modèle de l'API (SQLAlchemy) et des commentaires du script "
          "`database/schema.sql`. Légende : **PK** clé primaire, **FK** clé étrangère, **U** valeur unique, "
          "**NN** valeur obligatoire.", ""]
for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
    lignes += [f"### Table `{table.name}`", ""]
    if (table.name, None) in notes:
        lignes += [notes[(table.name, None)], ""]
    uniques = {c.name for c in table.columns if c.unique} | {
        col.name for contrainte in table.constraints if contrainte.__class__.__name__ == "UniqueConstraint"
        for col in contrainte.columns if len(contrainte.columns) == 1}
    uniques |= {col.name for index in table.indexes if index.unique for col in index.columns}
    lignes += ["| Colonne | Type | Contraintes | Description |", "|---|---|---|---|"]
    for c in table.columns:
        contraintes = [x for x, ok in (("PK", c.primary_key), ("NN", not c.nullable and not c.primary_key),
                                      ("U", c.name in uniques)) if ok]
        contraintes += [f"FK → {fk.column.table.name}" for fk in c.foreign_keys]
        lignes.append(f"| `{c.name}` | {type_sql(c)} | {', '.join(contraintes)} | {notes.get((table.name, c.name), '')} |")
    lignes.append("")
(ANNEXES / "A_dictionnaire_de_donnees.md").write_text("\n".join(lignes), encoding="utf-8")

# --- B. Référence de l'API ------------------------------------------------------------------------
openapi = app.openapi()
(ANNEXES / "openapi.json").write_text(json.dumps(openapi, ensure_ascii=False, indent=2), encoding="utf-8")
par_tag: dict[str, list[str]] = {}
nb = 0
for chemin, operations in openapi["paths"].items():
    for methode, op in operations.items():
        noms_param = {p["name"] for p in op.get("parameters", [])}
        appareil = "X-Terminal-Key" in noms_param
        jeton = bool(op.get("security"))
        auth = "clé appareil + jeton" if appareil and jeton else "clé appareil" if appareil else "jeton" if jeton else "public"
        description = (op.get("description") or op.get("summary") or "").split("\n")[0].strip()
        if not description:
            description = op.get("summary", "")
        tag = (op.get("tags") or ["Autres"])[0]
        par_tag.setdefault(tag, []).append(f"| `{methode.upper()}` | `{chemin}` | {auth} | {description} |")
        nb += 1
lignes = ["# Annexe B — Référence de l'API centrale", "",
          f"{nb} points d'accès, générés à partir du schéma OpenAPI de l'API (fichier `openapi.json` joint, "
          "importable dans Postman, Insomnia ou Swagger Editor). La documentation interactive est servie par "
          "l'API elle-même sur `/docs` (essais directs) et `/redoc`.", "",
          "Authentification : **jeton** = `Authorization: Bearer <jeton de session>` ; **clé appareil** = "
          "`X-Terminal-Key: <clé du terminal ou du téléphone>` ; **public** = sans authentification.", ""]
for tag in sorted(par_tag):
    lignes += [f"### {tag}", "", "| Méthode | Chemin | Authentification | Description |", "|---|---|---|---|",
               *par_tag[tag], ""]
(ANNEXES / "B_reference_api.md").write_text("\n".join(lignes), encoding="utf-8")

# --- C. Résultats des tests ------------------------------------------------------------------------
lignes = ["# Annexe C — Résultats détaillés des tests automatisés", ""]
for titre, fichier in (("SQLite (base de développement)", "resultats_tests_sqlite.xml"),
                       ("PostgreSQL 16 (base cible)", "resultats_tests_postgresql.xml")):
    chemin = DOSSIER / "outils" / fichier
    if not chemin.exists():
        continue
    racine = ET.parse(chemin).getroot()
    cas = list(racine.iter("testcase"))
    ko = [c for c in cas if c.find("failure") is not None or c.find("error") is not None]
    duree = sum(float(c.get("time")) for c in cas)
    lignes += [f"### {titre}", "", f"**{len(cas) - len(ko)} tests réussis sur {len(cas)}** — durée {duree:.0f} s.", "",
               "| Fichier | Test | Durée (s) | Résultat |", "|---|---|---|---|"]
    for c in cas:
        lignes.append(f"| {c.get('classname').split('.')[-1]} | `{c.get('name')}` | {float(c.get('time')):.2f} | "
                      f"{'KO' if c in ko else 'OK'} |")
    lignes.append("")
(ANNEXES / "C_resultats_des_tests.md").write_text("\n".join(lignes), encoding="utf-8")

shutil.copy(RACINE / "database" / "schema.sql", ANNEXES / "schema.sql")
print(f"Annexes générées dans {ANNEXES} : {len(Base.metadata.tables)} tables, {nb} points d'accès")
