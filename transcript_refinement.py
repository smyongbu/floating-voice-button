from __future__ import annotations

import re
import unicodedata


_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_PROTECTED_TOKEN = re.compile(
    r"`[^`\r\n]*`"
    r"|(?:https?://|www\.)[^\s]+"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|(?:[A-Za-z]:\\|\\\\)[^\s]+"
    r"|\b[vV]?\d+(?:\.\d+)+\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|\b\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?\b"
    r"|\b[\w.-]+\.(?:py|js|ts|json|txt|md|exe|dll|ini|ya?ml|html|css)\b",
    re.IGNORECASE,
)
_REMOVABLE_ZERO_WIDTH = re.compile("[\u200b\ufeff]")
_ASCII_PUNCTUATION_OR_TOKEN_CHAR = ",.?!:;A-Za-z0-9_"


def _protect_tokens(text: str) -> tuple[str, dict[str, str]]:
    marker_by_token: dict[str, str] = {}
    token_by_marker: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        marker = marker_by_token.get(token)
        if marker is None:
            marker = f"\ue000{len(marker_by_token)}\ue001"
            marker_by_token[token] = marker
            token_by_marker[marker] = token
        return marker

    return _PROTECTED_TOKEN.sub(replace, text), token_by_marker


def _restore_tokens(text: str, token_by_marker: dict[str, str]) -> str:
    for marker, token in token_by_marker.items():
        text = text.replace(marker, token)
    return text


def _normalize_chinese_punctuation(text: str) -> str:
    mapping = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}
    text = re.sub(r"\s+([，。！？：；、,.!?:;])", r"\1", text)

    def replace(match: re.Match[str]) -> str:
        return mapping[match.group(1)]

    # 连续半角标点整体保留；紧接 ASCII 标识符字符的句点等符号也可能属于
    # 文件名、成员访问或编号。遇到这些有歧义的情况宁可不转换。
    text = re.sub(
        rf"(?<=[{_CJK}])([,?!:;])(?![{_ASCII_PUNCTUATION_OR_TOKEN_CHAR}])",
        replace,
        text,
    )
    text = re.sub(
        rf"(?<=[{_CJK}])(\.)(?![{_ASCII_PUNCTUATION_OR_TOKEN_CHAR}])"
        rf"(?![ \t]*[A-Za-z0-9_])",
        replace,
        text,
    )
    text = re.sub(rf"([，。！？：；、])\s+(?=[{_CJK}])", r"\1", text)
    return text


def refine_transcript(text: str) -> str:
    """只修正安全的空格和标点格式，不猜测词义，也不删改原话。"""
    cleaned = unicodedata.normalize("NFC", str(text or ""))
    # 只移除零宽空格和 BOM；U+200C/U+200D 会参与文字或表情连接，必须保留。
    cleaned = _REMOVABLE_ZERO_WIDTH.sub("", cleaned)
    protected, token_by_marker = _protect_tokens(cleaned)
    protected = protected.replace("\r\n", "\n").replace("\r", "\n")
    protected = re.sub(r"[ \t\f\v\u3000]+", " ", protected)
    protected = re.sub(r" *\n *", "\n", protected).strip()
    protected = _normalize_chinese_punctuation(protected)
    return _restore_tokens(protected.strip(), token_by_marker)
