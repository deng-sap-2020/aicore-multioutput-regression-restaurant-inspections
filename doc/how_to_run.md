# How to Run

## Training (Local)

All commands must be run from the **project root**.

**1. Install dependencies (once):**
```bash
pip install -r src/train/requirements.txt
```

**2. Add the following to `local.env`:**
```
DATA_SOURCE=data
OUTPUT_PATH=model_output
```

**3. Run training:**
```bash
python src/train/train.py
```

`local.env` is loaded automatically. Trained model artifacts are written to `model_output/`.

---

## Training (Docker)

All commands must be run from the **project root**.

**Build the image:**
```bash
docker build -f src/train/Dockerfile -t restaurant-train .
```

docker tag restaurant-train zhoudeng2026/restaurant-train:latest


docker push zhoudeng2026/restaurant-train:latest    


python .\ai_core_prep.py      


**Run training:**
```bash
docker run restaurant-train python /app/src/train.py
```

The trained model artifacts are written to `/app/model` inside the container. To persist them on the host, mount a local directory:

```bash
docker run -v $(pwd)/model_output:/app/model restaurant-train python /app/src/train.py
```

---

## Deploy to SAP BTP AI Core

All steps use credentials from `local.env`. Set these shell variables first:

```bash
source local.env   # or: export $(grep -v '^#' local.env | xargs)
```

### 1. Update the workflow with your Docker image

Edit `workflows/train.yaml` and `workflows/serve.yaml` — replace the `<DOCKER-IMAGE-*>` placeholders with your pushed image:

```
image: zhoudeng2026/restaurant-train:latest   # in train.yaml
image: zhoudeng2026/restaurant-serve:latest   # in serve.yaml
```

Then commit and push both files to GitHub. AI Core syncs workflows from the repo automatically.

### 2. Get an OAuth token

```bash
TOKEN=$(curl -s -X POST "$BTP_TOKEN_URL" \
  -u "$BTP_CLIENT_ID:$BTP_CLIENT_SECRET" \
  -d "grant_type=client_credentials" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### 3. Register the Docker registry secret (once)

```bash
curl -X POST "$BTP_AI_API_URL/v2/admin/secrets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "docker-registry-secret",
    "type": "container-registry",
    "data": {
      "server": "https://index.docker.io/v1/",
      "username": "'"$DOCKER_HUB_USER"'",
      "password": "'"$DOCKER_HUB_TOKEN"'"
    }
  }'
```

### 4. Register the training dataset artifact (S3)

```bash
curl -X POST "$BTP_AI_API_URL/v2/lm/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "inspections",
    "kind": "dataset",
    "url": "ai://default/inspections",
    "scenarioId": "inspection-mo-regression-scenario",
    "description": "Restaurant inspections dataset"
  }'
```

Note the returned `id` — use it as `ARTIFACT_ID` in the next step.

### 5. Create a training configuration

```bash
curl -X POST "$BTP_AI_API_URL/v2/lm/configurations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "inspection-train-config",
    "scenarioId": "inspection-mo-regression-scenario",
    "executableId": "inspection-mo-regression-train-0",
    "inputArtifactBindings": [
      { "key": "inspections", "artifactId": "<ARTIFACT_ID>" }
    ]
  }'
```

Note the returned `id` — use it as `CONFIG_ID` in the next step.

### 6. Start a training execution

```bash
curl -X POST "$BTP_AI_API_URL/v2/lm/executions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  -H "Content-Type: application/json" \
  -d '{ "configurationId": "<CONFIG_ID>" }'
```

### 7. Monitor execution status

```bash
curl "$BTP_AI_API_URL/v2/lm/executions/<EXECUTION_ID>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP"
```

Status will move through `PENDING → RUNNING → COMPLETED`. The trained model artifact is registered automatically on completion.

### 8. Create a serving deployment (after training completes)

Create a serving configuration referencing the model output artifact, then start a deployment:

```bash
curl -X POST "$BTP_AI_API_URL/v2/lm/deployments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  -H "Content-Type: application/json" \
  -d '{ "configurationId": "<SERVING_CONFIG_ID>" }'
```

The deployment URL is available in AI Launchpad under **ML Operations → Deployments** once status reaches `RUNNING`.

**1. Log in:**
```bash
docker login -u zhoudeng2026
```

**2. Tag the image:**
```bash
docker tag restaurant-train zhoudeng2026/restaurant-train:latest
```

**3. Push:**
```bash
docker push zhoudeng2026/restaurant-train:latest
```
