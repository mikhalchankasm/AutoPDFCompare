"""Shared browser runtime for the image comparison slider."""

from __future__ import annotations

import json
from typing import Any


SLIDER_RUNTIME_SOURCE = r"""
(function () {
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }

  window.PDFCOMPARE_MOUNT_SLIDER = function (options) {
    const slider = document.getElementById('split');
    const zoom = document.getElementById('zoom');
    const zoomVal = document.getElementById('zoomVal');
    const fitBtn = document.getElementById('fitBtn');
    const stage = document.getElementById('stage');
    const surface = document.getElementById('surface');
    const oldLayer = document.getElementById('oldLayer');
    const divider = document.getElementById('divider');
    const bboxLayer = document.getElementById('bboxLayer');
    const loadMsg = document.getElementById('loadMsg');
    const oldImg = document.getElementById('imgOld');
    const newImg = document.getElementById('imgNew');
    const bboxOpacity = document.getElementById('bboxOpacity');
    const bboxOpacityVal = document.getElementById('bboxOpacityVal');
    const palettes = {
      yellow: { border: '255,180,0', fill: '255,235,120' },
      pink: { border: '236,72,153', fill: '244,114,182' },
      green: { border: '22,163,74', fill: '134,239,172' }
    };
    let activeColor = 'yellow';
    let loaded = 0;
    let naturalW = 0;
    let naturalH = 0;
    let draggingSplit = false;
    let panning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartScrollLeft = 0;
    let panStartScrollTop = 0;

    function currentAlpha() {
      const value = clamp(Number(bboxOpacity.value) || options.bboxOpacity, 5, 35);
      bboxOpacity.value = String(value);
      bboxOpacityVal.textContent = value + '%';
      return value / 100;
    }
    function applyBboxStyle() {
      const palette = palettes[activeColor] || palettes.yellow;
      const alpha = currentAlpha();
      const borderAlpha = Math.min(0.9, 0.35 + alpha * 3);
      surface.style.setProperty('--bbox-border', `rgba(${palette.border},${borderAlpha.toFixed(2)})`);
      surface.style.setProperty('--bbox-fill', `rgba(${palette.fill},${alpha.toFixed(2)})`);
      try { localStorage.setItem(options.storagePrefix + ':bboxOpacity', bboxOpacity.value); } catch (e) {}
    }
    function setBboxColor(name) {
      activeColor = palettes[name] ? name : 'yellow';
      applyBboxStyle();
      try { localStorage.setItem(options.storagePrefix + ':bboxColor', activeColor); } catch (e) {}
    }
    function buildBboxes() {
      bboxLayer.innerHTML = '';
      options.bboxes.forEach(b => {
        const x = Number(b.x || 0), y = Number(b.y || 0);
        const w = Number(b.w || 0), h = Number(b.h || 0);
        if (w <= 1 || h <= 1) return;
        const box = document.createElement('div');
        box.className = 'bbox';
        box.style.left = (100 * x / naturalW) + '%';
        box.style.top = (100 * y / naturalH) + '%';
        box.style.width = (100 * w / naturalW) + '%';
        box.style.height = (100 * h / naturalH) + '%';
        bboxLayer.appendChild(box);
      });
    }
    function applySplit() {
      const pct = clamp(Number(slider.value) || 0, 0, 100);
      oldLayer.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
      divider.style.left = pct + '%';
    }
    function setZoomPercent(value) {
      const clamped = clamp(Math.round(value), 1, 500);
      zoom.value = String(clamped);
      applyZoom();
    }
    function applyZoom() {
      if (!naturalW || !naturalH) return;
      const value = Number(zoom.value) / 100;
      zoomVal.textContent = Math.round(value * 100) + '%';
      surface.style.width = Math.max(1, Math.round(naturalW * value)) + 'px';
      surface.style.height = Math.max(1, Math.round(naturalH * value)) + 'px';
    }
    function fitToWindow() {
      if (!naturalW || !naturalH) return;
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / naturalW);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / naturalH);
      setZoomPercent(Math.max(0.01, Math.min(sx, sy)) * 100);
    }
    function setSplitFromClientX(clientX) {
      const rect = surface.getBoundingClientRect();
      if (!rect.width) return;
      const x = clamp(clientX - rect.left, 0, rect.width);
      slider.value = String((x / rect.width) * 100);
      applySplit();
    }
    function initialize() {
      naturalW = Math.max(oldImg.naturalWidth || 1, newImg.naturalWidth || 1);
      naturalH = Math.max(oldImg.naturalHeight || 1, newImg.naturalHeight || 1);
      surface.style.display = 'block';
      loadMsg.style.display = 'none';
      buildBboxes();
      applySplit();
      fitToWindow();
    }
    function ready() { loaded += 1; if (loaded >= 2) initialize(); }
    function fail() { loadMsg.textContent = options.loadError; }

    document.querySelectorAll('input[name="bboxColor"]').forEach(input => {
      input.addEventListener('change', () => setBboxColor(input.value));
    });
    try {
      const savedColor = localStorage.getItem(options.storagePrefix + ':bboxColor') || 'yellow';
      const savedOpacity = localStorage.getItem(options.storagePrefix + ':bboxOpacity') || String(options.bboxOpacity);
      bboxOpacity.value = savedOpacity;
      const savedInput = document.querySelector(`input[name="bboxColor"][value="${savedColor}"]`);
      if (savedInput) savedInput.checked = true;
      setBboxColor(savedColor);
    } catch (e) { setBboxColor('yellow'); }
    bboxOpacity.addEventListener('input', applyBboxStyle);
    oldImg.onload = ready;
    newImg.onload = ready;
    oldImg.onerror = fail;
    newImg.onerror = fail;
    oldImg.src = options.oldSrc;
    newImg.src = options.newSrc;
    surface.addEventListener('mousedown', e => {
      if (e.button === 2) {
        panning = true;
        stage.classList.add('panning');
        panStartX = e.clientX;
        panStartY = e.clientY;
        panStartScrollLeft = stage.scrollLeft;
        panStartScrollTop = stage.scrollTop;
        e.preventDefault();
        return;
      }
      if (e.button !== 0) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.clientX);
    });
    window.addEventListener('mousemove', e => {
      if (panning) {
        stage.scrollLeft = panStartScrollLeft - (e.clientX - panStartX);
        stage.scrollTop = panStartScrollTop - (e.clientY - panStartY);
        return;
      }
      if (draggingSplit) setSplitFromClientX(e.clientX);
    });
    window.addEventListener('mouseup', () => {
      draggingSplit = false;
      panning = false;
      stage.classList.remove('dragging');
      stage.classList.remove('panning');
    });
    stage.addEventListener('contextmenu', e => e.preventDefault());
    stage.addEventListener('wheel', e => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setZoomPercent(Number(zoom.value) + (e.deltaY < 0 ? 6 : -6));
    }, { passive: false });
    slider.addEventListener('input', applySplit);
    zoom.addEventListener('input', () => setZoomPercent(Number(zoom.value)));
    fitBtn.addEventListener('click', fitToWindow);
  };
}());
""".strip()


def render_slider_runtime(options: dict[str, Any]) -> str:
    """Return the shared runtime and its page-specific configuration."""
    return (
        "<script>\n"
        f"{SLIDER_RUNTIME_SOURCE}\n"
        "</script>\n"
        "<script>\n"
        f"window.PDFCOMPARE_MOUNT_SLIDER({json.dumps(options, ensure_ascii=False)});\n"
        "</script>"
    )
