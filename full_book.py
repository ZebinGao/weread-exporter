"""
整本抓取脚本（playwright connect_over_cdp + 新 cookie + 修改版 hook.js）

用法：
    python full_book.py <书籍ID>

示例：
    python full_book.py 35042012a43425f456b6c44514244524344446b36637936634ed71

说明：
  - 首次运行自动弹出浏览器扫码登录，cookie 存 cache/cookie.txt
  - hook.js 的 clearRect 不重置 markdown，让文字跨页持续累积
  - 章节边界：翻页直到 URL 变化（进入下一章），取变化前的 md
  - 断点续传：每章 md 存 output/chapters/N.md，重跑自动跳过已抓章节
"""
import argparse, atexit, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from playwright.sync_api import sync_playwright
from weread_exporter import utils

OUT_DIR = "output"
CH_DIR = os.path.join(OUT_DIR, "chapters")
HERE = os.path.dirname(os.path.abspath(__file__))


def find_chrome() -> str:
    """跨平台查找 Chrome：先 PATH，再常见安装位置。"""
    for name in ("chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    candidates = []
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise SystemExit("未找到 Chrome，请将其加入 PATH 或安装到默认位置。")


def kill_tree(proc) -> None:
    """只结束本脚本启动的 Chrome 进程树，不影响用户其它 Chrome 窗口。"""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
    except Exception:
        pass


def ensure_cookie(context) -> dict:
    """检查 cache/cookie.txt；不存在则弹出浏览器扫码登录获取。"""
    if os.path.isfile("cache/cookie.txt"):
        return json.load(open("cache/cookie.txt"))
    print("未找到 cache/cookie.txt，请在弹出的浏览器窗口扫码登录微信读书...", flush=True)
    login_page = context.new_page()
    login_page.goto("https://weread.qq.com/", wait_until="domcontentloaded", timeout=60000)
    for _ in range(72):  # 最多 6 分钟
        if any(c["name"] == "wr_skey" for c in context.cookies()):
            ck = {c["name"]: c["value"] for c in context.cookies()}
            os.makedirs("cache", exist_ok=True)
            with open("cache/cookie.txt", "w") as f:
                json.dump(ck, f)
            print("登录成功，cookie 已保存到 cache/cookie.txt", flush=True)
            login_page.close()
            return ck
        time.sleep(5)
    raise SystemExit("登录超时（6 分钟内未检测到扫码）")


def get_meta(page, encode_id: str):
    page.goto(f"https://weread.qq.com/web/reader/{encode_id}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    data = page.evaluate("(()=>{try{return JSON.parse(JSON.stringify(window.__INITIAL_STATE__))}catch(e){return null}})()")
    if not data:
        raise RuntimeError("无法读取书籍目录（__INITIAL_STATE__）")
    return data['reader']['bookInfo'], data['reader']['chapterInfos']


def main() -> None:
    parser = argparse.ArgumentParser(description="导出微信读书整本为 epub")
    parser.add_argument("book", help='书籍 ID（encodeId）：阅读页 URL /web/reader/<book> 中间那串')
    parser.add_argument("--profile", help="Chrome 用户数据目录（默认用临时目录）")
    parser.add_argument("--port", type=int, default=9222, help="Chrome 调试端口（默认 9222）")
    args = parser.parse_args()

    chrome = find_chrome()
    profile = args.profile or tempfile.mkdtemp(prefix="weread_chrome_")
    encode_id = args.book
    port = args.port

    hook_js = open(os.path.join(HERE, "weread_exporter", "hook.js"), encoding="utf-8").read()
    hook_js = hook_js.replace('this.data.markdown = "";', '// keep md accumulating across pages')
    hook_js += "\n;\nwindow.canvasContextHandler = canvasContextHandler;"

    os.makedirs(CH_DIR, exist_ok=True)

    # 启动 Chrome（手动启动 + 调试端口；不走 playwright launch，保持 navigator.webdriver=false）
    proc = subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run", "about:blank"])
    atexit.register(lambda: kill_tree(proc))
    endpoint = f"http://localhost:{port}"
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{endpoint}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise SystemExit(f"Chrome 调试端口 {port} 未就绪（被占用？可加 --port 换一个）")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        context.add_init_script(hook_js)
        ck = ensure_cookie(context)
        context.add_cookies([{"name": k, "value": v, "url": "https://weread.qq.com", "secure": True} for k, v in ck.items()])
        page = context.new_page()
        book_info, chapters = get_meta(page, encode_id)
        print(f"BOOK: {book_info.get('title')} | {len(chapters)} chapters", flush=True)

        for idx, ch in enumerate(chapters):
            uid = ch['chapterUid']
            title = ch.get('title') or f"第{idx+1}章"
            md_file = os.path.join(CH_DIR, f"{idx+1:03d}.md")
            if os.path.isfile(md_file) and os.path.getsize(md_file) > 100:
                print(f"[{idx+1}/{len(chapters)}] {title}: cached", flush=True)
                continue
            chapter_url = f"https://weread.qq.com/web/reader/{encode_id}k{utils.wr_hash(str(uid))}"
            try:
                page.evaluate("window.canvasContextHandler.data.markdown = ''")
            except Exception:
                pass
            page.goto(chapter_url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(30):
                try:
                    if page.evaluate("!!(window.canvasContextHandler && window.canvasContextHandler.data && window.canvasContextHandler.data.complete)"):
                        break
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            initial_url = page.url
            prev_md = ""
            for _ in range(80):
                try:
                    cur_md = page.evaluate("window.canvasContextHandler.data.markdown") or ""
                except Exception:
                    cur_md = prev_md
                if page.url != initial_url:
                    break
                prev_md = cur_md
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(3500)
            md_clean = prev_md.replace("\u200b", "")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(md_clean)
            print(f"[{idx+1}/{len(chapters)}] {title}: {len(md_clean)} chars", flush=True)
        browser.close()

    # 生成 epub
    import markdown as md_lib
    from ebooklib import epub
    title = book_info.get('title') or 'weread_book'
    safe_title = "".join(c for c in title if c not in '\\/:*?"<>|') or "book"
    book = epub.EpubBook()
    book.set_identifier("weread-" + safe_title)
    book.set_title(title)
    book.set_language("zh-CN")
    book.add_author(book_info.get('author') or "未知")
    spine = ["nav"]; toc = []
    files = sorted(os.listdir(CH_DIR))
    for i, fn in enumerate(files):
        t = f"第{i+1}章"
        c = open(os.path.join(CH_DIR, fn), encoding="utf-8").read()
        fname = f"chap_{i+1:04d}.xhtml"
        chap = epub.EpubHtml(title=t, file_name=fname, lang="hr")
        chap.content = md_lib.markdown(c, extensions=["fenced_code", "attr_list"])
        book.add_item(chap); spine.append(chap)
        toc.append(epub.Link(fname, t, str(i + 1)))
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    out = os.path.join(OUT_DIR, f"{safe_title}.epub")
    epub.write_epub(out, book, {})
    print(f"=== EPUB saved: {out} ===", flush=True)


if __name__ == "__main__":
    main()
