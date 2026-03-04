from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nostr_relay: str = "wss://relay.ygg.gratis"
    api_key: str = ""
    log_level: str = "info"
    port: int = 8715

    # WebSocket tuning
    ws_connect_timeout: float = 10.0
    ws_response_timeout: float = 15.0
    ws_reconnect_delay: float = 5.0
    ws_max_reconnect_attempts: int = 5

    model_config = {"env_prefix": "", "case_sensitive": False}
