import sys
import tkinter as tk
from db.database import create_license_record, get_connection
from db.migrate import run_migrations


def create_db_key(ltype: str, hwid: str = "") -> str:
    run_migrations(seed_defaults=True)
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
    run_migrations(seed_defaults=True)
    root = tk.Tk()
    root.title("Chess Stealth Pro - Admin License Manager")
    root.geometry("460x320")
    root.configure(bg="#18181b")
    root.resizable(False, False)
    root.eval("tk::PlaceWindow . center")

    tk.Label(
        root,
        text="ADMIN LICENSE MANAGER (SQLite + Ed25519)",
        fg="#f59e0b",
        bg="#18181b",
        font=("Segoe UI", 12, "bold"),
    ).pack(pady=(16, 4))

    tk.Label(
        root,
        text="Nhập HWID để gắn trước (Để trống = gắn tự động khi khách kích hoạt lần đầu):",
        fg="#a1a1aa",
        bg="#18181b",
        font=("Segoe UI", 8),
    ).pack(pady=(4, 4))

    hwid_entry = tk.Entry(
        root,
        width=38,
        font=("Consolas", 10),
        bg="#27272a",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
        justify="center",
    )
    hwid_entry.pack(pady=4, ipady=5)

    out_var = tk.StringVar(value="Chọn loại Key cần tạo vào Database...")
    out_entry = tk.Entry(
        root,
        textvariable=out_var,
        width=38,
        font=("Consolas", 11, "bold"),
        bg="#09090b",
        fg="#22c55e",
        readonlybackground="#09090b",
        relief="flat",
        justify="center",
        state="readonly",
    )
    out_entry.pack(pady=12, ipady=7)

    def gen_and_copy(ltype: str):
        k = create_db_key(ltype, hwid_entry.get())
        out_var.set(k)
        root.clipboard_clear()
        root.clipboard_append(k)
        status_lbl.config(
            text=f"Đã lưu Key [{ltype}] vào Database và Copy vào Clipboard!",
            fg="#22c55e",
        )

    btn_frame = tk.Frame(root, bg="#18181b")
    btn_frame.pack(pady=6)

    tk.Button(
        btn_frame,
        text="KEY 24 GIỜ",
        command=lambda: gen_and_copy("trial_24h"),
        bg="#f59e0b",
        fg="#18181b",
        font=("Segoe UI", 9, "bold"),
        width=13,
        relief="flat",
        cursor="hand2",
        pady=6,
    ).grid(row=0, column=0, padx=4)

    tk.Button(
        btn_frame,
        text="KEY 30 NGÀY",
        command=lambda: gen_and_copy("monthly"),
        bg="#38bdf8",
        fg="#09090b",
        font=("Segoe UI", 9, "bold"),
        width=13,
        relief="flat",
        cursor="hand2",
        pady=6,
    ).grid(row=0, column=1, padx=4)

    tk.Button(
        btn_frame,
        text="KEY LIFETIME",
        command=lambda: gen_and_copy("lifetime"),
        bg="#22c55e",
        fg="#09090b",
        font=("Segoe UI", 9, "bold"),
        width=13,
        relief="flat",
        cursor="hand2",
        pady=6,
    ).grid(row=0, column=2, padx=4)

    status_lbl = tk.Label(
        root,
        text="Key mẫu có sẵn: FREE-TEST-1DAY | PRO30D-TEST-MONTH | LIFE-VIP-9999",
        fg="#71717a",
        bg="#18181b",
        font=("Segoe UI", 8),
    )
    status_lbl.pack(pady=(12, 0))

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        print("24h Key:", create_db_key("trial_24h"))
        print("30d Key:", create_db_key("monthly"))
        print("Lifetime Key:", create_db_key("lifetime"))
    else:
        run_gui()
