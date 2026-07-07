import { spawn } from "node:child_process";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";

const host = "127.0.0.1";
const port = 5173;
const baseUrl = `http://${host}:${port}`;
const startupTimeoutMs = 60_000;
const pollIntervalMs = 300;
const args = process.argv.slice(2);

let viteProcess;

function spawnNode(script, scriptArgs) {
  return spawn(process.execPath, [script, ...scriptArgs], {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
    windowsHide: true
  });
}

async function waitForServer() {
  const startedAt = Date.now();
  while (Date.now() - startedAt < startupTimeoutMs) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok || response.status < 500) {
        return;
      }
    } catch {
      // Server is not ready yet.
    }
    await delay(pollIntervalMs);
  }

  throw new Error(`Timed out waiting for Vite dev server at ${baseUrl}`);
}

async function stopVite() {
  if (!viteProcess || viteProcess.exitCode !== null || viteProcess.signalCode !== null) {
    return;
  }

  const exit = once(viteProcess, "exit").then(() => "exit");
  const timeout = delay(2_000).then(() => "timeout");
  viteProcess.kill();
  const result = await Promise.race([exit, timeout]);
  if (result === "timeout") {
    viteProcess.kill("SIGKILL");
  }
}

try {
  viteProcess = spawnNode("./node_modules/vite/bin/vite.js", ["--host", host]);
  await waitForServer();

  const playwrightProcess = spawnNode("./node_modules/playwright/cli.js", ["test", ...args]);
  const [code, signal] = await once(playwrightProcess, "exit");
  await stopVite();

  if (signal) {
    console.error(`Playwright exited with signal ${signal}`);
    process.exitCode = 1;
  } else {
    process.exitCode = code ?? 1;
  }
} catch (error) {
  await stopVite();
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
