/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	mcv1alpha3 "erag.intel.com/gmc/api/v1alpha3"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	// ensureKeysPath is the fingerprint microservice route that seeds a default
	// row for each requested parameter group. It is idempotent: keys that
	// already exist are left untouched.
	ensureKeysPath = "/v1/system_fingerprint/ensure_keys"

	// ensureKeysTenant is the tenant the controller seeds under. A single
	// tenant is used today; the dimension is kept so per-user tenants can be
	// added without re-keying the store.
	ensureKeysTenant = "_global"

	// ensureKeysTimeout bounds a single ensure-keys request.
	ensureKeysTimeout = 5 * time.Second
)

var (
	// ensureKeysAttempts is the number of times an ensure-keys request is tried
	// before the controller gives up for this reconcile pass.
	ensureKeysAttempts = 3

	// ensureKeysRetryBackoff is the pause between ensure-keys attempts. It is a
	// variable so tests can shorten it.
	ensureKeysRetryBackoff = time.Second

	// ensureKeysRequeueAfter is how long the reconcile waits before retrying
	// ensure-keys after the in-call attempts are exhausted. The reconcile
	// requeues itself by this interval until the fingerprint service becomes
	// ready and the keys are seeded, so a startup race no longer leaves the
	// keys unregistered forever. It is a variable so tests can shorten it.
	ensureKeysRequeueAfter = 30 * time.Second

	// ensureKeysGracePeriod is how long seeding may keep failing before the
	// pipeline is reported as degraded. The retry stays unbounded; this only
	// decides when it stops being treated as a slow startup. It is measured in
	// elapsed time rather than failed passes because a pass is triggered by any
	// watched Deployment or ConfigMap event, so during a cold start dozens of
	// passes can fail within seconds -- a pass count would report a pipeline
	// degraded while the chart's own wait-for-fingerprint gate is still waiting.
	// It is a variable so tests can shorten it.
	ensureKeysGracePeriod = 5 * time.Minute
)

// ensureKeysDegradedReason is the status reason and Event reason set when
// ensure-keys has been failing for longer than ensureKeysGracePeriod.
const ensureKeysDegradedReason = "FingerprintKeysUnavailable"

// ensureKeysRecoveredReason replaces the degraded condition once seeding works.
const ensureKeysRecoveredReason = "FingerprintKeysSeeded"

// paramKeyEntry is a single {params_key, params_kind} item in an ensure-keys
// request body.
type paramKeyEntry struct {
	ParamsKey  string `json:"params_key"`
	ParamsKind string `json:"params_kind"`
}

// ensureKeysRequest is the ensure-keys request body: the target store
// coordinates plus the parameter groups to seed.
type ensureKeysRequest struct {
	Pipeline string          `json:"pipeline"`
	Tenant   string          `json:"tenant"`
	Keys     []paramKeyEntry `json:"keys"`
}

// collectParamKeys walks the pipeline graph and returns the parameter groups it
// declares, deduplicated by params_key. Only steps whose internal-service
// config sets "paramsKind" take part: those steps opt into fingerprint
// parameter injection, and their kind has already been validated at admission
// time. The key is resolved with the same rule the webhook validates against
// (explicit "paramsKey", else the lowercased step name).
func collectParamKeys(graph *mcv1alpha3.GMConnector) []paramKeyEntry {
	seen := make(map[string]struct{})
	var keys []paramKeyEntry
	for _, node := range graph.Spec.Nodes {
		for _, step := range node.Steps {
			kind := step.InternalService.Config[mcv1alpha3.ConfigParamsKind]
			if kind == "" {
				continue
			}
			key := mcv1alpha3.ResolveParamsKey(step)
			// An empty key (only possible with an empty step name, which the
			// webhook rejects) would be refused by the fingerprint service, so
			// skip it rather than send an unusable request.
			if key == "" {
				continue
			}
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			keys = append(keys, paramKeyEntry{ParamsKey: key, ParamsKind: kind})
		}
	}
	return keys
}

// ensureParamKeys registers the pipeline's declared parameter groups with the
// fingerprint service so their default rows exist before the router starts
// reading them. The HTTP call is synchronous but bounded by ensureKeysTimeout
// and ensureKeysAttempts, so a slow or unreachable service can only delay a
// reconcile briefly. It returns an error when the keys could not be seeded so
// the caller can requeue and retry; a graph that declares no parameter groups
// is a no-op and returns nil.
func (r *GMConnectorReconciler) ensureParamKeys(ctx context.Context, graph *mcv1alpha3.GMConnector) error {
	keys := collectParamKeys(graph)
	if len(keys) == 0 {
		return nil
	}

	req := ensureKeysRequest{
		Pipeline: graph.Name,
		Tenant:   ensureKeysTenant,
		Keys:     keys,
	}
	baseURL := os.Getenv(mcv1alpha3.FingerprintServiceURLEnv)
	if baseURL == "" {
		baseURL = mcv1alpha3.DefaultFingerprintServiceURL
		// Log the fallback so a deployment that forgot to wire the env var does
		// not silently register keys against an unintended endpoint. It is at
		// debug level because clusters that intentionally omit the var would
		// otherwise log this on every reconcile.
		_log.V(1).Info("FINGERPRINT_SERVICE_URL is not set; using default",
			"url", baseURL, "pipeline", graph.Name, "namespace", graph.Namespace)
	}

	if err := postEnsureKeys(ctx, http.DefaultClient, baseURL, req); err != nil {
		return fmt.Errorf("ensure-keys for pipeline %q: %w", graph.Name, err)
	}
	return nil
}

// postEnsureKeys sends the ensure-keys request, retrying a bounded number of
// times on any failure (a transport error or a non-2xx response). Since the
// endpoint is idempotent, a retry is always safe even when the previous
// attempt actually reached the service. It returns an error only after every
// attempt has failed; callers treat that as non-fatal.
func postEnsureKeys(ctx context.Context, client *http.Client, baseURL string, req ensureKeysRequest) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal ensure-keys request: %w", err)
	}
	endpoint := strings.TrimRight(baseURL, "/") + ensureKeysPath

	var lastErr error
	for attempt := 1; attempt <= ensureKeysAttempts; attempt++ {
		if err := doEnsureKeys(ctx, client, endpoint, body); err != nil {
			lastErr = err
			if attempt < ensureKeysAttempts {
				select {
				case <-ctx.Done():
					return ctx.Err()
				case <-time.After(ensureKeysRetryBackoff):
				}
			}
			continue
		}
		return nil
	}
	return lastErr
}

// doEnsureKeys performs a single ensure-keys HTTP call. It returns an error on
// a transport failure or any non-2xx status; postEnsureKeys decides whether to
// retry.
func doEnsureKeys(ctx context.Context, client *http.Client, endpoint string, body []byte) error {
	reqCtx, cancel := context.WithTimeout(ctx, ensureKeysTimeout)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(reqCtx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build ensure-keys request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(httpReq)
	if err != nil {
		return fmt.Errorf("post ensure-keys: %w", err)
	}
	defer resp.Body.Close()
	// Drain the body so the connection can be reused.
	_, _ = io.Copy(io.Discard, resp.Body)

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("ensure-keys returned status %d", resp.StatusCode)
	}
	return nil
}

// ensureKeysFailure is when seeding first started failing for a pipeline, and
// whether the degraded condition has already been reported for that spell.
type ensureKeysFailure struct {
	since    time.Time
	reported bool
}

// noteEnsureKeysFailure records a failed ensure-keys pass and reports the
// pipeline as degraded once it has been failing for ensureKeysGracePeriod. The
// reconcile keeps requeueing either way.
func (r *GMConnectorReconciler) noteEnsureKeysFailure(graph *mcv1alpha3.GMConnector, cause error) {
	r.ensureKeysMu.Lock()
	defer r.ensureKeysMu.Unlock()

	if r.ensureKeysFailures == nil {
		r.ensureKeysFailures = make(map[string]*ensureKeysFailure)
	}
	key := graph.Namespace + "/" + graph.Name
	failure, ok := r.ensureKeysFailures[key]
	if !ok {
		failure = &ensureKeysFailure{since: time.Now()}
		r.ensureKeysFailures[key] = failure
	}

	failing := time.Since(failure.since)
	if failing < ensureKeysGracePeriod {
		return
	}

	msg := fmt.Sprintf(
		"Seeding fingerprint parameter keys has been failing for %s (%v). "+
			"The pipeline cannot serve component parameters until the fingerprint "+
			"service responds; retrying every %s.",
		failing.Round(time.Second), cause, ensureKeysRequeueAfter)

	// Emit once per spell rather than on every later pass, so a long outage does
	// not flood the namespace's events.
	if !failure.reported && r.Recorder != nil {
		r.Recorder.Event(graph, corev1.EventTypeWarning, ensureKeysDegradedReason, msg)
	}
	failure.reported = true

	graph.Status.Condition = mcv1alpha3.GMConnectorCondition{
		Type:           mcv1alpha3.ConnectorFailed,
		Reason:         ensureKeysDegradedReason,
		Message:        msg,
		LastUpdateTime: metav1.Now(),
	}
}

// clearEnsureKeysFailures forgets a pipeline's failure spell after a successful
// ensure-keys pass and clears the degraded condition it set, so a pipeline that
// recovered does not keep reporting a stale failure. A condition set by anything
// else is left alone.
func (r *GMConnectorReconciler) clearEnsureKeysFailures(graph *mcv1alpha3.GMConnector) {
	r.ensureKeysMu.Lock()
	defer r.ensureKeysMu.Unlock()

	delete(r.ensureKeysFailures, graph.Namespace+"/"+graph.Name)

	if graph.Status.Condition.Reason == ensureKeysDegradedReason {
		graph.Status.Condition = mcv1alpha3.GMConnectorCondition{
			Type:           mcv1alpha3.ConnectorSuccess,
			Reason:         ensureKeysRecoveredReason,
			Message:        "Fingerprint parameter keys are seeded.",
			LastUpdateTime: metav1.Now(),
		}
	}
}

// forgetEnsureKeysFailures drops a deleted pipeline's entry so the map does not
// grow for names that no longer exist.
func (r *GMConnectorReconciler) forgetEnsureKeysFailures(namespace, name string) {
	r.ensureKeysMu.Lock()
	defer r.ensureKeysMu.Unlock()
	delete(r.ensureKeysFailures, namespace+"/"+name)
}
