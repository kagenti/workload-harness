# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities through GitHub Security Advisories:
**[Report a vulnerability](https://github.com/kagenti/workload-harness/security/advisories/new)**

Do **NOT** open public issues for security vulnerabilities.

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 7 days
- **Fix timeline:** Based on severity (critical vulnerabilities prioritized)

## Security Controls

This repository uses:

- **CI security scanning** — Trivy filesystem scan, CodeQL (Python), dependency review
- **Dependency updates** — Dependabot for pip and GitHub Actions ecosystems
- **OpenSSF Scorecard** — Continuous supply chain security monitoring
- **Pre-commit hooks** — Local linting and formatting checks
- **Action pinning** — All GitHub Actions are SHA-pinned

## Supported Versions

Only the latest release on the `main` branch is supported with security updates.
