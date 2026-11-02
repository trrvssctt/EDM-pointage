import { useState } from "react";
import { cx } from "./ui";

/** Logo de l'organisation (téléversé par l'administrateur), sur fond blanc arrondi comme dans les maquettes. */
export function Logo({ taille = 56, className, source = "/api/organisation/logo" }: { taille?: number; className?: string; source?: string }) {
  const [erreur, setErreur] = useState(false);
  return (
    <img src={erreur ? "/logo-defaut.png" : source} alt="Logo de l'organisation" onError={() => setErreur(true)}
      style={{ width: taille, height: taille }}
      className={cx("shrink-0 rounded-xl bg-white object-contain", className)} />
  );
}
