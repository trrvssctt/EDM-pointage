/** Palette relevée sur les maquettes ; « primaire » et « menu » suivent la marque de l'organisation. */
export default {
  content: ["./index.html", "./terminal.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        encre: { DEFAULT: "#142040", douce: "#4B5878", moyenne: "#3B4767" },
        primaire: { DEFAULT: "rgb(var(--primaire) / <alpha-value>)", fonce: "rgb(var(--menu) / <alpha-value>)",
          pale: "#E3EAFB", focus: "#6C8CE0", clair: "#8FA6DE" },
        menu: { DEFAULT: "rgb(var(--menu) / <alpha-value>)", texte: "#C9D3F0", titre: "#AEBBE3" },
        fond: "#F3F5FA",
        surface: { DEFAULT: "#F6F8FC", grise: "#E8ECF4", bleutee: "#E6EBF5" },
        bord: { DEFAULT: "#DCE2EE", leger: "#EAEEF6", champ: "#B8C2D9" },
        succes: { DEFAULT: "#0B6B41", pale: "#E1F4EA", vif: "#3DDC97" },
        alerte: { DEFAULT: "#7A4A00", pale: "#FCEFD2", barre: "#B5530A" },
        danger: { DEFAULT: "#A8150D", pale: "#FBE3E1", vif: "#FF6B61" },
        kiosque: { DEFAULT: "#0B1430", texte: "#B9C5E8", voile: "rgba(8, 16, 40, 0.78)" },
      },
      borderRadius: { carte: "12px" },
    },
  },
  plugins: [],
};
