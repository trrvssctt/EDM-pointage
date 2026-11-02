/** Liste des agents (maquette « Agents ») et fiche agent (création, modification, désactivation). */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Check, Plus, ScanFace, ShieldCheck, Trash2 } from "lucide-react";
import { api, parametres } from "../api";
import { enOptions, useHoraires, useServices, useSites } from "../donnees";
import { useSession } from "../session";
import type { Agent, Page } from "../types";
import { Avatar, Bouton, CaseACocher, Carte, Cellule, Champ, EnTetePage, Encart, Ligne, MessageErreur, Modale, Pagination,
  Pastille, Radio, Selection, Tableau, useNotifier } from "../composants/ui";
import { dateCourte, initiales } from "../../commun/format";

const TAILLE = 8;

export function Agents() {
  const { peut } = useSession();
  const naviguer = useNavigate();
  const [recherche] = useSearchParams();
  const [q, setQ] = useState("");
  const [service, setService] = useState("");
  const [site, setSite] = useState("");
  const [statut, setStatut] = useState("");
  const [page, setPage] = useState(1);
  const [fiche, setFiche] = useState<Agent | "nouveau" | null>(null);
  const services = useServices();
  const sites = useSites();

  useEffect(() => setPage(1), [q, service, site, statut]);
  const liste = useQuery({
    queryKey: ["agents", q, service, site, statut, page],
    placeholderData: (precedent) => precedent,
    queryFn: () => api.get<Page<Agent>>(`/api/agents${parametres({
      q, service_id: service, site_id: site, page, taille: TAILLE,
      actif: statut === "actif" ? true : statut === "desactive" ? false : "",
      enrole: statut === "a_enroler" ? false : "" })}`),
  });
  useEffect(() => {
    const id = recherche.get("agent");
    if (id) api.get<Agent>(`/api/agents/${id}`).then(setFiche).catch(() => {});
  }, [recherche]);

  return (
    <>
      <EnTetePage titre="Agents" sousTitre="Dossiers des agents, matricule unique, service et site de rattachement"
        actions={peut("agents.gerer") && <Bouton variante="primaire" grand icone={Plus} onClick={() => setFiche("nouveau")}>Nouvel agent</Bouton>} />
      <Carte>
        <Champ libelle="Rechercher" placeholder="Nom ou matricule" value={q} onChange={(e) => setQ(e.target.value)} type="search" />
        <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr_0.85fr]">
          <Selection libelle="Service" vide="Tous les services" value={service} onChange={(e) => setService(e.target.value)}
            options={enOptions(services.data, (s) => s.nom)} />
          <Selection libelle="Site de rattachement" vide="Tous les sites" value={site} onChange={(e) => setSite(e.target.value)}
            options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
          <Selection libelle="Statut" vide="Tous" value={statut} onChange={(e) => setStatut(e.target.value)}
            options={[{ valeur: "actif", libelle: "Actifs" }, { valeur: "desactive", libelle: "Désactivés" },
              { valeur: "a_enroler", libelle: "À enrôler" }]} />
        </div>
        <div className="mt-5">
          {liste.error ? <MessageErreur erreur={liste.error} /> : (
            <Tableau largeurMin={860} entetes={["Agent", "Matricule", "Service", "Site de rattachement", "Visage", "Statut", ""]}
              chargement={liste.isLoading} vide={liste.data?.elements.length === 0}>
              {liste.data?.elements.map((a) => (
                <Ligne key={a.id}>
                  <Cellule>
                    <span className="flex items-center gap-2.5 font-semibold">
                      <Avatar initiales={initiales(a.nom_complet)} /> {a.nom_complet}
                    </span>
                  </Cellule>
                  <Cellule className="whitespace-nowrap font-mono text-[13px]">{a.matricule}</Cellule>
                  <Cellule>{a.service_nom}</Cellule>
                  <Cellule>{a.site_rattachement_nom}</Cellule>
                  <Cellule>{a.nb_gabarits ? <Pastille ton="succes" icone={Check}>Visage enrôlé</Pastille> : <Pastille ton="alerte">À enrôler</Pastille>}</Cellule>
                  <Cellule>{a.actif ? <Pastille ton="succes">Actif</Pastille> : <Pastille>Désactivé</Pastille>}</Cellule>
                  <Cellule className="text-right">
                    {!a.nb_gabarits && a.actif && peut("biometrie.enroler")
                      ? <button type="button" className="font-semibold text-primaire underline" onClick={() => naviguer(`/enrolement?agent=${a.id}`)}>Enrôler</button>
                      : <button type="button" className="font-semibold text-primaire underline" onClick={() => setFiche(a)}>Ouvrir</button>}
                  </Cellule>
                </Ligne>
              ))}
            </Tableau>
          )}
          {liste.data && <Pagination page={page} taille={TAILLE} total={liste.data.total} onPage={setPage}
            libelle={`${liste.data.total ? (page - 1) * TAILLE + 1 : 0} à ${Math.min(page * TAILLE, liste.data.total)} sur ${liste.data.total.toLocaleString("fr-FR")} agents`} />}
        </div>
      </Carte>
      {fiche && <FicheAgent agent={fiche === "nouveau" ? null : fiche} onFermer={() => setFiche(null)} />}
    </>
  );
}

function FicheAgent({ agent, onFermer }: { agent: Agent | null; onFermer: () => void }) {
  const { peut, organisation } = useSession();
  const client = useQueryClient();
  const notifier = useNotifier();
  const naviguer = useNavigate();
  const services = useServices();
  const sites = useSites();
  const horaires = useHoraires();
  const modifiable = peut("agents.gerer");
  const [v, setV] = useState({
    matricule: agent?.matricule ?? organisation?.prefixe_matricule ?? "", nom: agent?.nom ?? "", prenom: agent?.prenom ?? "",
    fonction: agent?.fonction ?? "", email: agent?.email ?? "", telephone: agent?.telephone ?? "",
    service_id: agent?.service_id ?? "", site_rattachement_id: agent?.site_rattachement_id ?? "", horaire_id: agent?.horaire_id ?? "",
    tous_sites: agent?.tous_sites ?? true, sites_autorises: agent?.sites_autorises ?? [] as number[], actif: agent?.actif ?? true,
  });
  const maj = (champ: string, valeur: unknown) => setV((x) => ({ ...x, [champ]: valeur }));
  useEffect(() => {  // valeurs par défaut des listes à la création
    if (!agent) setV((x) => ({ ...x, service_id: x.service_id || services.data?.[0]?.id || "", site_rattachement_id:
      x.site_rattachement_id || sites.data?.[0]?.id || "", horaire_id: x.horaire_id || horaires.data?.[0]?.id || "" }));
  }, [agent, services.data, sites.data, horaires.data]);

  const enregistrer = useMutation({
    mutationFn: () => {
      const corps = { ...v, service_id: Number(v.service_id), site_rattachement_id: Number(v.site_rattachement_id),
        horaire_id: Number(v.horaire_id) };
      if (agent) {
        const { matricule: _, ...modif } = corps;
        return api.put<Agent>(`/api/agents/${agent.id}`, modif);
      }
      const { actif: _, ...creation } = corps;
      return api.post<Agent>("/api/agents", creation);
    },
    onSuccess: (a) => {
      client.invalidateQueries({ queryKey: ["agents"] });
      notifier(agent ? "Dossier de l’agent enregistré" : `Agent ${a.matricule} créé`);
      if (!agent && peut("biometrie.enroler")) naviguer(`/enrolement?agent=${a.id}`);
      onFermer();
    },
  });
  const supprimerBiometrie = useMutation({
    mutationFn: () => api.delete<{ message: string }>(`/api/agents/${agent!.id}/gabarits`),
    onSuccess: (r) => { client.invalidateQueries({ queryKey: ["agents"] }); notifier(r.message); onFermer(); },
  });

  const basculerSite = (id: number) => maj("sites_autorises",
    v.sites_autorises.includes(id) ? v.sites_autorises.filter((s) => s !== id) : [...v.sites_autorises, id]);

  return (
    <Modale large titre={agent ? agent.nom_complet : "Nouvel agent"} onFermer={onFermer}
      sousTitre={agent ? `${agent.matricule} · dossier créé le ${dateCourte(agent.cree_le)}` : "Le matricule doit être unique"}
      actions={modifiable && <>
        <Bouton onClick={onFermer}>Annuler</Bouton>
        <Bouton variante="primaire" chargement={enregistrer.isPending} onClick={() => enregistrer.mutate()}>
          {agent ? "Enregistrer" : "Créer et enrôler"}
        </Bouton>
      </>}>
      <fieldset disabled={!modifiable} className="grid gap-4 sm:grid-cols-2">
        <Champ libelle="Matricule" value={v.matricule} disabled={!!agent} onChange={(e) => maj("matricule", e.target.value.toUpperCase())} />
        <Champ libelle="Fonction" value={v.fonction} onChange={(e) => maj("fonction", e.target.value)} />
        <Champ libelle="Prénom" value={v.prenom} onChange={(e) => maj("prenom", e.target.value)} />
        <Champ libelle="Nom" value={v.nom} onChange={(e) => maj("nom", e.target.value)} />
        <Champ libelle="Adresse e-mail" type="email" value={v.email} onChange={(e) => maj("email", e.target.value)} />
        <Champ libelle="Téléphone" value={v.telephone} onChange={(e) => maj("telephone", e.target.value)} />
        <Selection libelle="Service" value={v.service_id} onChange={(e) => maj("service_id", e.target.value)} options={enOptions(services.data, (s) => s.nom)} />
        <Selection libelle="Site de rattachement" value={v.site_rattachement_id} onChange={(e) => maj("site_rattachement_id", e.target.value)}
          options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
        <Selection libelle="Horaire de travail" className="sm:col-span-2" value={v.horaire_id} onChange={(e) => maj("horaire_id", e.target.value)}
          options={enOptions(horaires.data, (h) => h.nom)} />
        <div className="sm:col-span-2">
          <p className="mb-1 text-[13px] font-semibold">Sites de pointage autorisés</p>
          <Radio nom="sites" libelle="Tous les sites équipés" coche={v.tous_sites} onChange={() => maj("tous_sites", true)} />
          <Radio nom="sites" libelle="Sélection de sites" coche={!v.tous_sites} onChange={() => maj("tous_sites", false)} />
          {!v.tous_sites && (
            <div className="mt-2 grid gap-2 rounded-[10px] border border-bord p-3 sm:grid-cols-2">
              {sites.data?.map((s) => (
                <CaseACocher key={s.id} libelle={s.nom_court || s.nom}
                  coche={v.sites_autorises.includes(s.id) || s.id === Number(v.site_rattachement_id)}
                  disabled={s.id === Number(v.site_rattachement_id)} onChange={() => basculerSite(s.id)} />
              ))}
            </div>
          )}
        </div>
        {agent && <div className="sm:col-span-2"><CaseACocher libelle="Agent actif (décocher pour désactiver le dossier : il ne pourra plus pointer)"
          coche={v.actif} onChange={(x) => maj("actif", x)} /></div>}
      </fieldset>

      {agent && (
        <div className="mt-5 flex flex-col gap-3 border-t border-bord pt-5">
          <p className="text-[13px] font-semibold">Données biométriques</p>
          {agent.nb_gabarits ? (
            <Encart icone={ShieldCheck}>
              {agent.nb_gabarits} gabarits chiffrés enregistrés
              {agent.consentement_le && ` · consentement recueilli le ${dateCourte(agent.consentement_le)}`}. Aucune photo n’est conservée.
            </Encart>
          ) : <Encart ton="alerte">Visage non enrôlé : l’agent ne peut pas encore pointer.</Encart>}
          <div className="flex flex-wrap gap-3">
            {peut("biometrie.enroler") && agent.actif && (
              <Bouton icone={ScanFace} onClick={() => naviguer(`/enrolement?agent=${agent.id}`)}>
                {agent.nb_gabarits ? "Refaire l’enrôlement" : "Enrôler le visage"}
              </Bouton>
            )}
            {peut("biometrie.supprimer") && agent.nb_gabarits > 0 && (
              <Bouton variante="danger" icone={Trash2} chargement={supprimerBiometrie.isPending}
                onClick={() => confirm("Supprimer définitivement le gabarit biométrique de cet agent ?") && supprimerBiometrie.mutate()}>
                Supprimer le gabarit biométrique
              </Bouton>
            )}
          </div>
        </div>
      )}
      {(enregistrer.error || supprimerBiometrie.error) && (
        <div className="mt-4"><MessageErreur erreur={enregistrer.error ?? supprimerBiometrie.error} /></div>
      )}
    </Modale>
  );
}
