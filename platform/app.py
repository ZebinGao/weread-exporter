"""简易桌面 GUI：登录 → 输入 id → 自动校验+抓取+进度 → 选导出 EPUB/TXT。

用法：python platform/app.py

依赖：tkinter（Python 标准库，Windows 自带）；底层抓取/打包由同目录的
full_book.py / fix_paragraphs.py / make_epub.py 完成（子进程调用）。
"""
import os, re, sys, queue, threading, subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_DIR = HERE
PROJECT_ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")
CH_DIR = os.path.join(PROJECT_ROOT, "output", "chapters")
COOKIE_FILE = os.path.join(CACHE_DIR, "cookie.txt")

FULL_BOOK = os.path.join(PLATFORM_DIR, "full_book.py")
FIX_PARAS = os.path.join(PLATFORM_DIR, "fix_paragraphs.py")
MAKE_EPUB = os.path.join(PLATFORM_DIR, "make_epub.py")

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")   # 子进程统一 UTF-8 输出


def parse_id(text: str) -> str:
    """从完整 URL 或纯 id 中取 reader/ 后那串。"""
    text = text.strip()
    m = re.search(r"/reader/([A-Za-z0-9]+)", text)
    return m.group(1) if m else text


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("微信读书导出（简易版）")
        self.root.geometry("760x620")

        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.running = False
        self.phase = ""                 # login / scrape / export
        self.book_title = None
        self.cookie_invalid = False
        self.saved_paths = []
        self.n_chapters = 0

        self._build()
        self.root.after(100, self._poll)

    # ---------------- UI ----------------
    def _build(self):
        # 第一行：登录
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")
        self.login_btn = ttk.Button(top, text="① 登录（扫码）", command=self.on_login)
        self.login_btn.pack(side="left")
        self.login_var = tk.StringVar(value=self._cookie_status())
        ttk.Label(top, textvariable=self.login_var, foreground="#444").pack(side="left", padx=10)

        # 第二行：输入 id + 开始抓取
        row = ttk.Frame(self.root, padding=(10, 0))
        row.pack(fill="x")
        ttk.Label(row, text="书籍 URL 或 ID：").pack(side="left")
        self.id_entry = ttk.Entry(row)
        self.id_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.id_entry.bind("<Return>", lambda e: self.on_scrape())
        self.scrape_btn = ttk.Button(row, text="② 开始抓取", command=self.on_scrape)
        self.scrape_btn.pack(side="left")

        # 进度条 + 状态
        prog = ttk.Frame(self.root, padding=(10, 8))
        prog.pack(fill="x")
        self.bar = ttk.Progressbar(prog, mode="determinate")
        self.bar.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(prog, textvariable=self.status_var, width=22).pack(side="left", padx=10)

        # 日志文本
        logf = ttk.Frame(self.root)
        logf.pack(fill="both", expand=True, padx=10)
        self.log = scrolledtext.ScrolledText(logf, height=18, wrap="word", state="disabled",
                                             font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        # 导出按钮
        bot = ttk.Frame(self.root, padding=(10, 8))
        bot.pack(fill="x")
        self.epub_btn = ttk.Button(bot, text="③ 导出 EPUB", state="disabled", command=lambda: self.on_export("epub"))
        self.epub_btn.pack(side="left")
        self.txt_btn = ttk.Button(bot, text="③ 导出 TXT", state="disabled", command=lambda: self.on_export("txt"))
        self.txt_btn.pack(side="left", padx=8)
        ttk.Label(bot, text="（抓取完成后启用）", foreground="#888").pack(side="left")

    def _cookie_status(self) -> str:
        return "已登录（cookie 存在）" if os.path.isfile(COOKIE_FILE) else "未登录"

    def log_line(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_running(self, running: bool):
        self.running = running
        state = "disabled" if running else "normal"
        for b in (self.login_btn, self.scrape_btn):
            b.configure(state=state)
        # 导出按钮仅在抓取成功后才可点
        export_state = "disabled" if (running or self.book_title is None) else "normal"
        self.epub_btn.configure(state=export_state)
        self.txt_btn.configure(state=export_state)

    # ---------------- 动作 ----------------
    def on_login(self):
        if self.running:
            return
        self._run([[sys.executable, FULL_BOOK, "--login-only"]], "login")

    def on_scrape(self):
        if self.running:
            return
        if not os.path.isfile(COOKIE_FILE):
            messagebox.showwarning("未登录", "请先点「① 登录」扫码后再抓取。", parent=self.root)
            return
        encode_id = parse_id(self.id_entry.get())
        if not encode_id:
            messagebox.showwarning("缺少 ID", "请粘贴阅读页 URL 或书籍 ID。", parent=self.root)
            return
        # 换书安全：旧章节记录是否清空
        if os.path.isdir(CH_DIR):
            olds = os.listdir(CH_DIR)
            if olds:
                msg = (f"output/chapters 已有 {len(olds)} 个文件。\n"
                       "是否清空后重新抓取？（选「否」按断点续传，但换书时可能混入上一本内容）")
                if messagebox.askyesno("发现旧记录", msg, parent=self.root):
                    for f in olds:
                        try:
                            os.remove(os.path.join(CH_DIR, f))
                        except OSError:
                            pass
                    self.log_line("已清空 output/chapters/")
        self.book_title = None
        self.bar["value"] = 0
        self._run([[sys.executable, FULL_BOOK, encode_id, "--no-epub"]], "scrape")

    def on_export(self, fmt: str):
        if self.running or self.book_title is None:
            return
        cmds = [[sys.executable, FIX_PARAS]]
        make = [sys.executable, MAKE_EPUB, self.book_title]
        if fmt == "txt":
            make.append("--txt")
        cmds.append(make)
        self._run(cmds, "export")

    # ---------------- 子进程执行 ----------------
    def _run(self, cmds, phase):
        self.set_running(True)
        self.phase = phase
        self.cookie_invalid = False
        self.saved_paths = []
        self.status_var.set({"login": "登录中…", "scrape": "抓取中…", "export": "导出中…"}[phase])
        t = threading.Thread(target=self._worker, args=(cmds,), daemon=True)
        t.start()

    def _worker(self, cmds):
        rc = 0
        try:
            for cmd in cmds:
                self.q.put(("LINE", " ".join(cmd)))
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=ENV,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace",
                                        bufsize=1, creationflags=flags)
                for line in iter(proc.stdout.readline, ""):
                    self.q.put(("LINE", line.rstrip("\n")))
                rc = proc.wait()
                if rc != 0:
                    break
        except Exception as e:
            self.q.put(("LINE", f"[子进程错误] {e}"))
            rc = -1
        self.q.put(("DONE", rc))

    # ---------------- 主线程轮询 ----------------
    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "LINE":
                    self._handle_line(data)
                elif kind == "DONE":
                    self._handle_done(data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle_line(self, line: str):
        self.log_line(line)
        # 登录成功 / cookie 状态
        if "登录成功" in line or "cookie 已保存" in line:
            self.login_var.set("已登录（cookie 已保存）")
        if line.startswith("COOKIE_INVALID"):
            self.cookie_invalid = True
        if line.startswith("BOOK:"):
            m = re.match(r"BOOK:\s*(.+?)\s*\|\s*(\d+)\s*chapters", line)
            if m:
                self.book_title = m.group(1).strip()
                self.n_chapters = int(m.group(2))
                self.bar["maximum"] = max(self.n_chapters, 1)
                self.bar["value"] = 0
                self.status_var.set(f"0 / {self.n_chapters} 章")
        mch = re.match(r"^\[(\d+)/\d+\]", line)         # [x/N] ...
        if mch:
            x = int(mch.group(1))
            self.bar["value"] = x
            self.status_var.set(f"{x} / {self.n_chapters} 章")
        if "saved:" in line:
            self.saved_paths.append(line.split("saved:", 1)[1].strip())

    def _handle_done(self, rc):
        self.set_running(False)
        if self.phase == "login":
            if rc == 0:
                self.login_var.set("已登录（cookie 已保存）")
                self.status_var.set("登录完成")
                self.log_line("登录完成，可粘贴 ID 后点「开始抓取」。")
            else:
                self.login_var.set(self._cookie_status())
                self.status_var.set("登录未完成")
                messagebox.showwarning("登录", "登录未完成（可能超时或未扫码）。", parent=self.root)
        elif self.phase == "scrape":
            if self.cookie_invalid or rc == 2:
                self.status_var.set("cookie 失效")
                messagebox.showwarning("抓取失败",
                                       "当前 cookie 无法抓到正文（可能已被标记失效）。\n请点「① 登录」重新扫码后再试。",
                                       parent=self.root)
            elif rc == 0:
                self.status_var.set("抓取完成")
                self.log_line("抓取完成，可点「导出 EPUB / TXT」。")
                self.epub_btn.configure(state="normal")
                self.txt_btn.configure(state="normal")
            else:
                self.status_var.set("抓取出错")
                messagebox.showerror("抓取失败", f"进程异常退出（code={rc}），请查看日志。", parent=self.root)
        elif self.phase == "export":
            if rc == 0 and self.saved_paths:
                self.status_var.set("导出完成")
                p = self.saved_paths[-1]
                messagebox.showinfo("导出完成", f"已生成：{p}", parent=self.root)
            elif rc == 0:
                self.status_var.set("导出完成")
                messagebox.showinfo("导出完成", "已完成。", parent=self.root)
            else:
                self.status_var.set("导出错")
                messagebox.showerror("导出失败", f"进程异常退出（code={rc}），请查看日志。", parent=self.root)
        self.phase = ""


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
