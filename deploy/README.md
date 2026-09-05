# Backend containers

The backend runs in a Python 3.12 image as a non-root user. Docker Compose
provides a health check and a restart policy. This deployment does not use a
vector database or configure persistent database storage.
The frontend runs separately. Native Python development remains supported;
Docker is optional on your development machine.

## Run locally with Docker (optional)

Install Docker with the Compose plugin. Run commands from the repository root.
If `backend/.env` does not exist, copy `backend/.env.example` to it. Keep your
existing `.env` if you already have one.

```sh
docker compose up --build -d --wait
curl --fail http://127.0.0.1:8000/health
docker compose logs -f backend
```

Expected health response: `{"status":"ok"}`. Stop an existing native backend
first if it uses port 8000, or select another port:

```sh
BACKEND_PORT=8001 docker compose up --build -d --wait
```

Point the frontend's `EXPO_PUBLIC_API_BASE_URL` at the selected port and restart
Expo if you change it. The default port needs no frontend configuration change.
The published port is bound to localhost. Rebuild with
`docker compose up --build -d --wait` after code changes; the container does not
use development reload or mount your source tree.

For a run with only the example settings, without copying a file:

```sh
SOCCER_ENV_FILE=./backend/.env.example docker compose up --build -d --wait
```

Use the same environment overrides for subsequent Compose commands. Runtime
keys are read from the selected environment file and never copied into the image.
Browser origins can be set using `CORS_ALLOW_ORIGINS` in that file.

Stop containers:

```sh
docker compose down
```

The health check reports HTTP availability; the restart policy restarts exited
containers, not containers that are merely unhealthy. The existing RAG code and
dependencies remain available, but RAG storage is not provisioned or checked by
this deployment. Configure storage separately before enabling vector database use.

## GitHub image builds

`.github/workflows/backend-image.yml` builds the image, runs the backend tests
inside it, and checks Compose startup and HTTP health. Pull requests targeting `main` run these checks without publishing.
Every push to `main`, and manual workflow runs on `main`, also publish the tested
image to GitHub Container Registry using the built-in `GITHUB_TOKEN`:

```text
ghcr.io/l-factorial/soccer-analysis-agent-backend:<full-commit-sha>
ghcr.io/l-factorial/soccer-analysis-agent-backend:latest
```

The workflow derives the lowercase image name from the repository name. No
droplet SSH secrets are needed for image builds. Repository/organization policy
must allow Actions to write packages. Builds currently target Linux amd64,
matching the hosted runner; local builds use your machine's native architecture.
Dependencies follow the existing unpinned `requirements.txt`; deployments should
use a tested image digest rather than rebuilding it on the server.

## Droplet deployment: next step

This change builds and publishes images only. It does not connect to the droplet
or enable automatic server updates. The previous SSH/systemd deployment workflow
has been replaced by the container workflow.

The next step is to install Docker on the droplet, configure registry access and
the server environment file, and add a deployment job that pulls the tested
image and verifies health with rollback. Compose can use a published image via
`BACKEND_IMAGE` and a server environment file via `SOCCER_ENV_FILE`.

`deploy/nginx.conf` retains the proposed hostname
`api.soccer-agent.lfactorial.com`. DNS, HTTPS, and trusted proxy settings will be
configured during droplet setup. No changes to the droplet are made by this work.

References: [Compose services](https://docs.docker.com/reference/compose-file/services/),
[GitHub container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
