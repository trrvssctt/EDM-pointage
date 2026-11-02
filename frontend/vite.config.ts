import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const ici = (fichier: string) => fileURLToPath(new URL(fichier, import.meta.url));

// Deux applications : l'administration (index.html) et l'écran du terminal (terminal.html).
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: { admin: ici("index.html"), terminal: ici("terminal.html") },
    },
  },
  server: {
    proxy: {
      "/api": process.env.VITE_CIBLE ?? "http://127.0.0.1:8000",
      "/video.mjpg": process.env.VITE_CIBLE ?? "http://127.0.0.1:8100",
    },
  },
});
