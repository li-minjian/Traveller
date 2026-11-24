#!/usr/bin/env bash
set -euo pipefail

case "${DEPLOY_DEV:-false}" in
  false) exit 0 ;;
  true) ;;
  *) exit 2 ;;
esac

: "${DB_HOST:?}" "${MIGRATION_DB_HOST:?}" "${DB_USER:?}" "${DB_NAME:?}" "${BACKEND_HOST:?}"
: "${PROJECT_ID:?}" "${PROJECT_NUMBER:?}" "${REGION:?}" "${ARTIFACT_REPO:?}" "${COMMIT_SHA:?}" "${BUILD_ID:?}"
: "${DB_PASSWORD_VERSION:?}" "${BACKEND_KEY_VERSION:?}" "${PLANNER_KEY_VERSION:?}"

if [[ "$DB_HOST" == *.neon.tech &&
      ( "$DB_HOST" != *-pooler.* || "${DB_HOST/-pooler./.}" != "$MIGRATION_DB_HOST" || "$MIGRATION_DB_HOST" == *-pooler.* ) ]]; then
  printf '%s\n' 'Use the Neon pooled hostname for Django and its direct counterpart for migrations.' >&2
  exit 2
fi

registry="$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO"
backend_image="$registry/traveller-backend:$COMMIT_SHA"
planner_image="$registry/traveller-journey-planner:$COMMIT_SHA"
backend_sa="traveller-backend@$PROJECT_ID.iam.gserviceaccount.com"
planner_sa="traveller-planner@$PROJECT_ID.iam.gserviceaccount.com"
planner_host="traveller-journey-planner-$PROJECT_NUMBER.$REGION.run.app"
labels="commit-sha=$COMMIT_SHA,gcb-build-id=$BUILD_ID,environment=dev"

target=(--project="$PROJECT_ID" --region="$REGION" --quiet)
db_env="POSTGRES_DB=$DB_NAME,POSTGRES_USER=$DB_USER,POSTGRES_SSLMODE=verify-full"
backend_secrets="DJANGO_SECRET_KEY=traveller-backend-key:$BACKEND_KEY_VERSION,POSTGRES_PASSWORD=traveller-db-password:$DB_PASSWORD_VERSION"
service_limits=(--cpu=1 --memory=512Mi --port=8080 --min-instances=0 --max-instances=2 --concurrency=4)
startup_probe=--startup-probe=tcpSocket.port=8080,periodSeconds=4,timeoutSeconds=2,failureThreshold=15

invoker_disabled="$(gcloud run services describe traveller-git "${target[@]}"   --format='value(metadata.annotations."run.googleapis.com/invoker-iam-disabled")')"
if [[ "$invoker_disabled" == true ]]; then
  printf '%s\n' 'The backend must require Cloud Run IAM before shared DEV can deploy.' >&2
  exit 1
fi

# Run schema changes on the direct PostgreSQL endpoint before staging the app.
gcloud run jobs deploy traveller-migrate "${target[@]}" \
  --image="$backend_image" --service-account="$backend_sa" \
  --command=python --args=manage.py,migrate,--noinput \
  --cpu=1 --memory=512Mi --tasks=1 --max-retries=0 --task-timeout=300s \
  --set-env-vars="$db_env,POSTGRES_HOST=$MIGRATION_DB_HOST,DJANGO_DEBUG=false" \
  --set-secrets="$backend_secrets" --labels="$labels" --execute-now --wait

gcloud run deploy traveller-journey-planner "${target[@]}" "${service_limits[@]}" "$startup_probe" \
  --image="$planner_image" --service-account="$planner_sa" --timeout=30s \
  --update-labels="$labels" --set-env-vars="PLANNER_ALLOWED_HOSTS=$planner_host,FLIGHT_PROVIDER=dummy,DJANGO_DEBUG=false" \
  --set-secrets="DJANGO_SECRET_KEY=traveller-planner-key:$PLANNER_KEY_VERSION"

# Vercel DEV uses the private tag. Changes to the service's default traffic
# are independently managed.
gcloud run deploy traveller-git "${target[@]}" "${service_limits[@]}" "$startup_probe" \
  --image="$backend_image" --service-account="$backend_sa" --timeout=95s \
  --no-traffic --tag=shared-dev --update-labels="$labels" \
  --set-env-vars="^|^${db_env//,/|}|POSTGRES_HOST=$DB_HOST|POSTGRES_POOLED=true|DJANGO_ALLOWED_HOSTS=$BACKEND_HOST|DJANGO_DEBUG=false|LLM_PROVIDER=offline|ISOLATE_PLANNING_SESSIONS=true|JOURNEY_PLANNER_URL=https://$planner_host|JOURNEY_PLANNER_USE_CLOUD_RUN_IAM=true" \
  --set-secrets="$backend_secrets"
