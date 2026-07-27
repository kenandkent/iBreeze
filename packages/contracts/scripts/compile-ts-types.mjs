#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, mkdirSync, writeFileSync } from "fs";
import { extname, join, resolve, dirname } from "path";
import { compile } from "json-schema-to-typescript";

const [,, inputDir, outputDirRaw, ...rest] = process.argv;

let outputDir = outputDirRaw;
let schemaCwd = resolve(inputDir);

for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--cwd" && i + 1 < rest.length) {
    schemaCwd = resolve(rest[i + 1]);
    i++;
  }
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

// Build $id -> file path map
const allFiles = collectSchemas(resolve(inputDir));
const idToFile = new Map();
const schemas = [];

for (const file of allFiles) {
  try {
    const content = readFileSync(file, "utf-8");
    const schema = JSON.parse(content);
    const relPath = file.replace(resolve(inputDir) + "/", "");
    schemas.push({ file, schema, relPath });
    if (schema.$id) {
      idToFile.set(schema.$id, file);
    }
  } catch {}
}

// Dereference $ref URLs that match local schemas
function dereferenceSchema(schema) {
  if (!schema || typeof schema !== "object") return schema;
  const copy = Array.isArray(schema) ? [...schema] : { ...schema };
  
  for (const key of Object.keys(copy)) {
    if (key === "$ref" && typeof copy[key] === "string") {
      const ref = copy[key];
      if (idToFile.has(ref)) {
        const targetFile = idToFile.get(ref);
        const targetContent = readFileSync(targetFile, "utf-8");
        const targetSchema = JSON.parse(targetContent);
        delete copy.$ref;
        Object.assign(copy, targetSchema);
        continue;
      }
    }
    if (typeof copy[key] === "object") {
      copy[key] = dereferenceSchema(copy[key]);
    }
  }
  return copy;
}

mkdirSync(outputDir, { recursive: true });

let generated = 0;
let errors = 0;

for (const { schema, relPath } of schemas) {
  const dereferenced = dereferenceSchema(schema);
  const outName = relPath.replace(/\.json$/, ".d.ts");
  const outFile = join(outputDir, outName);

  try {
    const ts = await compile(dereferenced, schema.title || "Schema", {
      style: { singleQuote: true, semiColons: true },
      bannerComment: "",
      unknownAny: false,
      strictIndexSignatures: true,
      enableConstEnums: false,
      unreachableDefinitions: false,
    });
    mkdirSync(dirname(outFile), { recursive: true });
    writeFileSync(outFile, ts);
    generated++;
  } catch (e) {
    // Try with minimal options
    try {
      const ts = await compile(dereferenced, schema.title || "Schema", {
        bannerComment: "",
      });
      mkdirSync(dirname(outFile), { recursive: true });
      writeFileSync(outFile, ts);
      generated++;
    } catch {
      errors++;
    }
  }
}

console.log(`Generated ${generated} files (${errors} errors)`);
if (errors > 0) process.exit(1);
