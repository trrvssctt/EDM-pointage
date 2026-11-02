/** Écran de connexion (maquette « Connexion »), vérification en deux étapes et mot de passe oublié. */
import { useState, type FormEvent } from "react";
import { Check, KeyRound, Lock } from "lucide-react";
import { api } from "../api";
import { useSession } from "../session";
import { Logo } from "../composants/Logo";
import { Bouton, CaseACocher, Champ, Encart, MessageErreur } from "../composants/ui";

interface Reponse { jeton?: string; deux_etapes_requise?: boolean; jeton_temporaire?: string }

const ATOUTS = [
  ["Pointage multisite", "Un agent pointe sur n’importe quel site autorisé, sans nouvel enrôlement."],
  ["Continuité de service", "Les terminaux enregistrent localement en cas de coupure réseau."],
  ["Accès selon les habilitations", "Chaque profil ne voit que ce que son rôle autorise."],
];

export function Connexion() {
  const { ouvrir, organisation } = useSession();
  const [etape, setEtape] = useState<"identifiants" | "code" | "oubli">("identifiants");
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [resterConnecte, setResterConnecte] = useState(false);
  const [code, setCode] = useState("");
  const [temporaire, setTemporaire] = useState("");
  const [erreur, setErreur] = useState<unknown>(null);
  const [info, setInfo] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const soumettre = async (e: FormEvent) => {
    e.preventDefault();
    setErreur(null);
    setEnvoi(true);
    try {
      if (etape === "identifiants") {
        const r = await api.post<Reponse>("/api/auth/connexion",
          { identifiant, mot_de_passe: motDePasse, rester_connecte: resterConnecte });
        if (r.deux_etapes_requise) {
          setTemporaire(r.jeton_temporaire!);
          setEtape("code");
        } else ouvrir(r.jeton!, resterConnecte);
      } else if (etape === "code") {
        const r = await api.post<Reponse>("/api/auth/deux-etapes", { jeton_temporaire: temporaire, code });
        ouvrir(r.jeton!, resterConnecte);
      } else {
        const r = await api.post<{ message: string }>("/api/auth/mot-de-passe-oublie", { identifiant });
        setInfo(r.message);
        setEtape("identifiants");
      }
    } catch (err) {
      setErreur(err);
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <section className="flex flex-col justify-center bg-menu px-8 py-10 text-white lg:w-[52.8%] lg:px-16">
        <div className="max-w-[470px]">
          <Logo taille={96} className="rounded-2xl" />
          <h1 className="mt-8 text-[30px] font-semibold leading-tight sm:text-[38px]">{organisation?.slogan ?? "Gestion des présences"}</h1>
          <p className="mt-3 text-lg text-menu-texte">
            Pointage biométrique par reconnaissance faciale pour tous les sites {organisation ? `d’${organisation.nom}` : ""}.
          </p>
          <ul className="mt-10 hidden flex-col gap-5 sm:flex">
            {ATOUTS.map(([titre, texte]) => (
              <li key={titre} className="flex gap-3.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/[.14]"><Check size={18} /></span>
                <span><b className="block font-semibold">{titre}</b><span className="text-sm text-menu-texte">{texte}</span></span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="flex flex-1 items-center justify-center bg-white px-6 py-10">
        <form onSubmit={soumettre} className="flex w-full max-w-[400px] flex-col gap-5">
          {etape === "code" ? (
            <>
              <div>
                <h2 className="text-[28px] font-semibold">Vérification</h2>
                <p className="mt-1 text-sm text-encre-douce">Saisissez le code à 6 chiffres affiché par votre application d’authentification.</p>
              </div>
              <Champ libelle="Code de vérification" inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" required />
            </>
          ) : etape === "oubli" ? (
            <>
              <div>
                <h2 className="text-[28px] font-semibold">Mot de passe oublié</h2>
                <p className="mt-1 text-sm text-encre-douce">Votre demande sera transmise à l’administrateur, qui vous communiquera un nouveau mot de passe.</p>
              </div>
              <Champ libelle="Matricule ou adresse e-mail" value={identifiant} onChange={(e) => setIdentifiant(e.target.value)} required autoFocus />
            </>
          ) : (
            <>
              <div>
                <h2 className="text-[28px] font-semibold">Connexion</h2>
                <p className="mt-1 text-sm text-encre-douce">Espace réservé au personnel habilité.</p>
              </div>
              <Champ libelle="Matricule ou adresse e-mail" placeholder={`ex. ${organisation?.prefixe_matricule ?? "EDM-"}001864`}
                autoComplete="username" value={identifiant} onChange={(e) => setIdentifiant(e.target.value)} required autoFocus />
              <Champ libelle="Mot de passe" type="password" placeholder="Votre mot de passe" autoComplete="current-password"
                value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} required />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CaseACocher libelle="Rester connecté sur ce poste" coche={resterConnecte} onChange={setResterConnecte} />
                <button type="button" className="text-[15px] text-primaire underline" onClick={() => { setEtape("oubli"); setErreur(null); setInfo(""); }}>
                  Mot de passe oublié ?
                </button>
              </div>
            </>
          )}

          {erreur !== null && <MessageErreur erreur={erreur} />}
          {info && <Encart icone={Check}>{info}</Encart>}

          <Bouton type="submit" variante="primaire" grand chargement={envoi} icone={etape === "code" ? KeyRound : undefined}>
            {etape === "code" ? "Valider le code" : etape === "oubli" ? "Envoyer la demande" : "Se connecter"}
          </Bouton>
          {etape !== "identifiants" && (
            <button type="button" className="text-sm text-primaire underline" onClick={() => { setEtape("identifiants"); setErreur(null); }}>
              Retour à la connexion
            </button>
          )}
          <Encart icone={Lock}>Les connexions sont journalisées. Une vérification en deux étapes peut vous être demandée.</Encart>
        </form>
      </section>
    </div>
  );
}
