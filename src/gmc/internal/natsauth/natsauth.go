/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

// Package natsauth builds the authentication and transport-security options a
// NATS client uses to reach the server. The NKey seed is mounted from a Secret
// and its path supplied through the environment; it is always required, because
// the NKey keeps the leader-elected controller the sole KV writer. TLS material
// is optional: the client presents a certificate and verifies the server only
// when its paths are set, so it connects in plaintext (or over an ambient mesh
// that terminates mTLS transparently) when they are not.
package natsauth

import (
	"fmt"
	"os"

	"github.com/nats-io/nats.go"
)

const (
	// EnvTLSCAFile points at the PEM bundle used to verify the server
	// certificate. When set, the client verifies the server's TLS identity.
	EnvTLSCAFile = "NATS_TLS_CA_FILE"

	// EnvTLSCertFile and EnvTLSKeyFile point at the client certificate and its
	// private key. Both must be set together to present a client certificate
	// for mutual TLS.
	EnvTLSCertFile = "NATS_TLS_CERT_FILE"
	EnvTLSKeyFile  = "NATS_TLS_KEY_FILE"

	// EnvNKeySeedFile points at the NKey seed file the client signs the server
	// nonce with. It must be set; the client always authenticates with an NKey.
	EnvNKeySeedFile = "NATS_NKEY_SEED_FILE"
)

// Options returns the NATS options implied by the environment: NKey
// authentication and, when the TLS paths are set, root CAs for server
// verification and a client certificate for mutual TLS. The RootCAs and
// ClientCert options defer reading their files to connect time, so this function
// surfaces an error only when the NKey seed is missing or unreadable, or the
// certificate pair is set inconsistently (only one of cert or key).
func Options() ([]nats.Option, error) {
	var opts []nats.Option

	if ca := os.Getenv(EnvTLSCAFile); ca != "" {
		opts = append(opts, nats.RootCAs(ca))
	}

	cert := os.Getenv(EnvTLSCertFile)
	key := os.Getenv(EnvTLSKeyFile)
	switch {
	case cert != "" && key != "":
		opts = append(opts, nats.ClientCert(cert, key))
	case cert != "" || key != "":
		return nil, fmt.Errorf("both %s and %s must be set for a client certificate", EnvTLSCertFile, EnvTLSKeyFile)
	}

	seed := os.Getenv(EnvNKeySeedFile)
	if seed == "" {
		return nil, fmt.Errorf("%s must be set: NATS requires NKey authentication", EnvNKeySeedFile)
	}
	opt, err := nats.NkeyOptionFromSeed(seed)
	if err != nil {
		return nil, fmt.Errorf("load NKey seed from %s: %w", seed, err)
	}
	opts = append(opts, opt)

	return opts, nil
}
