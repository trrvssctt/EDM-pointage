import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../commun/styles.css";
import { FournisseurSession, useSession } from "./session";
import { FournisseurNotifications, Chargement } from "./composants/ui";
import { Disposition } from "./composants/Disposition";
import { Connexion } from "./pages/Connexion";
import { TableauDeBord } from "./pages/TableauDeBord";
import { Agents } from "./pages/Agents";
import { Enrolement } from "./pages/Enrolement";
import { Pointages } from "./pages/Pointages";
import { Rapports } from "./pages/Rapports";
import { SitesTerminaux } from "./pages/SitesTerminaux";
import { Utilisateurs } from "./pages/Utilisateurs";
import { Parametres } from "./pages/Parametres";
import { Compte } from "./pages/Compte";

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

function Application() {
  const { session, chargement, peut } = useSession();
  if (chargement) return <Chargement />;
  if (!session) return <Connexion />;
  const u = session.utilisateur;
  return (
    <Disposition>
      <Routes>
        <Route path="/" element={<TableauDeBord />} />
        <Route path="/agents" element={<Agents />} />
        {peut("biometrie.enroler") && <Route path="/enrolement" element={<Enrolement />} />}
        <Route path="/pointages" element={<Pointages />} />
        <Route path="/rapports" element={<Rapports />} />
        {u.role !== "RESPONSABLE" && <Route path="/sites" element={<SitesTerminaux />} />}
        {u.role !== "RESPONSABLE" && <Route path="/utilisateurs" element={<Utilisateurs />} />}
        {peut("utilisateurs.gerer") && <Route path="/parametres" element={<Parametres />} />}
        <Route path="/compte" element={<Compte />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Disposition>
  );
}

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <FournisseurNotifications>
        <BrowserRouter>
          <FournisseurSession>
            <Application />
          </FournisseurSession>
        </BrowserRouter>
      </FournisseurNotifications>
    </QueryClientProvider>
  </StrictMode>,
);
