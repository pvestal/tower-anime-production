#!/usr/bin/env python3
"""
Authentication Helper for Tower Anime Production Integration Tests
Provides standardized authentication methods for test suites
"""

import os
import requests
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import jwt

logger = logging.getLogger(__name__)

class TowerAuthHelper:
    """
    Authentication helper for Tower System integration tests.
    Handles JWT authentication using existing Tower auth patterns.
    """

    def __init__(self, base_url: str = "http://192.168.50.135:8328"):
        self.base_url = base_url
        self.auth_url = f"{base_url}/auth"

        # Use the existing vault secret key
        self.jwt_secret = os.getenv('JWT_SECRET_KEY', 'echo-brain-secret-key-2025')
        self.jwt_algorithm = "HS256"
        self.jwt_expire_hours = 24

        # Admin credentials from existing auth system
        self.admin_credentials = {
            "username": "admin",
            "password": os.getenv('ADMIN_PASSWORD', 'tower_admin_2025')
        }

        # User credentials from existing auth system
        self.user_credentials = {
            "username": "user",
            "password": os.getenv('USER_PASSWORD', 'tower_user_2025')
        }

        # Token cache
        self._tokens = {}
        self._token_expiry = {}

    def _create_local_token(self, username: str, role: str) -> str:
        """
        Create JWT token locally using the same logic as the auth service.
        This provides a fallback if the auth service is unavailable.
        """
        payload = {
            "sub": username,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=self.jwt_expire_hours),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate with Tower auth service and return token data.
        Falls back to local token generation if auth service unavailable.
        """
        try:
            # Try to authenticate with the actual auth service
            response = requests.post(
                f"{self.auth_url}/login",
                json={"username": username, "password": password},
                timeout=10
            )

            if response.status_code == 200:
                token_data = response.json()
                logger.info(f"Successfully authenticated user '{username}' with auth service")

                # Cache the token
                self._tokens[username] = token_data["access_token"]
                self._token_expiry[username] = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 86400))

                return token_data
            else:
                logger.warning(f"Auth service returned {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Auth service unavailable: {e}")

        # Fallback: create local token if we know this is a valid user
        if username in ["admin", "user"]:
            # Verify password matches expected hash (same logic as auth service)
            expected_users = {
                "admin": {
                    "role": "admin",
                    "password_hash": hashlib.sha256(self.admin_credentials["password"].encode()).hexdigest()
                },
                "user": {
                    "role": "user",
                    "password_hash": hashlib.sha256(self.user_credentials["password"].encode()).hexdigest()
                }
            }

            user_data = expected_users.get(username)
            if user_data and hashlib.sha256(password.encode()).hexdigest() == user_data["password_hash"]:
                token = self._create_local_token(username, user_data["role"])
                logger.info(f"Created local token for user '{username}' (auth service fallback)")

                # Cache the token
                self._tokens[username] = token
                self._token_expiry[username] = datetime.utcnow() + timedelta(hours=self.jwt_expire_hours)

                return {
                    "access_token": token,
                    "token_type": "bearer",
                    "expires_in": self.jwt_expire_hours * 3600
                }

        raise Exception(f"Authentication failed for user '{username}'")

    def login_admin(self) -> Dict[str, Any]:
        """Login as admin user and return token data"""
        return self.login(self.admin_credentials["username"], self.admin_credentials["password"])

    def login_user(self) -> Dict[str, Any]:
        """Login as regular user and return token data"""
        return self.login(self.user_credentials["username"], self.user_credentials["password"])

    def get_auth_headers(self, username: str = "admin") -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        Returns headers with valid JWT token.
        """
        # Check if we have a cached, non-expired token
        if username in self._tokens and username in self._token_expiry:
            if datetime.utcnow() < self._token_expiry[username]:
                return {
                    "Authorization": f"Bearer {self._tokens[username]}",
                    "Content-Type": "application/json"
                }

        # Need to login/refresh token
        if username == "admin":
            token_data = self.login_admin()
        elif username == "user":
            token_data = self.login_user()
        else:
            raise ValueError(f"Unknown user: {username}")

        return {
            "Authorization": f"Bearer {token_data['access_token']}",
            "Content-Type": "application/json"
        }

    def get_admin_headers(self) -> Dict[str, str]:
        """Get authentication headers for admin user"""
        return self.get_auth_headers("admin")

    def get_user_headers(self) -> Dict[str, str]:
        """Get authentication headers for regular user"""
        return self.get_auth_headers("user")

    def get_guest_headers(self) -> Dict[str, str]:
        """Get headers for guest mode (no authentication)"""
        return {"Content-Type": "application/json"}

    def verify_auth_service(self) -> bool:
        """
        Verify that the auth service is responding correctly.
        Returns True if auth service is healthy, False otherwise.
        """
        try:
            # Try to get current user info with a token
            headers = self.get_admin_headers()
            response = requests.get(f"{self.auth_url}/me", headers=headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Auth service verification failed: {e}")
            return False

    def test_guest_restrictions(self, endpoint: str, method: str = "POST", data: Optional[Dict] = None) -> requests.Response:
        """
        Test that an endpoint properly restricts guest users.
        Returns the response for assertion in tests.
        """
        guest_headers = self.get_guest_headers()

        if method.upper() == "POST":
            return requests.post(endpoint, json=data or {}, headers=guest_headers)
        elif method.upper() == "GET":
            return requests.get(endpoint, headers=guest_headers)
        elif method.upper() == "PUT":
            return requests.put(endpoint, json=data or {}, headers=guest_headers)
        elif method.upper() == "DELETE":
            return requests.delete(endpoint, headers=guest_headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    def cleanup_tokens(self):
        """Clear cached tokens (useful for test cleanup)"""
        self._tokens.clear()
        self._token_expiry.clear()


# Singleton instance for easy import
tower_auth = TowerAuthHelper()

# Convenience functions for backward compatibility
def get_admin_headers() -> Dict[str, str]:
    """Get admin authentication headers"""
    return tower_auth.get_admin_headers()

def get_user_headers() -> Dict[str, str]:
    """Get user authentication headers"""
    return tower_auth.get_user_headers()

def get_guest_headers() -> Dict[str, str]:
    """Get guest headers (no auth)"""
    return tower_auth.get_guest_headers()

def test_guest_restrictions(endpoint: str, method: str = "POST", data: Optional[Dict] = None) -> requests.Response:
    """Test guest user restrictions on endpoint"""
    return tower_auth.test_guest_restrictions(endpoint, method, data)