# Run both application components as host processes. No container runtime or
# Kubernetes cluster is needed for this development environment.
local_resource(
    "backend",
    cmd='python -m pip install -e ".[dev]"',
    serve_cmd="python -m chore_tracker",
    deps=["pyproject.toml"],
    env={"CHORE_TRACKER_ENVIRONMENT": "development"},
)

local_resource(
    "frontend",
    cmd="npm --prefix frontend ci",
    serve_cmd="npm --prefix frontend run dev",
    deps=["frontend/package.json", "frontend/package-lock.json"],
)
