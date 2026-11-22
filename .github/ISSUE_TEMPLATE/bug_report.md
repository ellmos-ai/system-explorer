---
name: Bug Report
about: Report a reproducible bug in system-explorer (CLI, manifest validation, search routing, or local UI)
title: "[Bug]: "
labels: ["bug", "triage"]
assignees: []
---

## Bug Description
A clear and concise description of what went wrong.

## Steps to Reproduce
1. Command or UI action executed (e.g. `system-explorer validate ...`):
2. Input workspace / manifest (`ellmos-module.v2.json` snippet, redacted):
3. Expected behavior:
4. Actual behavior / error output:

## Environment
- **OS:** (e.g. Windows 11, Ubuntu 24.04, macOS)
- **Python version:** (`python --version`)
- **system-explorer version:** (`0.4.2`)

## Architecture & Security Invariant Check
- [ ] Reproducible locally (`100% Offline`, **Zero-Egress**, `127.0.0.1` loopback only, no outbound network required)
- [ ] Executed unprivileged (`RunAsInvoker`, no admin/root elevation required)
- [ ] No private paths, credentials, tokens, or local sensitive artifacts included in this report
