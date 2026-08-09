"""从 output/chapters/*.md 重新生成 epub（用于 fix_paragraphs 处理后合并）。
用法：python make_epub.py <书名>
"""
import os, sys, markdown
from ebooklib import epub

CH_DIR = "output/chapters"
OUT_DIR = "output"


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else None
    if not title:
        import re
        try:
            log = ""
            for enc in ("utf-8", "gbk"):
                try:
                    log = open("newbook.log", encoding=enc).read(); break
                except UnicodeDecodeError:
                    pass
            m = re.search(r"^BOOK: (.+?) \|", log, re.M)
            title = m.group(1) if m else "weread_book"
        except Exception:
            title = "weread_book"
    safe = "".join(c for c in title if c not in '\\/:*?"<>|') or "book"
    book = epub.EpubBook()
    book.set_identifier("weread-" + safe)
    book.set_title(title)
    book.set_language("zh-CN")
    book.add_author("未知")
    spine = ["nav"]; toc = []
    files = sorted(f for f in os.listdir(CH_DIR) if f.endswith(".md"))
    for i, fn in enumerate(files):
        c = open(os.path.join(CH_DIR, fn), encoding="utf-8").read()
        fname = f"chap_{i+1:04d}.xhtml"
        chap = epub.EpubHtml(title=f"第{i+1}章", file_name=fname, lang="hr")
        chap.content = markdown.markdown(c, extensions=["fenced_code", "attr_list"])
        book.add_item(chap); spine.append(chap)
        toc.append(epub.Link(fname, f"第{i+1}章", str(i + 1)))
    book.toc = toc
    book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())
    book.spine = spine
    out = os.path.join(OUT_DIR, f"{safe}.epub")
    epub.write_epub(out, book, {})
    print(f"EPUB saved: {out} ({len(files)} chapters)")


if __name__ == "__main__":
    main()
