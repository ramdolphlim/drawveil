#!/bin/bash
# 图隐 DrawVeil · 网页版部署到 Cloudflare Workers（免费版即可）
# 前提：npm i -g wrangler && wrangler login，并已按 wrangler.toml.example 写好 wrangler.toml
set -e
cd "$(dirname "$0")"
python3 build_web.py
# KV 里的文件名要和 src/worker.js 里 FILES 表的一致；升级前端时一起改这里和 worker.js 里的 VERSION
put() { npx wrangler kv key put --binding=FILES --remote "$1" --path "$2"; }
put index.v3.html src/index.html
put app.v3.js     src/app.js
put app.v4.css    src/app.css
put pyworker.js   src/pyworker.js
put favicon.svg   src/favicon.svg
put engine.py     dist/engine.min.py
put samples.py    dist/samples.min.py
npx wrangler deploy
