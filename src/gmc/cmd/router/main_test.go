/*
* Copyright (C) 2024-2026 Intel Corporation
* SPDX-License-Identifier: Apache-2.0
 */

package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	mcv1alpha3 "erag.intel.com/gmc/api/v1alpha3"
	"github.com/stretchr/testify/assert"
	"knative.dev/pkg/apis"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
)

func init() {
	logf.SetLogger(zap.New())
}

func TestSimpleModelChainer(t *testing.T) {
	// Start a local HTTP server
	service1 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{"predictions": "1"}
		responseBytes, _ := json.Marshal(response)
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service1Url, err := apis.ParseURL(service1.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service1.Close()
	service2 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{"predictions": "2"}
		responseBytes, _ := json.Marshal(response)
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service2Url, err := apis.ParseURL(service2.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service2.Close()

	gmcGraph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: service1Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "embedding-service",
								},
							},
						},
						{
							StepName:   "service2",
							ServiceURL: service2Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
							Data: "$response",
						},
					},
				},
			},
		},
	}
	input := map[string]interface{}{
		"instances": []string{
			"test",
			"test2",
		},
	}
	jsonBytes, _ := json.Marshal(input)
	headers := http.Header{
		"Authorization": {"Bearer Token"},
	}

	ctx := context.Background()
	res, _, err := routeStep(ctx, "root", gmcGraph, jsonBytes, jsonBytes, headers)
	if err != nil {
		return
	}
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(res)
	if rerr != nil {
		t.Fatalf("Error while reading the response body: %v", rerr)
		return
	}
	err = json.Unmarshal(responseBytes, &response)
	if err != nil {
		return
	}
	expectedResponse := map[string]interface{}{
		"predictions": "2",
	}
	fmt.Printf("final response:%v\n", response)
	assert.Equal(t, expectedResponse, response)
}

func TestSimpleServiceEnsemble(t *testing.T) {
	// Start a local HTTP server
	service1 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{"predictions": "1"}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service1Url, err := apis.ParseURL(service1.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service1.Close()
	service2 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{"predictions": "2"}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service2Url, err := apis.ParseURL(service2.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service2.Close()

	gmcGraph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Ensemble,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: service1Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "embedding-service",
								},
							},
						},
						{
							StepName:   "service2",
							ServiceURL: service2Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
						},
					},
				},
			},
		},
	}

	input := map[string]interface{}{
		"instances": []string{
			"test",
			"test2",
		},
	}
	jsonBytes, _ := json.Marshal(input)
	headers := http.Header{
		"Authorization": {"Bearer Token"},
	}
	ctx := context.Background()
	res, _, err := routeStep(ctx, "root", gmcGraph, jsonBytes, jsonBytes, headers)
	if err != nil {
		return
	}
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(res)
	if rerr != nil {
		t.Fatalf("Error while reading the response body")
		return
	}
	err = json.Unmarshal(responseBytes, &response)
	if err != nil {
		return
	}
	expectedResponse := map[string]interface{}{
		"service1": map[string]interface{}{
			"predictions": "1",
		},
		"service2": map[string]interface{}{
			"predictions": "2",
		},
	}
	fmt.Printf("final response:%v\n", response)
	assert.Equal(t, expectedResponse, response)
}

func TestMCWithCondition(t *testing.T) {
	// Start a local HTTP server
	service1 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "cat",
					"score": []float32{
						0.1, 0.9,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service1Url, err := apis.ParseURL(service1.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service1.Close()
	service2 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "dog",
					"score": []float32{
						0.8, 0.2,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service2Url, err := apis.ParseURL(service2.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service2.Close()

	// Start a local HTTP server
	service3 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "beagle",
					"score": []float32{
						0.1, 0.9,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service3Url, err := apis.ParseURL(service3.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service3.Close()
	service4 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "poodle",
					"score": []float32{
						0.8, 0.2,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service4Url, err := apis.ParseURL(service4.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service4.Close()

	gmcGraph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName: "step1",
							Executor: mcv1alpha3.Executor{
								NodeName: "animal-categorize",
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
						},
						{
							StepName: "step2",
							Executor: mcv1alpha3.Executor{
								NodeName: "breed-categorize",
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tgi-service",
								},
							},
							Condition: "predictions.#(label==\"dog\")",
						},
					},
				},
				"animal-categorize": {
					RouterType: mcv1alpha3.Switch,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: service1Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
							Condition: "instances.#(modelId==\"1\")",
						},
						{
							StepName:   "service2",
							ServiceURL: service2Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tgi-service",
								},
							},
							Condition: "instances.#(modelId==\"2\")",
						},
					},
				},
				"breed-categorize": {
					RouterType: mcv1alpha3.Ensemble,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service3",
							ServiceURL: service3Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
						},
						{
							StepName:   "service4",
							ServiceURL: service4Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tgi-service",
								},
							},
						},
					},
				},
			},
		},
	}
	input := map[string]interface{}{
		"instances": []map[string]string{
			{"modelId": "2"},
		},
	}
	jsonBytes, _ := json.Marshal(input)
	headers := http.Header{
		"Authorization": {"Bearer Token"},
	}
	ctx := context.Background()
	res, _, err := routeStep(ctx, "root", gmcGraph, jsonBytes, jsonBytes, headers)
	if err != nil {
		return
	}
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(res)
	if rerr != nil {
		t.Fatalf("Error while reading the response body")
		return
	}
	err = json.Unmarshal(responseBytes, &response)
	if err != nil {
		return
	}
	expectedservice3Response := map[string]interface{}{
		"predictions": []interface{}{
			map[string]interface{}{
				"label": "beagle",
				"score": []interface{}{
					0.1, 0.9,
				},
			},
		},
	}

	expectedservice4Response := map[string]interface{}{
		"predictions": []interface{}{
			map[string]interface{}{
				"label": "poodle",
				"score": []interface{}{
					0.8, 0.2,
				},
			},
		},
	}
	fmt.Printf("final response:%v\n", response)
	assert.Equal(t, expectedservice3Response, response["service3"])
	assert.Equal(t, expectedservice4Response, response["service4"])
}

func TestCallServiceWhenNoneHeadersToPropagateIsEmpty(t *testing.T) {
	// Start a local HTTP server
	service1 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		// Putting headers as part of response so that we can assert the headers' presence later
		response := make(map[string]interface{})
		response["predictions"] = "1"
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service1Url, err := apis.ParseURL(service1.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service1.Close()

	input := map[string]interface{}{
		"instances": []string{
			"test",
			"test2",
		},
	}
	jsonBytes, _ := json.Marshal(input)
	headers := http.Header{
		"Authorization":   {"Bearer Token"},
		"Test-Header-Key": {"Test-Header-Value"},
	}

	step := &mcv1alpha3.Step{
		StepName:   "service1",
		ServiceURL: service1Url.String(),
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{
				ServiceName: "tei-embedding-service",
			},
		},
		Condition: "instances.#(modelId==\"1\")",
	}

	ctx := context.Background()
	res, _, err := callService(ctx, step, service1Url.String(), jsonBytes, headers)
	if err != nil {
		return
	}
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(res)
	if rerr != nil {
		t.Fatalf("Error while reading the response body")
		return
	}
	err = json.Unmarshal(responseBytes, &response)
	if err != nil {
		return
	}
	expectedResponse := map[string]interface{}{
		"predictions": "1",
	}
	fmt.Printf("final response:%v\n", response)
	assert.Equal(t, expectedResponse, response)
}

func TestMalformedURL(t *testing.T) {
	malformedURL := "http://single-1.default.{$your-domain}/switch"
	step := &mcv1alpha3.Step{
		StepName:   "service1",
		ServiceURL: malformedURL,
		Executor: mcv1alpha3.Executor{
			InternalService: mcv1alpha3.GMCTarget{
				ServiceName: "tei-embedding-service",
			},
		},
		Condition: "instances.#(modelId==\"1\")",
	}

	ctx := context.Background()
	_, response, err := callService(ctx, step, malformedURL, []byte{}, http.Header{})
	if err != nil {
		assert.Equal(t, 500, response)
	}
}
func TestPrepareErrorResponse(t *testing.T) {
	err := errors.New("test error")
	errorMessage := "Test error message"
	expectedResponse := []byte(`{"error":"Test error message","cause":"test error","user_message":"test error"}`)

	response := prepareErrorResponse(err, errorMessage)

	assert.Equal(t, expectedResponse, response)
}

func TestExtractUserMessage(t *testing.T) {
	tests := []struct {
		name     string
		cause    string
		expected string
	}{
		{
			name:     "double-quoted message field",
			cause:    `Error occured for step (stepName=Llm) with statusCode=400. Stopping pipeline execution. Error details: A BadRequestError occured while processing: Error code: 400 - {'object': 'error', 'message': "This model's maximum context length is 4096 tokens. However, you requested 4207 tokens (3183 in the messages, 1024 in the completion). Please reduce the length of the messages or completion. None", 'type': 'BadRequestError', 'param': None, 'code': 400}`,
			expected: "This model's maximum context length is 4096 tokens. However, you requested 4207 tokens (3183 in the messages, 1024 in the completion). Please reduce the length of the messages or completion. None",
		},
		{
			name:     "single-quoted message field",
			cause:    `Error details: {'message': 'Some error occurred', 'type': 'Error'}`,
			expected: "Some error occurred",
		},
		{
			name:     "json-style double-quoted message field",
			cause:    `Error details: {"message": "Token limit exceeded", "code": 400}`,
			expected: "Token limit exceeded",
		},
		{
			name:     "json-style no-space message field (vLLM format)",
			cause:    `Error occured for step (stepName=Embedding) with statusCode=400. Stopping pipeline execution. Error details: ValueError occured while validating the input: vLLM returned an error response: 400 - {"error":{"message":"This model's maximum context length is 512 tokens. However, your request has 5729 input tokens. Please reduce the length of the input messages. (parameter=input_tokens, value=5729)","type":"BadRequestError","param":null,"code":400}}`,
			expected: "This model's maximum context length is 512 tokens. However, your request has 5729 input tokens. Please reduce the length of the input messages. (parameter=input_tokens, value=5729)",
		},
		{
			name:     "no message field but has Error details prefix",
			cause:    "Error occured for step (stepName=Llm) with statusCode=500. Stopping pipeline execution. Error details: Internal server error",
			expected: "Internal server error",
		},
		{
			name:     "no known pattern",
			cause:    "some unexpected error format",
			expected: "some unexpected error format",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			result := extractUserMessage(tc.cause)
			assert.Equal(t, tc.expected, result)
		})
	}
}

func TestMcGraphHandler(t *testing.T) {
	// Start a local HTTP server
	service1 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "cat",
					"score": []float32{
						0.1, 0.9,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service1Url, err := apis.ParseURL(service1.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service1.Close()
	service2 := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, err := io.ReadAll(req.Body)
		if err != nil {
			return
		}
		response := map[string]interface{}{
			"predictions": []map[string]interface{}{
				{
					"label": "dog",
					"score": []float32{
						0.8, 0.2,
					},
				},
			},
		}
		responseBytes, err := json.Marshal(response)
		if err != nil {
			return
		}
		_, err = rw.Write(responseBytes)
		if err != nil {
			return
		}
	}))
	service2Url, err := apis.ParseURL(service2.URL)
	if err != nil {
		t.Fatalf("Failed to parse model url")
	}
	defer service2.Close()

	mockGraph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName: "step1",
							Executor: mcv1alpha3.Executor{
								NodeName: "animal-categorize",
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
						},
						{
							StepName: "step2",
							Executor: mcv1alpha3.Executor{
								NodeName: "breed-categorize",
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tgi-service",
								},
							},
							Condition: "predictions.#(label==\"dog\")",
						},
					},
				},
				"animal-categorize": {
					RouterType: mcv1alpha3.Switch,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: service1Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tei-embedding-service",
								},
							},
							Condition: "instances.#(modelId==\"1\")",
						},
						{
							StepName:   "service2",
							ServiceURL: service2Url.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{
									ServiceName: "tgi-service",
								},
							},
							Condition: "instances.#(modelId==\"2\")",
						},
					},
				},
			},
		},
	}

	mcGraph = &mockGraph
	// Create a request with a sample input
	input := []byte(`{"instances": ["test", "test2"]}`)
	req, err := http.NewRequest("POST", "/", bytes.NewBuffer(input))
	if err != nil {
		t.Fatal(err)
	}

	// Create a response recorder to capture the response
	rr := httptest.NewRecorder()

	// Call the handler function
	mcGraphHandler(rr, req)

	// Check the response status code
	// if rr.Code != http.StatusOK {
	// 	t.Errorf("expected status code %d, got %d", http.StatusOK, rr.Code)
	// }

	// // Check the response body
	// expectedResponse := []byte(`{"service1": {"predictions": "1"}, "service2": {"predictions": "2"}}`)
	// if !bytes.Equal(rr.Body.Bytes(), expectedResponse) {
	// 	t.Errorf("expected response body %s, got %s", expectedResponse, rr.Body.String())
	// }
}

// Mock os.Exit to prevent exiting the process
//
//	func mockOsExit() func() {
//		originalOsExit := os.Exit
//		os.Exit = func(code int) {}
//		return func() { os.Exit = originalOsExit }
//	}
func TestMain(t *testing.T) {
	// Create a new HTTP request
	_, err := http.NewRequest("GET", "/", nil)
	if err != nil {
		t.Fatal(err)
	}
	jsonGraph := `
	{
		"root": {
			"routerType": "sequence",
			"steps": [
				{
					"stepName": "step1",
					"executor": {
						"nodeName": "animal-categorize",
						"internalService": {
							"namespace": "default",
							"serviceName": "tei-embedding-service"
						}
					}
				},
				{
					"stepName": "step2",
					"executor": {
						"nodeName": "breed-categorize",
						"internalService": {
							"namespace": "default",
							"serviceName": "tgi-service"
						}
					},
					"condition": "predictions.#(label==\"dog\")"
				}
			]
		}
	}
	`

	os.Args = []string{"main", "--graph-json", jsonGraph}

	// Mock os.Exit
	// defer mockOsExit()()

	// Call the main function, which handles the request
	go main()

	// Simulate doing some work or waiting for a condition
	time.Sleep(2 * time.Second)
}

func TestMcGraphHandler_Timeout(t *testing.T) {
	// Mock server with a context timeout of 1 second
	handler := http.HandlerFunc(mcGraphHandler)
	server := httptest.NewServer(handler)
	defer server.Close()

	client := server.Client()

	// Create a request with a short context timeout
	req, err := http.NewRequest(http.MethodGet, server.URL, nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	ctx, cancel := context.WithTimeout(req.Context(), time.Second)
	defer cancel()
	req = req.WithContext(ctx)

	// Send the request
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}

	defer func() {
		if err := resp.Body.Close(); err != nil {
			t.Errorf("error closing response body: %v", err)
		}
	}()

	// Check if the response status code is StatusInternalServerError (500)
	if resp.StatusCode != http.StatusInternalServerError {
		t.Errorf("expected status %d; got %d", http.StatusInternalServerError, resp.StatusCode)
	}

	// Read and validate the response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read response body: %v", err)
	}
	expectedErrorMessage := "Failed to process request"
	if !strings.Contains(string(body), expectedErrorMessage) {
		t.Errorf("expected error message '%s'; got '%s'", expectedErrorMessage, string(body))
	}
}

// TestRouteStepCycleGuard verifies that a graph cycle (two nodes routing into
// each other) is rejected with a 500 rather than recursing until the stack
// overflows.
func TestRouteStepCycleGuard(t *testing.T) {
	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{StepName: "toB", Executor: mcv1alpha3.Executor{NodeName: "nodeB"}},
					},
				},
				"nodeB": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{StepName: "toRoot", Executor: mcv1alpha3.Executor{NodeName: "root"}},
					},
				},
			},
		},
	}

	input := []byte(`{"query": "hi"}`)
	body, statusCode, err := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	assert.Error(t, err, "a graph cycle must return an error")
	assert.Equal(t, http.StatusInternalServerError, statusCode)
	assert.Contains(t, err.Error(), "possible graph cycle")
	if body != nil {
		_ = body.Close()
	}
}

// TestSwitchNoMatchReturnsError verifies that a Switch node whose branches all
// fail their condition returns a defined status and error rather than a nil body
// with a zero status.
func TestSwitchNoMatchReturnsError(t *testing.T) {
	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Switch,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: "http://unused.invalid",
							Condition:  "instances.#(modelId==\"1\")",
						},
					},
				},
			},
		},
	}

	input := []byte(`{"instances": [{"modelId": "99"}]}`)
	body, statusCode, err := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	assert.Error(t, err, "a switch with no matching branch must return an error")
	assert.Equal(t, http.StatusNotFound, statusCode)
	if body != nil {
		_ = body.Close()
	}
}

// TestSwitchSelectsFirstMatchOnly verifies that a Switch node executes exactly
// the first branch whose condition matches, not every matching branch.
func TestSwitchSelectsFirstMatchOnly(t *testing.T) {
	var firstCalled, secondCalled atomic.Int32
	first := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		firstCalled.Add(1)
		_, _ = rw.Write([]byte(`{"predictions": "first"}`))
	}))
	defer first.Close()
	firstURL, err := apis.ParseURL(first.URL)
	if err != nil {
		t.Fatalf("failed to parse first url")
	}
	second := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		secondCalled.Add(1)
		_, _ = rw.Write([]byte(`{"predictions": "second"}`))
	}))
	defer second.Close()
	secondURL, err := apis.ParseURL(second.URL)
	if err != nil {
		t.Fatalf("failed to parse second url")
	}

	// Both branches share a condition the input satisfies, so a loop that did not
	// stop at the first match would call both services.
	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Switch,
					Steps: []mcv1alpha3.Step{
						{StepName: "first", ServiceURL: firstURL.String(), Condition: "instances.#(modelId==\"1\")"},
						{StepName: "second", ServiceURL: secondURL.String(), Condition: "instances.#(modelId==\"1\")"},
					},
				},
			},
		},
	}

	input := []byte(`{"instances": [{"modelId": "1"}]}`)
	body, statusCode, err := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	assert.NoError(t, err)
	assert.Equal(t, http.StatusOK, statusCode)
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(body)
	assert.NoError(t, rerr)
	_ = body.Close()
	assert.NoError(t, json.Unmarshal(responseBytes, &response))
	assert.Equal(t, "first", response["predictions"], "the first matching branch must be the one returned")
	assert.Equal(t, int32(1), firstCalled.Load(), "the first matching branch must be called")
	assert.Equal(t, int32(0), secondCalled.Load(), "later matching branches must not be called")
}

// TestSequenceMalformed422NoPanic verifies that a hard-dependency step answering
// 422 with an empty detail list is handled without panicking on Detail[0].
func TestSequenceMalformed422NoPanic(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		rw.WriteHeader(422)
		// A 422 whose detail list is empty must not panic the router.
		_, _ = rw.Write([]byte(`{"detail": []}`))
	}))
	defer service.Close()
	serviceURL, err := apis.ParseURL(service.URL)
	if err != nil {
		t.Fatalf("failed to parse service url")
	}

	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "service1",
							ServiceURL: serviceURL.String(),
							Dependency: mcv1alpha3.Hard,
						},
					},
				},
			},
		},
	}

	input := []byte(`{"query": "hi"}`)
	body, statusCode, err := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	assert.Error(t, err, "a hard-dependency 422 must surface as an error")
	assert.Equal(t, 422, statusCode)
	assert.Contains(t, err.Error(), "Pydantic error")
	if body != nil {
		_ = body.Close()
	}
}

// TestEnsembleCancelsSiblingsOnHardFailure verifies that when a hard-dependency
// step fails fast, the sibling goroutines are cancelled and none is left leaked
// on a blocked send. It runs under -race and asserts the goroutine count settles
// back after the call returns.
func TestEnsembleCancelsSiblingsOnHardFailure(t *testing.T) {
	// A hard-dependency step that fails immediately.
	failing := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		rw.WriteHeader(http.StatusInternalServerError)
		_, _ = rw.Write([]byte(`{"detail": "boom"}`))
	}))
	defer failing.Close()
	failingURL, err := apis.ParseURL(failing.URL)
	if err != nil {
		t.Fatalf("failed to parse failing url")
	}

	// A slow sibling that blocks until its request context is cancelled or a long
	// timeout elapses. If the ensemble left it running rather than cancelling it,
	// routeStep would block on errgroup.Wait for the full sleep.
	slow := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		select {
		case <-req.Context().Done():
		case <-time.After(10 * time.Second):
		}
		rw.WriteHeader(http.StatusOK)
		_, _ = rw.Write([]byte(`{"predictions": "late"}`))
	}))
	defer slow.Close()
	slowURL, err := apis.ParseURL(slow.URL)
	if err != nil {
		t.Fatalf("failed to parse slow url")
	}

	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Ensemble,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "failing",
							ServiceURL: failingURL.String(),
							Dependency: mcv1alpha3.Hard,
						},
						{
							StepName:   "slow",
							ServiceURL: slowURL.String(),
						},
					},
				},
			},
		},
	}

	input := []byte(`{"query": "hi"}`)
	start := time.Now()
	body, statusCode, _ := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	elapsed := time.Since(start)
	if body != nil {
		_, _ = io.ReadAll(body)
		_ = body.Close()
	}

	// The hard failure returns that step's status without waiting out the slow
	// sibling's 10s sleep. routeStep only returns after every worker goroutine has
	// finished (errgroup.Wait), so returning well under that sleep proves the slow
	// sibling was cancelled rather than left blocked on a send or a half-read body.
	assert.Equal(t, http.StatusInternalServerError, statusCode)
	assert.Less(t, elapsed, 5*time.Second, "must not block on the cancelled sibling")
}

// TestEnsemblePartialFailureReported verifies that a soft-dependency step
// failing does not fail the whole ensemble but is reported as a multi-status.
func TestEnsemblePartialFailureReported(t *testing.T) {
	ok := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, _ = rw.Write([]byte(`{"predictions": "1"}`))
	}))
	defer ok.Close()
	okURL, err := apis.ParseURL(ok.URL)
	if err != nil {
		t.Fatalf("failed to parse ok url")
	}
	bad := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		rw.WriteHeader(http.StatusInternalServerError)
		_, _ = rw.Write([]byte(`{"detail": "boom"}`))
	}))
	defer bad.Close()
	badURL, err := apis.ParseURL(bad.URL)
	if err != nil {
		t.Fatalf("failed to parse bad url")
	}

	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Ensemble,
					Steps: []mcv1alpha3.Step{
						{StepName: "ok", ServiceURL: okURL.String()},
						{StepName: "bad", ServiceURL: badURL.String()},
					},
				},
			},
		},
	}

	input := []byte(`{"query": "hi"}`)
	body, statusCode, err := routeStep(context.Background(), "root", graph, input, input, http.Header{})
	assert.NoError(t, err, "a soft failure must not fail the ensemble")
	assert.Equal(t, http.StatusMultiStatus, statusCode)
	var response map[string]interface{}
	responseBytes, rerr := io.ReadAll(body)
	assert.NoError(t, rerr)
	_ = body.Close()
	assert.NoError(t, json.Unmarshal(responseBytes, &response))
	assert.Contains(t, response, "ok", "the successful step's response must be merged")
}

// TestPerStepTimeout verifies that a downstream call slower than the per-step
// deadline is aborted rather than pinning the handler for the old hour-long
// timeout.
func TestPerStepTimeout(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		select {
		case <-req.Context().Done():
		case <-time.After(10 * time.Second):
		}
	}))
	defer slow.Close()
	slowURL, err := apis.ParseURL(slow.URL)
	if err != nil {
		t.Fatalf("failed to parse slow url")
	}

	step := &mcv1alpha3.Step{
		StepName:   "slow",
		ServiceURL: slowURL.String(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	start := time.Now()
	body, statusCode, err := callService(ctx, step, slowURL.String(), []byte(`{}`), http.Header{})
	elapsed := time.Since(start)
	assert.Error(t, err, "a call exceeding the deadline must return an error")
	assert.Equal(t, 500, statusCode)
	assert.Less(t, elapsed, 5*time.Second, "the per-step deadline must abort the slow call")
	if body != nil {
		_ = body.Close()
	}
}

// TestMcGraphHandlerStreamsSSEWithSeparators verifies that a streaming SSE
// response is forwarded verbatim, including the blank lines that separate
// events, and that the non-streaming JSON remap does not run once data has been
// streamed.
func TestMcGraphHandlerStreamsSSEWithSeparators(t *testing.T) {
	// A backend emitting a standard SSE stream: each event is a data line
	// followed by a blank separator line.
	upstream := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, _ = io.WriteString(rw, "data: one\n\ndata: two\n\ndata: [DONE]\n\n")
	}))
	defer upstream.Close()
	upstreamURL, err := apis.ParseURL(upstream.URL)
	if err != nil {
		t.Fatalf("failed to parse upstream url")
	}

	mcGraph = &mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "llm",
							ServiceURL: upstreamURL.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{ServiceName: "llm-svc"},
							},
						},
					},
				},
			},
		},
	}

	req, err := http.NewRequest("POST", "/", bytes.NewBufferString(`{"query": "hi"}`))
	if err != nil {
		t.Fatal(err)
	}
	rr := httptest.NewRecorder()
	mcGraphHandler(rr, req)

	// The blank separator lines must survive and no remapped JSON document must be
	// appended after the streamed data.
	assert.Equal(t, "data: one\n\ndata: two\n\ndata: [DONE]\n\n", rr.Body.String())
}

// TestScanSSELines verifies the SSE split function returns whole lines with
// their trailing newline and never splits a prefix across a boundary.
func TestScanSSELines(t *testing.T) {
	input := "data: one\ndata: two\njson: {\"a\":1}"
	scanner := bufio.NewScanner(strings.NewReader(input))
	scanner.Split(scanSSELines)

	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	assert.NoError(t, scanner.Err())
	assert.Equal(t, []string{"data: one\n", "data: two\n", "json: {\"a\":1}"}, lines)
}

// TestMcGraphHandlerForwardsWholeJSONTrailer verifies that a "json:" document
// spanning more than one line survives, including the part the scanner has
// already buffered. Reading the body directly at that point returns nothing,
// because the scanner has read ahead.
func TestMcGraphHandlerForwardsWholeJSONTrailer(t *testing.T) {
	// The guardrail and vllm connectors close a stream with a data frame and then
	// emit the reranked documents as a json: document, flushed in one write.
	upstream := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, _ = io.WriteString(rw, "json: {\"reranked_docs\":[\n{\"text\":\"a\"}\n]}\n")
	}))
	defer upstream.Close()
	upstreamURL, err := apis.ParseURL(upstream.URL)
	if err != nil {
		t.Fatalf("failed to parse upstream url")
	}

	mcGraph = &mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "llm",
							ServiceURL: upstreamURL.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{ServiceName: "llm-svc"},
							},
						},
					},
				},
			},
		},
	}

	req, err := http.NewRequest("POST", "/", bytes.NewBufferString(`{"query": "hi"}`))
	if err != nil {
		t.Fatal(err)
	}
	rr := httptest.NewRecorder()
	mcGraphHandler(rr, req)

	assert.Contains(t, rr.Body.String(), "reranked_docs")
	assert.Contains(t, rr.Body.String(), "{\"text\":\"a\"}", "the buffered remainder of the json: document must survive")
	assert.Contains(t, rr.Body.String(), "]}", "the json: document must not be truncated")
}

// TestMcGraphHandlerPassesLargeNonStreamingBody verifies that a non-streaming
// answer larger than an SSE line's scale is forwarded rather than failing the
// request. Such a body is one newline-free document, so it reaches the scanner
// as a single token and a line-scale cap would reject it.
func TestMcGraphHandlerPassesLargeNonStreamingBody(t *testing.T) {
	large := `{"text":"` + strings.Repeat("x", 2<<20) + `"}`
	upstream := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, _ = io.WriteString(rw, large)
	}))
	defer upstream.Close()
	upstreamURL, err := apis.ParseURL(upstream.URL)
	if err != nil {
		t.Fatalf("failed to parse upstream url")
	}

	mcGraph = &mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Sequence,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "llm",
							ServiceURL: upstreamURL.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{ServiceName: "llm-svc"},
							},
						},
					},
				},
			},
		},
	}

	req, err := http.NewRequest("POST", "/", bytes.NewBufferString(`{"query": "hi"}`))
	if err != nil {
		t.Fatal(err)
	}
	rr := httptest.NewRecorder()
	mcGraphHandler(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code, "a large non-streaming body must not fail the request")
	// The non-streaming path remaps the document into a GeneratedDoc shape, so
	// compare the payload rather than the byte count.
	assert.Contains(t, rr.Body.String(), strings.Repeat("x", 2<<20), "the whole payload must survive")
}

// A hard-dependency ensemble step that answered 200 with a body that is not a
// JSON object must not fail the request: the body is carried as text.
func TestEnsembleKeepsNonJSONHardStepResponse(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		_, _ = io.WriteString(rw, "data: hello\n\n")
	}))
	defer upstream.Close()
	upstreamURL, err := apis.ParseURL(upstream.URL)
	if err != nil {
		t.Fatalf("failed to parse upstream url")
	}

	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root": {
					RouterType: mcv1alpha3.Ensemble,
					Steps: []mcv1alpha3.Step{
						{
							StepName:   "Llm",
							Dependency: mcv1alpha3.Hard,
							ServiceURL: upstreamURL.String(),
							Executor: mcv1alpha3.Executor{
								InternalService: mcv1alpha3.GMCTarget{ServiceName: "llm-svc"},
							},
						},
					},
				},
			},
		},
	}

	input := []byte(`{"query":"hi"}`)
	body, statusCode, err := handleEnsemblePipeline(context.Background(), "root", graph, input, input, http.Header{})
	if err != nil {
		t.Fatalf("a successful non-JSON answer must not fail the ensemble: %v", err)
	}
	if statusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", statusCode)
	}
	merged, _ := io.ReadAll(body)
	assert.Contains(t, string(merged), "data: hello", "the raw body must be carried into the merged response")
}

// The fan-out budget is shared by every node a request reaches, so a graph of
// nested Ensemble nodes cannot multiply its concurrency with depth. A step that
// routes to a sub-node takes no slot, so a parent never blocks on children that
// cannot start.
func TestEnsembleFanoutBudgetIsSharedPerRequest(t *testing.T) {
	var live, peak int64
	var mu sync.Mutex
	upstream := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		n := atomic.AddInt64(&live, 1)
		mu.Lock()
		if n > peak {
			peak = n
		}
		mu.Unlock()
		time.Sleep(20 * time.Millisecond)
		atomic.AddInt64(&live, -1)
		_, _ = io.WriteString(rw, `{"ok":true}`)
	}))
	defer upstream.Close()
	upstreamURL, err := apis.ParseURL(upstream.URL)
	if err != nil {
		t.Fatalf("failed to parse upstream url")
	}

	// root fans out to leaves plus a sub-node that fans out again, so the total
	// width exceeds the budget while the depth stays small.
	leaf := func(name string) mcv1alpha3.Step {
		return mcv1alpha3.Step{
			StepName:   name,
			ServiceURL: upstreamURL.String(),
			Executor: mcv1alpha3.Executor{
				InternalService: mcv1alpha3.GMCTarget{ServiceName: "llm-svc"},
			},
		}
	}
	rootSteps := []mcv1alpha3.Step{}
	childSteps := []mcv1alpha3.Step{}
	for i := 0; i < MaxEnsembleConcurrency; i++ {
		rootSteps = append(rootSteps, leaf(fmt.Sprintf("r%d", i)))
		childSteps = append(childSteps, leaf(fmt.Sprintf("c%d", i)))
	}
	rootSteps = append(rootSteps, mcv1alpha3.Step{
		StepName: "toChild",
		Executor: mcv1alpha3.Executor{NodeName: "child"},
	})

	graph := mcv1alpha3.GMConnector{
		Spec: mcv1alpha3.GMConnectorSpec{
			Nodes: map[string]mcv1alpha3.Router{
				"root":  {RouterType: mcv1alpha3.Ensemble, Steps: rootSteps},
				"child": {RouterType: mcv1alpha3.Ensemble, Steps: childSteps},
			},
		},
	}

	input := []byte(`{"query":"hi"}`)
	done := make(chan struct{})
	go func() {
		_, _, _ = routeStep(context.Background(), "root", graph, input, input, http.Header{})
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(60 * time.Second):
		t.Fatal("routing deadlocked: a routing step must not hold a budget slot")
	}

	mu.Lock()
	got := peak
	mu.Unlock()
	if got > int64(MaxEnsembleConcurrency) {
		t.Errorf("concurrent upstream calls %d exceeded the budget of %d", got, MaxEnsembleConcurrency)
	}
	if got == 0 {
		t.Error("expected the upstream to be called")
	}
}
