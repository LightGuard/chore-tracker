# Chore Tracker documentation

This directory contains the contributor and operator guides. The
[README](../README.md) is the short project overview; start here when you need
to run, change, deploy, or recover the application.

## Reading paths

**New contributor**

1. [README](../README.md) - purpose, MVP scope, architecture summary, quick start.
2. [Development](development.md) - clean setup, configuration, Tilt, and tests.
3. [Architecture](architecture.md) - layers, data model, immutability, and rollover.
4. [API](api.md) or [Themes](themes.md) - depending on the change.
5. [Operations](operations.md) - how the running application is administered.

**Operator**

1. [Deployment](deployment.md) - Docker Compose and Kubernetes.
2. [Operations](operations.md) - administrator bootstrap, family/chore setup,
   reports, rollover recovery, upgrades, and limitations.
3. [Backup and restore](backup-restore.md) - tested backup and recovery
   procedures.
4. [Helm chart README](../deploy/kubernetes/chore-tracker/README.md) - chart
   values and cluster-specific procedures.

**Reviewer or maintainer**

- [Development](development.md#quality-gates) lists every check CI runs and how
  to reproduce it locally.
- [Architecture](architecture.md#invariants) records the contracts that protect
  historical data.
- The [weekly rotation policy](weekly-rotation.md) is the source of truth for
  deterministic assignment generation.

## Guide map

| Guide | Audience | Contents |
| --- | --- | --- |
| [Development](development.md) | Contributors | Prerequisites, clean checkout, configuration, Tilt, quality gates, browser tests, CI |
| [Architecture](architecture.md) | Contributors and reviewers | System context, backend layers, frontend routes, schema, invariants, rollover sequence, health |
| [API](api.md) | Frontend and integration contributors | Endpoint contracts, authentication, errors, pagination, timezone rules |
| [Themes](themes.md) | Frontend and design contributors | Theme catalog, preference storage, theme behavior, fonts, previews, adding a theme |
| [Operations](operations.md) | Household operator | Admin setup, family/chore setup, reports, monitoring, rollover recovery, migrations, troubleshooting |
| [Backup and restore](backup-restore.md) | Household operator | Backup, verification, restore, upgrades, and recovery scenarios for host, Docker, and Kubernetes |
| [Deployment](deployment.md) | Operator | Docker Compose, release images, Kubernetes summary, health checks |
| [Weekly rotation policy](weekly-rotation.md) | Contributors | Rotation anchor, stable ordering, assignment algorithm, catalog-change rules |
| [Helm chart README](../deploy/kubernetes/chore-tracker/README.md) | Operator | Chart installation, values reference, test cluster, chart backup/rollback |

## Conventions

- Commands run from the repository root unless the section says otherwise.
- Backend API paths are shown without the `/api` prefix. The frontend proxies
  `/api/*` to the API in development and in the Compose deployment.
- Use `http://localhost:5173` in a browser, not `127.0.0.1`. Passkey validation
  and the default allowed origin depend on the exact hostname.
- SQL examples are read-only unless a procedure explicitly says otherwise.
  Historical assignment, completion, and report rows are immutable.
- Never commit `.env`, `.env.docker`, `compose.override.yaml`, `secrets/`, or
  passkey/SMTP material. The repository ignores these paths for a reason.
- Documentation changes should keep links relative and run
  `python scripts/check-docs-links.py` before opening a pull request.
