# Releases API

## Overview

The Releases module manages catalog releases with a draft→reconciled→published state machine. Releases bundle verified resources (agents, models, providers, skills) into signed manifests for distribution to desktop clients.

## State Machine

```
draft (publishing) → reconciled → published
```

- **draft/publishing**: Initial state after creation. Manifest is built but not signed for distribution.
- **reconciled**: All resources validated, dangling objects cleaned. Ready for publishing.
- **published**: Manifest is signed, uploaded to S3, and available for clients to download.

## Endpoints

### Admin API (`/admin/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/catalog/releases` | List all releases (admin) |
| POST | `/catalog/releases` | Create a new release draft |
| POST | `/catalog/releases/{id}/reconcile` | Reconcile resources, validate, clean dangling objects |
| POST | `/catalog/releases/{id}/publish` | Sign manifest and publish release |
| POST | `/emergency-disables` | Create emergency disable entry |
| GET | `/emergency-disables/latest` | Get latest emergency disable |

### Public API (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/catalog/manifest` | Get latest published manifest |
| GET | `/catalog/releases/{id}` | Get single release details |
| GET | `/catalog/agents` | List published agents |
| GET | `/catalog/agents/{id}/models` | List published models for an agent |
| GET | `/catalog/providers` | List published providers |
| GET | `/catalog/providers/{id}/models` | List published models for a provider |
| GET | `/catalog/skills` | List published skills |
| GET | `/catalog/releases/{id}/resources/{type}` | Get release resources by type |
| GET | `/catalog/emergency-disables/latest` | Get latest emergency disable (public) |

## Emergency Disable

Emergency disable allows operators to immediately disable a resource (agent, model, provider, or skill) across all clients. The disable record is signed and published so desktop clients can verify authenticity.

Fields:
- `resource_type`: Type of resource (`agents`, `models`, `providers`, `skills`)
- `resource_id`: UUID of the resource
- `resource_version`: Optional version string
- `action`: `disable` or `rollback`
- `reason`: Human-readable explanation
- `code`: Emergency confirmation code (typically `EMERGENCY`)

## Release Workflow

1. Admin creates a release via `POST /catalog/releases`
2. The system builds a manifest snapshot of all validated resources
3. Admin reconciles via `POST /catalog/releases/{id}/reconcile` to validate and clean
4. Admin publishes via `POST /catalog/releases/{id}/publish` to sign and distribute
