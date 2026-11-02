/** Session de l'utilisateur connecté, droits et identité de l'organisation (marque blanche). */
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, jeton, quandSessionExpire } from "./api";
import { appliquerMarque } from "../commun/marque";
import type { Organisation, Session } from "./types";

interface Contexte {
  session: Session | null;
  organisation: Organisation | null;
  chargement: boolean;
  peut: (droit: string) => boolean;
  ouvrir: (jeton: string, durable: boolean) => void;
  fermer: () => void;
}

const ContexteSession = createContext<Contexte>(null!);
export const useSession = () => useContext(ContexteSession);

export function FournisseurSession({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const organisation = useQuery({ queryKey: ["organisation"], queryFn: () => api.get<Organisation>("/api/organisation") });
  const session = useQuery({
    queryKey: ["session"], retry: false, staleTime: 60_000,
    queryFn: () => (jeton.lire() ? api.get<Session>("/api/auth/session") : Promise.resolve(null)),
  });

  useEffect(() => {
    if (organisation.data) {
      appliquerMarque(organisation.data.couleur_primaire, organisation.data.couleur_menu);
      document.title = `${organisation.data.sigle} · ${organisation.data.slogan}`;
    }
  }, [organisation.data]);

  useEffect(() => quandSessionExpire(() => client.setQueryData(["session"], null)), [client]);

  const valeur: Contexte = {
    session: session.data ?? null,
    organisation: organisation.data ?? null,
    chargement: session.isLoading,
    peut: (droit) => (session.data?.droits[droit] ?? "non") !== "non",
    ouvrir: (t, durable) => {
      jeton.ecrire(t, durable);
      client.invalidateQueries({ queryKey: ["session"] });
    },
    fermer: () => {
      jeton.effacer();
      client.clear();
      client.setQueryData(["session"], null);
    },
  };
  return <ContexteSession.Provider value={valeur}>{children}</ContexteSession.Provider>;
}

export const LIBELLES_ROLE = { ADMIN: "Administrateur", DRH: "Direction des RH", RESPONSABLE: "Responsable habilité" } as const;
