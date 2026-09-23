/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package controller

import (
	"strings"
	"testing"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

func TestHashConfigResourcesStableAcrossCalls(t *testing.T) {
	res := []string{
		"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\ndata:\n  a: b\n",
		"apiVersion: v1\nkind: Service\nmetadata:\n  name: x\n",
		"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: x\n",
	}
	first := hashConfigResources(res)
	second := hashConfigResources(res)
	if first == "" {
		t.Fatal("expected a non-empty hash for manifest with ConfigMap/Service")
	}
	if first != second {
		t.Errorf("hash not stable: %q vs %q", first, second)
	}
}

func TestHashConfigResourcesChangesWithContent(t *testing.T) {
	base := []string{"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\ndata:\n  a: b\n"}
	changed := []string{"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: x\ndata:\n  a: c\n"}
	if hashConfigResources(base) == hashConfigResources(changed) {
		t.Error("expected different hashes for different ConfigMap content")
	}
}

func TestHashConfigResourcesEmptyWithoutConfigOrService(t *testing.T) {
	res := []string{"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: x\n"}
	if got := hashConfigResources(res); got != "" {
		t.Errorf("expected empty hash when no ConfigMap/Service present, got %q", got)
	}
}

func TestHashConfigResourcesIgnoresServiceAccount(t *testing.T) {
	res := []string{
		"apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: x\n",
		"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: x\n",
	}
	if got := hashConfigResources(res); got != "" {
		t.Errorf("ServiceAccount must not count as a Service; expected empty hash, got %q", got)
	}
}

func TestDesiredMatchesLiveIgnoresServerFields(t *testing.T) {
	desired := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "v1",
		"kind":       "ConfigMap",
		"metadata": map[string]interface{}{
			"name":   "x",
			"labels": map[string]interface{}{"app": "x"},
		},
		"data": map[string]interface{}{"a": "b"},
	}}
	live := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "v1",
		"kind":       "ConfigMap",
		"metadata": map[string]interface{}{
			"name":              "x",
			"labels":            map[string]interface{}{"app": "x"},
			"uid":               "abc-123",
			"resourceVersion":   "9999",
			"creationTimestamp": "2026-01-01T00:00:00Z",
			"managedFields":     []interface{}{map[string]interface{}{"manager": "x"}},
		},
		"data":   map[string]interface{}{"a": "b"},
		"status": map[string]interface{}{"phase": "Active"},
	}}
	if !desiredMatchesLive(desired, live) {
		t.Error("expected match when only server-managed metadata and status differ")
	}

	// A real content change must be detected.
	live.Object["data"] = map[string]interface{}{"a": "c"}
	if desiredMatchesLive(desired, live) {
		t.Error("expected mismatch when data content differs")
	}
}

func TestMergeServerManagedMetadataPreservesLiveKeys(t *testing.T) {
	desired := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "apps/v1",
		"kind":       "Deployment",
		"metadata": map[string]interface{}{
			"name":        "x",
			"annotations": map[string]interface{}{"gmc.erag.intel.com/config-hash": "abc"},
		},
	}}
	live := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "apps/v1",
		"kind":       "Deployment",
		"metadata": map[string]interface{}{
			"name": "x",
			"annotations": map[string]interface{}{
				"gmc.erag.intel.com/config-hash":    "abc",
				"deployment.kubernetes.io/revision": "7",
			},
		},
	}}
	mergeServerManagedMetadata(desired, live)
	ann := desired.GetAnnotations()
	if ann["deployment.kubernetes.io/revision"] != "7" {
		t.Error("expected server-managed revision annotation to be carried over")
	}
	if ann["gmc.erag.intel.com/config-hash"] != "abc" {
		t.Error("expected controller-owned annotation to be preserved")
	}
	if !desiredMatchesLive(desired, live) {
		t.Error("expected match once server-managed annotations are merged in")
	}
}

func TestNextReconnectBackoffCapsAndGrows(t *testing.T) {
	b := reconnectBackoff
	prev := b
	for i := 0; i < 20; i++ {
		b = nextReconnectBackoff(b)
		if b < prev && b != maxReconnectBackoff {
			t.Errorf("backoff shrank unexpectedly: %v -> %v", prev, b)
		}
		if b > maxReconnectBackoff {
			t.Errorf("backoff %v exceeded cap %v", b, maxReconnectBackoff)
		}
		prev = b
	}
	if b != maxReconnectBackoff {
		t.Errorf("expected backoff to reach cap %v, got %v", maxReconnectBackoff, b)
	}
}

func TestJitteredWithinRange(t *testing.T) {
	d := 4 * maxReconnectBackoff
	for i := 0; i < 100; i++ {
		j := jittered(d)
		if j < d/2 || j > d {
			t.Fatalf("jittered(%v)=%v out of range [%v, %v]", d, j, d/2, d)
		}
	}
	if jittered(0) != 0 {
		t.Error("jittered(0) should be 0")
	}
}

// A workload an autoscaler owns renders without spec.replicas, so the count must
// be carried over from the live object; leaving it unset makes the API server
// reset it to one and undo every scaling decision.
func TestMergeAutoscaledReplicasKeepsLiveCount(t *testing.T) {
	desired := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "apps/v1",
		"kind":       "Deployment",
		"metadata":   map[string]interface{}{"name": "router-service-deployment"},
		"spec":       map[string]interface{}{"strategy": map[string]interface{}{"type": "RollingUpdate"}},
	}}
	live := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "apps/v1",
		"kind":       "Deployment",
		"metadata":   map[string]interface{}{"name": "router-service-deployment"},
		"spec":       map[string]interface{}{"replicas": int64(4)},
	}}

	mergeAutoscaledReplicas(desired, live)

	got, found, err := unstructured.NestedInt64(desired.Object, "spec", "replicas")
	if err != nil || !found {
		t.Fatalf("expected the live replica count to be carried over, found=%v err=%v", found, err)
	}
	if got != 4 {
		t.Errorf("expected 4 replicas carried over, got %d", got)
	}
}

// A manifest that does set replicas owns the count, so the live value must not
// override it.
func TestMergeAutoscaledReplicasKeepsRenderedCount(t *testing.T) {
	desired := &unstructured.Unstructured{Object: map[string]interface{}{
		"spec": map[string]interface{}{"replicas": int64(1)},
	}}
	live := &unstructured.Unstructured{Object: map[string]interface{}{
		"spec": map[string]interface{}{"replicas": int64(7)},
	}}

	mergeAutoscaledReplicas(desired, live)

	got, _, _ := unstructured.NestedInt64(desired.Object, "spec", "replicas")
	if got != 1 {
		t.Errorf("a rendered replica count must win, got %d", got)
	}
}

// Merging metadata must not write into the live object's maps, so a caller can
// still read what the live object actually carries.
func TestMergeServerManagedMetadataDoesNotMutateLive(t *testing.T) {
	desired := &unstructured.Unstructured{Object: map[string]interface{}{}}
	desired.SetLabels(map[string]string{"app": "desired"})
	live := &unstructured.Unstructured{Object: map[string]interface{}{}}
	live.SetLabels(map[string]string{"app": "live", "kept": "yes"})

	mergeServerManagedMetadata(desired, live)

	if live.GetLabels()["app"] != "live" {
		t.Errorf("the live object's labels were mutated, app=%q", live.GetLabels()["app"])
	}
	if desired.GetLabels()["kept"] != "yes" {
		t.Error("a server-managed label must be carried into the desired object")
	}
	if desired.GetLabels()["app"] != "desired" {
		t.Error("a rendered label must win over the live value")
	}
}

// A value containing three hyphens must not be read as a document boundary; a
// bare "---" split would cut the document mid-scalar and leave a fragment that
// no longer parses.
func TestSplitYAMLDocumentsSplitsOnBoundariesOnly(t *testing.T) {
	manifest := "apiVersion: v1\nkind: Service\nmetadata:\n  name: a\nspec:\n" +
		"  externalName: http://host---with---hyphens\n" +
		"---\n" +
		"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: b\n"

	docs := splitYAMLDocuments(manifest)
	if len(docs) != 2 {
		t.Fatalf("expected 2 documents, got %d: %q", len(docs), docs)
	}
	if !strings.Contains(docs[0], "host---with---hyphens") {
		t.Error("the hyphenated value must stay inside the first document")
	}
	if !strings.Contains(docs[1], "kind: ConfigMap") {
		t.Error("the second document must survive the split")
	}
}

// A separator carrying a trailing comment is still a boundary.
func TestSplitYAMLDocumentsAcceptsCommentedSeparator(t *testing.T) {
	docs := splitYAMLDocuments("kind: Service\n--- # next\nkind: ConfigMap\n")
	if len(docs) != 2 {
		t.Fatalf("expected 2 documents, got %d: %q", len(docs), docs)
	}
}
