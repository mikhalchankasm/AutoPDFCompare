"""Run-folder names derived from the two PDFs being compared.

A comparison folder is named after the pair it holds ("Проект_R5_vs_R6"), not
after the clock: the GUI's "generate name" button, the MCP `prepare` tool and
anything else that needs a folder name go through here so they agree.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from .runner import MAX_RUN_FOLDER_NAME_LEN, sanitize_run_folder_name

# One-character tokens count: "R5" and "5" are the revision markers we are after.
NAME_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]+")


def extract_revision(stem: str) -> str | None:
    """The revision marker of a file name, prefix included: "plan_r1" -> "R1".

    The prefix is part of the answer: "plan_1_vs_2" reads like a page range, while
    "plan_R1_vs_R2" says what it is.
    """
    patterns = [
        r"(?i)(?:^|[^A-Za-zА-Яа-я0-9])((?:rev(?:ision)?|r|рев|ревизия|р)[-_ ]*[A-Za-zА-Яа-я]*\d+[A-Za-zА-Яа-я]*)\b",
        r"(?i)([A-Za-zА-Яа-я]{1,3}\d{1,4}[A-Za-zА-Яа-я]{0,2})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if match:
            return re.sub(r"[-_ ]+", "", match.group(1)).upper()
    return None


def common_prefix_tokens(left: str, right: str) -> list[str]:
    left_tokens = NAME_TOKEN_RE.findall(left)
    right_tokens = NAME_TOKEN_RE.findall(right)
    common: list[str] = []
    for left_token, right_token in zip(left_tokens, right_tokens, strict=False):
        if left_token.casefold() != right_token.casefold():
            break
        common.append(left_token)
    return common


def compact_name(name: str, max_len: int = 70) -> str:
    normalized = re.sub(r"\s+", "_", str(name or "").strip(), flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip(" ._")
    if not normalized:
        normalized = "Comparison"
    if len(normalized) > max_len:
        normalized = normalized[:max_len].rstrip(" ._")
    return sanitize_run_folder_name(normalized)


def available_folder_name(out_dir: Path, raw_name: str) -> str:
    """`raw_name`, or the first `raw_name_N` that does not exist in `out_dir`."""
    base = compact_name(raw_name, MAX_RUN_FOLDER_NAME_LEN)
    candidate = base
    index = 2
    while (out_dir / candidate).exists():
        suffix = f"_{index}"
        candidate = sanitize_run_folder_name(f"{base[: max(1, MAX_RUN_FOLDER_NAME_LEN - len(suffix))]}{suffix}")
        index += 1
    return sanitize_run_folder_name(candidate)


def _pair_base(old_stem: str, new_stem: str) -> str:
    """What the two file names have in common — the part worth keeping once."""
    common = common_prefix_tokens(old_stem, new_stem)
    if common:
        return compact_name("_".join(common[:8]), max_len=60)
    prefix = os.path.commonprefix([old_stem, new_stem]).strip(" ._-")
    return compact_name(prefix or old_stem[:36], max_len=60)


def _drop_revision_words(base: str, old_rev: str, new_rev: str) -> str:
    """Strip base tokens the revision markers already carry.

    "Проект_Ревизия 5" and "Проект_Ревизия 6" share the token "Ревизия", and it is
    also the head of both markers — kept, the name reads "Проект_Ревизия_РЕВИЗИЯ5…".
    """
    tokens = NAME_TOKEN_RE.findall(base)
    while tokens:
        tail = tokens[-1].upper()
        if not (old_rev.startswith(tail) and new_rev.startswith(tail)):
            break
        tokens.pop()
    return "_".join(tokens)


def suggest_run_folder_name(old_path: Path, new_path: Path) -> str:
    """The one name to offer for this pair: shared part + both revisions.

    "Проект_рев5.pdf" vs "Проект_рев6.pdf" gives "Проект_РЕВ5_vs_РЕВ6" — the
    shared part is written once, which is the whole point of the button.
    """
    old_stem = old_path.stem
    new_stem = new_path.stem
    old_rev = extract_revision(old_stem)
    new_rev = extract_revision(new_stem)
    base = _pair_base(old_stem, new_stem)
    if old_rev and new_rev and old_rev != new_rev:
        base = _drop_revision_words(base, old_rev, new_rev)
        pair = f"{old_rev}_vs_{new_rev}"
        return compact_name(f"{base}_{pair}" if base else pair, MAX_RUN_FOLDER_NAME_LEN)
    if old_stem.casefold() == new_stem.casefold():
        return compact_name(f"{base}_old_vs_new", MAX_RUN_FOLDER_NAME_LEN)
    return compact_name(
        f"{compact_name(old_stem, 32)}_vs_{compact_name(new_stem, 32)}", MAX_RUN_FOLDER_NAME_LEN
    )


def suggest_folder_names(old_path: Path, new_path: Path, out_dir: Path) -> list[dict[str, str]]:
    """Several named options with a reason each — what the MCP `prepare` tool offers."""
    old_stem = old_path.stem
    new_stem = new_path.stem
    old_rev = extract_revision(old_stem)
    new_rev = extract_revision(new_stem)
    base = _pair_base(old_stem, new_stem)

    today = datetime.now().strftime("%Y-%m-%d")
    raw_suggestions: list[tuple[str, str]] = []
    if old_rev and new_rev:
        raw_suggestions.append((f"{base}_{old_rev}_vs_{new_rev}", "общая часть имени + найденные ревизии"))
    raw_suggestions.extend(
        [
            (f"{base}_old_vs_new", "нейтральное имя для пары старый/новый"),
            (f"{compact_name(old_stem, 36)}_vs_{compact_name(new_stem, 36)}", "полные имена обоих PDF"),
            (f"Comparison_{today}_{base}", "дата запуска + общий идентификатор документов"),
        ]
    )

    seen: set[str] = set()
    suggestions: list[dict[str, str]] = []
    for raw_name, reason in raw_suggestions:
        try:
            name = available_folder_name(out_dir, raw_name)
        except ValueError:
            continue
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        suggestions.append({"name": name, "reason": reason})
        if len(suggestions) >= 4:
            break
    return suggestions
