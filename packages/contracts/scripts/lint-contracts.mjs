#!/usr/bin/env node

import { readFileSync, readdirSync, existsSync, statSync } from "fs";
import { join, dirname, extname, resolve } from "path";
import { fileURLToPath, pathToFileURL } from "url";
import Ajv from "ajv";
import addFormats from "ajv-formats";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const SCHEMA_DIRS = [
  "events",
  "domain-events",
  "artifacts",
  "approvals",
  "skill",
  "../rpc-schema",
  "routing",
];

const SKIP_FILES = new Set([
  "registry.v1.json",
  "reverse-methods.v1.json",
  "meta.schema.json",
]);

function collectAllSchemaFiles() {
  const files = [];
  for (const dir of SCHEMA_DIRS) {
    const dirPath = join(ROOT, dir);
    if (!existsSync(dirPath)) {
      console.log(`SKIP: ${dir} (not found)`);
      continue;
    }
    const entries = readdirSync(dirPath, { recursive: true });
    for (const entry of entries) {
      const full = join(dirPath, entry);
      if (extname(entry) === ".json" && statSync(full).isFile()) {
        const basename = entry.split("/").pop() || entry;
        if (SKIP_FILES.has(basename)) continue;
        files.push(full);
      }
    }
  }
  return files;
}

let errors = 0;
const allIds = new Map();
const schemas = [];
const files = collectAllSchemaFiles();

if (files.length === 0) {
  console.error("FATAL: no schema files found");
  process.exit(1);
}

// Phase 1: Parse all schemas and check basic structure
for (const filePath of files) {
  try {
    const content = readFileSync(filePath, "utf-8");
    const schema = JSON.parse(content);
    schemas.push({ filePath, schema, content });

    if (schema.$id) {
      if (allIds.has(schema.$id)) {
        console.error(
          `DUPLICATE $id: ${schema.$id} in ${filePath} and ${allIds.get(schema.$id)}`,
        );
        errors++;
      } else {
        allIds.set(schema.$id, filePath);
      }
    }
  } catch (e) {
    const rel = filePath.replace(ROOT + "/", "");
    console.error(`PARSE_FAIL: ${rel} - ${e.message}`);
    errors++;
  }
}

// Phase 2: Validate structure
for (const { filePath, schema } of schemas) {
  const rel = filePath.replace(ROOT + "/", "");
  try {
    if (!schema.$schema || !schema.$schema.includes("json-schema.org/")) {
      throw new Error(`missing or invalid $schema`);
    }
    if (!schema.$id) {
      throw new Error(`missing $id`);
    }
    console.log(`OK: ${rel}`);
  } catch (e) {
    console.error(`FAIL: ${rel} - ${e.message}`);
    errors++;
  }
}

// Build a map of file path -> $id for relative $ref resolution
const filePathToId = new Map();
for (const { filePath, schema } of schemas) {
  if (schema.$id) {
    filePathToId.set(filePath, schema.$id);
  }
}

// Phase 3: AJV compilation in a second pass (with all schemas loaded)
const ajv = new Ajv({
  strictSchema: false,
  validateFormats: true,
  allowUnionTypes: true,
  strict: false,
  validateSchema: false,
});
addFormats(ajv);

// First add all schemas to AJV
for (const { filePath, schema } of schemas) {
  try {
    if (schema.$id) {
      ajv.addSchema(schema, schema.$id);
    }
    // Also register by file URI so relative $ref paths resolve
    const fileUri = pathToFileURL(resolve(filePath)).href;
    ajv.addSchema(schema, fileUri);
  } catch (e) {
    // Ignore add errors, we'll catch them in compilation
  }
}

// Then compile each
for (const { filePath, schema } of schemas) {
  const rel = filePath.replace(ROOT + "/", "");
  try {
    ajv.compile(schema);
  } catch (e) {
    console.error(`COMPILE_FAIL: ${rel} - ${e.message}`);
    errors++;
  }
}

// Phase 4: Check for broken $ref references
function resolveRefTarget(target, sourceFile) {
  if (target.startsWith("#")) return null;
  const fragment = target.includes("#") ? target.split("#")[1] : null;
  const base = target.includes("#") ? target.split("#")[0] : target;
  if (base.startsWith("http")) return null;
  if (base.startsWith("file://")) return null;
  // Resolve relative paths against the source file's directory
  const resolved = resolve(dirname(sourceFile), base);
  const fileUri = pathToFileURL(resolved).href;
  // Look up by file URI or by $id
  return { resolved, fileUri };
}

for (const [id, filePath] of allIds) {
  const content = readFileSync(filePath, "utf-8");
  const schema = JSON.parse(content);
  const strContent = JSON.stringify(schema);
  const refMatches = strContent.match(/\$ref":\s*"([^"]+)"/g) || [];
  for (const ref of refMatches) {
    const target = ref.match(/\$ref":\s*"([^"]+)"/)[1];
    if (target.startsWith("#")) continue;
    const resolvedId = target.includes("#") ? target.split("#")[0] : target;
    if (resolvedId && allIds.has(resolvedId)) continue;
    if (resolvedId && resolvedId.startsWith("http")) continue;
    // Check relative path resolution
    const resolved = resolveRefTarget(target, filePath);
    if (resolved) {
      if (allIds.has(resolved.fileUri)) continue;
      if (filePathToId.has(resolved.resolved) || filePathToId.has(resolved.fileUri)) continue;
    }
    console.error(
      `BROKEN_REF: ${filePath} references "${target}" but no schema has $id="${resolvedId}"`,
    );
    errors++;
  }
}

if (errors > 0) {
  console.error(`\n${errors} schema validation error(s) found`);
  process.exit(1);
}

console.log(`\nAll ${files.length} schemas valid`);
process.exit(0);
