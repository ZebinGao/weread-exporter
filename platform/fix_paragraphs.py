"""
后处理抓取回来的章节 md：合并被屏幕换行截断的段落，同时保留独句成段。

规则（针对 canvas 抓取产生的"每个视觉行都成一段"）：
  - 行末是句末标点（。！？；：）」"'… 等）→ 段落结束
  - 行末非句末标点 且 行长 >= MIN_LEN → 段内被屏幕换行截断，合并到当前段
  - 行末非句末标点 且 行长 <  MIN_LEN → 独句成段，保留为独立段落（不合到上一段）

用法：
    python fix_paragraphs.py                 # 处理 output/chapters/*.bak
    python fix_paragraphs.py a.bak b.bak     # 处理指定文件（输出去掉 .bak）
    python fix_paragraphs.py --min 20 *.bak  # 调独句长度阈值
"""
import os, re, sys, glob, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)   # platform 的父目录 = 仓库根
CH_DIR = os.path.join(PROJECT_ROOT, "output", "chapters")

END_MARKS = "。！？；：）」＂\"'…"
MIN_LEN = 15   # 行长小于此值且行末非句末标点 → 视为独句，独立成段


def fix(text, min_len=MIN_LEN):
    lines = [l.strip() for l in re.split(r"\n\s*\n", text) if l.strip()]
    out = []
    cur = ""
    for l in lines:
        last = l[-1] if l else ""
        is_end = last in END_MARKS
        is_short = (not is_end) and len(l) < min_len
        if is_short:
            # 独句成段：先把当前累积的段落收尾，再让它单独成段
            if cur:
                out.append(cur); cur = ""
            out.append(l)
        else:
            cur = (cur + l) if cur else l
            if is_end:
                out.append(cur); cur = ""
    if cur:
        out.append(cur)
    return "\n\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="合并被屏幕换行截断的段落，保留独句成段")
    ap.add_argument("files", nargs="*", help="待处理文件（默认 output/chapters/*.bak）")
    ap.add_argument("--min", type=int, default=MIN_LEN, help=f"独句长度阈值（默认 {MIN_LEN}）")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(os.path.join(CH_DIR, "*.md")))
    for src in files:
        if src.endswith(".bak"):
            md = src[:-4]
            text = open(src, encoding="utf-8").read()
        else:
            # .md：先备份原始内容到 .bak，再原地修复（这样可反复跑、不丢原始数据）
            md = src
            text = open(md, encoding="utf-8").read()
            open(md + ".bak", "w", encoding="utf-8").write(text)
        before = len([p for p in re.split(r"\n\s*\n", text) if p.strip()])
        fixed = fix(text, args.min)
        after = len([p for p in re.split(r"\n\s*\n", fixed) if p.strip()])
        open(md, "w", encoding="utf-8").write(fixed)
        print(f"{md}: {before} -> {after} 段（原始备份在 {md}.bak）")


if __name__ == "__main__":
    main()
