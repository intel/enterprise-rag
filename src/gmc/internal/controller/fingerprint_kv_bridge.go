/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand/v2"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"github.com/go-logr/logr"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"github.com/prometheus/client_golang/prometheus"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/metrics"

	"erag.intel.com/gmc/internal/natsauth"
)

const (
	// fingerprintKVBucket is the JetStream key/value bucket that holds the
	// projection of the fingerprint_config table. It uses memory storage: the
	// contents are rebuilt from Postgres by the reconcile loop, so a NATS
	// restart never loses anything durable.
	fingerprintKVBucket = "fingerprint"

	// fingerprintNotifyChannel is the Postgres channel the fingerprint table's
	// trigger emits on after every INSERT/UPDATE. The payload carries the
	// changed row's (pipeline, tenant, params_key).
	fingerprintNotifyChannel = "fingerprint_config_changed"

	// defaultReconcileInterval is how often the reconcile loop compares
	// Postgres against the KV bucket when KV_RECONCILE_INTERVAL_SECONDS is not
	// set.
	defaultReconcileInterval = 45 * time.Second

	// reconnectBackoff is the pause before re-establishing the LISTEN
	// connection after it drops.
	reconnectBackoff = time.Second

	// maxReconnectBackoff caps the exponential backoff used when the LISTEN
	// connection keeps failing, so repeated failures do not hammer Postgres.
	maxReconnectBackoff = 30 * time.Second

	// maxConsecutiveReconcileErrors is the number of back-to-back reconcile
	// failures after which the bridge reports itself unready.
	maxConsecutiveReconcileErrors = 3
)

// nextReconnectBackoff doubles the current backoff up to maxReconnectBackoff
// and adds up to full jitter, so multiple replicas reconnecting after a shared
// outage spread their attempts instead of retrying in lockstep.
func nextReconnectBackoff(current time.Duration) time.Duration {
	next := current * 2
	if next > maxReconnectBackoff {
		next = maxReconnectBackoff
	}
	if next <= 0 {
		next = reconnectBackoff
	}
	return next
}

// jittered returns a random duration in [d/2, d]. It uses math/rand/v2, whose
// global source is randomly seeded per process, so replicas do not share a
// deterministic jitter sequence.
func jittered(d time.Duration) time.Duration {
	if d <= 0 {
		return 0
	}
	half := d / 2
	return half + time.Duration(rand.Int64N(int64(half)+1))
}

// rowSkips counts fingerprint_config rows the bridge skipped because their
// segments cannot form a usable KV key, so propagation could continue for the
// rest. It does not count transient KV backend errors, which fail the pass.
var rowSkips = prometheus.NewCounter(prometheus.CounterOpts{
	Name: "fingerprint_kv_bridge_row_skips_total",
	Help: "Number of fingerprint_config rows skipped because their key segments are not valid for KV.",
})

func init() {
	metrics.Registry.MustRegister(rowSkips)
}

// fpRow is a single fingerprint_config row as needed for the KV projection.
type fpRow struct {
	Pipeline  string
	Tenant    string
	ParamsKey string
	Values    []byte
	Version   int64
}

// kvKey returns the JetStream key for the row: <pipeline>.<tenant>.<params_key>
// (the Postgres column values are used verbatim as the three segments).
func (r fpRow) kvKey() string {
	return r.Pipeline + "." + r.Tenant + "." + r.ParamsKey
}

// validKey reports whether the row's three segments form an unambiguous
// JetStream key. Dots separate segments, so a segment must not itself contain
// a dot; the token wildcards ('*', '>') and whitespace are rejected because
// they would break key lookups and orphan-cleanup scoping. Empty segments are
// rejected too.
func (r fpRow) validKey() bool {
	return validKeySegment(r.Pipeline) && validKeySegment(r.Tenant) && validKeySegment(r.ParamsKey)
}

// validKeySegment reports whether s is safe to use as one dot-separated segment
// of a JetStream KV key. It validates positively against the character set NATS
// accepts in a KV key ('A'-'Z', 'a'-'z', '0'-'9', '-', '_', '/', '='); the dot
// is excluded because it separates segments, and everything else (whitespace,
// the wildcards '*'/'>', and other punctuation such as ':') is rejected so a
// value that NATS would refuse never reaches kv.Put. Empty segments are
// rejected too.
func validKeySegment(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		switch {
		case r >= 'A' && r <= 'Z':
		case r >= 'a' && r <= 'z':
		case r >= '0' && r <= '9':
		case r == '-' || r == '_' || r == '/' || r == '=':
		default:
			return false
		}
	}
	return true
}

// kvStore is the subset of the JetStream key/value API the projection uses.
// It is an interface so the projection logic can be exercised with an
// in-memory fake in tests.
type kvStore interface {
	Put(ctx context.Context, key string, value []byte) error
	Get(ctx context.Context, key string) (value []byte, found bool, err error)
	Keys(ctx context.Context) ([]string, error)
	Delete(ctx context.Context, key string) error
}

// rowSource reads fingerprint_config rows. It is an interface for the same
// testing reason as kvStore.
type rowSource interface {
	Row(ctx context.Context, pipeline, tenant, paramsKey string) (row fpRow, found bool, err error)
	AllRows(ctx context.Context) ([]fpRow, error)
}

// projector carries the pure projection logic that maps Postgres rows onto KV
// keys. It holds no connections, so it can be tested against fakes.
type projector struct {
	kv  kvStore
	src rowSource
	log logr.Logger
}

// publish writes the current value of one row to KV. It is called for each
// change notification. A row that no longer exists is left for reconcile to
// clean up as an orphan.
func (p *projector) publish(ctx context.Context, pipeline, tenant, paramsKey string) error {
	row, found, err := p.src.Row(ctx, pipeline, tenant, paramsKey)
	if err != nil {
		return err
	}
	if !found {
		return nil
	}
	if !row.validKey() {
		p.skipRow(row, "invalid KV key segments")
		return nil
	}
	if err := p.kv.Put(ctx, row.kvKey(), row.Values); err != nil {
		return err
	}
	p.log.V(1).Info("published fingerprint config to KV", "key", row.kvKey(), "version", row.Version)
	return nil
}

// resync writes every Postgres row to KV. It is used on startup and after a
// LISTEN or NATS reconnection, where individual change notifications may have
// been missed. A row whose key NATS rejects as invalid is skipped so it cannot
// stop the rest of the bucket from being seeded; a backend error (for example a
// connection or permission failure) is remembered and returned once the loop
// has tried every other row, so readiness still reflects an unhealthy KV.
func (p *projector) resync(ctx context.Context) error {
	rows, err := p.src.AllRows(ctx)
	if err != nil {
		return err
	}
	var firstErr error
	for _, row := range rows {
		if !row.validKey() {
			p.skipRow(row, "invalid KV key segments")
			continue
		}
		if err := p.kv.Put(ctx, row.kvKey(), row.Values); err != nil {
			if isInvalidKey(err) {
				p.skipInvalidKey(row.kvKey())
				continue
			}
			p.log.Error(err, "publish to KV failed", "key", row.kvKey())
			if firstErr == nil {
				firstErr = err
			}
		}
	}
	if firstErr != nil {
		return firstErr
	}
	p.log.V(1).Info("resynced fingerprint config to KV", "rows", len(rows))
	return nil
}

// isInvalidKey reports whether err is NATS rejecting a key as malformed, as
// opposed to a backend failure. An invalid key is a property of the row and can
// be skipped; any other error means the KV backend is unhealthy and must not be
// swallowed.
func isInvalidKey(err error) bool {
	return errors.Is(err, jetstream.ErrInvalidKey)
}

// reconcile brings the KV bucket back in line with Postgres: it inserts keys
// that are missing, rewrites keys whose value has drifted, and deletes keys
// that no longer have a matching row. Deletion is limited to keys whose
// pipeline prefix still exists in Postgres, so unrelated data is never
// touched.
//
// A row whose key NATS rejects as invalid is skipped so one un-publishable row
// cannot stall propagation for every other row. Any other per-key failure and
// the pass-wide errors (reading Postgres, listing the bucket) are still
// returned so readiness reflects a broken KV backend; per-key backend errors do
// not abort the pass but the loop continues and returns the first one at the
// end, so the remaining keys still converge.
func (p *projector) reconcile(ctx context.Context) error {
	rows, err := p.src.AllRows(ctx)
	if err != nil {
		return err
	}

	desired := make(map[string][]byte, len(rows))
	pipelines := make(map[string]struct{})
	for _, row := range rows {
		// Track the pipeline regardless of full-key validity so orphan cleanup
		// still runs under a pipeline that is present in Postgres but happens
		// to have rows with unusable tenant/params_key segments.
		if validKeySegment(row.Pipeline) {
			pipelines[row.Pipeline] = struct{}{}
		}
		if !row.validKey() {
			p.skipRow(row, "invalid KV key segments")
			continue
		}
		desired[row.kvKey()] = row.Values
	}

	keys, err := p.kv.Keys(ctx)
	if err != nil {
		return err
	}

	var firstErr error
	record := func(key string, err error, what string) {
		p.log.Error(err, what, "key", key)
		if firstErr == nil {
			firstErr = err
		}
	}

	seen := make(map[string]struct{}, len(keys))
	for _, key := range keys {
		seen[key] = struct{}{}
		want, ok := desired[key]
		if !ok {
			// No matching row. Only remove the key when its pipeline is still
			// present in Postgres; a fully removed pipeline is left alone.
			if _, known := pipelines[pipelineOf(key)]; known {
				if err := p.kv.Delete(ctx, key); err != nil {
					record(key, err, "delete orphaned KV key failed")
					continue
				}
				p.log.V(1).Info("deleted orphaned KV key", "key", key)
			}
			continue
		}
		cur, found, err := p.kv.Get(ctx, key)
		if err != nil {
			record(key, err, "read KV key failed")
			continue
		}
		if !found || !bytes.Equal(canonicalJSON(cur), canonicalJSON(want)) {
			if err := p.kv.Put(ctx, key, want); err != nil {
				record(key, err, "repair stale KV key failed")
				continue
			}
			p.log.V(1).Info("repaired stale KV key", "key", key)
		}
	}

	for key, want := range desired {
		if _, ok := seen[key]; ok {
			continue
		}
		if err := p.kv.Put(ctx, key, want); err != nil {
			// An invalid key is a property of the row, not a backend fault, so
			// skip it rather than failing the pass; every valid key still
			// desired here is inserted regardless.
			if isInvalidKey(err) {
				p.skipInvalidKey(key)
				continue
			}
			record(key, err, "insert missing KV key failed")
			continue
		}
		p.log.V(1).Info("inserted missing KV key", "key", key)
	}

	return firstErr
}

// skipRow records a row left out of the projection because its segments cannot
// form a usable KV key.
func (p *projector) skipRow(row fpRow, reason string) {
	rowSkips.Inc()
	p.log.Info("skipping row: "+reason,
		"pipeline", row.Pipeline, "tenant", row.Tenant, "paramsKey", row.ParamsKey)
}

// skipInvalidKey records a row skipped because NATS rejected its assembled key,
// which the up-front segment check should already prevent. It shares the
// counter and log prefix with skipRow so every skip path stays consistent.
func (p *projector) skipInvalidKey(key string) {
	rowSkips.Inc()
	p.log.Info("skipping row: rejected by KV as an invalid key", "key", key)
}

// pipelineOf returns the pipeline segment of a KV key (everything before the
// first dot).
func pipelineOf(key string) string {
	if i := strings.IndexByte(key, '.'); i >= 0 {
		return key[:i]
	}
	return key
}

// canonicalJSON normalises a JSON document so two encodings of the same value
// compare equal. Numbers are decoded with UseNumber so large integers keep
// their exact value instead of being coerced to float64. It falls back to the
// raw bytes if the input is not a single well-formed JSON value; in particular
// trailing bytes after the value (for example `{"a":1}junk`) make the input
// fall back to raw so a corrupted value does not compare equal and skip a
// repair.
func canonicalJSON(b []byte) []byte {
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	var v interface{}
	if err := dec.Decode(&v); err != nil {
		return b
	}
	// Reject anything after the first value; only whitespace may remain.
	if dec.More() {
		return b
	}
	out, err := json.Marshal(v)
	if err != nil {
		return b
	}
	return out
}

// FingerprintKVBridge propagates fingerprint configuration from Postgres to
// the JetStream key/value bucket. It listens for change notifications for
// low-latency updates and runs a periodic reconcile that repairs any drift, so
// the bucket is eventually consistent with Postgres even if a notification is
// missed or the bucket is lost on a NATS restart. It runs only on the elected
// leader, which keeps it the single writer of the bucket.
type FingerprintKVBridge struct {
	log      logr.Logger
	pgDSN    string
	natsURL  string
	interval time.Duration

	// resyncCh coalesces requests for a full resync raised by the reconnect
	// callbacks.
	resyncCh chan struct{}

	// healthy is false once the reconcile loop has failed
	// maxConsecutiveReconcileErrors times in a row.
	healthy atomic.Bool
}

// NewFingerprintKVBridge builds the bridge from the environment. Postgres and
// NATS connection details come from POSTGRES_* and NATS_URL; the reconcile
// interval comes from KV_RECONCILE_INTERVAL_SECONDS. Defaults to sslmode=prefer,
// which uses TLS if the server offers it but falls back to plaintext, so the
// bridge starts on a default install (the in-repo postgresql chart has no
// server-side TLS). Production deployment supplies real values via secrets and
// ConfigMap.
func NewFingerprintKVBridge() *FingerprintKVBridge {
	host := GetEnvWithDefault("POSTGRES_HOST", "localhost")
	port := GetEnvWithDefault("POSTGRES_PORT", "5432")
	user := GetEnvWithDefault("POSTGRES_USER", "postgres")
	password := GetEnvWithDefault("POSTGRES_PASSWORD", "postgres")
	dbName := GetEnvWithDefault("POSTGRES_DB", "system_fingerprint")
	sslMode := GetEnvWithDefault("POSTGRES_SSLMODE", "prefer")

	// Build the DSN via url.URL so credentials, database name and IPv6 hosts
	// are escaped correctly rather than by hand.
	dsnURL := url.URL{
		Scheme:   "postgres",
		User:     url.UserPassword(user, password),
		Host:     net.JoinHostPort(host, port),
		Path:     "/" + dbName,
		RawQuery: url.Values{"sslmode": {sslMode}}.Encode(),
	}
	dsn := dsnURL.String()

	interval := defaultReconcileInterval
	if raw := GetEnvWithDefault("KV_RECONCILE_INTERVAL_SECONDS", ""); raw != "" {
		if secs, err := time.ParseDuration(raw + "s"); err == nil && secs > 0 {
			interval = secs
		}
	}

	b := &FingerprintKVBridge{
		log:      ctrl.Log.WithName("fingerprint-kv-bridge"),
		pgDSN:    dsn,
		natsURL:  GetEnvWithDefault("NATS_URL", ""),
		interval: interval,
		resyncCh: make(chan struct{}, 1),
	}
	b.healthy.Store(true)
	return b
}

// NeedLeaderElection reports that the bridge must run only on the elected
// leader so the bucket has a single writer.
func (b *FingerprintKVBridge) NeedLeaderElection() bool {
	return true
}

// ReadyCheck fails the readiness probe while the elected leader cannot reach
// its backends or after the reconcile loop has failed too many times in a row.
// Non-leader replicas never run the bridge and stay ready.
func (b *FingerprintKVBridge) ReadyCheck(_ *http.Request) error {
	if !b.healthy.Load() {
		return fmt.Errorf("fingerprint KV bridge is not healthy")
	}
	return nil
}

// Start runs the bridge until the context is cancelled. It is a
// controller-runtime Runnable and is invoked once the manager wins leader
// election. On exit (including stepping down as leader) the bridge reports
// ready again so the shared readiness probe is not left failing.
func (b *FingerprintKVBridge) Start(ctx context.Context) error {
	defer b.healthy.Store(true)

	if b.natsURL == "" {
		b.log.Info("fingerprint KV bridge disabled: NATS_URL is not set")
		<-ctx.Done()
		return nil
	}

	pool, nc, kv := b.connect(ctx)
	if pool == nil {
		// Context was cancelled while connecting.
		return nil
	}
	defer pool.Close()
	defer nc.Close()

	proj := &projector{kv: &jetstreamKVStore{kv: kv}, src: &pgxRowSource{pool: pool}, log: b.log}

	// Seed the bucket from Postgres before serving updates. Readiness stays
	// false until this succeeds so the bridge never reports ready over an
	// unseeded bucket; if the initial resync fails, the immediate reconcile in
	// runReconcile is the backstop that flips readiness once KV is populated.
	if err := proj.resync(ctx); err != nil {
		b.log.Error(err, "initial resync failed; reconcile loop will retry")
	} else {
		b.healthy.Store(true)
	}

	go b.runListen(ctx, proj)
	go b.runResyncOnReconnect(ctx, proj)
	b.runReconcile(ctx, proj)
	return nil
}

// connect opens the Postgres pool and NATS connection and ensures the KV
// bucket exists, retrying until it succeeds or the context is cancelled. The
// bridge stays unready throughout: readiness is only granted once KV has been
// seeded from Postgres (by the initial resync or the first reconcile), not on
// connection alone. It returns nil values if the context is cancelled first.
func (b *FingerprintKVBridge) connect(ctx context.Context) (*pgxpool.Pool, *nats.Conn, jetstream.KeyValue) {
	b.healthy.Store(false)
	for {
		if ctx.Err() != nil {
			return nil, nil, nil
		}
		pool, nc, kv, err := b.dial(ctx)
		if err == nil {
			b.log.Info("fingerprint KV bridge connected", "bucket", fingerprintKVBucket)
			return pool, nc, kv
		}
		b.log.Error(err, "fingerprint KV bridge connect failed; retrying")
		select {
		case <-ctx.Done():
			return nil, nil, nil
		case <-time.After(reconnectBackoff):
		}
	}
}

// dial performs a single connection attempt: Postgres pool, NATS connection
// with a reconnect callback that requests a resync, and the KV bucket.
func (b *FingerprintKVBridge) dial(ctx context.Context) (*pgxpool.Pool, *nats.Conn, jetstream.KeyValue, error) {
	pool, err := pgxpool.New(ctx, b.pgDSN)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("postgres pool: %w", err)
	}
	// pgxpool.New establishes connections lazily, so verify connectivity here.
	// Otherwise the retry loop would treat an unreachable database as connected.
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, nil, nil, fmt.Errorf("postgres ping: %w", err)
	}

	authOpts, err := natsauth.Options()
	if err != nil {
		pool.Close()
		return nil, nil, nil, fmt.Errorf("nats auth options: %w", err)
	}
	opts := append([]nats.Option{
		nats.MaxReconnects(-1),
		nats.ReconnectWait(reconnectBackoff),
		nats.ReconnectHandler(func(_ *nats.Conn) {
			b.log.Info("NATS reconnected; requesting resync")
			b.requestResync()
		}),
	}, authOpts...)
	nc, err := nats.Connect(b.natsURL, opts...)
	if err != nil {
		pool.Close()
		return nil, nil, nil, fmt.Errorf("nats connect: %w", err)
	}

	kv, err := b.ensureBucket(ctx, nc)
	if err != nil {
		nc.Close()
		pool.Close()
		return nil, nil, nil, err
	}
	return pool, nc, kv, nil
}

// ensureBucket returns a handle to the memory-backed KV bucket, creating it
// only if it does not already exist. An existing bucket is opened as-is so its
// configuration is never mutated on startup.
func (b *FingerprintKVBridge) ensureBucket(ctx context.Context, nc *nats.Conn) (jetstream.KeyValue, error) {
	js, err := jetstream.New(nc)
	if err != nil {
		return nil, fmt.Errorf("jetstream: %w", err)
	}
	kv, err := js.KeyValue(ctx, fingerprintKVBucket)
	if err == nil {
		return kv, nil
	}
	if !errors.Is(err, jetstream.ErrBucketNotFound) {
		return nil, fmt.Errorf("open KV bucket: %w", err)
	}
	kv, err = js.CreateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket:   fingerprintKVBucket,
		Storage:  jetstream.MemoryStorage,
		History:  1,
		Replicas: 1,
	})
	if err != nil {
		return nil, fmt.Errorf("create KV bucket: %w", err)
	}
	return kv, nil
}

// runListen keeps a dedicated Postgres LISTEN connection open and publishes
// each change notification to KV. On any connection error it backs off with
// jittered exponential delay, reconnects and requests a full resync so no
// change is lost. The backoff resets after a connection stays up long enough
// to succeed.
func (b *FingerprintKVBridge) runListen(ctx context.Context, proj *projector) {
	backoff := reconnectBackoff
	for {
		if ctx.Err() != nil {
			return
		}
		if err := b.listenOnce(ctx, proj); err != nil && ctx.Err() == nil {
			b.log.Error(err, "LISTEN connection dropped; reconnecting", "backoff", backoff)
			b.requestResync()
			select {
			case <-ctx.Done():
				return
			case <-time.After(jittered(backoff)):
			}
			backoff = nextReconnectBackoff(backoff)
		} else {
			backoff = reconnectBackoff
		}
	}
}

// listenOnce opens one LISTEN connection and processes notifications until it
// fails or the context is cancelled.
func (b *FingerprintKVBridge) listenOnce(ctx context.Context, proj *projector) error {
	conn, err := pgx.Connect(ctx, b.pgDSN)
	if err != nil {
		return fmt.Errorf("listen connect: %w", err)
	}
	defer conn.Close(context.Background())

	if _, err := conn.Exec(ctx, "LISTEN "+fingerprintNotifyChannel); err != nil {
		return fmt.Errorf("listen: %w", err)
	}
	b.log.Info("listening for fingerprint config changes", "channel", fingerprintNotifyChannel)

	for {
		notification, err := conn.WaitForNotification(ctx)
		if err != nil {
			return err
		}
		pipeline, tenant, paramsKey, err := parseNotifyPayload(notification.Payload)
		if err != nil {
			b.log.Error(err, "ignoring malformed notification", "payload", notification.Payload)
			continue
		}
		if err := proj.publish(ctx, pipeline, tenant, paramsKey); err != nil {
			b.log.Error(err, "failed to publish change to KV", "pipeline", pipeline, "tenant", tenant, "paramsKey", paramsKey)
		}
	}
}

// runReconcile reconciles once immediately, then on a fixed interval, and
// tracks health: consecutive failures mark the bridge unready, and a success
// clears the counter. Reconciling up front avoids leaving KV unseeded or
// unrepaired for a full interval on startup or right after a failed initial
// resync.
func (b *FingerprintKVBridge) runReconcile(ctx context.Context, proj *projector) {
	ticker := time.NewTicker(b.interval)
	defer ticker.Stop()

	consecutiveErrors := 0
	b.reconcileOnce(ctx, proj, &consecutiveErrors)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			b.reconcileOnce(ctx, proj, &consecutiveErrors)
		}
	}
}

// reconcileOnce runs a single reconcile pass and updates the consecutive-error
// counter and readiness accordingly.
func (b *FingerprintKVBridge) reconcileOnce(ctx context.Context, proj *projector, consecutiveErrors *int) {
	if err := proj.reconcile(ctx); err != nil {
		*consecutiveErrors++
		b.log.Error(err, "reconcile failed", "consecutiveErrors", *consecutiveErrors)
		if *consecutiveErrors >= maxConsecutiveReconcileErrors {
			b.healthy.Store(false)
		}
		return
	}
	*consecutiveErrors = 0
	b.healthy.Store(true)
}

// runResyncOnReconnect performs a full resync whenever a reconnect callback
// asks for one. If a resync fails (for example because a backend is still
// recovering) it retries with a backoff, so the "reconnect triggers a full
// resync" guarantee holds even when the first attempt happens too early.
func (b *FingerprintKVBridge) runResyncOnReconnect(ctx context.Context, proj *projector) {
	for {
		select {
		case <-ctx.Done():
			return
		case <-b.resyncCh:
			for {
				if err := proj.resync(ctx); err == nil {
					break
				} else {
					b.log.Error(err, "resync after reconnect failed; retrying")
				}
				select {
				case <-ctx.Done():
					return
				case <-time.After(reconnectBackoff):
				}
			}
		}
	}
}

// requestResync signals the resync goroutine without blocking if a request is
// already pending.
func (b *FingerprintKVBridge) requestResync() {
	select {
	case b.resyncCh <- struct{}{}:
	default:
	}
}

// parseNotifyPayload extracts the composite key from a change notification
// payload.
func parseNotifyPayload(payload string) (pipeline, tenant, paramsKey string, err error) {
	var p struct {
		Pipeline  string `json:"pipeline"`
		Tenant    string `json:"tenant"`
		ParamsKey string `json:"params_key"`
	}
	if err := json.Unmarshal([]byte(payload), &p); err != nil {
		return "", "", "", err
	}
	if p.Pipeline == "" || p.Tenant == "" || p.ParamsKey == "" {
		return "", "", "", fmt.Errorf("incomplete notification payload")
	}
	return p.Pipeline, p.Tenant, p.ParamsKey, nil
}

// jetstreamKVStore adapts a JetStream key/value handle to the kvStore
// interface.
type jetstreamKVStore struct {
	kv jetstream.KeyValue
}

func (s *jetstreamKVStore) Put(ctx context.Context, key string, value []byte) error {
	_, err := s.kv.Put(ctx, key, value)
	return err
}

func (s *jetstreamKVStore) Get(ctx context.Context, key string) ([]byte, bool, error) {
	entry, err := s.kv.Get(ctx, key)
	if err != nil {
		if errors.Is(err, jetstream.ErrKeyNotFound) {
			return nil, false, nil
		}
		return nil, false, err
	}
	return entry.Value(), true, nil
}

func (s *jetstreamKVStore) Keys(ctx context.Context) ([]string, error) {
	keys, err := s.kv.Keys(ctx)
	if err != nil {
		if errors.Is(err, jetstream.ErrNoKeysFound) {
			return nil, nil
		}
		return nil, err
	}
	return keys, nil
}

func (s *jetstreamKVStore) Delete(ctx context.Context, key string) error {
	return s.kv.Delete(ctx, key)
}

// pgxRowSource reads fingerprint_config rows through a pgx pool.
type pgxRowSource struct {
	pool *pgxpool.Pool
}

func (s *pgxRowSource) Row(ctx context.Context, pipeline, tenant, paramsKey string) (fpRow, bool, error) {
	const query = `SELECT pipeline, tenant, params_key, values::text, version
		FROM fingerprint_config WHERE pipeline = $1 AND tenant = $2 AND params_key = $3`
	var (
		row    fpRow
		values string
	)
	err := s.pool.QueryRow(ctx, query, pipeline, tenant, paramsKey).
		Scan(&row.Pipeline, &row.Tenant, &row.ParamsKey, &values, &row.Version)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return fpRow{}, false, nil
		}
		return fpRow{}, false, err
	}
	row.Values = []byte(values)
	return row, true, nil
}

func (s *pgxRowSource) AllRows(ctx context.Context) ([]fpRow, error) {
	const query = `SELECT pipeline, tenant, params_key, values::text, version FROM fingerprint_config`
	rows, err := s.pool.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []fpRow
	for rows.Next() {
		var (
			row    fpRow
			values string
		)
		if err := rows.Scan(&row.Pipeline, &row.Tenant, &row.ParamsKey, &values, &row.Version); err != nil {
			return nil, err
		}
		row.Values = []byte(values)
		result = append(result, row)
	}
	return result, rows.Err()
}
