# Tower Animation Production - Authentication for Integration Tests

## Overview

The integration test suite now includes proper JWT authentication that works with the existing Tower auth system. This ensures tests run with appropriate permissions and can validate both authenticated and guest workflows.

## Quick Start

```python
from auth_helper import get_admin_headers, get_user_headers, get_guest_headers

# Make authenticated API calls
headers = get_admin_headers()
response = requests.post(f"{base_url}/api/anime/projects", json=project_data, headers=headers)

# Test guest restrictions
response = test_guest_restrictions(f"{base_url}/api/anime/projects", "POST", project_data)
assert response.status_code == 401
```

## Authentication Helper Features

### 1. Multiple Authentication Methods
- **Admin Authentication**: Full system access with `tower_admin_2025` credentials
- **User Authentication**: Standard user access with `tower_user_2025` credentials
- **Guest Mode**: No authentication (tests access restrictions)

### 2. Automatic Fallback
- Connects to Tower auth service at `http://192.168.50.135:8328/auth`
- Falls back to local token generation if auth service unavailable
- Uses vault secret: `echo-brain-secret-key-2025`

### 3. Token Management
- Automatic token caching with expiration tracking
- Refreshes tokens when needed
- Cleanup methods for test isolation

## Environment Setup

The auth helper requires these environment variables:

```bash
export JWT_SECRET_KEY="echo-brain-secret-key-2025"
export ADMIN_PASSWORD="tower_admin_2025"  # Optional, defaults to this value
export USER_PASSWORD="tower_user_2025"    # Optional, defaults to this value
```

## Usage Examples

### Basic Authentication
```python
from auth_helper import tower_auth, get_admin_headers

# Test auth service health
if tower_auth.verify_auth_service():
    print("Auth service is healthy")

# Get headers for API calls
headers = get_admin_headers()
response = requests.post(endpoint, json=data, headers=headers)
```

### Testing Guest Restrictions
```python
from auth_helper import test_guest_restrictions

# Test that guests can't create projects
response = test_guest_restrictions(
    f"{base_url}/api/anime/projects",
    method="POST",
    data={"name": "Test Project"}
)
assert response.status_code == 401
```

### Complete Test Integration
```python
class MyTestSuite:
    def __init__(self):
        self.auth_helper = tower_auth

    def setup_authentication(self):
        """Initialize and verify auth system"""
        try:
            admin_token = self.auth_helper.login_admin()
            print("Authentication ready")
        except Exception as e:
            print(f"Auth failed: {e}")

    def test_with_auth(self):
        headers = get_admin_headers()
        response = requests.post(endpoint, json=data, headers=headers)
        # ... test logic

    def cleanup(self):
        self.auth_helper.cleanup_tokens()
```

## Integration Test Results

The authentication system passes all tests:

- ✅ **Auth Service Health**: Tower auth service responding correctly
- ✅ **Admin Login**: Admin authentication working with proper token generation
- ✅ **User Login**: User authentication working with proper token generation
- ✅ **Token Generation**: Local fallback token generation working
- ✅ **Header Generation**: Proper Authorization headers created
- ✅ **Guest Mode**: Guest mode works without auth headers
- ✅ **Fallback Mode**: System works when auth service unavailable

## Security Features

1. **Proper JWT Validation**: Uses HS256 algorithm with vault secret
2. **Password Hashing**: SHA256 hashing matches auth service patterns
3. **Token Expiration**: 24-hour token expiry with automatic refresh
4. **Guest Restrictions**: Proper 401 responses for unauthenticated users
5. **Fallback Security**: Local tokens use same security patterns as auth service

## Troubleshooting

### Auth Service Unavailable
If auth service is down, the helper automatically falls back to local token generation using the same credentials and secret key.

### Token Expired
Tokens are automatically refreshed when expired. Clear cache if needed:
```python
tower_auth.cleanup_tokens()
```

### Permission Denied
Ensure you're using admin headers for admin-required endpoints:
```python
headers = get_admin_headers()  # Not get_user_headers()
```

### Environment Variables
Set JWT secret if not using default:
```bash
export JWT_SECRET_KEY="your-secret-key"
```

## Files

- `auth_helper.py`: Main authentication helper class
- `test_authentication_only.py`: Focused auth tests
- `test_neon_tokyo_nights_lifecycle.py`: Updated integration test using auth helper

This authentication system ensures your integration tests work properly with the Tower security model while providing robust fallback capabilities.