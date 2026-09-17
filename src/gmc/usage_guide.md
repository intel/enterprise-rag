# Usage guide for genai-microservices-connector(GMC)

genai-microservices-connector(GMC) can be used to compose and adjust GenAI pipelines dynamically. It can leverage the microservices provided
by [GenAIComps](https://github.com/opea-project/GenAIComps) and external services to compose GenAI pipelines.

Below are sample use cases:

## Use GMC to compose a chatQnA Pipeline

The GMConnector resource is not hand-written. It is composed from
[deployment/pipelines/chatqna/pipeline.yaml](../../deployment/pipelines/chatqna/pipeline.yaml)
by `deployment/scripts/compose_pipeline.py`, which the `app_pipeline` role runs during
`install erag`. The rendered resource is written to
`env/<name>/logs/rag/gmconnector-chatqna.yaml` in the core installer's environment
directory.

**Deploy chatQnA GMC custom resource**

To apply a composed resource by hand, for example after editing it:

```sh
kubectl create ns chatqna
kubectl apply -f env/<name>/logs/rag/gmconnector-chatqna.yaml
```

**GMC will reconcile chatQnA custom resource and get all related components/services ready**

```sh
kubectl get service -n chatqna
```

**Check GMC chatQnA custom resource to get access URL for the pipeline**

```bash
$kubectl get gmconnectors.gmc.erag.intel.com -n chatqna
NAME     URL                                                      READY     AGE
chatqna   http://router-service.chatqna.svc.cluster.local:8080      8/0/8     3m
```

**Deploy one client pod for testing the chatQnA application**

```bash
kubectl create deployment client-test -n chatqna --image=python:3.8.13 -- sleep infinity
```

**Access the pipeline using the above URL from the client pod**

```bash
export CLIENT_POD=$(kubectl get pod -A -l app=client-test -o jsonpath={.items..metadata.name})
export accessUrl=$(kubectl get gmc -n chatqna -o jsonpath="{.items[?(@.metadata.name=='chatqna')].status.accessUrl}")
kubectl exec "$CLIENT_POD" -n chatqna -- curl --no-buffer -s $accessUrl  -X POST  -d '{"text":"What is the revenue of Nike in 2023?","parameters":{"max_new_tokens":17, "do_sample": true, "streaming":true }}' -H 'Content-Type: application/json'
```

## Use GMC to adjust the chatQnA Pipeline

**Modify chatQnA custom resource to change to another LLM model**

```yaml
- name: Tgi
  internalService:
    serviceName: tgi-svc
    config:
      LLM_MODEL_ID: Llama-2-7b-chat-hf
```

**Check the tgi-svc-deployment has been changed to use the new LLM Model**

```sh
kubectl get deployment tgi-svc-deployment -n chatqna -o jsonpath="{.spec.template.spec.containers[*].env[?(@.name=='LLM_MODEL_ID')].value}"
```

**Access the updated pipeline using the above URL from the client pod**

```bash
kubectl exec "$CLIENT_POD" -n chatqna -- curl $accessUrl  -X POST  -d '{"text":"What is the revenue of Nike in 2023?","parameters":{"max_new_tokens":17, "do_sample": true}}' -H 'Content-Type: application/json'
```

## Use GMC and Istio to compose a GenAI pipeline with authentication and authorization enabled

The critical steps of authentication and authorization are vital to maintaining the integrity and safety of our GenAI workload.
