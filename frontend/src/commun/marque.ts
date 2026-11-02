/** Applique les couleurs de l'organisation (marque blanche) aux variables CSS de Tailwind. */
export function appliquerMarque(primaire?: string, menu?: string) {
  const racine = document.documentElement;
  const rvb = (hex: string) => {
    const n = parseInt(hex.replace("#", ""), 16);
    return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
  };
  if (primaire && /^#[0-9a-f]{6}$/i.test(primaire)) racine.style.setProperty("--primaire", rvb(primaire));
  if (menu && /^#[0-9a-f]{6}$/i.test(menu)) racine.style.setProperty("--menu", rvb(menu));
}
