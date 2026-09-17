# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

---
apiVersion: apps/v1
kind: Deployment
metadata:
{{- `
  name: {{.DplymntName}}
  namespace: {{.Namespace}}
` }}
  labels:
    {{- include "manifest.labels" (list "gmc-router" .) | nindent 4 }}
spec:
  {{- if not .Values.router.hpa.enabled }}
  replicas: {{ .Values.router.replicaCount | default 1 }}
  {{- end }}
  # Keep at least one pod serving during a rollout; readiness gates cutover.
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: router-service
      app.kubernetes.io/name: router-service
      app.kubernetes.io/version: "v0.8"
  template:
    metadata:
      labels:
        app: router-service
        app.kubernetes.io/name: router-service
        app.kubernetes.io/version: "v0.8"
    spec:
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      serviceAccountName: default
      {{- include "gmc.imagePullSecrets" . }}
      # Spread replicas across nodes when more than one is scheduled.
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              topologyKey: kubernetes.io/hostname
              labelSelector:
                matchLabels:
                  app: router-service
      containers:
      - name: router-server
        {{- $image := "gmcRouter" }}
        image: {{ include "manifest.image" (list $image .Values) }}
        imagePullPolicy: {{ toYaml (index .Values "images" $image "pullPolicy" | default "Always") }}
        securityContext:
            {{- toYaml .Values.securityContext | nindent 10 }}
        ports:
        - containerPort: 8080
        # Router serves liveness/readiness on the same :8080 as traffic; a hung
        # process fails these so it is restarted and taken out of rotation.
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 15
          timeoutSeconds: 3
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
        env:
        - name: NATS_URL
          value: {{ .Values.nats.url | quote }}
        - name: FINGERPRINT_SERVICE_URL
          value: {{ .Values.fingerprint.url | quote }}
        - name: NATS_NKEY_SEED_FILE
          value: /etc/nats/auth/{{ .Values.nats.auth.userSeedKey }}
        {{- `
        - name: no_proxy
          value: {{.NoProxy}}
        - name: http_proxy
          value: {{.HttpProxy}}
        - name: https_proxy
          value: {{.HttpsProxy}}
        ### Fingerprint config source (KV projection)
        # pipeline scope: the router watches only its own <pipeline>.<tenant>.* keys
        - name: PIPELINE_NAME
          value: "{{.Namespace}}"
        - name: TENANT_NAME
          value: "_global"
        ### OTEL/Tracing
        # target
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otelcol-traces-collector.monitoring-traces:4318"
        # exclusion
        - name: OTEL_GO_EXCLUDED_URLS
          value: "/metrics"
        # identification
        - name: OTEL_SERVICE_NAME
          value: "{{.Namespace}}/{{.DplymntName}}"
        # identification (namespace is used to distinguish different span names for different router-instances) used by router not OTEL
        - name: OTEL_NAMESPACE
          value: "{{.Namespace}}"
        ### TODO: Enabling this breaks traces->logs correlation when query in Grafana
        # - name: OTEL_RESOURCE_ATTRIBUTES
        #   value: "namespace={{.Namespace}}"
        # ratio: 0 never and 1 always with 0.5 half of queries will be traced
        - name: OTEL_TRACES_SAMPLER_FRACTION
          value: "1.0"
        ### OTEL/Logs: Warning: Enabling logs through collector disables logs to stdout
        # - name: OTEL_LOGS_GRPC_ENDPOINT
        #   value: "otelcol-traces-collector.monitoring-traces:4317"
        ` -}}
        args:
        {{- `
        - "--graph-json"
        - {{.GRAPH_JSON}}
        ` -}}
        resources:
          {{- if and .Values.services (index .Values.services "gmc-router") (index .Values.services "gmc-router" "resources") }}
          {{- index .Values.services "gmc-router" "resources" | toYaml | nindent 12 }}
          {{- else }}
          {{- toYaml .Values.router.resources | nindent 12 }}
          {{- end }}
        volumeMounts:
        - name: nats-auth
          mountPath: /etc/nats/auth
          readOnly: true
      volumes:
      - name: nats-auth
        secret:
          secretName: {{ .Values.nats.auth.existingSecret | quote }}
          defaultMode: 0440
          items:
          - key: {{ .Values.nats.auth.userSeedKey }}
            path: {{ .Values.nats.auth.userSeedKey }}
---
apiVersion: v1
kind: Service
metadata:
{{- `
  name: {{.SvcName}}
  namespace: {{.Namespace}}
` -}}
spec:
  type: ClusterIP
  selector:
    app: router-service
    app.kubernetes.io/name: router-service
    app.kubernetes.io/version: "v0.8"
  ports:
    - protocol: TCP
      port: 8080
      targetPort: 8080
{{- if .Values.router.pdb.enabled }}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
{{- `
  name: {{.DplymntName}}-pdb
  namespace: {{.Namespace}}
` }}
  labels:
    {{- include "manifest.labels" (list "gmc-router" .) | nindent 4 }}
spec:
  minAvailable: {{ .Values.router.pdb.minAvailable | default 1 }}
  selector:
    matchLabels:
      app: router-service
{{- end }}
{{- if .Values.router.hpa.enabled }}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
{{- `
  name: {{.DplymntName}}
  namespace: {{.Namespace}}
` }}
  labels:
    {{- include "manifest.labels" (list "gmc-router" .) | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
{{- `
    name: {{.DplymntName}}
` }}
  minReplicas: {{ .Values.router.hpa.minReplicas | default 1 }}
  maxReplicas: {{ .Values.router.hpa.maxReplicas | default 4 }}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {{ .Values.router.hpa.targetCPUUtilizationPercentage | default 80 }}
  {{- with .Values.router.hpa.behavior }}
  behavior:
    {{- toYaml . | nindent 4 }}
  {{- else }}
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
    scaleUp:
      selectPolicy: Max
      stabilizationWindowSeconds: 0
      policies:
      - type: Pods
        value: 1
        periodSeconds: 30
  {{- end }}
{{- end }}
{{- if .Values.monitoring.enabled }}
---
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
{{- `
  name: router-service
  namespace: {{.Namespace}}
` }}
  labels:
    {{- include "manifest.labels" (list "gmc-router" .) | nindent 4 }}
    release: {{ .Release.Name }}
spec:
  selector:
    matchLabels:
      app: router-service
  podMetricsEndpoints:
  - targetPort: 8080
{{- end }}
