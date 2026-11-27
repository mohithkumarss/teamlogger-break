import { defineConfig } from "vite";

// Tauri expects a fixed port and fails if it is taken.
export default defineConfig({
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    // the bundled font lives in ../fonts (shared with the Linux app)
    fs: { allow: [".."] },
    watch: { ignored: ["**/src-tauri/**", "**/dev-data/**"] },
  },
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
  },
});
