/** Écran tactile du terminal de pointage (maquettes « Terminal · … »), affiché en mode kiosque.
 *  Conçu en 1024 × 600 et mis à l'échelle pour remplir n'importe quel écran. */
import { StrictMode, useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, ArrowLeft, ArrowRight, Building2, Camera, Check, Eye, PhoneCall, RefreshCw, RotateCcw, ScanFace,
  UserX, Wifi, WifiOff, X } from "lucide-react";
import "../commun/styles.css";
import { appliquerMarque } from "../commun/marque";
import { dateLongue, heure } from "../commun/format";

interface Etat {
  etat: "ATTENTE" | "ANALYSE" | "DEFI" | "SUCCES" | "REFUS" | "INFO" | "CAMERA";
  visage: number[] | null; progression: number;
  defi: { type: "tourner" | "cligner"; direction: "droite" | "gauche" | null; consigne: string; restant: number } | null;
  resultat: { type: "ENTREE" | "SORTIE"; agent: { prenom: string; nom: string; matricule: string; initiales: string };
    heure: string; site_rattachement: string; hors_rattachement: boolean; hors_ligne: boolean } | null;
  refus: { code: string; titre: string; message: string } | null;
  fin_dans: number | null; mode: "ENTREE" | "SORTIE" | null; type_propose: "ENTREE" | "SORTIE";
  terminal: { code: string; site: string; reseau: string; message_reseau: string; en_attente: number; agents: number;
    organisation: { couleur_primaire?: string; couleur_menu?: string; sigle?: string } };
}

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
const envoyer = (chemin: string, corps?: unknown) =>
  fetch(chemin, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps ?? {}) });

function useEtat() {
  const [etat, setEtat] = useState<Etat | null>(null);
  const [perdu, setPerdu] = useState(false);
  useEffect(() => {
    let actif = true;
    const lire = async () => {
      try {
        const r = await fetch("/api/etat");
        if (actif && r.ok) { setEtat(await r.json()); setPerdu(false); }
      } catch { if (actif) setPerdu(true); }
      if (actif) setTimeout(lire, 200);
    };
    lire();
    return () => { actif = false; };
  }, []);
  return { etat, perdu };
}

/** Met à l'échelle la scène 1024 × 600 pour remplir l'écran sans déformation. */
function useEchelle() {
  const calcul = () => Math.min(window.innerWidth / 1024, window.innerHeight / 600);
  const [e, setE] = useState(calcul);
  useEffect(() => { const f = () => setE(calcul()); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  return e;
}

function Horloge() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return (
    <div className="flex flex-col items-end">
      <span className="text-[30px] font-semibold leading-none">{heure(t)}</span>
      <span className="mt-1 text-[13px] text-kiosque-texte">{dateLongue(t)}</span>
    </div>
  );
}

function Reseau({ t }: { t: Etat["terminal"] }) {
  const style = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-[3px] text-xs font-semibold";
  if (t.reseau === "EN_LIGNE") return <span className={cx(style, "bg-succes-pale text-succes")}><Wifi size={14} /> En ligne</span>;
  if (t.reseau === "SYNCHRO") return <span className={cx(style, "bg-primaire-pale text-primaire")}><RefreshCw size={14} /> Synchronisation…</span>;
  if (t.reseau === "REFUSE") return <span className={cx(style, "bg-danger-pale text-danger")}><X size={14} /> Terminal non autorisé</span>;
  if (t.reseau === "CONNEXION") return <span className={cx(style, "bg-surface-grise text-encre-douce")}><RefreshCw size={14} /> Connexion…</span>;
  return <span className={cx(style, "bg-alerte-pale text-alerte")}><WifiOff size={14} /> Hors ligne · enregistrement local</span>;
}

function Ecran() {
  const { etat: e, perdu } = useEtat();
  const echelle = useEchelle();
  const [logoKo, setLogoKo] = useState(false);
  useEffect(() => { appliquerMarque(e?.terminal.organisation.couleur_primaire, e?.terminal.organisation.couleur_menu); },
    [e?.terminal.organisation.couleur_primaire, e?.terminal.organisation.couleur_menu]);

  return (
    <div className="flex h-screen w-screen items-center justify-center overflow-hidden bg-kiosque">
      <div style={{ width: 1024, height: 600, transform: `scale(${echelle})` }}
        className="flex shrink-0 select-none flex-col overflow-hidden bg-kiosque text-white">
        <header className="flex h-[76px] shrink-0 items-center justify-between px-7">
          <div className="flex items-center gap-3.5">
            <img src={logoKo ? "/logo-defaut.png" : "/api/logo"} onError={() => setLogoKo(true)} alt=""
              className="h-12 w-12 rounded-[10px] bg-white object-contain" />
            <div className="flex flex-col">
              <span className="text-xl font-semibold">{e?.terminal.site || "Terminal de pointage"}</span>
              <span className="text-[13px] text-kiosque-texte">Terminal {e?.terminal.code}</span>
            </div>
          </div>
          <div className="flex items-center gap-5">
            {e && <Reseau t={e.terminal} />}
            <Horloge />
          </div>
        </header>
        <div className="flex min-h-0 flex-1 gap-5 px-7 pb-7">
          <Camera_ e={e} perdu={perdu} />
          <aside className="flex w-[340px] shrink-0 flex-col gap-3.5 rounded-[20px] bg-white p-6 text-encre">
            {perdu || !e ? <Panneau titre="Service indisponible" texte="Le service du terminal ne répond pas. Il redémarre automatiquement." />
              : <PanneauDroit e={e} />}
          </aside>
        </div>
      </div>
    </div>
  );
}

function Camera_({ e, perdu }: { e: Etat | null; perdu: boolean }) {
  const [videoKo, setVideoKo] = useState(false);
  const etat = e?.etat;
  const couleurOvale = etat === "SUCCES" ? "border-succes-vif" : etat === "REFUS" ? "border-danger-vif"
    : etat === "DEFI" ? "border-[#F5B83D]" : etat === "INFO" && e?.refus?.code !== "DEJA" ? "border-danger-vif" : "border-white";
  let bulle: ReactNode = null;
  if (!e || perdu) bulle = null;
  else if (etat === "CAMERA") bulle = <><Camera size={20} /> Caméra indisponible</>;
  else if (etat === "SUCCES" && e.resultat) bulle = <><Check size={20} className="text-succes-vif" />
    {e.resultat.type === "ENTREE" ? "Bonjour" : "Au revoir"} {e.resultat.agent.prenom}</>;
  else if (etat === "REFUS") bulle = <><AlertTriangle size={20} className="text-danger-vif" /> Vérification de vivacité échouée</>;
  else if (etat === "INFO" && e.refus) bulle = <><AlertTriangle size={20} className="text-danger-vif" /> {e.refus.titre}</>;
  else if (etat === "DEFI" && e.defi) bulle = <>{e.defi.type === "cligner" ? <Eye size={20} /> : <ScanFace size={20} />} {e.defi.consigne}</>;
  else if (etat === "ANALYSE") bulle = <><ScanFace size={20} /> Restez immobile…</>;
  else bulle = <><Camera size={20} /> Recherche d’un visage…</>;

  return (
    <div className="relative flex min-w-0 flex-1 items-center justify-center overflow-hidden rounded-[20px] bg-gradient-to-br from-[#233868] to-[#0F1A3A]">
      {!videoKo && etat !== "CAMERA" && !perdu
        ? <img src="/video.mjpg" alt="" onError={() => setVideoKo(true)} className="absolute inset-0 h-full w-full object-cover" />
        : <div className="absolute bottom-0 left-1/2 -ml-[160px]"><div className="mx-auto mb-[-60px] h-[124px] w-[124px] rounded-full bg-white/[.18]" />
            <div className="h-[220px] w-[320px] rounded-t-[160px] bg-white/[.12]" /></div>}
      <div className={cx("relative h-[310px] w-[236px] rounded-[50%] border-[5px] transition-colors duration-200", couleurOvale)}>
        {etat === "ANALYSE" && (
          <svg className="absolute -inset-[5px] h-[310px] w-[236px]" viewBox="0 0 236 310" aria-hidden>
            <ellipse cx="118" cy="155" rx="115.5" ry="152.5" fill="none" stroke="#3DDC97" strokeWidth="5"
              strokeDasharray={`${(e?.progression ?? 0) * 845} 845`} transform="rotate(-90 118 155)" />
          </svg>
        )}
        {etat === "DEFI" && e?.defi?.type === "tourner" && (
          <span className={cx("absolute top-1/2 -translate-y-1/2 text-[#F5B83D]", e.defi.direction === "droite" ? "-right-24" : "-left-24")}>
            {e.defi.direction === "droite" ? <ArrowRight size={64} strokeWidth={2.5} className="animate-pulse" /> : <ArrowLeft size={64} strokeWidth={2.5} className="animate-pulse" />}
          </span>
        )}
      </div>
      <span className="absolute left-[18px] top-4 text-xs text-menu-texte">Aperçu caméra</span>
      {bulle && (
        <span className="absolute bottom-6 left-1/2 inline-flex -translate-x-1/2 items-center gap-2.5 whitespace-nowrap rounded-full bg-kiosque-voile px-5 py-3 text-[17px] font-medium">
          {bulle}
        </span>
      )}
    </div>
  );
}

const Badge = ({ ton, icone, children }: { ton: "succes" | "danger" | "alerte" | "info"; icone: ReactNode; children: ReactNode }) => (
  <span className={cx("inline-flex items-center gap-1.5 self-stretch rounded-full px-3 py-1 text-[13px] font-semibold",
    { succes: "bg-succes-pale text-succes", danger: "bg-danger-pale text-danger", alerte: "bg-alerte-pale text-alerte", info: "bg-primaire-pale text-primaire" }[ton])}>
    {icone}{children}
  </span>
);

const BoutonKiosque = ({ primaire, onClick, children }: { primaire?: boolean; onClick: () => void; children: ReactNode }) => (
  <button type="button" onClick={onClick} className={cx("flex min-h-[48px] w-full items-center justify-center gap-2 rounded-[10px] text-[15px] font-semibold active:scale-[.98]",
    primaire ? "bg-primaire text-white" : "border border-bord-champ bg-white text-encre")}>{children}</button>
);

function Panneau({ titre, texte }: { titre: string; texte: string }) {
  return <><h1 className="text-[28px] font-semibold leading-[1.15]">{titre}</h1><p className="text-base text-encre-douce">{texte}</p></>;
}

function PanneauDroit({ e }: { e: Etat }) {
  if (e.etat === "CAMERA") return <Panneau titre="Caméra indisponible" texte="Vérifiez le branchement de la caméra. Le terminal réessaie automatiquement." />;

  if (e.etat === "SUCCES" && e.resultat) {
    const r = e.resultat;
    return (
      <>
        <Badge ton="succes" icone={<Check size={16} />}>{r.type === "ENTREE" ? "Entrée enregistrée" : "Sortie enregistrée"}</Badge>
        <div className="flex items-center gap-4">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primaire-pale text-[22px] font-semibold text-primaire">{r.agent.initiales}</span>
          <div className="min-w-0"><p className="truncate text-2xl font-semibold leading-tight">{r.agent.prenom} {r.agent.nom}</p>
            <p className="font-mono text-[13px]">{r.agent.matricule}</p></div>
        </div>
        <p className="border-b border-bord pb-3.5 text-[40px] font-semibold leading-none">{r.heure}</p>
        <div className="border-b border-bord pb-3"><p className="text-xs text-encre-douce">Site de pointage</p><p className="font-semibold">{e.terminal.site}</p></div>
        <div><p className="text-xs text-encre-douce">Site de rattachement</p><p className="font-semibold">{r.site_rattachement}</p></div>
        {r.hors_rattachement && !r.hors_ligne && <Badge ton="info" icone={<Building2 size={15} />}>Hors rattachement · pointage autorisé</Badge>}
        {r.hors_ligne && (
          <div className="flex gap-3 rounded-[10px] bg-alerte-pale p-3.5 text-[13px] text-alerte">
            <WifiOff size={18} className="shrink-0" />
            <span><b>Enregistré sur ce terminal.</b> Envoi au serveur dès le retour du réseau. {e.terminal.en_attente} pointage{e.terminal.en_attente > 1 ? "s" : ""} en attente.</span>
          </div>
        )}
        <div className="flex-1" />
        <BoutonKiosque onClick={() => envoyer("/api/annuler")}>Ce n’est pas moi</BoutonKiosque>
        {!r.hors_ligne && <p className="text-center text-xs text-encre-douce">Cet écran se ferme dans {e.fin_dans ?? 0} s</p>}
      </>
    );
  }

  if (e.etat === "REFUS" && e.refus) return (
    <>
      <Badge ton="danger" icone={<X size={16} />}>Pointage refusé</Badge>
      <h1 className="text-[28px] font-semibold leading-[1.15]">{e.refus.titre}</h1>
      <p className="text-base text-encre-douce">{e.refus.message}</p>
      <div className="rounded-[10px] border border-bord bg-surface p-3.5">
        <p className="text-sm font-semibold">Tentative enregistrée</p>
        <p className="text-[13px] text-encre-douce">Elle sera transmise au responsable pour contrôle.</p>
      </div>
      <div className="flex-1" />
      <BoutonKiosque primaire onClick={() => envoyer("/api/reessayer")}><RotateCcw size={18} /> Réessayer</BoutonKiosque>
      <BoutonKiosque onClick={() => envoyer("/api/superviseur")}><PhoneCall size={18} /> Appeler le superviseur</BoutonKiosque>
    </>
  );

  if (e.etat === "INFO" && e.refus) {
    const r = e.refus;
    const ton = r.code === "DEJA" || r.code === "SUPERVISEUR" ? "info" : r.code === "CONTESTE" ? "alerte" : "danger";
    const icone = r.code === "CONTESTE" ? <UserX size={16} /> : r.code === "DEJA" ? <Check size={16} /> : r.code === "SUPERVISEUR" ? <PhoneCall size={16} /> : <X size={16} />;
    const libelle = { DEJA: "Déjà enregistré", SUPERVISEUR: "Assistance demandée", CONTESTE: "Pointage annulé", NON_AUTORISE: "Pointage refusé",
      INCONNU: "Pointage refusé", GALERIE_VIDE: "Synchronisation requise" }[r.code] ?? "Information";
    return (
      <>
        <Badge ton={ton} icone={icone}>{libelle}</Badge>
        <h1 className="text-[28px] font-semibold leading-[1.15]">{r.titre}</h1>
        <p className="text-base text-encre-douce">{r.message}</p>
        <div className="flex-1" />
        {r.code === "INCONNU" && <BoutonKiosque onClick={() => envoyer("/api/superviseur")}><PhoneCall size={18} /> Appeler le superviseur</BoutonKiosque>}
        <BoutonKiosque primaire onClick={() => envoyer("/api/reessayer")}><RotateCcw size={18} /> {r.code === "DEJA" ? "Fermer" : "Réessayer"}</BoutonKiosque>
        <p className="text-center text-xs text-encre-douce">Cet écran se ferme dans {e.fin_dans ?? 0} s</p>
      </>
    );
  }

  if (e.etat === "DEFI" && e.defi) return (
    <>
      <p className="text-xs font-semibold tracking-[0.08em] text-encre-douce">CONTRÔLE ANTI-FRAUDE</p>
      <h1 className="text-[28px] font-semibold leading-[1.15]">{e.defi.consigne}</h1>
      <p className="text-base text-encre-douce">
        {e.defi.type === "cligner" ? "Fermez puis rouvrez les yeux naturellement, en regardant la caméra."
          : `Tournez la tête vers votre ${e.defi.direction}, comme dans un miroir, puis revenez de face.`}
      </p>
      <div className="flex flex-1 items-center justify-center text-primaire">
        {e.defi.type === "cligner" ? <Eye size={88} strokeWidth={1.5} /> : e.defi.direction === "droite"
          ? <ArrowRight size={88} strokeWidth={1.5} /> : <ArrowLeft size={88} strokeWidth={1.5} />}
      </div>
      <div className="h-2 rounded-full bg-surface-grise">
        <div className="h-full rounded-full bg-primaire transition-all duration-200" style={{ width: `${(e.defi.restant / 7) * 100}%` }} />
      </div>
      <p className="text-center text-xs text-encre-douce">Ce contrôle empêche le pointage avec une photo ou un écran.</p>
    </>
  );

  const choisi = e.mode ?? e.type_propose;
  const choisir = (t: "ENTREE" | "SORTIE") => envoyer("/api/mode", { mode: e.mode === t ? null : t });
  return (
    <>
      <p className="text-xs font-semibold tracking-[0.08em] text-encre-douce">POINTAGE AUTOMATIQUE</p>
      <h1 className="text-[28px] font-semibold leading-[1.15]">Regardez la caméra</h1>
      <ol className="mt-1 flex flex-col gap-3">
        {["Placez votre visage dans l’ovale", "Restez immobile une seconde", "Clignez des yeux si demandé"].map((t, i) => (
          <li key={t} className="flex items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primaire-pale font-semibold text-primaire">{i + 1}</span>
            <span className="text-base">{t}</span>
          </li>
        ))}
      </ol>
      <div className="flex-1" />
      <div className="flex flex-col gap-2.5 border-t border-bord pt-3.5">
        <p className="text-[13px] text-encre-douce">Type de pointage</p>
        <div className="flex overflow-hidden rounded-[10px] border border-bord-champ">
          {(["ENTREE", "SORTIE"] as const).map((t) => (
            <button key={t} type="button" onClick={() => choisir(t)}
              className={cx("min-h-[48px] flex-1 text-base font-semibold", choisi === t ? "bg-primaire text-white" : "bg-white text-encre")}>
              {t === "ENTREE" ? "Entrée" : "Sortie"}
            </button>
          ))}
        </div>
        <p className="text-xs text-encre-douce">
          {e.mode ? "Choix manuel, valable 30 secondes." : "Détecté automatiquement d’après votre dernier pointage."}
        </p>
      </div>
    </>
  );
}

createRoot(document.getElementById("racine")!).render(<StrictMode><Ecran /></StrictMode>);
