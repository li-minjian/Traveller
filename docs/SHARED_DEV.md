# Traveller shared DEV

The shared environment uses the merged frontend on Vercel Preview, Django and
Main-Agent on the `shared-dev` tag of `traveller-git`, a private Journey Planner,
and PostgreSQL on the dedicated Neon Free project. The production Vercel domain
serves the MSW demo. The chat and flight cards in Preview use Django responses.
The itinerary and map continue to use the frontend's sample itinerary.

## Access

Vercel protects the Preview with Vercel Authentication. Team members use the
protected branch URL and sign in with Vercel or use the branch's revocable
teammate link. Treat that link as a credential and share it privately. The
browser calls relative
`/api/v1/` URLs. A Vercel function exchanges its Preview OIDC identity for a
short-lived Google ID token. Django calls the private planner using its Cloud Run
identity. Each browser has a signed secure cookie that scopes access to its own
planning sessions. A session ID from another browser returns 404. Public-demo
sessions are local to the mock. This prototype provides browser-level ownership
and stores no account identity or cross-device session mapping.

## Deploy

- Keep the existing Developer Connect repository link and the
  `cloud-run-source-deploy` Artifact Registry. Configure the regional Cloud Build
  trigger to read `cloudbuild.yaml` and watch only the trusted DEV branch.
- The CI identity pushes commit-tagged images. Set `_DEPLOY_DEV=true` after
  bootstrapping both private services and the migration job. The migration job
  uses the direct Neon host, while Django uses the pooled host. Both verify TLS.
  Set the database host, user, and name through trigger substitutions.
  Confirm the returned Neon hostname before deriving its counterpart, because
  a connection string can already use the pooler. Change
  pinned Secret Manager version substitutions when rotating credentials.
- The backend uses `LLM_PROVIDER=offline`. The planner uses
  `FLIGHT_PROVIDER=dummy`. Cloud Run scales to zero with at most two instances
  per revision, at 1 vCPU and 512 MiB each. The migration job has one task.
- Scope the Vercel environment variables to the trusted Preview branch.
  `TRAVELLER_BACKEND_URL` is the Cloud Run tagged URL.
  `TRAVELLER_BACKEND_AUDIENCE` is the service's canonical URL.
  Set `TRAVELLER_WIF_AUDIENCE` to the full Workload Identity provider resource
  prefixed with `//iam.googleapis.com/`, and
  `TRAVELLER_CALLER_SERVICE_ACCOUNT` to the Vercel caller identity.
- A failed migration stops the build before either serving revision is updated.
  Keep migrations compatible with the prior serving revision so it can remain
  available during a rollout or rollback.

## Verify and roll back

Record the Git SHA, Cloud Build ID, Cloud Run migration execution, backend tag
target, planner revision, and Vercel deployment ID. Verify `/api/v1/health/`,
then create a trip in the protected preview. Ask for a future one-way flight from
Berlin to Lisbon, confirm flight cards appear, reload and check the conversation
and Trip State, then check that a fresh browser session cannot read that trip.
The direct Cloud Run URLs should reject an unauthenticated request.

To restore a previously verified release, move the backend's `shared-dev` tag to
its previous revision with `gcloud run services update-traffic traveller-git
--update-tags=shared-dev=REVISION`. If necessary, restore the matching planner
with `gcloud run services update-traffic traveller-journey-planner
--to-revisions=REVISION=100`. Run the two commands in `bpvs-traveler`,
`europe-west1`, and verify the protected preview again. For a frontend rollback,
redeploy the known-good source as a protected Preview. Database migrations are
managed separately from revision rollback.
