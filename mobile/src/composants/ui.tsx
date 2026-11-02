/** Composants d'interface fidèles aux maquettes mobiles (en-tête bleu nuit, cartes, pastilles). */
import { useState, type ReactNode } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps,
  type ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@expo/vector-icons/Feather";
import { router } from "expo-router";
import { C, F } from "@/lib/theme";
import { stockage } from "@/lib/api";

export function EnTete({ titre, sousTitre, retour }: { titre: string; sousTitre?: string; retour?: () => void }) {
  const marge = useSafeAreaInsets();
  return (
    <View style={[s.entete, { paddingTop: marge.top + 14 }]}>
      <View style={s.ligne}>
        {retour && (
          <Pressable onPress={retour} hitSlop={12} accessibilityLabel="Retour" style={{ marginRight: 14 }}>
            <Feather name="arrow-left" size={22} color="#fff" />
          </Pressable>
        )}
        <View style={{ flex: 1 }}>
          <Text style={s.titre}>{titre}</Text>
          {sousTitre ? <Text style={s.sousTitre}>{sousTitre}</Text> : null}
        </View>
      </View>
    </View>
  );
}

type Variante = "primaire" | "secondaire" | "danger";
export function Bouton({ titre, onPress, variante = "primaire", icone, chargement, desactive, style }:
  { titre: string; onPress: () => void; variante?: Variante; icone?: keyof typeof Feather.glyphMap; chargement?: boolean;
    desactive?: boolean; style?: ViewStyle }) {
  const couleur = variante === "primaire" ? "#fff" : variante === "danger" ? C.danger : C.encre;
  return (
    <Pressable onPress={onPress} disabled={desactive || chargement} accessibilityRole="button"
      style={({ pressed }) => [s.bouton, variante === "primaire" ? s.boutonPrimaire : s.boutonSecondaire,
        (desactive || chargement) && { opacity: 0.5 }, pressed && { opacity: 0.85 }, style]}>
      {chargement ? <ActivityIndicator color={couleur} /> : icone ? <Feather name={icone} size={18} color={couleur} /> : null}
      <Text style={[s.boutonTexte, { color: couleur }]}>{titre}</Text>
    </Pressable>
  );
}

export const Carte = ({ children, style }: { children: ReactNode; style?: ViewStyle }) => (
  <View style={[s.carte, style]}>{children}</View>
);

export type Ton = "succes" | "alerte" | "danger" | "info" | "neutre";
const TONS: Record<Ton, [string, string]> = {
  succes: [C.succesPale, C.succes], alerte: [C.alertePale, C.alerte], danger: [C.dangerPale, C.danger],
  info: [C.primairePale, C.primaire], neutre: ["#E8ECF4", C.douce],
};
export function Pastille({ texte, ton = "neutre", icone }: { texte: string; ton?: Ton; icone?: keyof typeof Feather.glyphMap }) {
  const [fond, couleur] = TONS[ton];
  return (
    <View style={[s.pastille, { backgroundColor: fond }]}>
      {icone && <Feather name={icone} size={12} color={couleur} />}
      <Text style={[s.pastilleTexte, { color: couleur }]}>{texte}</Text>
    </View>
  );
}

export const Avatar = ({ initiales, taille = 44 }: { initiales: string; taille?: number }) => (
  <View style={{ width: taille, height: taille, borderRadius: taille / 2, backgroundColor: C.primairePale,
    alignItems: "center", justifyContent: "center" }}>
    <Text style={{ fontFamily: F.gras, color: C.primaire, fontSize: taille * 0.36 }}>{initiales}</Text>
  </View>
);

export function Champ({ libelle, ...props }: TextInputProps & { libelle: string }) {
  const [focus, setFocus] = useState(false);
  return (
    <View style={{ gap: 6 }}>
      <Text style={s.libelle}>{libelle}</Text>
      <TextInput placeholderTextColor="#7B86A0" autoCapitalize="none" autoCorrect={false} {...props}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={[s.champ, focus && { borderColor: C.primaire, borderWidth: 2 }, props.style]} />
    </View>
  );
}

/** Barre de progression en 3 segments (« Étape 2 sur 3 »). */
export const Etapes = ({ courante, texte }: { courante: number; texte: string }) => (
  <View style={{ gap: 10 }}>
    <View style={{ flexDirection: "row", gap: 6 }}>
      {[1, 2, 3].map((n) => <View key={n} style={{ flex: 1, height: 5, borderRadius: 3, backgroundColor: n <= courante ? C.primaire : "#D5DCEB" }} />)}
    </View>
    <Text style={{ fontFamily: F.normal, fontSize: 12, color: C.douce }}>{texte}</Text>
  </View>
);

export const Encart = ({ icone, texte, ton = "neutre", titre }: { icone: keyof typeof Feather.glyphMap; texte: string; ton?: "neutre" | "alerte"; titre?: string }) => (
  <View style={[s.encart, ton === "alerte" && { backgroundColor: C.alertePale, borderColor: "#F3DFB0" }]}>
    <Feather name={icone} size={16} color={ton === "alerte" ? C.alerte : C.douce} style={{ marginTop: 2 }} />
    <Text style={[s.encartTexte, ton === "alerte" && { color: C.alerte }]}>
      {titre ? <Text style={{ fontFamily: F.gras }}>{titre} </Text> : null}{texte}
    </Text>
  </View>
);

export function Logo({ taille = 96 }: { taille?: number }) {
  const [erreur, setErreur] = useState(false);
  const a = stockage.appareil();
  const source = a && !erreur ? { uri: `${a.url_serveur}/api/organisation/logo` } : require("../../assets/logo.png");
  return <Image source={source} onError={() => setErreur(true)} accessibilityLabel="Logo"
    style={{ width: taille, height: taille, borderRadius: 18, backgroundColor: "#fff" }} resizeMode="contain" />;
}

export const Lien = ({ texte, onPress }: { texte: string; onPress: () => void }) => (
  <Pressable onPress={onPress} hitSlop={8}><Text style={s.lien}>{texte}</Text></Pressable>
);

export const allerAccueil = () => router.replace("/");

export const initiales = (nom: string) => {
  const m = nom.replace(/-/g, " ").split(" ").filter(Boolean);
  return m.length ? (m[0][0] + (m.length > 1 ? m[m.length - 1][0] : "")).toUpperCase() : "?";
};

export const heure = (iso: string, secondes = false) => {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}${secondes ? `:${p(d.getSeconds())}` : ""}`;
};

export const s = StyleSheet.create({
  entete: { backgroundColor: C.menu, paddingHorizontal: 20, paddingBottom: 16 },
  ligne: { flexDirection: "row", alignItems: "center" },
  titre: { color: "#fff", fontFamily: F.gras, fontSize: 18 },
  sousTitre: { color: C.menuTexte, fontFamily: F.normal, fontSize: 12, marginTop: 2 },
  bouton: { minHeight: 48, borderRadius: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingHorizontal: 16 },
  boutonPrimaire: { backgroundColor: C.primaire },
  boutonSecondaire: { backgroundColor: "#fff", borderWidth: 1, borderColor: C.champ },
  boutonTexte: { fontFamily: F.gras, fontSize: 15 },
  carte: { backgroundColor: C.carte, borderRadius: 14, borderWidth: 1, borderColor: C.bord, padding: 14 },
  pastille: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 3, borderRadius: 999, alignSelf: "flex-start" },
  pastilleTexte: { fontFamily: F.gras, fontSize: 12 },
  libelle: { fontFamily: F.gras, fontSize: 13, color: C.encre },
  champ: { minHeight: 46, borderWidth: 1, borderColor: C.champ, borderRadius: 8, paddingHorizontal: 12, fontFamily: F.normal, fontSize: 15, color: C.encre, backgroundColor: "#fff" },
  encart: { flexDirection: "row", gap: 10, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: C.bord, backgroundColor: C.surface },
  encartTexte: { flex: 1, fontFamily: F.normal, fontSize: 13, color: C.douce, lineHeight: 19 },
  lien: { fontFamily: F.moyen, fontSize: 14, color: C.primaire, textDecorationLine: "underline", textAlign: "center" },
  page: { flex: 1, backgroundColor: C.fond },
  section: { fontFamily: F.gras, fontSize: 14, color: C.encre },
  texte: { fontFamily: F.normal, fontSize: 14, color: C.encre },
  petit: { fontFamily: F.normal, fontSize: 12, color: C.douce },
  mono: { fontFamily: F.mono, fontSize: 12, color: C.encre },
  erreur: { fontFamily: F.moyen, fontSize: 13, color: C.danger },
});
