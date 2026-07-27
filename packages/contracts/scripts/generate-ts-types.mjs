#!/usr/bin/env node
import { readFileSync, readdirSync, existsSync, statSync, mkdirSync, writeFileSync } from "fs";
import { join, extname, dirname, resolve } from "path";
import { pathToFileURL } from "url";

const [,, inputDir, outputDir, ...rest] = process.argv;

if (!inputDir || !outputDir) {
  console.error("Usage: generate-ts-types.mjs <input-dir> <output-dir> [--cwd <dir>]");
  process.exit(1);
}

const cwdIdx = rest.indexOf("--cwd");
const schemaCwd = cwdIdx >= 0 ? resolve(rest[cwdIdx + 1]) : resolve(inputDir);

const otherArgs = [];
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--cwd") { i++; continue; }
  otherArgs.push(rest[i]);
}

// Collect all schema files
function collectSchemas(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { recursive: true })) {
    const full = join(dir, entry);
    if (extname(entry) === ".json" && statSync(full).isFile()) {
      const content = readFileSync(full, "utf-8");
      if (content.includes('"$schema"') || content.includes('"$id"')) {
        files.push(full);
      }
    }
  }
  return files;
}

// Build a map of $id -> absolute file path
function buildIdMap(files) {
  const map = new Map();
  for (const file of files) {
    try {
      const schema = JSON.parse(readFileSync(file, "utf-8"));
      if (schema.$id) {
        map.set(schema.$id, file);
      }
    } catch {}
  }
  return map;
}

const allSchemas = collectSchemas(resolve(inputDir));
const idToFile = buildIdMap(allSchemas);

// Build a JSON-Schema $defs bundle with all schemas by $id
const bundle = { $defs: {} };
for (const file of allSchemas) {
  const schema = JSON.parse(readFileSync(file, "utf-8"));
  if (schema.$id) {
    bundle.$defs[schema.$id] = schema;
  }
}

// Write the bundle to a temp file
const tmpDir = outputDir + ".tmp";
mkdirSync(tmpDir, { recursive: true });
const bundlePath = join(tmpDir, "schema-bundle.json");
writeFileSync(bundlePath, JSON.stringify(bundle, null, 2));

// Generate from the bundle using json2ts
const { execSync } = await import("child_process");
const args = [
  "json2ts",
  "-i", bundlePath,
  "-o", outputDir,
  ...otherArgs,
];
try {
  execSync(`npx ${args.join(" ")}`, {
    stdio: "inherit",
    cwd: dirname(import.meta.url.replace("file://", "")),
  });
} catch (e) {
  process.exit(1);
}
