/** État global : appareil enregistré, utilisateur connecté, réseau et file d'envoi. */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { File, Paths } from "expo-file-system";
import { api, quandSessionExpire, requete, stockage, type Appareil } from "./api";
import { fileEnvoi } from "./file";

export interface Utilisateur {
  identifiant: string; nom_complet: string; fonction: string; role: "ADMIN" | "DRH" | "RESPONSABLE"; perimetre: string;
}
export interface Accueil {
  appareil: { code: string; site: string; site_id: number; libelle: string };
  utilisateur: { utilisateur: Utilisateur; droits: Record<string, string> };
  organisation: { nom: string; sigle: string; couleur_primaire: string; couleur_menu: string; prefixe_matricule: string };
  activite: { uuid: string; nature: "ENROLEMENT" | "SECOURS"; titre: string; date: string; statut: string; type?: string; motif?: string }[];
}
interface ReponseConnexion { jeton?: string; deux_etapes_requise?: boolean; jeton_temporaire?: string }

interface Contexte {
  pret: boolean;
  appareil: Appareil | null;
  accueil: Accueil | null;
  enLigne: boolean;
  enAttente: number;
  appairer: (a: Appareil) => Promise<string>;
  connecter: (identifiant: string, motDePasse: string) => Promise<ReponseConnexion>;
  validerCode: (temporaire: string, code: string) => Promise<void>;
  deconnecter: () => Promise<void>;
  oublierAppareil: () => Promise<void>;
  rafraichir: () => Promise<void>;
  peut: (droit: string) => boolean;
}

const Ctx = createContext<Contexte>(null!);
export const useSession = () => useContext(Ctx);
// Dernier écran d'accueil connu : permet d'utiliser l'application sans réseau.
const cache = new File(Paths.document, "accueil.json");

export function FournisseurSession({ children }: { children: ReactNode }) {
  const [pret, setPret] = useState(false);
  const [appareil, setAppareil] = useState<Appareil | null>(null);
  const [accueil, setAccueil] = useState<Accueil | null>(null);
  const [enLigne, setEnLigne] = useState(false);
  const [enAttente, setEnAttente] = useState(0);
  const enLigneRef = useRef(false);

  const memoriser = (a: Accueil | null) => {
    setAccueil(a);
    if (a) { if (!cache.exists) cache.create(); cache.write(JSON.stringify(a)); } else if (cache.exists) cache.delete();
  };

  const rafraichir = useCallback(async () => {
    try {
      const a = await api.get<Accueil>("/api/mobile/accueil", 8000);
      memoriser(a);
      setEnLigne(true);
    } catch (e) {
      setEnLigne(!(e instanceof Error && e.message === "Serveur central injoignable"));
    }
  }, []);

  // Démarrage : relecture de l'appareil et du jeton depuis le Keychain
  useEffect(() => {
    (async () => {
      const { appareil: a, jeton } = await stockage.charger();
      setAppareil(a);
      if (a && jeton) {
        try { memoriser(JSON.parse(cache.textSync())); } catch { /* pas de cache */ }
        await rafraichir();
      }
      setEnAttente(fileEnvoi.enAttente());
      setPret(true);
    })();
    quandSessionExpire(() => memoriser(null));
    return fileEnvoi.ecouter(() => setEnAttente(fileEnvoi.enAttente()));
  }, [rafraichir]);

  // Surveillance du réseau : au retour de la connexion, la file d'envoi part automatiquement.
  useEffect(() => {
    if (!appareil || !accueil) return;
    const verifier = async () => {
      let ok = false;
      try {
        await requete("GET", "/api/terminal/configuration", undefined, { delai: 4000, sansJeton: true });
        ok = true;
      } catch { ok = false; }
      setEnLigne(ok);
      if (ok && !enLigneRef.current) rafraichir();
      enLigneRef.current = ok;
      if (ok && fileEnvoi.enAttente()) await fileEnvoi.vider();
    };
    verifier();
    const i = setInterval(verifier, 10000);
    return () => clearInterval(i);
  }, [appareil, accueil !== null, rafraichir]);  // eslint-disable-line react-hooks/exhaustive-deps

  const valeur: Contexte = {
    pret, appareil, accueil, enLigne, enAttente, rafraichir,
    peut: (droit) => (accueil?.utilisateur.droits[droit] ?? "non") !== "non",
    async appairer(a) {
      const config = await requete<{ site_nom: string }>("GET", "/api/terminal/configuration", undefined,
        { appareilEssai: a, sansJeton: true, delai: 8000 });
      await stockage.enregistrerAppareil(a);
      setAppareil(stockage.appareil());
      return config.site_nom;
    },
    async connecter(identifiant, motDePasse) {
      const r = await api.post<ReponseConnexion>("/api/mobile/connexion", { identifiant, mot_de_passe: motDePasse, rester_connecte: true });
      if (r.jeton) { await stockage.enregistrerJeton(r.jeton); await rafraichir(); }
      return r;
    },
    async validerCode(temporaire, code) {
      const r = await api.post<ReponseConnexion>("/api/auth/deux-etapes", { jeton_temporaire: temporaire, code });
      await stockage.enregistrerJeton(r.jeton!);
      await rafraichir();
    },
    async deconnecter() {
      await stockage.enregistrerJeton(null);
      memoriser(null);
    },
    async oublierAppareil() {
      await stockage.oublierAppareil();
      fileEnvoi.effacerTout();
      memoriser(null);
      setAppareil(null);
    },
  };
  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}
