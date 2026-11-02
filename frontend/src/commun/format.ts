/** Formats français (dates, heures, nombres). */
const JOURS = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
  "novembre", "décembre"];

export const dateIso = (d: Date = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const decalerJours = (jours: number, depuis: Date = new Date()) => {
  const d = new Date(depuis);
  d.setDate(d.getDate() + jours);
  return d;
};

export const lireDate = (iso: string) => new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);

/** « Vendredi 30 octobre 2026 » */
export const dateLongue = (d: Date | string) => {
  const x = typeof d === "string" ? lireDate(d) : d;
  return `${JOURS[x.getDay()]} ${x.getDate()} ${MOIS[x.getMonth()]} ${x.getFullYear()}`;
};

/** « 30/10/2026 » */
export const dateCourte = (d: Date | string) => {
  const x = typeof d === "string" ? lireDate(d) : d;
  return `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}/${x.getFullYear()}`;
};

export const heure = (d: Date | string, secondes = false) => {
  const x = typeof d === "string" ? lireDate(d) : d;
  const hm = `${String(x.getHours()).padStart(2, "0")}:${String(x.getMinutes()).padStart(2, "0")}`;
  return secondes ? `${hm}:${String(x.getSeconds()).padStart(2, "0")}` : hm;
};

/** « Aujourd'hui 07:30 », « Hier 17:40 », « 29/10/2026 » */
export const dateRelative = (iso: string | null | undefined) => {
  if (!iso) return "Jamais";
  const d = lireDate(iso);
  const jour = dateIso(d);
  if (jour === dateIso()) return `Aujourd’hui ${heure(d)}`;
  if (jour === dateIso(decalerJours(-1))) return `Hier ${heure(d)}`;
  return dateCourte(d);
};

/** « Sam 24 » */
export const jourAbrege = (iso: string) => {
  const d = lireDate(iso);
  return `${JOURS[d.getDay()].slice(0, 3)} ${d.getDate()}`;
};

export const nombre = (n: number) => n.toLocaleString("fr-FR");
export const pourcent = (n: number) => `${n.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;

export const initiales = (nom: string) => {
  const m = nom.replace(/-/g, " ").split(" ").filter(Boolean);
  return m.length ? (m[0][0] + (m.length > 1 ? m[m.length - 1][0] : "")).toUpperCase() : "?";
};
