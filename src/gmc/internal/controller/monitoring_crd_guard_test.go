/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"strings"
	"testing"

	mcv1alpha3 "erag.intel.com/gmc/api/v1alpha3"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/tools/record"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func serviceMonitorObj() *unstructured.Unstructured {
	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(schema.GroupVersionKind{
		Group:   monitoringCoreOSGroup,
		Version: "v1",
		Kind:    "ServiceMonitor",
	})
	obj.SetName("llm-usvc")
	return obj
}

func newReconcilerWithMapper(mapper meta.RESTMapper) (*GMConnectorReconciler, *record.FakeRecorder) {
	rec := record.NewFakeRecorder(10)
	c := fake.NewClientBuilder().WithRESTMapper(mapper).Build()
	return &GMConnectorReconciler{Client: c, Scheme: c.Scheme(), Recorder: rec}, rec
}

// When the ServiceMonitor CRD is absent, the RESTMapper resolves nothing and the
// object is skipped with a Warning Event rather than failing the reconcile.
func TestSkipIfCRDMissingSkipsWhenCRDAbsent(t *testing.T) {
	mapper := meta.NewDefaultRESTMapper(nil)
	r, rec := newReconcilerWithMapper(mapper)

	skip, err := r.skipIfCRDMissing(&mcv1alpha3.GMConnector{}, serviceMonitorObj())
	if err != nil {
		t.Fatalf("expected no error when CRD is missing, got %v", err)
	}
	if !skip {
		t.Fatal("expected skip=true when the ServiceMonitor CRD is not installed")
	}
	select {
	case ev := <-rec.Events:
		// FakeRecorder formats events as "<Type> <Reason> <Message>".
		if !strings.HasPrefix(ev, "Warning MonitoringCRDMissing ") {
			t.Errorf("expected a Warning/MonitoringCRDMissing event, got %q", ev)
		}
	default:
		t.Error("expected a Warning Event to be recorded for the missing CRD")
	}
}

// When the ServiceMonitor CRD is registered, the object is applied normally.
func TestSkipIfCRDMissingAppliesWhenCRDPresent(t *testing.T) {
	gvk := schema.GroupVersionKind{Group: monitoringCoreOSGroup, Version: "v1", Kind: "ServiceMonitor"}
	mapper := meta.NewDefaultRESTMapper([]schema.GroupVersion{gvk.GroupVersion()})
	mapper.Add(gvk, meta.RESTScopeNamespace)
	r, _ := newReconcilerWithMapper(mapper)

	skip, err := r.skipIfCRDMissing(&mcv1alpha3.GMConnector{}, serviceMonitorObj())
	if err != nil {
		t.Fatalf("expected no error when CRD is present, got %v", err)
	}
	if skip {
		t.Fatal("expected skip=false when the ServiceMonitor CRD is installed")
	}
}

// Non-monitoring resources bypass the guard regardless of the RESTMapper.
func TestSkipIfCRDMissingIgnoresOtherKinds(t *testing.T) {
	r, _ := newReconcilerWithMapper(meta.NewDefaultRESTMapper(nil))

	cm := &unstructured.Unstructured{}
	cm.SetGroupVersionKind(schema.GroupVersionKind{Version: "v1", Kind: "ConfigMap"})
	cm.SetName("x")

	skip, err := r.skipIfCRDMissing(&mcv1alpha3.GMConnector{ObjectMeta: metav1.ObjectMeta{Name: "g"}}, cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if skip {
		t.Fatal("expected skip=false for a non-monitoring resource")
	}
}
