import { Redirect } from "expo-router";
import { useSession } from "@/lib/session";

/** Aiguillage : appareil à enregistrer → connexion → application. */
export default function Entree() {
  const { appareil, accueil } = useSession();
  if (!appareil) return <Redirect href="/appairage" />;
  if (!accueil) return <Redirect href="/connexion" />;
  return <Redirect href="/accueil" />;
}
