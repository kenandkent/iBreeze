#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, mkdirSync, writeFileSync } from "fs";
import { extname, join, resolve, dirname } from "path";

const [,, inputDir, outputDir] = process.argv;

if (!inputDir || !outputDir) {
  console.error("Usage: bundle-schemas.mjs <input-dir> <output-dir>");
  process.exit(1);
}

// Collect all schema files
function collectSchemas(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { recursive: true })) {
    const full = join(dir, entry);
    if (extname(entry) === ".json" && statSync(full).isFile()) {
      const content = readFileSync(full, "utf-8");
      const low = content.toLowerCase();
      if (low.includes('"$schema"') || low.includes('"$id"')) {
        files.push(full);
      }
    }
  }
  return files;
}

// Build $id -> file path map
const allFiles = collectSchemas(resolve(inputDir));
const idToFile = new Map();

for (const file of allFiles) {
  try {
    const schema = JSON.parse(readFileSync(file, "utf-8"));
    if (schema.$id) {
      idToFile.set(schema.$id, file);
    }
  } catch {}
}

// Dereference $ref URLs that match local schemas (inline them)
function dereference(schema, visited = new Set()) {
  if (!schema || typeof schema !== "object") return schema;
  if (visited.has(schema)) return schema;
  visited.add(schema);

  const copy = Array.isArray(schema) ? [...schema] : { ...schema };

  for (const key of Object.keys(copy)) {
    if (key === "$ref" && typeof copy[key] === "string") {
      const ref = copy[key];
      if (idToFile.has(ref)) {
        const target = JSON.parse(readFileSync(idToFile.get(ref), "utf-8"));
        delete copy.$ref;
        // Merge target into copy, preserving copy's own properties
        for (const k of Object.keys(target)) {
          if (!(k in copy)) {
            copy[k] = target[k];
          }
        }
        // Recursively dereference the merged target
        for (const k of Object.keys(target)) {
          if (k !== "$id" && k !== "$schema") {
            copy[k] = dereference(copy[k], visited);
          }
        }
        continue;
      }
    }
    if (typeof copy[key] === "object") {
      copy[key] = dereference(copy[key], visited);
    }
  }
  return copy;
}

mkdirSync(outputDir, { recursive: true });

for (const file of allFiles) {
  const relPath = file.replace(resolve(inputDir) + "/", "");
  const schema = JSON.parse(readFileSync(file, "utf-8"));
  const bundled = dereference(schema);
  const outFile = join(outputDir, relPath);
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, JSON.stringify(bundled, null, 2));
}

console.log(`Bundled ${allFiles.length} schemas to ${outputDir}`);
