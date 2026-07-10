# Deployment Mac setup

## GitHub Actions runner

Create a repository-level self-hosted runner in GitHub, install it under a
dedicated macOS user, and add the custom label `srt-flow-deploy`. During runner
configuration, keep the default `self-hosted` and `macOS` labels. Install and
start its generated launchd service:

```bash
./config.sh --url https://github.com/superhzb/srt-flow --token <short-lived-token> --labels srt-flow-deploy --unattended
./svc.sh install
./svc.sh start
```

The workflow grants only `contents: read`. Do not store the router passcode in
GitHub: the deployment script reads it from the deployment user's local config.

## Deployment configuration

The existing brbot-router `.env` is used automatically when it lives at
`~/Documents/GitHub/brbot-router/.env`. Otherwise copy `deploy.env.example` to
`~/.config/srt-flow/deploy.env`, fill in the local values, and run
`chmod 600 ~/.config/srt-flow/deploy.env`.

Both deployment clones must be clean and checked out on their assigned branch.
Each deployment runs `npm ci` followed by `npm run build`; FastAPI serves the
resulting `srt-frontend/dist` directory instead of exposing the Vite dev server.
Vite's hashed assets are cached immutably while the HTML shell is revalidated.
Configure each router project to run `make serve` and route its public domain to
the project's `BACKEND_PORT`; `make dev` and `FRONTEND_PORT` are local-only.
The prototype currently uses `ENV=dev` and `AUTH_MODE=dev` in each clone's
ignored `srt-backend/.env`. Before treating either public site as production,
switch to Google authentication and the corresponding `ENV` value.

## brbot-router launchd service

Build the router, copy `launchd/com.brettbot.brbot-router.plist` to
`~/Library/LaunchAgents/com.brettbot.brbot-router.plist`, replace `/Users/you`,
then load it:

```bash
cd ~/Documents/GitHub/brbot-router
npm ci
npm run build
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.brettbot.brbot-router.plist
launchctl enable "gui/$(id -u)/com.brettbot.brbot-router"
```

The router's `.env`, `projects.json`, Cloudflare credentials, and deployment
logs remain outside this repository.
