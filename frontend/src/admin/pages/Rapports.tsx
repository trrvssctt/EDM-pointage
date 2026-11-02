/** Rapports de présence, retards et absences (maquette « Rapports »), exports PDF et Excel. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Download, FileText } from "lucide-react";
import { api, parametres } from "../api";
import { enOptions, useServices, useSites } from "../donnees";
import type { Rapport } from "../types";
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
  const [recherche] = useSearchParams();
  const dateLien = recherche.get("date");
  const [type, setType] = useState<Type>("presence");
  const [periode, setPeriode] = useState<Periode>(dateLien ? "perso" : "jour");
  const [du, setDu] = useState(dateLien ?? dateIso());
  const [au, setAu] = useState(dateLien ?? dateIso());
  const [site, setSite] = useState("");
  const [service, setService] = useState("");
  const [regroupement, setRegroupement] = useState<"service" | "site" | "agent">("service");
  const [demande, setDemande] = useState(0);
  const sites = useSites();
  const services = useServices();
  const [debut, fin] = bornes(periode, du, au);
  const filtres = { type_rapport: type, date_debut: debut, date_fin: fin, site_id: site, service_id: service, regroupement };
  const [actifs, setActifs] = useState(filtres);

  const rapport = useQuery({
    queryKey: ["rapport", actifs, demande], placeholderData: (p) => p,
    queryFn: () => api.get<Rapport>(`/api/rapports${parametres(actifs)}`),
  });
  const generer = () => { setActifs(filtres); setDemande((n) => n + 1); };
  const exporter = (format: "pdf" | "xlsx") =>
    api.telecharger(`/api/rapports/export.${format}${parametres(actifs)}`).catch((e) => notifier(e.message, "danger"));
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

        <Carte titre={r ? `${r.titre} · ${unJour ? r.periode.replace("Journée du ", "") : r.periode}` : "Rapport"} sousTitre={r?.perimetre}
          action={r && <div className="flex gap-2">
            <Bouton grand icone={Download} onClick={() => exporter("pdf")}>PDF</Bouton>
            <Bouton grand icone={Download} onClick={() => exporter("xlsx")}>Excel</Bouton>
          </div>}>
          {rapport.error && <MessageErreur erreur={rapport.error} />}
          {r && (
            <>
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
              {(actifs.type_rapport !== "presence" || r.regroupement === "agent") && r.detail.length > 0 && (
                <div className="mt-6">
                  <h3 className="mb-3 text-[15px] font-semibold">
                    {actifs.type_rapport === "retards" ? "Détail des retards" : actifs.type_rapport === "absences" ? "Détail des absences" : "Détail journalier"}
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
