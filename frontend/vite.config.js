import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

function getBackendTarget() {
  try {
    const portFile = path.resolve(__dirname, '../runtime/port.json');
    if (fs.existsSync(portFile)) {
      const data = JSON.parse(fs.readFileSync(portFile, 'utf8'));
      if (data.port) return `http://${data.host || '127.0.0.1'}:${data.port}`;
    }
  } catch {}
  return `http://127.0.0.1:${process.env.BACKEND_PORT || 8765}`;
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: Object.fromEntries(
      ['/health','/status','/transcribe','/tickets','/ticket-ideas','/task-options','/tasks','/validate','/fill','/screenshots','/agent'].map(endpoint => [
        endpoint,
        {
          target: getBackendTarget(),
          changeOrigin: true,
          // Vite's proxy ignores `router`; re-read runtime/port.json on every
          // request so a backend that moved to another port is still reached.
          configure: proxy => {
            const web = proxy.web.bind(proxy);
            proxy.web = (req, res, options, ...rest) => web(req, res, {...options, target: getBackendTarget()}, ...rest);
          }
        }
      ])
    )
  }
});
