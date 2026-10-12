import httpx

from .config import cfg


class DBError(Exception):
    pass


class Supabase:
    """Минимальный async-клиент PostgREST (Supabase)."""

    def __init__(self):
        h = {"apikey": cfg.supabase_key, "Content-Type": "application/json"}
        if cfg.supabase_key.startswith("eyJ"):
            h["Authorization"] = "Bearer " + cfg.supabase_key
        self.http = httpx.AsyncClient(base_url=cfg.supabase_url.rstrip("/") + "/rest/v1", headers=h, timeout=20)

    async def _req(self, method, table, params=None, json=None, prefer=None, headers=None):
        hdr = dict(headers or {})
        if prefer:
            hdr["Prefer"] = prefer
        r = await self.http.request(method, f"/{table}", params=params, json=json, headers=hdr)
        if r.status_code >= 400:
            raise DBError(f"{method} {table}: {r.status_code} {r.text[:300]}")
        return r

    async def select(self, table, params=None):
        return (await self._req("GET", table, params={"select": "*", **(params or {})})).json()

    async def select_all(self, table, params=None, page=1000):
        out, off = [], 0
        while True:
            rows = (await self._req("GET", table, params={"select": "*", **(params or {}), "limit": page, "offset": off})).json()
            out += rows
            if len(rows) < page:
                return out
            off += page

    async def count(self, table, params=None) -> int:
        r = await self._req("GET", table, params={"select": "*", **(params or {})},
                            headers={"Prefer": "count=exact", "Range": "0-0"})
        return int(r.headers.get("content-range", "*/0").split("/")[-1] or 0)

    async def insert(self, table, data, upsert=None, ignore=False, returning=True):
        prefer = ["return=representation" if returning else "return=minimal"]
        params = {}
        if upsert:
            prefer.append("resolution=ignore-duplicates" if ignore else "resolution=merge-duplicates")
            params["on_conflict"] = upsert
        r = await self._req("POST", table, params=params, json=data, prefer=",".join(prefer))
        return r.json() if returning and r.text else None

    async def update(self, table, filters, data):
        r = await self._req("PATCH", table, params=filters, json=data, prefer="return=representation")
        return r.json()

    async def delete(self, table, filters):
        await self._req("DELETE", table, params=filters)


db = Supabase()
