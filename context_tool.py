import httpx

_CONTEXT_BASE_URL = "https://api.context.dev/v1/search"

TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "fetch_live_data",
        "description": (
            "Fetches live enrichment data about a company or person from Context.dev. "
            "Call this when you need real-time company info, technographics, funding, "
            "or other enrichment before qualifying the lead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The company name, domain, or person to look up. "
                        "Examples: 'Acme Corp', 'acme.com', 'Jane Doe at TechCorp'"
                    ),
                }
            },
            "required": ["query"],
        },
    },
}


async def fetch_live_data(query: str) -> dict:
    from config import get_settings
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _CONTEXT_BASE_URL,
                params={"q": query},
                headers={"Authorization": f"Bearer {settings.CONTEXT_DEV_API_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        print(f"[context_tool] fetch_live_data error for query {query!r}: {exc}")
        return {"error": str(exc), "data": None}


def get_tool_schema() -> dict:
    return TOOL_SCHEMA
