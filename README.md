# My-Ai

FastAPI ingestion service for MyTIMeS, read-only Canvas course access, and
read-only Gmail synchronization.

## Canvas setup (read-only)

1. Set `CANVAS_BASE_URL` and `CANVAS_ACCESS_KEY` in `.env`. The checked-in
   default is the NUS Canvas domain.
2. Start the API with `uvicorn main:app --reload`.
3. Check the connection and list courses:

   ```bash
   curl http://localhost:8000/canvas/status \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   curl http://localhost:8000/canvas/profile \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   curl http://localhost:8000/canvas/courses \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   curl http://localhost:8000/canvas/active-courses/details \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   ```

4. Use a returned course ID to read its modules, lecture/tutorial materials,
   assignments, quizzes, discussions, and files:

   ```bash
   curl http://localhost:8000/canvas/courses/123/content \
     -H "X-Scheduler-Secret: $SCHEDULER_SHARED_SECRET"
   ```

`GET /canvas/active-courses/details` performs the complete discovery flow in one
request: it first lists the user's active, available courses and then loads each
course's learning materials, active announcements, and deadlines. Each course
contains `lectures`, `tutorials`, `assignments`, `quizzes`, `announcements`,
`deadlines`, and `upcoming_deadlines`. The response also provides combined
cross-course deadline lists. If Canvas hides an optional resource such as a
course's Files tab, the other course data is retained and the course includes a
warning describing the unavailable resource.

The Canvas client has no write method and every upstream request is `GET`.
The local routes are also `GET`-only and require `X-Scheduler-Secret` whenever
`SCHEDULER_SHARED_SECRET` is configured. A manually generated Canvas token may
still inherit the user's wider Canvas permissions; for a credential-level
guarantee, ask the institution's Canvas administrator for a scoped developer
key limited to these scopes:

- `url:GET|/api/v1/users/self/profile`
- `url:GET|/api/v1/courses`
- `url:GET|/api/v1/courses/:id`
- `url:GET|/api/v1/courses/:course_id/modules`
- `url:GET|/api/v1/courses/:course_id/modules/:module_id/items`
- `url:GET|/api/v1/courses/:course_id/assignments`
- `url:GET|/api/v1/courses/:course_id/quizzes`
- `url:GET|/api/v1/courses/:course_id/files`
- `url:GET|/api/v1/announcements`

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
- `GET /canvas/status`
- `GET /canvas/profile`
- `GET /canvas/courses`
- `GET /canvas/active-courses/details`
- `GET /canvas/courses/{course_id}/content`
- `GET /gmail/status`
- `GET /gmail/oauth/authorize`
- `GET /gmail/oauth/callback`
- `POST /internal/scheduler/gmail`
- `POST /internal/scheduler/mytimes`
