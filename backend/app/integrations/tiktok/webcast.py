"""TikTok LIVE capabilities currently unavailable through a documented API.

TikTok's documented developer APIs do not expose public LIVE status, live chat,
or a live participant roster. Do not replace this with private endpoints or
page/Webcast scraping. Enable this integration only after approved API access
for these capabilities becomes available.
"""


UNAVAILABLE_REASON = (
    "TikTok LIVE status and chat are unavailable: this app has no approved "
    "official TikTok API access for those capabilities."
)


async def fetch_tiktok_room(unique_id: str):
    raise RuntimeError(UNAVAILABLE_REASON)


class TikTokWebcastMonitor:
    def __init__(self, unique_id: str, *, on_event) -> None:
        self.unique_id = unique_id
        self.on_event = on_event

    async def run(self) -> None:
        raise RuntimeError(UNAVAILABLE_REASON)

    async def stop(self) -> None:
        return None
