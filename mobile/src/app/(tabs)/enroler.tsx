/** Écrans 15 à 18 — Enrôler un agent : choisir l'agent, photographier 5 poses, vérifier, envoyer, suivre. */
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router, useFocusEffect, useNavigation } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@expo/vector-icons/Feather";
import { api, horsLigne } from "@/lib/api";
import { fileEnvoi } from "@/lib/file";
import { nouvelUuid, prendrePhoto, type Photo } from "@/lib/photos";
import { useSession } from "@/lib/session";
import { Avatar, Bouton, Carte, EnTete, Encart, Etapes, Pastille, heure, initiales, s, type Ton } from "@/composants/ui";
import { C, F } from "@/lib/theme";

interface Agent { id: number; matricule: string; nom_complet: string; service_nom: string; site_rattachement_nom: string; nb_gabarits: number }
interface Analyse { nb_visages: number; luminosite: string | null; nettete: string | null; lacet: number | null; tangage: number | null;
  taille_ok: boolean; score?: number | null; trop_tourne?: boolean }
type Pose = "face" | "gauche" | "droite" | "haut" | "bas";
interface Capture extends Photo { analyse: Analyse | null }

const POSES: { pose: Pose; libelle: string; consigne: string }[] = [
  { pose: "face", libelle: "Face", consigne: "Regardez droit vers l’objectif" },
  { pose: "gauche", libelle: "Gauche", consigne: "Tournez la tête vers la gauche (un quart de tour)" },
  { pose: "droite", libelle: "Droite", consigne: "Tournez la tête de l’autre côté (un quart de tour)" },
  { pose: "haut", libelle: "Haut", consigne: "Levez légèrement le menton, visage vers l’objectif" },
  { pose: "bas", libelle: "Bas", consigne: "Baissez légèrement la tête, visage vers l’objectif" },
];
// Orientation (lacet : position du nez entre les yeux, 0,5 = de face). Le sens « gauche / droite » n'est pas
// imposé (la consigne est comprise différemment selon que l'on parle de la gauche de l'agent ou du photographe) :
// il faut un côté, puis le côté opposé. Le profil complet est refusé (gabarit peu fiable).
const ROTATION_MIN = 0.1, ROTATION_MAX = 0.36, FACE_MAX = 0.15, INCLINAISON_MAX = 0.25;

/** Vérifie la qualité et l'orientation ; renvoie un message si la photo doit être reprise. */
function controler(a: Analyse, pose: Pose, captures: Partial<Record<Pose, { analyse: Analyse | null }>>): string | null {
  if (a.nb_visages === 0) return "Aucun visage détecté : cadrez le visage dans l’ovale.";
  if (a.nb_visages > 1) return "Plusieurs visages sur la photo : un seul agent doit être dans le cadre.";
  if (!a.taille_ok) return "Le visage est trop petit : rapprochez-vous de l’agent.";
  if (a.score != null && a.score < 0.85) return "Visage mal visible : évitez le contre-jour et cadrez tout le visage.";
  if (a.nettete === "FLOUE") return "La photo est floue : tenez le téléphone immobile.";
  if (a.luminosite === "SOMBRE") return "La photo est trop sombre : rapprochez-vous de la lumière.";
  if (a.lacet === null) return null;
  const ecart = a.lacet - 0.5;
  if (pose === "face") return Math.abs(ecart) > FACE_MAX ? "L’agent doit regarder droit vers l’objectif." : null;
  if (pose === "haut" || pose === "bas") return Math.abs(ecart) > INCLINAISON_MAX ? "Gardez le visage tourné vers l’objectif, seule la tête s’incline." : null;
  if (Math.abs(ecart) > ROTATION_MAX || a.trop_tourne) return "Tête trop tournée (profil) : demandez seulement un quart de tour.";
  if (Math.abs(ecart) < ROTATION_MIN) return "Tête pas assez tournée : un quart de tour est nécessaire.";
  if (pose === "droite") {
    const premier = captures.gauche?.analyse?.lacet;
    if (premier != null && Math.sign(premier - 0.5) === Math.sign(ecart)) return "Même côté que la photo précédente : tournez la tête de l’autre côté.";
  }
  return null;
}

export default function Enroler() {
  const navigation = useNavigation();
  const { peut } = useSession();
  const [etape, setEtape] = useState<1 | 2 | 3 | 4>(1);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [captures, setCaptures] = useState<Partial<Record<Pose, Capture>>>({});
  const [envoi, setEnvoi] = useState<{ uuid: string; enLigne: boolean } | null>(null);

  // Les étapes de capture et de vérification s'affichent en plein écran (sans barre d'onglets)
  useEffect(() => {
    navigation.setOptions({ tabBarStyle: etape === 2 || etape === 3 ? { display: "none" } : { backgroundColor: "#fff", borderTopColor: C.bord } });
  }, [etape, navigation]);

  const recommencer = () => { setEtape(1); setAgent(null); setCaptures({}); setEnvoi(null); };
  if (!peut("biometrie.proposer")) {
    return <View style={s.page}><EnTete titre="Enrôler un agent" /><View style={{ padding: 16 }}>
      <Encart icone="lock" texte="Votre profil ne permet pas de proposer un enrôlement." /></View></View>;
  }
  if (etape === 1) return <ChoixAgent agent={agent} onChoix={setAgent} onSuivant={() => setEtape(2)} />;
  if (etape === 2 && agent) return <Prise agent={agent} captures={captures} setCaptures={setCaptures}
    onRetour={() => setEtape(1)} onTermine={() => setEtape(3)} />;
  if (etape === 3 && agent) return <Revue agent={agent} captures={captures} onRetour={() => setEtape(2)}
    onReprendre={(p) => { setCaptures((c) => { const n = { ...c }; delete n[p]; return n; }); setEtape(2); }}
    onEnvoye={(uuid, enLigne) => { setEnvoi({ uuid, enLigne }); setEtape(4); }} />;
  if (etape === 4 && agent && envoi) return <Suivi agent={agent} envoi={envoi} nbPhotos={Object.keys(captures).length}
    onAutre={recommencer} />;
  return null;
}

/* ---------- Étape 1 : choisir l'agent (écran 15) ---------- */
function ChoixAgent({ agent, onChoix, onSuivant }: { agent: Agent | null; onChoix: (a: Agent) => void; onSuivant: () => void }) {
  const { accueil } = useSession();
  const [q, setQ] = useState(accueil?.organisation.prefixe_matricule ?? "");
  const [resultats, setResultats] = useState<Agent[] | null>(null);
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const chercher = async () => {
    setErreur("");
    setEnCours(true);
    try {
      const r = await api.get<{ elements: Agent[] }>(`/api/agents?q=${encodeURIComponent(q.trim())}&enrole=false&actif=true&taille=15`);
      setResultats(r.elements);
    } catch (e) {
      setErreur(horsLigne(e) ? "Recherche impossible sans réseau : connectez-vous au Wi-Fi de l’entreprise." : String((e as Error).message));
    } finally {
      setEnCours(false);
    }
  };
  return (
    <View style={s.page}>
      <EnTete titre="Enrôler un agent" retour={() => router.navigate("/accueil")} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <Etapes courante={1} texte="Étape 1 sur 3 · Choisir l’agent" />
        <Text style={s.section}>Matricule ou nom</Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <TextInput value={q} onChangeText={setQ} onSubmitEditing={chercher} returnKeyType="search" autoCapitalize="characters"
            autoCorrect={false} placeholder="EDM-009" placeholderTextColor="#7B86A0" style={[s.champ, { flex: 1 }]} />
          <Pressable onPress={chercher} accessibilityLabel="Rechercher" style={{ width: 46, borderRadius: 8, backgroundColor: C.primaire, alignItems: "center", justifyContent: "center" }}>
            {enCours ? <ActivityIndicator color="#fff" /> : <Feather name="search" size={20} color="#fff" />}
          </Pressable>
        </View>
        {erreur ? <Text style={s.erreur}>{erreur}</Text> : null}
        {resultats && <Text style={s.section}>Résultat{resultats.length > 1 ? "s" : ""}</Text>}
        {resultats?.length === 0 && <Text style={s.petit}>Aucun agent à enrôler ne correspond.</Text>}
        {resultats?.map((a) => (
          <Pressable key={a.id} onPress={() => onChoix(a)}>
            <Carte style={{ flexDirection: "row", alignItems: "center", gap: 12, borderColor: agent?.id === a.id ? C.primaire : C.bord, borderWidth: agent?.id === a.id ? 2 : 1 }}>
              <Avatar initiales={initiales(a.nom_complet)} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontFamily: F.gras, fontSize: 16, color: C.encre }}>{a.nom_complet}</Text>
                <Text style={s.mono}>{a.matricule}</Text>
                <Text style={s.petit}>{a.service_nom} · {a.site_rattachement_nom}</Text>
              </View>
              <Pastille texte="À enrôler" ton="alerte" />
            </Carte>
          </Pressable>
        ))}
        <Encart icone="lock" texte="Seuls les agents sans visage enrôlé sont proposés. Le dossier est créé dans l’application web." />
        <View style={{ flex: 1 }} />
        <Bouton titre="Photographier l’agent" icone="camera" onPress={onSuivant} desactive={!agent} />
      </ScrollView>
    </View>
  );
}

/* ---------- Étape 2 : prise des 5 poses (écran 16) ---------- */
function Prise({ agent, captures, setCaptures, onRetour, onTermine }: {
  agent: Agent; captures: Partial<Record<Pose, Capture>>; setCaptures: React.Dispatch<React.SetStateAction<Partial<Record<Pose, Capture>>>>;
  onRetour: () => void; onTermine: () => void }) {
  const marge = useSafeAreaInsets();
  const camera = useRef<CameraView>(null);
  const [permission, demander] = useCameraPermissions();
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [pret, setPret] = useState(false);
  const [enCours, setEnCours] = useState(false);
  const [derniere, setDerniere] = useState<Analyse | null>(null);
  const [message, setMessage] = useState("");
  const [actif, setActif] = useState(true);
  useFocusEffect(useCallback(() => { setActif(true); return () => setActif(false); }, []));  // une seule caméra active
  const courante = POSES.find((p) => !captures[p.pose]);
  const index = courante ? POSES.indexOf(courante) + 1 : 5;

  useEffect(() => { if (!courante) onTermine(); }, [courante, onTermine]);

  const declencher = async () => {
    if (!courante || enCours) return;
    setEnCours(true);
    setMessage("");
    try {
      const photo = await prendrePhoto(camera.current);
      let analyse: Analyse | null = null;
      try {
        analyse = await api.post<Analyse>("/api/agents/enrolement/analyse", { image: photo.dataUrl }, 12000);
      } catch (e) {
        if (!horsLigne(e)) throw e;  // hors ligne : contrôle fait par le serveur à la réception
      }
      setDerniere(analyse);
      const probleme = analyse ? controler(analyse, courante.pose, captures) : null;
      // Une photo non conforme n'est jamais gardée : elle produirait un gabarit peu fiable.
      if (!probleme) setCaptures((c) => ({ ...c, [courante.pose]: { ...photo, analyse } }));
      else setMessage(probleme);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setEnCours(false);
    }
  };

  const qualite = (libelle: string, valeur: string | null | undefined, bon: string[]): [string, Ton] =>
    !derniere || !valeur ? [`${libelle} : —`, "neutre"] : bon.includes(valeur) ? [`${libelle} ${valeur === "BONNE" ? "bonne" : "correcte"}`, "succes"] : [`${libelle} insuffisante`, "alerte"];

  return (
    <View style={s.page}>
      <EnTete titre="Photographier l’agent" retour={onRetour} />
      <View style={{ padding: 16, gap: 12, flex: 1, paddingBottom: marge.bottom + 12 }}>
        <Etapes courante={2} texte={`Étape 2 sur 3 · Pose ${index} sur 5`} />
        <View style={{ flex: 1, borderRadius: 16, overflow: "hidden", backgroundColor: C.camera }}>
          {!permission?.granted ? (
            <View style={{ flex: 1, justifyContent: "center", padding: 20, gap: 12 }}>
              <Text style={[s.texte, { color: "#fff", textAlign: "center" }]}>L’application a besoin de la caméra pour photographier l’agent.</Text>
              <Bouton titre="Autoriser la caméra" icone="camera" onPress={demander} />
            </View>
          ) : actif ? (
            <CameraView ref={camera} style={{ flex: 1 }} facing={facing} mirror={false} onCameraReady={() => setPret(true)} />
          ) : null}
          <View pointerEvents="none" style={{ position: "absolute", inset: 0, alignItems: "center", justifyContent: "center" }}>
            <View style={{ width: "58%", aspectRatio: 0.76, borderRadius: 999, borderWidth: 4, borderColor: "#fff" }} />
          </View>
          <View style={{ position: "absolute", top: 10, right: 10, backgroundColor: C.primairePale, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 }}>
            <Text style={{ fontFamily: F.gras, fontSize: 12, color: C.primaire }}>{agent.nom_complet}</Text>
          </View>
          <Pressable onPress={() => setFacing(facing === "back" ? "front" : "back")} accessibilityLabel="Changer de caméra"
            style={{ position: "absolute", top: 10, left: 10, backgroundColor: C.voile, borderRadius: 999, padding: 8 }}>
            <Feather name="refresh-ccw" size={16} color="#fff" />
          </Pressable>
          <View style={{ position: "absolute", left: 12, right: 12, bottom: 12, backgroundColor: C.voile, borderRadius: 999, paddingVertical: 10,
            paddingHorizontal: 14, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center" }}>
            <Feather name="camera" size={16} color="#fff" />
            <Text style={{ fontFamily: F.gras, fontSize: 14, color: "#fff", textAlign: "center", flexShrink: 1 }}>{courante?.consigne ?? "Poses terminées"}</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: 6 }}>
          {POSES.map((p) => {
            const faite = !!captures[p.pose], enCoursP = courante?.pose === p.pose;
            return (
              <View key={p.pose} style={{ flex: 1, alignItems: "center", paddingVertical: 6, borderRadius: 8,
                backgroundColor: faite ? C.succesPale : enCoursP ? C.primairePale : "#E8ECF4" }}>
                <Text style={{ fontFamily: F.gras, fontSize: 12, color: faite ? C.succes : enCoursP ? C.primaire : C.douce }}>{p.libelle}</Text>
              </View>
            );
          })}
        </View>
        <View style={{ flexDirection: "row", gap: 8, justifyContent: "center" }}>
          {[qualite("Lumière", derniere?.luminosite, ["CORRECTE"]), qualite("Netteté", derniere?.nettete, ["BONNE", "CORRECTE"])].map(([t, ton]) =>
            <Pastille key={t} texte={t} ton={ton} icone={ton === "succes" ? "check" : undefined} />)}
        </View>
        {message ? <Text style={[s.erreur, { textAlign: "center" }]}>{message}</Text> : null}
        <Pressable onPress={declencher} disabled={!pret || enCours} accessibilityLabel="Prendre la photo"
          style={{ alignSelf: "center", width: 72, height: 72, borderRadius: 36, borderWidth: 4, borderColor: "#B8C6EA",
            backgroundColor: C.primaire, alignItems: "center", justifyContent: "center", opacity: pret ? 1 : 0.5 }}>
          {enCours ? <ActivityIndicator color="#fff" /> : null}
        </Pressable>
      </View>
    </View>
  );
}

/* ---------- Étape 3 : vérifier et envoyer (écran 17) ---------- */
function Revue({ agent, captures, onRetour, onReprendre, onEnvoye }: {
  agent: Agent; captures: Partial<Record<Pose, Capture>>; onRetour: () => void; onReprendre: (p: Pose) => void;
  onEnvoye: (uuid: string, enLigne: boolean) => void }) {
  const marge = useSafeAreaInsets();
  const [consentement, setConsentement] = useState(false);
  const [enCours, setEnCours] = useState(false);
  const envoyer = async () => {
    setEnCours(true);
    const uuid = nouvelUuid();
    const element = fileEnvoi.ajouter({
      uuid, nature: "ENROLEMENT", titre: `Enrôlement · ${agent.nom_complet}`, detail: `${Object.keys(captures).length} photos`,
      corps: { uuid, agent_id: agent.id, consentement: true, capture_le: new Date().toISOString(),
        images: POSES.filter((p) => captures[p.pose]).map((p) => ({ pose: p.pose, image: captures[p.pose]!.dataUrl })) },
    });
    const r = await fileEnvoi.envoyer(element);
    setEnCours(false);
    if (r.statut === "ERREUR") Alert.alert("Envoi refusé", r.erreur ?? "");
    else onEnvoye(uuid, r.statut === "ENVOYE");
  };
  return (
    <View style={s.page}>
      <EnTete titre="Vérifier les photos" retour={onRetour} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: marge.bottom + 16, flexGrow: 1 }}>
        <Etapes courante={3} texte="Étape 3 sur 3 · Vérifier et envoyer" />
        <Carte style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Avatar initiales={initiales(agent.nom_complet)} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontFamily: F.gras, fontSize: 16, color: C.encre }}>{agent.nom_complet}</Text>
            <Text style={s.mono}>{agent.matricule}</Text>
            <Text style={s.petit}>{agent.service_nom} · {agent.site_rattachement_nom}</Text>
          </View>
          <Pastille texte={`${Object.keys(captures).length} photos`} ton="info" />
        </Carte>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {POSES.map((p) => (
            <Pressable key={p.pose} onPress={() => onReprendre(p.pose)} style={{ width: "31.5%", aspectRatio: 0.95, borderRadius: 10, overflow: "hidden", backgroundColor: C.camera }}>
              {captures[p.pose] && <Image source={{ uri: captures[p.pose]!.uri }} style={{ flex: 1 }} />}
              <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", justifyContent: "space-between",
                padding: 6, backgroundColor: "rgba(8,16,40,0.6)" }}>
                <Text style={{ fontFamily: F.gras, fontSize: 12, color: "#fff" }}>{p.libelle}</Text>
                <Feather name="check" size={14} color={C.succesVif} />
              </View>
            </Pressable>
          ))}
          <Pressable onPress={() => onReprendre("face")} style={{ width: "31.5%", aspectRatio: 0.95, borderRadius: 10, borderWidth: 1.5,
            borderStyle: "dashed", borderColor: C.champ, alignItems: "center", justifyContent: "center", gap: 6 }}>
            <Feather name="refresh-cw" size={18} color={C.douce} />
            <Text style={{ fontFamily: F.gras, fontSize: 12, color: C.douce }}>Reprendre</Text>
          </Pressable>
        </View>
        <Text style={s.petit}>Touchez une photo pour la reprendre.</Text>
        <Pressable onPress={() => setConsentement(!consentement)} style={{ flexDirection: "row", gap: 10, alignItems: "flex-start" }}
          accessibilityRole="checkbox" accessibilityState={{ checked: consentement }}>
          <View style={{ width: 22, height: 22, borderRadius: 5, borderWidth: 2, borderColor: consentement ? C.primaire : C.champ,
            backgroundColor: consentement ? C.primaire : "#fff", alignItems: "center", justifyContent: "center", marginTop: 1 }}>
            {consentement && <Feather name="check" size={15} color="#fff" />}
          </View>
          <Text style={[s.texte, { flex: 1 }]}>L’agent a été informé et consent au traitement de ses données biométriques.</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Bouton titre="Envoyer au serveur central" icone="arrow-right" onPress={envoyer} chargement={enCours} desactive={!consentement} />
      </ScrollView>
    </View>
  );
}

/* ---------- Étape 4 : envoyé, suivi de la validation (écran 18) ---------- */
function Suivi({ agent, envoi, nbPhotos, onAutre }: { agent: Agent; envoi: { uuid: string; enLigne: boolean }; nbPhotos: number; onAutre: () => void }) {
  const [statut, setStatut] = useState<{ statut: string; motif: string; recu_le?: string } | null>(null);
  useEffect(() => {
    let actif = true;
    const lire = async () => {
      try {
        const r = await api.get<{ statut: string; motif: string; recu_le: string }>(`/api/mobile/enrolements/${envoi.uuid}`, 6000);
        if (actif) setStatut(r);
      } catch { /* pas encore reçu ou hors ligne */ }
    };
    lire();
    const i = setInterval(lire, 5000);
    return () => { actif = false; clearInterval(i); };
  }, [envoi.uuid]);
  const recu = !!statut;
  // Rejet automatique à la réception (moins de 3 photos exploitables) ≠ rejet par la DRH
  const inexploitable = statut?.statut === "REJETEE" && (statut.motif.includes("exploitable") || statut.motif.startsWith("À refaire"));
  const etapes: [string, string, "fait" | "cours" | "attente" | "erreur"][] = [
    ["Reçu par le serveur", recu ? `${heure(statut!.recu_le ?? new Date().toISOString())} · ${nbPhotos} photos` : "En attente du réseau · conservé sur le téléphone", recu ? "fait" : "cours"],
    ["Calcul du gabarit", !recu ? "—" : inexploitable ? statut!.motif : statut!.statut === "RECUE" ? "En cours" : "Terminé",
      !recu ? "attente" : inexploitable ? "erreur" : statut!.statut === "RECUE" ? "cours" : "fait"],
    ["Validation par la DRH", statut?.statut === "VALIDEE" ? "Validé : l’agent peut pointer" : statut?.statut === "REJETEE" ? (inexploitable ? "Non transmis : refaites les photos" : `Rejeté · ${statut.motif}`) : "Dans l’application web › Enrôlement",
      statut?.statut === "VALIDEE" ? "fait" : statut?.statut === "REJETEE" ? "erreur" : recu ? "cours" : "attente"],
  ];
  return (
    <View style={s.page}>
      <EnTete titre="Enrôlement" />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 16, flexGrow: 1 }}>
        <View style={{ alignItems: "center", gap: 8, marginTop: 10 }}>
          <View style={{ width: 66, height: 66, borderRadius: 33, backgroundColor: recu ? C.succesPale : C.alertePale, alignItems: "center", justifyContent: "center" }}>
            <Feather name={recu ? "check" : "clock"} size={32} color={recu ? C.succes : C.alerte} />
          </View>
          <Text style={{ fontFamily: F.gras, fontSize: 21, color: C.encre }}>{recu ? "Photos envoyées" : "Photos enregistrées"}</Text>
          <Text style={s.petit}>{agent.nom_complet} · {agent.matricule}</Text>
        </View>
        <Carte style={{ gap: 4 }}>
          {etapes.map(([titre, detail, etat], i) => (
            <View key={titre} style={{ flexDirection: "row", gap: 12, paddingVertical: 10, borderTopWidth: i ? 1 : 0, borderTopColor: C.bordLeger }}>
              <View style={{ width: 24, height: 24, borderRadius: 12, borderWidth: 2, alignItems: "center", justifyContent: "center",
                borderColor: etat === "fait" ? C.primaire : etat === "erreur" ? C.danger : etat === "cours" ? C.primaire : C.champ,
                backgroundColor: etat === "fait" ? C.primaire : etat === "erreur" ? C.danger : "#fff" }}>
                {etat === "fait" && <Feather name="check" size={14} color="#fff" />}
                {etat === "erreur" && <Feather name="x" size={14} color="#fff" />}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontFamily: F.gras, fontSize: 14, color: C.encre }}>{titre}</Text>
                <Text style={s.petit}>{detail}</Text>
              </View>
            </View>
          ))}
        </Carte>
        {!recu && <Encart ton="alerte" icone="wifi-off" texte="Les photos partiront automatiquement dès le retour du réseau (onglet File d’envoi)." />}
        <View style={{ flex: 1 }} />
        <Bouton titre="Enrôler un autre agent" icone="user-plus" onPress={onAutre} />
        <Bouton titre="Retour à l’accueil" variante="secondaire" onPress={() => { onAutre(); router.navigate("/accueil"); }} />
      </ScrollView>
    </View>
  );
}
