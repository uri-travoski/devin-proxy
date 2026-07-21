# Devin Proxy

An OpenAI-compatible API proxy for [Devin AI](https://devin.ai). Run it with Docker Compose, point any OpenAI-compatible client at it, and use Devin as the backend.

## Quick Start

1. Create a `.env` file in the project root:

```bash
DEVIN_API_KEY=your_devin_api_key
DEVIN_ORG_ID=org-your-org-id
PROXY_API_KEY=your_proxy_api_key
```

2. Start the proxy:

```bash
docker compose up -d
```

3. Point your OpenAI-compatible app at the proxy:

| Setting | Value |
|---|---|
| API Base URL | `http://localhost:8000/v1` |
| API Key | Your `PROXY_API_KEY` |
| Model | `adaptive`, `glm5.2-high`, or `swe1.7-max` |

## Available Models

| Model name | Devin mode | Description |
|---|---|---|
| `adaptive` | normal | Intelligent model router (default) |
| `glm5.2-high` | fast | ~2x faster, higher throughput |
| `swe1.7-max` | ultra | Maximum capability |

## Usage Examples

### cURL

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your_proxy_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "adaptive",
    "messages": [{"role": "user", "content": "Write a Python script that prints hello world"}]
  }'
```

### Streaming

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your_proxy_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm5.2-high",
    "stream": true,
    "messages": [{"role": "user", "content": "Explain how async/await works in Python"}]
  }'
```

### List Models

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer your_proxy_api_key"
```

### Python (openai library)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your_proxy_api_key",
)

response = client.chat.completions.create(
    model="adaptive",
    messages=[{"role": "user", "content": "Write a hello world script"}],
)

print(response.choices[0].message.content)
```

## Configuration

All configuration is via environment variables (set in `.env` or `docker-compose.yml`):

| Variable | Default | Description |
|---|---|---|
| `DEVIN_API_URL` | `https://api.devin.ai` | Devin API base URL |
| `DEVIN_API_KEY` | (required) | Devin API key |
| `DEVIN_ORG_ID` | (required) | Devin organization ID |
| `PROXY_API_KEY` | (required) | API key for proxy authentication |
| `PROXY_PORT` | `8000` | Port the proxy listens on |
| `SESSION_IDLE_TIMEOUT` | `1800` | Seconds before idle sessions are cleaned up |
| `POLL_INTERVAL` | `3` | Seconds between status polls |
| `MAX_POLL_DURATION` | `600` | Max seconds to poll before timeout |

## How It Works

1. Each conversation (identified by a hash of the message history) maps to a Devin session.
2. The first message creates a new Devin session. Subsequent messages are sent to the existing session.
3. The proxy polls the Devin API for session status and output.
4. For streaming requests, Devin's output is streamed back as SSE chunks in OpenAI format.
5. Idle sessions are automatically archived and cleaned up after the timeout.

## Endpoints

- `POST /v1/chat/completions` — OpenAI-compatible chat completions (streaming + non-streaming)
- `GET /v1/models` — List available models
- `GET /health` — Health check
