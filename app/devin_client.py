import httpx
from app.config import settings


class DevinClient:
    def __init__(self) -> None:
        self._base_url = settings.devin_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.devin_api_key}",
            "Content-Type": "application/json",
        }
        self._org_id = settings.devin_org_id

    def _session_url(self, session_id: str) -> str:
        return f"{self._base_url}/v3/organizations/{self._org_id}/sessions/{session_id}"

    async def create_session(
        self,
        prompt: str,
        devin_mode: str | None = None,
        title: str | None = None,
    ) -> dict:
        body: dict = {"prompt": prompt}
        if devin_mode:
            body["devin_mode"] = devin_mode
        if title:
            body["title"] = title
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/v3/organizations/{self._org_id}/sessions",
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session(self, session_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._session_url(session_id),
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def send_message(self, session_id: str, message: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._session_url(session_id)}/messages",
                headers=self._headers,
                json={"message": message},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_messages(
        self, session_id: str, after: str | None = None
    ) -> dict:
        params: dict = {}
        if after:
            params["after"] = after
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._session_url(session_id)}/messages",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_session(self, session_id: str, archive: bool = True) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                self._session_url(session_id),
                headers=self._headers,
                params={"archive": str(archive).lower()},
            )
            resp.raise_for_status()


devin_client = DevinClient()
