"""Drag-and-drop handlers (tkinterdnd2-based) for PDF and folder targets"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .utils import parse_dnd_filelist

# tkinterdnd2 detection happens in the parent module (pdfcompare_gui.py);
# the mixin only reads HAS_TKDND / DND_FILES that the host module sets.
try:
    from tkinterdnd2 import DND_FILES
    HAS_TKDND = True
except ImportError:
    HAS_TKDND = False
    DND_FILES = None

from .contracts import AppProtocol


class DragDropMixin:
    def _install_drop_hook(self: AppProtocol) -> None:
        self.root.update_idletasks()
        try:
            if HAS_TKDND and DND_FILES is not None:
                # Use tkinterdnd2 for drag & drop (Python 3.12+ compatible)
                # Main drop canvas
                # tkinterdnd2 monkey-patches Canvas/Entry with drop_target_register /
                # dnd_bind at runtime — these aren't visible to mypy.
                if self.drop_canvas:
                    self.drop_canvas.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                    self.drop_canvas.dnd_bind('<<Drop>>', self._on_tkdnd_drop)  # type: ignore[attr-defined]

                # Individual path entry fields
                if self.old_entry:
                    self.old_entry.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                    self.old_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_old)  # type: ignore[attr-defined]
                if self.new_entry:
                    self.new_entry.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                    self.new_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_new)  # type: ignore[attr-defined]
                if self.out_entry:
                    self.out_entry.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                    self.out_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_out)  # type: ignore[attr-defined]

                self._set_status("status_initial")
            else:
                # Fallback: drag & drop not available
                self._set_status("status_drag_unavailable", error="tkinterdnd2 not installed")
        except Exception as exc:
            self._set_status("status_drag_unavailable", error=str(exc))

    def _on_tkdnd_drop(self: AppProtocol, event) -> None:
        """Main canvas: route into the general dropped-files handler."""
        try:
            self._handle_dropped_files(parse_dnd_filelist(self.root, event.data))
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_old(self: AppProtocol, event) -> None:
        try:
            paths = parse_dnd_filelist(self.root, event.data)
            if paths and paths[0].suffix.lower() == ".pdf":
                self.old_pdf.set(str(paths[0]))
                self._save_state()
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_new(self: AppProtocol, event) -> None:
        try:
            paths = parse_dnd_filelist(self.root, event.data)
            if paths and paths[0].suffix.lower() == ".pdf":
                self.new_pdf.set(str(paths[0]))
                self._save_state()
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_out(self: AppProtocol, event) -> None:
        """Accept both folders and files (use the file's parent folder if a file is dropped)."""
        try:
            paths = parse_dnd_filelist(self.root, event.data)
            if paths:
                path = paths[0]
                self.out_dir.set(str(path if path.is_dir() else path.parent))
                self._save_state()
        except Exception:
            pass
        return event.action

    def _handle_dropped_files(self: AppProtocol, paths: Iterable[Path]) -> None:
        pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
        if not pdfs:
            self._set_status("status_drop_no_pdf")
            return

        if len(pdfs) >= 2:
            self.old_pdf.set(str(pdfs[0]))
            self.new_pdf.set(str(pdfs[1]))
            self._set_status("status_drop_loaded_two")
            self._save_state()
            return

        one = str(pdfs[0])
        if not self.old_pdf.get():
            self.old_pdf.set(one)
            self._set_status("status_drop_set_old")
        elif not self.new_pdf.get():
            self.new_pdf.set(one)
            self._set_status("status_drop_set_new")
        else:
            self.new_pdf.set(one)
            self._set_status("status_drop_replaced_new")
        self._save_state()

