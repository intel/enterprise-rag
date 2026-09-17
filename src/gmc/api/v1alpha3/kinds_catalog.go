/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package v1alpha3

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"slices"
	"strings"
	"sync"
	"time"
)

const (
	// FingerprintServiceURLEnv names the environment variable that carries the
	// base URL of the fingerprint microservice. The webhook and the controller
	// both read it, so they agree on the endpoint; it is exported so the
	// controller shares this one definition rather than repeating the literal.
	FingerprintServiceURLEnv = "FINGERPRINT_SERVICE_URL"

	// DefaultFingerprintServiceURL is used when FingerprintServiceURLEnv is not
	// set, so admission still works in environments where the variable was not
	// wired up. It is exported so the controller shares this one default rather
	// than keeping its own copy that could silently diverge.
	DefaultFingerprintServiceURL = "http://fingerprint-svc.fingerprint.svc:6012"

	// kindsPath is the fingerprint route that returns the parameter-kind
	// catalog the write path accepts.
	kindsPath = "/v1/system_fingerprint/kinds"

	// kindsResponseLimit caps how many bytes are read from a kinds response, so
	// a misbehaving or compromised fingerprint cannot exhaust admission memory
	// with an oversized body. The catalog is a short list of kind names, so this
	// is far above any legitimate response.
	kindsResponseLimit = 1 << 20
)

var (
	// kindsCatalogTTL bounds how long a fetched catalog is reused before it is
	// refreshed. It is a variable so tests can shorten it.
	kindsCatalogTTL = 5 * time.Minute

	// kindsBootstrapRetry is how often a fetch is retried while no catalog has
	// ever been fetched. It is shorter than the TTL so the fail-open window
	// after startup closes quickly once the fingerprint is reachable, without a
	// failed fetch hammering the service. It is a variable so tests can shorten
	// it.
	kindsBootstrapRetry = 15 * time.Second

	// kindsFetchTimeout bounds a single catalog fetch, so a slow fingerprint
	// cannot stall admission for long.
	kindsFetchTimeout = 3 * time.Second

	// kindCatalog is the catalog the webhook validates paramsKind against.
	kindCatalog = newParamsKindCatalog()
)

// kindsResponse is the body the fingerprint returns from its kinds route
// (kindsPath, /v1/system_fingerprint/kinds).
type kindsResponse struct {
	Kinds []string `json:"kinds"`
}

// paramsKindCatalog holds the parameter-kind catalog served by the fingerprint
// microservice and refreshes it on a TTL. Validating against it, rather than a
// list compiled into the webhook, means a kind added to the fingerprint is
// accepted at admission with no change here.
type paramsKindCatalog struct {
	client *http.Client

	mu          sync.RWMutex
	kinds       []string
	haveKinds   bool
	lastAttempt time.Time
}

// newParamsKindCatalog returns a catalog that fetches from the fingerprint over
// HTTP. The base URL is resolved from the environment on each fetch. Its client
// caps connections to the fingerprint rather than using http.DefaultClient,
// which is unbounded, so a burst of admissions after the TTL expires cannot open
// an unbounded number of connections to the fingerprint. A single caller claims
// each refresh (see refreshIfDue), so in steady state only one fetch is in
// flight, but the cap bounds the worst case.
func newParamsKindCatalog() *paramsKindCatalog {
	// Clone the default transport and override only the connection caps, so the
	// proxy (HTTP(S)_PROXY / NO_PROXY) and TLS defaults are preserved.
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxConnsPerHost = 2
	transport.MaxIdleConnsPerHost = 1
	return &paramsKindCatalog{client: &http.Client{Transport: transport}}
}

// allows reports whether kind is an accepted parameter kind and returns the
// catalog it was checked against, for use in an error message. It refreshes the
// catalog from the fingerprint when the cached copy is older than the refresh
// interval, at most once per interval so a repeated failure cannot hammer the
// service. On a failed refresh the last known-good catalog is kept, so a
// transient fingerprint outage does not disturb admission.
//
// While no catalog has ever been fetched the interval is the shorter
// kindsBootstrapRetry rather than the full TTL, so the accept-all window after
// startup closes soon after the fingerprint becomes reachable.
//
// When no catalog has ever been fetched (every fetch attempt so far has failed
// — the fingerprint is unreachable, or returns a non-2xx status, a body that
// does not decode, or an empty catalog), it accepts the kind and returns a nil
// catalog. The webhook failurePolicy is Fail, so rejecting here would block
// every GMConnector write while the fingerprint is unavailable; accepting keeps
// admission working, and the controller's ensure-keys call still validates the
// kind against the store once the fingerprint is back. The catalog is only read
// to build the rejection message, which is reached only when a fetched catalog
// is in hand.
//
// The network fetch runs without any lock held: a caller that finds the copy
// due for refresh claims the refresh (by stamping lastAttempt), fetches, then
// re-acquires the lock only to store the result. Steady-state admissions decide
// under the read lock and proceed concurrently, so a slow fingerprint cannot
// serialize them behind the fetch, and stamping lastAttempt when claiming keeps
// a burst of writes from each firing its own fetch.
func (c *paramsKindCatalog) allows(kind string) (allowed bool, catalog []string) {
	if c.refreshIfDue() {
		fetched, err := c.fetch()

		c.mu.Lock()
		if err != nil {
			if c.haveKinds {
				vlog.Error(err, "could not refresh paramsKind catalog from fingerprint; keeping last known-good")
			} else {
				vlog.Error(err, "could not fetch paramsKind catalog from fingerprint; admitting kinds until one is available")
			}
		} else {
			c.kinds = fetched
			c.haveKinds = true
		}
		c.mu.Unlock()
	}

	c.mu.RLock()
	defer c.mu.RUnlock()
	if !c.haveKinds {
		return true, nil
	}
	return slices.Contains(c.kinds, kind), c.kinds
}

// refreshIfDue reports whether the caller should fetch a fresh catalog, and if
// so claims the refresh so only one concurrent caller fetches. A refresh is due
// once the cached copy is older than the refresh interval, which is the shorter
// kindsBootstrapRetry while no catalog has ever been fetched and the full TTL
// once one is in hand.
//
// The common case, where the cached copy is still fresh, is decided under the
// read lock so steady-state admissions proceed concurrently. Only when a
// refresh looks due does it take the write lock and re-check, so at most one
// caller claims the refresh; claiming stamps lastAttempt, so a caller that
// arrives while a fetch is in flight sees the copy as fresh and serves the
// cached one rather than launching its own fetch.
func (c *paramsKindCatalog) refreshIfDue() bool {
	c.mu.RLock()
	due := c.due()
	c.mu.RUnlock()
	if !due {
		return false
	}

	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.due() {
		return false
	}
	c.lastAttempt = time.Now()
	return true
}

// due reports whether the cached catalog is older than its refresh interval.
// The caller must hold the lock, as it reads haveKinds and lastAttempt.
func (c *paramsKindCatalog) due() bool {
	interval := kindsCatalogTTL
	if !c.haveKinds {
		interval = kindsBootstrapRetry
	}
	return time.Since(c.lastAttempt) >= interval
}

// fetch reads the catalog from the fingerprint. It returns an error on a
// transport failure, a non-2xx status, or an empty catalog; an empty list is
// refused rather than adopted so a degenerate response cannot replace a good
// catalog with one that rejects every kind.
func (c *paramsKindCatalog) fetch() ([]string, error) {
	baseURL := os.Getenv(FingerprintServiceURLEnv)
	if baseURL == "" {
		baseURL = DefaultFingerprintServiceURL
	}
	endpoint := strings.TrimRight(baseURL, "/") + kindsPath

	ctx, cancel := context.WithTimeout(context.Background(), kindsFetchTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("build kinds request: %w", err)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("get kinds: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// Drain a bounded prefix rather than the whole error body: a large body
		// should not force the webhook to spend time draining it. Reading only a
		// prefix may leave the connection unread to EOF, so net/http may not
		// reuse it, which is an acceptable trade for the bound.
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, kindsResponseLimit))
		return nil, fmt.Errorf("kinds returned status %d", resp.StatusCode)
	}

	var body kindsResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, kindsResponseLimit)).Decode(&body); err != nil {
		return nil, fmt.Errorf("decode kinds response: %w", err)
	}
	if len(body.Kinds) == 0 {
		return nil, fmt.Errorf("kinds response carried no kinds")
	}
	return body.Kinds, nil
}
