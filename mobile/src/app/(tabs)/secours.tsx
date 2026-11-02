/** Écrans 20 et 21 — Pointage de secours quand la borne du site est en panne.
 *  Le téléphone photographie l'agent ; la reconnaissance est faite par le serveur central avec la même
 *  galerie que les bornes. Sans réseau, la photo attend dans la file d'envoi et l'agent est reconnu à l'envoi. */
import { useCallback, useRef, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, Text, View } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useFocusEffect } from "expo-router";
import Feather from "@expo/vector-icons/Feather";
import { api } from "@/lib/api";
import { fileEnvoi, type Element } from "@/lib/file";
import { nouvelUuid, prendrePhoto } from "@/lib/photos";
import { useSession } from "@/lib/session";
import { Avatar, Bouton, Carte, EnTete, Encart, Lien, Pastille, heure, initiales, s } from "@/composants/ui";
import { C, F } from "@/lib/theme";

type TypeP = "ENTREE" | "SORTIE";

export default function Secours() {
  const { accueil, enLigne, peut } = useSession();
  const camera = useRef<CameraView>(null);
  const [permission, demander] = useCameraPermissions();
  const [type, setType] = useState<TypeP>(new Date().getHours() < 12 ? "ENTREE" : "SORTIE");
  const [actif, setActif] = useState(true);
  const [pret, setPret] = useState(false);
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState("");
  const [resultat, setResultat] = useState<Element | null>(null);
  const [dernier, setDernier] = useState<Element | null>(null);
  useFocusEffect(useCallback(() => { setActif(true); return () => setActif(false); }, []));
  if (!accueil) return null;
  const sousTitre = `${accueil.appareil.site} · ${accueil.appareil.code}`;

  if (!peut("pointages.secours")) {
    return <View style={s.page}><EnTete titre="Pointage de secours" sousTitre={sousTitre} />
      <View style={{ padding: 16 }}><Encart icone="lock" texte="Votre profil ne permet pas le pointage de secours." /></View></View>;
  }

  const pointer = async () => {
    if (enCours) return;
    setEnCours(true);
    setMessage("");
    try {
      const photo = await prendrePhoto(camera.current);
      const uuid = nouvelUuid();
      const element = fileEnvoi.ajouter({
        uuid, nature: "SECOURS", titre: "Secours · agent à reconnaître", detail: `${type === "ENTREE" ? "Entrée" : "Sortie"} · ${heure(new Date().toISOString())}`,
        corps: { uuid, horodatage: new Date().toISOString(), type, image: photo.dataUrl, hors_ligne: !enLigne },
      });
      const r = await fileEnvoi.envoyer(element);
      if (r.statut === "ENVOYE" && r.reponse?.resultat === "REPRENDRE") {
        fileEnvoi.supprimer(uuid);
        setMessage(r.reponse.message + " : reprenez la photo en cadrant le visage de face.");
        return;
      }
      setResultat(r);
      setDernier(r);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setEnCours(false);
    }
  };

  if (resultat) return <Resultat element={resultat} sousTitre={sousTitre} onSuivant={() => setResultat(null)} />;

  return (
    <View style={s.page}>
      <EnTete titre="Pointage de secours" sousTitre={sousTitre} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, flexGrow: 1 }}>
        <Encart ton="alerte" icone="alert-triangle" titre="Mode secours."
          texte="À utiliser uniquement si le terminal du site est hors service. Chaque pointage est marqué « secours »." />
        <Pressable onPress={pointer} disabled={!pret || enCours} accessibilityLabel="Photographier l’agent pour pointer"
          style={{ height: 330, borderRadius: 16, overflow: "hidden", backgroundColor: C.camera }}>
          {!permission?.granted ? (
            <View style={{ flex: 1, justifyContent: "center", padding: 20, gap: 12 }}>
              <Text style={[s.texte, { color: "#fff", textAlign: "center" }]}>Autorisez la caméra pour photographier l’agent.</Text>
              <Bouton titre="Autoriser la caméra" icone="camera" onPress={demander} />
            </View>
          ) : actif ? <CameraView ref={camera} style={{ flex: 1 }} facing="back" onCameraReady={() => setPret(true)} /> : null}
          <View pointerEvents="none" style={{ position: "absolute", inset: 0, alignItems: "center", justifyContent: "center" }}>
            <View style={{ width: "52%", aspectRatio: 0.76, borderRadius: 999, borderWidth: 4, borderColor: "#fff" }} />
          </View>
          <View pointerEvents="none" style={{ position: "absolute", left: 0, right: 0, bottom: 14, alignItems: "center" }}>
            <View style={{ flexDirection: "row", gap: 8, alignItems: "center", backgroundColor: C.voile, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 9 }}>
              {enCours ? <ActivityIndicator color="#fff" size="small" /> : <Feather name="camera" size={16} color="#fff" />}
              <Text style={{ fontFamily: F.gras, color: "#fff", fontSize: 14 }}>{enCours ? "Reconnaissance…" : "Cadrez le visage, puis touchez l’image"}</Text>
            </View>
          </View>
        </Pressable>
        {message ? <Text style={[s.erreur, { textAlign: "center" }]}>{message}</Text> : null}
        <View style={{ flexDirection: "row", borderWidth: 1, borderColor: C.champ, borderRadius: 10, overflow: "hidden" }}>
          {(["ENTREE", "SORTIE"] as TypeP[]).map((t) => (
            <Pressable key={t} onPress={() => setType(t)} accessibilityRole="tab" accessibilityState={{ selected: type === t }}
              style={{ flex: 1, minHeight: 48, alignItems: "center", justifyContent: "center", backgroundColor: type === t ? C.primaire : "#fff" }}>
              <Text style={{ fontFamily: F.gras, fontSize: 16, color: type === t ? "#fff" : C.encre }}>{t === "ENTREE" ? "Entrée" : "Sortie"}</Text>
            </Pressable>
          ))}
        </View>
        <Bouton titre="Pointer" icone="camera" onPress={pointer} chargement={enCours} desactive={!pret} />
        {dernier && <Lien texte="Voir le dernier résultat de pointage" onPress={() => setResultat(dernier)} />}
      </ScrollView>
    </View>
  );
}

function Ligne({ libelle, valeur }: { libelle: string; valeur: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.bordLeger }}>
      <Text style={[s.petit, { fontSize: 13 }]}>{libelle}</Text>
      <Text style={{ fontFamily: F.gras, fontSize: 13, color: C.encre }}>{valeur}</Text>
    </View>
  );
}

/** Écran 21 — résultat du pointage. */
function Resultat({ element, sousTitre, onSuivant }: { element: Element; sousTitre: string; onSuivant: () => void }) {
  const { accueil } = useSession();
  const [annule, setAnnule] = useState(false);
  const r = element.reponse;
  const enAttente = element.statut === "EN_ATTENTE";

  const pasMoi = () => Alert.alert("Annuler ce pointage ?", "Le pointage sera annulé et la contestation transmise au responsable.", [
    { text: "Non", style: "cancel" },
    { text: "Oui, annuler", style: "destructive", onPress: async () => {
      try {
        if (enAttente) fileEnvoi.supprimer(element.uuid);
        else await api.post(`/api/mobile/secours/${element.uuid}/annuler`);
        setAnnule(true);
      } catch (e) { Alert.alert("Annulation impossible", e instanceof Error ? e.message : String(e)); }
    } }]);

  let contenu: React.ReactNode;
  if (element.statut === "ERREUR" || r?.resultat === "REFUSE") {
    contenu = (
      <Carte style={{ gap: 12, padding: 18 }}>
        <Pastille ton="danger" icone="x" texte="Pointage refusé" />
        <Text style={{ fontFamily: F.gras, fontSize: 22, color: C.encre }}>{r?.message ?? "Envoi refusé"}</Text>
        <Text style={s.texte}>{r?.motif === "SITE_NON_AUTORISE" ? "Cet agent n’est pas autorisé à pointer sur ce site."
          : r?.motif === "VISAGE_INCONNU" ? "Le visage n’est pas enrôlé ou n’a pas été reconnu. La tentative est transmise au responsable."
          : element.erreur}</Text>
      </Carte>
    );
  } else if (enAttente) {
    contenu = (
      <Carte style={{ gap: 12, padding: 18 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Pastille ton="alerte" icone="wifi-off" texte="Enregistré sur le téléphone" /><Pastille ton="alerte" texte="Secours" />
        </View>
        <Text style={{ fontFamily: F.gras, fontSize: 36, color: C.encre }}>{heure(element.cree_le, true)}</Text>
        <Ligne libelle="Type" valeur={element.detail.split(" · ")[0]} />
        <Ligne libelle="Site de pointage" valeur={accueil?.appareil.site ?? ""} />
        <Ligne libelle="Appareil" valeur={accueil?.appareil.code ?? ""} />
        <Ligne libelle="Synchronisation" valeur="En attente" />
        <Encart ton="alerte" icone="wifi-off" texte="Pas de réseau : la photo partira au retour de la connexion et l’agent sera reconnu par le serveur. L’heure réelle du pointage est conservée." />
      </Carte>
    );
  } else {
    const a = r!.agent;
    const libelle = r!.resultat === "DEJA_POINTE" ? "Déjà enregistré"
      : `${r!.type === "ENTREE" ? "Entrée" : "Sortie"} enregistrée`;
    contenu = (
      <Carte style={{ padding: 18 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 14 }}>
          <Pastille ton={annule ? "neutre" : r!.resultat === "DEJA_POINTE" ? "info" : "succes"} icone={annule ? "slash" : "check"}
            texte={annule ? "Pointage annulé" : libelle} />
          <Pastille ton="alerte" texte="Secours" />
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 14 }}>
          <Avatar initiales={initiales(a.nom_complet)} taille={52} />
          <View><Text style={{ fontFamily: F.gras, fontSize: 21, color: C.encre }}>{a.nom_complet}</Text><Text style={s.mono}>{a.matricule}</Text></View>
        </View>
        <Text style={{ fontFamily: F.gras, fontSize: 40, color: C.encre, marginVertical: 14 }}>{heure(r!.horodatage, true)}</Text>
        <Ligne libelle="Site de pointage" valeur={r!.site} />
        <Ligne libelle="Rattachement" valeur={r!.rattachement} />
        <Ligne libelle="Appareil" valeur={r!.appareil} />
        <Ligne libelle="Synchronisation" valeur="Envoyé" />
      </Carte>
    );
  }
  const reconnu = !enAttente && r?.agent && !annule;
  return (
    <View style={s.page}>
      <EnTete titre="Pointage de secours" sousTitre={sousTitre} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, flexGrow: 1 }}>
        {contenu}
        {(reconnu || (enAttente && !annule)) && <Bouton titre="Ce n’est pas moi" variante="secondaire" onPress={pasMoi} />}
        {annule && <Encart icone="slash" texte="Pointage annulé. La contestation est tracée pour le responsable." />}
        <View style={{ flex: 1 }} />
        <Bouton titre={element.statut === "ERREUR" || r?.resultat === "REFUSE" ? "Réessayer" : "Pointage suivant"} icone="camera" onPress={onSuivant} />
      </ScrollView>
    </View>
  );
}
