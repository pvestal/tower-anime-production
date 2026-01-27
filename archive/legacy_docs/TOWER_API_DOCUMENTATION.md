# Tower System API Documentation
Generated: 2026-01-25 22:21 UTC

## Service Overview

| Service | Port | Status | Base URL |
|---------|------|--------|----------|
| Tower Anime Production | 8328 | ✅ Active | http://localhost:8328 |
| Echo Brain | 8309 | ✅ Active | http://localhost:8309 |
| Semantic Memory | 8310 | ✅ Active | http://localhost:8310 |
| Echo Frontend | 8311 | ✅ Active | http://localhost:8311 |
| Echo Brain MCP | 8312 | ✅ Active | http://localhost:8312 |
| ComfyUI | 8188 | ✅ Active | http://localhost:8188 |

## Tower Anime Production API (Port 8328)

### Health Endpoints
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/health` | `{"status": "healthy", "service": "tower-anime-production", "version": "2.0.0"}` | ✅ Working |
| GET | `/api/anime/health` | `{"status": "operational", "modules": {...}}` | ✅ Working |

### Project Management
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/api/anime/projects` | Returns project list | ⚠️ Auth required |
| GET | `/api/anime/projects/{project_id}` | Get specific project | ⚠️ Auth required |
| POST | `/api/anime/projects` | Create new project | ⚠️ Auth required |
| POST | `/api/anime/projects/{id}/echo-suggest` | `{"suggestions": [...]}` | ✅ Working |
| POST | `/api/anime/projects/{id}/generate-episode` | Generate episode | ❌ Import error |

### Video Generation
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/api/video/workflows` | Returns available workflows | ✅ Working |
| POST | `/api/video/generate` | `{"job_id": "...", "status": "queued"}` | ✅ Working |
| GET | `/api/video/status/{job_id}` | `{"status": "completed", "progress": 1.0}` | ✅ Working |
| GET | `/api/video/download/{filename}` | File download or error | ✅ Working |

### Content Management
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/api/anime/characters` | `[]` | ✅ Working |
| GET | `/api/anime/episodes` | `[]` | ✅ Working |
| GET | `/api/anime/scenes` | `[]` | ✅ Working |
| GET | `/api/anime/budget/daily` | `{"budget_used": 0, "budget_limit": 1000}` | ✅ Working |

### Job Management
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/api/anime/jobs/{job_id}/status` | `{"job_id": "...", "status": "completed"}` | ✅ Working |
| GET | `/jobs/{job_id}` | Legacy endpoint | ✅ Working |
| GET | `/quality/assess/{job_id}` | Legacy quality check | ✅ Working |

### Generation Endpoints
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| POST | `/api/anime/projects/{id}/generate` | Generate content | ⚠️ Auth required |
| POST | `/api/anime/characters/{id}/generate` | Generate character | ⚠️ Auth required |
| POST | `/api/anime/scenes/{id}/generate` | Generate scene | ⚠️ Auth required |
| GET | `/api/anime/generation/{id}/status` | Generation status | ⚠️ Auth required |
| DELETE | `/api/anime/generation/{id}/cancel` | Cancel generation | ⚠️ Auth required |

### AI Enhancement
| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| POST | `/echo/enhance-prompt` | `{"enhanced_options": [...]}` | ✅ Working |
| POST | `/generate/integrated` | Integrated generation | ⚠️ Auth required |
| POST | `/generate/professional` | Professional generation | ⚠️ Auth required |

## Echo Brain API (Port 8309)

| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/health` | `{"status": "healthy", "uptime_seconds": ...}` | ✅ Working |
| POST | `/api/echo/chat` | Chat with Echo Brain | ✅ Working |
| GET | `/api/models/{model_name}/path` | Get model path | ✅ Working |

## Semantic Memory API (Port 8310)

| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/health` | `{"status": "healthy"}` | ✅ Working |

## Echo Frontend (Port 8311)

| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/health` | `{"status": "healthy"}` | ✅ Working |
| GET | `/` | Web interface | ✅ Working |

## Echo Brain MCP Server (Port 8312)

| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| POST | `/mcp` | MCP protocol interface | ✅ Working |

### MCP Methods Available:
- `search_memory` - Search semantic memory (54,000+ vectors)
- `get_facts` - Get structured facts
- `store_fact` - Store new fact (currently has DB constraint issue)

## ComfyUI (Port 8188)

| Method | Endpoint | Response | Status |
|--------|----------|----------|--------|
| GET | `/` | Web interface | ✅ Working |
| POST | `/prompt` | Submit workflow | ✅ Working |
| GET | `/history` | Get generation history | ✅ Working |
| GET | `/view` | View generated images | ✅ Working |

## OpenAPI Access

### Tower Anime Production
- **OpenAPI JSON**: http://localhost:8328/openapi.json
- **Swagger UI**: http://localhost:8328/docs
- **ReDoc**: http://localhost:8328/redoc

### Testing All Endpoints Script
```bash
#!/bin/bash
# Test all Tower system endpoints

echo "Testing Tower Anime Production..."
curl -s http://localhost:8328/health | jq

echo "Testing Echo Brain..."
curl -s http://localhost:8309/health | jq

echo "Testing Semantic Memory..."
curl -s http://localhost:8310/health | jq

echo "Testing Echo Frontend..."
curl -s http://localhost:8311/health | jq

echo "Testing video workflows..."
curl -s http://localhost:8328/api/video/workflows | jq

echo "Testing Echo prompt enhancement..."
curl -X POST http://localhost:8328/echo/enhance-prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}' | jq
```

## Authentication Status
- Most generation endpoints require authentication
- Health and informational endpoints are public
- Legacy endpoints work without auth

## Known Issues
1. `/api/anime/projects` - Returns validation error for some records
2. `/api/anime/projects/{id}/generate-episode` - Import error needs fix
3. MCP `store_fact` - Database constraint issue
4. Some endpoints need auth token implementation

## Test Results Summary
- ✅ **Working**: 18 endpoints
- ⚠️ **Auth Required**: 9 endpoints
- ❌ **Errors**: 2 endpoints
- **Total Tested**: 29 endpoints