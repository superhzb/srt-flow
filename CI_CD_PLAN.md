# srt-flow CI/CD Plan

## Goal

Support a simple solo-developer workflow:

1. Develop on another Mac and push commits directly to `staging`.
2. Run CI and automatically update the staging deployment on the deployment Mac.
3. Test `https://staging.srt-flow.com` manually.
4. Fast-forward merge the tested `staging` branch into `main` without a pull request.
5. Run CI and automatically update production at `https://www.srt-flow.com`.

Development authentication can remain enabled while the application is a prototype.

## Repository and deployments

- GitHub repository: `superhzb/srt-flow`
- Staging branch: `staging`
- Production branch: `main`
- Staging clone: `srt-flow/srt-flow-staging/srt-flow`
- Production clone: `srt-flow/srt-flow-prod/srt-flow`
- Staging router project: `srt-flow-stg`
- Production router project: `srt-flow`

The two deployments use the same MLX resource group, so their files can be updated independently, but only one application stack can run at a time.

## Developer workflow

### Deploy to staging

```bash
git switch staging
git pull --ff-only origin staging
git add .
git commit -m "describe the change"
git push origin staging
```

A successful push runs CI and then updates the staging clone on the deployment Mac.

### Promote staging to production

After testing staging:

```bash
git fetch origin
tested_sha=$(git rev-parse origin/staging)
# Record this SHA when manual testing begins. If staging advances, retest it.
git switch main
git pull --ff-only origin main
test "$(git rev-parse origin/staging)" = "$tested_sha"
git merge --ff-only "$tested_sha"
git push origin main
```

The recorded SHA and equality check ensure `main` becomes exactly the commit tested on staging. If either check fails, the branches or the tested target changed and must be inspected rather than force-pushed.

## Implementation plan

### 1. Clean the deployment clones

- Review and commit the existing `Makefile` and `srt-frontend/vite.config.ts` changes.
- Make both deployment clones clean before enabling automation.
- Do not use the deployment clones for manual development afterward.

Verification:

```bash
git -C /path/to/staging/clone status --short
git -C /path/to/production/clone status --short
```

Both commands must produce no changed files.

### 2. Repair and extend CI

- Run the existing CI jobs on pushes to both `staging` and `main`.
- Explicitly set `ENV=dev` and `AUTH_MODE=dev` for backend integration tests.
- Keep the existing Ruff, typecheck, test, and frontend build jobs.
- Do not deploy when any CI job fails.

Verification: all CI jobs pass for the same commit on both branches.

### 3. Install a self-hosted GitHub Actions runner

- Install a GitHub Actions runner on the deployment Mac.
- Give it a dedicated label such as `srt-flow-deploy`.
- Run it as a macOS `launchd` service so it survives logout and reboot.
- Use it only for deployment jobs triggered by pushes to `staging` or `main`.

Verification: GitHub reports the runner online after reboot.

### 4. Add a local deployment script

Create one script that accepts `staging` or `production` and:

1. Acquires a deployment lock.
2. Selects the correct clone, branch, router project, and public URL.
3. Refuses to deploy if the clone has uncommitted changes.
4. Records the currently deployed commit and active router project.
5. Fetches the requested branch from GitHub.
6. Requires the remote branch tip to equal the CI event SHA and requires a fast-forward update.
7. Stops the project through the local router API if it is running.
8. Fast-forwards the local branch.
9. Installs locked Python and Node dependencies with `uv sync --frozen` and `npm ci`.
10. Restarts the project when appropriate using the router's authenticated, resource-group-aware start operation.
11. Checks `/api/health` for the expected commit, checks worker readiness, and records the deployment result.
12. On failure or termination after mutation begins, restores the prior commit, dependencies, and active router project.

The deployment script must never force-push or overwrite a dirty working tree. Deployment jobs share a non-cancelling concurrency group, and the local script also holds a machine lock.

### 5. Add CI-gated deployment jobs

For a push to `staging`:

- Run all CI jobs.
- After they pass, run the staging deployment on the self-hosted runner.
- If staging was already active, restart and health-check it.
- If production was active, update the stopped staging clone without preempting production.

For a push to `main`:

- Run all CI jobs.
- After they pass, run the production deployment on the self-hosted runner.
- Start production and health-check `https://www.srt-flow.com`.
- The authenticated router start atomically preempts whichever MLX resource-group project is active.

Verification: a deliberately failing CI commit does not change either deployment clone.

### 6. Run brbot-router persistently

- Install `brbot-router` as a macOS `launchd` service.
- Keep its `.env`, `projects.json`, and Cloudflare credentials outside Git.
- Configure persistent stdout and stderr logs.
- Restart it automatically after unexpected failure or reboot.

Verification: the router dashboard and Cloudflare tunnel recover after reboot.

### 7. Test the complete staging flow

```bash
git switch staging
git pull --ff-only origin staging
git commit --allow-empty -m "test: staging deployment"
git push origin staging
```

Verify that:

- CI passes.
- The deployment job succeeds.
- The staging clone matches `origin/staging`.
- Staging works after selecting it through the router dashboard.

### 8. Test production promotion

```bash
git fetch origin
tested_sha=$(git rev-parse origin/staging)
git switch main
git pull --ff-only origin main
test "$(git rev-parse origin/staging)" = "$tested_sha"
git merge --ff-only "$tested_sha"
git push origin main
```

Verify that:

- CI passes on `main`.
- Production updates automatically.
- The production clone, `origin/main`, and the tested staging commit have the same commit SHA.
- `/api/health` returns HTTP 200 with the promoted commit SHA and all required workers report healthy.

## Rollback

Revert the bad commit on `staging`, verify the revert in staging, and promote it normally:

```bash
git switch staging
git pull --ff-only origin staging
git revert <bad-commit>
git push origin staging

git switch main
git pull --ff-only origin main
git merge --ff-only origin/staging
git push origin main
```

## Completion criteria

The setup is complete when:

- A direct push to `staging` updates staging only after CI passes.
- A fast-forward merge from `staging` into `main` triggers a CI-gated production update.
- Failed CI never changes a deployment.
- Dirty deployment clones are never overwritten.
- The runner and router recover automatically after the deployment Mac reboots.
