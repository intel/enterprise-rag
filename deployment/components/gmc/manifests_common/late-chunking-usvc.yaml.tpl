---
# Source: late-chunking-usvc/templates/configmap.yaml
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

apiVersion: v1
kind: ConfigMap
metadata:
  name: late-chunking-usvc-config
  labels:
    {{- include "manifest.labels" (list .filename .) | nindent 4 }}
data:
  {{- include "manifest.addEnvsAndEnvFile" (list .filename .) | nindent 2 }}
  http_proxy: {{ .Values.proxy.http_proxy | quote }}
  https_proxy: {{ .Values.proxy.https_proxy | quote }}
  no_proxy: {{ .Values.proxy.no_proxy | quote }}
---
# Source: late-chunking-usvc/templates/service.yaml
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

apiVersion: v1
kind: Service
metadata:
  name: late-chunking-usvc
  labels:
    {{- include "manifest.labels" (list .filename .) | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: 8003
      targetPort: 8003
      protocol: TCP
      name: late-chunking-usvc
  selector:
    {{- include "manifest.selectorLabels" (list .filename .) | nindent 4 }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  labels:
    app.kubernetes.io/name: late-chunking-usvc
    app.kubernetes.io/instance: late-chunking-usvc
  name: late-chunking-usvc
---
# Source: late-chunking-usvc/templates/deployment.yaml
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

apiVersion: apps/v1
kind: Deployment
metadata:
  name: late-chunking-usvc
  labels:
    {{- include "manifest.labels" (list .filename .) | nindent 4 }}
spec:
  replicas: {{ include "getReplicas" (list .filename .Values) | default 1 }}
  selector:
    matchLabels:
    {{- include "manifest.selectorLabels" (list .filename .) | nindent 6 }}
  template:
    metadata:
      {{- include "manifest.podLabels" (list .filename .) | nindent 6 }}
    spec:
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      serviceAccountName: late-chunking-usvc
      initContainers:
        - name: wait-for-embedding-service
          image: alpine/curl
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
              - ALL
            readOnlyRootFilesystem: true
          envFrom:
            - configMapRef:
                name: late-chunking-usvc-config
            - configMapRef:
                name: extra-env-config
                optional: true
          command:
            - sh
            - -c
            - |
                if [ -z "$EMBEDDING_ENDPOINT" ]; then
                  echo "Environment variable EMBEDDING_ENDPOINT is not set. Skipping the init container.";
                else
                  until curl -sf $EMBEDDING_ENDPOINT; do
                    echo "waiting for embedding service $EMBEDDING_ENDPOINT to be ready...";
                    sleep 2;
                  done;
                fi;
      {{- include "gmc.imagePullSecrets" . }}
      containers:
        - name: late-chunking-usvc
          envFrom:
            - configMapRef:
                name: late-chunking-usvc-config
            - configMapRef:
                name: extra-env-config
                optional: true
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: {{ include "manifest.image" (list .filename .Values) }}
          imagePullPolicy: {{ toYaml (index .Values "images" .filename "pullPolicy" | default "Always") }}
          ports:
            - name: late-chunking-usvc
              containerPort: 8003
              protocol: TCP
          volumeMounts:
            - mountPath: /tmp
              name: tmp
          livenessProbe:
            failureThreshold: 24
            httpGet:
              path: v1/health_check
              port: late-chunking-usvc
            initialDelaySeconds: 5
            periodSeconds: 60
            timeoutSeconds: 10
          readinessProbe:
            httpGet:
              path: v1/health_check
              port: late-chunking-usvc
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 10
          startupProbe:
            failureThreshold: 240
            httpGet:
              path: v1/health_check
              port: late-chunking-usvc
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 10
          resources:
            {{- $defaultValues := "{requests: {cpu: '1', memory: '2Gi'}, limits: {cpu: '4', memory: '4Gi'}}" -}}
            {{- include "manifest.getResource" (list .filename $defaultValues .Values) | nindent 12 }}
      volumes:
        - name: tmp
          emptyDir: {}
{{- include "manifest.serviceMonitor" (list .filename "late-chunking-usvc" .) }}

