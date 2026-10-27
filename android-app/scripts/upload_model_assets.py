"""使用本机 Git 已有登录上传三模型附件；不输出、保存或接收明文令牌参数。"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from bundle_models import APP_ROOT, asset_name, catalog, verify

REPOSITORY = "smyongbu/floating-voice-button"
MODEL_TAG = "voice-bundled-models-v1"


def authorization() -> str:
    result = subprocess.run(
        ["git", "-c", "credential.credentialStore=dpapi", "credential", "fill"],
        input=b"protocol=https\nhost=github.com\n\n", capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("请先通过 Git Credential Manager 完成 GitHub 登录")
    fields = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    if not fields.get("password"):
        raise RuntimeError("GitHub 登录不可用")
    raw = (fields.get("username", "x-access-token") + ":" + fields["password"]).encode()
    return "Basic " + base64.b64encode(raw).decode()


class GitHub:
    def __init__(self) -> None:
        self.auth = authorization()

    def headers(self) -> dict:
        return {"Authorization": self.auth, "User-Agent": "VoicePoint-Model-Build", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def request(self, method: str, path: str, body: dict | None = None):
        connection = http.client.HTTPSConnection("api.github.com", timeout=120)
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        headers = self.headers()
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, payload, headers)
            response = connection.getresponse()
            data = response.read()
            if response.status == 404:
                return None
            if response.status >= 300:
                raise RuntimeError(f"GitHub 请求失败，HTTP {response.status}")
            return json.loads(data) if data else None
        finally:
            connection.close()

    def upload(self, release_id: int, file: Path, expected_hash: str | None = None) -> None:
        assets = self.request("GET", f"/repos/{REPOSITORY}/releases/{release_id}/assets?per_page=100")
        existing = next((a for a in assets if a["name"] == file.name), None)
        if existing:
            if existing["state"] == "uploaded" and existing["size"] == file.stat().st_size and expected_hash and existing.get("digest") == "sha256:" + expected_hash:
                print("复用已校验附件：" + file.name, flush=True)
                return
            if existing["state"] != "uploaded":
                self.request("DELETE", f"/repos/{REPOSITORY}/releases/assets/{existing['id']}")
            else:
                raise RuntimeError("同名附件已存在且尚未确认哈希，请检查：" + file.name)
        size = file.stat().st_size
        if size >= 2 * 1024**3:
            raise ValueError("附件超过 GitHub 2 GiB 限制")
        connection = http.client.HTTPSConnection("uploads.github.com", timeout=180)
        try:
            connection.putrequest("POST", f"/repos/{REPOSITORY}/releases/{release_id}/assets?name={quote(file.name)}")
            for key, value in self.headers().items():
                connection.putheader(key, value)
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("Content-Length", str(size))
            connection.endheaders()
            sent = 0
            started = last_report = time.monotonic()
            with file.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    connection.send(chunk)
                    sent += len(chunk)
                    now = time.monotonic()
                    if now - last_report >= 20:
                        rate = sent / max(now - started, .001)
                        print(f"上传 {file.name}: {sent / size:.1%}，{rate / 1024**2:.1f} MiB/s，剩余约 {(size - sent) / rate:.0f} 秒", flush=True)
                        last_report = now
            response = connection.getresponse()
            data = response.read()
            if response.status != 201:
                raise RuntimeError(f"GitHub 附件上传失败，HTTP {response.status}")
            asset = json.loads(data)
            if asset["size"] != size or (expected_hash and asset.get("digest") not in (None, "sha256:" + expected_hash)):
                raise ValueError("远端附件校验失败")
            print("附件上传完成：" + file.name, flush=True)
        finally:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=APP_ROOT / "local-resources/github-model-assets")
    args = parser.parse_args()
    import hashlib
    resources = catalog()
    distribution = json.loads((args.directory / "bundled-models.json").read_text(encoding="utf-8")).get("releaseFiles", {})
    uploads = []
    for resource in resources:
        for item in resource["files"]:
            name = asset_name(resource, item)
            for asset in distribution.get(name, [{"name": name, **item}]):
                file = args.directory / asset["name"]
                verify(file, asset)
                uploads.append((file, asset["sha256"]))
    client = GitHub()
    endpoint = f"/repos/{REPOSITORY}/releases"
    release = client.request("GET", endpoint + "/tags/" + MODEL_TAG)
    if release is None:
        release = client.request("POST", endpoint, {
            "tag_name": MODEL_TAG, "target_commitish": "main",
            "name": "语点三模型构建资源 v1", "prerelease": True, "draft": False,
            "body": "用于语点自带三模型安装包的构建资源。文件版本、来源、许可证、大小与 SHA-256 见 bundled-models.json；不含录音、历史或凭据。",
        })
    print("模型资源页：" + release["html_url"], flush=True)
    # 只清理本轮大文件上传中断留下的未完成占位附件。
    existing_assets = client.request("GET", endpoint + f"/{release['id']}/assets?per_page=100")
    for asset in existing_assets:
        if asset["name"] in distribution and asset["state"] != "uploaded":
            client.request("DELETE", f"/repos/{REPOSITORY}/releases/assets/{asset['id']}")
    def upload_one(entry):
        file, digest = entry
        for attempt in range(3):
            try:
                client.upload(release["id"], file, digest)
                return
            except (OSError, http.client.HTTPException):
                if attempt == 2:
                    raise
                print(f"附件连接中断，重试 {attempt + 1}/2：{file.name}", flush=True)
                time.sleep(3 * (attempt + 1))
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(upload_one, uploads))
    manifest = args.directory / "bundled-models.json"
    client.upload(release["id"], manifest, hashlib.sha256(manifest.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
