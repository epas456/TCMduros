import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// La interfaz compilada se copia dentro del paquete Python para que
// `durostcm serve` la sirva sin necesitar Node en el equipo final.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../durostcm/web",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:7777", ws: true },
    },
  },
});
