#!/usr/bin/env node

import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");
const RPC_SCHEMA = join(ROOT, "rpc-schema");

let errors = 0;

function fail(msg) {
  console.error(`FAIL: ${msg}`);
  errors++;
}

// Load registry
let registry;
try {
  registry = JSON.parse(readFileSync(join(RPC_SCHEMA, "registry.v1.json"), "utf-8"));
} catch (e) {
  console.error(`FATAL: cannot load registry.v1.json - ${e.message}`);
  process.exit(1);
}

const methods = registry.methods;
if (!Array.isArray(methods)) {
  console.error(`FATAL: registry.methods is not an array`);
  process.exit(1);
}

// Load error codes
let errorCodes;
try {
  const ec = JSON.parse(readFileSync(join(RPC_SCHEMA, "error-codes.v1.json"), "utf-8"));
  errorCodes = new Set(ec.error_codes.map(e => e.code));
} catch (e) {
  console.error(`FATAL: cannot load error-codes.v1.json - ${e.message}`);
  process.exit(1);
}

// 1. Each method unique
const seen = new Set();
for (const entry of methods) {
  if (!entry.method) {
    fail(`entry missing method field`);
    continue;
  }
  if (seen.has(entry.method)) {
    fail(`duplicate method: ${entry.method}`);
  }
  seen.add(entry.method);
}

// 2-4. Validate enums
for (const entry of methods) {
  if (!["rust", "sidecar", "supervisor"].includes(entry.owner)) {
    fail(`invalid owner "${entry.owner}" for method ${entry.method}`);
  }
  if (!["read", "write", "stream"].includes(entry.kind)) {
    fail(`invalid kind "${entry.kind}" for method ${entry.method}`);
  }
  if (!["none", "profile", "company"].includes(entry.scope)) {
    fail(`invalid scope "${entry.scope}" for method ${entry.method}`);
  }
}

// 5. Write methods must have non-zero idempotency_ttl_seconds
for (const entry of methods) {
  if (entry.kind === "write" && entry.idempotency_ttl_seconds === 0) {
    fail(`write method ${entry.method} has idempotency_ttl_seconds=0`);
  }
  if (entry.kind === "read" && entry.idempotency_ttl_seconds !== 0) {
    fail(`read method ${entry.method} should have idempotency_ttl_seconds=0 (got ${entry.idempotency_ttl_seconds})`);
  }
}

// 6. allowed_errors must exist in error-codes.v1.json
for (const entry of methods) {
  if (!Array.isArray(entry.allowed_errors)) {
    fail(`method ${entry.method} missing allowed_errors array`);
    continue;
  }
  for (const err of entry.allowed_errors) {
    if (!errorCodes.has(err)) {
      fail(`method ${entry.method} references unknown error code "${err}"`);
    }
  }
}

// 7. request_schema and response_schema files must exist
for (const entry of methods) {
  const reqPath = join(RPC_SCHEMA, entry.request_schema);
  const resPath = join(RPC_SCHEMA, entry.response_schema);
  if (!existsSync(reqPath)) {
    fail(`method ${entry.method}: request_schema file not found at ${entry.request_schema}`);
  }
  if (!existsSync(resPath)) {
    fail(`method ${entry.method}: response_schema file not found at ${entry.response_schema}`);
  }
}

// 8. company scope request must contain company_id
// Exemptions: company.create (no ID exists yet), company.list (cross-company listing)
const COMPANY_ID_EXEMPTIONS = new Set(["company.create", "company.list"]);
for (const entry of methods) {
  if (entry.scope !== "company") continue;
  if (COMPANY_ID_EXEMPTIONS.has(entry.method)) continue;
  const reqPath = join(RPC_SCHEMA, entry.request_schema);
  if (!existsSync(reqPath)) continue; // already reported above
  try {
    const req = JSON.parse(readFileSync(reqPath, "utf-8"));
    const hasCompanyId =
      req.properties &&
      req.properties.company_id;
    if (!hasCompanyId) {
      fail(`company-scope method ${entry.method} request schema does not include company_id property`);
    }
  } catch (e) {
    fail(`company-scope method ${entry.method}: cannot parse request schema - ${e.message}`);
  }
}

if (errors > 0) {
  console.error(`\n${errors} validation error(s) found`);
  process.exit(1);
}

console.log(`\nAll ${methods.length} registry entries valid`);
process.exit(0);
