"""
Content Safety and Filtering System
Handles age verification, content classification, and safety controls for NSFW content
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal
from enum import Enum
from pathlib import Path
import jwt
from functools import wraps

logger = logging.getLogger(__name__)

class ContentLevel(Enum):
    """Content classification levels"""
    SFW = "sfw"  # Safe for work
    SUGGESTIVE = "suggestive"  # Mildly suggestive
    NSFW_SOFT = "nsfw_soft"  # Artistic/tasteful adult content
    NSFW_EXPLICIT = "nsfw_explicit"  # Explicit adult content

class ContentSafetyFilter:
    """
    Comprehensive content safety and filtering system.
    Handles age verification, consent tracking, and audit logging.
    """

    def __init__(self, config: Dict = None):
        self.config = config or self._default_config()
        self.audit_log_path = Path("/opt/tower-anime-production/audit_logs")
        self.audit_log_path.mkdir(exist_ok=True, parents=True)
        self.jwt_secret = self.config.get("jwt_secret", "tower-anime-production-secret-2025")

    def _default_config(self) -> Dict:
        """Default safety configuration"""
        return {
            "min_age": 18,
            "require_explicit_consent": True,
            "enable_watermarking": True,
            "audit_logging": True,
            "content_isolation": True,  # Separate storage for NSFW content
            "rate_limiting": {
                "nsfw_per_hour": 10,
                "nsfw_per_day": 50
            },
            "blocked_keywords": [],  # Keywords that trigger automatic blocking
            "require_2fa_for_explicit": False,  # Optional 2FA for explicit content
        }

    def verify_age_and_consent(
        self,
        user_context: Dict,
        content_level: ContentLevel,
        request_metadata: Dict = None
    ) -> Dict:
        """
        Verify user age and consent for requested content level.

        Args:
            user_context: User information including auth tokens
            content_level: Requested content classification
            request_metadata: Additional request context

        Returns:
            Validation result with approval status and requirements
        """
        validation_result = {
            "approved": False,
            "content_level": content_level.value,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_context.get("user_id", "anonymous"),
            "checks_performed": []
        }

        # Check 1: Age verification
        age_verified = self._verify_age(user_context)
        validation_result["checks_performed"].append({
            "check": "age_verification",
            "passed": age_verified,
            "required_age": self.config["min_age"]
        })

        if not age_verified:
            validation_result["rejection_reason"] = "Age verification failed"
            self._audit_log(validation_result, "REJECTED")
            return validation_result

        # Check 2: Content-specific consent
        if content_level in [ContentLevel.NSFW_SOFT, ContentLevel.NSFW_EXPLICIT]:
            consent_verified = self._verify_consent(user_context, content_level)
            validation_result["checks_performed"].append({
                "check": "nsfw_consent",
                "passed": consent_verified,
                "content_level": content_level.value
            })

            if not consent_verified:
                validation_result["rejection_reason"] = "NSFW consent not provided"
                self._audit_log(validation_result, "REJECTED")
                return validation_result

        # Check 3: Explicit content additional verification
        if content_level == ContentLevel.NSFW_EXPLICIT and self.config["require_explicit_consent"]:
            explicit_consent = user_context.get("explicit_content_consent", False)
            validation_result["checks_performed"].append({
                "check": "explicit_consent",
                "passed": explicit_consent
            })

            if not explicit_consent:
                validation_result["rejection_reason"] = "Explicit content consent required"
                self._audit_log(validation_result, "REJECTED")
                return validation_result

        # Check 4: Rate limiting for NSFW content
        if content_level in [ContentLevel.NSFW_SOFT, ContentLevel.NSFW_EXPLICIT]:
            rate_limit_ok = self._check_rate_limits(user_context, content_level)
            validation_result["checks_performed"].append({
                "check": "rate_limiting",
                "passed": rate_limit_ok
            })

            if not rate_limit_ok:
                validation_result["rejection_reason"] = "Rate limit exceeded"
                self._audit_log(validation_result, "RATE_LIMITED")
                return validation_result

        # All checks passed
        validation_result["approved"] = True
        validation_result["access_token"] = self._generate_access_token(
            user_context, content_level
        )

        # Audit successful approval
        self._audit_log(validation_result, "APPROVED")

        return validation_result

    def _verify_age(self, user_context: Dict) -> bool:
        """Verify user meets minimum age requirement"""
        # Check for age verification token
        age_token = user_context.get("age_verification_token")
        if age_token:
            try:
                payload = jwt.decode(
                    age_token,
                    self.jwt_secret,
                    algorithms=["HS256"]
                )
                return payload.get("age", 0) >= self.config["min_age"]
            except jwt.InvalidTokenError:
                logger.warning("Invalid age verification token")
                return False

        # Check for explicit age confirmation
        age_confirmed = user_context.get("age_confirmed", 0)
        return age_confirmed >= self.config["min_age"]

    def _verify_consent(self, user_context: Dict, content_level: ContentLevel) -> bool:
        """Verify user has consented to content level"""
        consent_levels = user_context.get("consented_levels", [])

        # Check if user has consented to this level or higher
        if content_level.value in consent_levels:
            return True

        # Check for session-specific consent
        session_consent = user_context.get("session_consent", {})
        return session_consent.get(content_level.value, False)

    def _check_rate_limits(self, user_context: Dict, content_level: ContentLevel) -> bool:
        """Check if user is within rate limits for NSFW content"""
        user_id = user_context.get("user_id", "anonymous")

        # Load user's request history
        history = self._load_user_history(user_id)

        # Count requests in time windows
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        hourly_count = sum(
            1 for req in history
            if datetime.fromisoformat(req["timestamp"]) > hour_ago
            and req["content_level"] in ["nsfw_soft", "nsfw_explicit"]
        )

        daily_count = sum(
            1 for req in history
            if datetime.fromisoformat(req["timestamp"]) > day_ago
            and req["content_level"] in ["nsfw_soft", "nsfw_explicit"]
        )

        limits = self.config["rate_limiting"]
        return (hourly_count < limits["nsfw_per_hour"] and
                daily_count < limits["nsfw_per_day"])

    def _generate_access_token(self, user_context: Dict, content_level: ContentLevel) -> str:
        """Generate time-limited access token for content generation"""
        payload = {
            "user_id": user_context.get("user_id", "anonymous"),
            "content_level": content_level.value,
            "issued_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
            "session_id": user_context.get("session_id", ""),
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def classify_prompt(self, prompt: str) -> ContentLevel:
        """
        Classify a text prompt to determine content level.
        Uses keyword matching and pattern detection.
        """
        prompt_lower = prompt.lower()

        # Check for blocked keywords first
        for keyword in self.config.get("blocked_keywords", []):
            if keyword.lower() in prompt_lower:
                logger.warning(f"Blocked keyword detected: {keyword}")
                raise ValueError(f"Prompt contains blocked content")

        # Explicit content indicators
        explicit_keywords = [
            "nude", "naked", "explicit", "xxx", "porn",
            "sex", "intercourse", "genital"
        ]

        # Soft NSFW indicators
        nsfw_soft_keywords = [
            "lingerie", "bikini", "sensual", "erotic",
            "seductive", "intimate", "bedroom", "shower"
        ]

        # Suggestive indicators
        suggestive_keywords = [
            "flirty", "cute", "attractive", "hot",
            "sexy", "alluring", "revealing"
        ]

        # Classification logic
        if any(keyword in prompt_lower for keyword in explicit_keywords):
            return ContentLevel.NSFW_EXPLICIT

        if any(keyword in prompt_lower for keyword in nsfw_soft_keywords):
            return ContentLevel.NSFW_SOFT

        if any(keyword in prompt_lower for keyword in suggestive_keywords):
            return ContentLevel.SUGGESTIVE

        return ContentLevel.SFW

    def apply_content_filters(self, generation_params: Dict, content_level: ContentLevel) -> Dict:
        """
        Apply appropriate filters and modifications based on content level.

        Args:
            generation_params: Original generation parameters
            content_level: Classified content level

        Returns:
            Modified parameters with safety filters applied
        """
        filtered_params = generation_params.copy()

        # Apply negative prompts for safety
        base_negative = filtered_params.get("negative_prompt", "")

        if content_level == ContentLevel.SFW:
            # Add strong NSFW blocking to negative prompt
            safety_negative = "nsfw, nude, naked, explicit, sexual, inappropriate, revealing clothes"
            filtered_params["negative_prompt"] = f"{base_negative}, {safety_negative}"

        elif content_level == ContentLevel.SUGGESTIVE:
            # Allow suggestive but block explicit
            safety_negative = "nude, naked, explicit, genitals, pornographic"
            filtered_params["negative_prompt"] = f"{base_negative}, {safety_negative}"

        # Add watermark configuration
        if self.config["enable_watermarking"]:
            filtered_params["add_watermark"] = True
            filtered_params["watermark_text"] = self._get_watermark_text(content_level)

        # Set appropriate model based on content
        if content_level in [ContentLevel.NSFW_SOFT, ContentLevel.NSFW_EXPLICIT]:
            # Use NSFW-capable model if specified
            if "nsfw_model" in self.config:
                filtered_params["model_override"] = self.config["nsfw_model"]

        return filtered_params

    def _get_watermark_text(self, content_level: ContentLevel) -> str:
        """Generate appropriate watermark text based on content level"""
        watermarks = {
            ContentLevel.SFW: "AI Generated",
            ContentLevel.SUGGESTIVE: "AI Generated - Artistic Content",
            ContentLevel.NSFW_SOFT: "AI Generated - Adult Content - 18+",
            ContentLevel.NSFW_EXPLICIT: "AI Generated - Explicit Content - 18+ Only"
        }
        return watermarks.get(content_level, "AI Generated")

    def get_storage_path(self, content_level: ContentLevel, base_path: str) -> Path:
        """
        Get appropriate storage path based on content level.
        Isolates NSFW content in separate directories.
        """
        base = Path(base_path)

        if self.config["content_isolation"]:
            if content_level == ContentLevel.NSFW_EXPLICIT:
                return base / "nsfw_explicit"
            elif content_level == ContentLevel.NSFW_SOFT:
                return base / "nsfw_soft"
            elif content_level == ContentLevel.SUGGESTIVE:
                return base / "suggestive"

        return base / "sfw"

    def _audit_log(self, validation_result: Dict, action: str):
        """Write detailed audit log entry"""
        if not self.config["audit_logging"]:
            return

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "user_id": validation_result.get("user_id"),
            "content_level": validation_result.get("content_level"),
            "approved": validation_result.get("approved", False),
            "checks": validation_result.get("checks_performed", []),
            "rejection_reason": validation_result.get("rejection_reason")
        }

        # Write to daily log file
        log_file = self.audit_log_path / f"audit_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")

        # Also log to standard logger
        logger.info(f"Content safety audit: {action} - User: {log_entry['user_id']} - Level: {log_entry['content_level']}")

    def _load_user_history(self, user_id: str) -> List[Dict]:
        """Load user's request history for rate limiting"""
        history_file = self.audit_log_path / f"user_{hashlib.md5(user_id.encode()).hexdigest()}_history.jsonl"

        if not history_file.exists():
            return []

        history = []
        with open(history_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    history.append(entry)
                except:
                    continue

        return history

    def create_age_verification_token(self, user_id: str, age: int) -> str:
        """
        Create a signed age verification token for the user.
        This should be called after proper age verification.
        """
        payload = {
            "user_id": user_id,
            "age": age,
            "verified_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")

        # Log the verification
        self._audit_log({
            "user_id": user_id,
            "action": "age_verification",
            "age": age
        }, "AGE_VERIFIED")

        return token


# Decorator for FastAPI endpoints requiring content safety checks
def require_content_safety(content_level: ContentLevel):
    """
    Decorator for API endpoints that require content safety validation.

    Usage:
        @require_content_safety(ContentLevel.NSFW_SOFT)
        async def generate_suggestive_content(request: Request):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args (assumes FastAPI endpoint structure)
            request = None
            for arg in args:
                if hasattr(arg, 'headers'):
                    request = arg
                    break

            if not request:
                raise ValueError("Request object not found")

            # Get user context from request
            user_context = {
                "user_id": request.headers.get("X-User-ID", "anonymous"),
                "age_verification_token": request.headers.get("X-Age-Token"),
                "session_id": request.headers.get("X-Session-ID"),
                "explicit_content_consent": request.headers.get("X-Explicit-Consent") == "true"
            }

            # Initialize safety filter
            safety_filter = ContentSafetyFilter()

            # Verify access
            validation = safety_filter.verify_age_and_consent(
                user_context,
                content_level,
                {"endpoint": func.__name__}
            )

            if not validation["approved"]:
                raise PermissionError(
                    f"Content safety validation failed: {validation.get('rejection_reason')}"
                )

            # Add validation result to kwargs for use in endpoint
            kwargs["content_validation"] = validation

            return await func(*args, **kwargs)

        return wrapper
    return decorator


# Global instance
content_safety = ContentSafetyFilter()