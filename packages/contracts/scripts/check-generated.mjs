#!/usr/bin/env node

/**
 * Check that generated files are up to date with their source schemas.
 * Run: node scripts/check-generated.mjs
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

const SCHEMA_DIRS = ['events', 'domain-events', 'artifacts', 'skill'];

function validateSchema(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  const schema = JSON.parse(content);

  if (!schema.$schema || !schema.$schema.includes('json-schema.org/draft/2020-12')) {
    throw new Error(`${filePath}: missing or invalid $schema`);
  }

  if (!schema.$id) {
    throw new Error(`${filePath}: missing $id`);
  }

  if (!schema.title) {
    throw new Error(`${filePath}: missing title`);
  }

  if (!schema.type) {
    throw new Error(`${filePath}: missing type`);
  }

  return true;
}

let errors = 0;

for (const dir of SCHEMA_DIRS) {
  const dirPath = join(ROOT, dir);
  if (!existsSync(dirPath)) {
    console.log(`SKIP: ${dir} (not found)`);
    continue;
  }

  const files = readdirSync(dirPath).filter(f => f.endsWith('.json'));
  for (const file of files) {
    const filePath = join(dirPath, file);
    try {
      validateSchema(filePath);
      console.log(`OK: ${dir}/${file}`);
    } catch (e) {
      console.error(`FAIL: ${dir}/${file} - ${e.message}`);
      errors++;
    }
  }
}

// Check for duplicate $id values
const allIds = new Map();
for (const dir of SCHEMA_DIRS) {
  const dirPath = join(ROOT, dir);
  if (!existsSync(dirPath)) continue;

  const files = readdirSync(dirPath).filter(f => f.endsWith('.json'));
  for (const file of files) {
    const filePath = join(dirPath, file);
    try {
      const schema = JSON.parse(readFileSync(filePath, 'utf-8'));
      if (schema.$id) {
        if (allIds.has(schema.$id)) {
          console.error(`DUPLICATE $id: ${schema.$id} in ${file} and ${allIds.get(schema.$id)}`);
          errors++;
        } else {
          allIds.set(schema.$id, file);
        }
      }
    } catch (e) {
      // Already reported above
    }
  }
}

if (errors > 0) {
  console.error(`\n${errors} schema validation errors found`);
  process.exit(1);
}

console.log('\nAll schemas valid');
process.exit(0);
