import asyncio
import hashlib
import time
from dataclasses import dataclass, field

from app.config import settings
from app.devin_client import devin_client


@dataclass
class SessionEntry:
    session_id: str
    devin_mode: str | None
    last_seen: float = field(default_factory=time.time)
    message_cursor: str | None = None
    last_output: str = ""


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    @staticmethod
    def conversation_hash(messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            parts.append(f"{role}:{content}")
        joined = "\n".join(parts)
        return hashlib.sha256(joined.encode()).hexdigest()

    async def get_or_create(
        self,
        conv_hash: str,
        prompt: str,
        devin_mode: str | None,
        title: str | None = None,
    ) -> SessionEntry:
        async with self._lock:
            entry = self._sessions.get(conv_hash)
            if entry:
                entry.last_seen = time.time()
                return entry

        session = await devin_client.create_session(
            prompt=prompt,
            devin_mode=devin_mode,
            title=title,
        )
        entry = SessionEntry(
            session_id=session["session_id"],
            devin_mode=devin_mode,
        )
        async with self._lock:
            self._sessions[conv_hash] = entry
        return entry

    async def get(self, conv_hash: str) -> SessionEntry | None:
        async with self._lock:
            entry = self._sessions.get(conv_hash)
            if entry:
                entry.last_seen = time.time()
            return entry

    async def remove(self, conv_hash: str) -> None:
        async with self._lock:
            self._sessions.pop(conv_hash, None)

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.time()
            to_remove: list[tuple[str, SessionEntry]] = []
            async with self._lock:
                for conv_hash, entry in self._sessions.items():
                    if now - entry.last_seen > settings.session_idle_timeout:
                        to_remove.append((conv_hash, entry))
                for conv_hash, _ in to_remove:
                    self._sessions.pop(conv_hash, None)

            for _, entry in to_remove:
                try:
                    await devin_client.delete_session(entry.session_id, archive=True)
                except Exception:
                    pass

    def start_cleanup(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self.cleanup_loop())


session_manager = SessionManager()
