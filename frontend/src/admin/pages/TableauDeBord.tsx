/** Tableau de bord (maquette « Tableau de bord »). Actualisation automatique toutes les 30 s. */
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Building2, Check, Clock, Download, KeyRound, PhoneCall, RefreshCw, ScanFace, WifiOff, X,
  type LucideIcon } from "lucide-react";
import { api } from "../api";
import { useSession } from "../session";
import type { Anomalie, TableauDeBord as Donnees } from "../types";
import { Bouton, Carte, Cellule, Chargement, EnTetePage, Ligne, MessageErreur, Pastille, Tableau, cx, useNotifier } from "../composants/ui";
import { EtatTerminalPastille } from "../composants/Etats";
import { jourAbrege, nombre, pourcent } from "../../commun/format";

function Indicateur({ libelle, valeur, legende, icone: Icone, ton }:
  { libelle: string; valeur: number; legende: string; icone: LucideIcon; ton: "succes" | "alerte" | "danger" | "info" }) {
  const couleurs = { succes: "bg-succes-pale text-succes", alerte: "bg-alerte-pale text-alerte",
    danger: "bg-danger-pale text-danger", info: "bg-primaire-pale text-primaire" }[ton];
  return (
    <div className="rounded-carte border border-bord bg-white p-5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-encre-douce">{libelle}</span>
        <span className={cx("flex h-[34px] w-[34px] items-center justify-center rounded-lg", couleurs)}><Icone size={18} /></span>
      </div>
      <p className="mt-2 text-[34px] font-semibold leading-none">{nombre(valeur)}</p>
      <p className="mt-3 text-[13px] text-encre-douce">{legende}</p>
    </div>
  );
}

const ICONES_ANOMALIE: Record<string, [LucideIcon, string]> = {
  FRAUDE: [AlertTriangle, "bg-danger-pale text-danger"], SUPERVISEUR: [PhoneCall, "bg-danger-pale text-danger"],
  SANS_SORTIE: [Clock, "bg-alerte-pale text-alerte"], TERMINAL: [WifiOff, "bg-alerte-pale text-alerte"],
  HORS_RATTACHEMENT: [Building2, "bg-primaire-pale text-primaire"], MOT_DE_PASSE: [KeyRound, "bg-primaire-pale text-primaire"],
  ENROLEMENT: [ScanFace, "bg-primaire-pale text-primaire"],
};

function lienAnomalie(a: Anomalie): string {
  const { page, ...reste } = a.lien;
  const chemin = { pointages: "/pointages", rapports: "/rapports", sites: "/sites", utilisateurs: "/utilisateurs", enrolement: "/enrolement" }[String(page)] ?? "/";
  const q = new URLSearchParams(Object.entries(reste).map(([k, v]) => [k, String(v)])).toString();
  return q ? `${chemin}?${q}` : chemin;
}

export function TableauDeBord() {
  const { session } = useSession();
  const notifier = useNotifier();
  const naviguer = useNavigate();
  const { data: d, error, isLoading } = useQuery({
    queryKey: ["tableau-de-bord"], refetchInterval: 30_000,
    queryFn: () => api.get<Donnees>("/api/tableau-de-bord"),
  });
  const u = session!.utilisateur;
  const portee = u.role === "RESPONSABLE" ? u.perimetre : "tous les sites";

  if (isLoading) return <Chargement />;
  if (error || !d) return <MessageErreur erreur={error} />;
  const maxJour = Math.max(1, ...d.evolution.map((e) => e.presents));
  const exporter = () => api.telecharger("/api/tableau-de-bord/export.xlsx").catch((e) => notifier(e.message, "danger"));

  return (
    <>
      <EnTetePage titre="Tableau de bord" sousTitre={`${d.date_longue.charAt(0).toUpperCase()}${d.date_longue.slice(1)} · ${portee}`}
        actions={<Bouton grand icone={Download} onClick={exporter}>Exporter la journée</Bouton>} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Indicateur libelle="Agents présents" valeur={d.presents} icone={Check} ton="succes"
          legende={`${pourcent(d.taux_presence)} des ${nombre(d.attendus)} attendus`} />
        <Indicateur libelle="Retards" valeur={d.retards} icone={Clock} ton="alerte" legende={`${pourcent(d.taux_retard)} des agents attendus`} />
        <Indicateur libelle="Absences" valeur={d.absences} icone={X} ton="danger" legende={`${pourcent(d.taux_absence)} des agents attendus`} />
        <Indicateur libelle="En attente de synchronisation" valeur={d.en_attente} icone={RefreshCw} ton="info"
          legende={d.en_attente ? `pointages sur ${d.terminaux_en_attente} terminal${d.terminaux_en_attente > 1 ? "aux" : ""}` : "tous les terminaux sont à jour"} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.55fr_1fr]">
        <Carte titre="Présence par site" sousTitre={`${d.date_longue.charAt(0).toUpperCase()}${d.date_longue.slice(1)} · principaux sites`}>
          {d.presence_par_site.length === 0 && <p className="text-sm text-encre-douce">Aucun agent attendu ce jour.</p>}
          <ul className="flex flex-col gap-3">
            {d.presence_par_site.slice(0, 6).map((s) => (
              <li key={s.site} className="grid grid-cols-[minmax(0,1.3fr)_minmax(80px,1fr)_auto_auto] items-center gap-3 text-sm sm:gap-4">
                <span className="truncate font-medium">{s.site}</span>
                <span className="h-2.5 rounded-full bg-surface-grise">
                  <span className={cx("block h-full rounded-full", s.taux < 85 ? "bg-alerte-barre" : "bg-primaire")}
                    style={{ width: `${s.taux}%` }} />
                </span>
                <span className="w-[72px] text-right text-[13px] text-encre-douce">{s.presents} / {s.attendus}</span>
                <span className="w-[52px] text-right font-semibold">{Math.round(s.taux)} %</span>
              </li>
            ))}
          </ul>
        </Carte>

        <Carte titre="Agents présents sur 7 jours" sousTitre="Week-end en teinte claire">
          <div className="flex h-[190px] items-end gap-3">
            {d.evolution.map((e) => (
              <div key={e.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
                <span className="text-xs font-semibold">{nombre(e.presents)}</span>
                <span className={cx("w-full max-w-[38px] rounded-t", e.week_end ? "bg-primaire-clair" : "bg-primaire")}
                  style={{ height: `${Math.max(2, (e.presents / maxJour) * 150)}px` }} title={`${e.presents} présents`} />
                <span className="whitespace-nowrap text-xs text-encre-douce">{jourAbrege(e.date)}</span>
              </div>
            ))}
          </div>
        </Carte>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Carte titre="Anomalies à traiter"
          action={d.anomalies.length > 0 && <Pastille ton="danger">{d.anomalies.length} à examiner</Pastille>}>
          {d.anomalies.length === 0 && <p className="text-sm text-encre-douce">Aucune anomalie à traiter.</p>}
          <ul>
            {d.anomalies.map((a, i) => {
              const [Icone, couleurs] = ICONES_ANOMALIE[a.type] ?? [AlertTriangle, "bg-surface text-encre"];
              return (
                <li key={i} className="flex items-center gap-3.5 border-t border-bord-leger py-3 first:border-0">
                  <span className={cx("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", couleurs)}><Icone size={18} /></span>
                  <span className="min-w-0 flex-1">
                    <b className="block text-sm font-semibold">{a.titre}</b>
                    <span className="text-[13px] text-encre-douce">{a.detail}</span>
                  </span>
                  <Link to={lienAnomalie(a)} className="text-sm font-semibold underline">Voir</Link>
                </li>
              );
            })}
          </ul>
        </Carte>

        <Carte titre="État des terminaux" action={u.role !== "RESPONSABLE" && <Link to="/sites" className="text-sm font-semibold underline">Gérer</Link>}>
          <Tableau entetes={["Terminal", "Site", "État", <span className="block text-right">En attente</span>]} vide={!d.terminaux.length}>
            {d.terminaux.map((t) => (
              <Ligne key={t.id} onClick={u.role !== "RESPONSABLE" ? () => naviguer(`/sites?terminal=${t.id}`) : undefined}>
                <Cellule className="whitespace-nowrap font-mono text-[13px]">{t.code}</Cellule>
                <Cellule>{t.site}</Cellule>
                <Cellule><EtatTerminalPastille etat={t.etat} /></Cellule>
                <Cellule className="text-right">{t.en_attente}</Cellule>
              </Ligne>
            ))}
          </Tableau>
        </Carte>
      </div>
    </>
  );
}
