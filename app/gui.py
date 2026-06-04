from __future__ import annotations

import sqlite3
import tkinter as tk
from datetime import date
from decimal import InvalidOperation
from pathlib import Path
from tkinter import messagebox, ttk

from app.db import create_transaction, fetch_transaction, list_materials
from app.models import LineItemInput, MaterialType, TransactionInput
from app.pricing import decimal_from_user, format_cents
from app.reports import export_daily_report_csv, generate_daily_report, render_daily_report_html


class RecyclingPOSApp(tk.Tk):
    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__()
        self.conn = conn
        self.title("Recycling Center POS MVP")
        self.geometry("980x680")
        self.configure(background="#c0c0c0")
        self.materials = list_materials(conn)
        self.material_by_label = {self._label(material): material for material in self.materials}
        self.material_by_id = {material.id: material for material in self.materials}
        self.pending_items: list[LineItemInput] = []
        self._build_style()
        self._build()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("classic")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#c0c0c0")
        style.configure("TLabel", background="#c0c0c0", font=("Tahoma", 9))
        style.configure("TButton", font=("Tahoma", 9))
        style.configure("Header.TLabel", font=("Tahoma", 12, "bold"))

    def _build(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Recycling Center POS - Local MVP", style="Header.TLabel").pack(
            anchor="w"
        )

        entry_panel = ttk.Frame(root)
        entry_panel.pack(fill="x", pady=8)
        ttk.Label(entry_panel, text="Material").grid(row=0, column=0, sticky="w")
        self.material_var = tk.StringVar(value=next(iter(self.material_by_label), ""))
        material_combo = ttk.Combobox(
            entry_panel,
            textvariable=self.material_var,
            values=list(self.material_by_label),
            width=48,
            state="readonly",
        )
        material_combo.grid(row=1, column=0, sticky="we", padx=(0, 8))

        ttk.Label(entry_panel, text="Quantity").grid(row=0, column=1, sticky="w")
        self.quantity_var = tk.StringVar(value="1")
        ttk.Entry(entry_panel, textvariable=self.quantity_var, width=12).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )

        ttk.Label(entry_panel, text="Description override").grid(row=0, column=2, sticky="w")
        self.description_var = tk.StringVar()
        ttk.Entry(entry_panel, textvariable=self.description_var, width=36).grid(
            row=1, column=2, sticky="we", padx=(0, 8)
        )

        ttk.Button(entry_panel, text="Add Line", command=self.add_line_item).grid(
            row=1, column=3, sticky="e"
        )
        entry_panel.columnconfigure(2, weight=1)

        self.tree = ttk.Treeview(
            root,
            columns=("material", "quantity", "unit", "rate"),
            show="headings",
            height=8,
        )
        for col, width in (
            ("material", 390),
            ("quantity", 100),
            ("unit", 90),
            ("rate", 110),
        ):
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", pady=(0, 8))

        meta = ttk.Frame(root)
        meta.pack(fill="x", pady=(0, 8))
        ttk.Label(meta, text="Operator initials").grid(row=0, column=0, sticky="w")
        self.operator_var = tk.StringVar(value="NA")
        ttk.Entry(meta, textvariable=self.operator_var, width=12).grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Label(meta, text="Payout method").grid(row=0, column=1, sticky="w")
        self.payout_var = tk.StringVar(value="cash")
        ttk.Entry(meta, textvariable=self.payout_var, width=16).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Label(meta, text="Transaction notes").grid(row=0, column=2, sticky="w")
        self.notes_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.notes_var, width=56).grid(
            row=1, column=2, sticky="we", padx=(0, 8)
        )
        ttk.Button(meta, text="Save Transaction", command=self.save_transaction).grid(
            row=1, column=3, sticky="e"
        )
        meta.columnconfigure(2, weight=1)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Generate Today Report", command=self.show_daily_report).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Export Today CSV", command=self.export_daily_csv).pack(
            side="left", padx=(0, 8)
        )
        self.total_var = tk.StringVar(value="Pending total: $0.00")
        ttk.Label(actions, textvariable=self.total_var, style="Header.TLabel").pack(side="right")

        self.output = tk.Text(root, height=22, font=("Courier New", 9), wrap="word")
        self.output.pack(fill="both", expand=True)
        self.output.insert(
            "1.0",
            "MVP ready. Add line items, save a transaction, then print/export from snapshots.\n",
        )

    def _label(self, material: MaterialType) -> str:
        crv = "CRV" if material.crv_eligible else "non-CRV"
        return f"{material.display_name} ({crv}, {material.unit_type})"

    def add_line_item(self) -> None:
        material = self.material_by_label.get(self.material_var.get())
        if material is None:
            messagebox.showerror("Missing material", "Select a material type.")
            return
        try:
            quantity = decimal_from_user(self.quantity_var.get())
        except (InvalidOperation, ValueError):
            messagebox.showerror("Invalid quantity", "Enter a numeric quantity.")
            return
        if quantity <= 0:
            messagebox.showerror("Invalid quantity", "Quantity must be greater than zero.")
            return
        item = LineItemInput(
            material_type_id=material.id,
            quantity=quantity,
            description=self.description_var.get(),
        )
        self.pending_items.append(item)
        rate_row = self.conn.execute(
            """
            SELECT rate_cents_per_unit FROM rates
            WHERE material_type_id = ? AND effective_to IS NULL
            ORDER BY effective_from DESC, id DESC LIMIT 1
            """,
            (material.id,),
        ).fetchone()
        rate_cents = int(rate_row["rate_cents_per_unit"]) if rate_row else 0
        self.tree.insert(
            "",
            "end",
            values=(
                item.description or material.display_name,
                str(quantity),
                material.unit_type,
                format_cents(rate_cents),
            ),
        )
        self.description_var.set("")
        self._update_pending_total_preview()

    def _update_pending_total_preview(self) -> None:
        total = 0
        for item in self.pending_items:
            material = self.material_by_id[item.material_type_id]
            row = self.conn.execute(
                """
                SELECT rate_cents_per_unit FROM rates
                WHERE material_type_id = ? AND effective_to IS NULL
                ORDER BY effective_from DESC, id DESC LIMIT 1
                """,
                (material.id,),
            ).fetchone()
            if row:
                from app.pricing import cents_for_quantity

                total += cents_for_quantity(item.quantity, int(row["rate_cents_per_unit"]))
        self.total_var.set(f"Pending total: {format_cents(total)}")

    def save_transaction(self) -> None:
        if not self.pending_items:
            messagebox.showerror("No line items", "Add at least one line item.")
            return
        tx_id = create_transaction(
            self.conn,
            TransactionInput(
                line_items=self.pending_items,
                operator_initials=self.operator_var.get(),
                payout_method=self.payout_var.get(),
                notes=self.notes_var.get(),
            ),
        )
        tx = fetch_transaction(self.conn, tx_id)
        self.pending_items.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.total_var.set("Pending total: $0.00")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", tx["receipt_snapshot_text"])

    def show_daily_report(self) -> None:
        report = generate_daily_report(self.conn, date.today())
        html = render_daily_report_html(report)
        self.output.delete("1.0", "end")
        self.output.insert("1.0", html)

    def export_daily_csv(self) -> None:
        report = generate_daily_report(self.conn, date.today())
        path = export_daily_report_csv(
            report, Path("data/exports") / f"daily-report-{date.today().isoformat()}.csv"
        )
        messagebox.showinfo("CSV exported", f"Exported {path}")
