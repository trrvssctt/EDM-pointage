/** Rapports de présence, retards et absences (maquette « Rapports »), exports PDF et Excel. */
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Download, FileText } from "lucide-react";
import { api, parametres } from "../api";
import { enOptions, useServices, useSites } from "../donnees";
import type { Rapport } from "../types";
import { useSession } from "../session";
import { Logo } from "../composants/Logo";
import { Bouton, Carte, Cellule, Champ, EnTetePage, Ligne, MessageErreur, Pastille, Radio, Segments, Selection, Tableau,
  cx, useNotifier } from "../composants/ui";
import { dateCourte, dateIso, decalerJours, nombre, pourcent } from "../../commun/format";

type Type = "presence" | "retards" | "absences";
type Periode = "jour" | "hier" | "semaine" | "mois" | "mois_precedent" | "perso";

function bornes(p: Periode, du: string, au: string): [string, string] {
  const a = new Date();
  switch (p) {
    case "hier": { const h = dateIso(decalerJours(-1)); return [h, h]; }
    case "semaine": { const lundi = decalerJours(-((a.getDay() + 6) % 7)); return [dateIso(lundi), dateIso(a)]; }
    case "mois": return [dateIso(new Date(a.getFullYear(), a.getMonth(), 1)), dateIso(a)];
    case "mois_precedent": return [dateIso(new Date(a.getFullYear(), a.getMonth() - 1, 1)), dateIso(new Date(a.getFullYear(), a.getMonth(), 0))];
    case "perso": return [du, au];
    default: return [dateIso(a), dateIso(a)];
  }
}

export function Rapports() {
  const notifier = useNotifier();
  const { organisation } = useSession();
  const [recherche] = useSearchParams();
  const dateLien = recherche.get("date");
  const [type, setType] = useState<Type>("presence");
  const [periode, setPeriode] = useState<Periode>(dateLien ? "perso" : "jour");
  const [du, setDu] = useState(dateLien ?? dateIso());
  const [au, setAu] = useState(dateLien ?? dateIso());
  const [site, setSite] = useState("");
  const [service, setService] = useState("");
  const [regroupement, setRegroupement] = useState<"service" | "site" | "agent">("service");
  const sites = useSites();
  const services = useServices();
  const [debut, fin] = bornes(periode, du, au);
  // Une seule source de vérité : le rapport affiché ET les exports suivent toujours les filtres visibles.
  const filtres = { type_rapport: type, date_debut: debut, date_fin: fin, site_id: site, service_id: service, regroupement };

  const rapport = useQuery({
    queryKey: ["rapport", filtres], placeholderData: (p) => p,
    queryFn: () => api.get<Rapport>(`/api/rapports${parametres(filtres)}`),
  });
  const resultat = useRef<HTMLDivElement>(null);
  const [exportEnCours, setExportEnCours] = useState<"pdf" | "xlsx" | null>(null);
  const generer = async () => {
    const r = await rapport.refetch();  // recalcul forcé (données arrivées entre-temps)
    if (r.isSuccess) {
      notifier(`${r.data.titre} généré · ${r.data.periode}`);
      resultat.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };
  const exporter = async (format: "pdf" | "xlsx") => {
    setExportEnCours(format);
    try {
      const nom = await api.telecharger(`/api/rapports/export.${format}${parametres(filtres)}`);
      notifier(`Fichier téléchargé : ${nom}`);
    } catch (e) {
      notifier(e instanceof Error ? e.message : String(e), "danger");
    } finally {
      setExportEnCours(null);
    }
  };
  const r = rapport.data;
  const unJour = r && r.debut === r.fin;
  const libelleGroupe = { service: "Service", site: "Site", agent: "Agent" }[r?.regroupement as "service" ?? "service"] ?? "Service";

  return (
    <>
      <EnTetePage titre="Rapports" sousTitre="Présence, retards et absences par agent, service, site et période" />
      <div className="grid items-start gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Carte titre="Paramètres du rapport">
          <div className="flex flex-col gap-4">
            <Segments valeur={type} onChange={setType} options={[{ valeur: "presence", libelle: "Présence" },
              { valeur: "retards", libelle: "Retards" }, { valeur: "absences", libelle: "Absences" }]} />
            <Selection libelle="Période" value={periode} onChange={(e) => setPeriode(e.target.value as Periode)} options={[
              { valeur: "jour", libelle: `Journée du ${dateCourte(new Date())}` }, { valeur: "hier", libelle: "Journée d’hier" },
              { valeur: "semaine", libelle: "Semaine en cours" }, { valeur: "mois", libelle: "Mois en cours" },
              { valeur: "mois_precedent", libelle: "Mois précédent" }, { valeur: "perso", libelle: "Période personnalisée" }]} />
            {periode === "perso" && (
              <div className="grid grid-cols-2 gap-3">
                <Champ libelle="Du" type="date" value={du} max={au} onChange={(e) => setDu(e.target.value)} />
                <Champ libelle="Au" type="date" value={au} min={du} max={dateIso()} onChange={(e) => setAu(e.target.value)} />
              </div>
            )}
            <Selection libelle="Site" vide="Tous les sites" value={site} onChange={(e) => setSite(e.target.value)}
              options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
            <Selection libelle="Service" vide="Tous les services" value={service} onChange={(e) => setService(e.target.value)}
              options={enOptions(services.data, (s) => s.nom)} />
            <fieldset>
              <legend className="mb-1 text-[13px] font-semibold">Regrouper par</legend>
              <Radio nom="groupe" libelle="Service" coche={regroupement === "service"} onChange={() => setRegroupement("service")} />
              <Radio nom="groupe" libelle="Site" coche={regroupement === "site"} onChange={() => setRegroupement("site")} />
              <Radio nom="groupe" libelle="Agent" coche={regroupement === "agent"} onChange={() => setRegroupement("agent")} />
            </fieldset>
            <Bouton variante="primaire" grand icone={FileText} chargement={rapport.isFetching} onClick={generer}>Générer le rapport</Bouton>
          </div>
        </Carte>

        <div ref={resultat} className="scroll-mt-6">
        <Carte titre={r ? `${r.titre} · ${unJour ? r.periode.replace("Journée du ", "") : r.periode}` : "Rapport"} sousTitre={r?.perimetre}
          action={r && <div className="flex gap-2">
            <Bouton grand icone={Download} chargement={exportEnCours === "pdf"} disabled={!!exportEnCours} onClick={() => exporter("pdf")}>PDF</Bouton>
            <Bouton grand icone={Download} chargement={exportEnCours === "xlsx"} disabled={!!exportEnCours} onClick={() => exporter("xlsx")}>Excel</Bouton>
          </div>}>
          {rapport.error && <MessageErreur erreur={rapport.error} />}
          {r && (
            <>
              <div className="mb-4 flex items-center gap-3 border-b border-bord pb-4">
                <Logo taille={48} className="border border-bord" />
                <div>
                  <p className="text-[15px] font-semibold">{organisation?.nom}</p>
                  <p className="text-xs text-encre-douce">{organisation?.slogan} · rapport édité le {dateCourte(new Date())}</p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {[["Taux de présence", pourcent(r.indicateurs.taux_presence)], ["Retards", nombre(r.indicateurs.retards)],
                  ["Absences", nombre(r.indicateurs.absences)]].map(([l, v]) => (
                  <div key={l} className="rounded-[10px] border border-bord p-3.5">
                    <p className="text-xs text-encre-douce">{l}</p>
                    <p className="mt-1 text-[26px] font-semibold leading-tight">{v}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4">
                <Tableau largeurMin={620} entetes={[libelleGroupe, ...["Effectif", unJour ? "Présents" : "Présences (j)", "Dont retards",
                  unJour ? "Absents" : "Absences (j)"].map((t) => <span key={t} className="block text-right">{t}</span>), "Taux de présence"]}
                  vide={r.lignes.length === 0}>
                  {r.lignes.map((l) => (
                    <Ligne key={l.cle}>
                      <Cellule>{r.regroupement === "agent" ? <><b className="font-semibold">{l.agent}</b> <span className="font-mono text-xs text-encre-douce">{l.matricule}</span></> : l.cle}</Cellule>
                      <Cellule className="text-right">{nombre(l.effectif)}</Cellule>
                      <Cellule className="text-right">{nombre(l.presences)}</Cellule>
                      <Cellule className="text-right">{nombre(l.retards)}</Cellule>
                      <Cellule className="text-right">{nombre(l.absences)}</Cellule>
                      <Cellule><Taux valeur={l.taux_presence} /></Cellule>
                    </Ligne>
                  ))}
                  {r.lignes.length > 0 && (
                    <tr className="border-t border-bord font-semibold">
                      <Cellule>Total</Cellule>
                      <Cellule className="text-right">{nombre(r.total.effectif)}</Cellule>
                      <Cellule className="text-right">{nombre(r.total.presences)}</Cellule>
                      <Cellule className="text-right">{nombre(r.total.retards)}</Cellule>
                      <Cellule className="text-right">{nombre(r.total.absences)}</Cellule>
                      <Cellule>{pourcent(r.total.taux_presence)}</Cellule>
                    </tr>
                  )}
                </Tableau>
              </div>
              {(type !== "presence" || r.regroupement === "agent") && r.detail.length > 0 && (
                <div className="mt-6">
                  <h3 className="mb-3 text-[15px] font-semibold">
                    {type === "retards" ? "Détail des retards" : type === "absences" ? "Détail des absences" : "Détail journalier"}
                  </h3>
                  <Tableau largeurMin={860} entetes={["Date", "Agent", "Service", "Statut", "Arrivée", "Départ", "Retard", "Anomalies"]}>
                    {r.detail.slice(0, 200).map((j) => (
                      <Ligne key={j.date + j.matricule}>
                        <Cellule className="whitespace-nowrap">{dateCourte(j.date)}</Cellule>
                        <Cellule><b className="font-semibold">{j.agent}</b> <span className="font-mono text-xs text-encre-douce">{j.matricule}</span></Cellule>
                        <Cellule>{j.service}</Cellule>
                        <Cellule><Pastille ton={j.statut === "PRESENT" ? "succes" : j.statut === "RETARD" ? "alerte" : "danger"}>
                          {{ PRESENT: "Présent", RETARD: "En retard", ABSENT: "Absent" }[j.statut]}</Pastille></Cellule>
                        <Cellule>{j.premiere_entree?.slice(0, 5) ?? "–"}</Cellule>
                        <Cellule>{j.derniere_sortie?.slice(0, 5) ?? "–"}</Cellule>
                        <Cellule>{j.retard_minutes ? `${j.retard_minutes} min` : ""}</Cellule>
                        <Cellule className="text-xs text-alerte">{j.anomalies.join(" · ")}</Cellule>
                      </Ligne>
                    ))}
                  </Tableau>
                  {r.detail.length > 200 && <p className="mt-2 text-xs text-encre-douce">200 premières lignes affichées : l’export Excel contient le détail complet.</p>}
                </div>
              )}
            </>
          )}
        </Carte>
        </div>
      </div>
    </>
  );
}

function Taux({ valeur }: { valeur: number }) {
  return (
    <span className="flex items-center gap-3">
      <span className="h-2 w-16 rounded-full bg-surface-grise">
        <span className={cx("block h-full rounded-full", valeur < 85 ? "bg-alerte-barre" : "bg-primaire")} style={{ width: `${valeur}%` }} />
      </span>
      <b className="whitespace-nowrap font-semibold">{pourcent(valeur)}</b>
    </span>
  );
}
