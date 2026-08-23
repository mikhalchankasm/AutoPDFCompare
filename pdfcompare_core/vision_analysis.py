from __future__ import annotations

import base64
import json
import os
import re
import shutil
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import cv2
import numpy as np

from .pdf_io import find_pages_dir, internal_dir
from .vision_report_ui import vision_index_html, vision_sheet_html


DEFAULT_DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"
DEFAULT_QWEN_VISION_MODEL = "qwen3.8-max"
DEEPSEEK_API_BASE_URL = "https://api.deepseek.com"
PROMPT_VERSION = 1


_ERRORS = {
    "ru": {
        "api_key_missing": "Не задан {env_var} для AI-провайдера {provider} в окружении MCP-сервера.",
        "api_unavailable": "{provider} API временно недоступен или вернул некорректный ответ.",
        "api_no_choices": "{provider} API не вернул вариант ответа.",
        "api_empty": "{provider} не сформировал текстовое описание.",
        "qwen_base_url_missing": "Не задан QWEN_BASE_URL для Qwen в окружении MCP-сервера.",
        "qwen_base_url_invalid": (
            "QWEN_BASE_URL должен быть официальным HTTPS endpoint Alibaba Model Studio "
            "с окончанием /compatible-mode/v1."
        ),
        "evidence_missing": "Для листа {seq} не найдены изображения сравнения.",
        "evidence_encode": "Не удалось подготовить визуальный монтаж листа {seq}.",
        "no_analysis": "Сначала выполните визуальный анализ сопоставленных изменённых листов.",
        "no_eligible": "Нет сопоставленных изменённых пар OLD + NEW для визуального анализа.",
    },
    "en": {
        "api_key_missing": "{env_var} is not configured for the {provider} provider in the MCP environment.",
        "api_unavailable": "The {provider} API is temporarily unavailable or returned an invalid response.",
        "api_no_choices": "The {provider} API did not return a response choice.",
        "api_empty": "{provider} did not produce a textual description.",
        "qwen_base_url_missing": "QWEN_BASE_URL is not configured for Qwen in the MCP environment.",
        "qwen_base_url_invalid": (
            "QWEN_BASE_URL must be an official Alibaba Model Studio HTTPS endpoint ending in /compatible-mode/v1."
        ),
        "evidence_missing": "Comparison images were not found for sheet {seq}.",
        "evidence_encode": "Could not build the visual evidence montage for sheet {seq}.",
        "no_analysis": "Run visual analysis for matched changed sheets first.",
        "no_eligible": "There are no matched changed OLD + NEW pairs eligible for visual analysis.",
    },
}


class VisionAnalysisError(RuntimeError):
    def __init__(self, key: str, **params: object):
        self.key = key
        self.params = params
        super().__init__(self.localized("ru"))

    def localized(self, lang: str) -> str:
        language = "en" if str(lang).lower().startswith("en") else "ru"
        template = _ERRORS.get(language, _ERRORS["ru"]).get(self.key, self.key)
        return template.format(**self.params)


@dataclass(frozen=True)
class VisionSelection:
    eligible: list[dict[str, Any]]
    skipped: dict[str, list[int]]


@dataclass(frozen=True)
class VisionEvidence:
    path: Path
    seq: int
    zones_total: int
    zones_shown: int


@dataclass(frozen=True)
class VisionAnalysis:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool = False
    cached_prompt_tokens: int = 0
    billed_at: str = ""


@dataclass(frozen=True)
class VisionReportArtifacts:
    html_path: Path
    markdown_path: Path
    json_path: Path
    zip_path: Path
    sheet_count: int


def normalize_lang(lang: str) -> str:
    return "en" if str(lang).lower().startswith("en") else "ru"


def select_vision_rows(
    pairs: Sequence[dict[str, Any]], excluded_seqs: Sequence[int] = ()
) -> VisionSelection:
    """Keep only real two-sided diffs and explain why every other row was skipped."""
    excluded = {int(seq) for seq in excluded_seqs}
    skipped: dict[str, list[int]] = {
        "excluded": [],
        "added": [],
        "removed": [],
        "one_sided": [],
        "not_matched": [],
        "unchanged": [],
        "no_diff": [],
    }
    eligible: list[dict[str, Any]] = []
    for raw_row in pairs:
        row = dict(raw_row)
        try:
            seq = int(row["seq"])
        except (KeyError, TypeError, ValueError):
            continue
        status = str(row.get("status") or "")
        if seq in excluded:
            skipped["excluded"].append(seq)
        elif status == "added":
            skipped["added"].append(seq)
        elif status == "removed":
            skipped["removed"].append(seq)
        elif row.get("a_page") is None or row.get("b_page") is None:
            skipped["one_sided"].append(seq)
        elif status != "matched":
            skipped["not_matched"].append(seq)
        elif str(row.get("change_level") or "") == "unchanged":
            skipped["unchanged"].append(seq)
        elif float(row.get("diff_percent") or 0.0) <= 0 and int(row.get("bboxes_count") or 0) <= 0:
            skipped["no_diff"].append(seq)
        else:
            eligible.append(row)
    return VisionSelection(eligible=eligible, skipped=skipped)


class OpenAICompatibleVisionClient:
    provider_name = "AI"
    api_key_env = "API_KEY"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_sec: float = 120.0,
        max_tokens: int = 1200,
    ):
        if not str(api_key).strip():
            raise VisionAnalysisError(
                "api_key_missing",
                provider=self.provider_name,
                env_var=self.api_key_env,
            )
        self.api_key = str(api_key).strip()
        self.base_url = str(base_url).rstrip("/")
        self.model = str(model).strip()
        self.timeout_sec = float(timeout_sec)
        self.max_tokens = int(max_tokens)

    def analyze(self, evidence: VisionEvidence, row: dict[str, Any], *, lang: str = "ru") -> VisionAnalysis:
        language = normalize_lang(lang)
        image = base64.b64encode(evidence.path.read_bytes()).decode("ascii")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _messages(row, evidence, image, language),
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        self._configure_payload(payload)
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                result = (
                    _read_stream_response(response)
                    if bool(payload.get("stream"))
                    else json.loads(response.read().decode("utf-8"))
                )
        except HTTPError as exc:
            detail = _http_error_message(exc)
            raise VisionAnalysisError("api_unavailable", provider=self.provider_name) from RuntimeError(detail)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise VisionAnalysisError("api_unavailable", provider=self.provider_name) from exc

        choices = result.get("choices") if isinstance(result, dict) else None
        if not isinstance(choices, list) or not choices:
            raise VisionAnalysisError("api_no_choices", provider=self.provider_name)
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        text = str(message.get("content") if isinstance(message, dict) else "").strip()
        if not text:
            raise VisionAnalysisError("api_empty", provider=self.provider_name)
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        return VisionAnalysis(
            text=text,
            model=str(result.get("model") or self.model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cached_prompt_tokens=_cached_prompt_tokens(usage),
            billed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def _configure_payload(self, payload: dict[str, Any]) -> None:
        del payload


class DeepSeekVisionClient(OpenAICompatibleVisionClient):
    provider_name = "DeepSeek"
    api_key_env = "DEEPSEEK_API_KEY"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_VISION_MODEL,
        timeout_sec: float = 120.0,
        max_tokens: int = 1200,
    ):
        super().__init__(
            api_key=api_key,
            base_url=DEEPSEEK_API_BASE_URL,
            model=str(model).strip() or DEFAULT_DEEPSEEK_VISION_MODEL,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
        )

    def _configure_payload(self, payload: dict[str, Any]) -> None:
        payload["thinking"] = {"type": "disabled"}


class QwenVisionClient(OpenAICompatibleVisionClient):
    provider_name = "Qwen"
    api_key_env = "QWEN_API_KEY"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = DEFAULT_QWEN_VISION_MODEL,
        timeout_sec: float = 300.0,
        max_tokens: int = 3000,
    ):
        super().__init__(
            api_key=api_key,
            base_url=validate_qwen_base_url(base_url),
            model=str(model).strip() or DEFAULT_QWEN_VISION_MODEL,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
        )

    def _configure_payload(self, payload: dict[str, Any]) -> None:
        payload["enable_thinking"] = True
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}


def validate_qwen_base_url(base_url: str) -> str:
    value = str(base_url).strip().rstrip("/")
    if not value:
        raise VisionAnalysisError("qwen_base_url_missing")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".maas.aliyuncs.com")
        or not parsed.path.endswith("/compatible-mode/v1")
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise VisionAnalysisError("qwen_base_url_invalid")
    return value


class VisionAnalysisCache:
    def __init__(self, run_dir: Path, model: str, *, lang: str = "ru", provider: str = "deepseek"):
        self.model = str(model)
        self.lang = normalize_lang(lang)
        self.provider = _safe_name(provider.lower()) or "ai"
        self.path = vision_root(run_dir) / "cache" / f"{self.provider}-{_safe_name(model)}-{self.lang}.json"

    def get(self, seq: int) -> VisionAnalysis | None:
        payload = self._load()
        if (
            int(payload.get("prompt_version") or 0) != PROMPT_VERSION
            or payload.get("model") != self.model
            or payload.get("lang") != self.lang
            or payload.get("provider") != self.provider
        ):
            return None
        item = (payload.get("sheets") or {}).get(str(seq))
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            return None
        return VisionAnalysis(
            text=str(item["text"]),
            model=str(item.get("model") or self.model),
            prompt_tokens=int(item.get("prompt_tokens") or 0),
            completion_tokens=int(item.get("completion_tokens") or 0),
            cached=True,
            cached_prompt_tokens=int(item.get("cached_prompt_tokens") or 0),
            billed_at=str(item.get("billed_at") or ""),
        )

    def put(self, seq: int, analysis: VisionAnalysis) -> None:
        payload = self._load()
        if (
            int(payload.get("prompt_version") or 0) != PROMPT_VERSION
            or payload.get("model") != self.model
            or payload.get("lang") != self.lang
            or payload.get("provider") != self.provider
        ):
            payload = {
                "prompt_version": PROMPT_VERSION,
                "provider": self.provider,
                "model": self.model,
                "lang": self.lang,
                "sheets": {},
            }
        sheets = payload.setdefault("sheets", {})
        sheets[str(seq)] = {
            "text": analysis.text,
            "model": analysis.model,
            "prompt_tokens": analysis.prompt_tokens,
            "completion_tokens": analysis.completion_tokens,
            "cached_prompt_tokens": analysis.cached_prompt_tokens,
            "billed_at": analysis.billed_at,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def cached_sequences(self) -> list[int]:
        payload = self._load()
        if (
            int(payload.get("prompt_version") or 0) != PROMPT_VERSION
            or payload.get("model") != self.model
            or payload.get("lang") != self.lang
            or payload.get("provider") != self.provider
        ):
            return []
        sheets = payload.get("sheets") or {}
        if not isinstance(sheets, dict):
            return []
        return sorted(int(seq) for seq, item in sheets.items() if str(seq).isdigit() and isinstance(item, dict))

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def vision_root(run_dir: Path) -> Path:
    return internal_dir(run_dir) / "vision_analysis"


def build_vision_evidence(run_dir: Path, row: dict[str, Any], *, max_zones: int) -> VisionEvidence:
    seq = int(row["seq"])
    pair_dir = find_pages_dir(run_dir) / str(row["pair_dir"])
    old = _read_image(pair_dir / "a.png")
    new = _read_image(pair_dir / "b.png")
    diff = _read_image(pair_dir / "overlay.png")
    boxes = _read_boxes(pair_dir / "bboxes.json")
    selected = sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)[: max(1, int(max_zones))]

    panels: list[tuple[str, np.ndarray]] = []
    annotated_old = _annotate(old, selected)
    annotated_new = _annotate(new, selected)
    if annotated_old is not None:
        panels.append(("OLD", annotated_old))
    if annotated_new is not None:
        panels.append(("NEW", annotated_new))
    if diff is not None:
        panels.append(("DIFF", diff))
    if not panels:
        raise VisionAnalysisError("evidence_missing", seq=seq)

    overview = _overview(panels)
    crops = _zone_grid(old, new, selected)
    canvas = overview if crops is None else np.vstack((overview, crops))
    target = vision_root(run_dir) / "evidence" / f"sheet_{seq:03d}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise VisionAnalysisError("evidence_encode", seq=seq)
    encoded.tofile(str(target))
    return VisionEvidence(target, seq, len(boxes), len(selected))


def vision_report_paths(
    run_dir: Path,
    model: str,
    *,
    lang: str = "ru",
    provider: str = "deepseek",
) -> VisionReportArtifacts:
    suffix = f"{_safe_name(provider.lower())}-{_safe_name(model)}-{normalize_lang(lang)}"
    report_dir = vision_root(run_dir) / "report" / suffix
    return VisionReportArtifacts(
        html_path=report_dir / "index.html",
        markdown_path=report_dir / "report.md",
        json_path=report_dir / "report.json",
        zip_path=vision_root(run_dir) / f"Vision_Analysis_Report-{suffix}.zip",
        sheet_count=0,
    )


def create_vision_report(
    run_dir: Path,
    model: str,
    rows: Sequence[dict[str, Any]],
    *,
    lang: str = "ru",
    max_zones: int = 8,
    provider: str = "deepseek",
) -> VisionReportArtifacts:
    language = normalize_lang(lang)
    provider_key = str(provider).strip().lower() or "deepseek"
    provider_name = "Qwen" if provider_key == "qwen" else "DeepSeek"
    cache = VisionAnalysisCache(run_dir, model, lang=language, provider=provider_key)
    paths = vision_report_paths(run_dir, model, lang=language, provider=provider_key)
    report_root = paths.html_path.parent
    report_root.mkdir(parents=True, exist_ok=True)
    image_dir = report_root / "sheets"
    image_dir.mkdir(parents=True, exist_ok=True)
    text_sections: list[str] = []
    markdown_sections: list[str] = []
    items: list[dict[str, Any]] = []
    generated_files: list[Path] = []
    source_labels = _report_source_labels(run_dir)
    for row in rows:
        seq = int(row["seq"])
        analysis = cache.get(seq)
        if analysis is None:
            continue
        pair_dir = find_pages_dir(run_dir) / str(row["pair_dir"])
        sheet_name = f"sheet_{seq:03d}"
        sheet_dir = image_dir / sheet_name
        sheet_dir.mkdir(parents=True, exist_ok=True)
        old = _read_image(pair_dir / "a.png")
        new = _read_image(pair_dir / "b.png")
        reference = old if old is not None else new
        if reference is None:
            continue
        height, width = reference.shape[:2]
        boxes = sorted(_read_boxes(pair_dir / "bboxes.json"), key=lambda box: box[2] * box[3], reverse=True)
        selected = boxes[: max(1, int(max_zones))]
        for role, source_name, image in (("old", "a.png", old), ("new", "b.png", new)):
            if image is None:
                continue
            target = sheet_dir / f"{role}.png"
            shutil.copy2(pair_dir / source_name, target)
            generated_files.append(target)
            thumb = sheet_dir / f"{role}_thumb.png"
            _write_thumbnail_png(image, thumb)
            generated_files.append(thumb)

        descriptions = _analysis_zone_descriptions(analysis.text)
        confidence = _analysis_confidence(analysis.text)
        zones: list[dict[str, Any]] = []
        for index, rect in enumerate(selected, start=1):
            description = (
                descriptions[index - 1]
                if index <= len(descriptions)
                else _zone_fallback_description(index, language)
            )
            classification = _description_classification(description)
            zone_images: dict[str, str] = {}
            for role, image in (("old", old), ("new", new)):
                if image is None:
                    continue
                name = f"details/zone_{index:02d}_{role}.png"
                target = sheet_dir / name
                if _write_zone_crop_png(image, target, rect):
                    generated_files.append(target)
                    zone_images[role] = name
            zones.append(
                {
                    "id": index,
                    "classification": classification,
                    "confidence": confidence if index <= len(descriptions) else min(confidence, 60),
                    "description": description,
                    "rect": dict(zip(("x", "y", "w", "h"), rect, strict=True)),
                    "images": zone_images,
                }
            )
        if not zones:
            zones.append(
                {
                    "id": 1,
                    "classification": _description_classification(analysis.text),
                    "confidence": confidence,
                    "description": analysis.text,
                    "rect": None,
                    "images": {},
                }
            )
        counts = {
            classification: sum(zone["classification"] == classification for zone in zones)
            for classification in ("real_change", "alignment_or_rendering_noise", "uncertain")
        }
        metrics = _report_metrics(row, language)
        metrics_text = " · ".join(f"{key}: {value}" for key, value in metrics.items())
        sheet_payload = {
            "seq": seq,
            "model": analysis.model,
            "metrics": metrics,
            "counts": counts,
            "global_alignment": _alignment_summary(row, language),
            "zones": zones,
            "original_analysis": analysis.text,
            "source": source_labels,
            "size_px": [width, height],
        }
        sheet_html_path = sheet_dir / "comparison.html"
        _atomic_write_text(
            sheet_html_path,
            vision_sheet_html(sheet_payload, [int(candidate["seq"]) for candidate in rows]),
        )
        generated_files.append(sheet_html_path)
        text_sections.append(f"{_sheet_word(language).upper()} {seq}\n{metrics_text}\n\n{analysis.text}\n")
        report_image_names = {
            "old": f"sheets/{sheet_name}/old.png",
            "new": f"sheets/{sheet_name}/new.png",
        }
        markdown_sections.append(_sheet_markdown(seq, language, metrics_text, analysis.text, report_image_names))
        item = dict(sheet_payload)
        item.update(
            {
                "description": analysis.text,
                "prompt_tokens": analysis.prompt_tokens,
                "completion_tokens": analysis.completion_tokens,
                "cached_prompt_tokens": analysis.cached_prompt_tokens,
                "billed_at": analysis.billed_at,
                "images": report_image_names,
            }
        )
        items.append(item)
    if not items:
        raise VisionAnalysisError("no_analysis")

    html = vision_index_html(provider_name, model, items)
    readme = _report_readme(provider_name, language, text_sections)
    markdown = _report_markdown(provider_name, model, language, markdown_sections)
    report_json = json.dumps(
        {"provider": provider_key, "model": model, "lang": language, "sheets": items},
        ensure_ascii=False,
        indent=2,
    )
    _atomic_write_text(paths.html_path, html)
    _atomic_write_text(paths.markdown_path, markdown)
    _atomic_write_text(paths.json_path, report_json)
    readme_path = report_root / "README.txt"
    _atomic_write_text(readme_path, readme)
    generated_files.extend((paths.html_path, paths.markdown_path, paths.json_path, readme_path))

    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.zip_path.with_name(f".{paths.zip_path.name}.{uuid4().hex}.part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in generated_files:
            archive.write(source, source.relative_to(report_root).as_posix())
    os.replace(temporary, paths.zip_path)
    return VisionReportArtifacts(paths.html_path, paths.markdown_path, paths.json_path, paths.zip_path, len(items))


def _report_source_labels(run_dir: Path) -> dict[str, str]:
    try:
        payload = json.loads((internal_dir(run_dir) / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}

    def label(key: str, fallback: str) -> tuple[str, str]:
        raw = str(payload.get(key) or "").replace("\\", "/")
        name = raw.rsplit("/", 1)[-1] if raw else fallback
        stem = name.rsplit(".", 1)[0]
        revision_match = re.search(r"(?:^|[-_])(r?[A-Za-zА-Яа-я]\d+)$", stem, flags=re.IGNORECASE)
        revision = revision_match.group(1) if revision_match else fallback
        return name, revision

    old_name, old_revision = label("file_a", "OLD")
    new_name, new_revision = label("file_b", "NEW")
    return {
        "old_name": old_name,
        "new_name": new_name,
        "old_revision": old_revision,
        "new_revision": new_revision,
    }


def _analysis_zone_descriptions(text: str) -> list[str]:
    descriptions: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*\d+[.)]\s*(.+)", line)
        if match:
            descriptions.append(match.group(1).strip())
    return descriptions


def _analysis_confidence(text: str) -> int:
    explicit = re.search(r"(?:уверенность|confidence)\s*:\s*(\d{1,3})", text, flags=re.IGNORECASE)
    if explicit:
        return max(0, min(100, int(explicit.group(1))))
    lowered = text.lower()
    if "высок" in lowered or "high" in lowered:
        return 90
    if "низк" in lowered or "low" in lowered:
        return 55
    return 75


def _description_classification(description: str) -> str:
    lowered = description.lower()
    noise_words = ("шум", "сдвиг", "антиалиас", "идентич", "без измен", "не является")
    uncertain_words = ("неопредел", "неяс", "нельзя определить", "возможно", "предполож")
    if any(word in lowered for word in noise_words):
        return "alignment_or_rendering_noise"
    if any(word in lowered for word in uncertain_words):
        return "uncertain"
    return "real_change"


def _zone_fallback_description(index: int, lang: str) -> str:
    if lang == "en":
        return f"Candidate diff zone {index}; compare OLD and NEW with the full model summary."
    return f"Кандидатная diff-зона {index}; сопоставьте OLD и NEW с общим выводом модели."


def _alignment_summary(row: dict[str, Any], lang: str) -> str:
    x = float(row.get("alignment_shift_x_mm") or 0.0)
    y = float(row.get("alignment_shift_y_mm") or 0.0)
    rotation = float(row.get("alignment_rotation_deg") or 0.0)
    if abs(x) < 0.01 and abs(y) < 0.01 and abs(rotation) < 0.001:
        return "Global shift not detected" if lang == "en" else "Глобальный сдвиг не обнаружен"
    if lang == "en":
        return f"Alignment: X {x:+.2f} mm, Y {y:+.2f} mm, rotation {rotation:+.3f}°"
    return f"Совмещение: X {x:+.2f} мм, Y {y:+.2f} мм, поворот {rotation:+.3f}°"


def _write_png(target: Path, image: np.ndarray) -> bool:
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not ok:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(target))
    return True


def _write_thumbnail_png(image: np.ndarray, target: Path, width: int = 900) -> bool:
    height = max(1, round(image.shape[0] * width / max(1, image.shape[1])))
    thumbnail = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return _write_png(target, thumbnail)


def _write_zone_crop_png(
    image: np.ndarray,
    target: Path,
    rect: tuple[int, int, int, int],
) -> bool:
    x, y, width, height = rect
    margin = max(50, min(180, round(max(width, height) * 0.08)))
    left, top = max(0, x - margin), max(0, y - margin)
    right = min(image.shape[1], x + width + margin)
    bottom = min(image.shape[0], y + height + margin)
    return _write_png(target, image[top:bottom, left:right])


def _messages(row: dict[str, Any], evidence: VisionEvidence, image: str, lang: str) -> list[dict[str, Any]]:
    context = _sheet_context(row, evidence)
    if lang == "en":
        system = (
            "You conservatively describe revision changes in technical drawings. Do not invent text, dimensions, "
            "labels, or object purposes when they are unreadable. Treat machine metrics as facts and visual "
            "interpretation as a hypothesis. Answer only in English."
        )
        user = (
            "Describe the actual changes on this sheet. The montage contains OLD, NEW, and DIFF at the top; red "
            "boxes and the OLD/NEW crops below are numbered. Red/blue in DIFF is machine markup, not source color.\n\n"
            f"Engine data:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            "Format: Sheet <number> — <one sentence>; Changes: numbered list by zone; Confidence: high/medium/low "
            "with a short reason. If the substantive change cannot be determined, state that explicitly."
        )
    else:
        system = (
            "Ты консервативно описываешь изменения между ревизиями технических чертежей. Не выдумывай текст, "
            "размеры, обозначения или назначение объектов, если они не читаются. Машинные метрики считай фактом, "
            "визуальную интерпретацию — гипотезой. Отвечай только по-русски."
        )
        user = (
            "Опиши фактические изменения на листе. На монтаже сверху расположены OLD, NEW и DIFF; красные рамки "
            "и нижние пары кропов OLD/NEW пронумерованы. Красный/синий цвет DIFF — машинная подсветка, а не цвет "
            f"исходного чертежа.\n\nДанные движка:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            "Формат: Лист <номер> — <одно предложение>; Изменения: нумерованный список по зонам; Уверенность: "
            "высокая/средняя/низкая с короткой причиной. Если содержательное изменение определить нельзя, напиши это."
        )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
            ],
        },
    ]


def _sheet_context(row: dict[str, Any], evidence: VisionEvidence) -> dict[str, Any]:
    fields = (
        "seq",
        "status",
        "change_level",
        "diff_percent",
        "diff_foreground_percent",
        "diff_area_mm2",
        "added_area_mm2",
        "removed_area_mm2",
        "alignment_shift_x_mm",
        "alignment_shift_y_mm",
        "alignment_rotation_deg",
    )
    context = {field: row.get(field) for field in fields}
    context["zones_total"] = evidence.zones_total
    context["zones_shown"] = evidence.zones_shown
    return context


def _read_image(path: Path) -> np.ndarray | None:
    if not path.is_file():
        return None
    raw = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR) if raw.size else None


def _write_annotated_mobile_jpeg(
    source: Path,
    target: Path,
    boxes: Sequence[tuple[int, int, int, int]],
    max_dimension: int = 3200,
) -> bool:
    """Write a full sheet with the same numbered zones that the model received."""
    image = _read_image(source)
    if image is None:
        return False
    annotated = _annotate(image, boxes)
    if annotated is None:
        return False
    height, width = annotated.shape[:2]
    longest = max(height, width)
    if longest > max_dimension:
        scale = max_dimension / float(longest)
        annotated = cv2.resize(
            annotated,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(target))
    return True


def _read_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(payload, list):
        return boxes
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            box = (int(item["x"]), int(item["y"]), int(item["w"]), int(item["h"]))
        except (KeyError, TypeError, ValueError):
            continue
        if box[2] > 0 and box[3] > 0:
            boxes.append(box)
    return boxes


def _annotate(image: np.ndarray | None, boxes: Sequence[tuple[int, int, int, int]]) -> np.ndarray | None:
    if image is None:
        return None
    result = image.copy()
    thickness = max(3, round(max(result.shape[:2]) / 700))
    font_scale = max(0.8, max(result.shape[:2]) / 1800)
    for number, (x, y, width, height) in enumerate(boxes, start=1):
        cv2.rectangle(result, (x, y), (x + width, y + height), (0, 0, 220), thickness)
        cv2.putText(
            result,
            str(number),
            (x + 4, max(25, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (0, 0, 220),
            thickness,
            cv2.LINE_AA,
        )
    return result


def _overview(panels: Sequence[tuple[str, np.ndarray]]) -> np.ndarray:
    canvas_width, gap, panel_height = 1800, 18, 680
    panel_width = (canvas_width - gap * (len(panels) + 1)) // len(panels)
    canvas = np.full((panel_height + 58, canvas_width, 3), 255, dtype=np.uint8)
    for index, (label, image) in enumerate(panels):
        fitted = _fit(image, panel_width, panel_height)
        x = gap + index * (panel_width + gap)
        y = 48 + (panel_height - fitted.shape[0]) // 2
        canvas[y : y + fitted.shape[0], x : x + fitted.shape[1]] = fitted
        cv2.putText(canvas, label, (x, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2, cv2.LINE_AA)
    return canvas


def _zone_grid(
    old: np.ndarray | None,
    new: np.ndarray | None,
    boxes: Sequence[tuple[int, int, int, int]],
) -> np.ndarray | None:
    if not boxes or (old is None and new is None):
        return None
    canvas_width, cell_width, cell_height, gap = 1800, 880, 330, 20
    rows = (len(boxes) + 1) // 2
    canvas = np.full((rows * cell_height + gap, canvas_width, 3), 248, dtype=np.uint8)
    for index, box in enumerate(boxes):
        row, column = divmod(index, 2)
        cell_x = gap + column * (cell_width + gap)
        cell_y = gap + row * cell_height
        cv2.putText(
            canvas,
            f"ZONE {index + 1}: OLD / NEW",
            (cell_x, cell_y + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
        pair = _crop_pair(old, new, box, (cell_width - 12) // 2, cell_height - 52)
        canvas[cell_y + 44 : cell_y + 44 + pair.shape[0], cell_x : cell_x + pair.shape[1]] = pair
    return canvas


def _crop_pair(
    old: np.ndarray | None,
    new: np.ndarray | None,
    box: tuple[int, int, int, int],
    target_width: int,
    target_height: int,
) -> np.ndarray:
    canvas = np.full((target_height, target_width * 2 + 12, 3), 255, dtype=np.uint8)
    for index, image in enumerate(image for image in (old, new) if image is not None):
        x, y, width, height = box
        margin = max(40, round(max(width, height) * 0.5))
        crop = image[
            max(0, y - margin) : min(image.shape[0], y + height + margin),
            max(0, x - margin) : min(image.shape[1], x + width + margin),
        ]
        fitted = _fit(crop, target_width, target_height)
        left = index * (target_width + 12)
        top = (target_height - fitted.shape[0]) // 2
        canvas[top : top + fitted.shape[0], left : left + fitted.shape[1]] = fitted
    return canvas


def _fit(image: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(max_width / max(1, width), max_height / max(1, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, size, interpolation=interpolation)


def _report_metrics(row: dict[str, Any], lang: str) -> dict[str, str]:
    def number(name: str, digits: int, suffix: str) -> str:
        value = row.get(name)
        return "—" if value is None else f"{float(value):.{digits}f}{suffix}"

    return {
        ("level" if lang == "en" else "уровень"): str(row.get("change_level") or "—"),
        "diff": number("diff_percent", 3, "%"),
        "FG": number("diff_foreground_percent", 2, "%"),
        ("area" if lang == "en" else "площадь"): number("diff_area_mm2", 1, " mm²"),
        ("zones" if lang == "en" else "зоны"): str(int(row.get("bboxes_count") or 0)),
    }


def _report_html(model: str, lang: str, sections: Sequence[str]) -> str:
    title = "DeepSeek visual analysis" if lang == "en" else "Визуальный анализ DeepSeek"
    note = (
        "Only matched OLD + NEW pairs with a real diff are included. Added, removed, and one-sided sheets were not "
        "sent to the model. AI descriptions require engineering review."
        if lang == "en"
        else "Включены только сопоставленные пары OLD + NEW с реальным diff. Добавленные, удалённые и "
        "односторонние листы модели не передавались. AI-описания требуют инженерной проверки."
    )
    return (
        f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>"
        "*{box-sizing:border-box}body{font-family:system-ui,sans-serif;max-width:1500px;margin:32px auto;"
        "padding:0 20px;color:#18202a;background:#f7f9fb}"
        "h1{margin-bottom:6px}section{border:1px solid #ccd3da;border-radius:16px;padding:20px;margin:24px 0;"
        "background:#fff;box-shadow:0 4px 18px #1b2a3a12}"
        ".note,.metrics{color:#52606d}pre{white-space:pre-wrap;font:inherit;line-height:1.5}"
        ".image-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:18px}"
        "figure{margin:0}figcaption{font-weight:700;margin:0 0 6px}"
        "img{display:block;width:100%;height:auto;border:1px solid #ccd3da;border-radius:8px;background:#fff}"
        ".image-button{display:block;width:100%;padding:0;border:0;background:transparent;cursor:zoom-in}"
        "details{margin-top:18px}summary{cursor:pointer;font-weight:700;margin-bottom:10px}"
        "dialog{width:min(96vw,1800px);height:min(96vh,1200px);padding:0;border:0;border-radius:12px;"
        "background:#101820;color:#fff}dialog::backdrop{background:#000b}.viewer{height:100%;display:grid;"
        "grid-template-rows:auto minmax(0,1fr) auto;gap:10px;padding:12px}.viewer-tools{display:flex;gap:8px;"
        "align-items:center}.viewer-tools .viewer-close{margin-left:auto}.viewer-stage{position:relative;overflow:hidden;"
        "display:flex;align-items:center;justify-content:center;touch-action:none;cursor:grab}.viewer-stage.is-panning{cursor:grabbing}"
        ".viewer img{max-width:100%;max-height:100%;width:auto;height:auto;margin:auto;border:0;border-radius:4px;"
        "transform-origin:center;will-change:transform}.viewer button{min-width:44px;min-height:44px;border:0;"
        "border-radius:8px;background:#ffffff24;color:#fff;font-size:1.4rem;cursor:pointer}.viewer-nav{position:absolute;"
        "top:50%;transform:translateY(-50%);z-index:1}.viewer-prev{left:8px}.viewer-next{right:8px}.viewer-help{"
        "font-size:.85rem;color:#d6dee6}.viewer-caption{margin:0;text-align:center}"
        "@media(max-width:760px){body{margin:0;padding:12px;background:#fff}h1{font-size:1.55rem}"
        "section{margin:14px 0;padding:14px;border-radius:10px;box-shadow:none}.image-grid{grid-template-columns:1fr}"
        "pre{overflow-wrap:anywhere}.metrics{line-height:1.6}.viewer{padding:8px;gap:6px}"
        ".viewer button{min-width:40px;min-height:40px}}"
        f"</style></head><body><h1>{escape(title)}</h1><p class='note'>{escape(note)} "
        f"Model: {escape(model)}.</p>{''.join(sections)}{_viewer_markup(lang)}{_viewer_script()}</body></html>"
    )


def _sheet_images_html(seq: int, lang: str, image_names: dict[str, str]) -> str:
    captions = {
        "old": "OLD — старая ревизия" if lang == "ru" else "OLD revision",
        "new": "NEW — новая ревизия" if lang == "ru" else "NEW revision",
        "diff": "DIFF — изменения" if lang == "ru" else "DIFF changes",
    }
    figures = []
    for role in ("old", "new"):
        name = image_names.get(role)
        if name:
            caption = captions[role]
            figures.append(
                f'<figure><figcaption>{escape(caption)}</figcaption><button class="image-button" type="button" '
                f'data-viewer-image="{escape(name)}" data-viewer-caption="{escape(caption)} · {seq}">'
                f'<img loading="lazy" src="{escape(name)}" alt="{escape(caption)} · {seq}"></button></figure>'
            )
    parts = [f'<div class="image-grid">{"".join(figures)}</div>'] if figures else []
    return "".join(parts)


def _viewer_markup(lang: str) -> str:
    close = "Закрыть" if lang == "ru" else "Close"
    previous = "Предыдущее изображение" if lang == "ru" else "Previous image"
    next_image = "Следующее изображение" if lang == "ru" else "Next image"
    zoom_out = "Уменьшить" if lang == "ru" else "Zoom out"
    zoom_in = "Увеличить" if lang == "ru" else "Zoom in"
    help_text = "Ctrl + колесо: масштаб · перетаскивание: панорама" if lang == "ru" else "Ctrl + wheel: zoom · drag: pan"
    return (
        "<dialog id='image-viewer'><div class='viewer'>"
        "<div class='viewer-tools'>"
        f"<button class='viewer-zoom-out' type='button' aria-label='{escape(zoom_out)}'>−</button>"
        f"<button class='viewer-zoom-in' type='button' aria-label='{escape(zoom_in)}'>+</button>"
        f"<span class='viewer-help'>{escape(help_text)}</span>"
        f"<button class='viewer-close' type='button' aria-label='{escape(close)}' title='{escape(close)}'>×</button>"
        "</div><div class='viewer-stage'><button class='viewer-nav viewer-prev' type='button' "
        f"aria-label='{escape(previous)}'>‹</button><img class='viewer-image' alt=''><button "
        f"class='viewer-nav viewer-next' type='button' aria-label='{escape(next_image)}'>›</button></div>"
        "<p class='viewer-caption'></p></div></dialog>"
    )


def _viewer_script() -> str:
    return """<script>(()=>{const dialog=document.getElementById('image-viewer');const stage=dialog.querySelector('.viewer-stage');const image=dialog.querySelector('.viewer-image');const caption=dialog.querySelector('.viewer-caption');const items=()=>[...document.querySelectorAll('[data-viewer-image]')];let index=0,scale=1,panX=0,panY=0,drag=null;const render=()=>{image.style.transform=`translate(${panX}px,${panY}px) scale(${scale})`;stage.classList.toggle('is-panning',!!drag);};const reset=()=>{scale=1;panX=0;panY=0;render();};const zoom=next=>{scale=Math.max(1,Math.min(6,next));if(scale===1){panX=0;panY=0;}render();};const show=i=>{const all=items();if(!all.length)return;index=(i+all.length)%all.length;const item=all[index];image.src=item.dataset.viewerImage||'';image.alt=item.dataset.viewerCaption||'';caption.textContent=item.dataset.viewerCaption||'';reset();};document.addEventListener('click',event=>{const item=event.target.closest('[data-viewer-image]');if(!item)return;show(items().indexOf(item));dialog.showModal();});dialog.querySelector('.viewer-close').addEventListener('click',()=>dialog.close());dialog.querySelector('.viewer-prev').addEventListener('click',()=>show(index-1));dialog.querySelector('.viewer-next').addEventListener('click',()=>show(index+1));dialog.querySelector('.viewer-zoom-in').addEventListener('click',()=>zoom(scale*1.25));dialog.querySelector('.viewer-zoom-out').addEventListener('click',()=>zoom(scale/1.25));stage.addEventListener('wheel',event=>{if(!event.ctrlKey)return;event.preventDefault();zoom(scale*(event.deltaY<0?1.15:1/1.15));},{passive:false});stage.addEventListener('pointerdown',event=>{if(scale<=1)return;drag={x:event.clientX,y:event.clientY,panX,panY};stage.setPointerCapture(event.pointerId);render();});stage.addEventListener('pointermove',event=>{if(!drag)return;panX=drag.panX+event.clientX-drag.x;panY=drag.panY+event.clientY-drag.y;render();});const stop=event=>{if(!drag)return;drag=null;if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId);render();};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop);dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});document.addEventListener('keydown',event=>{if(!dialog.open)return;if(event.key==='ArrowLeft'){event.preventDefault();show(index-1);}else if(event.key==='ArrowRight'){event.preventDefault();show(index+1);}else if(event.key==='+'||event.key==='='){event.preventDefault();zoom(scale*1.25);}else if(event.key==='-'){event.preventDefault();zoom(scale/1.25);}else if(event.key==='0'){event.preventDefault();reset();}});})();</script>"""


def _sheet_markdown(
    seq: int,
    lang: str,
    metrics_text: str,
    description: str,
    image_names: dict[str, str],
) -> str:
    lines = [f"## {_sheet_word(lang)} {seq}", "", metrics_text, "", description, ""]
    labels = {
        "old": "OLD — старая ревизия" if lang == "ru" else "OLD revision",
        "new": "NEW — новая ревизия" if lang == "ru" else "NEW revision",
    }
    for role in ("old", "new"):
        name = image_names.get(role)
        if name:
            label = labels[role]
            lines.extend((f"### {label}", "", f"[![{label}]({name})]({name})", ""))
    return "\n".join(lines)


def _report_markdown(provider: str, model: str, lang: str, sections: Sequence[str]) -> str:
    title = f"{provider} visual analysis" if lang == "en" else f"Визуальный анализ {provider}"
    note = (
        "Only matched OLD + NEW pairs with a real diff are included. Added, removed, and one-sided sheets were not "
        f"sent to {provider}. AI descriptions require engineering review."
        if lang == "en"
        else "Включены только сопоставленные пары OLD + NEW с реальным diff. Добавленные, удалённые и "
        f"односторонние листы не отправлялись в {provider}. AI-описания требуют инженерной проверки."
    )
    return f"# {title}\n\n{note}\n\n**Model:** `{model}`\n\n" + "\n".join(sections)


def _report_readme(provider: str, lang: str, sections: Sequence[str]) -> str:
    if lang == "en":
        intro = (
            f"{provider} visual analysis\n\nOnly matched OLD + NEW pairs with a real diff are included.\n"
            f"Added, removed, and one-sided sheets were not sent to {provider}.\n"
            "Open index.html in a browser or report.md in a Markdown viewer.\n"
            "Each sheet folder contains separate full-page OLD and NEW PNG files with numbered AI zones.\n\n"
        )
    else:
        intro = (
            f"Визуальный анализ {provider}\n\nВключены только сопоставленные пары OLD + NEW с реальным diff.\n"
            f"Добавленные, удалённые и односторонние листы не отправлялись в {provider}.\n"
            "Откройте index.html в браузере или report.md в Markdown-просмотрщике.\n"
            "В папке каждого листа лежат отдельные полноформатные PNG OLD и NEW с нумерованными зонами AI.\n\n"
        )
    return intro + "\n".join(sections)


def _sheet_word(lang: str) -> str:
    return "Sheet" if lang == "en" else "Лист"


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _http_error_message(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read(8192).decode("utf-8", errors="replace"))
        message = str((payload.get("error") or {}).get("message") or "").strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        message = ""
    return (message or f"HTTP {error.code}")[:500]


def _read_stream_response(response: Any) -> dict[str, Any]:
    text_parts: list[str] = []
    usage: dict[str, Any] = {}
    model = ""
    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        chunk = json.loads(data)
        model = str(chunk.get("model") or model)
        chunk_usage = chunk.get("usage")
        if isinstance(chunk_usage, dict) and chunk_usage:
            usage = chunk_usage
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        delta = choices[0].get("delta") or {}
        if isinstance(delta, dict) and delta.get("content"):
            text_parts.append(str(delta["content"]))
    return {
        "model": model,
        "choices": [{"message": {"content": "".join(text_parts)}}],
        "usage": usage,
    }


def _cached_prompt_tokens(usage: dict[str, Any]) -> int:
    direct = usage.get("prompt_cache_hit_tokens")
    if direct is not None:
        return max(0, int(direct or 0))
    details = usage.get("prompt_tokens_details") or {}
    return max(0, int(details.get("cached_tokens") or 0)) if isinstance(details, dict) else 0
