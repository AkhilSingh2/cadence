#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000/v1}"
HDR=(-H "Content-Type: application/json" -H "X-User-Id: 00000000-0000-4000-8000-000000000001")

echo "== healthz =="
curl -sf "$BASE/healthz" | tee /tmp/cadence_healthz.json
echo

echo "== demo bad day =="
curl -sf -X POST "$BASE/demo/bad-day" "${HDR[@]}" | tee /tmp/cadence_bad_day.json
echo
python3 - <<'PY'
import json
p=json.load(open("/tmp/cadence_bad_day.json"))
assert p["day_state"] in ("RED","AMBER","DELOAD"), p["day_state"]
nut=p["nutrition"]
assert nut.get("surface_calories") is False
study=p["study"]
assert study.get("minutes", 99) <= 30
print("bad-day plan OK:", p["day_state"], "study", study.get("minutes"), "opener:", p.get("opener","")[:60])
PY

echo "== chat =="
curl -sf -X POST "$BASE/chat" "${HDR[@]}" -d '{"message":"I hate mass-gainer shakes","turn_class":"chat"}' | tee /tmp/cadence_chat.json
echo

echo "== preference =="
curl -sf -X POST "$BASE/preferences" "${HDR[@]}" -d '{"content":"Dislikes mass-gainer shakes — bloating","metadata":{"disliked":true,"food":"mass-gainer"}}' >/dev/null

echo "== dsa attempt x3 =="
for i in 1 2 3; do
  curl -sf -X POST "$BASE/problems/attempt" "${HDR[@]}" \
    -d '{"problem_ref":"invert-binary-tree","difficulty":"medium","outcome":"stuck","bug_tags":["recursion_base_case"],"minutes_spent":20}' >/dev/null
done

echo "== dashboard =="
curl -sf "$BASE/dashboard" "${HDR[@]}" | tee /tmp/cadence_dash.json
echo
echo "SMOKE OK"
