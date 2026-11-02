/** Menu latéral (bureau) / barre supérieure et tiroir (tablette, mobile), d'après les maquettes. */
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Clock, FileText, LayoutGrid, LogOut, Menu, Monitor, ScanFace, Settings, ShieldCheck, User, X,
  type LucideIcon } from "lucide-react";
import { useSession, LIBELLES_ROLE } from "../session";
import { Logo } from "./Logo";
import { Avatar, cx } from "./ui";
import { initiales } from "../../commun/format";

interface Entree { vers: string; libelle: string; icone: LucideIcon; visible: boolean }

export function Disposition({ children }: { children: ReactNode }) {
  const { session, organisation, peut, fermer } = useSession();
  const [ouvert, setOuvert] = useState(false);
  const { pathname } = useLocation();
  const u = session!.utilisateur;
  const gestion: Entree[] = [
    { vers: "/", libelle: "Tableau de bord", icone: LayoutGrid, visible: true },
    { vers: "/agents", libelle: "Agents", icone: User, visible: true },
    { vers: "/enrolement", libelle: "Enrôlement", icone: ScanFace, visible: peut("biometrie.enroler") },
    { vers: "/pointages", libelle: "Pointages", icone: Clock, visible: peut("pointages.consulter") },
    { vers: "/rapports", libelle: "Rapports", icone: FileText, visible: peut("rapports.generer") },
  ];
  const administration: Entree[] = [
    { vers: "/sites", libelle: "Sites et terminaux", icone: Monitor, visible: u.role !== "RESPONSABLE" },
    { vers: "/utilisateurs", libelle: "Utilisateurs et droits", icone: ShieldCheck, visible: u.role !== "RESPONSABLE" },
    { vers: "/parametres", libelle: "Paramètres", icone: Settings, visible: peut("utilisateurs.gerer") },
  ];

  const lien = (e: Entree) => e.visible && (
    <NavLink key={e.vers} to={e.vers} end={e.vers === "/"} onClick={() => setOuvert(false)}
      className={({ isActive }) => cx("flex min-h-[44px] items-center gap-3 rounded-lg px-3 text-sm no-underline",
        isActive ? "bg-white/[.14] font-semibold text-white" : "font-medium text-menu-texte hover:bg-white/[.07] hover:text-white")}>
      <e.icone size={20} strokeWidth={1.8} />{e.libelle}
    </NavLink>
  );

  const menu = (
    <div className="flex h-full flex-col gap-7 px-3.5 py-[22px]">
      <div className="flex items-center gap-3 px-1">
        <Logo />
        <div className="flex flex-col">
          <span className="text-[15px] font-semibold">{organisation?.nom}</span>
          <span className="text-xs text-menu-texte">{organisation?.slogan}</span>
        </div>
      </div>
      <nav className="flex flex-col gap-0.5" aria-label="Gestion">
        <p className="px-3 pb-1 text-[11px] font-semibold tracking-[0.08em] text-menu-titre">GESTION</p>
        {gestion.map(lien)}
      </nav>
      {administration.some((e) => e.visible) && (
        <nav className="flex flex-col gap-0.5" aria-label="Administration">
          <p className="px-3 pb-1 text-[11px] font-semibold tracking-[0.08em] text-menu-titre">ADMINISTRATION</p>
          {administration.map(lien)}
        </nav>
      )}
      <div className="mt-auto flex flex-col gap-3 border-t border-white/[.18] pt-4">
        <NavLink to="/compte" onClick={() => setOuvert(false)} className="flex items-center gap-3 rounded-lg px-1 py-1 text-white no-underline hover:bg-white/[.07] hover:text-white">
          <span className="rounded-full bg-white"><Avatar initiales={initiales(u.nom_complet || u.identifiant)} /></span>
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold">{u.nom_complet || u.identifiant}</span>
            <span className="truncate text-xs text-menu-texte">{u.role === "RESPONSABLE" ? u.perimetre : LIBELLES_ROLE[u.role]}</span>
          </span>
        </NavLink>
        <button type="button" onClick={fermer} className="flex items-center gap-3 px-3 text-sm text-menu-texte hover:text-white">
          <LogOut size={18} /> Se déconnecter
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 overflow-y-auto bg-menu text-white lg:block">{menu}</aside>
      <div className="sticky top-0 z-40 flex items-center justify-between bg-menu px-4 py-2.5 text-white lg:hidden">
        <div className="flex items-center gap-2.5">
          <Logo taille={36} className="rounded-lg" />
          <span className="text-[15px] font-semibold">{organisation?.nom}</span>
        </div>
        <button type="button" aria-label="Ouvrir le menu" onClick={() => setOuvert(true)} className="rounded-lg p-2 hover:bg-white/10"><Menu /></button>
      </div>
      {ouvert && (
        <div className="fixed inset-0 z-50 bg-[#081028]/50 lg:hidden" onClick={() => setOuvert(false)}>
          <aside className="relative h-full w-[280px] overflow-y-auto bg-menu text-white" onClick={(e) => e.stopPropagation()}>
            <button type="button" aria-label="Fermer le menu" onClick={() => setOuvert(false)} className="absolute right-3 top-3 rounded-lg p-2 hover:bg-white/10"><X /></button>
            {menu}
          </aside>
        </div>
      )}
      <main key={pathname} className="min-w-0 flex-1 px-4 py-6 sm:px-7 sm:py-7 xl:px-9">
        {organisation?.deux_etapes_obligatoire_admin && u.role === "ADMIN" && !u.deux_etapes && pathname !== "/compte" && (
          <NavLink to="/compte" className="mb-5 flex items-center gap-2 rounded-[10px] border border-alerte/20 bg-alerte-pale px-4 py-3 text-sm font-semibold text-alerte no-underline">
            <ShieldCheck size={18} /> La politique de sécurité exige la vérification en deux étapes pour les administrateurs : configurez-la maintenant.
          </NavLink>
        )}
        {children}
      </main>
    </div>
  );
}
