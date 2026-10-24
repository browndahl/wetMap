import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        id: "/",
        scope: "/",
        name: "WetMap – DMI radar",
        short_name: "WetMap",
        description: "Tilgængelig 3D-visualisering af DMI radarmålinger",
        theme_color: "#07111f",
        background_color: "#07111f",
        display: "standalone",
        lang: "da",
        start_url: "/",
        icons: [
          {
            src: "/pwa-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "/pwa-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
        ],
      },
      workbox: {
        importScripts: ["push-sw.js"],
        navigateFallback: "/index.html",
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/tiles\.openfreemap\.org\//,
            handler: "CacheFirst",
            options: {
              cacheName: "openfreemap",
              expiration: { maxEntries: 180, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: /\/(frames|nowcast)\/.*\.(webp|png)$/,
            handler: "CacheFirst",
            options: {
              cacheName: "radar-frames",
              expiration: { maxEntries: 24, maxAgeSeconds: 7200 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: { "/api": { target: "http://localhost:8080", changeOrigin: true } },
  },
});
