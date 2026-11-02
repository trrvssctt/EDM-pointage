/** Composants d'interface communs, fidèles aux maquettes (rayons, couleurs, typographie). */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode, type ButtonHTMLAttributes,
  type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Loader2, Wifi, WifiOff, X, type LucideIcon } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/* ---------- Boutons ---------- */
type VarianteBouton = "primaire" | "secondaire" | "danger" | "fantome";
const VARIANTES: Record<VarianteBouton, string> = {
  primaire: "bg-primaire text-white border border-primaire hover:bg-primaire-fonce",
  secondaire: "bg-white text-encre border border-bord-champ hover:bg-surface",
  danger: "bg-white text-danger border border-danger/40 hover:bg-danger-pale",
  fantome: "bg-transparent text-primaire border border-transparent hover:bg-primaire-pale",
};

export function Bouton({ variante = "secondaire", icone: Icone, chargement, grand, className, children, ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variante?: VarianteBouton; icone?: LucideIcon; chargement?: boolean; grand?: boolean }) {
  return (
    <button type="button" {...props} disabled={props.disabled || chargement}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50", grand ? "min-h-[44px] px-5 text-[15px]" : "min-h-[40px] px-4 text-sm",
        VARIANTES[variante], className)}>
      {chargement ? <Loader2 size={18} className="animate-spin" /> : Icone && <Icone size={18} strokeWidth={1.9} />}
      {children}
    </button>
  );
}

/* ---------- Cartes et en-têtes ---------- */
export function Carte({ titre, sousTitre, action, children, className, sansMarge }:
  { titre?: ReactNode; sousTitre?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; sansMarge?: boolean }) {
  return (
    <section className={cx("rounded-carte border border-bord bg-white", !sansMarge && "p-5", className)}>
      {(titre || action) && (
        <div className={cx("mb-4 flex flex-wrap items-start justify-between gap-3", sansMarge && "px-5 pt-5")}>
          <div>
            {titre && <h2 className="text-base font-semibold">{titre}</h2>}
            {sousTitre && <p className="mt-0.5 text-[13px] text-encre-douce">{sousTitre}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function EnTetePage({ titre, sousTitre, actions }: { titre: string; sousTitre?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight">{titre}</h1>
        {sousTitre && <p className="mt-1 text-sm text-encre-douce">{sousTitre}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <EtatServeur />
        {actions}
      </div>
    </header>
  );
}

/** Pastille « Serveur central connecté » : vérifie la disponibilité de l'API toutes les 15 s. */
export function EtatServeur() {
  const { isError, isSuccess } = useQuery({
    queryKey: ["sante"], refetchInterval: 15000, retry: false,
    queryFn: async () => { const r = await fetch("/api/sante"); if (!r.ok) throw new Error(); return r.json(); },
  });
  if (isError) return <Pastille ton="danger" icone={WifiOff}>Serveur central injoignable</Pastille>;
  if (!isSuccess) return null;
  return <Pastille ton="succes" icone={Wifi}>Serveur central connecté</Pastille>;
}

/* ---------- Pastilles, avatars ---------- */
export type Ton = "succes" | "alerte" | "danger" | "info" | "neutre";
const TONS: Record<Ton, string> = {
  succes: "bg-succes-pale text-succes", alerte: "bg-alerte-pale text-alerte", danger: "bg-danger-pale text-danger",
  info: "bg-primaire-pale text-primaire", neutre: "bg-surface-grise text-encre-douce",
};

export function Pastille({ ton = "neutre", icone: Icone, children, className }:
  { ton?: Ton; icone?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-[3px] text-xs font-semibold",
      TONS[ton], className)}>
      {Icone && <Icone size={14} strokeWidth={2} />}
      {children}
    </span>
  );
}

export function Avatar({ initiales, taille = 36, ton = "info" }: { initiales: string; taille?: number; ton?: "info" | "neutre" }) {
  return (
    <span style={{ width: taille, height: taille, fontSize: taille * 0.36 }}
      className={cx("inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        ton === "info" ? "bg-primaire-pale text-primaire" : "bg-surface-grise text-encre-douce")}>
      {initiales}
    </span>
  );
}

/* ---------- Champs de formulaire ---------- */
const STYLE_CHAMP = "w-full min-h-[44px] rounded-lg border border-bord-champ bg-white px-3 text-[15px] text-encre " +
  "placeholder:text-encre-douce/80 disabled:bg-surface";

export function Champ({ libelle, aide, erreur, className, ...props }:
  InputHTMLAttributes<HTMLInputElement> & { libelle?: string; aide?: string; erreur?: string }) {
  return (
    <label className={cx("flex flex-col gap-1.5", className)}>
      {libelle && <span className="text-[13px] font-semibold">{libelle}</span>}
      <input {...props} className={cx(STYLE_CHAMP, erreur && "border-danger")} />
      {aide && !erreur && <span className="text-xs text-encre-douce">{aide}</span>}
      {erreur && <span className="text-xs text-danger">{erreur}</span>}
    </label>
  );
}

export function Selection({ libelle, options, vide, className, ...props }:
  SelectHTMLAttributes<HTMLSelectElement> & { libelle?: string; vide?: string;
    options: { valeur: string | number; libelle: string }[] }) {
  return (
    <label className={cx("flex flex-col gap-1.5", className)}>
      {libelle && <span className="text-[13px] font-semibold">{libelle}</span>}
      <select {...props} className={cx(STYLE_CHAMP, "pr-8")}>
        {vide !== undefined && <option value="">{vide}</option>}
        {options.map((o) => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
      </select>
    </label>
  );
}

export function CaseACocher({ libelle, coche, onChange, disabled }:
  { libelle: ReactNode; coche: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-[15px]">
      <input type="checkbox" checked={coche} disabled={disabled} onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 accent-primaire" />
      <span>{libelle}</span>
    </label>
  );
}

export function Radio({ libelle, coche, onChange, nom }: { libelle: ReactNode; coche: boolean; onChange: () => void; nom: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 py-1 text-[15px]">
      <input type="radio" name={nom} checked={coche} onChange={onChange} className="h-5 w-5 accent-primaire" />
      {libelle}
    </label>
  );
}

export function Interrupteur({ actif, onChange, libelle, disabled }:
  { actif: boolean; onChange: (v: boolean) => void; libelle?: ReactNode; disabled?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" role="switch" aria-checked={actif} disabled={disabled} onClick={() => onChange(!actif)}
        className={cx("relative h-6 w-10 shrink-0 rounded-full transition-colors disabled:opacity-50",
          actif ? "bg-primaire" : "bg-bord-champ")}>
        <span className={cx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", actif ? "left-[18px]" : "left-0.5")} />
      </button>
      {libelle && <span className="text-sm font-semibold leading-tight">{libelle}</span>}
    </span>
  );
}

/** Groupe de boutons à bascule (« Présence | Retards | Absences », « Entrée | Sortie »). */
export function Segments<T extends string>({ valeur, options, onChange, className }:
  { valeur: T; options: { valeur: T; libelle: string }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cx("flex overflow-hidden rounded-[10px] border border-bord-champ", className)} role="tablist">
      {options.map((o) => (
        <button key={o.valeur} type="button" role="tab" aria-selected={valeur === o.valeur} onClick={() => onChange(o.valeur)}
          className={cx("min-h-[44px] flex-1 px-3 text-[15px] font-semibold",
            valeur === o.valeur ? "bg-primaire text-white" : "bg-white text-encre hover:bg-surface")}>
          {o.libelle}
        </button>
      ))}
    </div>
  );
}

/* ---------- Tableaux ---------- */
export function Tableau({ entetes, children, vide, chargement, largeurMin = 0 }:
  { entetes: ReactNode[]; children: ReactNode; vide?: boolean; chargement?: boolean; largeurMin?: number }) {
  return (
    <div className="overflow-x-auto rounded-[10px] border border-bord">
      <table className="w-full border-collapse text-sm" style={{ minWidth: largeurMin }}>
        <thead>
          <tr className="bg-surface text-left">
            {entetes.map((e, i) => (
              <th key={i} className="whitespace-nowrap border-b border-bord px-3.5 py-2.5 text-[13px] font-semibold text-encre-douce">{e}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {chargement && <Chargement />}
      {!chargement && vide && <EtatVide />}
    </div>
  );
}

export const Ligne = ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
  <tr onClick={onClick} className={cx("border-b border-bord-leger last:border-0", onClick && "cursor-pointer hover:bg-surface")}>{children}</tr>
);
export const Cellule = ({ children, className }: { children?: ReactNode; className?: string }) => (
  <td className={cx("px-3.5 py-3 align-middle", className)}>{children}</td>
);

export function Pagination({ page, total, taille, onPage, libelle }:
  { page: number; total: number; taille: number; onPage: (p: number) => void; libelle?: string }) {
  const pages = Math.max(1, Math.ceil(total / taille));
  const debut = total ? (page - 1) * taille + 1 : 0;
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <span className="text-[13px] text-encre-douce">
        {libelle ?? `${debut} à ${Math.min(page * taille, total)} sur ${total.toLocaleString("fr-FR")}`}
      </span>
      <div className="flex gap-2">
        <Bouton grand icone={ChevronLeft} disabled={page <= 1} onClick={() => onPage(page - 1)}>Précédent</Bouton>
        <Bouton grand disabled={page >= pages} onClick={() => onPage(page + 1)}>Suivant <ChevronRight size={18} /></Bouton>
      </div>
    </div>
  );
}

/* ---------- États ---------- */
export const Chargement = ({ texte = "Chargement…" }: { texte?: string }) => (
  <div className="flex items-center justify-center gap-2 p-8 text-sm text-encre-douce">
    <Loader2 size={18} className="animate-spin" /> {texte}
  </div>
);

export const EtatVide = ({ texte = "Aucun résultat" }: { texte?: string }) => (
  <p className="p-8 text-center text-sm text-encre-douce">{texte}</p>
);

export const MessageErreur = ({ erreur }: { erreur: unknown }) => (
  <div className="flex items-start gap-2 rounded-[10px] border border-danger/30 bg-danger-pale p-4 text-sm text-danger">
    <AlertTriangle size={18} className="mt-0.5 shrink-0" />
    <span className="whitespace-pre-line">{erreur instanceof Error ? erreur.message : String(erreur)}</span>
  </div>
);

export const Encart = ({ icone: Icone, children, ton = "neutre" }: { icone?: LucideIcon; children: ReactNode; ton?: "neutre" | "alerte" }) => (
  <div className={cx("flex items-start gap-2.5 rounded-[10px] border p-3.5 text-[13px]",
    ton === "alerte" ? "border-alerte/20 bg-alerte-pale text-alerte" : "border-bord bg-surface text-encre-douce")}>
    {Icone && <Icone size={17} className="mt-0.5 shrink-0" />}
    <div>{children}</div>
  </div>
);

/* ---------- Fenêtre modale ---------- */
export function Modale({ titre, sousTitre, onFermer, children, actions, large }:
  { titre: string; sousTitre?: string; onFermer: () => void; children: ReactNode; actions?: ReactNode; large?: boolean }) {
  useEffect(() => {
    const echap = (e: KeyboardEvent) => e.key === "Escape" && onFermer();
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [onFermer]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#081028]/50 sm:items-center sm:p-6" onMouseDown={onFermer}>
      <div role="dialog" aria-modal="true" aria-label={titre} onMouseDown={(e) => e.stopPropagation()}
        className={cx("max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl",
          large ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{titre}</h2>
            {sousTitre && <p className="mt-0.5 text-sm text-encre-douce">{sousTitre}</p>}
          </div>
          <button type="button" aria-label="Fermer" onClick={onFermer} className="rounded-lg p-1.5 text-encre-douce hover:bg-surface">
            <X size={20} />
          </button>
        </div>
        {children}
        {actions && <div className="mt-6 flex flex-wrap justify-end gap-3">{actions}</div>}
      </div>
    </div>
  );
}

/* ---------- Notifications ---------- */
type Notif = { id: number; texte: string; ton: "succes" | "danger" };
const ContexteNotif = createContext<(texte: string, ton?: "succes" | "danger") => void>(() => {});
export const useNotifier = () => useContext(ContexteNotif);

export function FournisseurNotifications({ children }: { children: ReactNode }) {
  const [liste, setListe] = useState<Notif[]>([]);
  const notifier = useCallback((texte: string, ton: "succes" | "danger" = "succes") => {
    const id = Date.now() + Math.random();
    setListe((l) => [...l, { id, texte, ton }]);
    setTimeout(() => setListe((l) => l.filter((n) => n.id !== id)), 5000);
  }, []);
  return (
    <ContexteNotif.Provider value={notifier}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {liste.map((n) => (
          <div key={n.id} className={cx("flex items-start gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg",
            n.ton === "succes" ? "bg-[#0F2A5C]" : "bg-danger")}>
            {n.ton === "succes" ? <Check size={18} className="mt-0.5 shrink-0" /> : <AlertTriangle size={18} className="mt-0.5 shrink-0" />}
            <span className="whitespace-pre-line">{n.texte}</span>
          </div>
        ))}
      </div>
    </ContexteNotif.Provider>
  );
}
