"""Small, non-executing configuration loader with secret-safe diagnostics."""

from dataclasses import dataclass, field
import os
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
MODES = {"auto", "live", "cache", "off"}
PROVIDERS = {"openai", "anthropic"}
DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-6"}
KEY_NAMES = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
ENV_NAMES = {
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID",
    "RAREBRIDGE_AI_PROVIDER", "RAREBRIDGE_AI_MODEL", "RAREBRIDGE_AI_MODE",
    "RAREBRIDGE_AI_TIMEOUT_SECONDS", "RAREBRIDGE_AI_MAX_OUTPUT_TOKENS",
    "RAREBRIDGE_AI_CACHE_DIR",
}


def read_dotenv(path):
    """Read literal key=value lines. Never execute or expand shell expressions."""
    path = Path(path)
    if not path.is_file():
        return {}
    if path.stat().st_size > 32_768:
        raise ValueError("Local .env exceeds the configuration size limit")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in ENV_NAMES:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(repr=False)
    model: str = "gpt-4o-mini"
    mode: str = "auto"
    timeout_seconds: float = 40
    max_output_tokens: int = 6000
    cache_dir: Path = WORKSPACE_ROOT / "rarebridge" / "ai" / "cache"
    provider: str = "openai"
    anthropic_workspace_id: str = ""

    def diagnostics(self):
        return {
            "api_key_configured": bool(self.api_key), "model": self.model,
            "mode": self.mode, "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "cache_dir": str(self.cache_dir),
            "provider": self.provider,
            "workspace_id_configured": bool(self.anthropic_workspace_id),
        }


def load_config(environ=None, env_path=None):
    values = read_dotenv(env_path or WORKSPACE_ROOT / ".env")
    exported = os.environ if environ is None else environ
    values.update({name: exported[name] for name in ENV_NAMES if name in exported})
    provider = values.get("RAREBRIDGE_AI_PROVIDER", "openai").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("RAREBRIDGE_AI_PROVIDER must be openai or anthropic")
    mode = values.get("RAREBRIDGE_AI_MODE", "auto").strip().lower()
    if mode not in MODES:
        raise ValueError("RAREBRIDGE_AI_MODE must be auto, live, cache or off")
    model = values.get("RAREBRIDGE_AI_MODEL", DEFAULT_MODELS[provider]).strip()
    if not model or len(model) > 150 or any(char.isspace() for char in model):
        raise ValueError("RAREBRIDGE_AI_MODEL must be a nonempty model ID")
    if provider == "anthropic" and not model.startswith("claude-"):
        raise ValueError("Select a Claude model ID for the Anthropic provider")
    if provider == "openai" and model.startswith("claude-"):
        raise ValueError("Select an OpenAI model ID for the OpenAI provider")
    workspace_id = values.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if len(workspace_id) > 150 or any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in workspace_id):
        raise ValueError("ANTHROPIC_WORKSPACE_ID must be a valid workspace identifier")
    try:
        timeout = float(values.get("RAREBRIDGE_AI_TIMEOUT_SECONDS", "40"))
        tokens = int(values.get("RAREBRIDGE_AI_MAX_OUTPUT_TOKENS", "6000"))
    except (TypeError, ValueError):
        raise ValueError("AI timeout and output-token settings must be numeric") from None
    if not 1 <= timeout <= 120 or not 256 <= tokens <= 12000:
        raise ValueError("AI timeout must be 1..120 seconds and output tokens 256..12000")
    cache_dir = Path(values.get("RAREBRIDGE_AI_CACHE_DIR", "rarebridge/ai/cache")).expanduser()
    if not cache_dir.is_absolute():
        cache_dir = WORKSPACE_ROOT / cache_dir
    return AIConfig(
        api_key=values.get(KEY_NAMES[provider], "").strip(), model=model, mode=mode,
        timeout_seconds=timeout, max_output_tokens=tokens, cache_dir=cache_dir,
        provider=provider, anthropic_workspace_id=workspace_id,
    )
