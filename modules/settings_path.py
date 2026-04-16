#v0.89.04 新增環境變數替換功能，設定檔中可使用 ${VAR_NAME} 來引用環境變數

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

# 載入 .env 檔案
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent / "settings" / ".env"
load_dotenv(_env_path)

SETTINGS_ENV_VAR = "SUBTITLE_AI_SETTINGS_FILE"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_path(path_value: str | Path, base_dir: Optional[Path] = None) -> Path:
    base = base_dir or _project_root()
    path = Path(path_value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _extract_override(candidate: Path) -> Optional[Path]:
    try:
        with open(candidate, "r", encoding="utf-8") as f:
            data = json.load(f)
        override_value = data.get("paths", {}).get("settings_file")
        if override_value:
            return _normalize_path(override_value)
    except Exception:
        pass
    return None


def _bootstrap_candidates() -> Iterable[Path]:
    root = _project_root()
    yield root / "settings" / "settings.json"
    legacy = (root.parent / "settings" / "settings.json").resolve()
    if legacy not in (root / "settings" / "settings.json",):
        yield legacy


@lru_cache(maxsize=1)
def resolve_settings_file() -> Path:
    env_value = os.environ.get(SETTINGS_ENV_VAR)
    if env_value:
        env_path = _normalize_path(env_value)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        return env_path

    for candidate in _bootstrap_candidates():
        if candidate.exists():
            override = _extract_override(candidate)
            target = override or candidate
            target.parent.mkdir(parents=True, exist_ok=True)
            return target

    fallback = next(iter(_bootstrap_candidates()))
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_settings_file_from_data(settings: Optional[dict]) -> Path:
    if settings:
        custom_path = settings.get("paths", {}).get("settings_file") if isinstance(settings.get("paths"), dict) else None
        if custom_path:
            target = _normalize_path(custom_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
    return resolve_settings_file()


def clear_settings_cache() -> None:
    resolve_settings_file.cache_clear()


def make_portable_path(path: Path) -> str:
    root = _project_root()
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        try:
            return str(path.resolve().relative_to(root.parent))
        except ValueError:
            return str(path.resolve())


def resolve_settings_dir() -> Path:
    return resolve_settings_file().parent


def resolve_settings_asset(*segments: str) -> Path:
    return resolve_settings_dir().joinpath(*segments)


def substitute_env_vars(data):
    """遞迴替換資料中的 ${ENV_VAR} 環境變數佔位符"""
    if isinstance(data, dict):
        return {key: substitute_env_vars(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [substitute_env_vars(item) for item in data]
    elif isinstance(data, str):
        import re
        pattern = r'\$\{([^}]+)\}'
        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return re.sub(pattern, replace, data)
    return data


def update_bootstrap_pointer(target: Path) -> None:
    bootstrap = _project_root() / "settings" / "settings.json"
    target_resolved = target.resolve()
    if not bootstrap.exists() and target_resolved != bootstrap.resolve():
        bootstrap.parent.mkdir(parents=True, exist_ok=True)
    if target_resolved == bootstrap.resolve():
        return
    pointer_content = {
        "paths": {
            "settings_file": make_portable_path(target_resolved)
        }
    }
    with open(bootstrap, "w", encoding="utf-8") as f:
        json.dump(pointer_content, f, ensure_ascii=False, indent=4)
