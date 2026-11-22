import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url));
const candidates = [
  process.env.PYTHON,
  path.join(repositoryRoot, ".venv", "bin", "python"),
  path.join(repositoryRoot, ".venv", "Scripts", "python.exe"),
  "python3",
  "python",
].filter(Boolean);

const python = candidates.find(
  (candidate) => candidate === "python3" || candidate === "python" || existsSync(candidate),
);

if (!python) {
  throw new Error("No Python interpreter found for the Playwright backend.");
}

const child = spawn(python, [path.join("frontend", "e2e", "backend_server.py")], {
  cwd: repositoryRoot,
  env: process.env,
  stdio: "inherit",
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
