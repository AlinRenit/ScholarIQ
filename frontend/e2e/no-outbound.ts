import fs from "node:fs";
import path from "node:path";

// Fails the run if the backend or the web server tried to open a connection
// to anything other than this machine (see e2e/offline/).
export default function noOutbound(): void {
  const dir = process.env.E2E_DIR;
  if (!dir) throw new Error("E2E_DIR is not set");
  const log = path.join(dir, "outbound.log");
  if (!fs.existsSync(log)) throw new Error(`The offline guard log is missing: ${log}`);
  const guards = path.join(dir, "guards.log");
  const loaded = fs.existsSync(guards) ? fs.readFileSync(guards, "utf8") : "";
  for (const runtime of ["python", "node"]) {
    if (!loaded.includes(`${runtime} `)) {
      throw new Error(
        `The ${runtime} offline guard was never loaded, so the check proves nothing.`,
      );
    }
  }
  const text = fs.readFileSync(log, "utf8").trim();
  if (text) {
    throw new Error(`Outbound network attempts were recorded during the offline run:\n${text}`);
  }
  console.log("Offline check: no outbound connection attempts by the API or web server.");
}
