/** Utilisateurs et droits (maquette « Utilisateurs et droits ») + journal d'audit. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, KeyRound, Plus, X } from "lucide-react";
import { api, parametres } from "../api";
import { enOptions, useServices, useSites } from "../donnees";
import { LIBELLES_ROLE, useSession } from "../session";
import type { Role, Utilisateur, ValeurDroit } from "../types";
import { Avatar, Bouton, CaseACocher, Carte, Cellule, Champ, EnTetePage, Ligne, MessageErreur, Modale, Pastille,
  Selection, Tableau, useNotifier } from "../composants/ui";
import { dateRelative, initiales, lireDate } from "../../commun/format";

interface Droit { code: string; libelle: string; ADMIN: ValeurDroit; DRH: ValeurDroit; RESPONSABLE: ValeurDroit }

export function Utilisateurs() {
  const { peut } = useSession();
  const admin = peut("utilisateurs.gerer");
  const [fiche, setFiche] = useState<Utilisateur | "nouveau" | null>(null);
  const utilisateurs = useQuery({ queryKey: ["utilisateurs"], queryFn: () => api.get<Utilisateur[]>("/api/utilisateurs") });
  const droits = useQuery({ queryKey: ["droits"], queryFn: () => api.get<Droit[]>("/api/droits") });

  return (
    <>
      <EnTetePage titre="Utilisateurs et droits" sousTitre="Profils d’accès : administrateur, Direction des RH, responsables habilités" />
      <Carte titre="Utilisateurs" action={admin && <Bouton variante="primaire" grand icone={Plus} onClick={() => setFiche("nouveau")}>Nouvel utilisateur</Bouton>}>
        {utilisateurs.error ? <MessageErreur erreur={utilisateurs.error} /> : (
          <Tableau largeurMin={760} entetes={["Utilisateur", "Profil", "Périmètre", "Dernière connexion", "Statut"]} chargement={utilisateurs.isLoading}>
            {utilisateurs.data?.map((u) => (
              <Ligne key={u.id} onClick={admin ? () => setFiche(u) : undefined}>
                <Cellule>
                  <span className="flex items-center gap-2.5 font-semibold">
                    <Avatar initiales={initiales(u.nom_complet || u.identifiant)} />
                    <span>{u.nom_complet || u.identifiant}<span className="block text-xs font-normal text-encre-douce">{u.identifiant}</span></span>
                  </span>
                </Cellule>
                <Cellule>{LIBELLES_ROLE[u.role]}</Cellule>
                <Cellule>{u.perimetre}</Cellule>
                <Cellule>{dateRelative(u.derniere_connexion)}</Cellule>
                <Cellule>
                  <span className="flex flex-wrap gap-1.5">
                    {u.actif ? <Pastille ton="succes">Actif</Pastille> : <Pastille>Désactivé</Pastille>}
                    {u.reinitialisation_demandee && <Pastille ton="alerte" icone={KeyRound}>Mot de passe oublié</Pastille>}
                    {u.deux_etapes && <Pastille ton="info">2 étapes</Pastille>}
                  </span>
                </Cellule>
              </Ligne>
            ))}
          </Tableau>
        )}
      </Carte>

      <Carte className="mt-6" titre="Droits par profil" sousTitre="Le profil « Responsable habilité » ne voit que son service ou son site.">
        <Tableau largeurMin={640} entetes={["Droit", "Administrateur", "Direction des RH", "Responsable habilité"]} chargement={droits.isLoading}>
          {droits.data?.map((d) => (
            <Ligne key={d.code}>
              <Cellule>{d.libelle}</Cellule>
              {(["ADMIN", "DRH", "RESPONSABLE"] as Role[]).map((r) => <Cellule key={r}><ValeurDroitCellule valeur={d[r]} /></Cellule>)}
            </Ligne>
          ))}
        </Tableau>
      </Carte>

      {peut("audit.consulter") && <JournalAudit />}
      {fiche && <FicheUtilisateur utilisateur={fiche === "nouveau" ? null : fiche} onFermer={() => setFiche(null)} />}
    </>
  );
}

function ValeurDroitCellule({ valeur }: { valeur: ValeurDroit }) {
  if (valeur === "oui") return <span className="inline-flex items-center gap-1.5 font-semibold text-succes"><Check size={16} /> Oui</span>;
  if (valeur === "perimetre") return <span className="inline-flex items-center gap-1.5 font-semibold text-alerte"><Building2 size={16} /> Son périmètre</span>;
  return <span className="inline-flex items-center gap-1.5 text-encre-douce"><X size={16} /> Non</span>;
}

function FicheUtilisateur({ utilisateur: u, onFermer }: { utilisateur: Utilisateur | null; onFermer: () => void }) {
  const client = useQueryClient();
  const notifier = useNotifier();
  const services = useServices();
  const sites = useSites();
  const [v, setV] = useState({
    identifiant: u?.identifiant ?? "", email: u?.email ?? "", nom_complet: u?.nom_complet ?? "", fonction: u?.fonction ?? "",
    role: u?.role ?? "DRH" as Role, service_id: u?.service_id ?? "", site_id: u?.site_id ?? "", actif: u?.actif ?? true,
    mot_de_passe: "", desactiver_deux_etapes: false,
  });
  const enregistrer = useMutation({
    mutationFn: () => {
      const corps = { ...v, service_id: v.service_id ? Number(v.service_id) : null, site_id: v.site_id ? Number(v.site_id) : null };
      if (u) {
        const { identifiant: _, mot_de_passe, ...modif } = corps;
        return api.put(`/api/utilisateurs/${u.id}`, mot_de_passe ? { ...modif, mot_de_passe } : modif);
      }
      const { actif: _a, desactiver_deux_etapes: _d, ...creation } = corps;
      return api.post("/api/utilisateurs", creation);
    },
    onSuccess: () => { client.invalidateQueries({ queryKey: ["utilisateurs"] }); notifier("Utilisateur enregistré"); onFermer(); },
  });
  return (
    <Modale large titre={u ? u.nom_complet || u.identifiant : "Nouvel utilisateur"} onFermer={onFermer}
      sousTitre={u ? `Dernière connexion : ${dateRelative(u.derniere_connexion)}` : "Le mot de passe sera communiqué à l’utilisateur, qui pourra le changer"}
      actions={<><Bouton onClick={onFermer}>Annuler</Bouton><Bouton variante="primaire" chargement={enregistrer.isPending} onClick={() => enregistrer.mutate()}>Enregistrer</Bouton></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Champ libelle="Identifiant (ou matricule)" value={v.identifiant} disabled={!!u} onChange={(e) => setV({ ...v, identifiant: e.target.value })} />
        <Champ libelle="Adresse e-mail" type="email" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        <Champ libelle="Nom complet" value={v.nom_complet} onChange={(e) => setV({ ...v, nom_complet: e.target.value })} />
        <Champ libelle="Fonction" value={v.fonction} onChange={(e) => setV({ ...v, fonction: e.target.value })} />
        <Selection libelle="Profil" className="sm:col-span-2" value={v.role} onChange={(e) => setV({ ...v, role: e.target.value as Role })}
          options={Object.entries(LIBELLES_ROLE).map(([valeur, libelle]) => ({ valeur, libelle }))} />
        {v.role === "RESPONSABLE" && <>
          <Selection libelle="Périmètre : service" vide="Tous les services" value={v.service_id} onChange={(e) => setV({ ...v, service_id: e.target.value })}
            options={enOptions(services.data, (s) => s.nom)} />
          <Selection libelle="Périmètre : site" vide="Tous les sites" value={v.site_id} onChange={(e) => setV({ ...v, site_id: e.target.value })}
            options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
        </>}
        <Champ libelle={u ? "Nouveau mot de passe (laisser vide pour conserver)" : "Mot de passe initial"} type="password" autoComplete="new-password"
          className="sm:col-span-2" aide="8 caractères minimum, avec des lettres et des chiffres" value={v.mot_de_passe}
          onChange={(e) => setV({ ...v, mot_de_passe: e.target.value })} />
        {u && <div className="flex flex-col gap-2 sm:col-span-2">
          <CaseACocher libelle="Compte actif" coche={v.actif} onChange={(x) => setV({ ...v, actif: x })} />
          {u.deux_etapes && <CaseACocher libelle="Réinitialiser la vérification en deux étapes (téléphone perdu)"
            coche={v.desactiver_deux_etapes} onChange={(x) => setV({ ...v, desactiver_deux_etapes: x })} />}
        </div>}
      </div>
      {enregistrer.error && <div className="mt-4"><MessageErreur erreur={enregistrer.error} /></div>}
    </Modale>
  );
}

interface EntreeAudit { date: string; acteur: string; action: string; details: string; adresse_ip: string }

function JournalAudit() {
  const [acteur, setActeur] = useState("");
  const journal = useQuery({ queryKey: ["audit", acteur], placeholderData: (p) => p,
    queryFn: () => api.get<EntreeAudit[]>(`/api/audit${parametres({ acteur, limite: 100 })}`) });
  return (
    <Carte className="mt-6" titre="Journal d’audit" sousTitre="Connexions, enrôlements, modifications et exports : 100 dernières actions"
      action={<Champ placeholder="Filtrer par utilisateur" value={acteur} onChange={(e) => setActeur(e.target.value)} type="search" />}>
      <Tableau largeurMin={760} entetes={["Date", "Utilisateur", "Action", "Détails", "Adresse IP"]} chargement={journal.isLoading} vide={journal.data?.length === 0}>
        {journal.data?.map((l, i) => (
          <Ligne key={i}>
            <Cellule className="whitespace-nowrap">{lireDate(l.date).toLocaleString("fr-FR")}</Cellule>
            <Cellule>{l.acteur}</Cellule>
            <Cellule><Pastille ton={l.action.startsWith("ECHEC") ? "danger" : "info"}>{l.action.replace(/_/g, " ").toLowerCase()}</Pastille></Cellule>
            <Cellule className="max-w-[340px] text-[13px] text-encre-douce">{l.details}</Cellule>
            <Cellule className="font-mono text-xs">{l.adresse_ip}</Cellule>
          </Ligne>
        ))}
      </Tableau>
    </Carte>
  );
}
