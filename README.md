# Curiosity -> Perplexity Bridge

A FastAPI service that bridges Curiosity Desktop App's local search API to Perplexity as a Custom Remote Connector.

## Architecture

```
Perplexity Chat -> Custom Remote Connector -> This Bridge -> Curiosity Desktop App
```

## Quick Start

### 1. Find your Curiosity local API port
- Open Curiosity Desktop App
- Go to Settings > Advanced
- Note the local API port (commonly 19191)

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your Curiosity port and a strong API key
```

### 3. Run locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Test
```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer your-secret-key-here" \
  -H "Content-Type: application/json" \
  -d '{"query": "project update from slack", "max_results": 5}'
```

### 5. Expose with Cloudflare Tunnel
```bash
cloudflared tunnel --url http://localhost:8000
```
This gives you a public URL like `https://abc123.trycloudflare.com`

### 6. Register in Perplexity
1. Go to Perplexity Settings > Connectors
2. Add a Custom Remote Connector
3. Set URL to your tunnel URL + `/search`
4. Set Auth to Bearer token with your BRIDGE_API_KEY
5. Enable the connector
6. Ask: "Use Curiosity to search for [your query]"

## Docker
```bash
docker build -t curiosity-bridge .
docker run -p 8000:8000 --env-file .env curiosity-bridge
```

## Endpoints
- `POST /search` - Main search (requires auth)
- `GET /health` - Health check
- `GET /schema` - Connector schema info
