"""从 output/chapters/*.md 重新生成 epub 或 txt（用于 fix_paragraphs 处理后合并）。

用法：
    python make_epub.py                 # 书名从 newbook.log 读
    python make_epub.py "<书名>"        # 手动指定书名
    python make_epub.py "<书名>" --txt  # 输出 txt 而非 epub
"""
import os, re, sys, argparse
import markdown
from ebooklib import epub

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CH_DIR = os.path.join(PROJECT_ROOT, "output", "chapters")
OUT_DIR = os.path.join(PROJECT_ROOT, "output")
NEWBOOK_LOG = os.path.join(PROJECT_ROOT, "newbook.log")


def read_title(cli_title):
    if cli_title:
        return cli_title
    try:
        log = ""
        for enc in ("utf-8", "gbk"):
            try:
                log = open(NEWBOOK_LOG, encoding=enc).read()
                break
            except UnicodeDecodeError:
                pass
        m = re.search(r"^BOOK: (.+?) \|", log, re.M)
        return m.group(1) if m else "weread_book"
    except Exception:
        return "weread_book"


def list_chapters():
    files = sorted(f for f in os.listdir(CH_DIR) if f.endswith(".md"))
    return [(f, open(os.path.join(CH_DIR, f), encoding="utf-8").read()) for f in files]


def make_epub(title, chapters):
    safe = "".join(c for c in title if c not in '\\/:*?"<>|') or "book"
    book = epub.EpubBook()
    book.set_identifier("weread-" + safe)
    book.set_title(title)
    book.set_language("zh-CN")
    book.add_author("未知")
    spine = ["nav"]; toc = []
    for i, (_, c) in enumerate(chapters):
        fname = f"chap_{i+1:04d}.xhtml"
        chap = epub.EpubHtml(title=f"第{i+1}章", file_name=fname, lang="hr")
        chap.content = markdown.markdown(c, extensions=["fenced_code", "attr_list"])
        book.add_item(chap); spine.append(chap)
        toc.append(epub.Link(fname, f"第{i+1}章", str(i + 1)))
    book.toc = toc
    book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())
    book.spine = spine
    out = os.path.join(OUT_DIR, f"{safe}.epub")
    # epub3_pages=False：关闭 ebooklib 的 nav 分页（它会逐章用 lxml 解析 HTML，遇空章节会抛 "Document is empty"）
    epub.write_epub(out, book, {"epub3_pages": False})
    return out


def make_txt(title, chapters):
    safe = "".join(c for c in title if c not in '\\/:*?"<>|') or "book"
    out = os.path.join(OUT_DIR, f"{safe}.txt")
    parts = [title, ""]
    for i, (_, c) in enumerate(chapters):
        parts.append(f"第{i+1}章")
        parts.append("")
        parts.append(c.strip())
        parts.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out


def main():
    ap = argparse.ArgumentParser(description="从 chapters/*.md 生成 epub 或 txt")
    ap.add_argument("title", nargs="?", help="书名（默认从 newbook.log 读取）")
    ap.add_argument("--txt", action="store_true", help="输出 txt 而非 epub")
    args = ap.parse_args()

    title = read_title(args.title)
    chapters = list_chapters()
    if not chapters:
        sys.exit(f"未找到章节文件：{CH_DIR}/*.md")

    if args.txt:
        out = make_txt(title, chapters)
        print(f"TXT saved: {out} ({len(chapters)} chapters)")
    else:
        out = make_epub(title, chapters)
        print(f"EPUB saved: {out} ({len(chapters)} chapters)")


if __name__ == "__main__":
    main()
