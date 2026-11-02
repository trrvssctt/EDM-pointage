/** Échanges avec le serveur central.
 *  Chaque requête porte la clé de l'appareil enregistré (X-Terminal-Key) et, une fois connecté,
 *  le jeton de l'utilisateur (Authorization: Bearer). La clé et le jeton sont rangés dans le Keychain iOS. */
import * as SecureStore from "expo-secure-store";

export interface Appareil { url_serveur: string; code_terminal: string; cle_api: string }

const CLE_APPAREIL = "appareil";
const CLE_JETON = "jeton";
let appareil: Appareil | null = null;
let jeton: string | null = null;
let surExpiration: () => void = () => {};

export class ErreurApi extends Error {
  constructor(message: string, public statut: number) { super(message); }
}
/** Erreur réseau : la requête pourra être rejouée depuis la file d'envoi. */
export const horsLigne = (e: unknown) => e instanceof ErreurApi && e.statut === 0;

export const stockage = {
  async charger() {
    const brut = await SecureStore.getItemAsync(CLE_APPAREIL);
    appareil = brut ? JSON.parse(brut) : null;
    jeton = await SecureStore.getItemAsync(CLE_JETON);
    return { appareil, jeton };
  },
  async enregistrerAppareil(a: Appareil) {
    appareil = { ...a, url_serveur: a.url_serveur.replace(/\/+$/, "") };
    await SecureStore.setItemAsync(CLE_APPAREIL, JSON.stringify(appareil));
  },
  async oublierAppareil() {
    appareil = null;
    jeton = null;
    await SecureStore.deleteItemAsync(CLE_APPAREIL);
    await SecureStore.deleteItemAsync(CLE_JETON);
  },
  async enregistrerJeton(j: string | null) {
    jeton = j;
    if (j) await SecureStore.setItemAsync(CLE_JETON, j);
    else await SecureStore.deleteItemAsync(CLE_JETON);
  },
  appareil: () => appareil,
};

export const quandSessionExpire = (f: () => void) => { surExpiration = f; };

function message(corps: unknown, statut: number): string {
  const d = (corps as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && "message" in d) return String((d as { message: string }).message);
  if (Array.isArray(d)) return d.map((e: { msg: string }) => e.msg).join("\n");
  return `Erreur ${statut}`;
}

export async function requete<T>(methode: string, chemin: string, corps?: unknown,
  options: { delai?: number; sansJeton?: boolean; appareilEssai?: Appareil } = {}): Promise<T> {
  const a = options.appareilEssai ?? appareil;
  if (!a) throw new ErreurApi("Appareil non enregistré", 401);
  const controle = new AbortController();
  const minuteur = setTimeout(() => controle.abort(), options.delai ?? 15000);
  let r: Response;
  try {
    r = await fetch(a.url_serveur + chemin, {
      method: methode,
      signal: controle.signal,
      headers: {
        "X-Terminal-Key": a.cle_api,
        "X-Terminal-Version": "mobile-1.0.0",
        ...(corps !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(jeton && !options.sansJeton ? { Authorization: `Bearer ${jeton}` } : {}),
      },
      body: corps !== undefined ? JSON.stringify(corps) : undefined,
    });
  } catch {
    throw new ErreurApi("Serveur central injoignable", 0);
  } finally {
    clearTimeout(minuteur);
  }
  const contenu = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (r.status === 401 && jeton && !chemin.startsWith("/api/mobile/connexion")) {
    await stockage.enregistrerJeton(null);
    surExpiration();
  }
  if (!r.ok) throw new ErreurApi(message(contenu, r.status), r.status);
  return contenu as T;
}

export const api = {
  get: <T>(chemin: string, delai?: number) => requete<T>("GET", chemin, undefined, { delai }),
  post: <T>(chemin: string, corps?: unknown, delai?: number) => requete<T>("POST", chemin, corps ?? {}, { delai }),
};

/** Le serveur répond-il ? (bandeau « En ligne » de l'accueil) */
export async function serveurJoignable(): Promise<boolean> {
  try {
    await requete("GET", "/api/terminal/configuration", undefined, { delai: 4000, sansJeton: true });
    return true;
  } catch {
    return false;
  }
}
