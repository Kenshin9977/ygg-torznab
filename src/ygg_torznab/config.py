from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ygg_username: str
    ygg_password: str
    ygg_domain: str = "www.yggtorrent.org"
    ygg_ip: str = "188.114.97.2"
    cf_clearance_url: str = "http://cf-clearance:3000"
    cf_refresh_interval: int = 1500  # seconds between proactive CF cookie refreshes
    turbo_user: bool = False
    api_key: str = ""
    log_level: str = "info"
    port: int = 8715

    # Tuning: retries, timeouts, timers
    max_retries: int = 3
    request_timeout: float = 30.0  # seconds for YGG HTTP requests
    cf_request_timeout: float = 120.0  # seconds for cf-clearance-scraper requests
    cf_refresh_margin: int = 300  # seconds before cookie expiry to trigger refresh
    cf_refresh_retry_delay: float = 5.0  # seconds between cf-clearance retry attempts
    non_turbo_wait: float = 31.0  # seconds to wait for non-turbo download token

    model_config = {"env_prefix": "", "case_sensitive": False}
