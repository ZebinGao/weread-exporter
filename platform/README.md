# platform —— 适配新版微信读书的抓取工具

本目录是适配**新版微信读书**的改进版抓取工具，包含命令行脚本与一个简易桌面 GUI。
原项目主程序（`weread_exporter`，基于 pyppeteer）已无法直接导出，原因见下文「兼容性说明」。

## 简易桌面 GUI（推荐）

零命令行记忆，图形界面操作：

```bash
python platform/app.py
```

界面流程：

1. **① 登录（扫码）**：点击后弹出 Chrome，在微信读书主页右上角点「登录」扫码。cookie 自动存到 `cache/cookie.txt`。
2. **② 开始抓取**：在输入框粘贴阅读页 URL（或书籍 ID），点击后程序会**先校验 cookie 能否渲染出正文**：
   - 能 → 自动抓取全书，实时显示进度（`[x/N] 章名: 字数`）；
   - 不能（cookie 被服务端标记失效）→ 弹窗提示「请点①登录重新扫码」，**不会白跑**。
3. **③ 导出 EPUB / TXT**：抓取完成后两个按钮可用，任选其一即可在 `output/` 下生成最终文件。

> 抓取期间**不要关闭**弹出的 Chrome 窗口，程序需通过它读取页面内容。

## 命令行用法

依赖：`pip install -e .`（提供 `utils.wr_hash`、`hook.js`）与 `pip install playwright`，另需系统已装 Chrome。

### 1. 登录（首次或 cookie 失效时）

```bash
python platform/full_book.py --login-only
```

弹出 Chrome 扫码，cookie 存 `cache/cookie.txt`（`--login-only` 会覆盖旧 cookie，强制重新登录）。

### 2. 抓取全书

```bash
python platform/full_book.py <ENCODE_ID>            # 抓 md 并自动生成 epub
python platform/full_book.py <ENCODE_ID> --no-epub  # 只抓 md，不自动打包
```

`<ENCODE_ID>` 从阅读页 URL `https://weread.qq.com/web/reader/<ENCODE_ID>` 中取。
脚本同样会在抓取前校验 cookie（输出 `COOKIE_OK` / `COOKIE_INVALID`）。

### 3. 修复段落换行（fix_paragraphs.py）

canvas 抓取会把每个视觉行当成独立段落（一行一段）。用后处理脚本合并被屏幕换行截断的段落、保留独句成段：

```bash
python platform/fix_paragraphs.py                  # 处理 output/chapters/*.md（自动备份 .bak）
python platform/fix_paragraphs.py 004.md --min 20  # 处理指定文件 / 调独句长度阈值（默认 15）
```

规则：

- 行末是句末标点（。！？；：）」"'… 等）→ 段落结束
- 行末非句末标点 且 行够长 → 段内被屏幕换行截断，合并到当前段
- 行末非句末标点 且 行短（< `--min`）→ 独句成段，保留独立

### 4. 生成 epub / txt（make_epub.py）

```bash
python platform/make_epub.py                # 书名自动从 newbook.log 读
python platform/make_epub.py "<书名>"       # 手动指定书名
python platform/make_epub.py "<书名>" --txt # 输出 txt 而非 epub
```

### 5. 取结果

- 完整电子书：`output/<书名>.epub` 或 `output/<书名>.txt`
- 每章 markdown：`output/chapters/*.md`（修复版）/ `*.bak`（原始抓取版）

## 兼容性说明

### 为什么 weread_exporter 失效

经多轮验证，失效由两个因素叠加导致，**并非单纯的"反爬无法绕过"**：

1. **cookie 被服务端标记**：cookie 在自动化环境反复使用后会被微信读书标记，之后章节直接"加载失败"、canvas 不渲染。这是最主要的拦截点。
2. **pyppeteer 的自动化指纹**：pyppeteer（2022 年停更）启动 Chrome 时注入 `--enable-automation`、`navigator.webdriver=true` 等标志，较易被识别。

> 早期曾推测"新版改用 `fillRect` 位图渲染导致 hook 失效"。后续验证表明，`fillRect` 位图只是 cookie 被标记后的降级表现之一，并非平台普遍的渲染方式变更。

### full_book.py 的可行方案

浏览器层换用 playwright，成功的关键三点：

1. **playwright `connect_over_cdp`**：连接到一个**手动启动**的 Chrome（不走 playwright 的 launch），不注入 `--enable-automation`，`navigator.webdriver === false`，指纹干净。
2. **未被标记的 cookie**：首次或 cookie 失效时扫码获取新 cookie；旧 cookie 若被标记会触发抓取前的校验失败（`COOKIE_INVALID`）。
3. **修改版 hook.js**：新版阅读页每页 `clearRect`，原 `hook.js` 会随之清空已累积的文字；脚本注入时去掉了 `clearRect` 对 markdown 的重置，使文字能跨页持续累积。

### weread_exporter 的兼容修复（记录备查）

主程序虽已无法直接导出，但 `weread_exporter/webpage.py` 仍做了以下兼容修复，使其至少能跑到"加载正文"这一步：

| 环节 | 问题 | 调整 |
|------|------|------|
| 登录 | 自动点击登录按钮在新版 Chrome 下会触发页面被关闭 | 改为半手动登录：浏览器启动后由用户手动扫码，程序仅等待登录完成 |
| 书籍元数据 | 介绍页（bookDetail）对部分书籍返回空数据 | 改从阅读页（reader）读取目录与 bookInfo，并携带登录态 |
| 页面加载 | `page.goto` 等待 `load` 事件超时 | 改用 `waitUntil="domcontentloaded"` |
| 翻页 | `button.readerFooter_button` 已被移除 | 改用新控件 `div.renderTarget_pager_content`，并通过结尾卡片判断章节结束 |

## 注意事项

- 运行期间**不要关闭**弹出的 Chrome 窗口，脚本需要通过它读取页面内容。
- `cache/cookie.txt` 是登录凭证，等价于你的微信读书账号，**不要外传或提交**（`.gitignore` 已忽略 `cache/`）。
- 章节较多时整本抓取需要一定时间（每章约十几秒），脚本支持断点续传：每章 md 存 `output/chapters/N.md`，重跑自动跳过已抓章节；**换书时记得清空** `output/chapters/`（GUI 会自动询问）。
- 抓取完成后**检查 `output/chapters/*.md` 不能有空文件**（0 字节）。空文件意味着那一章没渲染出来（cookie 失效或加载异常）——删掉对应的 `N.md` 重抓该章即可；打包虽已对空章节容错，但空章在 epub/txt 里会是空白。
