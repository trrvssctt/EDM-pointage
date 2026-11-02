export type Role = "ADMIN" | "DRH" | "RESPONSABLE";
export type ValeurDroit = "oui" | "non" | "perimetre";

export interface Utilisateur {
  id: number; identifiant: string; email: string | null; nom_complet: string; fonction: string; role: Role;
  service_id: number | null; site_id: number | null; perimetre: string; actif: boolean; deux_etapes: boolean;
  derniere_connexion: string | null; reinitialisation_demandee: boolean;
}
export interface Session { utilisateur: Utilisateur; droits: Record<string, ValeurDroit> }
export interface Organisation {
  nom: string; sigle: string; slogan: string; couleur_primaire: string; couleur_menu: string; prefixe_matricule: string;
  deux_etapes_obligatoire_admin: boolean; duree_conservation_jours: number; a_un_logo: boolean;
}
export interface Service { id: number; code: string; nom: string }
export type EtatTerminal = "EN_LIGNE" | "SYNCHRO" | "HORS_LIGNE" | "DESACTIVE" | "JAMAIS_CONNECTE";
export type TypeSite = "SIEGE" | "DIRECTION_REGIONALE" | "AGENCE" | "CENTRALE" | "SERVICE_TECHNIQUE";
export interface Site {
  id: number; code: string; nom: string; nom_court: string; type: TypeSite; ville: string; actif: boolean;
  nb_terminaux: number; etat: EtatTerminal | "AUCUN_TERMINAL"; nb_agents: number;
}
export interface Horaire { id: number; nom: string; heure_debut: string; heure_fin: string; tolerance_minutes: number; jours_travailles: string }
export interface Terminal {
  id: number; code: string; libelle: string; site_id: number; site_nom: string; actif: boolean;
  dernier_contact: string | null; adresse_ip: string; version: string; nb_en_attente: number;
  synchro_demandee: boolean; type: "BORNE" | "MOBILE"; etat: EtatTerminal; cle_api?: string;
}
export interface Agent {
  id: number; matricule: string; nom: string; prenom: string; nom_complet: string; fonction: string; email: string;
  telephone: string; service_id: number; service_nom: string; site_rattachement_id: number;
  site_rattachement_nom: string; horaire_id: number; horaire_nom: string; tous_sites: boolean;
  sites_autorises: number[]; actif: boolean; nb_gabarits: number; consentement_le: string | null; cree_le: string;
}
export interface Page<T> { total: number; elements: T[] }
export interface LignePointage {
  id: string; nature: "POINTAGE" | "REFUS"; horodatage: string; agent: string; initiales: string;
  matricule: string | null; service: string; site: string; site_rattachement: string; terminal: string;
  type: "ENTREE" | "SORTIE" | "REFUSE"; alerte: string | null; libelle_alerte: string | null; motif?: string;
  synchro: "SYNCHRONISE" | "DIFFERE"; confiance: number | null; secours?: boolean;
}
export interface Anomalie { type: string; id?: number; titre: string; detail: string; lien: Record<string, string | number> }
export interface TableauDeBord {
  date: string; date_longue: string; attendus: number; presents: number; taux_presence: number; retards: number;
  taux_retard: number; absences: number; taux_absence: number; en_attente: number; terminaux_en_attente: number;
  presence_par_site: { site: string; presents: number; attendus: number; taux: number }[];
  evolution: { date: string; presents: number; week_end: boolean }[];
  anomalies: Anomalie[];
  terminaux: { id: number; code: string; site: string; etat: EtatTerminal; en_attente: number }[];
}
export interface LigneRapport {
  cle: string; agent?: string; service?: string; matricule?: string; effectif: number; jours_ouvres: number;
  presences: number; retards: number; absences: number; minutes_retard: number; heures_travaillees: number;
  anomalies: number; taux_presence: number;
}
export interface Journee {
  date: string; matricule: string; agent: string; service: string; site_rattachement: string;
  statut: "PRESENT" | "RETARD" | "ABSENT"; premiere_entree: string | null; derniere_sortie: string | null;
  retard_minutes: number; duree_minutes: number; sites: string[]; anomalies: string[];
}
export interface Rapport {
  titre: string; periode: string; perimetre: string; debut: string; fin: string; regroupement: string;
  indicateurs: { taux_presence: number; retards: number; absences: number; minutes_retard: number };
  lignes: LigneRapport[]; total: LigneRapport; detail: Journee[];
}
export interface Analyse {
  nb_visages: number; luminosite: "CORRECTE" | "SOMBRE" | "SUREXPOSEE" | null; nettete: "BONNE" | "CORRECTE" | "FLOUE" | null;
  lacet: number | null; tangage: number | null; taille_ok: boolean; boite: number[] | null;
  largeur_image: number; hauteur_image: number;
}
export interface DemandeEnrolement {
  uuid: string; statut: "RECUE" | "GABARIT_CALCULE" | "VALIDEE" | "REJETEE"; motif: string; agent_id: number; agent: string;
  matricule: string; service: string; site_rattachement: string; appareil: string; auteur: string; nb_photos: number;
  vivacite: boolean; controles: string; capture_le: string; recu_le: string; traite_par: string; traite_le: string | null;
  photos?: Record<string, string>;
}
