/** Écran 19 — File d'envoi : éléments conservés sur le téléphone et transmis au retour du réseau. */
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { fileEnvoi, type Element } from "@/lib/file";
import { useSession } from "@/lib/session";
import { Bouton, Carte, EnTete, Encart, Pastille, heure, s } from "@/composants/ui";
import { C, F } from "@/lib/theme";

export default function FileEnvoi() {
  const { accueil, enLigne } = useSession();
  const [elements, setElements] = useState<Element[]>([]);
  const [enCours, setEnCours] = useState(false);
  const lire = useCallback(() => setElements(fileEnvoi.lister()), []);
  useEffect(() => fileEnvoi.ecouter(lire), [lire]);
  useFocusEffect(lire);
  const attente = elements.filter((e) => e.statut === "EN_ATTENTE").length;

  const envoyer = async () => {
    setEnCours(true);
    await fileEnvoi.vider();
    lire();
    setEnCours(false);
  };

  return (
    <View style={s.page}>
      <EnTete titre="File d’envoi" sousTitre={`Appareil ${accueil?.appareil.code ?? ""}`} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={enCours} onRefresh={envoyer} />}>
        {enLigne
          ? <Encart icone="wifi" texte={attente ? "Réseau disponible : les éléments en attente partent automatiquement." : "Réseau disponible : tout est envoyé."} />
          : <Encart ton="alerte" icone="wifi-off" titre="Réseau indisponible"
              texte="Les données restent sur le téléphone, protégées par le chiffrement d’iOS, et partent dès le retour du réseau." />}
        <Text style={s.section}>{elements.length} élément{elements.length > 1 ? "s" : ""}</Text>
        {elements.length === 0 && <Text style={s.petit}>Aucun élément.</Text>}
        {elements.map((e) => (
          <Carte key={e.uuid} style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontFamily: F.gras, fontSize: 14, color: C.encre }}>{e.titre}</Text>
              <Text style={s.petit}>{e.nature === "ENROLEMENT" ? `${e.detail} · ${heure(e.cree_le)}` : e.detail}</Text>
              {e.erreur ? <Text style={[s.petit, { color: C.danger }]}>{e.erreur}</Text> : null}
            </View>
            {e.statut === "EN_ATTENTE" ? <Pastille ton="alerte" texte="En attente" />
              : e.statut === "ERREUR" ? <Pastille ton="danger" texte="Refusé" />
              : <Pastille ton="succes" icone="check" texte="Envoyé" />}
          </Carte>
        ))}
        <View style={{ flex: 1 }} />
        <Bouton titre="Envoyer maintenant" icone="refresh-cw" variante="secondaire" onPress={envoyer} chargement={enCours} desactive={!attente} />
      </ScrollView>
    </View>
  );
}
