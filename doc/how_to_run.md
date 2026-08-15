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

**Run training:**
```bash
docker run restaurant-train python /app/src/train.py
```

The trained model artifacts are written to `/app/model` inside the container. To persist them on the host, mount a local directory:

```bash
docker run -v $(pwd)/model_output:/app/model restaurant-train python /app/src/train.py
```
