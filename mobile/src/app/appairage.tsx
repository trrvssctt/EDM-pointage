/** Enregistrement de l'appareil : scan du QR code affiché dans l'application web
 *  (Sites et terminaux › Enregistrer un terminal › Téléphone), ou saisie manuelle. */
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "@/lib/session";
import type { Appareil } from "@/lib/api";
import { Bouton, Carte, Champ, Encart, Lien, Logo, s } from "@/composants/ui";
import { C, F } from "@/lib/theme";

export default function Appairage() {
  const { appairer } = useSession();
  const marge = useSafeAreaInsets();
  const [permission, demander] = useCameraPermissions();
  const [mode, setMode] = useState<"scan" | "manuel">("scan");
  const [v, setV] = useState<Appareil>({ url_serveur: "http://", code_terminal: "MOB-", cle_api: "" });
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [lu, setLu] = useState(false);

  const valider = async (a: Appareil) => {
    setErreur("");
    setEnCours(true);
    try {
      await appairer(a);
      router.replace("/connexion");
    } catch (e) {
      setErreur(`${e instanceof Error ? e.message : e}. Vérifiez que le téléphone est sur le même réseau que le serveur et que l'adresse est correcte (${a.url_serveur}).`);
      setLu(false);
    } finally {
      setEnCours(false);
    }
  };

  const scan = ({ data }: { data: string }) => {
    if (lu) return;
    try {
      const a = JSON.parse(data) as Appareil;
      if (!a.url_serveur || !a.cle_api || !a.code_terminal) throw new Error();
      setLu(true);
      setV(a);
      valider(a);
    } catch {
      setErreur("Ce QR code n'est pas un QR code d'enregistrement d'appareil.");
    }
  };

  return (
    <KeyboardAvoidingView style={s.page} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: marge.top + 30, gap: 18 }} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: "center", gap: 10 }}>
          <Logo taille={80} />
          <Text style={{ fontFamily: F.gras, fontSize: 22, color: C.encre }}>Enregistrer l’appareil</Text>
          <Text style={[s.petit, { textAlign: "center", fontSize: 14 }]}>
            Seuls les appareils enregistrés par l’administrateur peuvent enrôler ou pointer.
          </Text>
        </View>

        {mode === "scan" ? (
          <Carte style={{ gap: 12 }}>
            <Text style={s.section}>Scanner le QR code d’enregistrement</Text>
            <Text style={s.petit}>Application web › Sites et terminaux › Enregistrer un terminal (Téléphone) ou « Nouvelle clé ».</Text>
            {!permission?.granted ? (
              <Bouton titre="Autoriser la caméra" icone="camera" onPress={demander} />
            ) : (
              <View style={{ height: 280, borderRadius: 12, overflow: "hidden", backgroundColor: C.kiosque }}>
                <CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ["qr"] }} onBarcodeScanned={lu ? undefined : scan} />
              </View>
            )}
          </Carte>
        ) : (
          <Carte style={{ gap: 14 }}>
            <Champ libelle="Adresse du serveur" value={v.url_serveur} onChangeText={(t) => setV({ ...v, url_serveur: t.trim() })}
              placeholder="http://192.168.1.24:8000" keyboardType="url" />
            <Champ libelle="Code de l'appareil" value={v.code_terminal} onChangeText={(t) => setV({ ...v, code_terminal: t.toUpperCase() })} />
            <Champ libelle="Clé d'accès" value={v.cle_api} onChangeText={(t) => setV({ ...v, cle_api: t.trim() })} placeholder="edmt_…" />
            <Bouton titre="Enregistrer" chargement={enCours} onPress={() => valider(v)} desactive={!v.cle_api || v.url_serveur.length < 10} />
          </Carte>
        )}
        {enCours && mode === "scan" ? <Text style={[s.petit, { textAlign: "center" }]}>Vérification auprès du serveur…</Text> : null}
        {erreur ? <Text style={s.erreur}>{erreur}</Text> : null}
        <Lien texte={mode === "scan" ? "Saisir les informations manuellement" : "Scanner un QR code"}
          onPress={() => { setMode(mode === "scan" ? "manuel" : "scan"); setErreur(""); }} />
        <Encart icone="lock" texte="La clé d'accès est conservée dans le trousseau sécurisé de l'iPhone (Keychain)." />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
