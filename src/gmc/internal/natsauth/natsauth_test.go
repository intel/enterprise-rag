/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package natsauth

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/nats-io/nkeys"
)

// clearEnv unsets every variable the package reads so one test's environment
// does not leak into the next.
func clearEnv(t *testing.T) {
	t.Helper()
	for _, k := range []string{EnvTLSCAFile, EnvTLSCertFile, EnvTLSKeyFile, EnvNKeySeedFile} {
		t.Setenv(k, "")
	}
}

// writeSeedFile writes a freshly generated user NKey seed to a temp file and
// returns its path, so NkeyOptionFromSeed accepts it.
func writeSeedFile(t *testing.T) string {
	t.Helper()
	kp, err := nkeys.CreateUser()
	if err != nil {
		t.Fatalf("create user nkey: %v", err)
	}
	seed, err := kp.Seed()
	if err != nil {
		t.Fatalf("read seed: %v", err)
	}
	seedFile := filepath.Join(t.TempDir(), "user.nk")
	if err := os.WriteFile(seedFile, seed, 0o600); err != nil {
		t.Fatalf("write seed file: %v", err)
	}
	return seedFile
}

func TestOptionsErrorsWhenNKeySeedUnset(t *testing.T) {
	clearEnv(t)

	if _, err := Options(); err == nil {
		t.Fatal("expected an error when the NKey seed is not set")
	}
}

func TestOptionsNKeyOnlyConnectsWithoutTLS(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))

	// With only the NKey seed set the client authenticates but adds no TLS
	// option, so it connects in plaintext (or over the ambient mesh).
	opts, err := Options()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(opts) != 1 {
		t.Fatalf("expected 1 option, got %d", len(opts))
	}
}

func TestOptionsRootCAAddsOption(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvTLSCAFile, "/etc/nats/ca.pem")
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))

	// Root CA plus the always-present NKey.
	opts, err := Options()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(opts) != 2 {
		t.Fatalf("expected 2 options, got %d", len(opts))
	}
}

func TestOptionsClientCertAndNKey(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvTLSCAFile, "/etc/nats/ca.pem")
	t.Setenv(EnvTLSCertFile, "/etc/nats/client.pem")
	t.Setenv(EnvTLSKeyFile, "/etc/nats/client-key.pem")
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))

	// Root CA, client certificate and the NKey.
	opts, err := Options()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(opts) != 3 {
		t.Fatalf("expected 3 options, got %d", len(opts))
	}
}

func TestOptionsClientCertRequiresBothFiles(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))
	t.Setenv(EnvTLSCertFile, "/etc/nats/client.pem")

	if _, err := Options(); err == nil {
		t.Fatal("expected an error when only the certificate is set")
	}

	clearEnv(t)
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))
	t.Setenv(EnvTLSKeyFile, "/etc/nats/client-key.pem")

	if _, err := Options(); err == nil {
		t.Fatal("expected an error when only the key is set")
	}
}

func TestOptionsNKeySeedIsLoaded(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvNKeySeedFile, writeSeedFile(t))

	opts, err := Options()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(opts) != 1 {
		t.Fatalf("expected 1 option, got %d", len(opts))
	}
}

func TestOptionsInvalidNKeySeedErrors(t *testing.T) {
	clearEnv(t)
	t.Setenv(EnvNKeySeedFile, "/no/such/seed.nk")

	if _, err := Options(); err == nil {
		t.Fatal("expected an error for an unreadable seed file")
	}
}
