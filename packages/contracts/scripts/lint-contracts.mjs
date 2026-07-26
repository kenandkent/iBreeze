#!/usr/bin/env node

import { readFileSync, readdirSync, existsSync, statSync } from "fs";
import { join, dirname, extname } from "path";
import { fileURLToPath } from "url";
import Ajv from "ajv";
import addFormats from "ajv-formats";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const SCHEMA_DIRS = [
  "events",
  "domain-events",
  "artifacts",
  "skill",
  "../rpc-schema",
];

const ajv = new Ajv({
  strictSchema: true,
  validateFormats: true,
  allowUnionTypes: true,
});
addFormats(ajv);

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
        files.push(full);
      }
    }
  }
  return files;
}

function validateSchema(filePath, schema) {
  if (!schema.$schema || !schema.$schema.includes("json-schema.org/")) {
    throw new Error(`missing or invalid $schema`);
  }
  if (!schema.$id) {
    throw new Error(`missing $id`);
  }
  if (!schema.title) {
    throw new Error(`missing title`);
  }
  if (!schema.type && !schema.anyOf && !schema.oneOf && !schema.$ref) {
    throw new Error(`missing type, anyOf, oneOf, or $ref`);
  }
  try {
    ajv.compile(schema);
  } catch (e) {
    throw new Error(`AJV compilation failed: ${e.message}`);
  }
}

let errors = 0;
const allIds = new Map();
const files = collectAllSchemaFiles();

if (files.length === 0) {
  console.error("FATAL: no schema files found");
  process.exit(1);
}

for (const filePath of files) {
  try {
    const content = readFileSync(filePath, "utf-8");
    const schema = JSON.parse(content);
    validateSchema(filePath, schema);

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

    const rel = filePath.replace(ROOT + "/", "");
    console.log(`OK: ${rel}`);
  } catch (e) {
    const rel = filePath.replace(ROOT + "/", "");
    console.error(`FAIL: ${rel} - ${e.message}`);
    errors++;
  }
}

// Check for broken $ref references
for (const [id, filePath] of allIds) {
  const content = readFileSync(filePath, "utf-8");
  const schema = JSON.parse(content);
  const refs = content.match(/\$ref:\s*"([^"]+)"/g) || [];
  for (const ref of refs) {
    const target = ref.match(/\$ref:\s*"([^"]+)"/)[1];
    if (target.startsWith("#")) continue;
    const resolvedId = target.includes("#") ? target.split("#")[0] : target;
    if (resolvedId && !allIds.has(resolvedId)) {
      if (resolvedId.startsWith("http")) continue;
      console.error(
        `BROKEN_REF: ${filePath} references "${target}" but no schema has $id="${resolvedId}"`,
      );
      errors++;
    }
  }
}

if (errors > 0) {
  console.error(`\n${errors} schema validation error(s) found`);
  process.exit(1);
}

console.log(`\nAll ${files.length} schemas valid`);
process.exit(0);
