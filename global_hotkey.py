from __future__ import annotations

from dataclasses import dataclass


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": ("Ctrl", MOD_CONTROL),
    "control": ("Ctrl", MOD_CONTROL),
    "alt": ("Alt", MOD_ALT),
    "shift": ("Shift", MOD_SHIFT),
    "win": ("Win", MOD_WIN),
    "windows": ("Win", MOD_WIN),
    "meta": ("Win", MOD_WIN),
}
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
_NAMED_KEYS = {
    "space": ("Space", 0x20),
    "enter": ("Enter", 0x0D),
    "home": ("Home", 0x24),
    "end": ("End", 0x23),
    "pageup": ("PageUp", 0x21),
    "pagedown": ("PageDown", 0x22),
    "insert": ("Insert", 0x2D),
}


@dataclass(frozen=True)
class ParsedHotkey:
    label: str
    modifiers: int
    virtual_key: int


def parse_hotkey(value: object) -> ParsedHotkey:
    """解析并规范化 Windows 全局快捷键。"""
    text = str(value or "").strip()
    parts = [part.strip() for part in text.split("+") if part.strip()]
    if not parts:
        raise ValueError("请输入全局快捷键，例如 Ctrl+Alt+Space。")

    modifiers: dict[str, int] = {}
    main_key: tuple[str, int] | None = None
    for part in parts:
        lowered = part.casefold().replace(" ", "")
        modifier = _MODIFIERS.get(lowered)
        if modifier is not None:
            modifiers[modifier[0]] = modifier[1]
            continue
        if main_key is not None:
            raise ValueError("快捷键只能包含一个主按键。")
        if len(part) == 1 and part.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            canonical = part.upper()
            main_key = (canonical, ord(canonical))
            continue
        if lowered.startswith("f") and lowered[1:].isdigit():
            number = int(lowered[1:])
            if 1 <= number <= 24:
                main_key = (f"F{number}", 0x70 + number - 1)
                continue
        named = _NAMED_KEYS.get(lowered)
        if named is None:
            raise ValueError("主按键仅支持字母、数字、F1～F24、空格等常用按键。")
        main_key = named

    if main_key is None:
        raise ValueError("快捷键还需要一个主按键。")
    is_function_key = main_key[0].startswith("F") and main_key[0][1:].isdigit()
    if not is_function_key and not any(name in modifiers for name in ("Ctrl", "Alt", "Win")):
        raise ValueError("普通按键必须包含 Ctrl、Alt 或 Win；F1～F24 可以单独使用。")

    modifier_flags = MOD_NOREPEAT
    ordered_labels: list[str] = []
    for name in _MODIFIER_ORDER:
        if name in modifiers:
            ordered_labels.append(name)
            modifier_flags |= modifiers[name]
    ordered_labels.append(main_key[0])
    return ParsedHotkey("+".join(ordered_labels), modifier_flags, main_key[1])


def normalize_hotkey(value: object, fallback: str = "Ctrl+Alt+Space") -> str:
    try:
        return parse_hotkey(value).label
    except ValueError:
        return parse_hotkey(fallback).label
