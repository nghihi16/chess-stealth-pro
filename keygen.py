import ctypes
import os
import sys
import tkinter as tk

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from db.database import create_license_record, get_connection

UI_THEMES = {
    "dark": {
        "bg": "#0b0d12",
        "card": "#131722",
        "elevated": "#1c2230",
        "elevated_hover": "#262e40",
        "border": "#2e3646",
        "focus": "#f59e0b",
        "text": "#f8fafc",
        "subtext": "#cbd5e1",
        "muted": "#94a3b8",
        "amber": "#f59e0b",
        "amber_hover": "#fbbf24",
        "amber_fg": "#09090b",
        "green": "#10b981",
        "green_hover": "#34d399",
        "green_fg": "#07080a",
        "sky": "#38bdf8",
        "sky_hover": "#7dd3fc",
        "sky_fg": "#09090b",
    },
    "light": {
        "bg": "#f1f5f9",
        "card": "#ffffff",
        "elevated": "#f8fafc",
        "elevated_hover": "#e2e8f0",
        "border": "#cbd5e1",
        "focus": "#d97706",
        "text": "#0f172a",
        "subtext": "#334155",
        "muted": "#475569",
        "amber": "#d97706",
        "amber_hover": "#b45309",
        "amber_fg": "#ffffff",
        "green": "#059669",
        "green_hover": "#047857",
        "green_fg": "#ffffff",
        "sky": "#0284c7",
        "sky_hover": "#0369a1",
        "sky_fg": "#ffffff",
    },
}
_CURRENT_THEME = "dark"


def _bind_hover(widget, bg_normal: str, bg_hover: str):
    widget.bind("<Enter>", lambda _: widget.config(bg=bg_hover))
    widget.bind("<Leave>", lambda _: widget.config(bg=bg_normal))


def create_db_key(ltype: str, hwid: str = "") -> str:
    hwid_clean = hwid.strip().upper() if hwid.strip() else None
    with get_connection() as conn:
        rec = create_license_record(
            conn,
            license_type=ltype,
            hwid=hwid_clean,
            activate_immediately=bool(hwid_clean),
        )
        return rec["key"]


def run_gui():
    global _CURRENT_THEME
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("Chess Stealth Pro — Admin License Manager (Supabase Cloud)")
    root.geometry("520x390")
    root.resizable(False, False)
    root.eval("tk::PlaceWindow . center")

    hwid_var = tk.StringVar(value="")
    out_var = tk.StringVar(value="Chọn gói bản quyền cần khởi tạo...")
    status_var = tk.StringVar(
        value="Mọi Key tạo tại đây được lưu trực tiếp lên Supabase Cloud PostgreSQL."
    )

    shell = tk.Frame(root)
    shell.pack(fill="both", expand=True)

    def render_ui():
        for w in shell.winfo_children():
            w.destroy()
        t = UI_THEMES[_CURRENT_THEME]
        root.configure(bg=t["bg"])
        shell.configure(bg=t["bg"], padx=24, pady=16)

        header = tk.Frame(shell, bg=t["bg"])
        header.pack(fill="x", pady=(0, 12))

        brand = tk.Frame(header, bg=t["bg"])
        brand.pack(side="left")
        tk.Label(
            brand,
            text="ADMIN LICENSE MANAGER",
            fg=t["text"],
            bg=t["bg"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="SUPABASE CLOUD  •  ED25519 SIGNATURE",
            fg=t["amber"],
            bg=t["bg"],
            font=("Segoe UI", 7, "bold"),
        ).pack(anchor="w")

        def toggle_theme():
            global _CURRENT_THEME
            _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
            render_ui()

        theme_btn = tk.Button(
            header,
            text="Sáng / Tối",
            command=toggle_theme,
            bg=t["elevated"],
            fg=t["subtext"],
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        )
        theme_btn.pack(side="right")
        _bind_hover(theme_btn, t["elevated"], t["elevated_hover"])

        card = tk.Frame(
            shell,
            bg=t["card"],
            highlightbackground=t["border"],
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        card.pack(fill="x", pady=(0, 12))

        tk.Label(
            card,
            text="Gắn trước HWID (Để trống = Tự động khóa khi khách kích hoạt lần đầu):",
            fg=t["subtext"],
            bg=t["card"],
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        hwid_border = tk.Frame(
            card,
            bg=t["elevated"],
            highlightbackground=t["border"],
            highlightthickness=1,
            padx=2,
            pady=2,
        )
        hwid_border.pack(fill="x", pady=(0, 12))

        hwid_entry = tk.Entry(
            hwid_border,
            textvariable=hwid_var,
            font=("Consolas", 10, "bold"),
            bg=t["elevated"],
            fg=t["text"],
            insertbackground=t["text"],
            relief="flat",
            justify="center",
        )
        hwid_entry.pack(fill="x", ipady=6)
        hwid_entry.bind(
            "<FocusIn>", lambda _: hwid_border.config(highlightbackground=t["focus"])
        )
        hwid_entry.bind(
            "<FocusOut>", lambda _: hwid_border.config(highlightbackground=t["border"])
        )

        tk.Label(
            card,
            text="Mã License Key Vừa Khởi Tạo:",
            fg=t["muted"],
            bg=t["card"],
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        out_entry = tk.Entry(
            card,
            textvariable=out_var,
            font=("Consolas", 12, "bold"),
            bg=t["bg"],
            fg=t["green"],
            readonlybackground=t["bg"],
            relief="flat",
            justify="center",
            state="readonly",
        )
        out_entry.pack(fill="x", ipady=8, pady=(0, 16))

        def gen_and_copy(ltype: str):
            k = create_db_key(ltype, hwid_var.get())
            out_var.set(k)
            root.clipboard_clear()
            root.clipboard_append(k)
            status_var.set(f"Đã tạo Key [{ltype}] lên Supabase và sao chép vào Clipboard!")

        btn_grid = tk.Frame(card, bg=t["card"])
        btn_grid.pack(fill="x")
        for i in range(3):
            btn_grid.columnconfigure(i, weight=1)

        b1 = tk.Button(
            btn_grid,
            text="TẠO KEY 24 GIỜ",
            command=lambda: gen_and_copy("trial_24h"),
            bg=t["amber"],
            fg=t["amber_fg"],
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            pady=10,
        )
        b1.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _bind_hover(b1, t["amber"], t["amber_hover"])

        b2 = tk.Button(
            btn_grid,
            text="TẠO KEY 30 NGÀY",
            command=lambda: gen_and_copy("monthly"),
            bg=t["sky"],
            fg=t["sky_fg"],
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            pady=10,
        )
        b2.grid(row=0, column=1, sticky="ew", padx=4)
        _bind_hover(b2, t["sky"], t["sky_hover"])

        b3 = tk.Button(
            btn_grid,
            text="TẠO KEY LIFETIME",
            command=lambda: gen_and_copy("lifetime"),
            bg=t["green"],
            fg=t["green_fg"],
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            pady=10,
        )
        b3.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        _bind_hover(b3, t["green"], t["green_hover"])

        tk.Label(
            shell,
            textvariable=status_var,
            fg=t["subtext"],
            bg=t["bg"],
            font=("Segoe UI", 8, "bold"),
        ).pack(pady=(4, 0))

    render_ui()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("trial_24h", "monthly", "lifetime"):
        hwid_arg = sys.argv[2] if len(sys.argv) >= 3 else ""
        print(create_db_key(sys.argv[1], hwid_arg))
    else:
        run_gui()
