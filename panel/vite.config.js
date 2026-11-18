import { defineConfig } from 'vite';

// El panel se sirve como SPA: cualquier ruta vuelve a index.html (ver nginx.conf).
export default defineConfig({
  server: { port: 5500, strictPort: true },
  preview: { port: 5500 },
  build: { outDir: 'dist', emptyOutDir: true },
});
