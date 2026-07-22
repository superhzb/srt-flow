# Deployment Mac setup

There is no automated deployment. GitHub Actions still runs CI
(lint/typecheck/test/build) on every push and pull request, but shipping a new
revision to the public sites is manual.

## Updating a running site

srt-flow runs as two brbot-router projects — `srt-flow` (production, `main`) and
`srt-flow-stg` (staging, `staging`) — each backed by a dedicated clone under
`~/Documents/GitHub/srt-flow`. To ship a new commit:

1. Pull it into the deployment clone:
   - production: `git -C ~/Documents/GitHub/srt-flow/srt-flow-prod/srt-flow pull --ff-only`
   - staging: `git -C ~/Documents/GitHub/srt-flow/srt-flow-staging/srt-flow pull --ff-only`
2. Restart the project in brbot-router so it rebuilds and re-serves the fresh
   commit. Use the dashboard, or the API (`start` runs `make build && make serve`,
   so a stop + start picks up the new code and reserves the MLX resource group):

   ```bash
   host=<dashboard-host>; pass=<passcode>; proj=srt-flow   # or srt-flow-stg
   curl -X POST -H "Host: $host" -H "Authorization: Bearer $pass" \
     http://127.0.0.1:9000/api/projects/$proj/stop
   curl -X POST -H "Host: $host" -H "Authorization: Bearer $pass" \
     http://127.0.0.1:9000/api/projects/$proj/start
   ```

Each clone must stay clean and checked out on its assigned branch. FastAPI
serves the prebuilt `srt-frontend/dist` (via `make serve`), not the Vite dev
server; Vite's hashed assets are cached immutably while the HTML shell is
revalidated. The prototype uses `ENV=dev` and `AUTH_MODE=dev` in each clone's
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

The router's `.env`, `projects.json`, and Cloudflare credentials remain outside
this repository.
