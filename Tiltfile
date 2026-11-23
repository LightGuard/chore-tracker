# Local development for the API and frontend. All resources run on the host;
# no container runtime or Kubernetes cluster is required. Activate the project
# virtual environment before `tilt up`, or set PYTHON to its interpreter.
python = shlex.quote(os.getenv("PYTHON", "python"))

# Install the editable backend and development dependencies once per dependency
# change. The migration and backend resources depend on this succeeding.
local_resource(
    "setup",
    cmd=python + ' -m pip install -e ".[dev]"',
    deps=["pyproject.toml"],
    env={"CHORE_TRACKER_ENVIRONMENT": "development"},
)

# The application never migrates during startup. Apply the schema before the
# API starts, and reapply it when a migration revision changes.
local_resource(
    "migrate",
    cmd=python + " -m alembic upgrade head",
    deps=["alembic.ini", "migrations"],
    resource_deps=["setup"],
    env={"CHORE_TRACKER_ENVIRONMENT": "development"},
)

local_resource(
    "backend",
    cmd=python + ' -m pip install -e ".[dev]"',
    serve_cmd=python + " -m chore_tracker",
    deps=["pyproject.toml"],
    resource_deps=["setup", "migrate"],
    env={"CHORE_TRACKER_ENVIRONMENT": "development"},
    serve_env={"CHORE_TRACKER_ENVIRONMENT": "development"},
    readiness_probe=probe(
        http_get=http_get_action(port=8000, path="/health/ready")
    ),
    links=["http://127.0.0.1:8000/docs"],
)

local_resource(
    "frontend",
    cmd="npm --prefix frontend ci",
    serve_cmd="npm --prefix frontend run dev",
    deps=["frontend/package.json", "frontend/package-lock.json"],
    serve_env={
        "API_PROXY_TARGET": "http://127.0.0.1:8000",
    },
    readiness_probe=probe(
        http_get=http_get_action(port=5173, path="/")
    ),
    links=["http://localhost:5173"],
)
