"""Generate and sync the GitHub Actions headless config from local state.

Two sync paths, tried in order:
1. A GitHub Personal Access Token configured in the panel (no CLI needed).
2. The locally installed `gh` CLI (auto-detected, no setup required here).

As a last resort the generated YAML can simply be copied and pasted into the
repo's `headless/config.yaml` on the GitHub website.
"""

from __future__ import annotations

import base64
import subprocess

import httpx
import yaml

REPO = "Frog755/fund-monitor-headless"
CONFIG_PATH = "headless/config.yaml"
COMMIT_MESSAGE = "Update monitor config from local panel"
_API = "https://api.github.com"

_CHANNELS_TEMPLATE = {
    "serverchan": {"send_key_env": "SCT_KEY"},
    "pushplus": {"token_env": "PUSHPLUS_TOKEN"},
}


def build_config(database) -> str:
    """Render the headless YAML from the local asset/rule repositories."""
    assets: list[dict] = []
    for asset in database.assets.list(enabled_only=True):
        ticker = _ticker_for(asset)
        if not ticker:
            continue
        entry: dict = {"name": asset.name, "code": ticker, "kind": asset.kind.value}
        threshold = _threshold_for(database, asset.id or 0)
        if threshold is not None:
            entry["threshold"] = float(threshold)
        assets.append(entry)

    config = {
        "timezone": "Asia/Shanghai",
        "assets": assets,
        "channels": _CHANNELS_TEMPLATE,
    }
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)


def _ticker_for(asset) -> str | None:
    tencent = asset.identifiers.get("tencent")
    if tencent:
        return tencent
    if asset.kind.value == "etf":
        code = asset.identifiers.get("eastmoney")
        if code:
            prefix = "sz" if code.startswith("1") else "sh"
            return f"{prefix}{code}"
    if asset.kind.value == "fund":
        code = asset.identifiers.get("eastmoney")
        if code:
            return f"jj{code}"
    return None


def _threshold_for(database, asset_id: int):
    for rule in database.rules.for_asset(asset_id):
        if rule.threshold is not None:
            return rule.threshold
    return None


def _run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _sync_via_token(content: str, repo: str, token: str) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(timeout=30, headers=headers) as client:
        fetch = client.get(f"{_API}/repos/{repo}/contents/{CONFIG_PATH}")
        if fetch.status_code == 404:
            raise RuntimeError(f"仓库或配置文件不存在：{repo}/{CONFIG_PATH}（请检查仓库名）")
        if fetch.status_code == 401:
            raise RuntimeError("GitHub Token 无效或已过期")
        if fetch.status_code != 200:
            raise RuntimeError(f"读取远程配置失败（HTTP {fetch.status_code}）")
        sha = fetch.json().get("sha", "")
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        update = client.put(
            f"{_API}/repos/{repo}/contents/{CONFIG_PATH}",
            json={
                "message": COMMIT_MESSAGE,
                "content": encoded,
                "sha": sha,
            },
        )
        if update.status_code not in (200, 201):
            raise RuntimeError(f"同步失败（HTTP {update.status_code}）：{update.text[:200]}")
    return f"已通过 GitHub Token 同步到 {repo}"


def _sync_via_gh_cli(content: str, repo: str) -> str:
    sha_result = _run_gh(f"repos/{repo}/contents/{CONFIG_PATH}", "--jq", ".sha")
    if sha_result.returncode != 0:
        raise RuntimeError(f"读取远程配置失败：{sha_result.stderr.strip()[:200]}")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    result = _run_gh(
        "-X", "PUT",
        f"repos/{repo}/contents/{CONFIG_PATH}",
        "-f", f"message={COMMIT_MESSAGE}",
        "-f", f"content={encoded}",
        "-f", f"sha={sha_result.stdout.strip()}",
    )
    if result.returncode != 0:
        raise RuntimeError(f"同步失败：{result.stderr.strip()[:200]}")
    return f"已通过 gh CLI 同步到 {repo}"


def sync_config(content: str, repo: str = REPO, token: str | None = None) -> str:
    """Sync with a GitHub token first, then fall back to the gh CLI."""
    if token:
        return _sync_via_token(content, repo, token)
    return _sync_via_gh_cli(content, repo)
