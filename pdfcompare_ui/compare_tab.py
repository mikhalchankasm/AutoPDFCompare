"""Compare-tab construction: file cards, output paths, options, actions, status.

These were sections of PDFCompareApp._build_ui, which built the entire window in
one ~500-line method. Each section is now a builder that reads as its own screen
region; _build_ui just calls them in order.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pdfcompare_core.diff_engine import DIFF_STRICTNESS_CHOICES

from .contracts import AppProtocol
from .tooltip import add_tooltip
from .styles import (
    ACCENT,
    ACCENT_DARK,
    BG_CARD,
    BG_INFO,
    BG_SOFT,
    BG_WINDOW,
    BORDER_STRONG,
    BORDER_THIN,
    SECTION_BAR_PX,
    TEXT_SECONDARY,
    card,
    section_header,
)

# The options live on a white card now, not on a beige panel a shade away from the
# window — that is what made the zone invisible.
PANEL = BG_CARD


class CompareTabMixin:
    progress: ttk.Progressbar
    swap_btn: ttk.Button | None
    bbox_merge_chip: ttk.Checkbutton | None
    bbox_merge_gap_entry: ttk.Entry | None
    bbox_merge_max_ratio_entry: ttk.Entry | None
    clear_btn: ttk.Button | None
    drop_canvas: tk.Frame | None
    exclude_pick_btn: ttk.Button | None
    from_history_btn: ttk.Button | None
    keep_debug_chip: ttk.Checkbutton | None
    new_entry: tk.Frame | None
    old_entry: tk.Frame | None
    open_report_btn: ttk.Button | None
    open_run_btn: ttk.Button | None
    options_bbox_merge_hint_label: ttk.Label | None
    options_bbox_merge_label: ttk.Label | None
    options_body: tk.Frame | None
    options_default_label: ttk.Label | None
    options_exclude_hint_label: ttk.Label | None
    options_exclude_label: ttk.Label | None
    options_group_label: ttk.Label | None
    options_keep_debug_hint_label: ttk.Label | None
    options_keep_debug_label: ttk.Label | None
    options_line_weight_hint_label: ttk.Label | None
    options_line_weight_label: ttk.Label | None
    options_strictness_hint_label: ttk.Label | None
    options_strictness_label: ttk.Label | None
    out_entry: ttk.Entry | None
    out_gen_btn: ttk.Button | None
    out_hint_label: ttk.Label | None
    out_label: ttk.Label | None
    out_pick_btn: ttk.Button | None
    report_ready_label: tk.Label | None
    ignore_line_weight_chip: ttk.Checkbutton | None
    run_btn: tk.Button | None
    status_text_label: tk.Label | None

    def _build_files_section(self: AppProtocol) -> None:
        """The two file cards and the drag-and-drop strip."""
        files_row = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        files_row.pack(fill=tk.X, pady=(0, 10))
        files_row.columnconfigure(0, weight=1, uniform="files")
        files_row.columnconfigure(2, weight=1, uniform="files")
        self.old_entry = self._build_file_card(files_row, self.old_pdf, old=True)
        self.old_entry.grid(row=0, column=0, sticky="nsew")
        swap_box = tk.Frame(files_row, bg=BG_WINDOW, width=36)
        swap_box.grid(row=0, column=1, sticky="ns", padx=10)
        self.swap_btn = ttk.Button(swap_box, text="⇅", width=3, style="Small.TButton", command=self._swap_files)
        self.swap_btn.pack(expand=True)
        self.new_entry = self._build_file_card(files_row, self.new_pdf, old=False)
        add_tooltip(self.old_entry, lambda: self._tr("tip_old"))
        add_tooltip(self.new_entry, lambda: self._tr("tip_new"))
        add_tooltip(self.swap_btn, lambda: self._tr("tip_swap"))
        self.new_entry.grid(row=0, column=2, sticky="nsew")

        # A dashed-looking drop strip: it is a target, so it should look like one
        # rather than like an empty line of text.
        self.drop_canvas = tk.Frame(
            self.compare_tab, bg=BG_SOFT, highlightthickness=1, highlightbackground=BORDER_STRONG
        )
        self.drop_canvas.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self.drop_canvas, text=self._tr("drop_hint"), style="Hint.TLabel", background=BG_SOFT).pack(
            anchor="w", padx=12, pady=6
        )

    def _build_output_section(self: AppProtocol) -> None:
        """The one output field: the folder this run will create."""
        out_wrap = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        out_wrap.pack(fill=tk.X, pady=(0, 12))
        head, self.out_label = section_header(out_wrap, self._section_title("path_out"))
        head.pack(anchor="w", pady=(0, 8))
        out_fields = tk.Frame(out_wrap, bg=BG_WINDOW)
        out_fields.pack(fill=tk.X)
        self.out_entry = ttk.Entry(out_fields, textvariable=self.out_dir, style="Path.TEntry")
        self.out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.out_pick_btn = ttk.Button(out_fields, text=self._tr("btn_select"), style="Small.TButton", command=self._pick_out_dir)
        add_tooltip(self.out_entry, lambda: self._tr("tip_out"))
        add_tooltip(self.out_pick_btn, lambda: self._tr("tip_out"))
        self.out_pick_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.out_gen_btn = ttk.Button(
            out_fields,
            text=self._tr("btn_gen_folder"),
            style="Small.TButton",
            command=self._generate_out_folder_name,
        )
        self.out_gen_btn.pack(side=tk.LEFT, padx=(6, 0))
        add_tooltip(self.out_gen_btn, lambda: self._tr("tip_gen_folder"))
        self.out_hint_label = ttk.Label(out_wrap, text=self._tr("path_out_hint"), style="Hint.TLabel")
        self.out_hint_label.pack(anchor="w", pady=(4, 0))


    def _build_options_section(self: AppProtocol) -> None:
        """DPI, tolerance, strictness, exclusion zones, bbox merge, debug."""
        self.options_body = card(self.compare_tab, pad=13)
        self.options_body.pack(fill=tk.X, pady=(0, 12))

        opts_head = tk.Frame(self.options_body, bg=PANEL)
        opts_head.pack(fill=tk.X, pady=(0, 4))
        title_row, self.options_group_label = section_header(
            opts_head, self._section_title("opts_group"), bg=PANEL
        )
        title_row.pack(side=tk.LEFT)
        self.options_default_label = ttk.Label(
            opts_head, text=self._tr("opts_default"), style="Hint.TLabel", background=PANEL
        )
        self.options_default_label.pack(side=tk.RIGHT)
        # A rule under the title: the card has a header, and the header ends here.
        tk.Frame(self.options_body, bg=BORDER_THIN, height=1).pack(fill=tk.X, pady=(8, 12))

        opts_grid = tk.Frame(self.options_body, bg=PANEL)
        opts_grid.pack(fill=tk.X)
        for col in range(2):
            opts_grid.columnconfigure(col, weight=1, uniform="opts")
        self._build_scale_option(opts_grid, 0, "opts_dpi", self.dpi, self.dpi_value, 100, 400, 10)
        self._build_scale_option(opts_grid, 1, "opts_stroke", self.stroke_tol, self.stroke_value, 0, 10, 0.5)
        # The scale rows are built by a helper, so the tooltips hang off their frames.
        for idx, key in ((0, "tip_dpi"), (1, "tip_stroke")):
            add_tooltip(opts_grid.grid_slaves(row=0, column=idx)[0], lambda k=key: self._tr(k))  # type: ignore[misc]

        advanced_grid = tk.Frame(self.options_body, bg=PANEL)
        advanced_grid.pack(fill=tk.X, pady=(10, 0))
        advanced_grid.columnconfigure(0, weight=1, uniform="advanced")
        advanced_grid.columnconfigure(1, weight=2, uniform="advanced")
        strict_frame = tk.Frame(advanced_grid, bg=PANEL)
        strict_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.options_strictness_label = ttk.Label(
            strict_frame,
            text=self._tr("opts_strictness"),
            style="SubHeader.TLabel",
            background=PANEL,
        )
        self.options_strictness_label.pack(anchor="w", pady=(0, 6))
        strict_chips = tk.Frame(strict_frame, bg=PANEL)
        strict_chips.pack(anchor="w")
        for value in DIFF_STRICTNESS_CHOICES:
            chip = tk.Label(
                strict_chips,
                text=self._tr(f"strictness_{value}"),
                padx=14,
                pady=6,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_STRONG,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            chip.pack(side=tk.LEFT, padx=(0, 6))
            chip.bind("<Button-1>", lambda _e, v=value: self.diff_strictness.set(v))  # type: ignore[misc]
            self.strictness_chips[value] = chip
            add_tooltip(chip, lambda: self._tr("tip_strictness"))
        self.options_strictness_hint_label = ttk.Label(
            strict_frame,
            text=self._tr("opts_strictness_hint"),
            style="Hint.TLabel",
            background=PANEL,
        )
        self.options_strictness_hint_label.pack(anchor="w", pady=(8, 0))

        exclude_frame = tk.Frame(advanced_grid, bg=PANEL)
        exclude_frame.grid(row=0, column=1, sticky="ew")
        self.options_exclude_label = ttk.Label(
            exclude_frame,
            text=self._tr("opts_exclude"),
            style="SubHeader.TLabel",
            background=PANEL,
        )
        self.options_exclude_label.pack(anchor="w", pady=(0, 6))
        exclude_entry_row = tk.Frame(exclude_frame, bg=PANEL)
        exclude_entry_row.pack(fill=tk.X)
        exclude_entry = ttk.Entry(exclude_entry_row, textvariable=self.exclude_regions, style="Path.TEntry")
        exclude_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        add_tooltip(exclude_entry, lambda: self._tr("tip_exclude"))
        self.exclude_pick_btn = ttk.Button(
            exclude_entry_row,
            text=self._tr("btn_pick_exclude"),
            style="Small.TButton",
            command=self._pick_exclude_regions,
        )
        self.exclude_pick_btn.pack(side=tk.LEFT, padx=(6, 0))
        add_tooltip(self.exclude_pick_btn, lambda: self._tr("tip_exclude_pick"))
        self.options_exclude_hint_label = ttk.Label(
            exclude_frame,
            text=self._tr("opts_exclude_hint"),
            style="Hint.TLabel",
            background=PANEL,
        )
        self.options_exclude_hint_label.pack(anchor="w", pady=(6, 0))

        # Row 1: bbox merge (experimental) + keep debug — full width, two sub-frames.
        advanced_row2 = tk.Frame(advanced_grid, bg=PANEL)
        advanced_row2.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        advanced_row2.columnconfigure(0, weight=1, uniform="advanced2")
        advanced_row2.columnconfigure(1, weight=1, uniform="advanced2")

        bbox_frame = tk.Frame(advanced_row2, bg=PANEL)
        bbox_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        bbox_head = tk.Frame(bbox_frame, bg=PANEL)
        bbox_head.pack(fill=tk.X)
        self.options_bbox_merge_label = ttk.Label(
            bbox_head,
            text=self._tr("opts_bbox_merge"),
            style="SubHeader.TLabel",
            background=PANEL,
        )
        self.options_bbox_merge_label.pack(side=tk.LEFT, pady=(0, 6))
        self.bbox_merge_chip = ttk.Checkbutton(
            bbox_head,
            text=self._tr("opts_enable"),
            variable=self.bbox_merge,
            onvalue="on",
            offvalue="off",
            command=self._update_bbox_merge_fields,
        )
        self.bbox_merge_chip.pack(side=tk.LEFT, padx=(8, 0))
        add_tooltip(self.bbox_merge_chip, lambda: self._tr("tip_bbox_merge"))
        bbox_fields = tk.Frame(bbox_frame, bg=PANEL)
        bbox_fields.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(bbox_fields, text=self._tr("opts_bbox_merge_gap"), style="FileLabel.TLabel", background=PANEL).pack(side=tk.LEFT)
        self.bbox_merge_gap_entry = ttk.Entry(bbox_fields, textvariable=self.bbox_merge_gap, width=6, state=tk.DISABLED)
        self.bbox_merge_gap_entry.pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(bbox_fields, text=self._tr("opts_bbox_merge_ratio"), style="FileLabel.TLabel", background=PANEL).pack(side=tk.LEFT)
        self.bbox_merge_max_ratio_entry = ttk.Entry(bbox_fields, textvariable=self.bbox_merge_max_ratio, width=6, state=tk.DISABLED)
        self.bbox_merge_max_ratio_entry.pack(side=tk.LEFT, padx=(6, 0))
        self.options_bbox_merge_hint_label = ttk.Label(
            bbox_frame,
            text=self._tr("opts_bbox_merge_hint"),
            style="Hint.TLabel",
            background=PANEL,
        )
        self.options_bbox_merge_hint_label.pack(anchor="w", pady=(6, 0))

        keep_debug_frame = tk.Frame(advanced_row2, bg=PANEL)
        keep_debug_frame.grid(row=0, column=1, sticky="ew")
        kd_head = tk.Frame(keep_debug_frame, bg=PANEL)
        kd_head.pack(fill=tk.X)
        self.options_keep_debug_label = ttk.Label(
            kd_head,
            text=self._tr("opts_keep_debug"),
            style="SubHeader.TLabel",
            background=PANEL,
        )
        self.options_keep_debug_label.pack(side=tk.LEFT, pady=(0, 6))
        self.keep_debug_chip = ttk.Checkbutton(
            kd_head,
            text=self._tr("opts_enable"),
            variable=self.keep_debug,
            onvalue="on",
            offvalue="off",
        )
        self.keep_debug_chip.pack(side=tk.LEFT, padx=(8, 0))
        add_tooltip(self.keep_debug_chip, lambda: self._tr("tip_keep_debug"))
        self.options_keep_debug_hint_label = ttk.Label(
            keep_debug_frame,
            text=self._tr("opts_keep_debug_hint"),
            style="Hint.TLabel",
            background=PANEL,
        )
        self.options_keep_debug_hint_label.pack(anchor="w", pady=(8, 0))

        line_weight_frame = tk.Frame(advanced_grid, bg=PANEL)
        line_weight_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        lw_head = tk.Frame(line_weight_frame, bg=PANEL)
        lw_head.pack(fill=tk.X)
        self.options_line_weight_label = ttk.Label(
            lw_head,
            text=self._tr("opts_line_weight"),
            style="SubHeader.TLabel",
            background=PANEL,
        )
        self.options_line_weight_label.pack(side=tk.LEFT)
        self.ignore_line_weight_chip = ttk.Checkbutton(
            lw_head,
            text=self._tr("opts_enable"),
            variable=self.ignore_line_weight,
            onvalue="on",
            offvalue="off",
        )
        self.ignore_line_weight_chip.pack(side=tk.LEFT, padx=(8, 0))
        add_tooltip(self.ignore_line_weight_chip, lambda: self._tr("tip_line_weight"))
        self.options_line_weight_hint_label = ttk.Label(
            line_weight_frame,
            text=self._tr("opts_line_weight_hint"),
            style="Hint.TLabel",
            background=PANEL,
        )
        self.options_line_weight_hint_label.pack(anchor="w", pady=(6, 0))


    def _build_actions_section(self: AppProtocol) -> None:
        """Compare / clear / open-report buttons."""
        actions = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        actions.pack(fill=tk.X, pady=(0, 10))
        self.run_btn = self._primary_button(actions, self._tr("btn_compare_short"), self.start_compare)
        self.run_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        add_tooltip(self.run_btn, lambda: self._tr("tip_run"))
        self.from_history_btn = ttk.Button(
            actions, text=self._tr("btn_from_history"), style="Small.TButton", command=self._restore_last_inputs
        )
        self.from_history_btn.pack(side=tk.LEFT, padx=8)
        self.clear_btn = ttk.Button(actions, text=self._tr("btn_clear"), style="Small.TButton", command=self._clear_inputs)
        self.clear_btn.pack(side=tk.LEFT)
        self.open_report_btn = ttk.Button(
            actions,
            text=self._tr("btn_open_report"),
            style="Small.TButton",
            command=self._open_report,
        )
        self.open_report_btn.pack(side=tk.LEFT, padx=(8, 0))
        add_tooltip(self.open_report_btn, lambda: self._tr("tip_open_report"))
        self.open_run_btn = ttk.Button(
            actions,
            text=self._tr("btn_open_folder"),
            style="Small.TButton",
            command=self._open_run_folder,
        )
        self.open_run_btn.pack(side=tk.LEFT, padx=(8, 0))
        add_tooltip(self.open_run_btn, lambda: self._tr("tip_open_folder"))


    def _build_status_panel(self: AppProtocol) -> None:
        """Status line, live-report banner and the progress bar."""
        status_wrap = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        status_wrap.pack(fill=tk.X)
        # An accent rule down the left edge — the status strip is a distinct zone,
        # not just another beige band.
        tk.Frame(status_wrap, bg=ACCENT, width=SECTION_BAR_PX).pack(side=tk.LEFT, fill=tk.Y)
        status_panel = tk.Frame(status_wrap, bg=BG_INFO, padx=12, pady=11)
        status_panel.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ok_dot = tk.Canvas(status_panel, width=8, height=8, bg=BG_INFO, highlightthickness=0)
        ok_dot.pack(side=tk.LEFT, padx=(0, 10))
        ok_dot.create_oval(1, 1, 7, 7, fill=ACCENT, outline=ACCENT)
        self.status_text_label = tk.Label(
            status_panel,
            textvariable=self.status,
            bg=BG_INFO,
            fg=ACCENT_DARK,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        self.status_text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Bold banner shown when a live report becomes available; hidden on completion.
        self.report_ready_label = tk.Label(
            status_panel,
            text=self._tr("status_report_ready"),
            bg=BG_INFO,
            fg=ACCENT,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.report_ready_label.bind("<Button-1>", lambda _e: self._open_report())
        self.progress = ttk.Progressbar(status_panel, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress.pack_forget()
        ttk.Label(status_panel, textvariable=self.elapsed, width=7, anchor="e", background=BG_INFO).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(status_panel, textvariable=self.progress_pct, width=6, anchor="e", background=BG_INFO).pack(side=tk.LEFT, padx=(4, 0))
