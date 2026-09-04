import asyncio
import logging
from typing import Dict, Set, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        # Queues para SSE (Server-Sent Events): workspace_id -> list of asyncio.Queue
        self.sse_subscribers: Dict[int, List[asyncio.Queue]] = {}
        # Conexões WebSocket ativas: workspace_id -> set of WebSocket
        self.ws_subscribers: Dict[int, Set[WebSocket]] = {}
        # Versão dos dados por workspace para sincronização e polling
        self.workspace_versions: Dict[int, int] = {}
        self.global_version = 1

    def subscribe_sse(self, workspace_id: int) -> asyncio.Queue:
        if workspace_id not in self.sse_subscribers:
            self.sse_subscribers[workspace_id] = []
        queue = asyncio.Queue()
        self.sse_subscribers[workspace_id].append(queue)
        return queue

    def unsubscribe_sse(self, workspace_id: int, queue: asyncio.Queue):
        if workspace_id in self.sse_subscribers:
            if queue in self.sse_subscribers[workspace_id]:
                self.sse_subscribers[workspace_id].remove(queue)
            if not self.sse_subscribers[workspace_id]:
                del self.sse_subscribers[workspace_id]

    async def register_ws(self, workspace_id: int, websocket: WebSocket):
        await websocket.accept()
        if workspace_id not in self.ws_subscribers:
            self.ws_subscribers[workspace_id] = set()
        self.ws_subscribers[workspace_id].add(websocket)

    def unregister_ws(self, workspace_id: int, websocket: WebSocket):
        if workspace_id in self.ws_subscribers:
            self.ws_subscribers[workspace_id].discard(websocket)
            if not self.ws_subscribers[workspace_id]:
                del self.ws_subscribers[workspace_id]

    def notify_workspace_update(self, workspace_id: int, event_type: str = "data_updated"):
        """Dispara evento de atualização instantânea para todos os navegadores abertos no workspace"""
        self.global_version += 1
        self.workspace_versions[workspace_id] = self.global_version
        
        # 1. Notifica filas SSE
        if workspace_id in self.sse_subscribers:
            for q in list(self.sse_subscribers[workspace_id]):
                try:
                    q.put_nowait({"event": event_type, "workspace_id": workspace_id, "version": self.global_version})
                except Exception as e:
                    logger.debug(f"Erro ao enfileirar evento SSE: {e}")

        # 2. Notifica WebSockets
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_ws(workspace_id, event_type))
        except RuntimeError:
            pass

    async def _broadcast_ws(self, workspace_id: int, event_type: str):
        if workspace_id not in self.ws_subscribers:
            return
        dead = set()
        for ws in list(self.ws_subscribers[workspace_id]):
            try:
                await ws.send_json({"event": event_type, "workspace_id": workspace_id, "version": self.global_version})
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.unregister_ws(workspace_id, ws)

    def get_workspace_version(self, workspace_id: int) -> int:
        return self.workspace_versions.get(workspace_id, 1)

event_bus = EventBus()
