"""Vérifie que database/schema.sql et le modèle de l'API (SQLAlchemy) décrivent exactement la même base.

Usage : EDM_DATABASE_URL=postgresql+psycopg://…/base_creee_par_schema_sql python livrables/semaine-2-bdd-api/outils/comparer_schema.py
"""
import os
import sys

from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.getcwd())
from server.app.database import Base  # noqa: E402
from server.app import models  # noqa: E402,F401

reel = inspect(create_engine(os.environ["EDM_DATABASE_URL"]))
ecarts = 0
for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
    if table.name not in reel.get_table_names():
        print(f"✗ table absente du script : {table.name}")
        ecarts += 1
        continue
    colonnes = {c["name"]: c for c in reel.get_columns(table.name)}
    for c in table.columns:
        if c.name not in colonnes:
            print(f"✗ {table.name}.{c.name} : absente du script")
            ecarts += 1
        elif colonnes[c.name]["nullable"] != c.nullable and not c.primary_key:
            print(f"✗ {table.name}.{c.name} : NULL autorisé = {colonnes[c.name]['nullable']} (script) / {c.nullable} (API)")
            ecarts += 1
    for nom in colonnes:
        if nom not in table.columns:
            print(f"✗ {table.name}.{nom} : présente dans le script mais inconnue de l'API")
            ecarts += 1
    print(f"✓ {table.name:24s} {len(table.columns):2d} colonnes")
print(f"\n{len(Base.metadata.tables)} tables comparées — {ecarts} écart(s)")
sys.exit(1 if ecarts else 0)
