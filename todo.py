import sys
import os


def _ensure_modern_tk():
    """macOS ships a deprecated system Tk 8.5 that can't render custom widget
    colors, leaving text/inputs invisible. If we're on it, transparently
    re-exec under a Python that has Tk >= 8.6 when one is available."""
    if os.environ.get("TODO_TK_RELAUNCHED") or sys.platform != "darwin":
        return
    import tkinter
    if tkinter.TkVersion >= 8.6:
        return
    import subprocess
    candidates = [
        "/opt/homebrew/bin/python3.13", "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.13", "/usr/local/bin/python3.12",
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
    ]
    here = os.path.realpath(sys.executable)
    for py in candidates:
        if not os.path.exists(py) or os.path.realpath(py) == here:
            continue
        try:
            ver = subprocess.check_output(
                [py, "-c", "import tkinter; print(tkinter.TkVersion)"],
                stderr=subprocess.DEVNULL, text=True).strip()
        except Exception:
            continue
        if ver and float(ver) >= 8.6:
            print(f"[todo] system Tk {tkinter.TkVersion} can't render colors on "
                  f"macOS; relaunching with {py}", file=sys.stderr)
            os.execve(py, [py] + sys.argv, dict(os.environ, TODO_TK_RELAUNCHED="1"))
    print(f"[todo] WARNING: running on macOS system Tk {tkinter.TkVersion}; text "
          "and colors will not render. Install a modern Tk, e.g.:\n"
          "         brew install python-tk@3.13\n"
          "       then run with that interpreter.", file=sys.stderr)


_ensure_modern_tk()

import tkinter as tk
from tkinter import messagebox
import json
import threading

# ── Supabase config ────────────────────────────────────────────────────────────
# Fill in your project URL and anon key from:
#   supabase.com → your project → Settings → API
SUPABASE_URL = "https://etodugosrtksfkngcgsa.supabase.co"
SUPABASE_KEY = "sb_publishable_bUkL7biqSyB0FlBdpA0nmw_vRnlC-DI"

CACHE_FILE = os.path.join(os.path.dirname(__file__), "todos_cache.json")

try:
    from supabase import create_client
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    _SUPABASE_READY = "placeholder" not in SUPABASE_URL
except Exception as _e:
    _sb = None
    _SUPABASE_READY = False
    print(f"[todo] Supabase unavailable: {_e}", file=sys.stderr)

# ── Colors ─────────────────────────────────────────────────────────────────────
BG = "#1e1e2e"
CARD = "#2a2a3e"
ACCENT = "#7c6af7"
TEXT = "#e0e0f0"
SUBTEXT = "#888aaa"
DONE_TEXT = "#555570"
RED = "#e05c6a"
WHITE = "#ffffff"
ENTRY_BG = "#ffffff"
ENTRY_FG = "#111111"


# ── Persistence ────────────────────────────────────────────────────────────────

def _write_cache(todos):
    with open(CACHE_FILE, "w") as f:
        json.dump(todos, f, indent=2, default=str)


def _read_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return []


def load_todos():
    if not _SUPABASE_READY:
        return _read_cache()
    try:
        res = _sb.table("todos").select("*").order("created_at").execute()
        todos = res.data
        _write_cache(todos)
        return todos
    except Exception as e:
        print(f"[todo] load failed, using cache: {e}", file=sys.stderr)
        return _read_cache()


def save_todo_add(text):
    res = _sb.table("todos").insert({"text": text, "done": False}).execute()
    return res.data[0]


def save_todo_update(todo_id, fields):
    _sb.table("todos").update(fields).eq("id", todo_id).execute()


def save_todo_delete(todo_id):
    _sb.table("todos").delete().eq("id", todo_id).execute()


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _shade(hex_color, factor):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (min(255, int(c * factor)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class ColorButton(tk.Label):
    """Clickable button drawn as a Label so macOS honors bg/fg colors."""

    def __init__(self, parent, text, command, bg, fg=WHITE,
                 font=("Helvetica Neue", 11, "bold"), padx=16, pady=6):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, cursor="hand2")
        self._bg = bg
        self._hover = _shade(bg, 1.18)
        self._command = command
        self.bind("<Button-1>", lambda e: self._command())
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))


# ── Main app ───────────────────────────────────────────────────────────────────

class TodoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Todo App")
        self.geometry("500x580")
        self.minsize(400, 400)
        self.configure(bg=BG)

        self.todos = load_todos()
        self.filter_var = tk.StringVar(value="all")
        self._build_ui()
        self._refresh_list()

        if not _SUPABASE_READY:
            self._show_banner("Supabase not configured — running offline. "
                              "Set SUPABASE_URL and SUPABASE_KEY in todo.py.")

    def _show_banner(self, msg):
        banner = tk.Label(self, text=msg, font=("Helvetica Neue", 9),
                          bg="#3a2a1e", fg="#ffbb55", pady=6, padx=12,
                          wraplength=460, justify="left")
        banner.pack(fill="x", before=self.winfo_children()[0])

    def _build_ui(self):
        tk.Label(self, text="My Todo List", font=("Helvetica Neue", 18, "bold"),
                 bg=BG, fg=ACCENT, pady=16).pack(fill="x")

        input_frame = tk.Frame(self, bg=BG, padx=16, pady=4)
        input_frame.pack(fill="x")

        entry_wrap = tk.Frame(input_frame, bg=ENTRY_BG, highlightthickness=2,
                              highlightbackground=ACCENT, highlightcolor=ACCENT)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.entry = tk.Entry(entry_wrap, font=("Helvetica Neue", 12),
                              bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                              relief="flat", bd=6)
        self.entry.pack(fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._add_todo())
        self.entry.focus_set()

        ColorButton(input_frame, "Add", self._add_todo, bg=ACCENT).pack(side="left")

        self.refresh_btn = tk.Label(input_frame, text="⟳", font=("Helvetica Neue", 18),
                                    bg=BG, fg=SUBTEXT, cursor="hand2", padx=8)
        self.refresh_btn.pack(side="left")
        self.refresh_btn.bind("<Button-1>", lambda e: self._refresh_from_cloud())

        tk.Label(self, text="Type a task above and press Enter or click Add",
                 font=("Helvetica Neue", 10), bg=BG, fg=SUBTEXT).pack(pady=(2, 6))

        filter_frame = tk.Frame(self, bg=BG, padx=16, pady=4)
        filter_frame.pack(fill="x")

        self._filter_tabs = {}
        for text, val in [("All", "all"), ("Active", "active"), ("Done", "done")]:
            tab = tk.Label(filter_frame, text=text,
                           font=("Helvetica Neue", 10, "bold"), cursor="hand2",
                           padx=14, pady=5)
            tab.pack(side="left", padx=2)
            tab.bind("<Button-1>", lambda e, v=val: self._set_filter(v))
            self._filter_tabs[val] = tab
        self._update_filter_tabs()

        tk.Frame(self, bg=SUBTEXT, height=1).pack(fill="x", padx=16, pady=4)

        list_outer = tk.Frame(self, bg=BG, padx=16)
        list_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_outer, bg=BG, bd=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.items_frame = tk.Frame(self.canvas, bg=BG)
        self._canvas_win = self.canvas.create_window((0, 0), window=self.items_frame, anchor="nw")

        self.items_frame.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self._canvas_win, width=e.width))

        tk.Frame(self, bg=SUBTEXT, height=1).pack(fill="x", padx=16, pady=4)
        footer = tk.Frame(self, bg=BG, pady=6)
        footer.pack(fill="x")

        self.status_label = tk.Label(footer, text="", font=("Helvetica Neue", 10),
                                     bg=BG, fg=SUBTEXT)
        self.status_label.pack(side="left", padx=16)

        ColorButton(footer, "Clear Completed", self._clear_completed, bg=RED,
                    font=("Helvetica Neue", 10), padx=10, pady=4).pack(side="right", padx=16)

    def _refresh_from_cloud(self):
        self.refresh_btn.config(fg=ACCENT)
        def _do():
            self.todos = load_todos()
            self.after(0, lambda: (
                self._refresh_list(),
                self.refresh_btn.config(fg=SUBTEXT)
            ))
        threading.Thread(target=_do, daemon=True).start()

    def _set_filter(self, val):
        self.filter_var.set(val)
        self._update_filter_tabs()
        self._refresh_list()

    def _update_filter_tabs(self):
        active = self.filter_var.get()
        for val, tab in self._filter_tabs.items():
            if val == active:
                tab.config(bg=ACCENT, fg=WHITE)
            else:
                tab.config(bg=BG, fg=SUBTEXT)

    def _add_todo(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        if not _SUPABASE_READY:
            self.todos.append({"text": text, "done": False})
            self._refresh_list()
            return
        def _do():
            todo = save_todo_add(text)
            self.todos.append(todo)
            self.after(0, self._refresh_list)
        threading.Thread(target=_do, daemon=True).start()

    def _toggle_todo(self, index):
        todo = self.todos[index]
        new_done = not todo["done"]
        todo["done"] = new_done
        self._refresh_list()
        if _SUPABASE_READY:
            threading.Thread(target=save_todo_update,
                             args=(todo["id"], {"done": new_done}),
                             daemon=True).start()

    def _delete_todo(self, index):
        todo = self.todos.pop(index)
        self._refresh_list()
        if _SUPABASE_READY:
            threading.Thread(target=save_todo_delete,
                             args=(todo["id"],),
                             daemon=True).start()

    def _clear_completed(self):
        completed = [t for t in self.todos if t["done"]]
        if not completed:
            return
        if messagebox.askyesno("Clear Completed", "Remove all completed tasks?"):
            self.todos = [t for t in self.todos if not t["done"]]
            self._refresh_list()
            if _SUPABASE_READY:
                def _do():
                    for t in completed:
                        save_todo_delete(t["id"])
                threading.Thread(target=_do, daemon=True).start()

    def _refresh_list(self):
        for w in self.items_frame.winfo_children():
            w.destroy()

        filt = self.filter_var.get()
        visible = [(i, t) for i, t in enumerate(self.todos)
                   if filt == "all"
                   or (filt == "done" and t["done"])
                   or (filt == "active" and not t["done"])]

        if not visible:
            tk.Label(self.items_frame, text="No tasks here yet.",
                     font=("Helvetica Neue", 11), bg=BG, fg=SUBTEXT,
                     pady=20).pack()

        for _i, (orig_index, todo) in enumerate(visible):
            row = tk.Frame(self.items_frame, bg=CARD, pady=8, padx=10)
            row.pack(fill="x", pady=3)

            box_glyph = "☑" if todo["done"] else "☐"
            box_fg = ACCENT if todo["done"] else SUBTEXT
            checkbox = tk.Label(row, text=box_glyph, font=("Helvetica Neue", 15),
                                bg=CARD, fg=box_fg, cursor="hand2", padx=2)
            checkbox.pack(side="left")
            checkbox.bind("<Button-1>", lambda e, idx=orig_index: self._toggle_todo(idx))

            fg = DONE_TEXT if todo["done"] else TEXT
            font_style = ("Helvetica Neue", 11, "overstrike") if todo["done"] else ("Helvetica Neue", 11)
            tk.Label(row, text=todo["text"], font=font_style,
                     bg=CARD, fg=fg, anchor="w").pack(side="left", fill="x", expand=True, padx=(6, 0))

            delete = tk.Label(row, text="✕", font=("Helvetica Neue", 12, "bold"),
                              bg=CARD, fg=RED, cursor="hand2", padx=4)
            delete.pack(side="right")
            delete.bind("<Button-1>", lambda e, idx=orig_index: self._delete_todo(idx))

        done_count = sum(1 for t in self.todos if t["done"])
        total = len(self.todos)
        self.status_label.config(
            text=f"{total - done_count} remaining · {done_count} done · {total} total")


if __name__ == "__main__":
    app = TodoApp()
    app.mainloop()
