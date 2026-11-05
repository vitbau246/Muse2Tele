from dataclasses import asdict, dataclass

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")


@dataclass
class Profile:
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    # None = follow the proxy's exit IP (Camoufox geoip); set to pin a value.
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    # Muse2Tele: cho phep social_post tu dong dang bai len fanpage Facebook / TikTok
    # bang tai khoan da dang nhap trong profile nay.
    auto_post_fanpage: bool = False
    auto_post_tiktok: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
