import express from 'express';
import { spawn, ChildProcess } from 'child_process';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = Number(process.env.PORT || 3000);
const PYTHON_PORT = Number(process.env.PYTHON_API_PORT || 8001);

let pythonProc: ChildProcess | null = null;
let botProc: ChildProcess | null = null;

function startTelegramBotIfConfigured() {
  if (botProc) return;
  if (!process.env.TELEGRAM_TOKEN || process.env.START_TELEGRAM_BOT !== '1') return;
  console.log('[server] START_TELEGRAM_BOT=1 detected — starting Bitsure Teddy Telegram Bot (main.py)...');
  botProc = spawn('python3', ['main.py'], {
    cwd: __dirname,
    env: {
      ...process.env,
      PYTHONPATH: __dirname,
      DISABLE_EMBEDDED_WEB: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  botProc.stdout?.on('data', (chunk) => {
    process.stdout.write(`[bot] ${chunk}`);
  });

  botProc.stderr?.on('data', (chunk) => {
    process.stderr.write(`[bot] ${chunk}`);
  });

  botProc.on('exit', (code) => {
    console.warn(`[server] Telegram Bot exited with code ${code}. Restarting in 5s...`);
    botProc = null;
    setTimeout(startTelegramBotIfConfigured, 5000);
  });
}

function startPythonBackend() {
  if (pythonProc) return;
  console.log(`[server] Starting Python Bitsure Teddy API server on port ${PYTHON_PORT}...`);
  pythonProc = spawn('python3', ['web_api_server.py'], {
    cwd: __dirname,
    env: {
      ...process.env,
      PYTHONPATH: __dirname,
      PYTHON_API_PORT: String(PYTHON_PORT),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProc.stdout?.on('data', (chunk) => {
    process.stdout.write(`[python] ${chunk}`);
  });

  pythonProc.stderr?.on('data', (chunk) => {
    process.stderr.write(`[python] ${chunk}`);
  });

  pythonProc.on('exit', (code) => {
    console.warn(`[server] Python API server exited with code ${code}. Restarting in 1.5s...`);
    pythonProc = null;
    setTimeout(startPythonBackend, 1500);
  });
}

async function waitForPythonReady(timeoutMs = 15000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ok = await new Promise<boolean>((resolve) => {
      const req = http.get(`http://127.0.0.1:${PYTHON_PORT}/api/auth/me`, (res) => {
        res.resume();
        resolve((res.statusCode || 500) < 500);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(1000, () => {
        req.destroy();
        resolve(false);
      });
    });
    if (ok) return true;
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

async function createServer() {
  startPythonBackend();
  await waitForPythonReady(12000);

  const app = express();

  // Proxy /api/* and /auth/* directly to the Python Bitsure Teddy engine on 127.0.0.1:8001
  app.use(['/api', '/auth'], (req, res) => {
    const targetPath = `${req.baseUrl}${req.url}`;
    const options: http.RequestOptions = {
      hostname: '127.0.0.1',
      port: PYTHON_PORT,
      path: targetPath,
      method: req.method,
      headers: {
        ...req.headers,
        host: `127.0.0.1:${PYTHON_PORT}`,
      },
    };

    const proxyReq = http.request(options, (proxyRes) => {
      res.status(proxyRes.statusCode || 200);
      Object.entries(proxyRes.headers).forEach(([k, v]) => {
        if (v !== undefined) res.setHeader(k, v);
      });
      proxyRes.pipe(res, { end: true });
    });

    proxyReq.on('error', (err) => {
      console.error(`[proxy] Error forwarding ${req.method} ${targetPath}:`, err.message);
      if (!res.headersSent) {
        res.status(502).json({
          ok: false,
          error: `Python backend connecting (${err.message}). Please retry in a moment.`,
        });
      }
    });

    req.pipe(proxyReq, { end: true });
  });

  if (process.env.NODE_ENV === 'production') {
    const distPath = path.join(__dirname, 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  } else {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, hmr: false },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[server] Bitsure Teddy Platform listening on http://0.0.0.0:${PORT}`);
  });
}

createServer().catch((err) => {
  console.error('[server] Fatal startup error:', err);
  process.exit(1);
});
