#!/usr/bin/env bash
# Deploys Nirnay to a Google Cloud project: BigQuery lakehouse (asia-south1) + Cloud Run service.
# Usage: ./deploy/deploy.sh <PROJECT_ID>        Run from the project root, in Cloud Shell or any machine with gcloud + bq.
set -euo pipefail
PROJECT="${1:?Usage: ./deploy/deploy.sh PROJECT_ID}"
REGION="asia-south1"
SA="nirnay-run@${PROJECT}.iam.gserviceaccount.com"
cd "$(dirname "$0")/.."

echo "== 1/6 Project and APIs"
gcloud config set project "$PROJECT" >/dev/null
gcloud services enable compute.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com bigquery.googleapis.com aiplatform.googleapis.com iam.googleapis.com

echo "== 2/6 BigQuery datasets in $REGION"
for ds in lending_raw lending_curated lending_gold; do
  bq --location="$REGION" show --dataset "$PROJECT:$ds" >/dev/null 2>&1 || bq --location="$REGION" mk --dataset --description "Nirnay demo: $ds" "$PROJECT:$ds"
done

echo "== 3/6 Load the raw layer (synthetic data)"
for f in data/out/raw/*.csv; do
  t=$(basename "$f" .csv)
  bq --location="$REGION" load --replace --source_format=CSV --skip_leading_rows=1 --allow_quoted_newlines "$PROJECT:lending_raw.$t" "$f" "deploy/schemas/$t.json" >/dev/null
  echo "   lending_raw.$t"
done
bq --location="$REGION" show "$PROJECT:lending_raw.ext_api_log" >/dev/null 2>&1 || bq --location="$REGION" mk --table "$PROJECT:lending_raw.ext_api_log" run_id:STRING,ts:STRING,service:STRING,request_key:STRING,latency_ms:INT64,cost_inr:FLOAT64,response:STRING
bq --location="$REGION" show "$PROJECT:lending_gold.agent_audit" >/dev/null 2>&1 || bq --location="$REGION" mk --table "$PROJECT:lending_gold.agent_audit" run_id:STRING,application_id:STRING,ts:STRING,step:STRING,event_type:STRING,detail:STRING
bq --location="$REGION" show "$PROJECT:lending_gold.officer_decisions" >/dev/null 2>&1 || bq --location="$REGION" mk --table "$PROJECT:lending_gold.officer_decisions" application_id:STRING,decided_at:STRING,agent_recommendation:STRING,officer_decision:STRING,override:INT64,override_reason:STRING,decided_by:STRING,run_id:STRING

echo "== 4/6 Build curated and decision-ready layers"
python3 deploy/render_sql.py > /tmp/nirnay_transform.sql
bq --location="$REGION" query --use_legacy_sql=false --project_id="$PROJECT" < /tmp/nirnay_transform.sql >/dev/null
bq --location="$REGION" query --use_legacy_sql=false --format=pretty "SELECT screening_result, COUNT(*) files FROM \`$PROJECT.lending_gold.application_features\` GROUP BY 1"

echo "== 5/6 Service account and roles"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create nirnay-run --display-name "Nirnay Cloud Run"
for role in roles/bigquery.dataEditor roles/bigquery.jobUser roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role "$role" --condition=None >/dev/null
done

PN=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role roles/run.builder --condition=None >/dev/null 2>&1 || true

echo "   Checking which Gemini model this project can use..."
TOKEN=$(gcloud auth print-access-token)
MODEL=""
for m in gemini-2.5-flash gemini-3-flash gemini-3.5-flash gemini-flash-latest gemini-3-flash-preview; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://aiplatform.googleapis.com/v1/projects/$PROJECT/locations/global/publishers/google/models/$m:generateContent" \
    -d '{"contents":[{"role":"user","parts":[{"text":"Reply with OK"}]}]}')
  echo "   $m -> $code"
  if [ "$code" = "200" ]; then MODEL="$m"; break; fi
done
[ -z "$MODEL" ] && { echo "   No Gemini model answered yet (new projects can take a few minutes). The app will retry at runtime."; MODEL="gemini-2.5-flash,gemini-3-flash,gemini-3.5-flash,gemini-flash-latest"; }

echo "== 6/6 Build and deploy to Cloud Run ($REGION)"
gcloud run deploy nirnay --source . --region "$REGION" --service-account "$SA" \
  --set-env-vars "^@^GCP_PROJECT=$PROJECT@BQ_LOCATION=$REGION@GEMINI_LOCATION=global@GEMINI_MODEL=$MODEL" \
  --memory 1Gi --cpu 1 --min-instances 0 --max-instances 1 --timeout 300 --allow-unauthenticated --quiet || {
  echo; echo "Deploy finished but public access may be blocked by an organisation policy (domain restricted sharing)."
  echo "Fix: gcloud org-policies reset constraints/iam.allowedPolicyMemberDomains --project=$PROJECT"
  echo "then: gcloud run services add-iam-policy-binding nirnay --region $REGION --member=allUsers --role=roles/run.invoker"; }
URL=$(gcloud run services describe nirnay --region "$REGION" --format 'value(status.url)')
echo; echo "Live at: $URL"
curl -s "$URL/api/meta"; echo
