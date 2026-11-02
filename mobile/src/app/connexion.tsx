/** Écran 13 — Connexion (matricule + mot de passe, vérification en deux étapes si activée). */
import { useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "@/lib/session";
import { Bouton, Carte, Champ, Lien, Logo, Pastille, s } from "@/composants/ui";
import { C, F } from "@/lib/theme";

export default function Connexion() {
  const { connecter, validerCode, appareil, oublierAppareil } = useSession();
  const marge = useSafeAreaInsets();
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [temporaire, setTemporaire] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  const soumettre = async () => {
    setErreur("");
    setEnCours(true);
    try {
      if (temporaire) {
        await validerCode(temporaire, code);
        router.replace("/accueil");
      } else {
        const r = await connecter(identifiant.trim(), motDePasse);
        if (r.deux_etapes_requise) setTemporaire(r.jeton_temporaire!);
        else router.replace("/accueil");
      }
    } catch (e) {
      setErreur(e instanceof Error ? e.message : String(e));
    } finally {
      setEnCours(false);
    }
  };

  const changerAppareil = () => Alert.alert("Retirer l'enregistrement ?", "Il faudra scanner un nouveau QR code d'enregistrement.", [
    { text: "Annuler", style: "cancel" },
    { text: "Retirer", style: "destructive", onPress: async () => { await oublierAppareil(); router.replace("/appairage"); } },
  ]);

  return (
    <KeyboardAvoidingView style={s.page} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingTop: marge.top + 40, gap: 18, flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: "center", gap: 6 }}>
          <Logo taille={96} />
          <Text style={{ fontFamily: F.gras, fontSize: 22, color: C.encre, marginTop: 14 }}>Énergie du Mali</Text>
          <Text style={[s.petit, { fontSize: 14 }]}>Application terrain · présences</Text>
        </View>
        <Carte style={{ gap: 14, padding: 16 }}>
          {temporaire ? (
            <Champ libelle="Code de vérification (6 chiffres)" value={code} onChangeText={(t) => setCode(t.replace(/\D/g, ""))}
              keyboardType="number-pad" maxLength={6} autoFocus textContentType="oneTimeCode" />
          ) : (
            <>
              <Champ libelle="Matricule" placeholder="ex. EDM-005120" value={identifiant} onChangeText={setIdentifiant}
                textContentType="username" returnKeyType="next" />
              <Champ libelle="Mot de passe" placeholder="Votre mot de passe" value={motDePasse} onChangeText={setMotDePasse}
                secureTextEntry textContentType="password" returnKeyType="go" onSubmitEditing={soumettre} />
            </>
          )}
          {erreur ? <Text style={s.erreur}>{erreur}</Text> : null}
          <Bouton titre={temporaire ? "Valider le code" : "Se connecter"} onPress={soumettre} chargement={enCours}
            desactive={temporaire ? code.length !== 6 : !identifiant || !motDePasse} />
        </Carte>
        <View style={{ alignItems: "center", gap: 10 }}>
          <Pastille ton="info" icone="check" texte={`Appareil enregistré · ${appareil?.code_terminal ?? ""}`} />
          <Text style={[s.petit, { textAlign: "center" }]}>Seuls les appareils enregistrés par l’administrateur peuvent enrôler ou pointer.</Text>
        </View>
        <View style={{ flex: 1 }} />
        <Lien texte="Changer d'appareil enregistré" onPress={changerAppareil} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
