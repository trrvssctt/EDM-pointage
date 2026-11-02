"""Outil de test : simule des pointages sur un terminal sans caméra.

Sert à démontrer la synchronisation après coupure réseau et le pointage multisite.
Les pointages passent par la même file locale et le même mécanisme de synchronisation
que le vrai terminal (seule l'étape de reconnaissance faciale est court-circuitée).

Exemples :
  python -m terminal.simulateur --config terminal/config/T-KATI-01.json EDM0002 EDM0005
  python -m terminal.simulateur --config terminal/config/T-KATI-01.json --etat
"""
import argparse

import requests

from terminal.noyau import Configuration, NoyauTerminal
from terminal.synchronisation import TerminalNonAutorise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("matricules", nargs="*", help="matricules à faire pointer")
    parser.add_argument("--etat", action="store_true", help="affiche seulement l'état de la file locale")
    args = parser.parse_args()

    noyau = NoyauTerminal(Configuration.charger(args.config))
    noyau.config.anti_rebond_s = 0
    synchro = noyau.synchro

    def synchroniser() -> None:
        try:
            synchro.cycle()
            synchro.en_ligne = True
        except (requests.RequestException, TerminalNonAutorise) as e:
            synchro.en_ligne = False
            print(f"  Serveur injoignable ({type(e).__name__}) : mode hors ligne")

    synchroniser()
    print(f"Terminal {noyau.config.code_terminal} - {'EN LIGNE' if synchro.en_ligne else 'HORS LIGNE'}"
          f" - site : {synchro.config_serveur.get('site_nom', 'inconnu (hors ligne)')}")
    if not args.etat:
        for matricule in args.matricules:
            r = noyau.enregistrer(matricule.upper(), score=1.0)
            print(f"  {matricule.upper()} : {r.message} {r.pointage['horodatage'] if r.pointage else ''}")
        synchroniser()
    print(f"Pointages en attente de synchronisation : {noyau.stockage.nb_en_attente()}")


if __name__ == "__main__":
    main()
