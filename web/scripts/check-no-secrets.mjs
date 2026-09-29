// Fails if a runtime AI credential could reach the browser (docs/WEB_ARCHITECTURE.md §6).
// Everything under src/, index.html and the built dist/ is public: it is shipped to every user.
// Prints file names and the matched rule only, never the matched text.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const targets = ["src", "index.html", "dist", "vite.config.ts"].map((p) => join(root, p)).filter(existsSync);

const rules = [
  ["server AI credential name", /\b(AI_API_KEY|AI_FALLBACK[12]_API_KEY|DEEPSEEK_API_KEY|DASHSCOPE_API_KEY|MOONSHOT_API_KEY|ZHIPU_API_KEY|AUTH_SECRET)\b/],
  ["public env var that looks secret", /\b(VITE|LEARNABLE_PUBLIC)_[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD)\b/],
  ["key-shaped string", /\bsk-[A-Za-z0-9_-]{20,}/],
];

// Local env files next to the web app would be read by Vite: none may define secrets.
for (const name of readdirSync(root)) {
  if (name.startsWith(".env")) targets.push(join(root, name));
}

const files = [];
const walk = (path) => {
  if (statSync(path).isDirectory()) {
    for (const entry of readdirSync(path)) if (entry !== "node_modules") walk(join(path, entry));
  } else if (!path.endsWith(".map") && !/\.(png|jpe?g|gif|ico|woff2?)$/.test(path)) {
    files.push(path);
  }
};
targets.forEach(walk);

const findings = [];
for (const file of files) {
  const text = readFileSync(file, "utf8");
  for (const [rule, pattern] of rules) {
    if (pattern.test(text)) findings.push(`${relative(root, file)}: ${rule}`);
  }
}

if (findings.length > 0) {
  console.error("Possible credential exposure in the browser bundle:\n  " + findings.join("\n  "));
  process.exit(1);
}
console.log(`No AI credentials in ${files.length} client files.`);
