

pkg-auth — Handles user signup, login, session/token management, and tier (free/paid) tracking.

pkg-file-upload — Manages uploading, storing, and retrieving files from object storage (S3/R2), independent of file type.

pkg-srt-services — Parses SRT files into a generic cue structure and serializes cue lists back into SRT output.

pkg-job-orch — Orchestrates job lifecycle (pending → processing → done/failed), routes translation work to the correct worker, and manages the pipeline-of-steps model.

pkg-billing — Integrates Stripe for checkout and webhooks, tracks usage, and enforces tier-based access rules.

pkg-notification — Sends email/webhook notifications to users when job status changes (e.g. completion, failure).