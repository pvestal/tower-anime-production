# Domain-Aware Configuration System

## Overview

The Tower Anime Production system now features a comprehensive domain-aware configuration system that automatically adapts service endpoints, database connections, and network bindings based on the deployment environment.

## Key Features

### 1. Environment-Based Configuration

The system supports multiple deployment environments:

- **Development**: Uses local network IP (192.168.50.135) for service discovery
- **Production**: Uses configurable domain names (e.g., tower.local)

### 2. Service URL Auto-Generation

Service URLs are automatically generated based on the current domain:

```python
from api.core.config import COMFYUI_URL, ECHO_BRAIN_URL, AUTH_SERVICE_URL

# Automatically resolves to appropriate URLs:
# Development: http://192.168.50.135:8188
# Production: http://tower.local:8188
```

### 3. Smart Database Host Selection

The database host selection is intelligent and prioritizes:

1. **Explicit override**: `DATABASE_HOST` environment variable
2. **Local availability**: Checks if PostgreSQL is available on localhost
3. **Network fallback**: Uses domain-aware configuration for remote databases

### 4. Network Accessibility

All services bind to `0.0.0.0` by default, making them accessible from:
- Local machine (localhost)
- Local network (192.168.50.x)
- External networks (when properly configured)

### 5. CORS Configuration

CORS origins are dynamically generated to include:
- Domain-based origins for all service ports
- HTTPS variants for secure connections
- Localhost fallbacks for development

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOWER_ENVIRONMENT` | Deployment environment | `development` |
| `TOWER_DOMAIN` | Base domain for services | `192.168.50.135` (dev) / `tower.local` (prod) |
| `DATABASE_HOST` | Database host override | Auto-detected |
| `COMFYUI_URL` | ComfyUI service URL | Auto-generated |
| `ECHO_SERVICE_URL` | Echo Brain service URL | Auto-generated |
| `BIND_HOST` | Service bind address | `0.0.0.0` |
| `SERVICE_PORT` | Service port | `8328` |

### Production Deployment

For production deployment, set:

```bash
export TOWER_ENVIRONMENT=production
export TOWER_DOMAIN=yourdomain.com
export DATABASE_HOST=your-db-server.com
```

### External Network Access

To make PostgreSQL accessible from external networks:

1. Edit `/etc/postgresql/16/main/postgresql.conf`:
   ```
   listen_addresses = '*'
   ```

2. Edit `/etc/postgresql/16/main/pg_hba.conf`:
   ```
   host all all 192.168.50.0/24 md5
   ```

3. Restart PostgreSQL:
   ```bash
   sudo systemctl restart postgresql
   ```

## Service Discovery

Services automatically discover each other using the domain-aware configuration:

- **ComfyUI**: Auto-discovered at configured domain:8188
- **Echo Brain**: Auto-discovered at configured domain:8309
- **Dashboard**: Auto-discovered at configured domain:8080
- **Database**: Smart host selection (local vs. remote)

## Benefits

1. **Zero Configuration**: Works out of the box in development
2. **Production Ready**: Easy transition to production domains
3. **Network Flexible**: Supports local, LAN, and WAN deployments
4. **Security Aware**: Prioritizes localhost connections when available
5. **Scalable**: Supports distributed service architectures

## Implementation

The domain-aware configuration is implemented in `/opt/tower-anime-production/api/core/config.py` and automatically applied across all services, routers, and integrations.