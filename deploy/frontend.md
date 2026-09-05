# Frontend on GitHub Pages

The Expo web frontend is hosted at `https://soccer-agent.lfactorial.com` using
GitHub Pages for the `L-factorial/soccer-analysis-agent` repository. It calls the
FastAPI backend at `https://api.soccer-agent.lfactorial.com` on DigitalOcean.

## Build and deployment

`.github/workflows/frontend-pages.yml` installs dependencies with `npm ci`, runs
TypeScript checks, and exports the Expo app using Node.js 22. Every push to
`main` deploys the resulting `frontend/dist` artifact to GitHub Pages. Pull
requests run build checks without deploying. The backend has its own workflow.

The frontend workflow sets `EXPO_PUBLIC_API_BASE_URL` to the production API URL
at build time. This URL is public browser configuration, not a secret. Local
Expo development still defaults to `http://127.0.0.1:8000` unless overridden.

The previous hosting provider configuration has been removed. The `build` and
`typecheck` scripts and Expo web settings are retained because Pages uses them.

## Repository and DNS settings

Under repository **Settings → Pages**, select **GitHub Actions** as the source
and set the custom domain to `soccer-agent.lfactorial.com`. The custom domain is
stored in repository settings; an Actions deployment does not need a CNAME file.

At the DNS provider for `lfactorial.com`, add:

| Type | Name | Value |
| --- | --- | --- |
| CNAME | `soccer-agent` | `l-factorial.github.io` |

Keep the homepage records and the `api.soccer-agent` A record as they are.
After GitHub provisions the certificate, enable **Enforce HTTPS** in Pages.

This export targets the custom domain root, not the repository subpath on the
default GitHub Pages URL. The current single-screen app uses `web.output: single`.
GitHub Pages has no SPA rewrite rules; if adding more page routes, use static
route exports or configure an appropriate navigation strategy first.

## Backend connection

The server environment at `/etc/soccer-backend.env` includes
`https://soccer-agent.lfactorial.com` in `CORS_ALLOW_ORIGINS`, alongside local Expo
origins. After deployment, open the frontend and run Analyze to verify a real
browser request to the API. Commentary remains disabled until separately enabled
on the backend.

Local build verification, from `frontend`:

```sh
npm run typecheck
EXPO_PUBLIC_API_BASE_URL=https://api.soccer-agent.lfactorial.com npm run build
```

References: [GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages),
[GitHub Pages custom domains](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).
