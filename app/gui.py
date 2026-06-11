from __future__ import annotations

import sqlite3
import tkinter as tk
from datetime import date
from decimal import InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from app.db import (
    REQUIRE_OPERATOR_PIN_ADMIN_KEY,
    REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY,
    add_rate,
    change_manager_pin,
    clear_operator_pin,
    create_manager_pin,
    create_material_type,
    create_operator,
    create_transaction,
    fetch_transaction,
    format_operator_label,
    get_current_rate,
    get_bool_setting,
    has_manager_pin,
    has_active_operator,
    list_audit_entries,
    list_materials,
    list_operators,
    list_transactions,
    list_rates,
    set_bool_setting,
    set_material_active,
    set_operator_active,
    set_operator_pin,
    update_material_type,
    update_operator,
    update_rate_metadata,
    verify_manager_pin,
    verify_operator_pin,
    void_transaction,
)
from app.models import LineItemInput, MaterialType, Operator, TransactionInput
from app.maintenance import (
    create_database_backup,
    default_audit_export_name,
    default_backup_name,
    default_pre_restore_backup_name,
    export_audit_log_csv,
    get_connection_db_path,
    restore_database_from_backup,
)
from app.permissions import has_permission
from app.pricing import dollars_to_cents, decimal_from_user, format_cents
from app.receipt import (
    ReceiptPrintUnavailable,
    export_receipt_pdf,
    mark_voided_receipt_text,
    print_receipt_text,
)
from app.reports import (
    export_daily_report_csv,
    export_feet_closeout_csv,
    export_feet_closeout_pdf,
    generate_daily_report,
    generate_feet_closeout_report,
    record_feet_closeout,
    render_daily_report_html,
    render_feet_closeout_html,
)


class RecyclingPOSApp(tk.Tk):
    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__()
        self.conn = conn
        self.title("Recycling Center POS MVP")
        self.geometry("980x680")
        self.configure(background="#c0c0c0")
        self.materials: list[MaterialType] = []
        self.material_by_label: dict[str, MaterialType] = {}
        self.material_by_id: dict[int, MaterialType] = {}
        self.operators: list[Operator] = []
        self.operator_by_label: dict[str, Operator] = {}
        self.verified_operator_id: int | None = None
        self.last_transaction_id: str | None = None
        self.pending_items: list[LineItemInput] = []
        self.material_combo: ttk.Combobox | None = None
        self.operator_combo: ttk.Combobox | None = None
        self._build_style()
        self.refresh_material_choices()
        self.refresh_operator_choices()
        self._build()
        self.after(100, self.ensure_first_operator)

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
        self.material_combo = ttk.Combobox(
            entry_panel,
            textvariable=self.material_var,
            values=list(self.material_by_label),
            width=48,
            state="readonly",
        )
        self.material_combo.grid(row=1, column=0, sticky="we", padx=(0, 8))

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
        ttk.Label(meta, text="Operator").grid(row=0, column=0, sticky="w")
        self.operator_var = tk.StringVar(value=next(iter(self.operator_by_label), ""))
        self.operator_combo = ttk.Combobox(
            meta,
            textvariable=self.operator_var,
            values=list(self.operator_by_label),
            width=32,
            state="readonly",
        )
        self.operator_combo.grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        self.operator_combo.bind("<<ComboboxSelected>>", self.on_operator_changed)
        self.operator_status_var = tk.StringVar(value="No operator selected")
        ttk.Button(meta, text="Verify Operator", command=self.verify_selected_operator).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Label(meta, textvariable=self.operator_status_var).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Label(meta, text="Payout method").grid(row=0, column=2, sticky="w")
        self.payout_var = tk.StringVar(value="cash")
        ttk.Entry(meta, textvariable=self.payout_var, width=16).grid(
            row=1, column=2, sticky="w", padx=(0, 8)
        )
        ttk.Label(meta, text="Transaction notes").grid(row=0, column=3, sticky="w")
        self.notes_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.notes_var, width=56).grid(
            row=1, column=3, sticky="we", padx=(0, 8)
        )
        ttk.Button(meta, text="Save Transaction", command=self.save_transaction).grid(
            row=1, column=4, sticky="e"
        )
        meta.columnconfigure(3, weight=1)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Print Receipt", command=self.print_current_receipt).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Save/Export Receipt", command=self.export_current_receipt).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            actions,
            text="Run FEET End-of-Day Closeout",
            command=self.run_feet_closeout,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generate Today Report", command=self.show_daily_report).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Export Today CSV", command=self.export_daily_csv).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            actions,
            text="Transaction History",
            command=self.open_transaction_history,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Admin Settings", command=self.open_admin_settings).pack(
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
        self.update_operator_status()

    def _label(self, material: MaterialType) -> str:
        crv = "CRV" if material.crv_eligible else "non-CRV"
        return f"{material.display_name} ({crv}, {material.unit_type})"

    def refresh_material_choices(self) -> None:
        self.materials = list_materials(self.conn, active_only=True)
        self.material_by_label = {self._label(material): material for material in self.materials}
        self.material_by_id = {material.id: material for material in self.materials}
        if self.material_combo is not None:
            labels = list(self.material_by_label)
            self.material_combo.configure(values=labels)
            self.material_var.set(labels[0] if labels else "")

    def refresh_operator_choices(self) -> None:
        self.operators = list_operators(self.conn, active_only=True)
        self.operator_by_label = {
            format_operator_label(operator): operator for operator in self.operators
        }
        if self.operator_combo is not None:
            current = self.operator_var.get()
            labels = list(self.operator_by_label)
            self.operator_combo.configure(values=labels)
            if current in self.operator_by_label:
                self.operator_var.set(current)
            else:
                self.operator_var.set(labels[0] if labels else "")
            current_operator = self.current_operator()
            if current_operator is None or current_operator.id != self.verified_operator_id:
                self.verified_operator_id = None
            self.update_operator_status()

    def ensure_first_operator(self) -> None:
        if has_active_operator(self.conn):
            return
        name = simpledialog.askstring(
            "Create First Operator",
            "No active operator exists. Enter the first operator name:",
            parent=self,
        )
        if not name:
            messagebox.showerror(
                "Operator required",
                "Create an operator before saving transactions.",
            )
            return
        initials = simpledialog.askstring(
            "Create First Operator",
            "Enter operator initials:",
            parent=self,
        )
        if not initials:
            messagebox.showerror(
                "Operator required",
                "Operator initials are required.",
            )
            return
        operator_pin = simpledialog.askstring(
            "Create First Operator",
            "Optional: enter an individual operator PIN, or leave blank to skip:",
            show="*",
            parent=self,
        )
        try:
            create_operator(
                self.conn,
                display_name=name,
                initials=initials,
                role="manager",
                initial_pin=operator_pin or None,
                audit=False,
            )
        except ValueError as exc:
            messagebox.showerror("Operator setup failed", str(exc))
            return
        self.refresh_operator_choices()
        self.update_operator_status()

    def current_operator(self) -> Operator | None:
        return self.operator_by_label.get(self.operator_var.get())

    def current_operator_audit_label(self) -> str:
        operator = self.current_operator()
        return format_operator_label(operator) if operator is not None else "manager"

    def on_operator_changed(self, _event: tk.Event) -> None:
        self.verified_operator_id = None
        self.update_operator_status()

    def update_operator_status(self) -> None:
        if not hasattr(self, "operator_status_var"):
            return
        operator = self.current_operator()
        if operator is None:
            self.operator_status_var.set("No operator selected")
        elif not operator.pin_set:
            self.operator_status_var.set("PIN not set")
        elif self.verified_operator_id == operator.id:
            self.operator_status_var.set("Verified")
        else:
            self.operator_status_var.set("Verification required")

    def verify_selected_operator(self) -> bool:
        operator = self.current_operator()
        if operator is None:
            messagebox.showerror("Operator required", "Select an active operator.")
            return False
        if not operator.pin_set:
            self.verified_operator_id = None
            self.update_operator_status()
            messagebox.showinfo("PIN not set", "This operator does not have an individual PIN.")
            return False
        pin = simpledialog.askstring(
            "Operator PIN",
            f"Enter PIN for {format_operator_label(operator)}:",
            show="*",
            parent=self,
        )
        if pin is None:
            return False
        verified = verify_operator_pin(
            self.conn,
            operator.id,
            pin,
            operator=format_operator_label(operator),
            audit=True,
        )
        if verified:
            self.verified_operator_id = operator.id
            self.update_operator_status()
            return True
        self.verified_operator_id = None
        self.update_operator_status()
        messagebox.showerror("Verification failed", "Incorrect operator PIN.")
        return False

    def operator_is_verified(self, operator: Operator) -> bool:
        return operator.pin_set and self.verified_operator_id == operator.id

    def require_permission(self, permission: str, action_label: str) -> bool:
        operator = self.current_operator()
        if has_permission(operator, permission):
            return True
        if operator is None:
            operator_label = "unknown"
            reason = "No active operator is selected."
        else:
            operator_label = format_operator_label(operator)
            reason = f"{operator.role} role cannot {action_label.lower()}."
        with self.conn:
            from app.db import record_admin_access_denied

            record_admin_access_denied(
                self.conn,
                permission=permission,
                reason=reason,
                operator=operator_label,
                action_label=action_label,
            )
        messagebox.showerror("Access denied", reason)
        return False

    def require_admin_action(self, permission: str, action_label: str) -> bool:
        if not self.require_permission(permission, action_label):
            return False
        return self.require_operator_pin_for_admin_action(action_label)

    def require_operator_pin_for_admin_action(self, action_label: str) -> bool:
        if not get_bool_setting(self.conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY):
            return True
        operator = self.current_operator()
        if operator is None:
            messagebox.showerror("Operator required", "Select an active operator.")
            return False
        if not operator.pin_set:
            messagebox.showerror(
                "Operator PIN required",
                "Operator PIN enforcement is enabled for admin actions, but this operator has no PIN.",
            )
            return False
        if self.operator_is_verified(operator):
            return True
        messagebox.showinfo(
            "Operator verification required",
            f"Verify {format_operator_label(operator)} before you {action_label.lower()}.",
        )
        return self.verify_selected_operator()

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
        try:
            rate_cents = get_current_rate(self.conn, material.id, date.today().isoformat())
        except ValueError as exc:
            messagebox.showerror("Missing current rate", str(exc))
            return
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
            try:
                rate_cents = get_current_rate(self.conn, material.id, date.today().isoformat())
            except ValueError:
                continue
            from app.pricing import cents_for_quantity

            total += cents_for_quantity(item.quantity, rate_cents)
        self.total_var.set(f"Pending total: {format_cents(total)}")

    def save_transaction(self) -> None:
        if not self.pending_items:
            messagebox.showerror("No line items", "Add at least one line item.")
            return
        operator = self.current_operator()
        if operator is None:
            messagebox.showerror("Operator required", "Select an active operator.")
            return
        if get_bool_setting(self.conn, REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY):
            if not operator.pin_set:
                messagebox.showerror(
                    "Operator PIN required",
                    "Operator PIN enforcement is enabled, but this operator has no PIN.",
                )
                return
            if not self.operator_is_verified(operator):
                messagebox.showerror(
                    "Operator verification required",
                    "Verify the selected operator before saving this transaction.",
                )
                return
        try:
            tx_id = create_transaction(
                self.conn,
                TransactionInput(
                    line_items=self.pending_items,
                    operator_id=operator.id,
                    operator_verified=self.operator_is_verified(operator),
                    payout_method=self.payout_var.get(),
                    notes=self.notes_var.get(),
                ),
            )
        except ValueError as exc:
            messagebox.showerror("Transaction validation", str(exc))
            return
        tx = fetch_transaction(self.conn, tx_id)
        self.last_transaction_id = tx_id
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

    def print_current_receipt(self) -> None:
        if not self.require_permission("print_receipt", "print receipts"):
            return
        receipt_text = self.current_receipt_text()
        if receipt_text is None:
            messagebox.showerror("No receipt", "Save or select a transaction receipt first.")
            return
        try:
            print_receipt_text(receipt_text)
        except ReceiptPrintUnavailable as exc:
            messagebox.showerror("Printer unavailable", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Print failed", str(exc))
            return
        messagebox.showinfo("Receipt sent", "Receipt sent to the operating system print queue.")

    def export_current_receipt(self) -> None:
        if not self.require_permission("export_receipt", "export receipts"):
            return
        receipt_text = self.current_receipt_text()
        if receipt_text is None:
            messagebox.showerror("No receipt", "Save or select a transaction receipt first.")
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Receipt PDF",
            initialdir=str(Path("data/exports")),
            initialfile=f"receipt-{date.today().isoformat()}.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_receipt_pdf(receipt_text, path, title="Recycling POS Receipt")
        except OSError as exc:
            messagebox.showerror("Receipt export failed", str(exc))
            return
        messagebox.showinfo("Receipt exported", f"Exported {path}")

    def current_receipt_text(self) -> str | None:
        if self.last_transaction_id:
            row = fetch_transaction(self.conn, self.last_transaction_id)
            return _receipt_text_from_transaction_row(row)
        text = self.output.get("1.0", "end").strip()
        if "Transaction ID:" in text:
            return text
        return None

    def run_feet_closeout(self) -> None:
        if not self.require_admin_action("run_feet_closeout", "run FEET closeout"):
            return
        operator = self.current_operator()
        if operator is None:
            messagebox.showerror("Operator required", "Select an active manager/admin operator.")
            return
        if not has_manager_pin(self.conn):
            messagebox.showerror(
                "Manager PIN required",
                "Create a manager PIN in Admin Settings before running FEET closeout.",
            )
            return
        manager_pin = self.prompt_manager_pin("run FEET closeout")
        if manager_pin is None:
            return
        expected_cash = self._optional_money_prompt("Expected Cash", "Expected cash amount:")
        if expected_cash is False:
            return
        actual_cash = self._optional_money_prompt("Actual Cash", "Actual cash amount:")
        if actual_cash is False:
            return
        discrepancy_notes = simpledialog.askstring(
            "Discrepancy Notes",
            "Optional discrepancy notes:",
            parent=self,
        )
        if discrepancy_notes is None:
            discrepancy_notes = ""
        try:
            report = generate_feet_closeout_report(
                self.conn,
                date.today(),
                expected_cash_cents=expected_cash,
                actual_cash_cents=actual_cash,
                discrepancy_notes=discrepancy_notes,
                operator_attestation=f"{format_operator_label(operator)} attests review complete",
                manager_approval="Manager PIN approval captured",
            )
            closeout_id = record_feet_closeout(
                self.conn,
                report,
                generated_by_operator_id=operator.id,
                manager_pin=manager_pin,
                operator_verified=self.operator_is_verified(operator),
                operator_label=self.current_operator_audit_label(),
            )
            export_dir = Path("data/exports")
            csv_path = export_feet_closeout_csv(
                report, export_dir / f"feet-closeout-{report['date']}.csv"
            )
            pdf_path = export_feet_closeout_pdf(
                report, export_dir / f"feet-closeout-{report['date']}.pdf"
            )
        except (PermissionError, ValueError, OSError) as exc:
            messagebox.showerror("FEET closeout failed", str(exc))
            return
        self.output.delete("1.0", "end")
        self.output.insert("1.0", render_feet_closeout_html(report))
        messagebox.showinfo(
            "FEET closeout complete",
            f"Closeout #{closeout_id} saved.\nCSV: {csv_path}\nPDF: {pdf_path}",
        )

    def _optional_money_prompt(self, title: str, prompt: str) -> int | None | bool:
        raw = simpledialog.askstring(title, prompt + "\nLeave blank if not counted.", parent=self)
        if raw is None:
            return False
        if not raw.strip():
            return None
        try:
            return dollars_to_cents(raw)
        except (InvalidOperation, ValueError) as exc:
            messagebox.showerror("Invalid amount", str(exc))
            return False

    def open_transaction_history(self) -> None:
        if not self.require_permission(
            "view_voided_transactions", "view transaction history"
        ):
            return
        TransactionHistoryWindow(self, self.conn)

    def open_admin_settings(self) -> None:
        if not self._manager_pin_allows_admin():
            return
        AdminSettingsWindow(self, self.conn)

    def _manager_pin_allows_admin(self) -> bool:
        if not self.require_permission("access_admin_settings", "open Admin Settings"):
            return False
        if not has_manager_pin(self.conn):
            pin = simpledialog.askstring(
                "Create Manager PIN",
                "No manager PIN exists. Create a manager PIN:",
                show="*",
                parent=self,
            )
            if not pin:
                return False
            confirm = simpledialog.askstring(
                "Confirm Manager PIN",
                "Confirm the new manager PIN:",
                show="*",
                parent=self,
            )
            if pin != confirm:
                messagebox.showerror("PIN setup failed", "Manager PIN entries did not match.")
                return False
            try:
                create_manager_pin(
                    self.conn,
                    pin,
                    operator=self.current_operator_audit_label(),
                )
            except ValueError as exc:
                messagebox.showerror("PIN setup failed", str(exc))
                return False
            messagebox.showinfo("PIN created", "Manager PIN created.")
            return self.require_operator_pin_for_admin_action("open Admin Settings")

        pin = simpledialog.askstring(
            "Manager PIN",
            "Enter manager PIN:",
            show="*",
            parent=self,
        )
        if pin is None:
            return False
        if not verify_manager_pin(self.conn, pin):
            messagebox.showerror("Access denied", "Incorrect manager PIN.")
            return False
        return self.require_operator_pin_for_admin_action("open Admin Settings")

    def prompt_manager_pin(self, action_label: str) -> str | None:
        pin = simpledialog.askstring(
            "Confirm Manager PIN",
            f"Enter manager PIN to {action_label}:",
            show="*",
            parent=self,
        )
        return pin


class TransactionHistoryWindow(tk.Toplevel):
    def __init__(self, app: RecyclingPOSApp, conn: sqlite3.Connection) -> None:
        super().__init__(app)
        self.app = app
        self.conn = conn
        self.title("Transaction History")
        self.geometry("960x620")
        self.configure(background="#c0c0c0")
        self.selected_transaction_id: str | None = None
        self._build()
        self.refresh_transactions()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            root,
            columns=("id", "created", "status", "operator", "total"),
            show="headings",
            height=10,
        )
        headings = (
            ("id", "Transaction ID", 260),
            ("created", "Created", 150),
            ("status", "Status", 80),
            ("operator", "Operator", 170),
            ("total", "Total", 90),
        )
        for col, label, width in headings:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.on_transaction_select)

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Refresh", command=self.refresh_transactions).pack(
            side="left", padx=(0, 8)
        )
        if self.app.current_operator() is not None:
            if self.app.require_permission("print_receipt", "print receipts"):
                ttk.Button(
                    buttons,
                    text="Print Receipt",
                    command=self.print_selected_receipt,
                ).pack(side="left", padx=(0, 8))
            if self.app.require_permission("export_receipt", "export receipts"):
                ttk.Button(
                    buttons,
                    text="Export Receipt PDF",
                    command=self.export_selected_receipt,
                ).pack(side="left", padx=(0, 8))
            if self.app.require_permission("void_transaction", "void transactions"):
                ttk.Button(
                    buttons,
                    text="Void Selected",
                    command=self.void_selected_transaction,
                ).pack(side="left", padx=(0, 8))
            if self.app.require_permission("correct_transaction", "correct transactions"):
                ttk.Button(
                    buttons,
                    text="Correction Workflow",
                    command=self.show_correction_placeholder,
                ).pack(side="left", padx=(0, 8))

        self.detail = tk.Text(root, height=24, font=("Courier New", 9), wrap="word")
        self.detail.pack(fill="both", expand=True)

    def selected_receipt_text(self) -> str | None:
        if self.selected_transaction_id is None:
            messagebox.showerror("No transaction selected", "Select a transaction first.")
            return None
        row = fetch_transaction(self.conn, self.selected_transaction_id)
        return _receipt_text_from_transaction_row(row)

    def print_selected_receipt(self) -> None:
        receipt_text = self.selected_receipt_text()
        if receipt_text is None:
            return
        try:
            print_receipt_text(receipt_text)
        except ReceiptPrintUnavailable as exc:
            messagebox.showerror("Printer unavailable", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Print failed", str(exc))
            return
        messagebox.showinfo("Receipt sent", "Receipt sent to the operating system print queue.")

    def export_selected_receipt(self) -> None:
        receipt_text = self.selected_receipt_text()
        if receipt_text is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Receipt PDF",
            initialdir=str(Path("data/exports")),
            initialfile=f"receipt-{self.selected_transaction_id}.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_receipt_pdf(receipt_text, path, title="Recycling POS Receipt")
        except OSError as exc:
            messagebox.showerror("Receipt export failed", str(exc))
            return
        messagebox.showinfo("Receipt exported", f"Exported {path}")

    def refresh_transactions(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in list_transactions(self.conn):
            operator = _operator_label_from_transaction_row(row)
            self.tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    row["id"],
                    row["created_at"],
                    row["status"],
                    operator,
                    format_cents(int(row["total_cents"])),
                ),
            )

    def on_transaction_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self.selected_transaction_id = selected[0]
        row = fetch_transaction(self.conn, self.selected_transaction_id)
        receipt_text = _receipt_text_from_transaction_row(row)
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", receipt_text)

    def void_selected_transaction(self) -> None:
        if self.selected_transaction_id is None:
            messagebox.showerror("No transaction selected", "Select a transaction first.")
            return
        if not self.app.require_admin_action("void_transaction", "void transactions"):
            return
        row = fetch_transaction(self.conn, self.selected_transaction_id)
        if row["status"] == "voided":
            messagebox.showerror("Already voided", "This transaction is already voided.")
            return
        reason = simpledialog.askstring(
            "Void Transaction",
            "Enter the required void reason:",
            parent=self,
        )
        if reason is None:
            return
        if not reason.strip():
            messagebox.showerror("Reason required", "A void reason is required.")
            return
        pin = self.app.prompt_manager_pin("void this transaction")
        if pin is None:
            return
        operator = self.app.current_operator()
        if operator is None:
            messagebox.showerror("Operator required", "Select an active operator.")
            return
        try:
            void_transaction(
                self.conn,
                self.selected_transaction_id,
                reason,
                acting_operator_id=operator.id,
                manager_pin=pin,
                operator_verified=self.app.operator_is_verified(operator),
                operator=self.app.current_operator_audit_label(),
            )
        except (PermissionError, ValueError) as exc:
            messagebox.showerror("Void failed", str(exc))
            return
        self.refresh_transactions()
        self.on_transaction_select(tk.Event())
        messagebox.showinfo("Transaction voided", "Transaction voided and audit logged.")

    def show_correction_placeholder(self) -> None:
        if not self.app.require_admin_action("correct_transaction", "correct transactions"):
            return
        messagebox.showinfo(
            "Correction workflow pending",
            "Full non-destructive correction transactions are not implemented yet. "
            "For this MVP, void the incorrect transaction with a reason and enter a new transaction.",
        )


def _operator_label_from_transaction_row(row: sqlite3.Row) -> str:
    name = str(row["operator_display_name_snapshot"] or "").strip()
    initials = str(row["operator_initials_snapshot"] or row["operator_initials"] or "").strip()
    if name and initials:
        return f"{name} ({initials})"
    return initials or name or "Unknown"


def _operator_label(name: str, initials: str) -> str:
    name = (name or "").strip()
    initials = (initials or "").strip()
    if name and initials:
        return f"{name} ({initials})"
    return initials or name or "Unknown"


def _receipt_text_from_transaction_row(row: sqlite3.Row) -> str:
    receipt_text = row["receipt_snapshot_text"]
    if row["status"] == "voided":
        receipt_text = mark_voided_receipt_text(
            receipt_text,
            voided_at=row["voided_at"] or "",
            reason=row["void_reason"] or "",
            approved_by=_operator_label(
                row["voided_by_operator_name_snapshot"],
                row["voided_by_operator_initials_snapshot"],
            ),
        )
    return receipt_text


class AdminSettingsWindow(tk.Toplevel):
    def __init__(self, app: RecyclingPOSApp, conn: sqlite3.Connection) -> None:
        super().__init__(app)
        self.app = app
        self.conn = conn
        self.title("Admin Settings")
        self.geometry("980x620")
        self.configure(background="#c0c0c0")
        self.selected_material_id: int | None = None
        self.selected_rate_id: int | None = None
        self.selected_operator_id: int | None = None
        self.material_rate_labels: dict[str, MaterialType] = {}
        self._build()
        self.refresh_materials()
        self.refresh_rates()
        self.refresh_operators()
        self.refresh_audit_log()

    def _build(self) -> None:
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.material_tab = ttk.Frame(tabs, padding=8)
        self.rate_tab = ttk.Frame(tabs, padding=8)
        self.operator_tab = ttk.Frame(tabs, padding=8)
        self.audit_tab = ttk.Frame(tabs, padding=8)
        self.settings_tab = ttk.Frame(tabs, padding=8)
        tabs.add(self.material_tab, text="Materials")
        tabs.add(self.rate_tab, text="Rates")
        tabs.add(self.operator_tab, text="Operators")
        tabs.add(self.audit_tab, text="Audit Log")
        tabs.add(self.settings_tab, text="Settings")
        self._build_material_tab()
        self._build_rate_tab()
        self._build_operator_tab()
        self._build_audit_tab()
        self._build_settings_tab()

    def _build_material_tab(self) -> None:
        self.material_tree = ttk.Treeview(
            self.material_tab,
            columns=("id", "name", "category", "group", "crv", "unit", "active", "sort"),
            show="headings",
            height=10,
        )
        headings = (
            ("id", "ID", 45),
            ("name", "Display Name", 230),
            ("category", "Category", 140),
            ("group", "Report Group", 150),
            ("crv", "CRV", 55),
            ("unit", "Unit", 75),
            ("active", "Active", 65),
            ("sort", "Sort", 55),
        )
        for col, label, width in headings:
            self.material_tree.heading(col, text=label)
            self.material_tree.column(col, width=width, anchor="w")
        self.material_tree.pack(fill="x", pady=(0, 8))
        self.material_tree.bind("<<TreeviewSelect>>", self.on_material_select)

        form = ttk.Frame(self.material_tab)
        form.pack(fill="x")
        self.material_name = tk.StringVar()
        self.material_category = tk.StringVar()
        self.material_group = tk.StringVar()
        self.material_crv = tk.BooleanVar(value=False)
        self.material_unit = tk.StringVar(value="weight")
        self.material_active = tk.BooleanVar(value=True)
        self.material_sort = tk.StringVar(value="0")
        self.material_notes = tk.StringVar()
        fields = [
            ("Display name", self.material_name, 0, 0, 34),
            ("Category", self.material_category, 0, 1, 24),
            ("Report group", self.material_group, 0, 2, 24),
            ("Sort order", self.material_sort, 0, 3, 8),
            ("Notes", self.material_notes, 2, 0, 80),
        ]
        for label, variable, row, col, width in fields:
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8))
            ttk.Entry(form, textvariable=variable, width=width).grid(
                row=row + 1, column=col, sticky="we", padx=(0, 8), pady=(0, 6)
            )
        ttk.Label(form, text="Unit type").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.material_unit,
            values=["weight", "count", "manual"],
            state="readonly",
            width=10,
        ).grid(row=1, column=4, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Checkbutton(form, text="CRV eligible", variable=self.material_crv).grid(
            row=2, column=3, sticky="w"
        )
        ttk.Checkbutton(form, text="Active", variable=self.material_active).grid(
            row=2, column=4, sticky="w"
        )
        form.columnconfigure(2, weight=1)

        buttons = ttk.Frame(self.material_tab)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="New", command=self.clear_material_form).pack(side="left")
        ttk.Button(buttons, text="Save Material", command=self.save_material).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Toggle Active", command=self.toggle_material_active).pack(
            side="left", padx=(8, 0)
        )

    def _build_rate_tab(self) -> None:
        self.rate_tree = ttk.Treeview(
            self.rate_tab,
            columns=("id", "material", "rate", "unit", "from", "to", "active", "notes"),
            show="headings",
            height=10,
        )
        headings = (
            ("id", "ID", 45),
            ("material", "Material", 260),
            ("rate", "Rate", 80),
            ("unit", "Unit", 75),
            ("from", "Start", 95),
            ("to", "End", 95),
            ("active", "Active", 65),
            ("notes", "Notes", 250),
        )
        for col, label, width in headings:
            self.rate_tree.heading(col, text=label)
            self.rate_tree.column(col, width=width, anchor="w")
        self.rate_tree.pack(fill="x", pady=(0, 8))
        self.rate_tree.bind("<<TreeviewSelect>>", self.on_rate_select)

        form = ttk.Frame(self.rate_tab)
        form.pack(fill="x")
        self.rate_material = tk.StringVar()
        self.rate_amount = tk.StringVar()
        self.rate_start = tk.StringVar(value=date.today().isoformat())
        self.rate_end = tk.StringVar()
        self.rate_active = tk.BooleanVar(value=True)
        self.rate_replace = tk.BooleanVar(value=True)
        self.rate_notes = tk.StringVar()

        ttk.Label(form, text="Material").grid(row=0, column=0, sticky="w")
        self.rate_material_combo = ttk.Combobox(
            form, textvariable=self.rate_material, state="readonly", width=42
        )
        self.rate_material_combo.grid(row=1, column=0, sticky="we", padx=(0, 8), pady=(0, 6))
        ttk.Label(form, text="Rate amount").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.rate_amount, width=12).grid(
            row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        ttk.Label(form, text="Start YYYY-MM-DD").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.rate_start, width=14).grid(
            row=1, column=2, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        ttk.Label(form, text="End optional").grid(row=0, column=3, sticky="w")
        ttk.Entry(form, textvariable=self.rate_end, width=14).grid(
            row=1, column=3, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        ttk.Label(form, text="Notes").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.rate_notes, width=82).grid(
            row=3, column=0, columnspan=3, sticky="we", padx=(0, 8), pady=(0, 6)
        )
        ttk.Checkbutton(form, text="Active", variable=self.rate_active).grid(
            row=3, column=3, sticky="w"
        )
        ttk.Checkbutton(
            form,
            text="End-date old active rate when adding",
            variable=self.rate_replace,
        ).grid(row=3, column=4, sticky="w")
        form.columnconfigure(0, weight=1)

        buttons = ttk.Frame(self.rate_tab)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="New", command=self.clear_rate_form).pack(side="left")
        ttk.Button(buttons, text="Add Rate", command=self.save_new_rate).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Update Metadata", command=self.save_rate_metadata).pack(
            side="left", padx=(8, 0)
        )

    def _build_operator_tab(self) -> None:
        self.operator_tree = ttk.Treeview(
            self.operator_tab,
            columns=("id", "name", "initials", "role", "active", "pin", "notes"),
            show="headings",
            height=10,
        )
        headings = (
            ("id", "ID", 45),
            ("name", "Display Name", 250),
            ("initials", "Initials", 80),
            ("role", "Role", 90),
            ("active", "Active", 70),
            ("pin", "PIN Set", 70),
            ("notes", "Notes", 280),
        )
        for col, label, width in headings:
            self.operator_tree.heading(col, text=label)
            self.operator_tree.column(col, width=width, anchor="w")
        self.operator_tree.pack(fill="x", pady=(0, 8))
        self.operator_tree.bind("<<TreeviewSelect>>", self.on_operator_select)

        form = ttk.Frame(self.operator_tab)
        form.pack(fill="x")
        self.operator_name = tk.StringVar()
        self.operator_initials = tk.StringVar()
        self.operator_role = tk.StringVar(value="operator")
        self.operator_active = tk.BooleanVar(value=True)
        self.operator_notes = tk.StringVar()

        ttk.Label(form, text="Display name").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.operator_name, width=34).grid(
            row=1, column=0, sticky="we", padx=(0, 8), pady=(0, 6)
        )
        ttk.Label(form, text="Initials").grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.operator_initials, width=10).grid(
            row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        ttk.Label(form, text="Role").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.operator_role,
            values=["operator", "manager", "admin"],
            state="readonly",
            width=12,
        ).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Checkbutton(form, text="Active", variable=self.operator_active).grid(
            row=1, column=3, sticky="w"
        )
        ttk.Label(form, text="Notes").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.operator_notes, width=82).grid(
            row=3, column=0, columnspan=3, sticky="we", padx=(0, 8), pady=(0, 6)
        )
        form.columnconfigure(0, weight=1)

        buttons = ttk.Frame(self.operator_tab)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="New", command=self.clear_operator_form).pack(side="left")
        ttk.Button(buttons, text="Save Operator", command=self.save_operator).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Toggle Active", command=self.toggle_operator_active).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Set/Reset PIN", command=self.set_selected_operator_pin).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Clear PIN", command=self.clear_selected_operator_pin).pack(
            side="left", padx=(8, 0)
        )

    def _build_audit_tab(self) -> None:
        filters = ttk.Frame(self.audit_tab)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Filter").pack(side="left", padx=(0, 6))
        self.audit_filter = tk.StringVar(value="all")
        ttk.Combobox(
            filters,
            textvariable=self.audit_filter,
            values=["all", "material_type", "rate", "operator", "settings"],
            state="readonly",
            width=18,
        ).pack(side="left")
        ttk.Button(filters, text="Refresh", command=self.refresh_audit_log).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(filters, text="Export CSV", command=self.export_audit_log).pack(
            side="left", padx=(8, 0)
        )

        self.audit_tree = ttk.Treeview(
            self.audit_tab,
            columns=("time", "operator", "action", "entity", "entity_id", "notes"),
            show="headings",
            height=12,
        )
        headings = (
            ("time", "Timestamp", 150),
            ("operator", "Operator", 90),
            ("action", "Action", 170),
            ("entity", "Entity", 110),
            ("entity_id", "Entity ID", 80),
            ("notes", "Notes", 290),
        )
        for col, label, width in headings:
            self.audit_tree.heading(col, text=label)
            self.audit_tree.column(col, width=width, anchor="w")
        self.audit_tree.pack(fill="x", pady=(0, 8))
        self.audit_tree.bind("<<TreeviewSelect>>", self.on_audit_select)

        self.audit_rows: dict[str, sqlite3.Row] = {}
        self.audit_detail = tk.Text(
            self.audit_tab, height=13, font=("Courier New", 9), wrap="word"
        )
        self.audit_detail.pack(fill="both", expand=True)

    def _build_settings_tab(self) -> None:
        frame = ttk.Frame(self.settings_tab)
        frame.pack(fill="x")
        ttk.Label(frame, text="Change Manager PIN", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=2, pady=(0, 8)
        )
        self.current_pin = tk.StringVar()
        self.new_pin = tk.StringVar()
        self.confirm_pin = tk.StringVar()
        fields = [
            ("Current PIN", self.current_pin),
            ("New PIN", self.new_pin),
            ("Confirm New PIN", self.confirm_pin),
        ]
        for row, (label, variable) in enumerate(fields, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8))
            ttk.Entry(frame, textvariable=variable, show="*", width=24).grid(
                row=row, column=1, sticky="w", pady=(0, 6)
            )
        ttk.Button(frame, text="Change PIN", command=self.save_manager_pin_change).grid(
            row=4, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(
            self.settings_tab,
            text="PIN protection is local-only access control for this workstation.",
        ).pack(anchor="w", pady=(18, 0))

        operator_pin_frame = ttk.Frame(self.settings_tab)
        operator_pin_frame.pack(fill="x", pady=(22, 0))
        ttk.Label(
            operator_pin_frame,
            text="Operator PIN Verification",
            style="Header.TLabel",
        ).grid(row=0, column=0, sticky="w", columnspan=2, pady=(0, 8))
        self.require_operator_pin_transactions = tk.BooleanVar(
            value=get_bool_setting(self.conn, REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY)
        )
        self.require_operator_pin_admin = tk.BooleanVar(
            value=get_bool_setting(self.conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY)
        )
        ttk.Checkbutton(
            operator_pin_frame,
            text="Require operator PIN verification for transactions",
            variable=self.require_operator_pin_transactions,
        ).grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Checkbutton(
            operator_pin_frame,
            text="Require operator PIN verification for admin actions",
            variable=self.require_operator_pin_admin,
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Button(
            operator_pin_frame,
            text="Save Operator PIN Settings",
            command=self.save_operator_pin_settings,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        backup_frame = ttk.Frame(self.settings_tab)
        backup_frame.pack(fill="x", pady=(22, 0))
        ttk.Label(backup_frame, text="Database Backup / Restore", style="Header.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Button(
            backup_frame, text="Create Database Backup", command=self.create_backup
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            backup_frame, text="Restore From Backup", command=self.restore_from_backup
        ).pack(side="left")
        ttk.Label(
            self.settings_tab,
            text="Restore replaces the local database and creates a pre-restore backup first.",
        ).pack(anchor="w", pady=(12, 0))

    def refresh_materials(self) -> None:
        for item in self.material_tree.get_children():
            self.material_tree.delete(item)
        for material in list_materials(self.conn, active_only=False):
            self.material_tree.insert(
                "",
                "end",
                iid=str(material.id),
                values=(
                    material.id,
                    material.display_name,
                    material.category,
                    material.report_grouping,
                    "yes" if material.crv_eligible else "no",
                    material.unit_type,
                    "yes" if material.active else "no",
                    material.sort_order,
                ),
            )
        labels = []
        self.material_rate_labels = {}
        for material in list_materials(self.conn, active_only=False):
            label = f"{material.display_name} ({material.unit_type})"
            labels.append(label)
            self.material_rate_labels[label] = material
        self.rate_material_combo.configure(values=labels)
        if labels and not self.rate_material.get():
            self.rate_material.set(labels[0])
        self.app.refresh_material_choices()

    def refresh_rates(self) -> None:
        for item in self.rate_tree.get_children():
            self.rate_tree.delete(item)
        for row in list_rates(self.conn):
            self.rate_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["id"],
                    row["material_display_name"],
                    format_cents(int(row["rate_cents_per_unit"])),
                    row["unit_type"],
                    row["effective_from"],
                    row["effective_to"] or "",
                    "yes" if row["active"] else "no",
                    row["notes"],
                ),
            )

    def refresh_operators(self) -> None:
        for item in self.operator_tree.get_children():
            self.operator_tree.delete(item)
        for operator in list_operators(self.conn, active_only=False):
            self.operator_tree.insert(
                "",
                "end",
                iid=str(operator.id),
                values=(
                    operator.id,
                    operator.display_name,
                    operator.initials,
                    operator.role,
                    "yes" if operator.active else "no",
                    "yes" if operator.pin_set else "no",
                    operator.notes,
                ),
            )
        self.app.refresh_operator_choices()

    def on_operator_select(self, _event: tk.Event) -> None:
        selected = self.operator_tree.selection()
        if not selected:
            return
        self.selected_operator_id = int(selected[0])
        operator = next(
            item
            for item in list_operators(self.conn, active_only=False)
            if item.id == self.selected_operator_id
        )
        self.operator_name.set(operator.display_name)
        self.operator_initials.set(operator.initials)
        self.operator_role.set(operator.role)
        self.operator_active.set(operator.active)
        self.operator_notes.set(operator.notes)

    def clear_operator_form(self) -> None:
        self.selected_operator_id = None
        self.operator_tree.selection_remove(self.operator_tree.selection())
        self.operator_name.set("")
        self.operator_initials.set("")
        self.operator_role.set("operator")
        self.operator_active.set(True)
        self.operator_notes.set("")

    def save_operator(self) -> None:
        if not self.app.require_admin_action("manage_operators", "manage operators"):
            return
        audit_operator = self.app.current_operator_audit_label()
        try:
            if self.selected_operator_id is None:
                create_operator(
                    self.conn,
                    display_name=self.operator_name.get(),
                    initials=self.operator_initials.get(),
                    role=self.operator_role.get(),
                    active=self.operator_active.get(),
                    notes=self.operator_notes.get(),
                    operator=audit_operator,
                )
            else:
                update_operator(
                    self.conn,
                    self.selected_operator_id,
                    display_name=self.operator_name.get(),
                    initials=self.operator_initials.get(),
                    role=self.operator_role.get(),
                    active=self.operator_active.get(),
                    notes=self.operator_notes.get(),
                    operator=audit_operator,
                )
        except ValueError as exc:
            messagebox.showerror("Operator validation", str(exc))
            return
        self.refresh_operators()
        self.refresh_audit_log()

    def toggle_operator_active(self) -> None:
        if not self.app.require_admin_action("manage_operators", "manage operators"):
            return
        if self.selected_operator_id is None:
            messagebox.showerror("No operator selected", "Select an operator first.")
            return
        try:
            set_operator_active(
                self.conn,
                self.selected_operator_id,
                not self.operator_active.get(),
                operator=self.app.current_operator_audit_label(),
            )
        except ValueError as exc:
            messagebox.showerror("Operator validation", str(exc))
            return
        self.refresh_operators()
        self.refresh_audit_log()

    def set_selected_operator_pin(self) -> None:
        if not self.app.require_admin_action("manage_operators", "manage operators"):
            return
        if self.selected_operator_id is None:
            messagebox.showerror("No operator selected", "Select an operator first.")
            return
        pin = simpledialog.askstring(
            "Set Operator PIN",
            "Enter the new operator PIN:",
            show="*",
            parent=self,
        )
        if pin is None:
            return
        confirm = simpledialog.askstring(
            "Confirm Operator PIN",
            "Confirm the new operator PIN:",
            show="*",
            parent=self,
        )
        if pin != confirm:
            messagebox.showerror("PIN change failed", "Operator PIN entries did not match.")
            return
        try:
            set_operator_pin(
                self.conn,
                self.selected_operator_id,
                pin,
                operator=self.app.current_operator_audit_label(),
            )
        except ValueError as exc:
            messagebox.showerror("PIN change failed", str(exc))
            return
        self.refresh_operators()
        self.refresh_audit_log()
        self.app.update_operator_status()
        messagebox.showinfo("PIN updated", "Operator PIN updated.")

    def clear_selected_operator_pin(self) -> None:
        if not self.app.require_admin_action("manage_operators", "manage operators"):
            return
        if self.selected_operator_id is None:
            messagebox.showerror("No operator selected", "Select an operator first.")
            return
        confirmed = messagebox.askyesno(
            "Clear operator PIN?",
            "Clear this operator PIN? The operator will no longer be able to verify by PIN.",
            icon="warning",
        )
        if not confirmed:
            return
        try:
            clear_operator_pin(
                self.conn,
                self.selected_operator_id,
                operator=self.app.current_operator_audit_label(),
            )
        except ValueError as exc:
            messagebox.showerror("PIN clear failed", str(exc))
            return
        self.refresh_operators()
        self.refresh_audit_log()
        self.app.verified_operator_id = None
        self.app.update_operator_status()
        messagebox.showinfo("PIN cleared", "Operator PIN cleared.")

    def on_material_select(self, _event: tk.Event) -> None:
        selected = self.material_tree.selection()
        if not selected:
            return
        self.selected_material_id = int(selected[0])
        material = next(
            mat
            for mat in list_materials(self.conn, active_only=False)
            if mat.id == self.selected_material_id
        )
        self.material_name.set(material.display_name)
        self.material_category.set(material.category)
        self.material_group.set(material.report_grouping)
        self.material_crv.set(material.crv_eligible)
        self.material_unit.set(material.unit_type)
        self.material_active.set(material.active)
        self.material_sort.set(str(material.sort_order))
        self.material_notes.set(material.notes)

    def clear_material_form(self) -> None:
        self.selected_material_id = None
        self.material_tree.selection_remove(self.material_tree.selection())
        self.material_name.set("")
        self.material_category.set("")
        self.material_group.set("")
        self.material_crv.set(False)
        self.material_unit.set("weight")
        self.material_active.set(True)
        self.material_sort.set("0")
        self.material_notes.set("")

    def save_material(self) -> None:
        if not self.app.require_admin_action("manage_materials", "manage materials"):
            return
        try:
            sort_order = int(self.material_sort.get() or "0")
            if self.selected_material_id is None:
                create_material_type(
                    self.conn,
                    display_name=self.material_name.get(),
                    category=self.material_category.get(),
                    report_grouping=self.material_group.get(),
                    crv_eligible=self.material_crv.get(),
                    unit_type=self.material_unit.get(),
                    active=self.material_active.get(),
                    sort_order=sort_order,
                    notes=self.material_notes.get(),
                    operator=self.app.current_operator_audit_label(),
                )
            else:
                update_material_type(
                    self.conn,
                    self.selected_material_id,
                    display_name=self.material_name.get(),
                    category=self.material_category.get(),
                    report_grouping=self.material_group.get(),
                    crv_eligible=self.material_crv.get(),
                    unit_type=self.material_unit.get(),
                    active=self.material_active.get(),
                    sort_order=sort_order,
                    notes=self.material_notes.get(),
                    operator=self.app.current_operator_audit_label(),
                )
        except ValueError as exc:
            messagebox.showerror("Material validation", str(exc))
            return
        self.refresh_materials()
        self.refresh_rates()

    def toggle_material_active(self) -> None:
        if not self.app.require_admin_action("manage_materials", "manage materials"):
            return
        if self.selected_material_id is None:
            messagebox.showerror("No material selected", "Select a material first.")
            return
        set_material_active(
            self.conn,
            self.selected_material_id,
            not self.material_active.get(),
            operator=self.app.current_operator_audit_label(),
        )
        self.refresh_materials()
        self.refresh_audit_log()

    def on_rate_select(self, _event: tk.Event) -> None:
        selected = self.rate_tree.selection()
        if not selected:
            return
        self.selected_rate_id = int(selected[0])
        row = next(row for row in list_rates(self.conn) if int(row["id"]) == self.selected_rate_id)
        label = f"{row['material_display_name']} ({row['unit_type']})"
        self.rate_material.set(label)
        self.rate_amount.set(format_cents(int(row["rate_cents_per_unit"])).replace("$", ""))
        self.rate_start.set(row["effective_from"])
        self.rate_end.set(row["effective_to"] or "")
        self.rate_active.set(bool(row["active"]))
        self.rate_notes.set(row["notes"])

    def clear_rate_form(self) -> None:
        self.selected_rate_id = None
        self.rate_tree.selection_remove(self.rate_tree.selection())
        if self.material_rate_labels:
            self.rate_material.set(next(iter(self.material_rate_labels)))
        self.rate_amount.set("")
        self.rate_start.set(date.today().isoformat())
        self.rate_end.set("")
        self.rate_active.set(True)
        self.rate_replace.set(True)
        self.rate_notes.set("")

    def save_new_rate(self) -> None:
        if not self.app.require_admin_action("manage_rates", "manage rates"):
            return
        material = self.material_rate_labels.get(self.rate_material.get())
        if material is None:
            messagebox.showerror("Rate validation", "Select a material.")
            return
        try:
            rate_id = add_rate(
                self.conn,
                material_type_id=material.id,
                rate_cents_per_unit=dollars_to_cents(self.rate_amount.get()),
                effective_from=self.rate_start.get(),
                effective_to=self.rate_end.get() or None,
                active=self.rate_active.get(),
                notes=self.rate_notes.get(),
                replace_current=self.rate_replace.get(),
                operator=self.app.current_operator_audit_label(),
            )
        except (InvalidOperation, ValueError) as exc:
            messagebox.showerror("Rate validation", str(exc))
            return
        self.selected_rate_id = rate_id
        self.refresh_rates()
        self.refresh_audit_log()

    def save_rate_metadata(self) -> None:
        if not self.app.require_admin_action("manage_rates", "manage rates"):
            return
        if self.selected_rate_id is None:
            messagebox.showerror("No rate selected", "Select a rate first.")
            return
        try:
            update_rate_metadata(
                self.conn,
                self.selected_rate_id,
                effective_to=self.rate_end.get() or None,
                active=self.rate_active.get(),
                notes=self.rate_notes.get(),
                operator=self.app.current_operator_audit_label(),
            )
        except ValueError as exc:
            messagebox.showerror("Rate validation", str(exc))
            return
        self.refresh_rates()
        self.refresh_audit_log()

    def refresh_audit_log(self) -> None:
        if not hasattr(self, "audit_tree"):
            return
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        entity_type = self.audit_filter.get()
        if entity_type == "all":
            entity_type = None
        self.audit_rows = {
            str(row["id"]): row for row in list_audit_entries(self.conn, entity_type=entity_type)
        }
        for row_id, row in self.audit_rows.items():
            self.audit_tree.insert(
                "",
                "end",
                iid=row_id,
                values=(
                    row["timestamp"],
                    row["operator"],
                    row["action_type"],
                    row["entity_type"],
                    row["entity_id"] or "",
                    row["notes"],
                ),
            )
        self.audit_detail.delete("1.0", "end")

    def on_audit_select(self, _event: tk.Event) -> None:
        selected = self.audit_tree.selection()
        if not selected:
            return
        row = self.audit_rows.get(selected[0])
        if row is None:
            return
        detail = (
            f"Before:\n{row['before_value'] or ''}\n\n"
            f"After:\n{row['after_value'] or ''}"
        )
        self.audit_detail.delete("1.0", "end")
        self.audit_detail.insert("1.0", detail)

    def save_manager_pin_change(self) -> None:
        if not self.app.require_admin_action("change_manager_pin", "change the manager PIN"):
            return
        if self.new_pin.get() != self.confirm_pin.get():
            messagebox.showerror("PIN change failed", "New PIN entries did not match.")
            return
        try:
            change_manager_pin(
                self.conn,
                self.current_pin.get(),
                self.new_pin.get(),
                operator=self.app.current_operator_audit_label(),
            )
        except ValueError as exc:
            messagebox.showerror("PIN change failed", str(exc))
            return
        self.current_pin.set("")
        self.new_pin.set("")
        self.confirm_pin.set("")
        self.refresh_audit_log()
        messagebox.showinfo("PIN changed", "Manager PIN changed.")

    def save_operator_pin_settings(self) -> None:
        if not self.app.require_admin_action(
            "manage_operator_pin_settings", "manage operator PIN settings"
        ):
            return
        operator = self.app.current_operator()
        if self.require_operator_pin_admin.get() and operator is not None and not operator.pin_set:
            messagebox.showerror(
                "Operator PIN required",
                "Set a PIN for the selected manager/admin before requiring PINs for admin actions.",
            )
            return
        set_bool_setting(
            self.conn,
            REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY,
            self.require_operator_pin_transactions.get(),
            operator=self.app.current_operator_audit_label(),
        )
        set_bool_setting(
            self.conn,
            REQUIRE_OPERATOR_PIN_ADMIN_KEY,
            self.require_operator_pin_admin.get(),
            operator=self.app.current_operator_audit_label(),
        )
        self.refresh_audit_log()
        messagebox.showinfo("Settings saved", "Operator PIN settings saved.")

    def export_audit_log(self) -> None:
        if not self.app.require_admin_action("export_audit_log", "export the audit log"):
            return
        entity_type = self.audit_filter.get()
        if entity_type == "all":
            entity_type = None
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Audit Log CSV",
            initialfile=default_audit_export_name(),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_audit_log_csv(
                self.conn,
                path,
                entity_type=entity_type,
                operator=self.app.current_operator_audit_label(),
            )
        except OSError as exc:
            messagebox.showerror("Audit export failed", str(exc))
            return
        self.refresh_audit_log()
        messagebox.showinfo("Audit export complete", f"Exported {path}")

    def create_backup(self) -> None:
        if not self.app.require_admin_action("create_backup", "create a database backup"):
            return
        db_path = get_connection_db_path(self.conn)
        initial_dir = db_path.parent if db_path is not None else Path("data")
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Create Database Backup",
            initialdir=str(initial_dir),
            initialfile=default_backup_name(),
            defaultextension=".sqlite3",
            filetypes=[("SQLite databases", "*.sqlite3"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            create_database_backup(
                self.conn,
                path,
                operator=self.app.current_operator_audit_label(),
            )
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            messagebox.showerror("Backup failed", str(exc))
            return
        self.refresh_audit_log()
        messagebox.showinfo("Backup complete", f"Backup created:\n{path}")

    def restore_from_backup(self) -> None:
        if not self.app.require_admin_action("restore_backup", "restore the database"):
            return
        restore_path = filedialog.askopenfilename(
            parent=self,
            title="Choose Backup To Restore",
            filetypes=[("SQLite databases", "*.sqlite3"), ("All files", "*.*")],
        )
        if not restore_path:
            return
        confirmed = messagebox.askyesno(
            "Restore database?",
            "Restore will replace the current local database. A pre-restore backup "
            "will be created automatically. Continue?",
            icon="warning",
        )
        if not confirmed:
            return
        pin = simpledialog.askstring(
            "Confirm Manager PIN",
            "Enter manager PIN again to restore:",
            show="*",
            parent=self,
        )
        if pin is None:
            return
        if not verify_manager_pin(self.conn, pin):
            messagebox.showerror("Restore denied", "Incorrect manager PIN.")
            return
        db_path = get_connection_db_path(self.conn)
        backup_dir = (db_path.parent if db_path is not None else Path("data")) / "backups"
        pre_restore_path = backup_dir / default_pre_restore_backup_name()
        try:
            restore_database_from_backup(
                self.conn,
                restore_path,
                pre_restore_path,
                operator=self.app.current_operator_audit_label(),
            )
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            self.refresh_audit_log()
            messagebox.showerror("Restore failed", str(exc))
            return
        self.refresh_materials()
        self.refresh_rates()
        self.refresh_audit_log()
        messagebox.showinfo(
            "Restore complete",
            "Database restored. Restart the app before regular operation.\n\n"
            f"Pre-restore backup:\n{pre_restore_path}",
        )
