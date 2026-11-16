/** Poste de pointage simulé : la webcam de ce poste filme, le serveur identifie en temps réel chaque personne
 *  présente dans le champ. Démonstration et contrôle de la galerie : aucun pointage n'est enregistré.
 *  Être reconnu ne suffit pas : une photo ou un écran est reconnu aussi. La vivacité est prouvée sans consigne par
 *  un clignement naturel, vu dans le navigateur (vivacitePassive.ts) ; à défaut au bout de 5 s, la personne tourne
 *  légèrement la tête dans le sens demandé puis revient de face. Seules les personnes vivantes comptent comme passage. */
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Cctv, Eye, EyeOff, Info, Play, Square } from "lucide-react";
import { api } from "../api";
import { Avatar, Bouton, Carte, EnTetePage, Encart, MessageErreur, Pastille, type Ton } from "../composants/ui";
import { initiales } from "../../commun/format";
import { VivacitePassive, type EtatPassif } from "../vivacitePassive";

type Statut = "RECONNU" | "AMBIGU" | "INCONNU" | "TROP_LOIN";
type Vivacite = "VERIFIEE" | "OBSERVATION" | "DEFI" | "ECHEC" | "NON_PROUVEE" | "NON_VERIFIEE";
interface FicheAgent { matricule: string; nom_complet: string; service: string; site_rattachement: string }
interface VisageDetecte {
  boite: [number, number, number, number]; statut: Statut; agent: FicheAgent | null; score: number | null;
  confiance: number | null; autre: (FicheAgent & { score: number }) | null; vivacite: Vivacite | null;
}
interface Defi {
  matricule: string; direction: "droite" | "gauche"; consigne: string; restant: number;
  phase: "ROTATION" | "RETOUR"; sens_inverse: boolean;
}
interface Reponse { visages: VisageDetecte[]; defi: Defi | null; fraude_signalee: boolean; largeur: number; hauteur: number; agents_enroles: number; seuil: number; duree_ms: number }
interface Passage { cle: string; heure: Date; agent: FicheAgent; confiance: number }

const COULEURS: Record<Statut, string> = { RECONNU: "#15803D", AMBIGU: "#B5530A", INCONNU: "#B42318", TROP_LOIN: "#64748B" };
const LIBELLES: Record<Statut, [string, Ton]> = {
  RECONNU: ["Reconnu", "succes"], AMBIGU: ["Ambigu", "alerte"], INCONNU: ["Inconnu", "danger"], TROP_LOIN: ["Trop loin", "neutre"],
};
// Visage reconnu dont la vivacité n'est pas (encore) prouvée : orange ; photo, écran ou vidéo suspecté : rouge.
const COULEUR_A_PROUVER = "#B5530A", COULEUR_FRAUDE = "#B42318";
// Affichage d'un visage dont la vivacité est suivie (y compris tourné et momentanément moins bien reconnu).
const VIVACITE: Record<Vivacite, { couleur: string; ton: Ton; etiquette: (nom: string) => string; detail: string }> = {
  VERIFIEE: { couleur: COULEURS.RECONNU, ton: "succes", etiquette: (n) => `${n} · vivant`, detail: "vivacité prouvée" },
  OBSERVATION: { couleur: COULEUR_A_PROUVER, ton: "alerte", etiquette: (n) => `${n} · regardez la caméra`, detail: "vivacité en cours de vérification" },
  DEFI: { couleur: COULEUR_A_PROUVER, ton: "alerte", etiquette: (n) => `${n} · suivez la consigne`, detail: "défi de vivacité en cours" },
  ECHEC: { couleur: COULEUR_FRAUDE, ton: "danger", etiquette: () => "Photo ou écran suspecté", detail: "tentative de fraude signalée" },
  NON_PROUVEE: { couleur: COULEUR_A_PROUVER, ton: "alerte", etiquette: (n) => `${n} · vivacité non prouvée`, detail: "consigne non suivie à temps : nouvel essai" },
  NON_VERIFIEE: { couleur: COULEUR_A_PROUVER, ton: "alerte", etiquette: (n) => `${n} · seul(e) devant la caméra`, detail: "vivacité non vérifiée (plusieurs personnes)" },
};
const ABSENCE_MS = 30_000;  // une personne revenue après 30 s d'absence compte comme un nouveau passage
const PAUSE_MS = 120;       // pause entre deux images envoyées au serveur

export function ReconnaissanceDirecte() {
  const video = useRef<HTMLVideoElement>(null);
  const capture = useRef<HTMLCanvasElement>(null);
  const calque = useRef<HTMLCanvasElement>(null);
  const [actif, setActif] = useState(false);
  const [erreur, setErreur] = useState("");
  const [reponse, setReponse] = useState<Reponse | null>(null);
  const [cadence, setCadence] = useState(0);
  const [passages, setPassages] = useState<Passage[]>([]);
  const vus = useRef(new Map<string, number>());
  // Vivacité passive : analyse de chaque image dans le navigateur (null si MediaPipe n'a pas pu être chargé)
  const passif = useRef<VivacitePassive | null>(null);
  const [etatPassif, setEtatPassif] = useState<EtatPassif | null>(null);
  const [passifIndisponible, setPassifIndisponible] = useState(false);

  useEffect(() => {
    if (!actif) return;
    let continuer = true, image = 0, dernierAffichage = 0;
    VivacitePassive.creer().then((p) => {
      if (!continuer) { p.fermer(); return; }
      passif.current = p;
      const suivante = (t: number) => {
        if (!continuer) return;
        const v = video.current;
        if (v) {
          try {
            const e = p.analyser(v, t);
            if (t - dernierAffichage > 250) { dernierAffichage = t; setEtatPassif({ ...e }); }
          } catch { /* image non prête : la suivante sera analysée */ }
        }
        image = requestAnimationFrame(suivante);
      };
      image = requestAnimationFrame(suivante);
    }).catch(() => { if (continuer) setPassifIndisponible(true); });
    return () => {
      continuer = false; cancelAnimationFrame(image);
      passif.current?.fermer(); passif.current = null; setEtatPassif(null); setPassifIndisponible(false);
    };
  }, [actif]);

  // Caméra : ouverte au démarrage, libérée à l'arrêt ou en quittant la page
  useEffect(() => {
    if (!actif) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setErreur("Caméra bloquée par le navigateur : ouvrez l’application par son adresse https://.");
      setActif(false);
      return;
    }
    let flux: MediaStream | null = null;
    navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
      .then((f) => { flux = f; if (video.current) video.current.srcObject = f; })
      .catch((e) => {
        setErreur(e.name === "NotAllowedError" ? "Accès à la caméra refusé : autorisez-la dans la barre d’adresse du navigateur."
          : e.name === "NotReadableError" ? "Caméra déjà utilisée par une autre application." : "Aucune caméra disponible.");
        setActif(false);
      });
    return () => { flux?.getTracks().forEach((t) => t.stop()); };
  }, [actif]);

  const dessiner = useCallback((r: Reponse | null) => {
    const v = video.current, c = calque.current;
    if (!v || !c) return;
    const l = c.clientWidth, h = c.clientHeight, ratio = window.devicePixelRatio || 1;
    c.width = l * ratio; c.height = h * ratio;
    const g = c.getContext("2d")!;
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, l, h);
    if (!r) return;
    // La vidéo remplit le cadre (object-cover) et s'affiche en miroir : même transformation pour les boîtes.
    const echelle = Math.max(l / r.largeur, h / r.hauteur);
    const dx = (l - r.largeur * echelle) / 2, dy = (h - r.hauteur * echelle) / 2;
    g.font = "600 14px 'IBM Plex Sans', system-ui, sans-serif";
    for (const f of r.visages) {
      const [x, y, w, hb] = f.boite;
      const gx = l - (dx + (x + w) * echelle), gy = dy + y * echelle, gw = w * echelle, gh = hb * echelle;
      const viv = f.vivacite ? VIVACITE[f.vivacite] : null;
      const couleur = viv ? viv.couleur : COULEURS[f.statut];
      g.lineWidth = 3; g.strokeStyle = couleur;
      g.strokeRect(gx, gy, gw, gh);
      const texte = viv ? viv.etiquette(f.agent?.nom_complet ?? "")
        : f.statut === "AMBIGU" ? `${f.agent?.nom_complet} ou ${f.autre?.nom_complet} ?`
        : f.statut === "INCONNU" ? "Visage inconnu" : "Approchez-vous";
      const largeurTexte = g.measureText(texte).width + 14;
      const ty = gy > 26 ? gy - 26 : gy + gh;
      g.fillStyle = couleur; g.fillRect(gx - 1.5, ty, largeurTexte, 24);
      g.fillStyle = "#fff"; g.fillText(texte, gx + 5.5, ty + 17);
    }
  }, []);

  // Boucle : une image à la fois vers le serveur, puis la suivante dès la réponse
  useEffect(() => {
    if (!actif) return;
    let continuer = true, premiere = true, compteur = 0, depuis = performance.now();
    const session = crypto.randomUUID();
    let enDefi: boolean = false;
    (async () => {
      while (continuer) {
        const v = video.current, c = capture.current;
        if (v && c && v.videoWidth) {
          // Pendant le défi : image plus petite et plus compressée, donc plus d'images par seconde (le mouvement
          // de la tête doit être vu sur deux images de suite). Hors défi : 960 px pour reconnaître de loin.
          const largeur = Math.min(enDefi ? 640 : 960, v.videoWidth);
          c.width = largeur; c.height = Math.round(v.videoHeight * largeur / v.videoWidth);
          c.getContext("2d")!.drawImage(v, 0, 0, c.width, c.height);
          try {
            const r: Reponse = await api.post<Reponse>("/api/reconnaissance/identifier", {
              image: c.toDataURL("image/jpeg", enDefi ? 0.7 : 0.8), debut: premiere, session,
              passif: passif.current ? { clignements: passif.current.etat.clignements, visages: passif.current.etat.visages } : null,
            });
            premiere = false;
            enDefi = r.defi !== null;
            if (!continuer) break;
            setErreur("");
            setReponse(r);
            dessiner(r);
            enregistrerPassages(r);
            compteur++;
            const ecoule = performance.now() - depuis;
            if (ecoule > 2000) { setCadence(Math.round((compteur * 10000) / ecoule) / 10); compteur = 0; depuis = performance.now(); }
          } catch (e) {
            setErreur(e instanceof Error ? e.message : String(e));
            await new Promise((ok) => setTimeout(ok, 1500));
          }
        }
        await new Promise((ok) => setTimeout(ok, PAUSE_MS));
      }
    })();
    return () => { continuer = false; dessiner(null); };
  }, [actif, dessiner]);  // eslint-disable-line react-hooks/exhaustive-deps

  const enregistrerPassages = (r: Reponse) => {
    const maintenant = Date.now(), nouveaux: Passage[] = [];
    for (const f of r.visages) {
      if (f.statut !== "RECONNU" || f.vivacite !== "VERIFIEE" || !f.agent) continue;
      const dernier = vus.current.get(f.agent.matricule);
      if (!dernier || maintenant - dernier > ABSENCE_MS) {
        nouveaux.push({ cle: `${f.agent.matricule}-${maintenant}`, heure: new Date(), agent: f.agent, confiance: f.confiance ?? 0 });
      }
      vus.current.set(f.agent.matricule, maintenant);
    }
    if (nouveaux.length) setPassages((p) => [...nouveaux, ...p].slice(0, 30));
  };

  const arreter = () => { setActif(false); setReponse(null); };
  const visages = actif ? reponse?.visages ?? [] : [];
  const compte = (s: Statut) => visages.filter((v) => v.statut === s).length;
  const defi = actif ? reponse?.defi ?? null : null;
  const fraude = visages.some((v) => v.vivacite === "ECHEC");
  const nonProuvee = !fraude && visages.some((v) => v.vivacite === "NON_PROUVEE");
  const consigne = defi ? defi.sens_inverse ? `Dans l’autre sens : ${defi.consigne.toLowerCase()}` : defi.consigne : "";

  return (
    <>
      <EnTetePage titre="Poste de pointage simulé" sousTitre="Identification en temps réel des personnes filmées par la webcam de ce poste"
        actions={actif
          ? <Bouton grand icone={Square} onClick={arreter}>Arrêter</Bouton>
          : <Bouton grand variante="primaire" icone={Play} onClick={() => { setErreur(""); setActif(true); }}>Démarrer la caméra</Bouton>} />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Carte titre="Champ de la caméra" sousTitre={actif && reponse
          ? `${reponse.agents_enroles} agents enrôlés · ${cadence || "…"} images/s vers le serveur · analyse ${reponse.duree_ms} ms par image`
          : "Plusieurs personnes peuvent être identifiées en même temps"}>
          <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-gradient-to-br from-[#233868] to-[#0F1A3A]">
            {actif
              ? <video ref={video} autoPlay playsInline muted className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
              : <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-menu-texte">
                  <Cctv size={44} strokeWidth={1.5} /><span className="text-[15px]">Caméra arrêtée</span>
                </div>}
            <canvas ref={calque} className="pointer-events-none absolute inset-0 h-full w-full" />
            {(defi || fraude || nonProuvee) && (
              <div className={`absolute inset-x-0 bottom-0 flex items-center justify-center gap-3 px-4 py-3 text-[17px] font-semibold text-white ${fraude ? "bg-[#B42318]/90" : "bg-[#B5530A]/90"}`}>
                {defi?.phase === "ROTATION" && defi.direction === "gauche" && <ArrowLeft size={26} strokeWidth={2.5} />}
                <span>{defi ? `${consigne} · ${Math.ceil(defi.restant)} s`
                  : fraude ? "Photo ou écran suspecté : tentative de fraude signalée dans l’historique des pointages"
                  : "Vivacité non prouvée : tournez franchement la tête dans le sens de la flèche, puis revenez face à la caméra"}</span>
                {defi?.phase === "ROTATION" && defi.direction === "droite" && <ArrowRight size={26} strokeWidth={2.5} />}
              </div>
            )}
            <canvas ref={capture} className="hidden" />
          </div>
          {erreur && <div className="mt-4"><MessageErreur erreur={erreur} /></div>}
          <div className="mt-4 flex flex-wrap gap-2">
            {(Object.keys(LIBELLES) as Statut[]).map((s) => (
              <Pastille key={s} ton={LIBELLES[s][1]}>{LIBELLES[s][0]} : {compte(s)}</Pastille>
            ))}
            <Pastille ton="info">Vivacité prouvée : {visages.filter((v) => v.vivacite === "VERIFIEE").length}</Pastille>
          </div>
          {actif && (
            <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-encre-douce">
              {passifIndisponible ? "Vivacité passive indisponible sur ce navigateur : défi de rotation de la tête uniquement."
                : !etatPassif ? "Chargement de l’analyse des yeux (une seule fois, environ 18 Mo)…"
                : <>
                    <span className="inline-flex items-center gap-1.5">
                      {etatPassif.attentif ? <Eye size={15} className="text-succes" /> : <EyeOff size={15} className="text-alerte" />}
                      {etatPassif.visages === 0 ? "Aucun visage" : etatPassif.visages > 1 ? `${etatPassif.visages} visages`
                        : etatPassif.attentif ? "Yeux ouverts, regard vers l’écran" : etatPassif.yeuxOuverts ? "Regard détourné" : "Yeux fermés"}
                    </span>
                    <span>Clignements : {etatPassif.clignements}</span>
                    <span className="font-mono text-xs">tête {Math.round(etatPassif.lacet)}° / {Math.round(etatPassif.tangage)}°</span>
                  </>}
            </p>
          )}
        </Carte>

        <div className="flex flex-col gap-5">
          <Carte titre="Dans le champ">
            {visages.length === 0 && <p className="text-sm text-encre-douce">{actif ? "Personne pour le moment." : "Démarrez la caméra."}</p>}
            <ul className="flex flex-col">
              {visages.map((v, i) => (
                <li key={i} className="flex items-center gap-3 border-t border-bord py-2.5 first:border-t-0">
                  <Avatar initiales={v.agent ? initiales(v.agent.nom_complet) : "?"} ton={v.statut === "RECONNU" ? "info" : "neutre"} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{v.agent && (v.statut !== "INCONNU" || v.vivacite) ? v.agent.nom_complet : LIBELLES[v.statut][0]}</p>
                    <p className="truncate text-xs text-encre-douce">
                      {v.vivacite && v.agent ? `${v.agent.matricule} · ${VIVACITE[v.vivacite].detail}`
                        : v.statut === "AMBIGU" ? `ou ${v.autre?.nom_complet ?? v.autre?.matricule} : écart trop faible`
                        : v.statut === "INCONNU" ? `ressemblance ${v.score?.toFixed(2)} < seuil ${reponse?.seuil}` : "visage trop petit"}
                    </p>
                  </div>
                  <Pastille ton={v.vivacite ? VIVACITE[v.vivacite].ton : LIBELLES[v.statut][1]}>
                    {v.statut === "RECONNU" ? `${v.confiance} %` : v.vivacite ? "Défi" : LIBELLES[v.statut][0]}</Pastille>
                </li>
              ))}
            </ul>
          </Carte>
          <Carte titre="Passages" action={passages.length > 0 && <Bouton onClick={() => { setPassages([]); vus.current.clear(); }}>Effacer</Bouton>}>
            {passages.length === 0 && <p className="text-sm text-encre-douce">Chaque personne reconnue dont la vivacité est prouvée s’inscrit ici.</p>}
            <ul className="flex max-h-[320px] flex-col overflow-y-auto">
              {passages.map((p) => (
                <li key={p.cle} className="flex items-center justify-between gap-3 border-t border-bord py-2 text-sm first:border-t-0">
                  <span className="min-w-0"><b className="block truncate font-semibold">{p.agent.nom_complet}</b>
                    <span className="font-mono text-xs text-encre-douce">{p.agent.matricule}</span></span>
                  <span className="whitespace-nowrap font-mono text-[13px]">{p.heure.toLocaleTimeString("fr-FR")}</span>
                </li>
              ))}
            </ul>
          </Carte>
          <Encart icone={Info}>
            Démonstration : aucun pointage n’est enregistré. Une photo ou un écran est reconnu comme la personne
            qu’il montre. Un clignement naturel, vu dans le navigateur, prouve une personne réelle sans rien lui
            demander ; à défaut au bout de 5 s, il faut tourner légèrement la tête dans le sens de la flèche puis
            revenir face à la caméra. La vérification se fait quand une seule personne est dans le champ. Un visage resté parfaitement immobile (photo, écran)
            ou qui change pendant le défi est signalé comme tentative de fraude ou d’usurpation d’identité
            (appareil POSTE-WEB). Les images ne sont pas conservées.
          </Encart>
        </div>
      </div>
    </>
  );
}
