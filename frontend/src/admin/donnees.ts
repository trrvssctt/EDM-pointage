/** Référentiels partagés (services, sites, horaires, terminaux), mis en cache par TanStack Query. */
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Horaire, Service, Site, Terminal } from "./types";

export const useServices = () => useQuery({ queryKey: ["services"], queryFn: () => api.get<Service[]>("/api/services"), staleTime: 300_000 });
export const useSites = () => useQuery({ queryKey: ["sites"], queryFn: () => api.get<Site[]>("/api/sites"), staleTime: 30_000 });
export const useHoraires = () => useQuery({ queryKey: ["horaires"], queryFn: () => api.get<Horaire[]>("/api/horaires"), staleTime: 300_000 });
export const useTerminaux = () => useQuery({ queryKey: ["terminaux"], queryFn: () => api.get<Terminal[]>("/api/terminaux"), refetchInterval: 20_000 });

export const enOptions = <T extends { id: number }>(liste: T[] | undefined, libelle: (x: T) => string) =>
  (liste ?? []).map((x) => ({ valeur: x.id, libelle: libelle(x) }));
