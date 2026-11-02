import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useFonts, IBMPlexSans_400Regular, IBMPlexSans_500Medium, IBMPlexSans_600SemiBold } from "@expo-google-fonts/ibm-plex-sans";
import { IBMPlexMono_400Regular } from "@expo-google-fonts/ibm-plex-mono";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ActivityIndicator, View } from "react-native";
import { FournisseurSession, useSession } from "@/lib/session";
import { C } from "@/lib/theme";

function Navigation() {
  const { pret } = useSession();
  if (!pret) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: C.fond }}><ActivityIndicator color={C.primaire} /></View>;
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: C.fond } }} />;
}

export default function RootLayout() {
  const [polices] = useFonts({ IBMPlexSans_400Regular, IBMPlexSans_500Medium, IBMPlexSans_600SemiBold, IBMPlexMono_400Regular });
  if (!polices) return null;
  return (
    <SafeAreaProvider>
      <FournisseurSession>
        <StatusBar style="light" />
        <Navigation />
      </FournisseurSession>
    </SafeAreaProvider>
  );
}
