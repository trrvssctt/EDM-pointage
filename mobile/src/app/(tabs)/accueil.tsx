/** Écran 14 — Accueil : appareil, actions principales et activité récente. */
import { useCallback, useEffect, useState } from "react";
import { Alert, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import Feather from "@expo/vector-icons/Feather";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useSession } from "@/lib/session";
import { fileEnvoi, type Element } from "@/lib/file";
import { Carte, EnTete, Pastille, heure, s, type Ton } from "@/composants/ui";
import { C, F } from "@/lib/theme";

const ROLES = { ADMIN: "Administrateur", DRH: "Direction des RH", RESPONSABLE: "Responsable habilité" };
const STATUTS: Record<string, [string, Ton]> = {
  EN_ATTENTE: ["En attente", "alerte"], ENVOYE: ["Envoyé", "succes"], ERREUR: ["Refusé", "danger"], GABARIT_CALCULE: ["En validation", "info"],
  RECUE: ["En validation", "info"], VALIDEE: ["Validé", "succes"], REJETEE: ["Rejeté", "danger"], SYNCHRONISE: ["Synchronisé", "succes"],
  ANNULE: ["Annulé", "neutre"],
};

function Action({ titre, texte, icone, fond, couleur, onPress, desactive }:
  { titre: string; texte: string; icone: React.ReactNode; fond: string; couleur: string; onPress: () => void; desactive?: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={desactive} style={({ pressed }) => [{ opacity: desactive ? 0.45 : pressed ? 0.8 : 1 }]}>
      <Carte style={{ flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 18 }}>
        <View style={{ width: 46, height: 46, borderRadius: 10, backgroundColor: fond, alignItems: "center", justifyContent: "center" }}>{icone}</View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: F.gras, fontSize: 17, color: C.encre }}>{titre}</Text>
          <Text style={[s.petit, { fontSize: 13, marginTop: 2 }]}>{texte}</Text>
        </View>
        <Feather name="arrow-right" size={20} color={couleur} />
      </Carte>
    </Pressable>
  );
}

export default function Accueil() {
  const { accueil, enLigne, rafraichir, peut, deconnecter } = useSession();
  const [locaux, setLocaux] = useState<Element[]>([]);
  const [chargement, setChargement] = useState(false);
  const recharger = useCallback(() => setLocaux(fileEnvoi.lister()), []);
  useEffect(() => fileEnvoi.ecouter(recharger), [recharger]);
  useFocusEffect(useCallback(() => { recharger(); rafraichir(); }, [recharger, rafraichir]));
  if (!accueil) return null;
  const u = accueil.utilisateur.utilisateur;

  // Activité : éléments encore sur le téléphone + historique du serveur (sans doublon)
  const connus = new Set(accueil.activite.map((a) => a.uuid));
  const activite = [
    ...locaux.filter((e) => e.statut !== "ENVOYE" || !connus.has(e.uuid)).map((e) => ({
      uuid: e.uuid, titre: e.titre, date: e.cree_le, detail: e.detail,
      statut: e.statut === "ENVOYE" && e.nature === "ENROLEMENT" ? (e.reponse?.statut ?? "ENVOYE") : e.statut })),
    ...accueil.activite.map((a) => ({ uuid: a.uuid, titre: a.titre, date: a.date,
      detail: a.nature === "SECOURS" ? `${a.type === "SORTIE" ? "Sortie" : "Entrée"} ${heure(a.date)}` : heure(a.date), statut: a.statut })),
  ].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 8);

  const quitter = () => Alert.alert("Se déconnecter ?", "Les éléments en attente restent sur le téléphone et seront envoyés après reconnexion.", [
    { text: "Annuler", style: "cancel" }, { text: "Se déconnecter", style: "destructive", onPress: async () => { await deconnecter(); router.replace("/connexion"); } }]);

  return (
    <View style={s.page}>
      <EnTete titre={`Bonjour ${u.nom_complet.split(" ")[0] || u.identifiant}`}
        sousTitre={`${ROLES[u.role]}${u.role === "RESPONSABLE" ? ` · ${u.perimetre}` : ""}`} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}
        refreshControl={<RefreshControl refreshing={chargement} onRefresh={async () => { setChargement(true); await rafraichir(); recharger(); setChargement(false); }} />}>
        <Carte style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontFamily: F.gras, fontSize: 14, color: C.encre }}>{accueil.appareil.site}</Text>
            <Text style={s.petit}>Appareil {accueil.appareil.code}</Text>
          </View>
          {enLigne ? <Pastille ton="succes" icone="wifi" texte="En ligne" /> : <Pastille ton="alerte" icone="wifi-off" texte="Hors ligne" />}
        </Carte>
        <Action titre="Enrôler un agent" texte="Photographier l’agent et l’envoyer à l’application web." fond={C.primairePale} couleur={C.encre}
          icone={<MaterialCommunityIcons name="face-recognition" size={24} color={C.primaire} />} onPress={() => router.navigate("/enroler")}
          desactive={!peut("biometrie.proposer")} />
        <Action titre="Pointage de secours" texte="À utiliser quand le terminal du site est en panne." fond={C.alertePale} couleur={C.encre}
          icone={<Feather name="camera" size={22} color={C.alerte} />} onPress={() => router.navigate("/secours")}
          desactive={!peut("pointages.secours")} />

        <Text style={[s.section, { marginTop: 6 }]}>Activité récente</Text>
        <View>
          {activite.length === 0 && <Text style={s.petit}>Aucune activité pour le moment.</Text>}
          {activite.map((a, i) => {
            const [texte, ton] = STATUTS[a.statut] ?? [a.statut, "neutre" as Ton];
            return (
              <View key={a.uuid + i} style={{ flexDirection: "row", alignItems: "center", paddingVertical: 11, borderTopWidth: i ? 1 : 0, borderTopColor: C.bord }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontFamily: F.gras, fontSize: 14, color: C.encre }}>{a.titre}</Text>
                  <Text style={s.petit}>{a.detail}</Text>
                </View>
                <Pastille texte={texte} ton={ton} />
              </View>
            );
          })}
        </View>
        <Pressable onPress={quitter} style={{ alignSelf: "center", marginTop: 10, flexDirection: "row", gap: 6, alignItems: "center" }}>
          <Feather name="log-out" size={15} color={C.douce} /><Text style={s.petit}>Se déconnecter ({u.identifiant})</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}
