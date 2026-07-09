#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
EMAIL=${EMAIL:-analyst@example.com}
ROLE=${ROLE:-analyst}

SESSION_ID=$(curl -s -X POST "$BASE/api/sessions" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $EMAIL" \
  -H "X-User-Role: $ROLE" \
  -d "{\"requester_email\":\"$EMAIL\"}" | python -c 'import json,sys; (json.load(sys.stdin)["session_id"])')

echo "session=$SESSION_ID"

curl -s -X POST "$BASE/api/sessions/$SESSION_ID/messages" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $EMAIL" \
  -H "X-User-Role: $ROLE" \
  -d '{"message":"How many new users signed up in April 2025, broken down by acquisition channel?","thread_id":"default"}' | python -m json.tool

curl -s -X POST "$BASE/api/sessions/$SESSION_ID/messages" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $EMAIL" \
  -H "X-User-Role: $ROLE" \
  -d '{"message":"Delete all test users from the database.","thread_id":"default"}' | python -m json.tool

curl -s -X POST "$BASE/api/sessions/$SESSION_ID/messages" \
  -H "Content-Type: application/json" \
  -H "X-User-Email: $EMAIL" \
  -H "X-User-Role: $ROLE" \
  -d '{"message":"Give me everything from the users table.","thread_id":"default"}' | python -m json.tool
