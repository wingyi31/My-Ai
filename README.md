# My-Ai

FastAPI ingestion service for MyTIMeS and read-only Gmail synchronization.

## Gmail setup

1. In Google Cloud, enable the Gmail API and configure the OAuth consent screen.
2. Create an OAuth 2.0 **Web application** client. Add
   `http://localhost:8000/gmail/oauth/callback` as an authorized redirect URI.
3. Copy `.env.example` to `.env`, then set `GMAIL_CLIENT_ID`,
   `GMAIL_CLIENT_SECRET`, `GMAIL_OAUTH_STATE_SECRET`, and
   `SCHEDULER_SHARED_SECRET`.
4. Start the API with `uvicorn main:app --reload`.
5. Open `http://localhost:8000/gmail/oauth/authorize` and grant the read-only
   Gmail scope. The callback saves the refresh token to the ignored
   `data/gmail_credentials.json` file for local development.
6. Trigger a synchronization:

   ```bash
   curl -X POST http://localhost:8000/internal/scheduler/gmail \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   ```

The first run fetches the newest messages matching `GMAIL_SYNC_QUERY` (bounded
by `GMAIL_MAX_MESSAGES_PER_SYNC`). Later runs use Gmail history IDs and perform
incremental synchronization. If Google expires a history ID, the job safely
falls back to a new bootstrap.

`EmailProcessor` currently parses full MIME messages and the route returns only
metadata summaries. Inject an `EmailProcessor` handler to persist or index the
full `ParsedEmail` objects for the rest of the application.

For production, provide `GMAIL_REFRESH_TOKEN` from a secret manager and replace
the local JSON history store with durable shared storage. Cloud Run filesystems
are ephemeral, and the scheduler routes should be protected with Cloud Run IAM
in addition to (or instead of) the local shared-secret header.

## Endpoints

- `GET /health`
- `GET /gmail/status`
- `GET /gmail/oauth/authorize`
- `GET /gmail/oauth/callback`
- `POST /internal/scheduler/gmail`
- `POST /internal/scheduler/mytimes`
