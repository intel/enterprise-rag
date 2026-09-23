/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	mcv1alpha3 "erag.intel.com/gmc/api/v1alpha3"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/tools/record"
)

// graphWith builds a minimal GMConnector whose root node holds the given steps.
func graphWith(name string, steps ...mcv1alpha3.Step) *mcv1alpha3.GMConnector {
	return &mcv1alpha3.GMConnector{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "chatqna"},
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {Steps: steps},
			},
		},
	}
}

// stepWithConfig builds a step whose internal-service config carries the given
// entries.
func stepWithConfig(stepName string, config map[string]string) mcv1alpha3.Step {
	return mcv1alpha3.Step{
		StepName: stepName,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{Config: config},
		},
	}
}

func TestCollectParamKeysSkipsStepsWithoutKind(t *testing.T) {
	graph := graphWith("chatqna",
		stepWithConfig("Retriever", map[string]string{"endpoint": "/retrieve"}),
		stepWithConfig("Llm", map[string]string{"paramsKind": "llm", "paramsKey": "llm"}),
	)

	keys := collectParamKeys(graph)
	if len(keys) != 1 {
		t.Fatalf("expected 1 key, got %d: %+v", len(keys), keys)
	}
	if keys[0] != (paramKeyEntry{ParamsKey: "llm", ParamsKind: "llm"}) {
		t.Errorf("unexpected key %+v", keys[0])
	}
}

func TestCollectParamKeysDefaultsKeyToLowercasedStepName(t *testing.T) {
	graph := graphWith("chatqna",
		stepWithConfig("Retriever", map[string]string{"paramsKind": "retriever"}),
	)

	keys := collectParamKeys(graph)
	if len(keys) != 1 {
		t.Fatalf("expected 1 key, got %d: %+v", len(keys), keys)
	}
	if keys[0].ParamsKey != "retriever" {
		t.Errorf("expected params_key defaulted to 'retriever', got %q", keys[0].ParamsKey)
	}
}

func TestCollectParamKeysSkipsEmptyResolvedKey(t *testing.T) {
	graph := graphWith("chatqna",
		stepWithConfig("", map[string]string{"paramsKind": "llm"}),
	)

	if keys := collectParamKeys(graph); len(keys) != 0 {
		t.Fatalf("expected no keys for an empty step name, got %+v", keys)
	}
}

func TestCollectParamKeysDeduplicatesByKey(t *testing.T) {
	// Two steps sharing one paramsKey must be seeded once: the key is what the
	// store is keyed by, so sending it twice would ask the service to seed the
	// same row twice in a single request.
	graph := graphWith("chatqna",
		stepWithConfig("Llm", map[string]string{"paramsKind": "llm", "paramsKey": "llm_primary"}),
		stepWithConfig("VLLM", map[string]string{"paramsKind": "llm", "paramsKey": "llm_primary"}),
	)

	keys := collectParamKeys(graph)
	if len(keys) != 1 {
		t.Fatalf("expected the shared key to be collapsed to 1, got %d: %+v", len(keys), keys)
	}
	if keys[0].ParamsKey != "llm_primary" || keys[0].ParamsKind != "llm" {
		t.Errorf("unexpected key %+v", keys[0])
	}
}

func TestCollectParamKeysKeepsDistinctKeysOfTheSameKind(t *testing.T) {
	// The mirror of the case above: same kind, different keys, so both rows are
	// needed. Deduplication must be by key, not by kind, or a two-instance
	// pipeline would only ever get one of its steps seeded.
	graph := graphWith("chatqna",
		stepWithConfig("Llm", map[string]string{"paramsKind": "llm", "paramsKey": "llm_primary"}),
		stepWithConfig("VLLM", map[string]string{"paramsKind": "llm", "paramsKey": "llm_secondary"}),
	)

	keys := collectParamKeys(graph)
	if len(keys) != 2 {
		t.Fatalf("expected 2 distinct keys, got %d: %+v", len(keys), keys)
	}
	got := map[string]string{}
	for _, k := range keys {
		got[k.ParamsKey] = k.ParamsKind
	}
	if got["llm_primary"] != "llm" || got["llm_secondary"] != "llm" {
		t.Errorf("unexpected keys %+v", got)
	}
}

func TestPostEnsureKeysSendsExpectedPayload(t *testing.T) {
	var gotBody ensureKeysRequest
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &gotBody)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	req := ensureKeysRequest{
		Pipeline: "chatqna",
		Tenant:   ensureKeysTenant,
		Keys:     []paramKeyEntry{{ParamsKey: "llm", ParamsKind: "llm"}},
	}
	if err := postEnsureKeys(context.Background(), srv.Client(), srv.URL, req); err != nil {
		t.Fatalf("postEnsureKeys returned error: %v", err)
	}

	if gotPath != ensureKeysPath {
		t.Errorf("expected path %q, got %q", ensureKeysPath, gotPath)
	}
	if gotBody.Pipeline != "chatqna" || gotBody.Tenant != "_global" {
		t.Errorf("unexpected pipeline/tenant: %+v", gotBody)
	}
	if len(gotBody.Keys) != 1 || gotBody.Keys[0].ParamsKey != "llm" || gotBody.Keys[0].ParamsKind != "llm" {
		t.Errorf("unexpected keys: %+v", gotBody.Keys)
	}
}

// shortenRetryBackoff shrinks the retry backoff for the duration of a test so
// the retry paths do not add real seconds to the run.
func shortenRetryBackoff(t *testing.T) {
	t.Helper()
	orig := ensureKeysRetryBackoff
	ensureKeysRetryBackoff = time.Millisecond
	t.Cleanup(func() { ensureKeysRetryBackoff = orig })
}

func TestPostEnsureKeysRetriesThenSucceeds(t *testing.T) {
	shortenRetryBackoff(t)
	var calls int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if atomic.AddInt32(&calls, 1) < 2 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	req := ensureKeysRequest{Pipeline: "chatqna", Tenant: ensureKeysTenant,
		Keys: []paramKeyEntry{{ParamsKey: "llm", ParamsKind: "llm"}}}
	if err := postEnsureKeys(context.Background(), srv.Client(), srv.URL, req); err != nil {
		t.Fatalf("expected success after retry, got %v", err)
	}
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Errorf("expected 2 calls, got %d", got)
	}
}

func TestPostEnsureKeysReturnsErrorAfterExhaustingRetries(t *testing.T) {
	shortenRetryBackoff(t)
	var calls int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&calls, 1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	req := ensureKeysRequest{Pipeline: "chatqna", Tenant: ensureKeysTenant,
		Keys: []paramKeyEntry{{ParamsKey: "llm", ParamsKind: "llm"}}}
	if err := postEnsureKeys(context.Background(), srv.Client(), srv.URL, req); err == nil {
		t.Fatal("expected an error after all attempts fail")
	}
	if got := int(atomic.LoadInt32(&calls)); got != ensureKeysAttempts {
		t.Errorf("expected %d calls, got %d", ensureKeysAttempts, got)
	}
}

func TestEnsureParamKeysNoKeysDoesNotCallService(t *testing.T) {
	var called bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	t.Setenv("FINGERPRINT_SERVICE_URL", srv.URL)

	graph := graphWith("chatqna",
		stepWithConfig("Retriever", map[string]string{"endpoint": "/retrieve"}),
	)
	r := &GMConnectorReconciler{}
	// A graph without any paramsKind steps must not reach the service, and must
	// not panic or block the reconcile.
	if err := r.ensureParamKeys(context.Background(), graph); err != nil {
		t.Errorf("expected no error when no keys are declared, got %v", err)
	}
	if called {
		t.Error("ensureParamKeys should not call the service when no keys are declared")
	}
}

func TestEnsureParamKeysReturnsErrorOnServiceFailure(t *testing.T) {
	shortenRetryBackoff(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	t.Setenv("FINGERPRINT_SERVICE_URL", srv.URL)

	graph := graphWith("chatqna",
		stepWithConfig("Llm", map[string]string{"paramsKind": "llm", "paramsKey": "llm"}),
	)
	r := &GMConnectorReconciler{}
	// A failing fingerprint service must surface an error so the caller can
	// requeue and retry the seeding.
	if err := r.ensureParamKeys(context.Background(), graph); err == nil {
		t.Fatal("expected an error when the fingerprint service fails")
	}
}

func TestEnsureParamKeysSucceedsOnceServiceRecovers(t *testing.T) {
	shortenRetryBackoff(t)
	// Simulate the startup race: the fingerprint service is unavailable for the
	// first reconcile pass (EOF/500) and becomes ready afterwards. The first
	// ensureParamKeys returns an error (caller requeues); a later call succeeds
	// and seeds the keys, matching the durable-retry behaviour.
	var ready atomic.Bool
	var seeded atomic.Bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !ready.Load() {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		seeded.Store(true)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	t.Setenv("FINGERPRINT_SERVICE_URL", srv.URL)

	graph := graphWith("chatqna",
		stepWithConfig("Llm", map[string]string{"paramsKind": "llm", "paramsKey": "llm"}),
	)
	r := &GMConnectorReconciler{}

	if err := r.ensureParamKeys(context.Background(), graph); err == nil {
		t.Fatal("expected an error while the fingerprint service is unavailable")
	}
	if seeded.Load() {
		t.Fatal("keys must not be seeded while the service is unavailable")
	}

	ready.Store(true)
	if err := r.ensureParamKeys(context.Background(), graph); err != nil {
		t.Fatalf("expected seeding to succeed once the service recovers, got %v", err)
	}
	if !seeded.Load() {
		t.Fatal("keys should be seeded after the service recovers")
	}
}

// withGracePeriod shortens the degraded-report grace period for a test and
// restores it afterwards.
func withGracePeriod(t *testing.T, d time.Duration) {
	t.Helper()
	original := ensureKeysGracePeriod
	ensureKeysGracePeriod = d
	t.Cleanup(func() { ensureKeysGracePeriod = original })
}

// failingSince backdates a pipeline's failure spell so a test can reach the
// degraded state without sleeping.
func failingSince(r *GMConnectorReconciler, graph *mcv1alpha3.GMConnector, d time.Duration) {
	r.ensureKeysFailures = map[string]*ensureKeysFailure{
		graph.Namespace + "/" + graph.Name: {since: time.Now().Add(-d)},
	}
}

func TestNoteEnsureKeysFailureStaysQuietWithinGracePeriod(t *testing.T) {
	withGracePeriod(t, time.Hour)
	recorder := record.NewFakeRecorder(10)
	r := &GMConnectorReconciler{Recorder: recorder}
	graph := graphWith("chatqna")

	// A cold start enqueues a reconcile for every watched Deployment and
	// ConfigMap event, so many passes can fail within seconds. None of them may
	// report the pipeline degraded while it is still inside the grace period,
	// or every cold start would raise an alarm.
	for i := 0; i < 50; i++ {
		r.noteEnsureKeysFailure(graph, errors.New("connection refused"))
	}

	if graph.Status.Condition.Type != "" {
		t.Fatalf("expected no condition inside the grace period, got %q", graph.Status.Condition.Type)
	}
	select {
	case ev := <-recorder.Events:
		t.Fatalf("expected no event inside the grace period, got %q", ev)
	default:
	}
}

func TestNoteEnsureKeysFailureReportsDegradedAfterGracePeriod(t *testing.T) {
	withGracePeriod(t, time.Minute)
	recorder := record.NewFakeRecorder(10)
	r := &GMConnectorReconciler{Recorder: recorder}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)

	r.noteEnsureKeysFailure(graph, errors.New("connection refused"))

	if graph.Status.Condition.Type != mcv1alpha3.ConnectorFailed {
		t.Errorf("expected condition %q, got %q", mcv1alpha3.ConnectorFailed, graph.Status.Condition.Type)
	}
	if graph.Status.Condition.Reason != ensureKeysDegradedReason {
		t.Errorf("expected reason %q, got %q", ensureKeysDegradedReason, graph.Status.Condition.Reason)
	}
	// The cause has to reach the message: "it failed" without the reason sends
	// the reader back to the controller log, which is what this replaces.
	if !strings.Contains(graph.Status.Condition.Message, "connection refused") {
		t.Errorf("expected the cause in the message, got %q", graph.Status.Condition.Message)
	}

	select {
	case ev := <-recorder.Events:
		if !strings.Contains(ev, ensureKeysDegradedReason) {
			t.Errorf("expected event to name %q, got %q", ensureKeysDegradedReason, ev)
		}
		if !strings.Contains(ev, "Warning") {
			t.Errorf("expected a Warning event, got %q", ev)
		}
	default:
		t.Fatal("expected an event once the grace period elapsed")
	}
}

func TestNoteEnsureKeysFailureEmitsEventOnlyOncePerSpell(t *testing.T) {
	withGracePeriod(t, time.Minute)
	recorder := record.NewFakeRecorder(10)
	r := &GMConnectorReconciler{Recorder: recorder}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)

	// A long outage requeues every 30s; emitting per pass would flood the
	// namespace's events.
	for i := 0; i < 6; i++ {
		r.noteEnsureKeysFailure(graph, errors.New("connection refused"))
	}

	events := 0
	for {
		select {
		case <-recorder.Events:
			events++
			continue
		default:
		}
		break
	}
	if events != 1 {
		t.Errorf("expected exactly 1 event across repeated failures, got %d", events)
	}
}

func TestEnsureKeysFailuresAreTrackedPerPipeline(t *testing.T) {
	withGracePeriod(t, time.Minute)
	r := &GMConnectorReconciler{}
	first := graphWith("chatqna")
	second := graphWith("docsum")
	// Only the first pipeline has been failing long enough. The second must not
	// inherit its spell, or one unhealthy pipeline would mark a healthy
	// neighbour degraded.
	failingSince(r, first, 2*time.Minute)

	r.noteEnsureKeysFailure(first, errors.New("boom"))
	r.noteEnsureKeysFailure(second, errors.New("boom"))

	if first.Status.Condition.Type != mcv1alpha3.ConnectorFailed {
		t.Errorf("expected the long-failing pipeline to be degraded, got %q", first.Status.Condition.Type)
	}
	if second.Status.Condition.Type != "" {
		t.Errorf("spell leaked to the other pipeline: %q", second.Status.Condition.Type)
	}
}

func TestClearEnsureKeysFailuresClearsTheDegradedCondition(t *testing.T) {
	withGracePeriod(t, time.Minute)
	r := &GMConnectorReconciler{}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)
	r.noteEnsureKeysFailure(graph, errors.New("boom"))
	if graph.Status.Condition.Type != mcv1alpha3.ConnectorFailed {
		t.Fatalf("precondition: expected a degraded condition, got %q", graph.Status.Condition.Type)
	}

	r.clearEnsureKeysFailures(graph)

	// A pipeline that recovered must stop reporting the failure. Leaving the
	// stale condition would keep a healthy pipeline looking broken, with a
	// message claiming a retry that is no longer happening.
	if graph.Status.Condition.Type != mcv1alpha3.ConnectorSuccess {
		t.Errorf("expected the condition to clear to %q, got %q",
			mcv1alpha3.ConnectorSuccess, graph.Status.Condition.Type)
	}
	if graph.Status.Condition.Reason != ensureKeysRecoveredReason {
		t.Errorf("expected reason %q, got %q", ensureKeysRecoveredReason, graph.Status.Condition.Reason)
	}
}

func TestClearEnsureKeysFailuresLeavesForeignConditionsAlone(t *testing.T) {
	r := &GMConnectorReconciler{}
	graph := graphWith("chatqna")
	graph.Status.Condition = mcv1alpha3.GMConnectorCondition{
		Type:    mcv1alpha3.ConnectorFailed,
		Reason:  "SomeOtherFailure",
		Message: "set by another code path",
	}

	r.clearEnsureKeysFailures(graph)

	if graph.Status.Condition.Reason != "SomeOtherFailure" {
		t.Errorf("clobbered a condition this code does not own: %+v", graph.Status.Condition)
	}
}

func TestClearEnsureKeysFailuresResetsTheSpell(t *testing.T) {
	withGracePeriod(t, time.Minute)
	r := &GMConnectorReconciler{}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)
	r.noteEnsureKeysFailure(graph, errors.New("boom"))
	r.clearEnsureKeysFailures(graph)

	// A later failure starts a fresh spell, so a recovered pipeline is not one
	// hiccup away from being reported degraded again.
	graph.Status.Condition = mcv1alpha3.GMConnectorCondition{}
	r.noteEnsureKeysFailure(graph, errors.New("boom"))

	if graph.Status.Condition.Type != "" {
		t.Errorf("expected a fresh grace period after recovery, got condition %q",
			graph.Status.Condition.Type)
	}
}

func TestForgetEnsureKeysFailuresDropsTheEntry(t *testing.T) {
	withGracePeriod(t, time.Minute)
	r := &GMConnectorReconciler{}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)

	// A pipeline deleted mid-failure never reaches a successful pass, so without
	// this the entry would stay for the controller's lifetime.
	r.forgetEnsureKeysFailures(graph.Namespace, graph.Name)

	if len(r.ensureKeysFailures) != 0 {
		t.Errorf("expected the entry to be dropped, got %d", len(r.ensureKeysFailures))
	}
}

func TestNoteEnsureKeysFailureWithoutRecorderStillSetsCondition(t *testing.T) {
	withGracePeriod(t, time.Minute)
	// A nil Recorder is valid (tests build reconcilers without one); the status
	// condition must still be set rather than panicking.
	r := &GMConnectorReconciler{}
	graph := graphWith("chatqna")
	failingSince(r, graph, 2*time.Minute)

	r.noteEnsureKeysFailure(graph, errors.New("boom"))

	if graph.Status.Condition.Reason != ensureKeysDegradedReason {
		t.Errorf("expected reason %q, got %q", ensureKeysDegradedReason, graph.Status.Condition.Reason)
	}
}
