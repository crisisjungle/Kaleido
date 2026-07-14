#!/usr/bin/env node

import { existsSync } from "node:fs";
import { mkdir, open, readFile, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = process.cwd();
const RUNTIME_DIR = join(ROOT, "backend", "logs");
const STATE_PATH = join(RUNTIME_DIR, "kaleido-frontend-stable.json");
const STOP_PATH = join(RUNTIME_DIR, "kaleido-frontend-stable.stop");
const LOG_PATH = join(RUNTIME_DIR, "kaleido-frontend-stable.log");
const HOST = process.env.KALEIDO_FRONTEND_HOST || "127.0.0.1";
const PORT = String(process.env.KALEIDO_FRONTEND_PORT || "3000");
const BASE_URL = `http://${HOST}:${PORT}`;
const LEGACY_FRONTEND_PORTS = (process.env.KALEIDO_FRONTEND_LEGACY_PORTS ?? "3001")
  .split(",")
  .map((port) => port.trim())
  .filter((port) => port && port !== PORT);
const WATCH_INTERVAL_MS = Number(process.env.KALEIDO_FRONTEND_WATCH_INTERVAL_MS || 5000);
const WATCH_FAILURES = Number(process.env.KALEIDO_FRONTEND_WATCH_FAILURES || 2);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function isAlive(pid) {
  if (!pid) return false;
  try { process.kill(Number(pid), 0); return true; } catch { return false; }
}

async function ensureRuntimeDir() {
  await mkdir(RUNTIME_DIR, { recursive: true });
}

async function readState() {
  try { return JSON.parse(await readFile(STATE_PATH, "utf8")); } catch { return null; }
}

async function writeState(state) {
  await ensureRuntimeDir();
  await writeFile(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
}

async function log(message) {
  await ensureRuntimeDir();
  await writeFile(LOG_PATH, `[${new Date().toISOString()}] ${message}\n`, { flag: "a" });
}

async function run(command, args) {
  const child = spawn(command, args, { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
  const code = await new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (status) => resolve(status ?? 1));
  });
  return { code, stdout };
}

async function listeningPids(port = PORT) {
  const result = await run("lsof", [`-tiTCP:${port}`, "-sTCP:LISTEN"]);
  return result.code === 0 ? result.stdout.trim().split(/\s+/).filter(Boolean) : [];
}

async function processCommand(pid) {
  return (await run("ps", ["-p", String(pid), "-o", "command="])).stdout.trim();
}

async function checkHealth() {
  const response = await fetch(BASE_URL, { signal: AbortSignal.timeout(3000) });
  if (response.status !== 200) throw new Error(`frontend HTTP ${response.status}`);
  const html = await response.text();
  if (!html.includes('id="app"')) throw new Error("frontend shell is incomplete");
  return { ok: true, status: response.status, checkedAt: new Date().toISOString() };
}

async function waitForReady(timeoutMs = 60_000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try { return await checkHealth(); } catch (error) { lastError = error; }
    await sleep(1000);
  }
  throw lastError || new Error("等待 Kaleido 前端就绪超时");
}

async function assertPortAvailable() {
  const state = await readState();
  const pids = await listeningPids();
  if (pids.length === 0) return;
  if (isAlive(state?.supervisorPid) && isAlive(state?.childPid)) return;
  const details = [];
  for (const pid of pids) details.push(`${pid}: ${await processCommand(pid)}`);
  throw new Error([
    `固定端口 ${PORT} 已被其他进程占用；Kaleido 前端看门狗不会自动换端口。`,
    ...details.map((line) => `  ${line}`),
    "请先停止占用进程，再运行 npm run frontend:stable。",
  ].join("\n"));
}

async function startLegacyRedirects() {
  const redirects = [];
  for (const port of LEGACY_FRONTEND_PORTS) {
    const server = createServer((request, response) => {
      const location = `${BASE_URL}${request.url || "/"}`;
      response.writeHead(302, { Location: location, "Cache-Control": "no-store" });
      response.end(`Kaleido frontend moved to ${location}\n`);
    });
    const result = await new Promise((resolve) => {
      server.once("error", (error) => resolve({ ok: false, error }));
      server.listen(Number(port), HOST, () => resolve({ ok: true }));
    });
    if (result.ok) {
      await log(`legacy frontend redirect listening on http://${HOST}:${port} -> ${BASE_URL}`);
      redirects.push({ port, target: BASE_URL, status: "listening", server });
    } else {
      const message = result.error instanceof Error ? result.error.message : String(result.error);
      await log(`legacy frontend redirect skipped on ${port}: ${message}`);
      redirects.push({ port, target: BASE_URL, status: "skipped", message });
    }
  }
  return redirects;
}

async function stopLegacyRedirects(redirects) {
  await Promise.all((redirects || [])
    .filter((redirect) => redirect.server)
    .map((redirect) => new Promise((resolve) => redirect.server.close(() => resolve()))));
}

function killGroup(pid, signal = "SIGTERM") {
  if (!pid) return;
  try { process.kill(-Number(pid), signal); } catch {
    try { process.kill(Number(pid), signal); } catch {}
  }
}

function runningState(childPid, startedAt, restartCount, health = null, failure = null, redirects = []) {
  return {
    supervisorPid: process.pid,
    childPid,
    root: ROOT,
    host: HOST,
    port: PORT,
    baseUrl: BASE_URL,
    logPath: LOG_PATH,
    legacyRedirects: redirects.map(({ port, target, status, message }) => ({ port, target, status, ...(message ? { message } : {}) })),
    startedAt,
    status: "running",
    watchdog: {
      enabled: true,
      intervalMs: WATCH_INTERVAL_MS,
      failuresBeforeRestart: WATCH_FAILURES,
      restartCount,
      healthFailureStreak: failure?.streak || 0,
      ...(health ? { lastHealth: health } : {}),
      ...(failure ? { lastFailure: failure } : {}),
    },
  };
}

async function start() {
  await ensureRuntimeDir();
  await rm(STOP_PATH, { force: true });
  const state = await readState();
  if (isAlive(state?.supervisorPid)) {
    const healthy = await checkHealth().then(() => true).catch(() => false);
    console.log(`Kaleido 前端看门狗已在运行：${BASE_URL}${healthy ? "（健康）" : "（正在恢复）"}`);
    return;
  }
  await assertPortAvailable();
  const supervisor = spawn(process.execPath, [fileURLToPath(import.meta.url), "supervise"], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, KALEIDO_FRONTEND_HOST: HOST, KALEIDO_FRONTEND_PORT: PORT },
  });
  supervisor.unref();
  await writeState({ supervisorPid: supervisor.pid, childPid: null, root: ROOT, host: HOST, port: PORT, baseUrl: BASE_URL, logPath: LOG_PATH, status: "starting" });
  const health = await waitForReady();
  console.log(`Kaleido 前端已固定并守护：${BASE_URL}（HTTP ${health.status}）`);
}

async function supervise() {
  await ensureRuntimeDir();
  await log(`supervisor started for ${BASE_URL}`);
  let child;
  let stopping = false;
  let restartCount = 0;
  const redirects = await startLegacyRedirects();

  async function stopChild() {
    if (!child?.pid) return;
    killGroup(child.pid);
    await sleep(800);
    if (isAlive(child.pid)) killGroup(child.pid, "SIGKILL");
  }

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, async () => {
      stopping = true;
      await log(`supervisor received ${signal}`);
      await stopChild();
      await stopLegacyRedirects(redirects);
      process.exit(0);
    });
  }

  while (!stopping && !existsSync(STOP_PATH)) {
    await assertPortAvailable();
    const logFile = await open(LOG_PATH, "a");
    child = spawn("npm", ["--prefix", "frontend", "run", "dev", "--", "--host", HOST, "--port", PORT, "--strictPort", "--no-open"], {
      cwd: ROOT,
      detached: true,
      stdio: ["ignore", logFile.fd, logFile.fd],
    });
    const startedAt = new Date().toISOString();
    let failureStreak = 0;
    let childExited = false;
    await writeState(runningState(child.pid, startedAt, restartCount, null, null, redirects));
    await log(`frontend child started pid=${child.pid}`);

    async function monitor() {
      while (!stopping && !childExited && !existsSync(STOP_PATH)) {
        await sleep(WATCH_INTERVAL_MS);
        if (stopping || childExited || existsSync(STOP_PATH)) return;
        try {
          const health = await checkHealth();
          failureStreak = 0;
          await writeState(runningState(child.pid, startedAt, restartCount, health, null, redirects));
        } catch (error) {
          failureStreak += 1;
          const message = error instanceof Error ? error.message : String(error);
          await log(`watchdog health failed ${failureStreak}/${WATCH_FAILURES}: ${message}`);
          await writeState(runningState(child.pid, startedAt, restartCount, null, { streak: failureStreak, message, checkedAt: new Date().toISOString() }, redirects));
          if (failureStreak >= WATCH_FAILURES) {
            await log("watchdog restarting frontend after repeated health failures");
            await stopChild();
            return;
          }
        }
      }
    }
    void monitor();

    const exit = await new Promise((resolve) => {
      child.on("exit", (code, signal) => { childExited = true; resolve({ code, signal }); });
      child.on("error", (error) => { childExited = true; resolve({ code: 1, signal: null, error }); });
    });
    await logFile.close();
    if (stopping || existsSync(STOP_PATH)) break;
    restartCount += 1;
    await log(`frontend child exited code=${exit.code ?? ""} signal=${exit.signal ?? ""}; restarting (${restartCount})`);
    await sleep(1500);
  }
  await stopChild();
  await stopLegacyRedirects(redirects);
  await writeState({ ...(await readState()), childPid: null, status: "stopped", stoppedAt: new Date().toISOString() });
  await rm(STOP_PATH, { force: true });
}

async function stop() {
  const state = await readState();
  await ensureRuntimeDir();
  await writeFile(STOP_PATH, `${new Date().toISOString()}\n`);
  if (isAlive(state?.childPid)) killGroup(state.childPid);
  if (isAlive(state?.supervisorPid)) {
    try { process.kill(Number(state.supervisorPid), "SIGTERM"); } catch {}
  }
  await sleep(1200);
  if (isAlive(state?.childPid)) killGroup(state.childPid, "SIGKILL");
  if (isAlive(state?.supervisorPid)) {
    try { process.kill(Number(state.supervisorPid), "SIGKILL"); } catch {}
  }
  await rm(STOP_PATH, { force: true });
  await writeState({ ...(state || {}), childPid: null, status: "stopped", stoppedAt: new Date().toISOString() });
  console.log("Kaleido 前端看门狗已停止。");
}

async function status() {
  const state = await readState();
  const health = await checkHealth().catch(() => null);
  console.log(JSON.stringify({
    configuredBaseUrl: BASE_URL,
    state,
    supervisorAlive: isAlive(state?.supervisorPid),
    childAlive: isAlive(state?.childPid),
    listeningPids: await listeningPids(),
    legacyRedirects: await Promise.all(LEGACY_FRONTEND_PORTS.map(async (port) => ({ port, target: BASE_URL, listeningPids: await listeningPids(port) }))),
    frontendReady: Boolean(health),
    health,
    logPath: LOG_PATH,
  }, null, 2));
}

async function logs() {
  try {
    const lines = (await readFile(LOG_PATH, "utf8")).trimEnd().split(/\r?\n/);
    console.log(lines.slice(-120).join("\n"));
  } catch { console.log(`还没有日志：${LOG_PATH}`); }
}

async function main() {
  const command = process.argv[2] || "start";
  if (command === "start") return start();
  if (command === "supervise") return supervise();
  if (command === "stop") return stop();
  if (command === "restart") { await stop(); return start(); }
  if (command === "status") return status();
  if (command === "logs") return logs();
  throw new Error(`未知命令：${command}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
