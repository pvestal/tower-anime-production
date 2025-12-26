#!/usr/bin/env python3
"""
Conversation Memory Service using Redis
Provides persistent conversation history storage and retrieval
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Handles conversation history storage using Redis"""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 2):
        """
        Initialize conversation memory with Redis connection

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number (using db=2 for conversation history)
        """
        try:
            # Create connection pool with proper configuration
            pool = redis.ConnectionPool(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                max_connections=50
            )
            self.redis_client = redis.Redis(connection_pool=pool)
            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Conversation memory connected to Redis at {redis_host}:{redis_port}/db={redis_db}")
        except RedisError as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise

    def add_message(self, conversation_id: str, role: str, content: str,
                   metadata: Optional[Dict] = None) -> bool:
        """
        Add a message to conversation history

        Args:
            conversation_id: Unique conversation identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata (e.g., model used, tokens, etc.)

        Returns:
            Success status
        """
        try:
            # Create message entry
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }

            # Store in Redis list (append to conversation)
            key = f"conversation:{conversation_id}"
            self.redis_client.rpush(key, json.dumps(message))

            # Set TTL to 7 days (604800 seconds) for automatic cleanup
            self.redis_client.expire(key, 604800)

            # Update conversation index
            self._update_conversation_index(conversation_id)

            # Store latest message for quick access
            latest_key = f"latest:{conversation_id}"
            self.redis_client.setex(latest_key, 3600, json.dumps(message))

            logger.debug(f"Added {role} message to conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False

    def get_conversation(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Retrieve conversation history

        Args:
            conversation_id: Unique conversation identifier
            limit: Optional limit on number of messages to return (returns latest)

        Returns:
            List of messages in chronological order
        """
        try:
            key = f"conversation:{conversation_id}"

            # Get all messages or limited number from the end
            if limit:
                messages_raw = self.redis_client.lrange(key, -limit, -1)
            else:
                messages_raw = self.redis_client.lrange(key, 0, -1)

            # Parse JSON messages
            messages = []
            for msg_raw in messages_raw:
                try:
                    messages.append(json.loads(msg_raw))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse message: {msg_raw[:100]}")

            return messages

        except Exception as e:
            logger.error(f"Failed to get conversation {conversation_id}: {e}")
            return []

    def get_conversation_summary(self, conversation_id: str) -> Dict:
        """
        Get conversation metadata and summary

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Conversation summary with metadata
        """
        try:
            messages = self.get_conversation(conversation_id)

            if not messages:
                return {
                    "conversation_id": conversation_id,
                    "message_count": 0,
                    "status": "not_found"
                }

            # Calculate summary statistics
            user_messages = [m for m in messages if m.get("role") == "user"]
            assistant_messages = [m for m in messages if m.get("role") == "assistant"]

            summary = {
                "conversation_id": conversation_id,
                "message_count": len(messages),
                "user_message_count": len(user_messages),
                "assistant_message_count": len(assistant_messages),
                "first_message_time": messages[0].get("timestamp") if messages else None,
                "last_message_time": messages[-1].get("timestamp") if messages else None,
                "topics": self._extract_topics(messages),
                "status": "active"
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to get conversation summary: {e}")
            return {
                "conversation_id": conversation_id,
                "error": str(e),
                "status": "error"
            }

    def list_conversations(self, user_id: Optional[str] = None,
                          limit: int = 10) -> List[Dict]:
        """
        List recent conversations

        Args:
            user_id: Optional user ID to filter conversations
            limit: Maximum number of conversations to return

        Returns:
            List of conversation summaries
        """
        try:
            # Get conversation IDs from index
            pattern = f"conversation:*"
            if user_id:
                pattern = f"conversation:{user_id}_*"

            # Scan for conversation keys
            conversations = []
            for key in self.redis_client.scan_iter(match=pattern, count=100):
                if key.startswith("conversation:"):
                    conversation_id = key.replace("conversation:", "")

                    # Get basic info without loading all messages
                    message_count = self.redis_client.llen(key)
                    if message_count > 0:
                        # Get first and last message for metadata
                        first_msg = json.loads(self.redis_client.lindex(key, 0))
                        last_msg = json.loads(self.redis_client.lindex(key, -1))

                        conversations.append({
                            "conversation_id": conversation_id,
                            "message_count": message_count,
                            "created_at": first_msg.get("timestamp"),
                            "updated_at": last_msg.get("timestamp"),
                            "preview": last_msg.get("content", "")[:100]
                        })

            # Sort by updated_at (most recent first)
            conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

            return conversations[:limit]

        except Exception as e:
            logger.error(f"Failed to list conversations: {e}")
            return []

    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear a conversation from history

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Success status
        """
        try:
            key = f"conversation:{conversation_id}"
            latest_key = f"latest:{conversation_id}"

            # Delete conversation and related keys
            self.redis_client.delete(key)
            self.redis_client.delete(latest_key)

            logger.info(f"Cleared conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")
            return False

    def get_context_window(self, conversation_id: str, max_messages: int = 10) -> List[Dict]:
        """
        Get recent context for AI responses

        Args:
            conversation_id: Unique conversation identifier
            max_messages: Maximum messages to include in context

        Returns:
            Recent messages suitable for AI context
        """
        messages = self.get_conversation(conversation_id, limit=max_messages)

        # Filter to user and assistant messages only
        context = []
        for msg in messages:
            if msg.get("role") in ["user", "assistant"]:
                context.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        return context

    def _update_conversation_index(self, conversation_id: str):
        """Update conversation index for tracking active conversations"""
        try:
            # Add to sorted set with current timestamp as score
            index_key = "conversations:index"
            score = time.time()
            self.redis_client.zadd(index_key, {conversation_id: score})

            # Keep only recent 1000 conversations in index
            self.redis_client.zremrangebyrank(index_key, 0, -1001)

        except Exception as e:
            logger.warning(f"Failed to update conversation index: {e}")

    def _extract_topics(self, messages: List[Dict], max_topics: int = 5) -> List[str]:
        """
        Extract main topics from conversation
        Simple keyword extraction (can be enhanced with NLP)
        """
        try:
            # Combine all user messages
            text = " ".join([m["content"] for m in messages if m.get("role") == "user"])

            # Simple topic extraction (can be enhanced)
            topics = []
            keywords = ["anime", "character", "video", "animation", "style", "generate",
                       "create", "workflow", "scene", "shot", "music", "sound"]

            for keyword in keywords:
                if keyword in text.lower():
                    topics.append(keyword)
                    if len(topics) >= max_topics:
                        break

            return topics

        except Exception:
            return []

    def get_stats(self) -> Dict:
        """Get conversation memory statistics"""
        try:
            # Get database info
            info = self.redis_client.info("memory")
            db_info = self.redis_client.info("keyspace")

            # Count conversations
            conversation_count = 0
            total_messages = 0

            for key in self.redis_client.scan_iter(match="conversation:*", count=100):
                conversation_count += 1
                total_messages += self.redis_client.llen(key)

            return {
                "status": "connected",
                "conversation_count": conversation_count,
                "total_messages": total_messages,
                "memory_used_mb": round(info.get("used_memory", 0) / (1024 * 1024), 2),
                "database_keys": db_info.get(f"db{self.redis_client.connection_pool.connection_kwargs.get('db', 0)}", {}).get("keys", 0)
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }