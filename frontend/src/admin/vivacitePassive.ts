/** Vivacité passive dans le navigateur, sans consigne : MediaPipe Face Landmarker suit 478 points du visage
 *  à chaque image de la webcam (~30 images/s) et mesure l'ouverture des yeux.
 *
 *  - Clignement naturel : fermeture des yeux nettement au-dessus du niveau habituel de la personne pendant 40 à
 *    600 ms, puis retour. On cligne toutes les 3 à 5 s sans y penser ; une photo ou un écran figé ne cligne pas.
 *    Le niveau « yeux ouverts » s'adapte à chacun (yeux plus fermés, regard vers le bas : ~0,3 au lieu de ~0,05).
 *    Seuls les clignements vus avec un seul visage dans le champ comptent.
 *  - Attention : yeux ouverts et tête tournée vers l'écran (comme Face ID, qui ne se déverrouille pas si son
 *    propriétaire dort ou regarde ailleurs). Sert aussi à repérer un regard détourné.
 *
 *  Limite : une vidéo de la personne qui cligne, rejouée sur un téléphone, cligne aussi. Seul un capteur de
 *  profondeur (caméra infrarouge type Face ID ou Windows Hello) écarte ce cas.
 *
 *  Le moteur (public/mediapipe/wasm) et le modèle (public/mediapipe/face_landmarker.task) sont préparés par
 *  scripts/preparer-mediapipe.mjs avant chaque compilation. */
import type { FaceLandmarker, FaceLandmarkerResult } from "@mediapipe/tasks-vision";

export interface EtatPassif {
  visages: number;        // visages vus sur la dernière image
  clignements: number;    // clignements vus depuis le démarrage, une seule personne dans le champ
  fermetureYeux: number;  // 0 = grands ouverts, 1 = fermés (moyenne des deux yeux)
  yeuxOuverts: boolean;
  attentif: boolean;      // yeux ouverts et tête tournée vers l'écran
  lacet: number;          // rotation gauche-droite de la tête (degrés, 0 = de face)
  tangage: number;        // rotation haut-bas (degrés)
}

// Fermeture des yeux (moyenne de eyeBlinkLeft et eyeBlinkRight, 0 à 1), relative au niveau habituel de la personne.
const HAUSSE_FERMES = 0.25, FERMES_MIN = 0.45;   // fermés : niveau habituel + 0,25, et au moins 0,45
const MARGE_OUVERTS = 0.12;                      // rouverts : revenus à moins de 0,12 du niveau habituel
const FERMETURE_MIN_MS = 40, FERMETURE_MAX_MS = 600;
const LACET_ATTENTIF = 25, TANGAGE_ATTENTIF = 20; // degrés

/** Détection d'un clignement à partir de la fermeture des yeux, image par image (sans caméra : testable seul). */
export class DetecteurClignement {
  private niveau: number | null = null;  // niveau habituel « yeux ouverts », moyenne glissante
  private ouvertesDepuis = 0;            // images consécutives yeux ouverts (un clignement part d'yeux ouverts)
  private fermeture: number | null = null;

  reinitialiser() { this.niveau = null; this.ouvertesDepuis = 0; this.fermeture = null; }

  /** Renvoie [clignement terminé sur cette image, yeux ouverts]. */
  image(fermetureYeux: number, maintenant: number): [boolean, boolean] {
    if (this.niveau === null) this.niveau = Math.min(fermetureYeux, 0.5);
    const fermes = fermetureYeux > Math.max(FERMES_MIN, this.niveau + HAUSSE_FERMES);
    const ouverts = fermetureYeux < this.niveau + MARGE_OUVERTS;
    let clignement = false;
    if (ouverts) {
      if (this.fermeture !== null) {
        const duree = maintenant - this.fermeture;
        clignement = this.ouvertesDepuis >= 3 && duree >= FERMETURE_MIN_MS && duree <= FERMETURE_MAX_MS;
        this.fermeture = null;
        this.ouvertesDepuis = 0;
      }
      this.ouvertesDepuis++;
    } else if (fermes && this.fermeture === null && this.ouvertesDepuis >= 3) {
      this.fermeture = maintenant;
    } else if (fermes && this.fermeture !== null && maintenant - this.fermeture > FERMETURE_MAX_MS) {
      this.ouvertesDepuis = 0;  // yeux fermés trop longtemps : pas un clignement
    }
    // Le niveau habituel ne suit que les yeux ouverts (ou presque), pas les clignements.
    if (!fermes && this.fermeture === null) this.niveau += 0.05 * (Math.min(fermetureYeux, 0.5) - this.niveau);
    return [clignement, ouverts];
  }
}

export class VivacitePassive {
  private dernierTemps = -1;
  private readonly clignement = new DetecteurClignement();
  readonly etat: EtatPassif = { visages: 0, clignements: 0, fermetureYeux: 0, yeuxOuverts: false, attentif: false, lacet: 0, tangage: 0 };

  private constructor(private readonly modele: FaceLandmarker) {}

  /** Charge le moteur WebAssembly et le modèle (GPU si possible, sinon processeur). */
  static async creer(): Promise<VivacitePassive> {
    const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
    const fichiers = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
    const options = (delegate: "GPU" | "CPU") => ({
      baseOptions: { modelAssetPath: "/mediapipe/face_landmarker.task", delegate },
      runningMode: "VIDEO" as const, numFaces: 3, outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
    });
    const modele = await FaceLandmarker.createFromOptions(fichiers, options("GPU"))
      .catch(() => FaceLandmarker.createFromOptions(fichiers, options("CPU")));
    return new VivacitePassive(modele);
  }

  /** À appeler à chaque image de la vidéo. */
  analyser(video: HTMLVideoElement, maintenant: number): EtatPassif {
    if (!video.videoWidth || maintenant <= this.dernierTemps) return this.etat;
    this.dernierTemps = maintenant;
    this.mettreAJour(this.modele.detectForVideo(video, maintenant), maintenant);
    return this.etat;
  }

  fermer() { this.modele.close(); }

  private mettreAJour(r: FaceLandmarkerResult, maintenant: number) {
    const e = this.etat;
    e.visages = r.faceLandmarks.length;
    if (e.visages !== 1) {  // personne, ou plusieurs : impossible d'attribuer un clignement
      this.clignement.reinitialiser();
      e.yeuxOuverts = e.attentif = false;
      return;
    }
    const scores = Object.fromEntries((r.faceBlendshapes[0]?.categories ?? []).map((c) => [c.categoryName, c.score]));
    const gauche = scores.eyeBlinkLeft ?? 0, droite = scores.eyeBlinkRight ?? 0;
    e.fermetureYeux = (gauche + droite) / 2;
    const [clignement, ouverts] = this.clignement.image(e.fermetureYeux, maintenant);
    if (clignement) e.clignements++;

    // Orientation de la tête : matrice de transformation 4×4 (colonnes), rotation R[ligne][colonne] = d[colonne*4+ligne].
    const d = r.facialTransformationMatrixes[0]?.data;
    if (d) {
      e.lacet = Math.atan2(-d[2], Math.hypot(d[6], d[10])) * 180 / Math.PI;
      e.tangage = Math.atan2(d[6], d[10]) * 180 / Math.PI;
    }
    e.yeuxOuverts = ouverts;
    e.attentif = ouverts && Math.abs(e.lacet) < LACET_ATTENTIF && Math.abs(e.tangage) < TANGAGE_ATTENTIF;
  }
}
