#!/usr/bin/env node

import { existsSync } from "node:fs";
import { mkdir, open, readFile, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = process.cwd();
const RUNTIME_DIR = join(ROOT, "backend", "logs");
const STATE_PATH = join(RUNTIME_DIR, "kaleido-backend-stable.json");
const STOP_PATH = join(RUNTIME_DIR, "kaleido-backend-stable.stop");
const LOG_PATH = join(RUNTIME_DIR, "kaleido-backend-stable.log");
const HOST = process.env.KALEIDO_BACKEND_HOST || "127.0.0.1";
const PORT = String(process.env.KALEIDO_BACKEND_PORT || "5001");
const BASE_URL = `http://${HOST}:${PORT}`;
const HEALTH_URL = `${BASE_URL}/health`;
const RESTART_DELAY_MS = Number(process.env.KALEIDO_BACKEND_RESTART_DELAY_MS || 1500);
const WATCH_INTERVAL_MS = Number(process.env.KALEIDO_BACKEND_WATCH_INTERVAL_MS || 5000);
const WATCH_FAILURES_BEFORE_RESTART = Number(process.env.KALEIDO_BACKEND_WATCH_FAILURES || 2);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isPidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(Number(pid), 0);
    return true;
  } catch {
    return false;
  }
}

async function ensureRuntimeDir() {
  await mkdir(RUNTIME_DIR, { recursive: true });
}

async function readJson(filePath) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function writeState(state) {
  await ensureRuntimeDir();
  await writeFile(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
}

function runningState(extra = {}) {
  return {
    supervisorPid: process.pid,
    childPid: extra.childPid ?? null,
    root: ROOT,
    host: HOST,
    port: PORT,
    baseUrl: BASE_URL,
    healthUrl: HEALTH_URL,
    logPath: LOG_PATH,
    startedAt: extra.startedAt ?? new Date().toISOString(),
    status: "running",
    watchdog: {
      enabled: true,
      intervalMs: WATCH_INTERVAL_MS,
      failuresBeforeRestart: WATCH_FAILURES_BEFORE_RESTART,
      ...(extra.watchdog || {}),
    },
  };
}

async function appendLog(message) {
  await ensureRuntimeDir();
  await writeFile(LOG_PATH, `[${new Date().toISOString()}] ${message}\n`, { flag: "a" });
}

async function run(command, args) {
  const child = spawn(command, args, {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
  child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
  const code = await new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (status) => resolve(status ?? 1));
  });
  return { code, stdout, stderr };
}

async function listeningPids() {
  const result = await run("lsof", [`-tiTCP:${PORT}`, "-sTCP:LISTEN"]);
  if (result.code !== 0) return [];
  return result.stdout.trim().split(/\s+/).filter(Boolean);
}

async function processCommand(pid) {
  const result = await run("ps", ["-p", String(pid), "-o", "command="]);
  return result.stdout.trim();
}

async function checkHealth() {
  const response = await fetch(HEALTH_URL, { method: "GET", signal: AbortSignal.timeout(3000) });
  if (response.status !== 200) throw new Error(`health HTTP ${response.status}`);
  const payload = await response.json();
  if (payload?.status !== "ok") throw new Error("health payload is not ok");
  return {
    ok: true,
    status: response.status,
    service: payload.service || null,
    checkedAt: new Date().toISOString(),
  };
}

async function waitForReady(timeoutMs = 60_000) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      return await checkHealth();
    } catch (error) {
      lastError = error;
    }
    await sleep(1000);
  }
  throw lastError ?? new Error("等待 Kaleido 后端就绪超时");
}

async function assertPortAvailableForStart() {
  const state = await readJson(STATE_PATH);
  const supervisorAlive = isPidAlive(state?.supervisorPid);
  const knownPids = supervisorAlive
    ? new Set([state?.supervisorPid, state?.childPid].filter(Boolean).map(String))
    : new Set();
  const pids = await listeningPids();
  const unknown = pids.filter((pid) => !knownPids.has(String(pid)));
  if (unknown.length === 0) return;

  const details = [];
  for (const pid of unknown) details.push(`${pid}: ${await processCommand(pid)}`);
  throw new Error([
    `固定端口 ${PORT} 已被其他进程占用；Kaleido 看门狗不会自动换端口。`,
    ...details.map((line) => `  ${line}`),
    "请先停止占用进程，再运行 npm run backend:stable。",
  ].join("\n"));
}

function killProcessGroup(pid, signal = "SIGTERM") {
  if (!pid) return;
  try {
    process.kill(-Number(pid), signal);
  } catch {
    try {
      process.kill(Number(pid), signal);
    } catch {}
  }
}

async function start() {
  await ensureRuntimeDir();
  await rm(STOP_PATH, { force: true });
  const current = await readJson(STATE_PATH);
  if (current?.supervisorPid && isPidAlive(current.supervisorPid)) {
    const health = await checkHealth().catch(() => null);
    console.log(`Kaleido 后端看门狗已在运行：${current.baseUrl || BASE_URL}${health ? "（健康）" : "（正在恢复）"}`);
    console.log("状态：npm run backend:stable:status");
    return;
  }

  await assertPortAvailableForStart();
  const supervisor = spawn(process.execPath, [fileURLToPath(import.meta.url), "supervise"], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: {
      ...process.env,
      KALEIDO_BACKEND_HOST: HOST,
      KALEIDO_BACKEND_PORT: PORT,
    },
  });
  supervisor.unref();
  await writeState({
    supervisorPid: supervisor.pid,
    childPid: null,
    root: ROOT,
    host: HOST,
    port: PORT,
    baseUrl: BASE_URL,
    healthUrl: HEALTH_URL,
    logPath: LOG_PATH,
    startedAt: new Date().toISOString(),
    status: "starting",
  });

  const health = await waitForReady();
  console.log(`Kaleido 后端已固定并守护：${BASE_URL}（健康检查 HTTP ${health.status}）`);
  console.log("日志：npm run backend:stable:logs");
}

async function supervise() {
  await ensureRuntimeDir();
  await appendLog(`supervisor started for ${BASE_URL}`);
  let child = null;
  let stopping = false;
  let restartCount = 0;
  let lastStartedAt = null;
  let healthFailureStreak = 0;

  async function stopChild(signal = "SIGTERM") {
    if (!child?.pid) return;
    killProcessGroup(child.pid, signal);
    await sleep(800);
    if (isPidAlive(child.pid)) killProcessGroup(child.pid, "SIGKILL");
  }

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, async () => {
      stopping = true;
      await appendLog(`supervisor received ${signal}`);
      await stopChild(signal);
      process.exit(0);
    });
  }

  while (!stopping) {
    if (existsSync(STOP_PATH)) break;
    await assertPortAvailableForStart();
    const logFile = await open(LOG_PATH, "a");
    child = spawn("npm", ["run", "backend"], {
      cwd: ROOT,
      detached: true,
      stdio: ["ignore", logFile.fd, logFile.fd],
      env: {
        ...process.env,
        FLASK_HOST: HOST,
        FLASK_PORT: PORT,
        FLASK_USE_RELOADER: "false",
      },
    });
    lastStartedAt = new Date().toISOString();
    healthFailureStreak = 0;
    await writeState(runningState({
      childPid: child.pid,
      startedAt: lastStartedAt,
      watchdog: { restartCount, healthFailureStreak },
    }));
    await appendLog(`backend child started pid=${child.pid}`);

    let childExited = false;
    async function monitorHealth() {
      while (!stopping && !childExited && !existsSync(STOP_PATH)) {
        await sleep(WATCH_INTERVAL_MS);
        if (stopping || childExited || existsSync(STOP_PATH)) return;
        try {
          const health = await checkHealth();
          healthFailureStreak = 0;
          await writeState(runningState({
            childPid: child.pid,
            startedAt: lastStartedAt,
            watchdog: { restartCount, healthFailureStreak, lastHealth: health },
          }));
        } catch (error) {
          healthFailureStreak += 1;
          const message = error instanceof Error ? error.message : String(error);
          await appendLog(`watchdog health failed ${healthFailureStreak}/${WATCH_FAILURES_BEFORE_RESTART}: ${message}`);
          await writeState(runningState({
            childPid: child.pid,
            startedAt: lastStartedAt,
            watchdog: {
              restartCount,
              healthFailureStreak,
              lastFailure: { message, checkedAt: new Date().toISOString() },
            },
          }));
          if (healthFailureStreak >= WATCH_FAILURES_BEFORE_RESTART) {
            await appendLog("watchdog restarting backend after repeated health failures");
            await stopChild();
            return;
          }
        }
      }
    }
    void monitorHealth();

    const exit = await new Promise((resolve) => {
      child.on("exit", (code, signal) => {
        childExited = true;
        resolve({ code, signal });
      });
      child.on("error", (error) => {
        childExited = true;
        resolve({ code: 1, signal: null, error });
      });
    });
    await logFile.close();
    if (existsSync(STOP_PATH) || stopping) break;
    restartCount += 1;
    await appendLog(`backend child exited code=${exit.code ?? ""} signal=${exit.signal ?? ""}; restarting (${restartCount})`);
    await sleep(RESTART_DELAY_MS);
  }

  await stopChild();
  await writeState({
    supervisorPid: process.pid,
    childPid: null,
    root: ROOT,
    host: HOST,
    port: PORT,
    baseUrl: BASE_URL,
    healthUrl: HEALTH_URL,
    logPath: LOG_PATH,
    stoppedAt: new Date().toISOString(),
    status: "stopped",
  });
  await rm(STOP_PATH, { force: true });
  await appendLog("supervisor stopped");
}

async function stop() {
  const state = await readJson(STATE_PATH);
  await ensureRuntimeDir();
  await writeFile(STOP_PATH, `${new Date().toISOString()}\n`);
  if (state?.childPid && isPidAlive(state.childPid)) killProcessGroup(state.childPid);
  if (state?.supervisorPid && isPidAlive(state.supervisorPid)) {
    try { process.kill(Number(state.supervisorPid), "SIGTERM"); } catch {}
  }
  await sleep(1200);
  if (state?.childPid && isPidAlive(state.childPid)) killProcessGroup(state.childPid, "SIGKILL");
  if (state?.supervisorPid && isPidAlive(state.supervisorPid)) {
    try { process.kill(Number(state.supervisorPid), "SIGKILL"); } catch {}
  }
  await rm(STOP_PATH, { force: true });
  await writeState({ ...(state || {}), childPid: null, stoppedAt: new Date().toISOString(), status: "stopped" });
  console.log("Kaleido 后端看门狗已停止。");
}

async function status() {
  const state = await readJson(STATE_PATH);
  const pids = await listeningPids();
  const health = await checkHealth().catch(() => null);
  console.log(JSON.stringify({
    configuredBaseUrl: BASE_URL,
    state: state || null,
    supervisorAlive: isPidAlive(state?.supervisorPid),
    childAlive: isPidAlive(state?.childPid),
    listeningPids: pids,
    backendReady: Boolean(health),
    health,
    logPath: LOG_PATH,
  }, null, 2));
}

async function logs() {
  try {
    const lines = (await readFile(LOG_PATH, "utf8")).trimEnd().split(/\r?\n/);
    console.log(lines.slice(-120).join("\n"));
  } catch {
    console.log(`还没有日志：${LOG_PATH}`);
  }
}

async function restart() {
  await stop();
  await start();
}

async function main() {
  if (dirname(fileURLToPath(import.meta.url)) !== join(ROOT, "scripts")) {
    throw new Error("请从 Kaleido 仓库根目录运行该脚本。");
  }
  const command = process.argv[2] || "start";
  if (command === "start") return start();
  if (command === "supervise") return supervise();
  if (command === "stop") return stop();
  if (command === "restart") return restart();
  if (command === "status") return status();
  if (command === "logs") return logs();
  throw new Error(`未知命令：${command}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
