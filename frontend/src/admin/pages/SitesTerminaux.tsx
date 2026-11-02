/** Sites et terminaux (maquette « Sites et terminaux ») : autorisations, état, synchronisation. */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import QRCode from "qrcode";
import { Copy, Download, KeyRound, Plus, Power, RefreshCw, ShieldCheck, Smartphone, WifiOff, Wifi } from "lucide-react";
import { api } from "../api";
import { enOptions, useHoraires, useServices, useSites, useTerminaux } from "../donnees";
import { useSession } from "../session";
import type { Terminal, TypeSite } from "../types";
import { Bouton, Carte, Cellule, Champ, EnTetePage, Encart, Interrupteur, Ligne, MessageErreur, Modale, Pastille,
  Selection, Tableau, cx, useNotifier } from "../composants/ui";
import { EtatTerminalPastille, LIBELLES_TYPE_SITE } from "../composants/Etats";
import { dateIso, heure, lireDate } from "../../commun/format";

interface Lot { date: string; terminal: string; recus: number; doublons: number; rejetes: number }

const contact = (iso: string | null) => {
  if (!iso) return "Jamais";
  const d = lireDate(iso);
  return dateIso(d) === dateIso() ? heure(d) : `${heure(d)} (${d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })})`;
};

export function SitesTerminaux() {
  const { peut } = useSession();
  const admin = peut("sites.gerer");
  const client = useQueryClient();
  const notifier = useNotifier();
  const [recherche] = useSearchParams();
  const sites = useSites();
  const terminaux = useTerminaux();
  const [selection, setSelection] = useState<number | null>(Number(recherche.get("terminal")) || null);
  const [modale, setModale] = useState<"site" | "terminal" | "journal" | null>(null);
  const [cle, setCle] = useState<Terminal | null>(null);

  useEffect(() => {
    if (!selection && terminaux.data?.length) {
      setSelection((terminaux.data.find((t) => t.etat === "HORS_LIGNE") ?? terminaux.data[0]).id);
    }
  }, [terminaux.data, selection]);

  const autoriser = useMutation({
    mutationFn: ({ id, autorise }: { id: number; autorise: boolean }) => api.patch(`/api/sites/${id}/pointage`, { autorise }),
    onSuccess: (_, v) => { client.invalidateQueries({ queryKey: ["sites"] }); notifier(v.autorise ? "Pointage autorisé sur ce site" : "Pointage suspendu sur ce site"); },
    onError: (e) => notifier(e.message, "danger"),
  });
  const horsLigne = terminaux.data?.filter((t) => t.etat === "HORS_LIGNE").length ?? 0;
  const choisi = terminaux.data?.find((t) => t.id === selection);

  return (
    <>
      <EnTetePage titre="Sites et terminaux" sousTitre="Sites autorisés au pointage, terminaux installés et synchronisation"
        actions={<>
          {horsLigne > 0 && <Pastille ton="alerte" icone={WifiOff}>{horsLigne} terminal{horsLigne > 1 ? "aux" : ""} hors ligne</Pastille>}
          <Bouton grand onClick={() => setModale("journal")}>Journal de synchronisation</Bouton>
        </>} />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.75fr)_minmax(340px,1fr)]">
        <div className="flex flex-col gap-5">
          <Carte titre="Sites" action={admin && <Bouton grand icone={Plus} onClick={() => setModale("site")}>Ajouter un site</Bouton>}>
            {sites.error ? <MessageErreur erreur={sites.error} /> : (
              <Tableau largeurMin={600} entetes={["Site", "Type", <span className="block text-right">Terminaux</span>, "État", "Pointage"]} chargement={sites.isLoading}>
                {sites.data?.map((s) => (
                  <Ligne key={s.id}>
                    <Cellule className="font-semibold">{s.nom_court || s.nom}</Cellule>
                    <Cellule>{LIBELLES_TYPE_SITE[s.type]}</Cellule>
                    <Cellule className="text-right">{s.nb_terminaux}</Cellule>
                    <Cellule><EtatTerminalPastille etat={s.etat} /></Cellule>
                    <Cellule>
                      <Interrupteur actif={s.actif} disabled={!admin} onChange={(v) => autoriser.mutate({ id: s.id, autorise: v })}
                        libelle={<span className="whitespace-nowrap">{s.actif ? "Autorisé" : "Non autorisé"}</span>} />
                    </Cellule>
                  </Ligne>
                ))}
              </Tableau>
            )}
          </Carte>

          <Carte titre="Terminaux" action={admin && <Bouton grand icone={Plus} onClick={() => setModale("terminal")}>Enregistrer un terminal</Bouton>}>
            <Tableau largeurMin={640} entetes={["Terminal", "Site", "Dernier contact", <span className="block text-right">En attente</span>, "Version", "État"]}
              chargement={terminaux.isLoading}>
              {terminaux.data?.map((t) => (
                <Ligne key={t.id} onClick={() => setSelection(t.id)}>
                  <Cellule className={cx("whitespace-nowrap font-mono text-[13px]", t.id === selection && "font-semibold text-primaire")}>
                    <span className="inline-flex items-center gap-1.5">{t.type === "MOBILE" && <Smartphone size={15} aria-label="Téléphone" />}{t.code}</span>
                  </Cellule>
                  <Cellule>{t.site_nom}</Cellule>
                  <Cellule className="whitespace-nowrap">{contact(t.dernier_contact)}</Cellule>
                  <Cellule className="text-right">{t.nb_en_attente}</Cellule>
                  <Cellule>{t.version ? `v${t.version}` : "–"}</Cellule>
                  <Cellule><EtatTerminalPastille etat={t.etat} /></Cellule>
                </Ligne>
              ))}
            </Tableau>
          </Carte>
          {admin && <Referentiels />}
        </div>
        {choisi && <PanneauSynchro terminal={choisi} admin={admin} onCle={setCle} />}
      </div>

      {modale === "site" && <NouveauSite onFermer={() => setModale(null)} />}
      {modale === "terminal" && <NouveauTerminal onFermer={() => setModale(null)} onCle={setCle} />}
      {modale === "journal" && <JournalSynchro onFermer={() => setModale(null)} />}
      {cle && <CleTerminal terminal={cle} onFermer={() => setCle(null)} />}
    </>
  );
}

function PanneauSynchro({ terminal: t, admin, onCle }: { terminal: Terminal; admin: boolean; onCle: (t: Terminal) => void }) {
  const client = useQueryClient();
  const notifier = useNotifier();
  const lots = useQuery({ queryKey: ["lots"], refetchInterval: 20_000, queryFn: () => api.get<Lot[]>("/api/synchronisation/lots?limite=6") });
  const forcer = useMutation({
    mutationFn: () => api.post(`/api/terminaux/${t.id}/synchroniser`),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["terminaux"] });
      notifier(t.etat === "HORS_LIGNE" ? "Consigne enregistrée : le terminal synchronisera dès son retour sur le réseau"
        : "Synchronisation demandée au terminal"); },
    onError: (e) => notifier(e.message, "danger"),
  });
  const basculer = useMutation({
    mutationFn: () => api.put(`/api/terminaux/${t.id}`, { actif: !t.actif }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["terminaux"] }); client.invalidateQueries({ queryKey: ["sites"] }); },
  });
  const nouvelleCle = useMutation({
    mutationFn: () => api.post<Terminal>(`/api/terminaux/${t.id}/nouvelle-cle`), onSuccess: onCle,
  });
  const bandeau = {
    HORS_LIGNE: ["bg-alerte-pale text-alerte", WifiOff, "Terminal hors ligne"],
    SYNCHRO: ["bg-primaire-pale text-primaire", RefreshCw, "Synchronisation en cours"],
    EN_LIGNE: ["bg-succes-pale text-succes", Wifi, "Terminal en ligne"],
    DESACTIVE: ["bg-surface-grise text-encre-douce", Power, "Terminal désactivé"],
    JAMAIS_CONNECTE: ["bg-surface-grise text-encre-douce", WifiOff, "Terminal jamais connecté"],
  } as const;
  const [classes, Icone, texte] = bandeau[t.etat];

  return (
    <Carte titre={`Synchronisation · ${t.code}`} sousTitre={`${t.libelle} · ${t.site_nom}`} className="xl:sticky xl:top-6">
      <div className={cx("flex items-center gap-3 rounded-[10px] px-4 py-3.5 font-semibold", classes)}><Icone size={20} />{texte}</div>
      <div className="mt-4 flex items-center justify-between text-[15px]"><span>Pointages en attente</span><b>{t.nb_en_attente}</b></div>
      <div className="mt-2 h-3 rounded-full bg-surface-grise">
        <div className={cx("h-full rounded-full", t.nb_en_attente ? "bg-alerte-barre" : "bg-succes-vif")}
          style={{ width: t.nb_en_attente ? `${Math.min(100, 20 + t.nb_en_attente)}%` : "100%" }} />
      </div>
      <p className="mt-2 text-[13px] text-encre-douce">
        {t.nb_en_attente ? "Stockés sur le terminal. Envoi automatique au retour du réseau." : "Aucun pointage en attente sur ce terminal."}
        {t.dernier_contact && ` Dernier contact : ${contact(t.dernier_contact)}${t.adresse_ip ? ` depuis ${t.adresse_ip}` : ""}.`}
      </p>
      <div className="mt-4"><Encart icone={ShieldCheck}>Chaque pointage porte un identifiant unique : un envoi répété est ignoré et ne crée aucun doublon.</Encart></div>
      <h3 className="mb-2 mt-5 text-[15px] font-semibold">Derniers lots reçus</h3>
      <Tableau entetes={["Heure", "Terminal", <span className="block text-right">Reçus</span>, <span className="block text-right">Doublons ignorés</span>]}
        vide={lots.data?.length === 0}>
        {lots.data?.map((l, i) => (
          <Ligne key={i}>
            <Cellule>{heure(l.date)}</Cellule>
            <Cellule className="whitespace-nowrap font-mono text-[13px]">{l.terminal}</Cellule>
            <Cellule className="text-right">{l.recus}</Cellule>
            <Cellule className="text-right">{l.doublons}</Cellule>
          </Ligne>
        ))}
      </Tableau>
      <Bouton grand icone={RefreshCw} className="mt-4 w-full" chargement={forcer.isPending} disabled={!t.actif || t.synchro_demandee}
        onClick={() => forcer.mutate()}>{t.synchro_demandee ? "Synchronisation demandée" : "Forcer la synchronisation"}</Bouton>
      {admin && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Bouton icone={Power} variante={t.actif ? "danger" : "secondaire"} chargement={basculer.isPending}
            onClick={() => (!t.actif || confirm(`Désactiver ${t.code} ? Ses pointages seront refusés par le serveur.`)) && basculer.mutate()}>
            {t.actif ? "Désactiver" : "Réactiver"}
          </Bouton>
          <Bouton icone={KeyRound} chargement={nouvelleCle.isPending}
            onClick={() => confirm("Générer une nouvelle clé ? L’ancienne sera immédiatement invalidée.") && nouvelleCle.mutate()}>Nouvelle clé</Bouton>
        </div>
      )}
    </Carte>
  );
}

function NouveauSite({ onFermer }: { onFermer: () => void }) {
  const client = useQueryClient();
  const notifier = useNotifier();
  const [v, setV] = useState({ code: "", nom: "", nom_court: "", type: "AGENCE" as TypeSite, ville: "" });
  const creer = useMutation({
    mutationFn: () => api.post("/api/sites", { ...v, actif: true }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["sites"] }); notifier("Site ajouté"); onFermer(); },
  });
  return (
    <Modale titre="Ajouter un site" onFermer={onFermer}
      actions={<><Bouton onClick={onFermer}>Annuler</Bouton><Bouton variante="primaire" chargement={creer.isPending} onClick={() => creer.mutate()}>Ajouter</Bouton></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Champ libelle="Code" placeholder="AG-KTI" value={v.code} onChange={(e) => setV({ ...v, code: e.target.value.toUpperCase() })} />
        <Selection libelle="Type" value={v.type} onChange={(e) => setV({ ...v, type: e.target.value as TypeSite })}
          options={Object.entries(LIBELLES_TYPE_SITE).map(([valeur, libelle]) => ({ valeur, libelle }))} />
        <Champ libelle="Nom complet" className="sm:col-span-2" placeholder="Agence commerciale de Kati" value={v.nom} onChange={(e) => setV({ ...v, nom: e.target.value })} />
        <Champ libelle="Nom court (affiché sur les terminaux)" placeholder="Agence Kati" value={v.nom_court} onChange={(e) => setV({ ...v, nom_court: e.target.value })} />
        <Champ libelle="Ville" value={v.ville} onChange={(e) => setV({ ...v, ville: e.target.value })} />
      </div>
      {creer.error && <div className="mt-4"><MessageErreur erreur={creer.error} /></div>}
    </Modale>
  );
}

function NouveauTerminal({ onFermer, onCle }: { onFermer: () => void; onCle: (t: Terminal) => void }) {
  const client = useQueryClient();
  const sites = useSites();
  const [v, setV] = useState({ code: "TRM-", libelle: "", site_id: "", type: "BORNE" as "BORNE" | "MOBILE" });
  const creer = useMutation({
    mutationFn: () => api.post<Terminal>("/api/terminaux", { ...v, site_id: Number(v.site_id || sites.data?.[0]?.id) }),
    onSuccess: (t) => { client.invalidateQueries({ queryKey: ["terminaux"] }); client.invalidateQueries({ queryKey: ["sites"] }); onFermer(); onCle(t); },
  });
  return (
    <Modale titre="Enregistrer un terminal" sousTitre="Une clé d’accès unique sera générée pour ce terminal" onFermer={onFermer}
      actions={<><Bouton onClick={onFermer}>Annuler</Bouton><Bouton variante="primaire" chargement={creer.isPending} onClick={() => creer.mutate()}>Enregistrer</Bouton></>}>
      <div className="grid gap-4">
        <Selection libelle="Type d’appareil" value={v.type}
          onChange={(e) => { const type = e.target.value as "BORNE" | "MOBILE"; setV({ ...v, type, code: type === "MOBILE" ? "MOB-" : "TRM-" }); }}
          options={[{ valeur: "BORNE", libelle: "Borne de pointage (écran tactile + caméra)" },
            { valeur: "MOBILE", libelle: "Téléphone de l’application terrain (enrôlement, secours)" }]} />
        <Champ libelle="Code de l’appareil" value={v.code} onChange={(e) => setV({ ...v, code: e.target.value.toUpperCase() })} />
        <Selection libelle="Site d’installation" value={v.site_id} onChange={(e) => setV({ ...v, site_id: e.target.value })}
          options={enOptions(sites.data, (s) => s.nom_court || s.nom)} />
        <Champ libelle="Emplacement" placeholder="Hall d’entrée" value={v.libelle} onChange={(e) => setV({ ...v, libelle: e.target.value })} />
      </div>
      {creer.error && <div className="mt-4"><MessageErreur erreur={creer.error} /></div>}
    </Modale>
  );
}

function CleTerminal({ terminal: t, onFermer }: { terminal: Terminal; onFermer: () => void }) {
  const notifier = useNotifier();
  const mobile = t.type === "MOBILE";
  // Le téléphone doit joindre le serveur par le réseau : « localhost » ne désigne que ce PC.
  const [url, setUrl] = useState(window.location.origin);
  const toile = useRef<HTMLCanvasElement>(null);
  const config = JSON.stringify(mobile ? { url_serveur: url, code_terminal: t.code, cle_api: t.cle_api }
    : { url_serveur: url, code_terminal: t.code, cle_api: t.cle_api, camera: 0, camera_miroir: false, intervalle_synchro_s: 10,
        anti_rebond_s: 60, port_local: 8100, defis: ["tourner", "cligner"] }, null, 2);
  useEffect(() => {
    if (mobile && toile.current) QRCode.toCanvas(toile.current, JSON.stringify({ url_serveur: url, code_terminal: t.code, cle_api: t.cle_api }), { width: 260, margin: 1 });
  }, [mobile, url, t]);
  const telecharger = () => {
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(new Blob([config], { type: "application/json" }));
    lien.download = `${t.code}.json`;
    lien.click();
  };
  const local = /localhost|127\.0\.0\.1/.test(url);
  return (
    <Modale titre={`Clé d’accès ${mobile ? "du téléphone" : "du terminal"} ${t.code}`} onFermer={onFermer}
      actions={<><Bouton icone={Copy} onClick={() => navigator.clipboard?.writeText(t.cle_api!).then(() => notifier("Clé copiée"))}>Copier la clé</Bouton>
        <Bouton variante={mobile ? "secondaire" : "primaire"} icone={Download} onClick={telecharger}>Fichier de configuration</Bouton></>}>
      <Encart ton="alerte" icone={KeyRound}>Cette clé ne sera plus jamais affichée.{" "}
        {mobile ? "Scannez ce QR code avec l’application terrain, depuis l’écran « Enregistrer l’appareil »."
          : <>Copiez le fichier de configuration dans <code className="mx-1 font-mono">terminal/config/</code> du poste de pointage, puis lancez <code className="font-mono">./run_terminal.sh {t.code}</code>.</>}</Encart>
      <Champ className="mt-4" libelle="Adresse du serveur vue depuis l’appareil" value={url} onChange={(e) => setUrl(e.target.value.trim())}
        aide={local ? "Remplacez localhost par l’adresse IP de ce PC sur le réseau (ex. http://192.168.1.24:8000)." : "Adresse que l’appareil utilisera pour joindre le serveur."} erreur={local && mobile ? "« localhost » n’est pas joignable depuis un téléphone" : undefined} />
      {mobile
        ? <div className="mt-4 flex justify-center"><canvas ref={toile} className="rounded-xl border border-bord" /></div>
        : <pre className="mt-4 overflow-x-auto rounded-[10px] bg-kiosque p-4 font-mono text-xs text-menu-texte">{config}</pre>}
    </Modale>
  );
}

function JournalSynchro({ onFermer }: { onFermer: () => void }) {
  const lots = useQuery({ queryKey: ["lots", "tous"], queryFn: () => api.get<Lot[]>("/api/synchronisation/lots?limite=200") });
  return (
    <Modale large titre="Journal de synchronisation" sousTitre="Lots de pointages reçus des terminaux" onFermer={onFermer}>
      <Tableau entetes={["Date", "Terminal", "Reçus", "Doublons ignorés", "Refusés"]} chargement={lots.isLoading} vide={lots.data?.length === 0}>
        {lots.data?.map((l, i) => (
          <Ligne key={i}>
            <Cellule className="whitespace-nowrap">{lireDate(l.date).toLocaleString("fr-FR")}</Cellule>
            <Cellule className="whitespace-nowrap font-mono text-[13px]">{l.terminal}</Cellule>
            <Cellule>{l.recus}</Cellule><Cellule>{l.doublons}</Cellule><Cellule>{l.rejetes}</Cellule>
          </Ligne>
        ))}
      </Tableau>
    </Modale>
  );
}

function Referentiels() {
  const client = useQueryClient();
  const notifier = useNotifier();
  const services = useServices();
  const horaires = useHoraires();
  const [service, setService] = useState({ code: "", nom: "" });
  const [horaire, setHoraire] = useState({ nom: "", heure_debut: "07:30", heure_fin: "16:00", tolerance_minutes: 10, jours_travailles: "0,1,2,3,4" });
  const ajouterService = useMutation({
    mutationFn: () => api.post("/api/services", service),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["services"] }); setService({ code: "", nom: "" }); notifier("Service ajouté"); },
    onError: (e) => notifier(e.message, "danger"),
  });
  const ajouterHoraire = useMutation({
    mutationFn: () => api.post("/api/horaires", horaire),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["horaires"] }); notifier("Horaire ajouté"); },
    onError: (e) => notifier(e.message, "danger"),
  });
  const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
  return (
    <Carte titre="Services et horaires de travail" sousTitre="Référentiels utilisés pour les dossiers agents et le calcul des retards">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <ul className="mb-3 divide-y divide-bord-leger text-sm">
            {services.data?.map((s) => <li key={s.id} className="flex justify-between py-2"><span>{s.nom}</span><span className="font-mono text-xs text-encre-douce">{s.code}</span></li>)}
          </ul>
          <div className="grid grid-cols-[1fr_2fr_auto] items-end gap-2">
            <Champ libelle="Code" value={service.code} onChange={(e) => setService({ ...service, code: e.target.value.toUpperCase() })} />
            <Champ libelle="Nouveau service" value={service.nom} onChange={(e) => setService({ ...service, nom: e.target.value })} />
            <Bouton grand icone={Plus} aria-label="Ajouter le service" disabled={!service.code || !service.nom} onClick={() => ajouterService.mutate()} />
          </div>
        </div>
        <div>
          <ul className="mb-3 divide-y divide-bord-leger text-sm">
            {horaires.data?.map((h) => (
              <li key={h.id} className="py-2">
                <span className="font-medium">{h.nom}</span>
                <span className="block text-xs text-encre-douce">
                  {h.heure_debut.slice(0, 5)} – {h.heure_fin.slice(0, 5)} · tolérance {h.tolerance_minutes} min · {h.jours_travailles.split(",").map((j) => JOURS[+j]).join(" ")}
                </span>
              </li>
            ))}
          </ul>
          <div className="grid grid-cols-2 gap-2">
            <Champ libelle="Nouvel horaire" className="col-span-2" value={horaire.nom} onChange={(e) => setHoraire({ ...horaire, nom: e.target.value })} />
            <Champ libelle="Début" type="time" value={horaire.heure_debut} onChange={(e) => setHoraire({ ...horaire, heure_debut: e.target.value })} />
            <Champ libelle="Fin" type="time" value={horaire.heure_fin} onChange={(e) => setHoraire({ ...horaire, heure_fin: e.target.value })} />
            <Champ libelle="Tolérance (min)" type="number" min={0} value={horaire.tolerance_minutes}
              onChange={(e) => setHoraire({ ...horaire, tolerance_minutes: Number(e.target.value) })} />
            <Champ libelle="Jours (0 = lundi)" value={horaire.jours_travailles} onChange={(e) => setHoraire({ ...horaire, jours_travailles: e.target.value })} />
            <Bouton grand icone={Plus} className="col-span-2" disabled={!horaire.nom} onClick={() => ajouterHoraire.mutate()}>Ajouter l’horaire</Bouton>
          </div>
        </div>
      </div>
    </Carte>
  );
}
