from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ygg_username: str
    ygg_password: str
    ygg_domain: str = "www.yggtorrent.org"
    ygg_ip: str = "188.114.97.2"
    cf_clearance_url: str = "http://cf-clearance:3000"
    api_key: str = ""
    log_level: str = "info"
    port: int = 8715

    model_config = {"env_prefix": "", "case_sensitive": False}
