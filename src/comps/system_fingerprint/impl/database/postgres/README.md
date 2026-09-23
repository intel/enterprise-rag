# PostgreSQL Database

This document focuses on using [PostgreSQL](https://www.postgresql.org/) for the System Fingerprint Microservice.

The microservice creates its schema (`fingerprint_config` table plus the change-notification trigger) automatically on startup, so a plain PostgreSQL instance with an empty database is all that is required.

## Getting Started

### Prerequisites

You can set all required environment variables in the [.env](../../microservice/.env) file.

### Start the PostgreSQL Service

To build and start the services use the docker-compose.yaml file provided:

```bash
docker compose --env-file ../../microservice/.env -f docker-compose.yaml up --build -d
```

### Verify the Services

In order to verify if services are working, use example requests provided in [README.md](../../../README.md)

### Service Cleanup

To cleanup the services, run the following command:

```bash
docker compose --env-file ../../microservice/.env -f docker-compose.yaml down
```
