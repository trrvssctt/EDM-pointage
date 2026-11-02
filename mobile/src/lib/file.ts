/** File d'envoi hors ligne (écran « File d'envoi »).
 *  Chaque action reçoit un identifiant unique (uuid) au moment où elle a lieu et est écrite dans le
 *  dossier privé de l'application, protégé par le chiffrement des données d'iOS. Un élément n'est
 *  marqué « Envoyé » qu'après la réponse du serveur ; un renvoi ne crée jamais de doublon côté serveur.
 *  Les photos sont effacées du téléphone dès l'accusé de réception. */
import { Directory, File, Paths } from "expo-file-system";
import { api, ErreurApi, horsLigne } from "./api";

export type Nature = "ENROLEMENT" | "SECOURS";
export type Statut = "EN_ATTENTE" | "ENVOYE" | "ERREUR";

export interface Element {
  uuid: string;
  nature: Nature;
  cree_le: string;
  statut: Statut;
  titre: string;
  detail: string;
  corps?: Record<string, unknown>;  // requête à envoyer (supprimée après envoi : plus de photo sur le téléphone)
  reponse?: Record<string, any>;
  erreur?: string;
}

const dossier = new Directory(Paths.document, "file-envoi");
const ecouteurs = new Set<() => void>();
let envoiEnCours: Promise<void> | null = null;

function preparer() {
  if (!dossier.exists) dossier.create({ idempotent: true, intermediates: true });
}

function ecrire(e: Element) {
  preparer();
  const f = new File(dossier, `${e.uuid}.json`);
  if (!f.exists) f.create();
  f.write(JSON.stringify(e));
  ecouteurs.forEach((x) => x());
}

export const fileEnvoi = {
  ecouter(f: () => void) {
    ecouteurs.add(f);
    return () => { ecouteurs.delete(f); };
  },

  lister(): Element[] {
    preparer();
    const elements: Element[] = [];
    for (const f of dossier.list()) {
      if (f instanceof File && f.name.endsWith(".json")) {
        try { elements.push(JSON.parse(f.textSync())); } catch { /* fichier incomplet : ignoré */ }
      }
    }
    return elements.sort((a, b) => b.cree_le.localeCompare(a.cree_le));
  },

  enAttente(): number {
    return this.lister().filter((e) => e.statut === "EN_ATTENTE").length;
  },

  ajouter(e: Omit<Element, "statut" | "cree_le">): Element {
    const element: Element = { ...e, statut: "EN_ATTENTE", cree_le: new Date().toISOString() };
    ecrire(element);
    return element;
  },

  /** Envoie un élément ; renvoie l'élément mis à jour (réseau coupé : il reste en attente). */
  async envoyer(e: Element): Promise<Element> {
    if (e.statut !== "EN_ATTENTE" || !e.corps) return e;
    const chemin = e.nature === "ENROLEMENT" ? "/api/mobile/enrolements" : "/api/mobile/secours";
    try {
      const reponse = await api.post<Record<string, any>>(chemin, e.corps, 60000);
      const maj: Element = { ...e, statut: "ENVOYE", reponse, corps: undefined };
      if (e.nature === "SECOURS" && reponse.agent) maj.titre = `Secours · ${reponse.agent.nom_complet}`;
      if (e.nature === "SECOURS" && reponse.resultat === "REFUSE") maj.detail = `${e.detail} · ${reponse.message}`;
      ecrire(maj);
      return maj;
    } catch (err) {
      if (horsLigne(err) || (err instanceof ErreurApi && err.statut === 401)) return e;  // réessayé plus tard
      const maj: Element = { ...e, statut: "ERREUR", erreur: err instanceof Error ? err.message : String(err), corps: undefined };
      ecrire(maj);
      return maj;
    }
  },

  /** Vide la file dans l'ordre chronologique (bouton « Envoyer maintenant » et retour du réseau). */
  vider(): Promise<void> {
    if (envoiEnCours) return envoiEnCours;
    envoiEnCours = (async () => {
      const attente = this.lister().filter((e) => e.statut === "EN_ATTENTE").reverse();
      for (const e of attente) {
        const r = await this.envoyer(e);
        if (r.statut === "EN_ATTENTE") break;  // réseau toujours absent : inutile d'insister
      }
      this.nettoyer();
    })().finally(() => { envoiEnCours = null; });
    return envoiEnCours;
  },

  /** Conserve l'historique des 30 derniers éléments envoyés. */
  nettoyer() {
    const envoyes = this.lister().filter((e) => e.statut !== "EN_ATTENTE");
    for (const e of envoyes.slice(30)) new File(dossier, `${e.uuid}.json`).delete();
  },

  /** Retire un élément jamais transmis (« Ce n'est pas moi » sans réseau) : rien n'atteindra le serveur. */
  supprimer(uuid: string) {
    const f = new File(dossier, `${uuid}.json`);
    if (f.exists) f.delete();
    ecouteurs.forEach((x) => x());
  },

  effacerTout() {
    if (dossier.exists) dossier.delete();
    ecouteurs.forEach((x) => x());
  },
};
