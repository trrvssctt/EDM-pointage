import { Redirect, Tabs } from "expo-router";
import Feather from "@expo/vector-icons/Feather";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";
import { useSession } from "@/lib/session";
import { C, F } from "@/lib/theme";

export default function Onglets() {
  const { accueil, enAttente } = useSession();
  if (!accueil) return <Redirect href="/" />;
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: C.primaire,
      tabBarInactiveTintColor: C.douce,
      tabBarLabelStyle: { fontFamily: F.moyen, fontSize: 11 },
      tabBarStyle: { backgroundColor: "#fff", borderTopColor: C.bord },
    }}>
      <Tabs.Screen name="accueil" options={{ title: "Accueil", tabBarIcon: ({ color }) => <Feather name="grid" size={22} color={color as string} /> }} />
      <Tabs.Screen name="enroler" options={{ title: "Enrôler", tabBarIcon: ({ color }) => <MaterialCommunityIcons name="face-recognition" size={22} color={color as string} /> }} />
      <Tabs.Screen name="secours" options={{ title: "Secours", tabBarIcon: ({ color }) => <Feather name="camera" size={22} color={color as string} /> }} />
      <Tabs.Screen name="file" options={{ title: "File d’envoi", tabBarBadge: enAttente || undefined,
        tabBarBadgeStyle: { backgroundColor: C.alerte, fontFamily: F.gras, fontSize: 11 },
        tabBarIcon: ({ color }) => <Feather name="refresh-cw" size={21} color={color as string} /> }} />
    </Tabs>
  );
}
