/** Enrôlement guidé en 5 poses (maquette « Enrôlement »).
 *  La caméra du poste RH est analysée en direct par le serveur (qualité, orientation) ;
 *  chaque pose est capturée automatiquement quand elle est correcte. Seuls des gabarits chiffrés sont conservés. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Camera, Check, Lock, RefreshCw, RotateCcw, Search, Smartphone } from "lucide-react";
import { api, parametres } from "../api";
import { useSites } from "../donnees";
import type { Agent, Analyse, DemandeEnrolement, Page } from "../types";
import { Avatar, Bouton, CaseACocher, Carte, Cellule, Champ, EnTetePage, Encart, Ligne, MessageErreur, Modale, Pastille,
  Radio, Tableau, cx, useNotifier, type Ton } from "../composants/ui";
import { initiales } from "../../commun/format";

type Pose = "face" | "gauche" | "droite" | "haut" | "bas";
const POSES: { pose: Pose; libelle: string; consigne: string }[] = [
  { pose: "face", libelle: "Face", consigne: "Regardez droit vers la caméra" },
  { pose: "gauche", libelle: "Gauche", consigne: "Tournez la tête vers la gauche (un quart de tour)" },
  { pose: "droite", libelle: "Droite", consigne: "Tournez la tête de l’autre côté (un quart de tour)" },
  { pose: "haut", libelle: "Haut", consigne: "Levez légèrement le menton" },
  { pose: "bas", libelle: "Bas", consigne: "Baissez légèrement la tête" },
];
// Seuils d'orientation relatifs à la pose de face (rapports nez / yeux / bouche, image non inversée).
// Lacet = position du nez entre les yeux (0,5 = de face). Un côté puis le côté opposé, sans imposer le sens
// (« gauche » est compris différemment selon les personnes) ; le profil complet est refusé (gabarit peu fiable).
const ROTATION_MIN = 0.1, ROTATION_MAX = 0.36, FACE_MAX = 0.12, INCLINAISON_MAX = 0.25, TANGAGE_MIN = 0.04;
const ECART_VIVACITE = 0.15, DELAI_MANUEL_MS = 8000;

export function Enrolement() {
  const [recherche, setRecherche] = useSearchParams();
  const id = recherche.get("agent");
  const onglet = recherche.get("onglet") === "validation" ? "validation" : "capture";
  const agent = useQuery({ queryKey: ["agent", id], enabled: !!id, queryFn: () => api.get<Agent>(`/api/agents/${id}`) });
  const demandes = useQuery({ queryKey: ["demandes"], refetchInterval: 20_000,
    queryFn: () => api.get<DemandeEnrolement[]>("/api/enrolements/demandes") });
  const enAttente = demandes.data?.filter((d) => d.statut === "GABARIT_CALCULE").length ?? 0;
  return (
    <>
      <EnTetePage titre="Enrôlement d’un agent" sousTitre="L’agent est enrôlé une seule fois et peut ensuite pointer sur tous les sites autorisés"
        actions={<AnnulerEnrolement />} />
      <div className="mb-6 flex gap-1 border-b border-bord" role="tablist">
        {([["capture", "Enrôler sur ce poste"], ["validation", `À valider${enAttente ? ` (${enAttente})` : ""}`]] as const).map(([cle, libelle]) => (
          <button key={cle} type="button" role="tab" aria-selected={onglet === cle}
            onClick={() => setRecherche(cle === "validation" ? { onglet: "validation" } : {})}
            className={cx("-mb-px border-b-2 px-4 py-2.5 text-[15px] font-semibold",
              onglet === cle ? "border-primaire text-primaire" : "border-transparent text-encre-douce hover:text-encre")}>
            {cle === "validation" && <Smartphone size={16} className="mr-1.5 inline" />}{libelle}
          </button>
        ))}
      </div>
      {onglet === "validation" ? <Validation demandes={demandes.data ?? []} chargement={demandes.isLoading} />
        : !id ? <ChoixAgent /> : agent.error ? <MessageErreur erreur={agent.error} /> : agent.data ? <Capture agent={agent.data} /> : null}
    </>
  );
}

const STATUTS: Record<DemandeEnrolement["statut"], [string, Ton]> = {
  RECUE: ["Reçue", "neutre"], GABARIT_CALCULE: ["À valider", "alerte"], VALIDEE: ["Validée", "succes"], REJETEE: ["Rejetée", "danger"],
};

/** Enrôlements proposés depuis l'application mobile, validés ou rejetés par la DRH. */
function Validation({ demandes, chargement }: { demandes: DemandeEnrolement[]; chargement: boolean }) {
  const [ouverte, setOuverte] = useState<string | null>(null);
  return (
    <Carte titre="Enrôlements reçus de l’application mobile"
      sousTitre="Vérifiez les 5 photos prises sur le terrain avant d’autoriser l’agent à pointer. Les photos sont effacées après la décision.">
      <Tableau largeurMin={820} entetes={["Agent", "Service · rattachement", "Envoyé par", "Reçu le", "Vivacité", "Statut", ""]}
        chargement={chargement} vide={!chargement && demandes.length === 0}>
        {demandes.map((d) => (
          <Ligne key={d.uuid} onClick={d.statut === "GABARIT_CALCULE" ? () => setOuverte(d.uuid) : undefined}>
            <Cellule><b className="font-semibold">{d.agent}</b> <span className="whitespace-nowrap font-mono text-xs text-encre-douce">{d.matricule}</span></Cellule>
            <Cellule>{d.service} · {d.site_rattachement}</Cellule>
            <Cellule>{d.auteur}<span className="block whitespace-nowrap font-mono text-xs text-encre-douce">{d.appareil}</span></Cellule>
            <Cellule className="whitespace-nowrap">{new Date(d.recu_le).toLocaleString("fr-FR")}</Cellule>
            <Cellule>{d.vivacite ? <Pastille ton="succes" icone={Check}>Validée</Pastille> : <Pastille ton="alerte">Non concluante</Pastille>}</Cellule>
            <Cellule><Pastille ton={STATUTS[d.statut][1]}>{STATUTS[d.statut][0]}</Pastille>
              {d.motif && <span className="mt-1 block text-xs text-encre-douce">{d.motif}</span>}</Cellule>
            <Cellule className="text-right">{d.statut === "GABARIT_CALCULE" &&
              <button type="button" className="font-semibold text-primaire underline">Examiner</button>}</Cellule>
          </Ligne>
        ))}
      </Tableau>
      {ouverte && <ExamenDemande uuid={ouverte} onFermer={() => setOuverte(null)} />}
    </Carte>
  );
}

function ExamenDemande({ uuid, onFermer }: { uuid: string; onFermer: () => void }) {
  const client = useQueryClient();
  const notifier = useNotifier();
  const [motif, setMotif] = useState("");
  const d = useQuery({ queryKey: ["demande", uuid], queryFn: () => api.get<DemandeEnrolement>(`/api/enrolements/demandes/${uuid}`) });
  const decider = useMutation({
    mutationFn: (action: "valider" | "rejeter") => api.post<DemandeEnrolement>(`/api/enrolements/demandes/${uuid}/${action}`,
      action === "rejeter" ? { motif } : {}),
    onSuccess: (r) => {
      client.invalidateQueries({ queryKey: ["demandes"] });
      client.invalidateQueries({ queryKey: ["agents"] });
      notifier(r.statut === "VALIDEE" ? `${r.agent} est enrôlé(e) : les terminaux le reconnaîtront à leur prochaine synchronisation`
        : `Demande rejetée : ${r.motif}`);
      onFermer();
    },
  });
  const x = d.data;
  return (
    <Modale large titre={x ? `${x.agent} · ${x.matricule}` : "Demande d’enrôlement"} onFermer={onFermer}
      sousTitre={x ? `Photographié le ${new Date(x.capture_le).toLocaleString("fr-FR")} par ${x.auteur} (${x.appareil})` : undefined}
      actions={x && <>
        <Bouton variante="danger" chargement={decider.isPending} disabled={!motif.trim()} onClick={() => decider.mutate("rejeter")}>Rejeter</Bouton>
        <Bouton variante="primaire" icone={Check} chargement={decider.isPending} onClick={() => decider.mutate("valider")}>Valider l’enrôlement</Bouton>
      </>}>
      {d.error && <MessageErreur erreur={d.error} />}
      {x && <>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {POSES.map((p) => (
            <figure key={p.pose} className="overflow-hidden rounded-[10px] border border-bord">
              {x.photos?.[p.pose] ? <img src={x.photos[p.pose]} alt={p.libelle} className="aspect-[3/4] w-full object-cover" />
                : <div className="flex aspect-[3/4] items-center justify-center bg-surface text-xs text-encre-douce">Absente</div>}
              <figcaption className="px-2 py-1 text-xs font-semibold">{p.libelle}</figcaption>
            </figure>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {x.vivacite ? <Pastille ton="succes" icone={Check}>Rotation de la tête constatée (vivacité)</Pastille>
            : <Pastille ton="alerte">Vivacité non concluante : vérifiez qu’il ne s’agit pas d’une photo</Pastille>}
          <Pastille ton="info">Consentement recueilli sur le terrain</Pastille>
        </div>
        {x.controles && <p className="mt-3 whitespace-pre-line text-[13px] text-alerte">{x.controles}</p>}
        <Champ className="mt-4" libelle="Motif en cas de rejet" placeholder="ex. photos floues, mauvais agent" value={motif}
          onChange={(e) => setMotif(e.target.value)} />
        {decider.error && <div className="mt-4"><MessageErreur erreur={decider.error} /></div>}
      </>}
    </Modale>
  );
}

function AnnulerEnrolement() {
  const naviguer = useNavigate();
  return <Bouton grand onClick={() => naviguer("/agents")}>Annuler</Bouton>;
}

function Etapes({ courante }: { courante: 1 | 2 | 3 }) {
  const etapes = ["Dossier de l’agent", "Capture du visage", "Validation"];
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
      {etapes.map((e, i) => {
        const n = i + 1;
        const faite = n < courante;
        return (
          <li key={e} className="flex items-center gap-3">
            {i > 0 && <span className="hidden h-px w-10 bg-bord-champ sm:block" />}
            <span className={cx("flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold",
              faite ? "border-primaire bg-primaire text-white" : n === courante ? "border-primaire text-primaire" : "border-bord-champ text-encre-douce")}>
              {faite ? <Check size={16} /> : n}
            </span>
            <span className={cx("text-[15px]", n <= courante ? "font-semibold" : "text-encre-douce")}>{e}</span>
          </li>
        );
      })}
    </ol>
  );
}

function ChoixAgent() {
  const naviguer = useNavigate();
  const [q, setQ] = useState("");
  const agents = useQuery({
    queryKey: ["agents-a-enroler", q],
    queryFn: () => api.get<Page<Agent>>(`/api/agents${parametres({ q, actif: true, enrole: q ? "" : false, taille: 12 })}`),
  });
  return (
    <>
      <Etapes courante={1} />
      <Carte titre="Choisir l’agent à enrôler" sousTitre="Agents actifs dont le visage n’est pas encore enrôlé (recherchez un nom pour refaire un enrôlement)">
        <Champ placeholder="Nom ou matricule" value={q} onChange={(e) => setQ(e.target.value)} type="search" />
        <ul className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {agents.data?.elements.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => naviguer(`/enrolement?agent=${a.id}`)}
                className="flex w-full items-center gap-3 rounded-[10px] border border-bord p-3 text-left hover:border-primaire hover:bg-surface">
                <Avatar initiales={initiales(a.nom_complet)} />
                <span className="min-w-0">
                  <b className="block truncate font-semibold">{a.nom_complet}</b>
                  <span className="block truncate font-mono text-[13px] text-encre-douce">{a.matricule} · {a.site_rattachement_nom}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {agents.data?.elements.length === 0 && <p className="mt-4 flex items-center gap-2 text-sm text-encre-douce"><Search size={16} /> Aucun agent à enrôler.</p>}
      </Carte>
    </>
  );
}

interface CapturePose { image: string; lacet: number; tangage: number }

/** Vrai si l'image analysée est exploitable et correspond à la pose demandée. */
function conformeA(a: Analyse, pose: Pose, captures: Partial<Record<Pose, CapturePose>>): boolean {
  if (a.nb_visages !== 1 || !a.taille_ok || a.lacet === null || a.tangage === null || a.nettete === "FLOUE"
    || a.luminosite !== "CORRECTE") return false;
  const ecart = a.lacet - 0.5;
  if (pose === "face") return Math.abs(ecart) < FACE_MAX;
  const ref = captures.face;
  if (!ref) return false;
  if (pose === "haut" || pose === "bas") return Math.abs(ecart) <= INCLINAISON_MAX && Math.abs(a.tangage - ref.tangage) >= TANGAGE_MIN;
  if (Math.abs(ecart) < ROTATION_MIN || Math.abs(ecart) > ROTATION_MAX) return false;
  const premier = captures.gauche?.lacet;
  return pose === "gauche" || premier === undefined || Math.sign(premier - 0.5) !== Math.sign(ecart);
}

function Capture({ agent }: { agent: Agent }) {
  const client = useQueryClient();
  const notifier = useNotifier();
  const naviguer = useNavigate();
  const sites = useSites();
  const video = useRef<HTMLVideoElement>(null);
  const toile = useRef<HTMLCanvasElement>(null);
  const [erreurCamera, setErreurCamera] = useState("");
  const [captures, setCaptures] = useState<Partial<Record<Pose, CapturePose>>>({});
  const [analyse, setAnalyse] = useState<Analyse | null>(null);
  const [consentement, setConsentement] = useState(false);
  const [tousSites, setTousSites] = useState(agent.tous_sites);
  const [termine, setTermine] = useState<{ vivacite: boolean; nombre: number } | null>(null);
  const [debutPose, setDebutPose] = useState(Date.now());
  const [maintenant, setMaintenant] = useState(Date.now());
  const enCours = POSES.find((p) => !captures[p.pose]);
  const completes = !enCours;

  // Caméra du poste d'enrôlement
  useEffect(() => {
    let flux: MediaStream | null = null;
    // Les navigateurs n'exposent la caméra qu'aux pages sécurisées (HTTPS ou localhost).
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setErreurCamera("Caméra bloquée par le navigateur : cette page n’est pas en HTTPS. Ouvrez l’application par son "
        + "adresse https:// (ou utilisez l’application mobile pour l’enrôlement).");
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      .then((f) => { flux = f; if (video.current) video.current.srcObject = f; })
      .catch((e) => setErreurCamera(e.name === "NotAllowedError" ? "Accès à la caméra refusé : autorisez-la dans la barre d’adresse du navigateur."
        : e.name === "NotReadableError" ? "Caméra déjà utilisée par une autre application (terminal de pointage, visioconférence…)."
        : "Aucune caméra disponible : vérifiez qu’elle est branchée."));
    return () => flux?.getTracks().forEach((t) => t.stop());
  }, []);

  const image = useCallback(() => {
    const v = video.current, c = toile.current;
    if (!v || !c || !v.videoWidth) return null;
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    return c.toDataURL("image/jpeg", 0.9);
  }, []);

  const conforme = (a: Analyse, pose: Pose) => conformeA(a, pose, captures);

  // Boucle d'analyse : une image toutes les 400 ms (état courant lu via des références)
  const capturesRef = useRef(captures);
  capturesRef.current = captures;
  useEffect(() => {
    if (termine || erreurCamera) return;
    let actif = true, occupe = false;
    const minuteur = setInterval(async () => {
      setMaintenant(Date.now());
      const pose = POSES.find((p) => !capturesRef.current[p.pose]);
      if (occupe || !pose) return;
      const img = image();
      if (!img) return;
      occupe = true;
      try {
        const a = await api.post<Analyse>("/api/agents/enrolement/analyse", { image: img });
        if (!actif) return;
        setAnalyse(a);
        if (conformeA(a, pose.pose, capturesRef.current)) {
          setCaptures((c) => ({ ...c, [pose.pose]: { image: img, lacet: a.lacet!, tangage: a.tangage! } }));
          setDebutPose(Date.now());
        }
      } catch { /* on passe à l'image suivante */ } finally { occupe = false; }
    }, 400);
    return () => { actif = false; clearInterval(minuteur); };
  }, [termine, erreurCamera, image]);

  const captureManuelle = () => {
    const img = image();
    if (img && enCours && analyse?.nb_visages === 1 && analyse.lacet !== null && analyse.tangage !== null) {
      setCaptures((c) => ({ ...c, [enCours.pose]: { image: img, lacet: analyse.lacet!, tangage: analyse.tangage! } }));
      setDebutPose(Date.now());
    }
  };
  const recommencer = () => { setCaptures({}); setDebutPose(Date.now()); };

  const vivacite: { ton: Ton; texte: string } = captures.gauche && captures.droite
    ? Math.abs(captures.gauche.lacet - captures.droite.lacet) >= ECART_VIVACITE
      ? { ton: "succes", texte: "Validé" } : { ton: "danger", texte: "Non concluant" }
    : { ton: "info", texte: "En cours" };

  const valider = useMutation({
    mutationFn: async () => {
      if (tousSites !== agent.tous_sites) await api.put(`/api/agents/${agent.id}`, { tous_sites: tousSites });
      return api.post<{ gabarits_enregistres: number; vivacite: boolean }>(`/api/agents/${agent.id}/enrolement`, {
        consentement, images: POSES.filter((p) => captures[p.pose]).map((p) => ({ pose: p.pose, image: captures[p.pose]!.image })),
      });
    },
    onSuccess: (r) => {
      client.invalidateQueries({ queryKey: ["agents"] });
      setTermine({ vivacite: r.vivacite, nombre: r.gabarits_enregistres });
      notifier(`${agent.nom_complet} est enrôlé(e) : ${r.gabarits_enregistres} gabarits chiffrés enregistrés`);
    },
  });

  const visible = analyse?.nb_visages === 1;
  const qualite: [string, Ton, string][] = [
    ["Luminosité", !visible ? "neutre" : analyse.luminosite === "CORRECTE" ? "succes" : "alerte",
      !visible ? "—" : { CORRECTE: "Correcte", SOMBRE: "Trop sombre", SUREXPOSEE: "Trop forte" }[analyse.luminosite!]],
    ["Netteté", !visible ? "neutre" : analyse.nettete === "FLOUE" ? "alerte" : "succes",
      !visible ? "—" : { BONNE: "Bonne", CORRECTE: "Correcte", FLOUE: "Floue" }[analyse.nettete!]],
    ["Un seul visage", !analyse ? "neutre" : visible ? "succes" : "danger",
      !analyse ? "—" : visible ? "Oui" : analyse.nb_visages ? `${analyse.nb_visages} visages` : "Aucun"],
  ];

  const etatPose = (p: Pose): [string, Ton] => captures[p] ? ["Capturée", "succes"] : enCours?.pose === p ? ["En cours", "info"] : ["À faire", "neutre"];
  const consigne = erreurCamera ? erreurCamera : analyse?.nb_visages === 0 ? "Placez le visage dans l’ovale"
    : analyse && !analyse.taille_ok && analyse.nb_visages === 1 ? "Rapprochez-vous de la caméra" : enCours?.consigne;

  if (termine) {
    return (
      <>
        <Etapes courante={3} />
        <Carte className="mx-auto max-w-xl text-center">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-succes-pale text-succes"><Check size={30} /></span>
          <h2 className="mt-4 text-xl font-semibold">Enrôlement terminé</h2>
          <p className="mt-2 text-encre-douce">
            {agent.nom_complet} ({agent.matricule}) peut désormais pointer sur {tousSites ? "tous les sites équipés" : "les sites autorisés"}.
            {" "}{termine.nombre} gabarits chiffrés ont été enregistrés{termine.vivacite ? ", test de vivacité validé" : ""}.
            Les terminaux les reçoivent à leur prochaine synchronisation.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Bouton grand onClick={() => naviguer("/agents")}>Retour aux agents</Bouton>
            <Bouton grand variante="primaire" onClick={() => naviguer("/enrolement")}>Enrôler un autre agent</Bouton>
          </div>
        </Carte>
      </>
    );
  }

  return (
    <>
      <Etapes courante={2} />
      <div className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)_300px]">
        <Carte titre="Agent" className="self-start">
          <div className="flex items-center gap-3 border-b border-bord pb-4">
            <Avatar initiales={initiales(agent.nom_complet)} taille={48} />
            <div><p className="text-[17px] font-semibold">{agent.nom_complet}</p><p className="font-mono text-[13px]">{agent.matricule}</p></div>
          </div>
          <dl className="text-[15px]">
            <div className="border-b border-bord py-3"><dt className="text-xs text-encre-douce">Service</dt><dd className="font-semibold">{agent.service_nom}</dd></div>
            <div className="py-3"><dt className="text-xs text-encre-douce">Site de rattachement</dt>
              <dd className="font-semibold">{sites.data?.find((s) => s.id === agent.site_rattachement_id)?.nom ?? agent.site_rattachement_nom}</dd></div>
          </dl>
          <p className="mb-1 mt-2 text-[13px] font-semibold">Sites de pointage autorisés</p>
          <Radio nom="sites" libelle="Tous les sites équipés" coche={tousSites} onChange={() => setTousSites(true)} />
          <Radio nom="sites" libelle="Sélection de sites" coche={!tousSites} onChange={() => setTousSites(false)} />
          {!tousSites && <p className="mt-1 text-xs text-encre-douce">La sélection se règle dans la fiche de l’agent (page Agents).</p>}
        </Carte>

        <Carte titre="Capture du visage" sousTitre="5 poses sont nécessaires pour une reconnaissance fiable sur tous les terminaux.">
          <div className="relative flex aspect-[4/3] max-h-[420px] w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-[#233868] to-[#0F1A3A]">
            <video ref={video} autoPlay playsInline muted className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
            <canvas ref={toile} className="hidden" />
            <span className={cx("relative h-[62%] w-[38%] rounded-[50%] border-[5px] transition-colors",
              completes ? "border-succes-vif" : analyse && enCours && conforme(analyse, enCours.pose) ? "border-succes-vif" : "border-white")} />
            <span className="absolute left-4 top-3 flex items-center gap-1.5 text-xs text-menu-texte"><Camera size={14} /> Aperçu caméra</span>
            {(consigne || completes) && (
              <span className="absolute bottom-4 left-1/2 w-max max-w-[90%] -translate-x-1/2 rounded-2xl bg-kiosque-voile px-5 py-2.5 text-center text-[15px] font-medium text-white">
                {completes ? "Toutes les poses sont capturées" : consigne}
              </span>
            )}
          </div>
          <div className="mt-4 grid grid-cols-5 gap-2">
            {POSES.map((p) => {
              const [texte, ton] = etatPose(p.pose);
              return (
                <div key={p.pose} className={cx("rounded-[10px] border p-2.5", enCours?.pose === p.pose ? "border-primaire" : "border-bord")}>
                  <p className="text-sm font-semibold">{p.libelle}</p>
                  <Pastille ton={ton} className="mt-1.5 px-2">{texte}</Pastille>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap justify-center gap-3">
            <Bouton grand icone={RotateCcw} onClick={recommencer}>Recommencer la capture</Bouton>
            {!completes && maintenant - debutPose > DELAI_MANUEL_MS && analyse?.nb_visages === 1 && (
              <Bouton grand icone={Camera} onClick={captureManuelle}>Capturer cette pose</Bouton>
            )}
            <Bouton grand variante="primaire" icone={Check} disabled={!completes || !consentement} chargement={valider.isPending}
              onClick={() => valider.mutate()}>Valider l’enrôlement</Bouton>
          </div>
          {valider.error && <div className="mt-4"><MessageErreur erreur={valider.error} /></div>}
        </Carte>

        <div className="flex flex-col gap-5">
          <Carte titre="Qualité de la capture">
            <ul>
              {[...qualite, ["Test de vivacité", vivacite.ton, vivacite.texte] as [string, Ton, string]].map(([libelle, ton, texte]) => (
                <li key={libelle} className="flex items-center justify-between border-t border-bord py-2.5 text-[15px]">
                  {libelle}
                  <Pastille ton={ton} icone={ton === "succes" ? Check : libelle === "Test de vivacité" && ton === "info" ? RefreshCw : undefined}>{texte}</Pastille>
                </li>
              ))}
            </ul>
          </Carte>
          <Carte titre="Consentement et protection">
            <CaseACocher coche={consentement} onChange={setConsentement}
              libelle="L’agent a été informé du traitement de ses données biométriques et y consent." />
            <div className="mt-4"><Encart icone={Lock}>Le gabarit du visage est chiffré avant d’être enregistré sur le serveur central.</Encart></div>
          </Carte>
        </div>
      </div>
    </>
  );
}
