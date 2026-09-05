# Frontend on Vercel

Import `L-factorial/soccer-analysis-agent` in Vercel using the GitHub integration.
Select `frontend` as the Root Directory, `Other` as the framework preset, and
Node.js 22.x. Keep `main` as the production branch.

`frontend/vercel.json` configures dependency installation with `npm ci`, the
Expo web export, `dist` output, and SPA rewrites. Its build command sets the
public API URL to `https://api.soccer-agent.lfactorial.com`. This URL is bundled
into browser JavaScript; it is not a secret. Native local development still
defaults to the local backend. Change the deployment build command if using
a different API for preview builds.

Add `soccer-agent.lfactorial.com` under the Vercel project's Domains settings.
At the DNS provider for `lfactorial.com`, create a CNAME named `soccer-agent`
using the exact target Vercel displays. Vercel provisions HTTPS after validating
the domain. Preserve the separate `api.soccer-agent` A record pointing to the
DigitalOcean droplet.

The backend's `/etc/soccer-backend.env` must include the production frontend
origin in `CORS_ALLOW_ORIGINS`. Local Expo origins can remain in the same list.
Preview deployment origins must be explicitly allowed before calling this API;
the setup does not allow arbitrary Vercel projects through CORS.

After domain setup, load the app and run Analyze to verify an actual API request.
Pushes to `main` trigger production frontend deployments through Vercel's GitHub
integration. The backend continues deploying independently through GitHub Actions.

Local verification from `frontend`:

```sh
npm run typecheck
EXPO_PUBLIC_API_BASE_URL=https://api.soccer-agent.lfactorial.com npm run build
```

References: [Expo on Vercel](https://docs.expo.dev/guides/publishing-websites/#vercel),
[Vercel monorepos](https://vercel.com/docs/monorepos).
