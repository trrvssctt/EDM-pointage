"""Démonstration : maintient « en ligne » les bornes configurées dans terminal/config/ sans caméra ni écran.

Chaque borne contacte le serveur toutes les 30 s, comme une vraie borne allumée (même appel, même clé). Rien n'est
pointé. Utile pendant une présentation pour que le tableau de bord et « Sites et terminaux » montrent un parc
en fonctionnement ; --sauf permet de garder une borne « hors ligne » pour illustrer la panne.

Sur le VPS (s'arrête seul après --duree heures, ou avec Ctrl+C) :
    cd /opt/edm-pointage && .venv/bin/python -m terminal.presence_bornes --serveur http://127.0.0.1:8200 --sauf TRM-SEL-01
"""
import argparse
import json
import time
from pathlib import Path

import requests

DOSSIER = Path(__file__).resolve().parent / "config"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serveur", help="adresse du serveur (par défaut, celle de chaque fichier de configuration)")
    parser.add_argument("--sauf", nargs="*", default=[], help="codes des bornes à laisser hors ligne")
    parser.add_argument("--duree", type=float, default=4, help="durée en heures (4 par défaut)")
    parser.add_argument("--intervalle", type=int, default=30, help="secondes entre deux contacts (30 par défaut)")
    args = parser.parse_args()

    bornes = []
    for f in sorted(DOSSIER.glob("*.json")):
        if f.name.endswith(".mobile.json"):
            continue
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("code_terminal") not in args.sauf:
            bornes.append(c)
    if not bornes:
        raise SystemExit(f"Aucune configuration de borne dans {DOSSIER}")
    print(f"{len(bornes)} borne(s) maintenue(s) en ligne pendant {args.duree} h : "
          + ", ".join(c["code_terminal"] for c in bornes), flush=True)
    fin = time.monotonic() + args.duree * 3600
    while time.monotonic() < fin:
        for c in bornes:
            url = (args.serveur or c["url_serveur"]).rstrip("/") + "/api/terminal/configuration"
            try:
                r = requests.get(url, headers={"X-Terminal-Key": c["cle_api"], "X-Terminal-Version": "1.0.0",
                                              "X-Terminal-En-Attente": "0"}, timeout=10)
                if r.status_code != 200:
                    print(f"{c['code_terminal']} : refusé ({r.status_code} {r.text[:80]})", flush=True)
            except requests.RequestException as e:
                print(f"{c['code_terminal']} : serveur injoignable ({type(e).__name__})", flush=True)
        time.sleep(args.intervalle)


if __name__ == "__main__":
    main()
