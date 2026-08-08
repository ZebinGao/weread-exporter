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

## 已知问题（新版微信读书兼容性）

**当前限制：暂无法导出正文内容。**

新版微信读书升级了反爬机制，正文渲染方式由 `fillText`（绘制文字）改为 `fillRect`（绘制像素块，文字被图像化）。本工具依赖 hook canvas 的 `fillText` 方法来提取文字（见 `weread_exporter/hook.js`），新版不再调用该方法，导致 hook 虽能成功注入，却捕获不到任何文字，导出的正文为空。此为服务端渲染方式变化所致，并非本地配置问题。

为兼容新版运行环境（新版 Chrome + 新版微信读书 DOM），`weread_exporter/webpage.py` 已做如下调整（使登录、目录读取、翻页等环节能在新版下跑通，但最终仍受限于上文的正文提取问题）：

| 环节 | 问题 | 调整 |
|------|------|------|
| 登录 | 自动点击登录按钮在新版 Chrome 下会触发页面被关闭 | 改为半手动登录：浏览器启动后由用户手动扫码，程序仅等待登录完成 |
| 书籍元数据 | 介绍页（bookDetail）对部分书籍返回空数据 | 改从阅读页（reader）读取目录与 bookInfo，并携带登录态 |
| 页面加载 | `page.goto` 等待 `load` 事件超时 | 改用 `waitUntil="domcontentloaded"` |
| 翻页 | `button.readerFooter_button` 已被移除 | 改用新控件 `div.renderTarget_pager_content`，并通过结尾卡片 `.readerFooter_ending_finish` 判断章节结束 |

### 运行注意事项

- **Chrome 需在 PATH 中**：若 Chrome 未加入系统 PATH，运行前需手动添加（否则报 `ChromeNotInstalledError`），例如：
  ```bash
  # Windows (Git Bash)
  export PATH="/c/Program Files/Google/Chrome/Application:$PATH"
  ```
- **首次使用需扫码登录**：运行时弹出的 Chrome 窗口中手动点登录、微信扫码即可；登录态保存在 `cache/cookie.txt`，之后无需重复扫码。
- **book_id 的获取**：从书籍介绍页 URL `/web/bookDetail/{book_id}` 中取。

## 免责申明

本工具仅作技术研究之用，请勿用于商业或违法用途，由于使用该工具导致的侵权或其它问题，该本工具不承担任何责任！
