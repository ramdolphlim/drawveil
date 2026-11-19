# 图隐 DrawVeil · 网页版

在线使用：<https://drawveil.limch.cc>

网页版把脱敏引擎（就是仓库根目录的 `cad_desensitize.py`）用 [Pyodide](https://pyodide.org) 放在浏览器的后台线程里运行。图纸只在打开网页的这台电脑上处理，不会上传到服务器。Cloudflare Worker 只负责把静态文件发给浏览器。

- 只支持 DXF；DWG 请先在 CAD 里另存为 DXF，或使用[桌面版](../desktop/README.md)。
- 首次打开会从 jsDelivr 下载约 10MB 的 Pyodide 运行环境，之后浏览器会缓存。

## 文件

| 文件 | 用途 |
|---|---|
| `src/index.html`、`src/app.js`、`src/app.css` | 页面（样式和桌面版共用一套） |
| `src/pyworker.js` | 浏览器后台线程：加载 Pyodide 和引擎 |
| `src/worker.js` | Cloudflare Worker：从 KV 读文件并加上安全响应头 |
| `web_api.py` | 引擎的浏览器接口（扫描、脱敏、生成示例图纸） |
| `build_web.py` | 从 `cad_desensitize.py` 生成浏览器用的 `dist/engine.min.py` 和 `dist/samples.min.py` |

## 本地预览

```bash
python3 build_web.py
mkdir -p /tmp/dv && cp src/* /tmp/dv/ && cp dist/engine.min.py /tmp/dv/engine.py && cp dist/samples.min.py /tmp/dv/samples.py
sed -i.bak 's/__V__/dev/g' /tmp/dv/index.html && cd /tmp/dv && python3 -m http.server 8000
```

然后打开 <http://localhost:8000>。

## 部署到自己的 Cloudflare

1. `npm i -g wrangler && wrangler login`
2. `wrangler kv namespace create drawveil-files`，把输出的 id 填进 `wrangler.toml`（从 `wrangler.toml.example` 复制）
3. `./deploy.sh`

全部用 Cloudflare 免费版的 Workers 和 KV 就够了。
