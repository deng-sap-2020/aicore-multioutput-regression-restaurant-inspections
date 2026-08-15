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

**Build:**
```bash
docker build -f src/train/Dockerfile -t restaurant-train .
```

**Run:**
```bash
docker run restaurant-train python /app/src/train.py
```

To persist model artifacts on the host:
```bash
docker run -v $(pwd)/model_output:/app/model restaurant-train python /app/src/train.py
```

**Tag and push to Docker Hub:**
```bash
docker tag restaurant-train zhoudeng2026/restaurant-train:latest
docker push zhoudeng2026/restaurant-train:latest
```

---

## Serving (Docker)

All commands must be run from the **`src/serve/` directory**.

**Build:**
```bash
docker build -t restaurant-serve src/serve/
```

**Run locally** (mount a trained model from `model_output/`):
```bash
docker run -p 9001:9001 \
  -e STORAGE_URI=/app/model \
  -v $(pwd)/model_output:/app/model \
  restaurant-serve
```

Test the endpoint:
```bash
curl -X POST http://localhost:9001/v1/models/restaurant-inspections:predict \
  -H "Content-Type: application/json" \
  -d @data/test_payload.json
```

**Tag and push to Docker Hub:**
```bash
docker tag restaurant-serve zhoudeng2026/restaurant-serve:latest
docker push zhoudeng2026/restaurant-serve:latest
```

---

## Deploy to SAP BTP AI Core

### Prerequisites

1. Push both Docker images to Docker Hub (see above).
2. Commit and push `workflows/train.yaml` and `workflows/serve.yaml` to GitHub.
3. Upload training data to S3:
   ```bash
   python store_training_data_2_s3.py
   ```

### Full run (train + deploy)

```bash
python ai_core_prep.py
```

### Serve only (skip training, use existing model artifact)

```bash
python ai_core_prep.py --serve-only <MODEL_ARTIFACT_ID>
```

To find the latest model artifact ID:
```bash
python - <<'EOF'
from dotenv import load_dotenv; from os import environ
import json, urllib.request, urllib.parse, base64
load_dotenv("local.env")
data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
creds = base64.b64encode(f"{environ['BTP_CLIENT_ID']}:{environ['BTP_CLIENT_SECRET']}".encode()).decode()
req = urllib.request.Request(environ["BTP_TOKEN_URL"], data=data,
    headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req) as r: token = json.load(r)["access_token"]
req = urllib.request.Request(f"{environ['BTP_AI_API_URL']}/v2/lm/artifacts?kind=model",
    headers={"Authorization": f"Bearer {token}", "AI-Resource-Group": environ["AICORE_RESOURCE_GROUP"]})
with urllib.request.urlopen(req) as r:
    [print(f"{a['id']}  {a['name']}  {a['createdAt']}") for a in json.load(r).get("resources",[])]
EOF
```

### Skip admin setup (secrets/resource group already configured)

```bash
python ai_core_prep.py --serve-only <MODEL_ARTIFACT_ID> --skip-admin
```

The deployment URL is shown in the logs and available in AI Launchpad under **ML Operations → Deployments**.
