# ARG for the Debian base image tag
ARG DEBIAN_IMAGE=debian:bookworm-20250929-slim
# ARG for the uv binary version
ARG UV_VERSION=0.8.22

# Stage for fetching the uv binary.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- Stage 1: python-base ---
# Creates a reusable base image with a specific Python version installed.
FROM ${DEBIAN_IMAGE} AS base
RUN apt-get update && apt-get install -y build-essential
# Install uv from the dedicated uv stage.
COPY --from=uv /uv /uvx /bin/
# Install the Python version specified in the .python-version file.
COPY .python-version ./
RUN uv python install


# --- Stage 2: builder ---
# Builds the application's virtual environment with all dependencies.
FROM base AS builder

# Change the working directory to the `app` directory
WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Copy the project into the intermediate image
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

RUN uv pip install .


# --- Stage 3: final ---
# Creates the lean, final runtime image.
FROM base AS final

# Copy the environment and source code
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app /app

# Set working directory
WORKDIR /app

# Expose the Restful port
EXPOSE 5000

# Set the CMD to run the CLI app by default.
ENTRYPOINT ["/app/.venv/bin/python", "-m", "src.main"]
