import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { Pastille } from "./ui";
import type { EtatTerminal } from "../types";

/** Pastille d'état d'un terminal ou d'un site, libellés des maquettes. */
export function EtatTerminalPastille({ etat }: { etat: EtatTerminal | "AUCUN_TERMINAL" }) {
  switch (etat) {
    case "EN_LIGNE": return <Pastille ton="succes" icone={Wifi}>En ligne</Pastille>;
    case "SYNCHRO": return <Pastille ton="info" icone={RefreshCw}>Synchro en cours</Pastille>;
    case "HORS_LIGNE": return <Pastille ton="alerte" icone={WifiOff}>Hors ligne</Pastille>;
    case "DESACTIVE": return <Pastille>Désactivé</Pastille>;
    case "JAMAIS_CONNECTE": return <Pastille>Jamais connecté</Pastille>;
    default: return <Pastille>Aucun terminal</Pastille>;
  }
}

export const LIBELLES_TYPE_SITE = {
  SIEGE: "Siège", DIRECTION_REGIONALE: "Direction régionale", AGENCE: "Agence commerciale",
  CENTRALE: "Centrale de production", SERVICE_TECHNIQUE: "Service technique",
} as const;
