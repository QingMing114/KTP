#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:8005"
PASS=0
FAIL=0
TOTAL=0
RUN_ID=""
SESSION_ID=""
DOC_ID=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() { TOTAL=$((TOTAL+1)); PASS=$((PASS+1)); echo -e "${GREEN}PASS${NC} [$TOTAL] $1"; }
log_fail() { TOTAL=$((TOTAL+1)); FAIL=$((FAIL+1)); echo -e "${RED}FAIL${NC} [$TOTAL] $1 — $2"; }
log_info() { echo -e "${YELLOW}INFO${NC} $1"; }

assert_status() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        log_pass "$desc"
    else
        log_fail "$desc" "expected HTTP $expected, got $actual"
    fi
}

assert_contains() {
    local desc="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        log_pass "$desc"
    else
        log_fail "$desc" "expected to contain '$needle'"
    fi
}

assert_not_contains() {
    local desc="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        log_fail "$desc" "expected NOT to contain '$needle'"
    else
        log_pass "$desc"
    fi
}

# ============================================================
# 0. Health check
# ============================================================
log_info "Checking backend health..."
HEALTH=$(curl -s "$BASE/health") || true
if echo "$HEALTH" | grep -q "ok\|degraded"; then
    log_info "Backend is running"
else
    log_fail "Backend health" "Backend not responding at $BASE"
    echo "Aborting tests."
    exit 1
fi

# ============================================================
# 1.1 Auth Module (7 tests)
# ============================================================
log_info "=== 1.1 Auth Module ==="

TEST_USER="testuser_$(date +%s)"
TEST_PASS="test1234"
ADMIN_USER="admin"
ADMIN_PASS="admin123"

ADMIN_TOKEN=""
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    ADMIN_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
    log_info "Admin login successful"
else
    log_info "Admin login failed (HTTP $HTTP_CODE), will register admin"
    RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"user_id\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')
    if [ "$HTTP_CODE" = "200" ]; then
        ADMIN_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
        log_info "Admin registered and got token"
    fi
fi

# Test 1: Register new user
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.1.1 Register new user" "200" "$HTTP_CODE"
TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
if [ -n "$TOKEN" ]; then
    log_pass "1.1.1b Got JWT token"
else
    log_fail "1.1.1b Got JWT token" "Token empty"
fi

# Test 2: Duplicate registration
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
assert_status "1.1.2 Duplicate registration → 409" "409" "$HTTP_CODE"

# Test 3: Login
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.1.3 Login" "200" "$HTTP_CODE"
TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

# Test 4: Wrong password
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$TEST_USER\",\"password\":\"wrongpassword\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
assert_status "1.1.4 Wrong password → 401" "401" "$HTTP_CODE"

# Test 5: Get /v2/auth/me
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/auth/me" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.1.5 Get current user" "200" "$HTTP_CODE"
assert_contains "1.1.5b Response has user_id" "$BODY" "$TEST_USER"

# Test 6: Change password
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/change-password" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"old_password\":\"$TEST_PASS\",\"new_password\":\"newpass1234\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
assert_status "1.1.6 Change password" "200" "$HTTP_CODE"

# Login with new password to get fresh token
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$TEST_USER\",\"password\":\"newpass1234\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

# Test 7: Admin list users (use admin token)
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/auth/users" \
    -H "Authorization: Bearer $ADMIN_TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.1.7 Admin list users" "200" "$HTTP_CODE"
assert_contains "1.1.7b Response is array" "$BODY" "user_id"

# ============================================================
# 1.2 Session Module (5 tests)
# ============================================================
log_info "=== 1.2 Session Module ==="
sleep 1

# Test 8: Create session
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/sessions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Test Session"}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.2.1 Create session" "200" "$HTTP_CODE"
SESSION_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['session']['session_id'])" 2>/dev/null || echo "")
if [ -n "$SESSION_ID" ]; then
    log_pass "1.2.1b Got session_id"
else
    log_fail "1.2.1b Got session_id" "session_id empty"
fi

# Test 9: List sessions
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/sessions" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.2.2 List sessions" "200" "$HTTP_CODE"
assert_contains "1.2.2b Contains new session" "$BODY" "$SESSION_ID"

# Test 10: Get session detail
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/sessions/$SESSION_ID" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.2.3 Get session detail" "200" "$HTTP_CODE"
assert_contains "1.2.3b Has session_id field" "$BODY" "$SESSION_ID"

# Test 11: Update session title
RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE/v2/sessions/$SESSION_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Updated Title"}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.2.4 Update session title" "200" "$HTTP_CODE"
assert_contains "1.2.4b Title updated" "$BODY" "Updated Title"

# Test 12: Delete session (create a temp one first)
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/sessions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"To Delete"}')
BODY=$(echo "$RESP" | sed '$d')
DEL_SID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['session']['session_id'])" 2>/dev/null || echo "")
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/v2/sessions/$DEL_SID" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
assert_status "1.2.5 Delete session" "204" "$HTTP_CODE"

# ============================================================
# 1.3 Messages & SSE (3 tests, real LLM)
# ============================================================
log_info "=== 1.3 Messages & SSE (Real LLM) ==="
sleep 1

# Test 13: Send message synchronously
RESP=$(curl -s -w "\n%{http_code}" --max-time 120 -X POST "$BASE/v2/sessions/$SESSION_ID/messages" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message":"你好","user_id":"tester"}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.3.1 Send message (sync, real LLM)" "200" "$HTTP_CODE"
RUN_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id',''))" 2>/dev/null || echo "")
if [ -n "$RUN_ID" ]; then
    log_pass "1.3.1b Got run_id: ${RUN_ID:0:8}..."
else
    log_fail "1.3.1b Got run_id" "run_id empty"
fi

# Test 14: SSE stream message (real LLM)
SSE_OUTPUT=$(curl -s --max-time 180 -N -X POST "$BASE/v2/sessions/$SESSION_ID/messages/stream" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message":"帮我分析河南小麦的生长状况","user_id":"tester"}' 2>/dev/null || true)
if echo "$SSE_OUTPUT" | grep -q "event:"; then
    log_pass "1.3.2 SSE stream has events"
else
    log_fail "1.3.2 SSE stream has events" "No SSE events found"
fi
if echo "$SSE_OUTPUT" | grep -q "completed\|run.completed"; then
    log_pass "1.3.2b SSE stream completed"
else
    log_fail "1.3.2b SSE stream completed" "No completion event"
fi

# Test 15: List session runs
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/sessions/$SESSION_ID/runs" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.3.3 List session runs" "200" "$HTTP_CODE"

# ============================================================
# 1.4 Knowledge Module (5 tests)
# ============================================================
log_info "=== 1.4 Knowledge Module ==="
sleep 1

# Test 16: Ingest document
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/knowledge/documents/ingest" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"document_id":"test-doc-001","title":"小麦LAI估算方法","source":"web-upload","text":"叶面积指数(LAI)是衡量作物生长状况的重要指标。通过遥感影像可以估算LAI，常用的方法包括经验模型法和物理模型法。PROSAIL辐射传输模型是一种常用的物理模型，可以反演LAI等植被参数。","metadata":{"region":"henan","crop_type":"wheat"}}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.4.1 Ingest document" "200" "$HTTP_CODE"

# Test 17: List documents
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/knowledge/documents" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.4.2 List documents" "200" "$HTTP_CODE"

# Test 18: Get document detail
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/knowledge/documents/test-doc-001" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.4.3 Get document detail"
else
    log_fail "1.4.3 Get document detail" "HTTP $HTTP_CODE (document may not be indexed yet)"
fi

# Test 19: Query knowledge
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/knowledge/query" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"query":"小麦LAI估算方法","top_k":3}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.4.4 Query knowledge"
else
    log_fail "1.4.4 Query knowledge" "HTTP $HTTP_CODE"
fi

# Test 20: Delete document
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/v2/knowledge/documents/test-doc-001" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.4.5 Delete document"
else
    log_fail "1.4.5 Delete document" "HTTP $HTTP_CODE"
fi

# ============================================================
# 1.5 Inference Module (3 tests, real inference use_mock=false)
# ============================================================
log_info "=== 1.5 Inference Module (Real Inference) ==="
sleep 1

# Test 21: Single inference - LAI estimation
RESP=$(curl -s -w "\n%{http_code}" --max-time 120 -X POST "$BASE/v2/inference/run" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"region":"henan","crop_type":"wheat","task_type":"lai_estimation","use_mock":false}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.5.1 Single inference (LAI, real)"
    assert_contains "1.5.1b Response has result" "$BODY" "success\|result\|message"
else
    log_fail "1.5.1 Single inference (LAI, real)" "HTTP $HTTP_CODE"
fi

# Test 22: Batch inference (3 regions)
RESP=$(curl -s -w "\n%{http_code}" --max-time 300 -X POST "$BASE/v2/inference/batch" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"tasks":[{"region":"henan","crop_type":"wheat","task_type":"lai_estimation","use_mock":false},{"region":"shandong","crop_type":"wheat","task_type":"lai_estimation","use_mock":false},{"region":"heilongjiang","crop_type":"wheat","task_type":"crop_health_detection","use_mock":false}]}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.5.2 Batch inference (3 regions, real)"
    assert_contains "1.5.2b Response has total" "$BODY" "total"
else
    log_fail "1.5.2 Batch inference (3 regions, real)" "HTTP $HTTP_CODE"
fi

# Test 23: Single inference - crop health detection
RESP=$(curl -s -w "\n%{http_code}" --max-time 120 -X POST "$BASE/v2/inference/run" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"region":"henan","crop_type":"wheat","task_type":"crop_health_detection","use_mock":false}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.5.3 Single inference (crop health, real)"
else
    log_fail "1.5.3 Single inference (crop health, real)" "HTTP $HTTP_CODE"
fi

# ============================================================
# 1.6 Tools & System (5 tests)
# ============================================================
log_info "=== 1.6 Tools & System ==="
sleep 1

# Test 24: List tools
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/tools" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.6.1 List tools" "200" "$HTTP_CODE"
assert_contains "1.6.1b Tools array not empty" "$BODY" "name"

# Test 25: List agents
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/agents" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.6.2 List agents" "200" "$HTTP_CODE"

# Test 26: List domain packs
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/domain-packs" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.6.3 List domain packs" "200" "$HTTP_CODE"

# Test 27: V2 health check (system status)
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/health" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.6.4 V2 health check (system status)" "200" "$HTTP_CODE"
assert_contains "1.6.4b Status ok" "$BODY" "ok"

# Test 28: Health check
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/health" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.6.5 V2 health check" "200" "$HTTP_CODE"
assert_contains "1.6.5b Status ok" "$BODY" "ok"

# ============================================================
# 1.7 Run Management (4 tests)
# ============================================================
log_info "=== 1.7 Run Management ==="
sleep 1

# Test 29: List all runs
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/runs" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.7.1 List all runs" "200" "$HTTP_CODE"

# Test 30: Get run detail (if we have a run_id)
if [ -n "$RUN_ID" ]; then
    RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/runs/$RUN_ID" \
        -H "Authorization: Bearer $TOKEN")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')
    assert_status "1.7.2 Get run detail" "200" "$HTTP_CODE"

    # Test 31: Get run trace
    RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/runs/$RUN_ID/trace" \
        -H "Authorization: Bearer $TOKEN")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    assert_status "1.7.3 Get run trace" "200" "$HTTP_CODE"

    # Test 32: Replay run
    RESP=$(curl -s -w "\n%{http_code}" --max-time 120 -X POST "$BASE/v2/runs/$RUN_ID/replay" \
        -H "Authorization: Bearer $TOKEN")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    assert_status "1.7.4 Replay run" "200" "$HTTP_CODE"
else
    log_fail "1.7.2 Get run detail" "No run_id available"
    log_fail "1.7.3 Get run trace" "No run_id available"
    log_fail "1.7.4 Replay run" "No run_id available"
fi

# ============================================================
# 1.8 Plugin System (4 tests)
# ============================================================
log_info "=== 1.8 Plugin System ==="
sleep 1

# Test 33: Register plugin tool
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/plugins/tools" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"name":"test.echo_tool","display_name":"Echo Test Tool","description":"A test tool that echoes input","category":"plugin","pack_name":"test","endpoint":{"adapter":"python_callable","module":"v2.tools.handlers","function":"handle_general_query"},"input_schema":{"query":"string"},"safety_level":"safe","enabled":true}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.8.1 Register plugin tool" "200" "$HTTP_CODE"

# Test 34: List plugin tools
RESP=$(curl -s -w "\n%{http_code}" -X GET "$BASE/v2/plugins/tools" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.8.2 List plugin tools" "200" "$HTTP_CODE"

# Test 35: Test plugin tool
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v2/plugins/tools/test.echo_tool/test" \
    -H "Content-Type: application/json" \
    -d '{"query":"hello test"}')
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "1.8.3 Test plugin tool"
else
    log_fail "1.8.3 Test plugin tool" "HTTP $HTTP_CODE"
fi

# Test 36: Unregister plugin tool
RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/v2/plugins/tools/test.echo_tool" \
    -H "Authorization: Bearer $TOKEN")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "1.8.4 Unregister plugin tool" "200" "$HTTP_CODE"

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================"
echo "  KTP Backend API Integration Test Results"
echo "============================================"
echo -e "  ${GREEN}PASS: $PASS${NC}"
echo -e "  ${RED}FAIL: $FAIL${NC}"
echo "  TOTAL: $TOTAL"
echo "============================================"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "  ${GREEN}All tests passed!${NC}"
    exit 0
fi
