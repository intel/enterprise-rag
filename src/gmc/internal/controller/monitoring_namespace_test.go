/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"context"
	"testing"

	mcv1alpha3 "erag.intel.com/gmc/api/v1alpha3"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/tools/record"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

// The pipeline namespace used throughout; deliberately different from the
// namespace a monitor must not be pinned to.
const testPipelineNs = "chatqna"

// A step manifest whose ServiceMonitor pins a central monitoring namespace, the
// shape the chart templates used to ship. The other documents stand in for the
// rest of a step so the manifest travels the normal decode path.
const stepManifestPinnedMonitorNs = `
apiVersion: v1
kind: ConfigMap
metadata:
  name: in-guard-usvc-config
data:
  KEY: "value"
---
apiVersion: v1
kind: Service
metadata:
  name: in-guard-usvc
spec:
  selector:
    app: in-guard-usvc
  ports:
  - name: in-guard-usvc
    port: 8080
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: in-guard-usvc
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app.kubernetes.io/instance: in-guard-usvc
  endpoints:
  - port: in-guard-usvc
`

// The same manifest with the ServiceMonitor carrying no namespace at all, which
// is what the chart renders today.
const stepManifestNoMonitorNs = `
apiVersion: v1
kind: Service
metadata:
  name: in-guard-usvc
spec:
  selector:
    app: in-guard-usvc
  ports:
  - name: in-guard-usvc
    port: 8080
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: in-guard-usvc
spec:
  selector:
    matchLabels:
      app.kubernetes.io/instance: in-guard-usvc
  endpoints:
  - port: in-guard-usvc
`

// A router template whose PodMonitor omits the namespace the rest of the
// documents interpolate.
const routerManifestNoMonitorNs = `
apiVersion: v1
kind: Service
metadata:
  name: {{.SvcName}}
  namespace: {{.Namespace}}
spec:
  selector:
    app: router-service
  ports:
  - name: router
    port: 8080
---
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: router-service
spec:
  selector:
    matchLabels:
      app: router-service
  podMetricsEndpoints:
  - targetPort: 8080
`

// A router template whose PodMonitor pins a central monitoring namespace.
const routerManifestPinnedMonitorNs = `
apiVersion: v1
kind: Service
metadata:
  name: {{.SvcName}}
  namespace: {{.Namespace}}
spec:
  selector:
    app: router-service
  ports:
  - name: router
    port: 8080
---
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: router-service
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: router-service
  podMetricsEndpoints:
  - targetPort: 8080
`

// newReconcilerWithManifest builds a reconciler backed by a fake client that
// serves the given manifest from the gmc ConfigMap, with the prometheus-operator
// kinds registered so the CRD guard lets the monitors through.
func newReconcilerWithManifest(manifestKey, manifest string) (*GMConnectorReconciler, client.Client) {
	sch := runtime.NewScheme()
	utilRuntimeMust(clientgoscheme.AddToScheme(sch))
	utilRuntimeMust(mcv1alpha3.AddToScheme(sch))

	groupVersion := schema.GroupVersion{Group: monitoringCoreOSGroup, Version: "v1"}
	mapper := meta.NewDefaultRESTMapper([]schema.GroupVersion{groupVersion})
	for _, kind := range []string{"ServiceMonitor", "PodMonitor"} {
		mapper.Add(groupVersion.WithKind(kind), meta.RESTScopeNamespace)
	}

	// getTemplateBytes reads the manifest from the ConfigMap in the controller's
	// own namespace, so seed it there.
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: GMCConfigMapName, Namespace: gmcNs},
		Data:       map[string]string{manifestKey: manifest},
	}
	c := fake.NewClientBuilder().WithScheme(sch).WithRESTMapper(mapper).WithObjects(cm).Build()
	return &GMConnectorReconciler{Client: c, Scheme: sch, Recorder: record.NewFakeRecorder(20)}, c
}

func utilRuntimeMust(err error) {
	if err != nil {
		panic(err)
	}
}

func testGraph() *mcv1alpha3.GMConnector {
	graph := &mcv1alpha3.GMConnector{
		ObjectMeta: metav1.ObjectMeta{Name: testPipelineNs, Namespace: testPipelineNs},
	}
	graph.Status.Annotations = map[string]string{}
	return graph
}

// assertMonitorInPipelineNs looks the monitor up in the pipeline namespace and
// checks it is owned by the GMConnector there, so deleting the pipeline takes
// its monitoring with it.
func assertMonitorInPipelineNs(t *testing.T, c client.Client, kind, name string) {
	t.Helper()

	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(schema.GroupVersionKind{Group: monitoringCoreOSGroup, Version: "v1", Kind: kind})
	key := client.ObjectKey{Namespace: testPipelineNs, Name: name}
	if err := c.Get(context.Background(), key, obj); err != nil {
		t.Fatalf("expected %s %q in namespace %q, got %v", kind, name, testPipelineNs, err)
	}
	if got := obj.GetNamespace(); got != testPipelineNs {
		t.Errorf("%s %q namespace = %q, want %q", kind, name, got, testPipelineNs)
	}

	owners := obj.GetOwnerReferences()
	if len(owners) != 1 || owners[0].Kind != "GMConnector" || owners[0].Name != testPipelineNs {
		t.Errorf("%s %q owner references = %v, want a single GMConnector %q", kind, name, owners, testPipelineNs)
	}
}

// A step's ServiceMonitor lands beside the service it monitors even when the
// manifest names a central monitoring namespace.
func TestStepServiceMonitorOverridesPinnedNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("in-guard-usvc.yaml", stepManifestPinnedMonitorNs)
	graph := testGraph()
	step := &mcv1alpha3.Step{
		StepName: LLMGuardInput,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{ServiceName: "in-guard-usvc"},
		},
	}
	node := &mcv1alpha3.Router{Steps: []mcv1alpha3.Step{*step}}

	if _, err := r.reconcileResource(context.Background(), testPipelineNs, step, node, graph); err != nil {
		t.Fatalf("reconcileResource failed: %v", err)
	}
	assertMonitorInPipelineNs(t, c, "ServiceMonitor", "in-guard-usvc")
}

// A step's ServiceMonitor is namespaced by the controller, not by the manifest,
// so a document that carries no namespace is still applied into the pipeline.
// Dropping that assignment leaves the monitor cluster-scoped, which the
// namespaced owner reference then rejects.
func TestStepServiceMonitorGetsPipelineNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("in-guard-usvc.yaml", stepManifestNoMonitorNs)
	graph := testGraph()
	step := &mcv1alpha3.Step{
		StepName: LLMGuardInput,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{ServiceName: "in-guard-usvc"},
		},
	}
	node := &mcv1alpha3.Router{Steps: []mcv1alpha3.Step{*step}}

	if _, err := r.reconcileResource(context.Background(), testPipelineNs, step, node, graph); err != nil {
		t.Fatalf("reconcileResource failed: %v", err)
	}
	assertMonitorInPipelineNs(t, c, "ServiceMonitor", "in-guard-usvc")
}

// The router's PodMonitor lands in the router namespace even when the template
// leaves the namespace off that document.
func TestRouterPodMonitorGetsRouterNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("gmc-router.yaml", routerManifestNoMonitorNs)

	if err := r.reconcileRouterService(context.Background(), testGraph()); err != nil {
		t.Fatalf("reconcileRouterService failed: %v", err)
	}
	assertMonitorInPipelineNs(t, c, "PodMonitor", "router-service")
}

// The router's PodMonitor lands in the router namespace even when the template
// names a central monitoring namespace.
func TestRouterPodMonitorOverridesPinnedNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("gmc-router.yaml", routerManifestPinnedMonitorNs)

	if err := r.reconcileRouterService(context.Background(), testGraph()); err != nil {
		t.Fatalf("reconcileRouterService failed: %v", err)
	}
	assertMonitorInPipelineNs(t, c, "PodMonitor", "router-service")
}

// A pipeline deployed under a different name and namespace gets its monitors in
// that namespace too, so the rule is not specific to chatqna.
func TestMonitorsFollowAnyPipelineNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("in-guard-usvc.yaml", stepManifestPinnedMonitorNs)
	graph := &mcv1alpha3.GMConnector{
		ObjectMeta: metav1.ObjectMeta{Name: "docsum", Namespace: "docsum"},
	}
	graph.Status.Annotations = map[string]string{}
	step := &mcv1alpha3.Step{
		StepName: LLMGuardInput,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{ServiceName: "in-guard-usvc"},
		},
	}
	node := &mcv1alpha3.Router{Steps: []mcv1alpha3.Step{*step}}

	if _, err := r.reconcileResource(context.Background(), "docsum", step, node, graph); err != nil {
		t.Fatalf("reconcileResource failed: %v", err)
	}

	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(schema.GroupVersionKind{Group: monitoringCoreOSGroup, Version: "v1", Kind: "ServiceMonitor"})
	key := client.ObjectKey{Namespace: "docsum", Name: "in-guard-usvc"}
	if err := c.Get(context.Background(), key, obj); err != nil {
		t.Fatalf("expected ServiceMonitor in namespace \"docsum\", got %v", err)
	}
}

// A step is always applied into the graph's namespace. The CRD used to let a step
// or the router name its own namespace, but the GMConnector owner reference every
// applied object carries cannot cross namespaces, so any value other than the
// graph's guaranteed a failed reconcile; the fields were removed. This pins the
// remaining behaviour so a per-step namespace cannot be reintroduced silently.
func TestStepAlwaysLandsInTheGraphNamespace(t *testing.T) {
	r, c := newReconcilerWithManifest("in-guard-usvc.yaml", stepManifestNoMonitorNs)
	graph := testGraph()
	step := &mcv1alpha3.Step{
		StepName: LLMGuardInput,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{ServiceName: "in-guard-usvc"},
		},
	}
	node := &mcv1alpha3.Router{Steps: []mcv1alpha3.Step{*step}}

	if _, err := r.reconcileResource(context.Background(), testPipelineNs, step, node, graph); err != nil {
		t.Fatalf("reconcileResource failed: %v", err)
	}

	// The Service and its monitor both belong to the pipeline, and the owner
	// reference is in-namespace, so nothing is rejected.
	for _, kind := range []string{"Service", "ServiceMonitor"} {
		obj := &unstructured.Unstructured{}
		if kind == "Service" {
			obj.SetGroupVersionKind(schema.GroupVersionKind{Version: "v1", Kind: kind})
		} else {
			obj.SetGroupVersionKind(schema.GroupVersionKind{Group: monitoringCoreOSGroup, Version: "v1", Kind: kind})
		}
		key := client.ObjectKey{Namespace: testPipelineNs, Name: "in-guard-usvc"}
		if err := c.Get(context.Background(), key, obj); err != nil {
			t.Fatalf("%s not found in %q: %v", kind, testPipelineNs, err)
		}
		if obj.GetNamespace() != testPipelineNs {
			t.Errorf("%s namespace = %q, want %q", kind, obj.GetNamespace(), testPipelineNs)
		}
	}
}
