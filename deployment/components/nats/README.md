# NATS component

NATS JetStream server that backs the fingerprint configuration projection. The
GMC controller writes the projection of the `fingerprint_config` Postgres table
into a memory-backed key/value bucket; the GMC router reads it to inject
per-step parameters. The fingerprint microservice never talks to NATS.

## Topology

The chart deploys a single NATS server by default (`cluster.enabled: false`),
which suits single-node clusters. Set `cluster.enabled: true` for a multi-node
RAFT cluster; it schedules `cluster.replicas` servers (3 by default) and needs
at least that many schedulable nodes to keep JetStream quorum.

The KV bucket (`fingerprint`) uses memory storage. Its contents are rebuilt from
Postgres by the controller's reconcile loop, so a NATS restart loses nothing
durable.

| Port | Name    | Purpose                    |
|------|---------|----------------------------|
| 4222 | client  | client connections         |
| 6222 | cluster | inter-server routes        |
| 8222 | monitor | HTTP monitoring / health   |
| 7777 | metrics | Prometheus exporter        |

`nats-svc` exposes the client port for the controller and router. A headless
service backs the StatefulSet for peer discovery when clustering is on.

## Authorization and transport security

Clients authenticate with an **NKey**, and NKey authorization is always on. Each
client signs the server nonce with its NKey seed, and the server admits only the
authorized public key. This keeps the leader-elected controller the sole writer
of the KV bucket, so no other pod on the network can inject fingerprint
parameters - the same principle by which Postgres and Redis keep their passwords
regardless of Istio.

Transport encryption follows the rest of the stack and is gated on Istio:

| Layer                | Istio enabled                          | Istio disabled           |
|----------------------|----------------------------------------|--------------------------|
| Transport encryption | ambient mesh mTLS (`nats://`)          | plaintext (`nats://`)    |
| NKey authorization   | always on                              | always on                |

When Istio is enabled, the `nats` namespace is labelled
`istio.io/dataplane-mode: ambient`, so the mesh encrypts traffic transparently
and the server runs no NATS-native TLS. When Istio is disabled there is no
transport encryption. Clients use the plaintext `nats://` scheme in both cases.

The `app_nats` Ansible role generates the NKey pair once and stores it in the
`nats-auth` secret:

| Secret key | Used by  | Contents                          |
|------------|----------|-----------------------------------|
| `user.pub` | server   | authorized client NKey public key |
| `user.nk`  | clients  | client NKey seed                  |

The server reads `user.pub` (substituted into `nats.conf` from the unquoted
`$NATS_USER_NKEY` at startup). The role mirrors `user.nk` into the controller and
router namespaces; each client reads its path from `NATS_NKEY_SEED_FILE`.

## KV bucket

A post-install/post-upgrade Job (`nats-box`) creates the `fingerprint` bucket if
it is absent (`--storage=memory --history=1 --replicas=1`). The check is
idempotent, and the controller's bridge also creates the bucket on connect, so
the two never conflict.

## Values

| Key                      | Default                          | Description                          |
|--------------------------|----------------------------------|--------------------------------------|
| `cluster.enabled`        | `false`                          | single server vs. RAFT cluster       |
| `cluster.replicas`       | `3`                              | server count when clustered          |
| `auth.existingSecret`    | `nats-auth`                      | secret holding the NKey pair          |
| `kv.bucket`              | `fingerprint`                    | KV bucket name                       |
| `jetstream.maxMemory`    | `256M`                           | JetStream memory store size          |
| `persistence.enabled`    | `false`                          | persist the JetStream store dir      |
| `monitoring.enabled`     | `true`                           | Prometheus exporter + ServiceMonitor |
