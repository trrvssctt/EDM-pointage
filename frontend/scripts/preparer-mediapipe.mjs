// Prépare les fichiers de MediaPipe Face Landmarker (vivacité passive dans le navigateur) dans public/mediapipe/ :
// moteur WebAssembly copié depuis node_modules, modèle téléchargé une seule fois. Lancé avant « npm run dev » et
// « npm run build » (scripts predev / prebuild) : aucune étape à ajouter au déploiement.
import { copyFile, mkdir, rename, stat, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const ici = (chemin) => fileURLToPath(new URL(chemin, import.meta.url));
const SOURCE = ici("../node_modules/@mediapipe/tasks-vision/wasm/");
const CIBLE = ici("../public/mediapipe/");
const MODELE = "face_landmarker.task";
const URL_MODELE = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

const existe = async (chemin) => (await stat(chemin).catch(() => null))?.size > 0;

await mkdir(`${CIBLE}wasm`, { recursive: true });
for (const fichier of ["vision_wasm_internal.js", "vision_wasm_internal.wasm"]) {
  await copyFile(SOURCE + fichier, `${CIBLE}wasm/${fichier}`);
}
if (!(await existe(CIBLE + MODELE))) {
  console.log(`Téléchargement du modèle ${MODELE}`);
  const reponse = await fetch(URL_MODELE);
  if (!reponse.ok) throw new Error(`Modèle ${MODELE} : HTTP ${reponse.status}`);
  await writeFile(`${CIBLE}${MODELE}.part`, Buffer.from(await reponse.arrayBuffer()));
  await rename(`${CIBLE}${MODELE}.part`, CIBLE + MODELE);
}
