# Documentation

This project ships with the following documentation:

| Document | What it covers |
|---|---|
| [KICKOFF.md](KICKOFF.md) | Requirements and design decisions (the "why" and "what") |
| [BUILD_LOG.md](BUILD_LOG.md) | The build process, issues found, and how each was fixed |
| [API.md](API.md) | **API guide** — endpoints, request/response reference, curl & SDK examples, error handling |
| [3D-VIEW.md](3D-VIEW.md) | **3D view guide** — how the three.js visualization works and how to build your own |

## Quick orientation

- **What it is:** a self-hosted REST API that checks whether a set of products
  fits in a container, and returns the remaining space (volume + percentage)
  plus the exact placement of every unit.
- **The API:** `POST /check` (the main endpoint) and `GET /health`.
- **The 3D view:** a self-contained `frontend/index.html` that calls the API
  and renders the result in three.js.

See [API.md](API.md) for the full API reference and [3D-VIEW.md](3D-VIEW.md)
for the visualization.
