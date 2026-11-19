// 图隐 DrawVeil · Cloudflare Worker：只提供静态页面，图纸处理全部在用户浏览器里完成
const VERSION = '5';
const T = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', txt: 'text/plain; charset=utf-8', svg: 'image/svg+xml', css: 'text/css; charset=utf-8' };
const FILES = {
  '/': ['index.v3.html', T.html], '/index.html': ['index.v3.html', T.html], '/app.js': ['app.v3.js', T.js], '/app.css': ['app.v4.css', T.css],
  '/pyworker.js': ['pyworker.js', T.js], '/engine.py': ['engine.py', T.txt], '/samples.py': ['samples.py', T.txt],
  '/favicon.svg': ['favicon.svg', T.svg]
};
const CSP = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval' 'wasm-unsafe-eval'; " +
  "worker-src 'self' blob:; connect-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; " +
  "img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
export default {
  async fetch(request, env) {
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method not allowed', { status: 405 });
    const url = new URL(request.url);
    const f = FILES[url.pathname];
    if (!f) return new Response('Not found', { status: 404, headers: { 'content-type': T.txt } });
    let body = await env.FILES.get(f[0], { cacheTtl: 300 });
    if (body == null) return new Response('Service unavailable', { status: 503 });
    if (f[1] === T.html) body = body.replaceAll('__V__', VERSION);
    return new Response(request.method === 'HEAD' ? null : body, {
      headers: {
        'content-type': f[1],
        'cache-control': f[1] === T.html ? 'no-cache' : 'public, max-age=86400',
        'content-security-policy': CSP,
        'x-content-type-options': 'nosniff',
        'referrer-policy': 'no-referrer',
        'permissions-policy': 'camera=(), microphone=(), geolocation=()'
      }
    });
  }
};
