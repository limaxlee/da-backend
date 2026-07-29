import os
import yaml
import argparse
from typing import Any
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from common.constants import ROOT_DIR


_ENV_MAP = {
    "SERVER_PORT": ("server_port", int),
    "LAB_ID": ("lab_id", str),
    "TENANT_CODE": ("tenant_code", str),
    "BASE_URL": ("base_url", str),
    "OTEL_ENABLED": ("otel_enabled", lambda value: value.strip().lower() == "true"),
    "LOG_LEVEL": ("log_level", str),
    "MONGODB_MCP_HOST": ("mongodb_mcp.host", str),
    "MONGODB_MCP_PORT": ("mongodb_mcp.port", int),
    "MILVUS_MCP_HOST": ("milvus_mcp.host", str),
    "MILVUS_MCP_PORT": ("milvus_mcp.port", int),
    "SESSION_DB_HOST": ("session_db.host", str),
    "SESSION_DB_PORT": ("session_db.port", int),
    "SESSION_DB_NAME": ("session_db.name", str),
    "OBJECT_STORAGE_BUCKET": ("object_storage.bucket", str),
    "OBJECT_STORAGE_ENDPOINT": ("object_storage.endpoint", str),
    "OBJECT_STORAGE_ACCESS_KEY": ("object_storage.access_key", str),
    "OBJECT_STORAGE_SECRET_KEY": ("object_storage.secret_key", str)
}


def _set_nested_config(config: dict[str, Any], key: str, value: Any) -> None:
    *groups, values = key.split(".")
    node = config
    for group in groups:
        node = node.setdefault(group, {})
        if not isinstance(node, dict):
            raise ValueError(f"Config key {group} is invalid: {type(node).__name__}")

    node[values] = value


def load_config() -> dict[str, Any]:
    default_config = os.path.join(ROOT_DIR, "config.yaml")
    parser = argparse.ArgumentParser(description="Data Agent Backend Configurations")
    parser.add_argument("--config", "-c", type=str, help="Path to the config.yaml", default=default_config)
    args, _ = parser.parse_known_args()

    config = {}
    if os.path.isfile(args.config):
        with open(args.config, "r") as f:
            file_config = yaml.safe_load(f) or {}

        if not isinstance(file_config, dict):
            raise ValueError(f"Config file is invalid: {args.config}")

        config.update(file_config)

    for env_name, (key, caster) in _ENV_MAP.items():
        env_value = os.getenv(env_name)
        if env_value is None:
            continue

        try:
            value = caster(env_value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid value for {env_name}: {env_value!r}") from error

        _set_nested_config(config, key, value)

    return config


class MCPConfig(BaseModel):
    host: str
    port: int


class SessionDBConfig(BaseModel):
    host: str
    port: int
    name: str


class ObjectStorageConfig(BaseModel):
    bucket: str
    endpoint: str
    access_key: str
    secret_key: str


class Settings(BaseSettings, extra="allow"):
    server_port: int
    lab_id: str
    tenant_code: str
    base_url: str
    otel_enabled: bool
    log_level: str

    mongodb_mcp: MCPConfig
    milvus_mcp: MCPConfig

    session_db: SessionDBConfig
    object_storage: ObjectStorageConfig


SETTINGS = Settings(**load_config())
