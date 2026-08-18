import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
from app.core.redis import get_redis

class ConnectionManager:
    """
    Real-time Live Chat & Support WebSocket Connection Manager:
    - Broadcasts visitor messages to Tenant Agent Inboxes
    - Broadcasts Agent messages/typing indicators to visitor widgets
    - Uses Redis Pub/Sub for horizontal multi-server scaling
    """

    def __init__(self):
        # Local active connections: conversation_id -> set of WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = set()
        self.active_connections[conversation_id].add(websocket)

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

    async def broadcast_to_conversation(self, conversation_id: str, message: dict):
        """Sends message directly to all local clients listening to this conversation."""
        if conversation_id in self.active_connections:
            dead_sockets = []
            for connection in self.active_connections[conversation_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_sockets.append(connection)
            for dead in dead_sockets:
                self.active_connections[conversation_id].discard(dead)

    async def publish_redis_event(self, channel: str, event_data: dict):
        """Publishes event to Redis channel for multi-instance distributed sync."""
        try:
            redis = await get_redis()
            await redis.publish(channel, json.dumps(event_data))
        except Exception:
            pass

manager = ConnectionManager()
