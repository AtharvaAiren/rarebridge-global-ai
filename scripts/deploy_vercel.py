#!/usr/bin/env python3
"""Credential-safe Vercel preparation and explicit production deployment.

prepare is offline and does not read .env. probe is read-only. configure changes
only allowlisted production environment variables. Project creation is explicit.
deploy configures those variables, then publishes through the installed CLI.
Never source .env, pass secrets as arguments, or echo provider/CLI responses.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 2_000_000
SETTINGS = {
    "VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID",
    "RAREBRIDGE_AI_PROVIDER", "RAREBRIDGE_AI_MODEL", "RAREBRIDGE_AI_MODE",
    "RAREBRIDGE_AI_TIMEOUT_SECONDS", "RAREBRIDGE_AI_MAX_OUTPUT_TOKENS",
    "RAREBRIDGE_AI_CACHE_DIR",
}
SECRET_NAMES = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"}
CLI_ENV_NAMES = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "SYSTEMROOT", "WINDIR",
                 "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "CI",
                 "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                 "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                 "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"}


class DeploymentError(Exception):
    """Messages are fixed diagnostics, never arbitrary remote response text."""

    def __init__(self, message, http_status=None):
        super().__init__(message)
        self.http_status = http_status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise DeploymentError("Vercel API redirect rejected; credentials were not forwarded.")


def read_settings(root=ROOT, environ=None):
    """Read allowlisted literal settings silently; exports override local .env."""
    values = {}
    path = root / ".env"
    try:
        if path.is_file():
            if path.stat().st_size > 32_768:
                raise DeploymentError("Local .env exceeds the configuration size limit.")
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:].strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if key not in SETTINGS:
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                elif " #" in value:
                    value = value.split(" #", 1)[0].rstrip()
                values[key] = value
    except (OSError, UnicodeError):
        raise DeploymentError("Could not read local configuration.") from None
    exported = os.environ if environ is None else environ
    values.update({key: exported[key] for key in SETTINGS if key in exported})
    return values


def safe_identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}", value):
        raise DeploymentError("Provide a valid " + name + " identifier or name.")
    return value


def api_request(token, path, *, method="GET", payload=None, opener=None):
    """Only api.vercel.com, no redirects, bounded JSON, no raw error details."""
    if not isinstance(token, str) or not token.strip() or len(token) > 4_096 or any(c.isspace() for c in token):
        raise DeploymentError("Set a valid VERCEL_TOKEN locally or in the exported environment.")
    if not path.startswith("/") or path.startswith("//"):
        raise DeploymentError("Invalid Vercel API path.")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request("https://api.vercel.com" + path, data=body, method=method,
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json", "Accept": "application/json"})
    opener = opener or build_opener(NoRedirects())
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise DeploymentError("Vercel API response exceeded the size limit.")
    except HTTPError as exc:
        status = exc.code
        exc.close()
        diagnoses = {401: "Vercel rejected the deployment token.",
                     403: "The token cannot access this Vercel project or scope.",
                     404: "The selected Vercel project or scope was not found.",
                     402: "Vercel requires an account billing change.",
                     409: "Vercel reported a conflicting project update.",
                     429: "Vercel request limit reached; retry later."}
        raise DeploymentError(diagnoses.get(status, "Vercel API request failed (HTTP " + str(status) + ")."), status) from None
    except (URLError, TimeoutError, OSError):
        raise DeploymentError("Could not reach Vercel securely within the request timeout.") from None
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError):
        raise DeploymentError("Vercel returned invalid JSON.") from None
    if not isinstance(result, dict):
        raise DeploymentError("Vercel returned an unexpected response shape.")
    return result


def scope_query(scope):
    if not scope:
        return {}
    scope = safe_identifier(scope, "scope")
    return {"teamId" if scope.startswith("team_") else "slug": scope}


def linked_project(root=ROOT):
    path = root / ".vercel/project.json"
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > 32_768:
            raise DeploymentError("Local Vercel linkage is oversized; specify the intended project explicitly.")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"id": safe_identifier(data.get("projectId"), "linked project"),
                "accountId": safe_identifier(data.get("orgId"), "linked account")}
    except (OSError, ValueError, AttributeError):
        raise DeploymentError("Local Vercel linkage is invalid; specify the intended project explicitly.") from None


def resolve_project(settings, project, scope=None, request=api_request, *, root=ROOT, create_project=False):
    """Resolve real account/project IDs before any environment mutation."""
    linkage = None
    if not project:
        if create_project:
            project = "rarebridge-global-ai"
        else:
            linkage = linked_project(root)
            if not linkage:
                raise DeploymentError("Choose --project explicitly or provide matching existing Vercel linkage.")
            if (settings.get("VERCEL_PROJECT_ID", linkage["id"]) != linkage["id"]
                    or settings.get("VERCEL_ORG_ID", linkage["accountId"]) != linkage["accountId"]):
                raise DeploymentError("Exported project/account settings conflict with local linkage; choose --project explicitly.")
            project = linkage["id"]
    project = safe_identifier(project, "project")
    org_id = linkage["accountId"] if linkage else settings.get("VERCEL_ORG_ID", "")
    selected_scope = scope or (org_id if org_id.startswith("team_") else "")
    query = scope_query(selected_scope)
    path = "/v9/projects/" + quote(project, safe="")
    if query:
        path += "?" + urlencode(query)
    try:
        result = request(settings.get("VERCEL_TOKEN", ""), path)
    except DeploymentError as exc:
        if not create_project or exc.http_status != 404:
            raise
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", project) or project.startswith("prj_"):
            raise DeploymentError("Creating a project requires a lowercase project slug, not an ID.") from None
        create_path = "/v11/projects" + ("?" + urlencode(query) if query else "")
        result = request(settings.get("VERCEL_TOKEN", ""), create_path, method="POST",
                         payload={"name": project, "framework": "fastapi"})
    project_id = safe_identifier(result.get("id"), "resolved project")
    account_id = safe_identifier(result.get("accountId"), "resolved account")
    if not project_id.startswith("prj_"):
        raise DeploymentError("Vercel did not return a real project ID.")
    name = safe_identifier(result.get("name"), "resolved project name")
    if linkage and (project_id != linkage["id"] or account_id != linkage["accountId"]):
        raise DeploymentError("Resolved project differs from local linkage; specify the intended project explicitly.")
    return {"id": project_id, "accountId": account_id, "name": name}


def production_environment(settings, root=ROOT):
    """Select one provider only; never deploy the Vercel token or a local path."""
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from rarebridge.ai.config import KEY_NAMES, load_config
    try:
        config = load_config(environ=settings, env_path=root / ".env")
    except (ValueError, OSError):
        raise DeploymentError("AI provider settings are invalid; correct local configuration before publishing.") from None
    if not config.api_key:
        raise DeploymentError("The selected AI provider key is missing; production inference cannot be enabled.")
    if config.mode not in {"auto", "live"}:
        raise DeploymentError("Set RAREBRIDGE_AI_MODE to auto or live for the production inference deployment.")
    # Serverless application files may be read-only. /tmp caching is best effort
    # and ephemeral; it is neither a durable cache nor a shipped demonstration.
    values = {KEY_NAMES[config.provider]: config.api_key,
              "RAREBRIDGE_AI_PROVIDER": config.provider,
              "RAREBRIDGE_AI_MODEL": config.model,
              "RAREBRIDGE_AI_MODE": config.mode,
              "RAREBRIDGE_AI_TIMEOUT_SECONDS": str(min(config.timeout_seconds, 100)),
              "RAREBRIDGE_AI_MAX_OUTPUT_TOKENS": str(config.max_output_tokens),
              "RAREBRIDGE_AI_CACHE_DIR": "/tmp/rarebridge-ai-cache"}
    if config.provider == "anthropic" and config.anthropic_workspace_id:
        values["ANTHROPIC_WORKSPACE_ID"] = config.anthropic_workspace_id
    return values


def configure_production(settings, project, *, root=ROOT, request=api_request):
    values = production_environment(settings, root)
    payload = [{"key": key, "value": value,
                "type": "encrypted" if key in SECRET_NAMES else "plain", "target": ["production"]}
               for key, value in values.items()]
    query = {"upsert": "true"}
    if project["accountId"].startswith("team_"):
        query["teamId"] = project["accountId"]
    path = "/v10/projects/" + quote(project["id"], safe="") + "/env?" + urlencode(query)
    result = request(settings.get("VERCEL_TOKEN", ""), path, method="POST", payload=payload)
    if not isinstance(result.get("failed"), list) or result["failed"]:
        raise DeploymentError("Vercel rejected at least one production environment update; deployment stopped.")
    created = result.get("created")
    if isinstance(created, dict):
        created = [created]
    if (not isinstance(created, list) or len(created) != len(values)
            or {item.get("key") for item in created if isinstance(item, dict)} != set(values)):
        raise DeploymentError("Vercel did not confirm the production environment update; deployment stopped.")
    return {"provider": values["RAREBRIDGE_AI_PROVIDER"], "configured_variable_names": sorted(values)}


def cli_command(root=ROOT):
    node = root / ".tools/node-v22.23.3-darwin-arm64/bin/node"
    cli = root / ".tools/node_modules/vercel/dist/index.js"
    if cli.is_file():
        binary = str(node) if node.is_file() else shutil.which("node")
        if not binary:
            raise DeploymentError("Node.js is unavailable for the installed Vercel CLI.")
        return [binary, str(cli)]
    binary = shutil.which("vercel")
    if not binary:
        raise DeploymentError("Install Vercel CLI before deploying.")
    return [binary]


def deploy_project(settings, project, *, root=ROOT, runner=subprocess.run):
    command = cli_command(root) + ["deploy", "--prod", "--yes", "--no-color",
                                   "--global-config", str(root / ".tools/vercel-config")]
    # Pass only the deployment credential. AI keys were sent directly to the
    # project's production environment, never as CLI arguments or public values.
    child_env = {key: value for key, value in os.environ.items() if key in CLI_ENV_NAMES}
    child_env.update({"VERCEL_TOKEN": settings.get("VERCEL_TOKEN", ""),
                      "VERCEL_ORG_ID": project["accountId"], "VERCEL_PROJECT_ID": project["id"],
                      "NO_UPDATE_NOTIFIER": "1", "VERCEL_TELEMETRY_DISABLED": "1",
                      "XDG_CACHE_HOME": str(root / ".tools/vercel-cache")})
    if len(command) > 1 and command[0].endswith("/node"):
        child_env["PATH"] = str(Path(command[0]).parent) + os.pathsep + child_env.get("PATH", "")
    try:
        # CLI output is captured and discarded except a validated deployment URL.
        result = runner(command, cwd=root, env=child_env, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, timeout=900, check=False)
    except subprocess.TimeoutExpired:
        raise DeploymentError("Vercel CLI exceeded the deployment timeout; check the project's deployments before retrying.") from None
    except OSError:
        raise DeploymentError("Could not start the Vercel CLI.") from None
    if result.returncode:
        combined = ((result.stdout or "") + (result.stderr or ""))[:MAX_RESPONSE_BYTES].casefold()
        if "token" in combined and any(word in combined for word in ("invalid", "expired", "unauthorized")):
            message = "Vercel CLI rejected the deployment token."
        elif "build failed" in combined or "exited with" in combined:
            message = "Vercel deployment build failed; inspect its cloud build log without sharing secrets."
        else:
            message = "Vercel CLI deployment failed; inspect the selected project's deployment status."
        raise DeploymentError(message)
    urls = re.findall(r"(?m)^https://[a-z0-9][a-z0-9.-]*\.vercel\.app/?$", (result.stdout or "")[:MAX_RESPONSE_BYTES].strip())
    if not urls:
        raise DeploymentError("Vercel CLI did not return a verified deployment URL; inspect the project's deployments.")
    return {"deployment_url": urls[-1], "cli_completed": True, "public_smoke_test": "pending"}


def prepare(root=ROOT):
    """Read deployment config only; no credential reads, network or mutation."""
    required = ["app.py", "pyproject.toml", "package.json", "vercel.json", ".vercelignore",
                "frontend/package.json", "frontend/package-lock.json",
                "rarebridge/data/graph.json", "rarebridge/data/disorders.json",
                "rarebridge/data/source-manifest.json", "curation/atlas-overlay.json",
                "handoffs/contracts/overlay.schema.json"]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise DeploymentError("Deployment inputs are incomplete: " + ", ".join(missing))
    try:
        config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        cli = root / ".tools/node_modules/vercel/package.json"
        cli_version = json.loads(cli.read_text(encoding="utf-8")).get("version") if cli.is_file() else "system CLI"
    except (OSError, ValueError):
        raise DeploymentError("Deployment configuration is not valid JSON.") from None
    if config.get("framework") != "fastapi" or config.get("buildCommand") != "npm run build":
        raise DeploymentError("The FastAPI deployment framework/build command needs review.")
    if not package.get("scripts", {}).get("build"):
        raise DeploymentError("The frontend build command is missing.")
    cli_command(root)
    return {"status": "prepared", "credential_read": False, "network_used": False,
            "frontend_build_present": (root / "frontend/dist/index.html").is_file(),
            "cli_version": cli_version, "cloud_build_verified": False,
            "next": "Supply VERCEL_TOKEN and choose the intended project/scope, then run probe or deploy."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "probe", "configure", "deploy"))
    parser.add_argument("--project", help="Existing Vercel project name or ID")
    parser.add_argument("--scope", help="Vercel team slug or team ID; omit for the token's personal account")
    parser.add_argument("--create-project", action="store_true",
                        help="Create the selected project only if missing; defaults to rarebridge-global-ai")
    args = parser.parse_args(argv)
    if args.create_project and args.action not in {"configure", "deploy"}:
        parser.error("--create-project applies only to explicit configure/deploy actions")
    try:
        if args.action == "prepare":
            result = prepare()
        else:
            settings = read_settings()
            if not settings.get("VERCEL_TOKEN"):
                raise DeploymentError("Set VERCEL_TOKEN in the local .env or exported environment before contacting Vercel.")
            if args.action == "probe" and not args.project and not linked_project():
                result = api_request(settings["VERCEL_TOKEN"], "/v2/user")
                if not isinstance(result.get("user"), dict):
                    raise DeploymentError("Vercel did not confirm the authenticated user.")
                result = {"token_authenticated": True, "project_access_verified": False,
                          "mutation_performed": False}
            else:
                # Validate provider settings before creating or changing a project.
                if args.action in {"configure", "deploy"}:
                    prepare()
                    production_environment(settings)
                project = resolve_project(settings, args.project, args.scope,
                                          create_project=args.create_project)
                result = {"project_access_verified": True, "project": project["name"]}
                if args.action == "probe":
                    result["mutation_performed"] = False
                else:
                    result.update(configure_production(settings, project))
                    if args.action == "deploy":
                        result.update(deploy_project(settings, project))
        print(json.dumps(result, indent=2))
        return 0
    except DeploymentError as exc:
        print(json.dumps({"status": "blocked", "message": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "message": "Deployment preparation failed; review local configuration and tooling."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
