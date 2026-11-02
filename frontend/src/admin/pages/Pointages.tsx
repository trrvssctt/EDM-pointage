/** Historique des pointages (maquette « Historique des pointages ») : entrées, sorties et refus. */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, Ban, Building2, Download, Smartphone, WifiOff, X } from "lucide-react";
import { api, parametres } from "../api";
import { enOptions, useSites, useTerminaux } from "../donnees";
import type { LignePointage, Page } from "../types";
import { Avatar, Bouton, Carte, Cellule, Champ, EnTetePage, Ligne, MessageErreur, Pagination, Pastille, Selection,
  Tableau, useNotifier } from "../composants/ui";
import { dateCourte, dateIso, decalerJours, heure } from "../../commun/format";

const TAILLE = 25;
type Periode = "jour" | "hier" | "semaine" | "mois" | "perso";

function bornes(periode: Periode, du: string, au: string): [string, string] {
  const auj = new Date();
  switch (periode) {
    case "hier": { const h = dateIso(decalerJours(-1)); return [h, h]; }
    case "semaine": return [dateIso(decalerJours(-6)), dateIso(auj)];
    case "mois": return [dateIso(new Date(auj.getFullYear(), auj.getMonth(), 1)), dateIso(auj)];
    case "perso": return [du, au];
    default: return [dateIso(auj), dateIso(auj)];
  }
}

export function Pointages() {
  const notifier = useNotifier();
  const [recherche] = useSearchParams();
  const dateLien = recherche.get("date");
  const [periode, setPeriode] = useState<Periode>(dateLien && dateLien !== dateIso() ? "perso" : "jour");
  const [du, setDu] = useState(dateLien ?? dateIso());
  const [au, setAu] = useState(dateLien ?? dateIso());
  const [site, setSite] = useState("");
  const [terminal, setTerminal] = useState("");
  const [type, setType] = useState("");
  const [alerte, setAlerte] = useState(recherche.get("alerte") ?? "");
  const [q, setQ] = useState(recherche.get("q") ?? "");
  const [page, setPage] = useState(1);
  const sites = useSites();
  const terminaux = useTerminaux();
  const [debut, fin] = bornes(periode, du, au);
  const filtres = { date_debut: debut, date_fin: fin, site_id: site, terminal_id: terminal, type, alerte, q };

  useEffect(() => setPage(1), [periode, du, au, site, terminal, type, alerte, q]);
  const liste = useQuery({
    queryKey: ["pointages", filtres, page], placeholderData: (p) => p, refetchInterval: 20_000,
    queryFn: () => api.get<Page<LignePointage>>(`/api/pointages${parametres({ ...filtres, page, taille: TAILLE })}`),
  });
  const plusieursJours = debut !== fin;
  const exporter = () => api.telecharger(`/api/pointages/export.xlsx${parametres(filtres)}`).catch((e) => notifier(e.message, "danger"));

  return (
    <>
      <EnTetePage titre="Historique des pointages" sousTitre="Date, heure, site et terminal de chaque événement"
        actions={<Bouton grand icone={Download} onClick={exporter}>Exporter</Bouton>} />
      <Carte>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[1.2fr_1.2fr_1fr_1fr]">
          <Selection libelle="Période" value={periode} onChange={(e) => setPeriode(e.target.value as Periode)} options={[
            { valeur: "jour", libelle: `Aujourd’hui · ${dateCourte(new Date())}` }, { valeur: "hier", libelle: "Hier" },
            { valeur: "semaine", libelle: "7 derniers jours" }, { valeur: "mois", libelle: "Ce mois-ci" },
            { valeur: "perso", libelle: "Période personnalisée" }]} />
          <Selection libelle="Site de pointage" vide="Tous les sites" value={site} onChange={(e) => setSite(e.target.value)}
            options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
          <Selection libelle="Terminal" vide="Tous les terminaux" value={terminal} onChange={(e) => setTerminal(e.target.value)}
            options={enOptions(terminaux.data?.filter((t) => !site || t.site_id === Number(site)), (t) => t.code)} />
          <Selection libelle="Type" vide="Tous les événements" value={type} onChange={(e) => setType(e.target.value)}
            options={[{ valeur: "ENTREE", libelle: "Entrées" }, { valeur: "SORTIE", libelle: "Sorties" }, { valeur: "REFUSE", libelle: "Refusés" }]} />
        </div>
        {periode === "perso" && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:w-1/2">
            <Champ libelle="Du" type="date" value={du} max={au} onChange={(e) => setDu(e.target.value)} />
            <Champ libelle="Au" type="date" value={au} min={du} max={dateIso()} onChange={(e) => setAu(e.target.value)} />
          </div>
        )}
        <div className="mt-4 grid gap-4 md:grid-cols-[3fr_1fr]">
          <Champ libelle="Agent" placeholder="Nom ou matricule" type="search" value={q} onChange={(e) => setQ(e.target.value)} />
          <Selection libelle="Alerte" vide="Toutes" value={alerte} onChange={(e) => setAlerte(e.target.value)} options={[
            { valeur: "HORS_RATTACHEMENT", libelle: "Hors rattachement" }, { valeur: "FRAUDE", libelle: "Fraude suspectée" },
            { valeur: "DIFFERE", libelle: "Différé · hors ligne" }, { valeur: "ANNULE", libelle: "Annulé par l’agent" }]} />
        </div>

        <div className="mt-5">
          {liste.error ? <MessageErreur erreur={liste.error} /> : (
            <Tableau largeurMin={1040} entetes={[plusieursJours ? "Date et heure" : "Heure", "Agent", "Matricule", "Site de pointage", "Terminal", "Type", "Alerte", "Synchro", "Confiance"]}
              chargement={liste.isLoading} vide={liste.data?.elements.length === 0}>
              {liste.data?.elements.map((p) => (
                <Ligne key={p.id}>
                  <Cellule className="whitespace-nowrap text-[15px]">
                    {plusieursJours && <span className="block text-xs text-encre-douce">{dateCourte(p.horodatage)}</span>}
                    {heure(p.horodatage, true)}
                  </Cellule>
                  <Cellule>
                    <span className="flex items-center gap-2.5 font-semibold">
                      <Avatar initiales={p.initiales} ton={p.nature === "REFUS" && !p.matricule ? "neutre" : "info"} />
                      <span className="max-w-[150px]">{p.agent}</span>
                    </span>
                  </Cellule>
                  <Cellule className="whitespace-nowrap font-mono text-[13px]">{p.matricule ?? "–"}</Cellule>
                  <Cellule>{p.site}</Cellule>
                  <Cellule className="whitespace-nowrap font-mono text-[13px]">{p.terminal}</Cellule>
                  <Cellule>
                    <span className="flex flex-wrap gap-1">
                      {p.type === "ENTREE" ? <Pastille ton="info">Entrée</Pastille> : p.type === "SORTIE" ? <Pastille ton="info">Sortie</Pastille>
                        : <Pastille ton="danger" icone={X}>Refusé</Pastille>}
                      {p.secours && <Pastille ton="alerte" icone={Smartphone}>Secours</Pastille>}
                    </span>
                  </Cellule>
                  <Cellule><Alerte ligne={p} /></Cellule>
                  <Cellule>{p.synchro === "DIFFERE" ? <Pastille ton="alerte" icone={WifiOff}>Différé · hors ligne</Pastille> : <Pastille ton="succes">Synchronisé</Pastille>}</Cellule>
                  <Cellule className="text-right">{p.confiance !== null ? `${p.confiance} %` : ""}</Cellule>
                </Ligne>
              ))}
            </Tableau>
          )}
          {liste.data && <Pagination page={page} total={liste.data.total} taille={TAILLE} onPage={setPage}
            libelle={`${liste.data.total.toLocaleString("fr-FR")} événement${liste.data.total > 1 ? "s" : ""} · chaque événement n’est conservé qu’une seule fois`} />}
        </div>
      </Carte>
    </>
  );
}

function Alerte({ ligne }: { ligne: LignePointage }) {
  if (!ligne.alerte) return <span className="text-encre-douce">–</span>;
  if (ligne.alerte === "HORS_RATTACHEMENT") return <Pastille ton="info" icone={Building2}>Hors rattachement</Pastille>;
  if (ligne.alerte === "FRAUDE") return <Pastille ton="danger" icone={AlertTriangle}>Fraude suspectée</Pastille>;
  if (ligne.alerte === "ANNULE") return <Pastille icone={Ban}>Annulé par l’agent</Pastille>;
  return <Pastille ton={ligne.alerte === "VISAGE_INCONNU" ? "neutre" : "alerte"}>{ligne.libelle_alerte}</Pastille>;
}
