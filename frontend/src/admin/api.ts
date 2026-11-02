/** Client de l'API du serveur central : jeton de session, erreurs lisibles, téléchargements. */
const CLE = "pointage.jeton";

export const jeton = {
  lire: () => localStorage.getItem(CLE) ?? sessionStorage.getItem(CLE),
  ecrire: (valeur: string, durable: boolean) => {
    (durable ? localStorage : sessionStorage).setItem(CLE, valeur);
    (durable ? sessionStorage : localStorage).removeItem(CLE);
  },
  effacer: () => { localStorage.removeItem(CLE); sessionStorage.removeItem(CLE); },
};

export class ErreurApi extends Error {
  constructor(message: string, public statut: number, public details?: unknown) { super(message); }
}

let surExpiration: () => void = () => {};
export const quandSessionExpire = (f: () => void) => { surExpiration = f; };

function message(corps: unknown, statut: number): string {
  const d = (corps as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && "message" in d) {
    const x = d as { message: string; images_rejetees?: string[] };
    return x.message + (x.images_rejetees?.length ? `\n${x.images_rejetees.join("\n")}` : "");
  }
  if (Array.isArray(d)) return d.map((e: { loc?: string[]; msg: string }) => `${e.loc?.at(-1)} : ${e.msg}`).join("\n");
  if (statut === 0) return "Serveur central injoignable";
  return `Erreur ${statut}`;
}

async function requete(methode: string, chemin: string, corps?: unknown): Promise<Response> {
  const t = jeton.lire();
  let r: Response;
  try {
    r = await fetch(chemin, {
      method: methode,
      headers: { ...(corps !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: corps !== undefined ? JSON.stringify(corps) : undefined,
    });
  } catch {
    throw new ErreurApi("Serveur central injoignable. Vérifiez la connexion réseau.", 0);
  }
  if (r.status === 401 && t && !chemin.startsWith("/api/auth/")) {
    jeton.effacer();
    surExpiration();
  }
  if (!r.ok) {
    const contenu = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
    throw new ErreurApi(message(contenu, r.status), r.status, contenu);
  }
  return r;
}

export const api = {
  get: async <T>(chemin: string): Promise<T> => (await requete("GET", chemin)).json(),
  post: async <T>(chemin: string, corps?: unknown): Promise<T> => (await requete("POST", chemin, corps ?? {})).json(),
  put: async <T>(chemin: string, corps: unknown): Promise<T> => (await requete("PUT", chemin, corps)).json(),
  patch: async <T>(chemin: string, corps: unknown): Promise<T> => (await requete("PATCH", chemin, corps)).json(),
  delete: async <T>(chemin: string): Promise<T> => (await requete("DELETE", chemin)).json(),
  /** Télécharge un fichier (Excel, PDF) en conservant le nom proposé par le serveur. */
  telecharger: async (chemin: string): Promise<string> => {
    const r = await requete("GET", chemin);
    const nom = r.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? "export";
    const url = URL.createObjectURL(await r.blob());
    // Le lien doit être dans la page pour que Firefox et Safari déclenchent le téléchargement.
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = nom;
    lien.style.display = "none";
    document.body.appendChild(lien);
    lien.click();
    lien.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return nom;
  },
};

/** Construit une chaîne de requête en ignorant les valeurs vides. */
export const parametres = (p: Record<string, string | number | boolean | null | undefined>) => {
  const q = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) q.set(k, String(v)); });
  const s = q.toString();
  return s ? `?${s}` : "";
};
