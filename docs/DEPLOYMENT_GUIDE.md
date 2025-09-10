# MAS Production Deployment Guide

A comprehensive guide for deploying the MAS (Multi-Agent System) to production environments.

## 🎯 Overview

This guide covers everything needed to deploy MAS in production, from containerization to monitoring and scaling strategies.

### Production Architecture

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Nginx/HAProxy]
    end
    
    subgraph "Application Layer"
        API1[FastAPI Instance 1]
        API2[FastAPI Instance 2]
        API3[FastAPI Instance N]
        MCP[FastMCP Server]
    end
    
    subgraph "Data Layer"
        DB[(PostgreSQL)]
        REDIS[(Redis Cache)]
        LOGS[Log Storage]
    end
    
    subgraph "External Services"
        GEMINI[Google Gemini API]
        TAVILY[Tavily Search]
        BACKEND[EMIS Backend]
    end
    
    subgraph "Monitoring"
        PROM[Prometheus]
        GRAF[Grafana]
        ALERT[AlertManager]
    end
    
    LB --> API1
    LB --> API2
    LB --> API3
    API1 --> MCP
    API2 --> MCP
    API3 --> MCP
    API1 --> DB
    API1 --> REDIS
    API1 --> GEMINI
    API1 --> TAVILY
    MCP --> BACKEND
    API1 --> PROM
    PROM --> GRAF
    PROM --> ALERT
```

## 🐳 Containerization

### Dockerfile

Create a production-ready Dockerfile:

```dockerfile
FROM python:3.13-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

FROM python:3.13-slim as runtime

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "streaming_api.py"]
```

### Docker Compose for Production

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - mas-api
    restart: unless-stopped
    networks:
      - mas-network

  mas-api:
    build: .
    image: mas:latest
    deploy:
      replicas: 3
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
      - DATABASE_URL=postgresql://user:password@postgres:5432/mas_db
      - REDIS_URL=redis://redis:6379/0
      - LOG_LEVEL=INFO
      - ENVIRONMENT=production
    depends_on:
      - postgres
      - redis
      - mas-mcp
    restart: unless-stopped
    networks:
      - mas-network
    volumes:
      - ./logs:/app/logs

  mas-mcp:
    build: .
    image: mas:latest
    command: ["python", "my_mcp_server.py"]
    environment:
      - BACKEND_URL=${BACKEND_URL}
      - LOG_LEVEL=INFO
    ports:
      - "8001:8000"
    restart: unless-stopped
    networks:
      - mas-network

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=mas_db
      - POSTGRES_USER=mas_user
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped
    networks:
      - mas-network

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - mas-network

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
    restart: unless-stopped
    networks:
      - mas-network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    restart: unless-stopped
    networks:
      - mas-network

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:

networks:
  mas-network:
    driver: bridge
```

### Environment Configuration

Create `.env.production`:

```env
# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
WORKERS=4

# API Keys
GOOGLE_API_KEY=your_production_google_api_key
TAVILY_API_KEY=your_production_tavily_api_key
LANGCHAIN_API_KEY=your_production_langchain_api_key

# Database
DATABASE_URL=postgresql://mas_user:secure_password@postgres:5432/mas_db
REDIS_URL=redis://:secure_redis_password@redis:6379/0

# Security
SECRET_KEY=your_very_secure_secret_key_here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# External Services
BACKEND_URL=https://api.yourdomain.com
MCP_SERVER_URL=http://mas-mcp:8000/mcp

# Monitoring
PROMETHEUS_ENABLED=true
SENTRY_DSN=your_sentry_dsn_here

# Performance
MAX_CONCURRENT_SESSIONS=100
SESSION_TIMEOUT=3600
TOOL_EXECUTION_TIMEOUT=300
```

## ⚙️ Nginx Configuration

### nginx.conf

```nginx
events {
    worker_connections 1024;
}

http {
    upstream mas_backend {
        least_conn;
        server mas-api:8000 max_fails=3 fail_timeout=30s;
        server mas-api:8000 max_fails=3 fail_timeout=30s;
        server mas-api:8000 max_fails=3 fail_timeout=30s;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=chat:10m rate=5r/s;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com www.yourdomain.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;

        # API routes
        location /health {
            proxy_pass http://mas_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Chat streaming endpoint with special handling
        location /chat/stream {
            limit_req zone=chat burst=10 nodelay;
            
            proxy_pass http://mas_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # SSE-specific settings
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 24h;
        }

        # Other API endpoints
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            
            proxy_pass http://mas_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Static files (if any)
        location /static/ {
            alias /app/static/;
            expires 30d;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

## 🚀 Deployment Strategies

### Blue-Green Deployment

```bash
#!/bin/bash
# deploy.sh

set -e

DOCKER_IMAGE="mas:latest"
BLUE_COMPOSE="docker-compose.blue.yml"
GREEN_COMPOSE="docker-compose.green.yml"
CURRENT_ENV=$(docker-compose -f $BLUE_COMPOSE ps -q mas-api | wc -l)

echo "Starting deployment..."

if [ $CURRENT_ENV -gt 0 ]; then
    echo "Blue environment is active, deploying to green..."
    DEPLOY_COMPOSE=$GREEN_COMPOSE
    CURRENT_COMPOSE=$BLUE_COMPOSE
else
    echo "Green environment is active, deploying to blue..."
    DEPLOY_COMPOSE=$BLUE_COMPOSE
    CURRENT_COMPOSE=$GREEN_COMPOSE
fi

# Build new image
echo "Building new image..."
docker build -t $DOCKER_IMAGE .

# Deploy to inactive environment
echo "Deploying to inactive environment..."
docker-compose -f $DEPLOY_COMPOSE up -d

# Health check
echo "Performing health checks..."
for i in {1..30}; do
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        echo "Health check passed!"
        break
    fi
    echo "Waiting for service to be ready... ($i/30)"
    sleep 10
done

# Switch traffic
echo "Switching traffic..."
docker-compose -f $DEPLOY_COMPOSE up -d nginx

# Stop old environment
echo "Stopping old environment..."
docker-compose -f $CURRENT_COMPOSE down

echo "Deployment completed successfully!"
```

### Rolling Deployment

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mas-api
  labels:
    app: mas-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  selector:
    matchLabels:
      app: mas-api
  template:
    metadata:
      labels:
        app: mas-api
    spec:
      containers:
      - name: mas-api
        image: mas:latest
        ports:
        - containerPort: 8000
        env:
        - name: GOOGLE_API_KEY
          valueFrom:
            secretKeyRef:
              name: mas-secrets
              key: google-api-key
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

## 📊 Monitoring & Observability

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'mas-api'
    static_configs:
      - targets: ['mas-api:8000']
    metrics_path: /metrics
    scrape_interval: 5s

  - job_name: 'nginx'
    static_configs:
      - targets: ['nginx:9113']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### Application Metrics

Add metrics to your FastAPI app:

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

# Metrics
REQUEST_COUNT = Counter('mas_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('mas_request_duration_seconds', 'Request duration')
ACTIVE_SESSIONS = Gauge('mas_active_sessions', 'Number of active sessions')
TOOL_EXECUTION_COUNT = Counter('mas_tool_executions_total', 'Tool executions', ['tool_name', 'status'])
TOOL_EXECUTION_DURATION = Histogram('mas_tool_execution_seconds', 'Tool execution duration', ['tool_name'])

class MetricsMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                duration = time.time() - start_time
                
                REQUEST_COUNT.labels(
                    method=scope["method"],
                    endpoint=scope["path"],
                    status=status_code
                ).inc()
                
                REQUEST_DURATION.observe(duration)
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)

# Add to FastAPI app
from fastapi import FastAPI
app = FastAPI()
app.add_middleware(MetricsMiddleware)

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "MAS Agent Dashboard",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(mas_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, mas_request_duration_seconds_bucket)",
            "legendFormat": "95th percentile"
          },
          {
            "expr": "histogram_quantile(0.50, mas_request_duration_seconds_bucket)",
            "legendFormat": "50th percentile"
          }
        ]
      },
      {
        "title": "Active Sessions",
        "type": "singlestat",
        "targets": [
          {
            "expr": "mas_active_sessions"
          }
        ]
      },
      {
        "title": "Tool Execution Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(mas_tool_executions_total[5m])",
            "legendFormat": "{{tool_name}}"
          }
        ]
      }
    ]
  }
}
```

## 🛡️ Security Hardening

### Application Security

```python
# security.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import hmac
import time

app = FastAPI()

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["yourdomain.com", "*.yourdomain.com"]
)

# CORS with strict origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Rate limiting
class RateLimitMiddleware:
    def __init__(self, app, calls: int = 100, period: int = 3600):
        self.app = app
        self.calls = calls
        self.period = period
        self.clients = {}
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        client_ip = scope.get("client", ["unknown"])[0]
        now = time.time()
        
        # Clean old entries
        self.clients = {
            ip: requests for ip, requests in self.clients.items()
            if any(req_time > now - self.period for req_time in requests)
        }
        
        # Check rate limit
        client_requests = self.clients.get(client_ip, [])
        recent_requests = [t for t in client_requests if t > now - self.period]
        
        if len(recent_requests) >= self.calls:
            response = {
                "type": "http.response.start",
                "status": 429,
                "headers": [[b"content-type", b"application/json"]],
            }
            await send(response)
            
            body = b'{"error": "Rate limit exceeded"}'
            await send({"type": "http.response.body", "body": body})
            return
        
        # Add current request
        recent_requests.append(now)
        self.clients[client_ip] = recent_requests
        
        await self.app(scope, receive, send)

# Add rate limiting
app.add_middleware(RateLimitMiddleware, calls=100, period=3600)
```

### Secret Management

```python
# secrets_manager.py
import os
from typing import Optional
import boto3
from botocore.exceptions import ClientError

class SecretsManager:
    def __init__(self):
        self.aws_client = boto3.client('secretsmanager')
        
    def get_secret(self, secret_name: str) -> Optional[str]:
        """Get secret from AWS Secrets Manager or environment."""
        # Try environment first (for development)
        env_value = os.getenv(secret_name)
        if env_value:
            return env_value
        
        # Try AWS Secrets Manager (for production)
        try:
            response = self.aws_client.get_secret_value(SecretId=secret_name)
            return response['SecretString']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return None
            raise
    
    def get_api_key(self, service: str) -> str:
        """Get API key for a service."""
        key = self.get_secret(f"{service.upper()}_API_KEY")
        if not key:
            raise ValueError(f"Missing API key for {service}")
        return key

# Usage
secrets = SecretsManager()
google_api_key = secrets.get_api_key("google")
```

## 🔄 CI/CD Pipeline

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - name: Install UV
        run: pip install uv
      
      - name: Install dependencies
        run: uv sync
      
      - name: Run tests
        run: |
          source .venv/bin/activate
          pytest --cov=. --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run security scan
        uses: securecodewarrior/github-action-add-sarif@v1
        with:
          sarif-file: 'security-scan.sarif'

  build:
    needs: [test, security]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=sha
            type=raw,value=latest
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to production
        run: |
          echo "${{ secrets.DEPLOY_KEY }}" | base64 -d > deploy_key
          chmod 600 deploy_key
          
          ssh -i deploy_key -o StrictHostKeyChecking=no ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }} << 'EOF'
            cd /opt/mas
            docker-compose pull
            docker-compose up -d --force-recreate
            docker system prune -f
          EOF
```

### Pre-deployment Checks

```bash
#!/bin/bash
# pre-deploy-checks.sh

set -e

echo "Running pre-deployment checks..."

# 1. Health check current deployment
echo "Checking current deployment health..."
curl -f http://localhost/health || {
    echo "Current deployment is unhealthy!"
    exit 1
}

# 2. Database migration check
echo "Checking database migrations..."
python manage.py check --deploy

# 3. Configuration validation
echo "Validating configuration..."
python -c "
from streaming_api import app
from main import EMISAgent
import os

# Check required environment variables
required_vars = ['GOOGLE_API_KEY', 'DATABASE_URL', 'REDIS_URL']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f'Missing environment variables: {missing_vars}')

print('Configuration validation passed!')
"

# 4. Security scan
echo "Running security scan..."
bandit -r . -f json -o security-report.json

# 5. Load test
echo "Running basic load test..."
ab -n 100 -c 10 http://localhost/health

echo "Pre-deployment checks passed!"
```

## 📈 Performance Optimization

### Gunicorn Configuration

```python
# gunicorn.conf.py
bind = "0.0.0.0:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 300
keepalive = 2
preload_app = True

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
```

### Database Optimization

```sql
-- init.sql
CREATE DATABASE mas_db;

-- Connection pooling settings
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;

-- Indexes for common queries
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);
CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
```

### Caching Strategy

```python
# cache.py
import redis
import json
from typing import Any, Optional
from functools import wraps
import hashlib

class CacheManager:
    def __init__(self, redis_url: str):
        self.redis_client = redis.from_url(redis_url)
    
    def cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from function arguments."""
        key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, expire: int = 300):
        """Set value in cache with expiration."""
        try:
            self.redis_client.setex(key, expire, json.dumps(value))
        except Exception as e:
            logger.error(f"Cache set error: {e}")

def cached(expire: int = 300, prefix: str = ""):
    """Decorator for caching function results."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = cache_manager.cache_key(prefix or func.__name__, *args, **kwargs)
            
            # Try to get from cache
            result = await cache_manager.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, result, expire)
            return result
        
        return wrapper
    return decorator

# Usage
@cached(expire=600, prefix="school_search")
async def search_schools(location: str, school_type: str) -> dict:
    # Expensive database query
    pass
```

## 🔧 Maintenance & Operations

### Backup Strategy

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"

# Database backup
echo "Backing up PostgreSQL..."
pg_dump -h postgres -U mas_user mas_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Redis backup
echo "Backing