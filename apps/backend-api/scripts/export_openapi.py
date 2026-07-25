#!/usr/bin/env python
# Export OpenAPI spec from FastAPI app
# Usage: python scripts/export_openapi.py

import json
import os
import sys
from pathlib import Path

# Add src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

# Set required env vars for app initialization
os.environ.setdefault("IBREEZE_DATABASE_URL", "postgresql+asyncpg://ibreeze:ibreeze_password@localhost:5432/ibreeze")
os.environ.setdefault("IBREEZE_API_PORT", "51080")
os.environ.setdefault("IBREEZE_S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("IBREEZE_S3_ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("IBREEZE_S3_SECRET_ACCESS_KEY", "minioadmin")
os.environ.setdefault("IBREEZE_S3_BUCKET_NAME", "ibreeze")
os.environ.setdefault("IBREEZE_AUTH_KEY_DIR", "/tmp/ibreeze_keys/auth")
os.environ.setdefault("IBREEZE_CATALOG_KEY_DIR", "/tmp/ibreeze_keys/catalog")

from ibreeze_backend.main import app

def main():
    output_path = Path(__file__).parent.parent / "packages" / "contracts" / "openapi" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    openapi_spec = app.openapi()
    
    # Ensure consistent ordering
    with open(output_path, 'w') as f:
        json.dump(openapi_spec, f, indent=2, sort_keys=True)
    
    print(f"OpenAPI spec exported to {output_path}")
    print(f"Paths: {len(openapi_spec.get('paths', {}))}")
    print(f"Components schemas: {len(openapi_spec.get('components', {}).get('schemas', {}))}")

if __name__ == "__main__":
    main()