# 微信读书导出工具

## 实现原理

通过Hook Web页面中的Canvas函数，获取绘制到Canvas中的文本及样式等信息，转换成markdown格式，保存到本地文件，然后再转换成最终的epub或pdf格式，而mobi格式则是使用kindlegen工具从epub格式转换来的。

## INSTALL

```bash
$ pip3 install -e .
```

## USAGE

```bash
$ python -m weread_exporter -b $book_id -o epub -o pdf
```

> 获取书籍ID的方法：在页面`https://weread.qq.com/`搜索目标书籍，进入到书籍介绍页，URL格式为：`https://weread.qq.com/web/bookDetail/08232ac0720befa90825d88`，这里的`08232ac0720befa90825d88`就是书籍ID。

`-o`参数用于指定要保存的文件格式，目前支持的格式有：`epub`、`pdf`、`mobi`，生成的文件在当前目录下的`output`目录中。

`epub`格式适合手机端访问，`pdf`格式适合电脑端访问，`mobi`格式适合kindle访问。

命令行还支持一个可选参数`--force-login`，默认为`False`，指定该参数时，会先进行登录操作。

## 新版微信读书兼容性说明

### 现状

| 工具 | 浏览器层 | 现状 |
|------|---------|------|
| `weread_exporter`（本项目主程序） | pyppeteer | 新版微信读书下已失效 |
| `full_book.py`（独立的替代脚本） | playwright | 可成功导出整本 epub |

### 为什么 weread_exporter 失效

经多轮验证，失效由两个因素叠加导致，**并非单纯的"反爬无法绕过"**：

1. **cookie 被服务端标记**：cookie 在自动化环境反复使用后会被微信读书标记，之后章节直接"加载失败"、canvas 不渲染。这是最主要的拦截点。
2. **pyppeteer 的自动化指纹**：pyppeteer（2022 年停更）启动 Chrome 时注入 `--enable-automation`、`navigator.webdriver=true` 等标志，较易被识别。

> 早期曾推测"新版改用 `fillRect` 位图渲染导致 hook 失效"。后续验证表明，`fillRect` 位图只是 cookie 被标记后的降级表现之一，并非平台普遍的渲染方式变更。

### full_book.py 的可行方案

`full_book.py` 是独立脚本（仅复用 `weread_exporter.utils.wr_hash` 与 `weread_exporter/hook.js`），浏览器层换用 playwright。成功的关键三点：

1. **playwright `connect_over_cdp`**：连接到一个**手动启动**的 Chrome（不走 playwright 的 launch），不注入 `--enable-automation`，`navigator.webdriver === false`，指纹干净。
2. **未被标记的 cookie**：首次或 cookie 失效时，在弹出的浏览器里扫码登录获取新 cookie；旧 cookie 若被标记会导致加载失败。
3. **修改版 hook.js**：新版阅读页每页 `clearRect`，原 `hook.js` 会随之清空已累积的文字；脚本注入时去掉了 `clearRect` 对 markdown 的重置，使文字能跨页持续累积。

实测可完整导出整本（每章字数与目录 wordCount 吻合）。

### 运行 full_book.py

依赖：`pip install playwright`（另需系统已装 Chrome，脚本会自动查找）。

```bash
python full_book.py <ENCODE_ID>
```

书籍 ID（encodeId）从阅读页 URL `/web/reader/<ENCODE_ID>` 中取。首次运行会弹出浏览器扫码登录，cookie 存 `cache/cookie.txt`（**内含登录凭证，切勿外传/提交**，`.gitignore` 已忽略）。完整参数说明与步骤见文末「完整使用步骤」。

### weread_exporter 的兼容修复（记录备查）

主程序虽已无法直接导出，但 `weread_exporter/webpage.py` 仍做了以下兼容修复，使其至少能跑到"加载正文"这一步：

| 环节 | 问题 | 调整 |
|------|------|------|
| 登录 | 自动点击登录按钮在新版 Chrome 下会触发页面被关闭 | 改为半手动登录：浏览器启动后由用户手动扫码，程序仅等待登录完成 |
| 书籍元数据 | 介绍页（bookDetail）对部分书籍返回空数据 | 改从阅读页（reader）读取目录与 bookInfo，并携带登录态 |
| 页面加载 | `page.goto` 等待 `load` 事件超时 | 改用 `waitUntil="domcontentloaded"` |
| 翻页 | `button.readerFooter_button` 已被移除 | 改用新控件 `div.renderTarget_pager_content`，并通过结尾卡片 `.readerFooter_ending_finish` 判断章节结束 |

## 免责申明

本工具仅作技术研究之用，请勿用于商业或违法用途，由于使用该工具导致的侵权或其它问题，该本工具不承担任何责任！

## 完整使用步骤（full_book.py）

从零开始导出一本书的完整流程。

### 1. 安装依赖

```bash
pip install -e .            # 提供 utils.wr_hash、hook.js
pip install playwright      # 浏览器自动化
```

另需系统已安装 Chrome（脚本会自动查找：先 PATH，再 Windows / macOS 的默认安装位置）。

### 2. 运行

书籍 ID 作为命令行参数传入：

```bash
python full_book.py <ENCODE_ID>
```

获取方法：在微信读书网页版打开该书任一章节，URL 形如 `https://weread.qq.com/web/reader/<ENCODE_ID>`，取中间那串即可。

可选参数：

- `--profile <目录>`：Chrome 用户数据目录（默认用临时目录）
- `--port <端口>`：Chrome 调试端口（默认 9222，被占用时换一个）

### 3. 登录（首次）

首次运行会弹出 Chrome 窗口，扫码登录微信读书。cookie 自动存 `cache/cookie.txt`，之后无需重复扫码。cookie 失效时（章节"加载失败"）删掉 `cache/cookie.txt` 重跑即可。

### 4. 取结果

- 完整电子书：`output/<书名>.epub`
- 每章 markdown 源文件：`output/chapters/*.md`（支持断点续传，中断后重跑会自动跳过已抓章节）

### 注意事项

- 运行期间**不要关闭**弹出的 Chrome 窗口，脚本需要通过它读取页面内容。
- `cache/cookie.txt` 是登录凭证，等价于你的微信读书账号，**不要外传或提交**（`.gitignore` 已忽略 `cache/`）。
- 章节较多时（如几十上百章）整本抓取需要一定时间，每章约十几秒，可随时中断续传。
