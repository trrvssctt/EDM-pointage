/** Poste de pointage simulé : la webcam de ce poste filme, le serveur identifie en temps réel chaque personne
 *  présente dans le champ. Démonstration et contrôle de la galerie : aucun pointage n'est enregistré. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Cctv, Info, Play, Square } from "lucide-react";
import { api } from "../api";
import { Avatar, Bouton, Carte, EnTetePage, Encart, MessageErreur, Pastille, type Ton } from "../composants/ui";
import { initiales } from "../../commun/format";

type Statut = "RECONNU" | "AMBIGU" | "INCONNU" | "TROP_LOIN";
interface FicheAgent { matricule: string; nom_complet: string; service: string; site_rattachement: string }
interface VisageDetecte {
  boite: [number, number, number, number]; statut: Statut; agent: FicheAgent | null; score: number | null;
  confiance: number | null; autre: (FicheAgent & { score: number }) | null;
}
interface Reponse { visages: VisageDetecte[]; largeur: number; hauteur: number; agents_enroles: number; seuil: number; duree_ms: number }
interface Passage { cle: string; heure: Date; agent: FicheAgent; confiance: number }

const COULEURS: Record<Statut, string> = { RECONNU: "#15803D", AMBIGU: "#B5530A", INCONNU: "#B42318", TROP_LOIN: "#64748B" };
const LIBELLES: Record<Statut, [string, Ton]> = {
  RECONNU: ["Reconnu", "succes"], AMBIGU: ["Ambigu", "alerte"], INCONNU: ["Inconnu", "danger"], TROP_LOIN: ["Trop loin", "neutre"],
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
      const couleur = COULEURS[f.statut];
      g.lineWidth = 3; g.strokeStyle = couleur;
      g.strokeRect(gx, gy, gw, gh);
      const texte = f.statut === "RECONNU" ? `${f.agent?.nom_complet} · ${f.confiance} %`
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
    (async () => {
      while (continuer) {
        const v = video.current, c = capture.current;
        if (v && c && v.videoWidth) {
          const largeur = Math.min(960, v.videoWidth);
          c.width = largeur; c.height = Math.round(v.videoHeight * largeur / v.videoWidth);
          c.getContext("2d")!.drawImage(v, 0, 0, c.width, c.height);
          try {
            const r = await api.post<Reponse>("/api/reconnaissance/identifier", { image: c.toDataURL("image/jpeg", 0.8), debut: premiere });
            premiere = false;
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
      if (f.statut !== "RECONNU" || !f.agent) continue;
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

  return (
    <>
      <EnTetePage titre="Poste de pointage simulé" sousTitre="Identification en temps réel des personnes filmées par la webcam de ce poste"
        actions={actif
          ? <Bouton grand icone={Square} onClick={arreter}>Arrêter</Bouton>
          : <Bouton grand variante="primaire" icone={Play} onClick={() => { setErreur(""); setActif(true); }}>Démarrer la caméra</Bouton>} />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Carte titre="Champ de la caméra" sousTitre={actif && reponse
          ? `${reponse.agents_enroles} agents enrôlés · ${cadence || "…"} images/s · analyse ${reponse.duree_ms} ms par image`
          : "Plusieurs personnes peuvent être identifiées en même temps"}>
          <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-gradient-to-br from-[#233868] to-[#0F1A3A]">
            {actif
              ? <video ref={video} autoPlay playsInline muted className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
              : <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-menu-texte">
                  <Cctv size={44} strokeWidth={1.5} /><span className="text-[15px]">Caméra arrêtée</span>
                </div>}
            <canvas ref={calque} className="pointer-events-none absolute inset-0 h-full w-full" />
            <canvas ref={capture} className="hidden" />
          </div>
          {erreur && <div className="mt-4"><MessageErreur erreur={erreur} /></div>}
          <div className="mt-4 flex flex-wrap gap-2">
            {(Object.keys(LIBELLES) as Statut[]).map((s) => (
              <Pastille key={s} ton={LIBELLES[s][1]}>{LIBELLES[s][0]} : {compte(s)}</Pastille>
            ))}
          </div>
        </Carte>

        <div className="flex flex-col gap-5">
          <Carte titre="Dans le champ">
            {visages.length === 0 && <p className="text-sm text-encre-douce">{actif ? "Personne pour le moment." : "Démarrez la caméra."}</p>}
            <ul className="flex flex-col">
              {visages.map((v, i) => (
                <li key={i} className="flex items-center gap-3 border-t border-bord py-2.5 first:border-t-0">
                  <Avatar initiales={v.agent ? initiales(v.agent.nom_complet) : "?"} ton={v.statut === "RECONNU" ? "info" : "neutre"} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{v.agent && v.statut !== "INCONNU" ? v.agent.nom_complet : LIBELLES[v.statut][0]}</p>
                    <p className="truncate text-xs text-encre-douce">
                      {v.statut === "RECONNU" && v.agent ? `${v.agent.matricule} · ${v.agent.service}`
                        : v.statut === "AMBIGU" ? `ou ${v.autre?.nom_complet ?? v.autre?.matricule} : écart trop faible`
                        : v.statut === "INCONNU" ? `ressemblance ${v.score?.toFixed(2)} < seuil ${reponse?.seuil}` : "visage trop petit"}
                    </p>
                  </div>
                  <Pastille ton={LIBELLES[v.statut][1]}>{v.statut === "RECONNU" ? `${v.confiance} %` : LIBELLES[v.statut][0]}</Pastille>
                </li>
              ))}
            </ul>
          </Carte>
          <Carte titre="Passages" action={passages.length > 0 && <Bouton onClick={() => { setPassages([]); vus.current.clear(); }}>Effacer</Bouton>}>
            {passages.length === 0 && <p className="text-sm text-encre-douce">Chaque personne reconnue s’inscrit ici à son arrivée dans le champ.</p>}
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
            Démonstration : aucun pointage n’est enregistré. La borne de pointage ajoute un défi de vivacité
            (une seule personne à la fois) pour écarter les photos et les écrans. Les images ne sont pas conservées.
          </Encart>
        </div>
      </div>
    </>
  );
}
