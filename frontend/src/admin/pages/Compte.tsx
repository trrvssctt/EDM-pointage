/** Mon compte : informations, changement de mot de passe et vérification en deux étapes. */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck, Smartphone } from "lucide-react";
import { api } from "../api";
import { LIBELLES_ROLE, useSession } from "../session";
import { Avatar, Bouton, Carte, Champ, EnTetePage, Encart, MessageErreur, Pastille, useNotifier } from "../composants/ui";
import { dateRelative, initiales } from "../../commun/format";

export function Compte() {
  const { session } = useSession();
  const u = session!.utilisateur;
  const client = useQueryClient();
  const notifier = useNotifier();
  const [mdp, setMdp] = useState({ ancien: "", nouveau: "", confirmation: "" });
  const [qr, setQr] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");

  const changer = useMutation({
    mutationFn: () => {
      if (mdp.nouveau !== mdp.confirmation) throw new Error("La confirmation ne correspond pas au nouveau mot de passe");
      return api.post("/api/auth/mot-de-passe", { ancien: mdp.ancien, nouveau: mdp.nouveau });
    },
    onSuccess: () => { setMdp({ ancien: "", nouveau: "", confirmation: "" }); notifier("Mot de passe modifié"); },
  });
  const preparer = useMutation({ mutationFn: () => api.post<{ secret: string; qr_svg: string }>("/api/auth/deux-etapes/preparer"), onSuccess: setQr });
  const activer = useMutation({
    mutationFn: () => api.post("/api/auth/deux-etapes/activer", { code }),
    onSuccess: () => { setQr(null); setCode(""); client.invalidateQueries({ queryKey: ["session"] }); notifier("Vérification en deux étapes activée"); },
  });

  return (
    <>
      <EnTetePage titre="Mon compte" sousTitre="Informations de connexion et sécurité" />
      <div className="grid items-start gap-5 xl:grid-cols-3">
        <Carte titre="Profil">
          <div className="flex items-center gap-3">
            <Avatar initiales={initiales(u.nom_complet || u.identifiant)} taille={52} />
            <div><p className="text-lg font-semibold">{u.nom_complet}</p><p className="text-sm text-encre-douce">{u.fonction}</p></div>
          </div>
          <dl className="mt-4 divide-y divide-bord-leger text-[15px]">
            {[["Identifiant", u.identifiant], ["E-mail", u.email ?? "—"], ["Profil", LIBELLES_ROLE[u.role]], ["Périmètre", u.perimetre],
              ["Dernière connexion", dateRelative(u.derniere_connexion)]].map(([l, x]) => (
              <div key={l} className="flex justify-between gap-3 py-2.5"><dt className="text-encre-douce">{l}</dt><dd className="text-right font-medium">{x}</dd></div>
            ))}
          </dl>
        </Carte>

        <Carte titre="Changer le mot de passe">
          <div className="flex flex-col gap-4">
            <Champ libelle="Mot de passe actuel" type="password" autoComplete="current-password" value={mdp.ancien} onChange={(e) => setMdp({ ...mdp, ancien: e.target.value })} />
            <Champ libelle="Nouveau mot de passe" type="password" autoComplete="new-password" aide="8 caractères minimum, avec des lettres et des chiffres"
              value={mdp.nouveau} onChange={(e) => setMdp({ ...mdp, nouveau: e.target.value })} />
            <Champ libelle="Confirmation" type="password" autoComplete="new-password" value={mdp.confirmation} onChange={(e) => setMdp({ ...mdp, confirmation: e.target.value })} />
            {changer.error && <MessageErreur erreur={changer.error} />}
            <Bouton variante="primaire" grand icone={KeyRound} chargement={changer.isPending} onClick={() => changer.mutate()}>Modifier le mot de passe</Bouton>
          </div>
        </Carte>

        <Carte titre="Vérification en deux étapes" action={u.deux_etapes ? <Pastille ton="succes" icone={ShieldCheck}>Activée</Pastille> : <Pastille>Désactivée</Pastille>}>
          {u.deux_etapes && !qr ? (
            <Encart icone={ShieldCheck}>Un code à 6 chiffres de votre application d’authentification vous est demandé à chaque connexion.
              En cas de perte du téléphone, demandez à un administrateur de la réinitialiser.</Encart>
          ) : qr ? (
            <div className="flex flex-col gap-4">
              <p className="text-sm">Scannez ce code avec Google Authenticator, Microsoft Authenticator ou FreeOTP, puis saisissez le code affiché.</p>
              <div className="mx-auto rounded-xl border border-bord bg-white p-2" dangerouslySetInnerHTML={{ __html: qr.qr_svg }} />
              <p className="break-all text-center font-mono text-xs text-encre-douce">Clé manuelle : {qr.secret}</p>
              <Champ libelle="Code de vérification" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
              {activer.error && <MessageErreur erreur={activer.error} />}
              <Bouton variante="primaire" grand chargement={activer.isPending} disabled={code.length !== 6} onClick={() => activer.mutate()}>Activer</Bouton>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-encre-douce">Protégez votre compte avec un code temporaire généré par votre téléphone, en plus du mot de passe.</p>
              <Bouton grand icone={Smartphone} chargement={preparer.isPending} onClick={() => preparer.mutate()}>Configurer</Bouton>
            </div>
          )}
        </Carte>
      </div>
    </>
  );
}
