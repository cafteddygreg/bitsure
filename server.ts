import http from "node:http";
import { execFile } from "node:child_process";

const PORT = Number(process.env.PORT || 3000);

function getTestSummary(): Promise<string> {
  return new Promise((resolve) => {
    execFile("python3", ["-m", "unittest", "discover", "-s", "tests", "-v"], { timeout: 10000 }, (err, stdout, stderr) => {
      const output = `${stdout || ""}\n${stderr || ""}`.trim();
      resolve(output || (err ? String(err) : "Tests OK"));
    });
  });
}

const server = http.createServer(async (req, res) => {
  if (req.url === "/api/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", service: "bitsure-teddy" }));
    return;
  }

  const testOutput = await getTestSummary();
  const escaped = testOutput
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(`<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Bitsure Teddy — Trading Bot Engine</title>
  <meta name="description" content="High-frequency algorithmic crypto trading bot and safety monitoring engine for Binance Spot & Futures." />
  <style>
    body { background: #0b0f17; color: #e2e8f0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; margin: 0; padding: 2rem; }
    .card { max-width: 960px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 1.5rem; }
    h1 { margin-top: 0; color: #38bdf8; font-size: 1.35rem; }
    .badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 4px; background: #065f46; color: #d1fae5; font-size: 0.8rem; margin-bottom: 1rem; }
    pre { background: #030712; padding: 1rem; border-radius: 6px; overflow-x: auto; border: 1px solid #1e293b; color: #a7f3d0; font-size: 0.85rem; line-height: 1.4; }
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">PYTHON ENGINE READY</span>
    <h1>Bitsure Teddy — Diagnostic &amp; Suite de Tests</h1>
    <pre>${escaped}</pre>
  </div>
</body>
</html>`);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log("Bitsure Teddy status server listening on http://0.0.0.0:" + PORT);
});
