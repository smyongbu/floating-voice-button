from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import Any

from local_asr import (
    FASTER_WHISPER_MODEL_ID,
    QWEN3_17_MODEL_ID,
    QWEN3_MODEL_ID,
    _model_directories,
)
from model_download import DownloadSpec, ModelDownloadManager
from realtime_asr import (
    DEFAULT_REALTIME_MODEL,
    ZIPFORMER_REALTIME_MODEL,
    _model_paths,
)


MODEL_FILES: dict[str, dict[str, Any]] = {
    DEFAULT_REALTIME_MODEL: {
        "version": "csukuangfj/streaming-paraformer@main",
        "base": "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/main/",
        "files": {
            "encoder.int8.onnx": (165_462_184, "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a", "encoder.int8.onnx"),
            "decoder.int8.onnx": (71_664_561, "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f", "decoder.int8.onnx"),
            "tokens.txt": (75_756, "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6", "tokens.txt"),
        },
    },
    ZIPFORMER_REALTIME_MODEL: {
        "version": "csukuangfj/zipformer@8a7306b4d4d40c3cb1bdb80e8f2f605167570af3",
        "base": "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/resolve/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/",
        "files": {
            "encoder-epoch-99-avg-1.int8.onnx": (42_980_793, "db6f51551762e40e549166fe041ea3e45464370b595e9ad23f06478ec3794fbb", "exp/32/encoder-epoch-99-avg-1.int8.onnx"),
            "decoder-epoch-99-avg-1.onnx": (13_877_276, "89be509a83175261695bdef5fd1c7b9ab1129a663d1284e7ba9f8507b21e0906", "exp/32/decoder-epoch-99-avg-1.onnx"),
            "joiner-epoch-99-avg-1.int8.onnx": (3_228_485, "bdda356d6f9b8c2d7cee9ee0e26075fa537490f7fd06520be408d287073667b9", "exp/32/joiner-epoch-99-avg-1.int8.onnx"),
            "tokens.txt": (56_317, "a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3", "data/lang_char_bpe/tokens.txt"),
        },
    },
    FASTER_WHISPER_MODEL_ID: {
        "version": "Systran/faster-whisper-small@2ec96c5472da50d38d40c0cfe0602af2e94b4c8a",
        "base": "https://huggingface.co/Systran/faster-whisper-small/resolve/2ec96c5472da50d38d40c0cfe0602af2e94b4c8a/",
        "files": {
            "config.json": (2_370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828", "config.json"),
            "model.bin": (483_546_902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671", "model.bin"),
            "tokenizer.json": (2_203_239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab", "tokenizer.json"),
            "vocabulary.txt": (459_861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913", "vocabulary.txt"),
        },
    },
    QWEN3_MODEL_ID: {
        "version": "csukuangfj2/qwen3-asr-0.6b@2cc50d1abfe4d4f2df8d71f536d108bb40f943d2",
        "base": "https://huggingface.co/csukuangfj2/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/resolve/2cc50d1abfe4d4f2df8d71f536d108bb40f943d2/",
        "files": {
            "conv_frontend.onnx": (44_148_281, "d22dc4423e0940e49884e903d2ea2f7e5567c14fc1aed97e4e26d6b8f208ef9e", "conv_frontend.onnx"),
            "decoder.int8.onnx": (756_563_239, "61e5f8249f9e7c82d5e01e1938c79fb3f5b3135f91664928033029e42451bd18", "decoder.int8.onnx"),
            "encoder.int8.onnx": (182_491_662, "60748d3e6744a57c9c91e1b17424a6c2990567e8adceb0783940c03ed98fa9d9", "encoder.int8.onnx"),
            "tokenizer/merges.txt": (1_671_853, "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5", "tokenizer/merges.txt"),
            "tokenizer/tokenizer_config.json": (12_487, "4942d005604266809309cabc9f4e9cb89ce855d59b14681fdc0e1cc62ea26c4c", "tokenizer/tokenizer_config.json"),
            "tokenizer/vocab.json": (2_776_833, "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910", "tokenizer/vocab.json"),
        },
    },
    QWEN3_17_MODEL_ID: {
        "version": "handy-computer/qwen3-asr-1.7b@92282af1610a2db19d66f2bef1e260f5deca782d",
        "base": "https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/resolve/92282af1610a2db19d66f2bef1e260f5deca782d/",
        "files": {
            "Qwen3-ASR-1.7B-Q5_K_M.gguf": (1_517_290_464, "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0", "Qwen3-ASR-1.7B-Q5_K_M.gguf"),
        },
    },
}


def _target_directory(model_id: str) -> Path:
    if model_id in (DEFAULT_REALTIME_MODEL, ZIPFORMER_REALTIME_MODEL):
        _normalized, _spec, source, local = _model_paths(model_id)
    else:
        source, local = _model_directories(model_id)
    return local if getattr(sys, "frozen", False) else source


def build_grouped_download_specs() -> dict[str, list[DownloadSpec]]:
    groups: dict[str, list[DownloadSpec]] = {}
    for model_id, metadata in MODEL_FILES.items():
        target_root = _target_directory(model_id)
        specs = []
        for index, (relative, (size, digest, remote)) in enumerate(metadata["files"].items()):
            target = target_root.joinpath(*PurePosixPath(relative).parts)
            specs.append(DownloadSpec(
                resource_id=f"{model_id}::{index}",
                url=f"{metadata['base']}{remote}?download=true",
                target_path=target,
                version=f"{metadata['version']}::{relative}",
                total_size=size,
                sha256=digest,
            ))
        groups[model_id] = specs
    return groups


class GroupedModelDownloadManager:
    def __init__(self, groups: dict[str, list[DownloadSpec]], *, run_log, error_log) -> None:
        self._groups = {key: tuple(value) for key, value in groups.items()}
        specs = {spec.resource_id: spec for values in groups.values() for spec in values}
        self._manager = ModelDownloadManager(specs, run_log=run_log, error_log=error_log)

    @property
    def resource_ids(self) -> tuple[str, ...]:
        return tuple(self._groups)

    def _snapshots(self, model_id: str) -> list[dict[str, Any]]:
        return [self._manager.status(spec.resource_id) for spec in self._groups[str(model_id)]]

    @staticmethod
    def _aggregate(model_id: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        states = {str(item.get("state") or "not_started") for item in snapshots}
        if snapshots and all(item.get("state") == "completed" and item.get("verified") is True for item in snapshots): state = "completed"
        elif "failed" in states: state = "failed"
        elif "deleting" in states: state = "deleting"
        elif "cancelling" in states: state = "cancelling"
        elif "pausing" in states: state = "pausing"
        elif states & {"queued", "downloading"}: state = "downloading"
        elif "verifying" in states: state = "verifying"
        elif "paused" in states: state = "paused"
        else: state = "not_started"
        total = sum(int(item.get("total_bytes") or 0) for item in snapshots)
        downloaded = sum(int(item.get("downloaded_bytes") or 0) for item in snapshots)
        installed = sum(int(item.get("installed_bytes") or 0) for item in snapshots)
        errors = [str(item.get("error") or "") for item in snapshots if item.get("error")]
        return {"resource_id": model_id, "state": state, "total_bytes": total, "downloaded_bytes": downloaded, "installed_bytes": installed, "percent": 100.0 if state == "completed" else (downloaded * 100.0 / total if total else 0.0), "verified": state == "completed", "installed": state == "completed", "error": errors[0] if errors else ""}

    def status(self, model_id: str) -> dict[str, Any]:
        return self._aggregate(model_id, self._snapshots(model_id))

    def start(self, model_id: str) -> dict[str, Any]:
        for spec in self._groups[str(model_id)]: self._manager.start(spec.resource_id)
        return self.status(model_id)

    def pause(self, model_id: str) -> dict[str, Any]:
        for spec in self._groups[str(model_id)]: self._manager.pause(spec.resource_id)
        return self.status(model_id)

    def cancel(self, model_id: str) -> dict[str, Any]:
        for spec in self._groups[str(model_id)]: self._manager.cancel(spec.resource_id)
        return self.status(model_id)

    def delete(self, model_id: str) -> dict[str, Any]:
        if not getattr(sys, "frozen", False):
            raise PermissionError("源码版不得从软件内删除共享模型仓库中的规范文件。")
        for spec in self._groups[str(model_id)]: self._manager.delete(spec.resource_id)
        return self.status(model_id)

    def shutdown(self, wait_seconds: float = 2.0) -> None:
        self._manager.shutdown(wait_seconds=wait_seconds)
