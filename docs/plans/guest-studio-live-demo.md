# Guest Studio and Live Demo Plan

## Goal

Allow signed-out visitors to upload and configure an SRT translation in Studio. When they try to process it, offer either Google sign-in for a real translation or a deterministic sample translation that uses no worker capacity or quota.

## Product behavior

- Public: Home, Studio, upload, parsing, source selection, and target-language selection.
- Protected: real processing, History, Billing, job results, and downloads.
- The customer navigation should not expose the DB or diagnostic Auth tabs.
- The landing page's **Live demo** action should open Studio.
- A signed-out visitor who clicks **Translate** sees three choices:
  - **Sign in & translate**
  - **Try the demo**
  - **Keep editing**
- Demo mode must always be clearly labelled and must use a bundled sample file rather than silently processing the visitor's upload.

## Implementation

### 1. Expose Studio before login

Refactor `srt-frontend/src/App.tsx` so authentication no longer controls whether the entire application shell renders.

- Render Studio for signed-out visitors.
- Keep account-specific screens behind a session check.
- Route signed-out History and Billing actions to the sign-in prompt.
- Connect the existing landing-page **Live demo** button to Studio.

### 2. Gate real processing

Intercept processing before `startJob()` is called.

- Signed-in users continue directly to real processing.
- Signed-out users see an accessible decision modal.
- Closing the modal must preserve uploaded files, parsed cues, and selections.
- The modal must manage keyboard focus, support Escape, and restore focus to the Translate button.

### 3. Preserve pending work across OAuth

Add a small IndexedDB persistence module for pending translation intent.

Persist:

- Uploaded `File`/blob and filename.
- Parsed cues and detected or selected source language.
- Selected worker and target languages.
- Schema version and creation time.

Before redirecting to Google, save the pending workflow. After OAuth returns to `/app`, restore it and ask for one final confirmation before consuming quota. Delete saved data after restoration, cancellation, logout, or a short expiry such as 30 minutes.

Move worker and target selection state from `ConfigureScreen.tsx` into the parent workflow so it can be persisted and restored.

### 4. Add deterministic demo fixtures

Bundle a demo dataset containing:

- One short, realistic sample SRT.
- Pre-generated translations for a curated set of popular languages.
- Simulated progress stages and completed output.

Demo processing must be entirely client-side:

- No job creation.
- No worker requests.
- No quota usage.
- Predictable progress and results.
- Persistent **Demo translation** labelling.

Only offer fixture-supported target languages in demo mode. If the visitor selected unsupported languages, ask them to choose from the supported demo set instead of generating fake placeholder translations.

### 5. Share the real results presentation

Separate result presentation from data transport in `srt-frontend/src/StackedOutput.tsx`.

- Real mode loads output using a job ID.
- Demo mode receives fixture cues and output directly.
- Both modes reuse subtitle preview, language ordering, and stacked-output presentation.
- If demo download is enabled, use an explicit sample filename such as `srt-flow-demo-stacked.srt`.

Add a lightweight demo-processing component that advances through parsing, translating, and completion without pretending a backend job exists.

### 6. Enforce backend authentication and ownership

Replace shared `dev_user_id` behavior before releasing the public Studio.

- Require an authenticated principal for create, list, status, output, and download operations.
- Pass the authenticated user ID through enqueueing and storage paths.
- Filter every job lookup by job ID and user ID.
- Return `401` for signed-out requests and `404` when a job belongs to another user.
- Inject the auth dependency at backend composition so `pkg-job-orch` does not own Google OAuth concerns.
- Preserve development auth through the same principal interface.

The public `/api/srt/prepare` endpoint can remain anonymous, with its file-size validation and suitable rate limiting.

## Test plan

### Frontend

- A signed-out visitor can enter Studio, upload, parse, and configure.
- Translate opens the login/demo modal.
- Cancelling the modal preserves configuration.
- Demo mode makes no job API request.
- Demo mode progresses and displays fixture results.
- Pending translation intent survives the OAuth redirect and restores correctly.
- Signed-in processing still calls the real job API.
- History and Billing require authentication.
- The decision modal meets keyboard and accessible-name requirements.

### Backend

- Anonymous job operations return `401`.
- Users only see their own jobs.
- Cross-user status and download requests return `404`.
- Jobs and stored outputs use the authenticated user's ID.
- Development auth mode remains supported.

## Validation

Run `make check`, then manually verify:

1. Landing -> Live demo -> Studio.
2. Guest upload -> configure -> dismiss login.
3. Guest upload -> demo -> preview, reorder, and optional sample download.
4. Guest upload -> Google login -> restored configuration -> real translation.
5. Signed-in History and Billing.
6. Direct anonymous and cross-user API requests.

## Delivery slices

1. Public Studio and processing decision modal.
2. Deterministic demo and shared results presentation.
3. OAuth restoration and backend per-user authorization.

Backend authorization is a release prerequisite even if it is developed in the final slice; frontend tab visibility is not a security boundary.
