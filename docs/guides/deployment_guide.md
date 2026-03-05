# CATERYA Enterprise — Deployment Guide

**Author:** Ary HH — CATERYA Tech

---

## Option 1: Local Development (5 minutes)

```bash
# Prerequisites: Docker Desktop, Python 3.11+
git clone https://github.com/cateryatech/caterya-enterprise
cd caterya-enterprise
cp .env.example .env

# Generate required keys
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print('BACKUP_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Add the above output to .env, then:
docker-compose up -d

# Pull Ollama model (first time only, ~4GB)
docker exec caterya_ollama ollama pull llama3

# Verify
curl http://localhost:8000/health
open http://localhost:8501   # Dashboard
open http://localhost:3000   # Grafana (admin / your GRAFANA_PASSWORD)
```

---

## Option 2: Standalone Python (No Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/caterya"
export REDIS_URL="redis://localhost:6379/0"
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export OLLAMA_BASE_URL="http://localhost:11434"

# Run database migrations
python -c "from migrations.init import run_migrations; run_migrations()"

# Start API
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Start dashboard (new terminal)
streamlit run dashboard/app.py --server.port 8501
```

---

## Option 3: Kubernetes (Production)

### Prerequisites
- kubectl configured
- Container registry access (ghcr.io)
- cert-manager installed for TLS

```bash
# 1. Create namespace and secrets
kubectl apply -f deploy/kubernetes/base/deployment.yaml

# 2. Create secrets (never commit to git)
kubectl create secret generic caterya-secrets \
  --from-literal=DATABASE_URL="postgresql://..." \
  --from-literal=REDIS_URL="redis://..." \
  --from-literal=JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --namespace caterya

# 3. Deploy
kubectl apply -f deploy/kubernetes/base/deployment.yaml

# 4. Verify
kubectl get pods -n caterya
kubectl get hpa -n caterya

# 5. Check logs
kubectl logs -n caterya deployment/caterya-api -f
```

### Auto-scaling
The HPA scales `caterya-api` from 2 to 20 replicas based on:
- CPU > 70% → scale up (max 4 pods per minute)
- CPU < 70% for 5 minutes → scale down (max 2 pods per minute)

### QuantumFairnessEvaluator for scaling decisions
```python
from src.caterya.quantum.fairness_evaluator import QuantumFairnessEvaluator
qfe = QuantumFairnessEvaluator()
result = qfe.evaluate({
    "action": "scale_up",
    "tenant_id": "acme",
    "all_tenants_metrics": {"acme": {"cpu_usage_pct": 85}},
})
assert result.passed, "Scaling decision is unfair!"
```

---

## Option 4: Vercel (Next.js Frontend PWA)

The frontend can be deployed as a PWA to Vercel. The backend (FastAPI) stays on your server or Kubernetes.

### Step 1: Create Next.js wrapper
```bash
npx create-next-app@latest caterya-pwa --typescript --tailwind --app
cd caterya-pwa
```

### Step 2: Configure environment
```bash
# .env.local
NEXT_PUBLIC_API_URL=https://api.caterya.tech
NEXTAUTH_SECRET=your-nextauth-secret
NEXTAUTH_URL=https://app.caterya.tech
```

### Step 3: Add PWA manifest
```json
// public/manifest.json
{
  "name": "CATERYA Enterprise",
  "short_name": "CATERYA",
  "theme_color": "#1a1a2e",
  "background_color": "#ffffff",
  "display": "standalone",
  "start_url": "/",
  "icons": [
    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

### Step 4: Deploy to Vercel
```bash
npm install -g vercel
vercel --prod

# Environment variables in Vercel dashboard:
# NEXT_PUBLIC_API_URL = https://api.caterya.tech
# NEXTAUTH_SECRET     = <secret>
```

### Step 5: Configure API for CORS
```python
# api/main.py — add your Vercel domain
app.add_middleware(CORSMiddleware,
    allow_origins=["https://caterya-pwa.vercel.app", "https://app.caterya.tech"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Option 5: Netlify (Static Frontend)

```bash
# Build static export
cd caterya-pwa
echo 'output: "export"' >> next.config.js
npm run build

# Deploy
npm install -g netlify-cli
netlify deploy --prod --dir=out

# netlify.toml
[[redirects]]
  from = "/api/*"
  to = "https://api.caterya.tech/api/:splat"
  status = 200
  force = true
```

---

## Option 6: AWS Lambda (Serverless Fallback)

```bash
cd deploy/lambda
pip install -r requirements-lambda.txt -t .
zip -r lambda.zip . -x "*.pyc" -x "__pycache__/*"

aws lambda create-function \
  --function-name caterya-agent-executor \
  --runtime python3.11 \
  --handler lambda_handler.lambda_handler \
  --zip-file fileb://lambda.zip \
  --role arn:aws:iam::ACCOUNT_ID:role/caterya-lambda \
  --timeout 300 \
  --memory-size 2048 \
  --environment Variables="{
    GROQ_API_KEY=your_key,
    DATABASE_URL=postgresql://...,
    REDIS_URL=redis://...
  }"
```

---

## Monitoring Setup

```bash
# Grafana at http://localhost:3000
# Default: admin / your GRAFANA_PASSWORD from .env
# Dashboards auto-provisioned from monitoring/grafana/dashboards/

# Set up Alertmanager email:
SMTP_HOST=smtp.gmail.com
SMTP_USER=your@gmail.com
SMTP_PASSWORD=app-specific-password  # Not your main password

# View alerts:
open http://localhost:9093

# Silence an alert (e.g. during maintenance):
curl -X POST http://localhost:9093/api/v2/silences \
  -H "Content-Type: application/json" \
  -d '{"matchers":[{"name":"alertname","value":"HighAPILatency","isRegex":false}],"startsAt":"now","endsAt":"now+2h","comment":"Planned maintenance"}'
```

---

## SSL/TLS with Let's Encrypt

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: cateryatech@proton.me
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

---

## Backup Verification

```bash
# Verify encryption key works
python -c "
from backup.backup_manager import BackupManager
import json

manager = BackupManager()
test_records = [{'record_id': 'test', 'data': 'hello', 'tenant_id': 'test'}]
manifest = manager.backup_provenance('test', test_records)
print('SHA256:', manifest.sha256[:16])
print('Size:', manifest.size_bytes, 'bytes')
"
```
