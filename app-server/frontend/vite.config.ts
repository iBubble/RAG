import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import type { Plugin } from 'vite'

function noStoreHtmlPlugin(): Plugin {
  return {
    name: 'no-store-html',
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        delete req.headers['if-none-match'];
        delete req.headers['if-modified-since'];

        const origSetHeader = res.setHeader.bind(res);
        res.setHeader = function (name: string, value: any) {
          if (name.toLowerCase() === 'cache-control') {
            value = 'no-store, must-revalidate';
          }
          return origSetHeader(name, value);
        };
        next();
      });
    },
  };
}

const sseProxyConfig = {
  target: 'http://127.0.0.1:8003', // 指向网关新端口 8003
  changeOrigin: true,
  timeout: 600000,
  proxyTimeout: 600000,
  selfHandleResponse: false,
  configure: (proxy: any) => {
    proxy.on('proxyReq', (proxyReq: any, req: any) => {
      if (req.url?.includes('/api/files/upload')) {
        proxyReq.socket?.setTimeout(0);
        proxyReq.setTimeout(0);
      }
    });
    proxy.on('proxyRes', (proxyRes: any, _req: any, res: any) => {
      const contentType = proxyRes.headers['content-type'] || '';
      if (contentType.includes('text/event-stream')) {
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
        res.setHeader('X-Accel-Buffering', 'no');
        res.setHeader('Content-Encoding', 'identity');
        
        if (typeof res.flushHeaders === 'function') {
          res.flushHeaders();
        }
      }
    });
    proxy.on('open', (proxySocket: any) => {
      proxySocket.on('data', () => { /* keep alive */ });
    });
    proxy.on('error', (err: any, _req: any, res: any) => {
      console.error('[Proxy Error]', err.message);
      if (res && !res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ detail: `Proxy error: ${err.message}` }));
      }
    });
  }
};

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    noStoreHtmlPlugin(),
  ],
  server: {
    port: 2028, // 前端运行端口 2028
    host: '0.0.0.0',
    allowedHosts: ['rag.syhsgis.com', 'rag1.syhsgis.com', 'lawrag.liukun.com', 'rag.liukun.com'],
    proxy: {
      '/api': sseProxyConfig
    }
  },
  preview: {
    port: 2028, // 前端预览端口 2028
    host: '0.0.0.0',
    allowedHosts: ['rag.syhsgis.com', 'rag1.syhsgis.com', 'lawrag.liukun.com', 'rag.liukun.com'],
    proxy: {
      '/api': sseProxyConfig
    }
  },
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-v4-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    }
  }
})
