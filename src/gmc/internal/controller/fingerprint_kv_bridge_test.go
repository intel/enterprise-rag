/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"testing"

	"github.com/nats-io/nats.go/jetstream"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// fakeKV is an in-memory kvStore for exercising the projection logic without a
// real NATS server.
type fakeKV struct {
	mu   sync.Mutex
	data map[string][]byte
}

func newFakeKV() *fakeKV {
	return &fakeKV{data: make(map[string][]byte)}
}

func (f *fakeKV) Put(_ context.Context, key string, value []byte) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.data[key] = append([]byte(nil), value...)
	return nil
}

func (f *fakeKV) Get(_ context.Context, key string) ([]byte, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	v, ok := f.data[key]
	return v, ok, nil
}

func (f *fakeKV) Keys(_ context.Context) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	keys := make([]string, 0, len(f.data))
	for k := range f.data {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys, nil
}

func (f *fakeKV) Delete(_ context.Context, key string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.data, key)
	return nil
}

// failingPutKV wraps fakeKV and returns putErr from Put for the key failOn,
// leaving every other key stored normally. putErr lets a test choose between an
// invalid-key rejection (skippable) and a backend failure (must fail the pass).
type failingPutKV struct {
	*fakeKV
	failOn string
	putErr error
}

func (f *failingPutKV) Put(ctx context.Context, key string, value []byte) error {
	if key == f.failOn {
		return f.putErr
	}
	return f.fakeKV.Put(ctx, key, value)
}

// fakeSource is an in-memory rowSource keyed like the fingerprint_config
// table.
type fakeSource struct {
	rows map[string]fpRow
}

func newFakeSource() *fakeSource {
	return &fakeSource{rows: make(map[string]fpRow)}
}

func (s *fakeSource) set(row fpRow) {
	s.rows[row.kvKey()] = row
}

func (s *fakeSource) Row(_ context.Context, pipeline, tenant, paramsKey string) (fpRow, bool, error) {
	key := pipeline + "." + tenant + "." + paramsKey
	row, ok := s.rows[key]
	return row, ok, nil
}

func (s *fakeSource) AllRows(_ context.Context) ([]fpRow, error) {
	rows := make([]fpRow, 0, len(s.rows))
	for _, r := range s.rows {
		rows = append(rows, r)
	}
	return rows, nil
}

// flakySource wraps fakeSource and returns an error from AllRows while fail is
// set, emulating a transiently unreachable Postgres during the initial seed.
type flakySource struct {
	*fakeSource
	fail bool
}

func (s *flakySource) AllRows(ctx context.Context) ([]fpRow, error) {
	if s.fail {
		return nil, errors.New("postgres unavailable")
	}
	return s.fakeSource.AllRows(ctx)
}

func newTestProjector(kv kvStore, src rowSource) *projector {
	return &projector{kv: kv, src: src, log: log.Log}
}

func TestPublishWritesChangedRowToKV(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"max_new_tokens":128}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.publish(context.Background(), "chatqa", "_global", "llm"); err != nil {
		t.Fatalf("publish: %v", err)
	}

	got, ok, _ := kv.Get(context.Background(), "chatqa._global.llm")
	if !ok {
		t.Fatal("expected KV key chatqa._global.llm to be written")
	}
	if string(got) != `{"max_new_tokens":128}` {
		t.Fatalf("unexpected KV value: %s", got)
	}
}

func TestPublishMissingRowIsNoOp(t *testing.T) {
	kv := newFakeKV()
	proj := newTestProjector(kv, newFakeSource())

	if err := proj.publish(context.Background(), "chatqa", "_global", "llm"); err != nil {
		t.Fatalf("publish: %v", err)
	}
	if keys, _ := kv.Keys(context.Background()); len(keys) != 0 {
		t.Fatalf("expected no KV keys, got %v", keys)
	}
}

func TestReconcileInsertsMissingKey(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "retriever",
		Values: []byte(`{"k":4}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	got, ok, _ := kv.Get(context.Background(), "chatqa._global.retriever")
	if !ok || string(got) != `{"k":4}` {
		t.Fatalf("expected missing key inserted, got ok=%v value=%s", ok, got)
	}
}

func TestReconcileRepairsStaleValue(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"max_new_tokens":256}`), Version: 2})
	// KV holds an older value for the same key.
	_ = kv.Put(context.Background(), "chatqa._global.llm", []byte(`{"max_new_tokens":128}`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	got, _, _ := kv.Get(context.Background(), "chatqa._global.llm")
	if string(got) != `{"max_new_tokens":256}` {
		t.Fatalf("expected stale value repaired, got %s", got)
	}
}

func TestReconcileIgnoresJSONFormattingDifferences(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"a":1,"b":2}`), Version: 1})
	// Same document, different key order and whitespace.
	_ = kv.Put(context.Background(), "chatqa._global.llm", []byte(`{ "b": 2, "a": 1 }`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	// The value must be left untouched since it is semantically equal.
	got, _, _ := kv.Get(context.Background(), "chatqa._global.llm")
	if string(got) != `{ "b": 2, "a": 1 }` {
		t.Fatalf("expected equal JSON left untouched, got %s", got)
	}
}

func TestReconcilePreservesLargeIntegers(t *testing.T) {
	// A large integer must survive canonicalisation without float coercion, so
	// an equal document is not needlessly rewritten and a changed one is.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"seed":9007199254740993}`), Version: 1})
	// Same value, different key order/whitespace: must be treated as equal.
	_ = kv.Put(context.Background(), "chatqa._global.llm", []byte(`{ "seed": 9007199254740993 }`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	got, _, _ := kv.Get(context.Background(), "chatqa._global.llm")
	if string(got) != `{ "seed": 9007199254740993 }` {
		t.Fatalf("expected equal large-integer document left untouched, got %s", got)
	}
}

func TestReconcileRepairsTrailingGarbageValue(t *testing.T) {
	// A KV value with trailing bytes after a valid document is corrupt and must
	// not compare equal to the Postgres row, so reconcile rewrites it.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"a":1}`), Version: 1})
	_ = kv.Put(context.Background(), "chatqa._global.llm", []byte(`{"a":1}junk`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	got, _, _ := kv.Get(context.Background(), "chatqa._global.llm")
	if string(got) != `{"a":1}` {
		t.Fatalf("expected corrupt trailing-garbage value repaired, got %s", got)
	}
}

func TestCanonicalJSONRejectsTrailingBytes(t *testing.T) {
	// Trailing non-whitespace makes the input fall back to raw so it does not
	// compare equal to a clean document.
	if string(canonicalJSON([]byte(`{"a":1}junk`))) != `{"a":1}junk` {
		t.Fatal("expected trailing garbage to fall back to raw bytes")
	}
	// Trailing whitespace is tolerated and canonicalised.
	if string(canonicalJSON([]byte(`{"a":1}  `))) != `{"a":1}` {
		t.Fatal("expected trailing whitespace to be tolerated")
	}
	// A second document is trailing garbage.
	if string(canonicalJSON([]byte(`{"a":1}{"b":2}`))) != `{"a":1}{"b":2}` {
		t.Fatal("expected a trailing second document to fall back to raw bytes")
	}
}

func TestReconcileOnceTracksHealth(t *testing.T) {
	// The immediate reconcile pass seeds KV and clears the error counter.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"a":1}`), Version: 1})
	b := &FingerprintKVBridge{log: log.Log}
	b.healthy.Store(false)
	proj := newTestProjector(kv, src)

	errs := maxConsecutiveReconcileErrors
	b.reconcileOnce(context.Background(), proj, &errs)

	if errs != 0 {
		t.Fatalf("expected error counter reset to 0, got %d", errs)
	}
	if !b.healthy.Load() {
		t.Fatal("expected a successful reconcile to mark the bridge healthy")
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); !ok {
		t.Fatal("expected the immediate reconcile to seed KV")
	}
}

func TestReconcileDeletesOrphanUnderKnownPipeline(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"x":1}`), Version: 1})
	// Orphan under the same (still-present) pipeline: no matching row.
	_ = kv.Put(context.Background(), "chatqa._global.reranker", []byte(`{"stale":true}`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.reranker"); ok {
		t.Fatal("expected orphaned key under known pipeline to be deleted")
	}
}

func TestReconcileKeepsKeysOfRemovedPipeline(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"x":1}`), Version: 1})
	// A key whose pipeline no longer appears in Postgres at all.
	_ = kv.Put(context.Background(), "docsum._global.llm", []byte(`{"y":2}`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "docsum._global.llm"); !ok {
		t.Fatal("expected key of fully removed pipeline to be left alone")
	}
}

func TestReconcileHealsDroppedNotification(t *testing.T) {
	// Simulate a NOTIFY that never arrived: Postgres has a row the bridge
	// never published. The reconcile loop must bring KV back in line.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"v":1}`), Version: 1})
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "reranker",
		Values: []byte(`{"v":2}`), Version: 1})
	proj := newTestProjector(kv, src)

	// Only one of the two changes made it to KV via the live path.
	if err := proj.publish(context.Background(), "chatqa", "_global", "llm"); err != nil {
		t.Fatalf("publish: %v", err)
	}
	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.reranker"); !ok {
		t.Fatal("expected reconcile to heal the dropped notification")
	}
}

func TestResyncRepublishesAllRows(t *testing.T) {
	// Emulates a NATS restart: the bucket is empty and resync must reseed it.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"v":1}`), Version: 1})
	src.set(fpRow{Pipeline: "docsum", Tenant: "acme", ParamsKey: "prompt_template",
		Values: []byte(`{"system":"hi"}`), Version: 3})
	proj := newTestProjector(kv, src)

	if err := proj.resync(context.Background()); err != nil {
		t.Fatalf("resync: %v", err)
	}
	keys, _ := kv.Keys(context.Background())
	if len(keys) != 2 {
		t.Fatalf("expected 2 keys after resync, got %v", keys)
	}
	if _, ok, _ := kv.Get(context.Background(), "docsum.acme.prompt_template"); !ok {
		t.Fatal("expected multi-tenant key to be published by resync")
	}
}

func TestParseNotifyPayload(t *testing.T) {
	pipeline, tenant, paramsKey, err := parseNotifyPayload(
		`{"pipeline":"chatqa","tenant":"_global","params_key":"llm"}`)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if pipeline != "chatqa" || tenant != "_global" || paramsKey != "llm" {
		t.Fatalf("unexpected parse result: %q %q %q", pipeline, tenant, paramsKey)
	}
}

func TestParseNotifyPayloadRejectsIncomplete(t *testing.T) {
	cases := []string{
		`{"pipeline":"chatqa","tenant":"_global"}`,
		`not json`,
		`{}`,
	}
	for _, payload := range cases {
		if _, _, _, err := parseNotifyPayload(payload); err == nil {
			t.Fatalf("expected error for payload %q", payload)
		}
	}
}

func TestKVKeyFormat(t *testing.T) {
	row := fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm"}
	if got := row.kvKey(); got != "chatqa._global.llm" {
		t.Fatalf("unexpected KV key: %s", got)
	}
}

func TestReconcileSkipsInvalidKeySegments(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"ok":1}`), Version: 1})
	// A tenant value containing a dot would produce an ambiguous key.
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad.tenant", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	keys, _ := kv.Keys(context.Background())
	if len(keys) != 1 || keys[0] != "chatqa._global.llm" {
		t.Fatalf("expected only the valid key written, got %v", keys)
	}
}

func TestReconcileCleansOrphansForPipelineWithInvalidRows(t *testing.T) {
	// A pipeline is present in Postgres but its only row has an unusable tenant
	// segment. Orphan cleanup must still run under that pipeline.
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad.tenant", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	_ = kv.Put(context.Background(), "chatqa._global.reranker", []byte(`{"stale":true}`))
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.reranker"); ok {
		t.Fatal("expected orphan under a still-present pipeline to be deleted even when its rows are invalid")
	}
}

func TestPublishSkipsInvalidKeySegments(t *testing.T) {
	kv := newFakeKV()
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "ll*m",
		Values: []byte(`{"bad":1}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.publish(context.Background(), "chatqa", "_global", "ll*m"); err != nil {
		t.Fatalf("publish: %v", err)
	}
	if keys, _ := kv.Keys(context.Background()); len(keys) != 0 {
		t.Fatalf("expected wildcard segment to be skipped, got %v", keys)
	}
}

func TestValidKeySegment(t *testing.T) {
	// The allowed charset covers NATS KV keys: alphanumerics plus '-_/=', which
	// includes a raw Keycloak sub UUID used as a per-user tenant.
	good := []string{
		"chatqa", "_global", "prompt_template", "llm-draft-1", "a=b", "a/b",
		"3f2504e0-4f89-41d3-9a0c-0305e82c3301",
	}
	for _, s := range good {
		if !validKeySegment(s) {
			t.Errorf("expected %q to be a valid segment", s)
		}
	}
	// A colon is invalid in a NATS KV key, so the "user:alice" tenant format is
	// rejected rather than accepted and then failing at kv.Put.
	bad := []string{"", "has space", "has.dot", "wild*", "gt>", "tab\there", "user:alice", "a:b", "a@b", "a+b"}
	for _, s := range bad {
		if validKeySegment(s) {
			t.Errorf("expected %q to be an invalid segment", s)
		}
	}
}

func TestPipelineOf(t *testing.T) {
	if got := pipelineOf("chatqa._global.llm"); got != "chatqa" {
		t.Fatalf("unexpected pipeline: %s", got)
	}
	if got := pipelineOf("nodots"); got != "nodots" {
		t.Fatalf("unexpected pipeline: %s", got)
	}
}

func TestBridgeReadyCheck(t *testing.T) {
	b := &FingerprintKVBridge{}
	b.healthy.Store(true)
	if err := b.ReadyCheck(nil); err != nil {
		t.Fatalf("expected ready when healthy, got %v", err)
	}
	b.healthy.Store(false)
	if err := b.ReadyCheck(nil); err == nil {
		t.Fatal("expected not-ready when unhealthy")
	}
}

// TestBridgeReadyEndpointHandler exercises the http.Handler that the manager
// serves at /readyz-bridge on the metrics server. The bridge readiness is kept
// off the pod's /readyz probe, so the webhook stays reachable when the backends
// are down; this endpoint surfaces the same check for manual inspection.
func TestBridgeReadyEndpointHandler(t *testing.T) {
	b := &FingerprintKVBridge{}
	handler := &healthz.CheckHandler{Checker: b.ReadyCheck}

	b.healthy.Store(true)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz-bridge", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 when healthy, got %d", rec.Code)
	}

	b.healthy.Store(false)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz-bridge", nil))
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when unhealthy, got %d", rec.Code)
	}
}

func TestBridgeNeedLeaderElection(t *testing.T) {
	b := &FingerprintKVBridge{}
	if !b.NeedLeaderElection() {
		t.Fatal("bridge must run under leader election")
	}
}

func TestReconcileSkipsInvalidKeyRowAndReportsSuccess(t *testing.T) {
	// One row's key is rejected by NATS as invalid; the other rows must still
	// converge and the pass reports success so readiness is not withheld for a
	// single un-encodable row.
	kv := &failingPutKV{fakeKV: newFakeKV(), failOn: "chatqa.bad.llm", putErr: jetstream.ErrInvalidKey}
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"ok":1}`), Version: 1})
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	src.set(fpRow{Pipeline: "docsum", Tenant: "_global", ParamsKey: "reranker",
		Values: []byte(`{"ok":2}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); !ok {
		t.Fatal("expected the good row before the bad one to be published")
	}
	if _, ok, _ := kv.Get(context.Background(), "docsum._global.reranker"); !ok {
		t.Fatal("expected the good row after the bad one to be published")
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa.bad.llm"); ok {
		t.Fatal("expected the un-publishable row to be absent")
	}
}

func TestReconcileFailsPassOnBackendError(t *testing.T) {
	// A non-invalid-key KV failure (e.g. a connection/permission error) must not
	// be swallowed: reconcile continues past it but returns the error so
	// readiness reflects an unhealthy KV backend. The healthy row still lands.
	kv := &failingPutKV{fakeKV: newFakeKV(), failOn: "chatqa.bad.llm", putErr: errors.New("nats: connection closed")}
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"ok":1}`), Version: 1})
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.reconcile(context.Background()); err == nil {
		t.Fatal("expected reconcile to return the backend error")
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); !ok {
		t.Fatal("expected the healthy row to be published despite the backend error")
	}
}

func TestResyncSkipsInvalidKeyRowAndReportsSuccess(t *testing.T) {
	// The initial seed path must be resilient too: a row NATS rejects as invalid
	// is skipped so the remaining rows are still seeded and resync succeeds.
	kv := &failingPutKV{fakeKV: newFakeKV(), failOn: "chatqa.bad.llm", putErr: jetstream.ErrInvalidKey}
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"ok":1}`), Version: 1})
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.resync(context.Background()); err != nil {
		t.Fatalf("resync: %v", err)
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); !ok {
		t.Fatal("expected the good row to be seeded despite a sibling failing")
	}
}

func TestResyncFailsOnBackendError(t *testing.T) {
	// A backend error during the initial seed must be returned so Start leaves
	// the bridge unready rather than reporting ready over a half-seeded bucket.
	kv := &failingPutKV{fakeKV: newFakeKV(), failOn: "chatqa.bad.llm", putErr: errors.New("nats: permissions violation")}
	src := newFakeSource()
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"ok":1}`), Version: 1})
	src.set(fpRow{Pipeline: "chatqa", Tenant: "bad", ParamsKey: "llm",
		Values: []byte(`{"bad":1}`), Version: 1})
	proj := newTestProjector(kv, src)

	if err := proj.resync(context.Background()); err == nil {
		t.Fatal("expected resync to return the backend error")
	}
}

func TestReconcileOnceStaysUnhealthyUntilKVSeeded(t *testing.T) {
	// The readiness gate at the reconcile level: while the row source is failing
	// the bridge stays unready, and it flips ready only once a reconcile pass
	// populates KV.
	kv := newFakeKV()
	src := &flakySource{fakeSource: newFakeSource()}
	src.set(fpRow{Pipeline: "chatqa", Tenant: "_global", ParamsKey: "llm",
		Values: []byte(`{"a":1}`), Version: 1})
	b := &FingerprintKVBridge{log: log.Log}
	b.healthy.Store(false)
	proj := newTestProjector(kv, src)

	errs := 0
	src.fail = true
	b.reconcileOnce(context.Background(), proj, &errs)
	if b.healthy.Load() {
		t.Fatal("expected bridge to stay unready while reconcile fails")
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); ok {
		t.Fatal("expected KV to remain unseeded while reconcile fails")
	}

	src.fail = false
	b.reconcileOnce(context.Background(), proj, &errs)
	if !b.healthy.Load() {
		t.Fatal("expected bridge to become ready once reconcile seeds KV")
	}
	if _, ok, _ := kv.Get(context.Background(), "chatqa._global.llm"); !ok {
		t.Fatal("expected KV to be seeded by the successful reconcile")
	}
}
