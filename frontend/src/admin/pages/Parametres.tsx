/** Paramètres de l'organisation : identité visuelle (marque blanche) et politique de sécurité. */
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Palette, Save, ShieldCheck, Upload } from "lucide-react";
import { api } from "../api";
import { useSession } from "../session";
import type { Organisation } from "../types";
import { Bouton, CaseACocher, Carte, Champ, EnTetePage, Encart, MessageErreur, useNotifier } from "../composants/ui";
import { Logo } from "../composants/Logo";
import { appliquerMarque } from "../../commun/marque";

export function Parametres() {
  const { organisation } = useSession();
  const client = useQueryClient();
  const notifier = useNotifier();
  const [v, setV] = useState<Organisation | null>(organisation);
  const [versionLogo, setVersionLogo] = useState(Date.now());
  useEffect(() => { if (organisation && !v) setV(organisation); }, [organisation, v]);
  useEffect(() => { if (v) appliquerMarque(v.couleur_primaire, v.couleur_menu); }, [v]);
  useEffect(() => () => { if (organisation) appliquerMarque(organisation.couleur_primaire, organisation.couleur_menu); }, [organisation]);

  const enregistrer = useMutation({
    mutationFn: () => api.put<Organisation>("/api/organisation", { nom: v!.nom, sigle: v!.sigle, slogan: v!.slogan,
      couleur_primaire: v!.couleur_primaire, couleur_menu: v!.couleur_menu, prefixe_matricule: v!.prefixe_matricule,
      deux_etapes_obligatoire_admin: v!.deux_etapes_obligatoire_admin, duree_conservation_jours: v!.duree_conservation_jours }),
    onSuccess: (o) => { client.setQueryData(["organisation"], o); notifier("Paramètres enregistrés. Les terminaux appliqueront la nouvelle identité à leur prochaine synchronisation."); },
  });
  const logo = useMutation({
    mutationFn: (image: string) => api.post<Organisation>("/api/organisation/logo", { image }),
    onSuccess: (o) => { client.setQueryData(["organisation"], o); setVersionLogo(Date.now()); notifier("Logo mis à jour"); },
    onError: (e) => notifier(e.message, "danger"),
  });
  const choisirLogo = (fichier?: File) => {
    if (!fichier) return;
    const lecteur = new FileReader();
    lecteur.onload = () => logo.mutate(String(lecteur.result));
    lecteur.readAsDataURL(fichier);
  };
  if (!v) return null;

  return (
    <>
      <EnTetePage titre="Paramètres" sousTitre="Identité de l’organisation, affichée sur l’administration, les terminaux et les rapports"
        actions={<Bouton variante="primaire" grand icone={Save} chargement={enregistrer.isPending} onClick={() => enregistrer.mutate()}>Enregistrer</Bouton>} />
      {enregistrer.error && <div className="mb-4"><MessageErreur erreur={enregistrer.error} /></div>}
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Carte titre="Identité de l’organisation" sousTitre="La solution peut être déployée pour toute entreprise sous sa propre marque">
          <div className="flex items-center gap-4 border-b border-bord pb-5">
            <Logo taille={72} source={`/api/organisation/logo?v=${versionLogo}`} className="border border-bord" />
            <div className="flex flex-col gap-2">
              <label className="inline-flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg border border-bord-champ px-4 text-sm font-semibold hover:bg-surface">
                <Upload size={18} /> Changer le logo
                <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="sr-only" onChange={(e) => choisirLogo(e.target.files?.[0])} />
              </label>
              <span className="text-xs text-encre-douce">PNG, JPEG, SVG ou WebP · 500 Ko maximum · format carré conseillé</span>
            </div>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Champ libelle="Raison sociale" value={v.nom} onChange={(e) => setV({ ...v, nom: e.target.value })} />
            <Champ libelle="Sigle" value={v.sigle} onChange={(e) => setV({ ...v, sigle: e.target.value })} />
            <Champ libelle="Sous-titre de l’application" value={v.slogan} onChange={(e) => setV({ ...v, slogan: e.target.value })} />
            <Champ libelle="Préfixe des matricules" value={v.prefixe_matricule} onChange={(e) => setV({ ...v, prefixe_matricule: e.target.value })} />
          </div>
        </Carte>

        <div className="flex flex-col gap-5">
          <Carte titre="Couleurs" sousTitre="Aperçu immédiat ; enregistrez pour appliquer à tous les utilisateurs">
            <div className="grid gap-4 sm:grid-cols-2">
              {([["couleur_primaire", "Couleur principale (boutons, liens)"], ["couleur_menu", "Couleur du menu et des en-têtes"]] as const).map(([cle, libelle]) => (
                <label key={cle} className="flex flex-col gap-1.5">
                  <span className="text-[13px] font-semibold">{libelle}</span>
                  <span className="flex items-center gap-3 rounded-lg border border-bord-champ p-1.5 pr-3">
                    <input type="color" value={v[cle]} onChange={(e) => setV({ ...v, [cle]: e.target.value.toUpperCase() })} className="h-9 w-12 cursor-pointer rounded border-0" />
                    <span className="font-mono text-sm">{v[cle]}</span>
                  </span>
                </label>
              ))}
            </div>
            <div className="mt-4"><Encart icone={Palette}>Choisissez des couleurs foncées : le texte blanc des boutons et du menu doit rester lisible.</Encart></div>
          </Carte>
          <Carte titre="Politique de sécurité et de conservation">
            <CaseACocher coche={v.deux_etapes_obligatoire_admin} onChange={(x) => setV({ ...v, deux_etapes_obligatoire_admin: x })}
              libelle="Exiger la vérification en deux étapes pour les administrateurs" />
            <Champ className="mt-4" libelle="Durée de conservation des pointages (jours)" type="number" min={30} max={3650}
              value={v.duree_conservation_jours} onChange={(e) => setV({ ...v, duree_conservation_jours: Number(e.target.value) })}
              aide="Au-delà, les pointages, tentatives et journaux sont purgés automatiquement (protection des données personnelles)." />
            <div className="mt-4"><Encart icone={ShieldCheck}>Les gabarits biométriques sont chiffrés (AES) et supprimés dès qu’un administrateur ou la DRH retire l’agent du dispositif.</Encart></div>
          </Carte>
        </div>
      </div>
    </>
  );
}
