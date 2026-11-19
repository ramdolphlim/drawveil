/* 图隐 DrawVeil · 网页版 · 简洁版界面 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const V = (document.currentScript && document.currentScript.src.split('v=')[1]) || '1';

  // ---------- 规则 ----------
  const OPTIONS = [
    ['titleblock_person', true, '图签与会签栏', '人员姓名（实名列、角色栏、图框属性）'],
    ['titleblock_org', true, '图签与会签栏', '单位名称（建设单位、设计单位……）'],
    ['titleblock_project', true, '图签与会签栏', '工程名称 / 项目名称 / 子项名称'],
    ['titleblock_address', true, '图签与会签栏', '工程地址 / 建设地点'],
    ['titleblock_projno', true, '图签与会签栏', '工程编号 / 合同号（图号不动）'],
    ['titleblock_cert', true, '图签与会签栏', '资质证书号、注册号、执业印章号'],
    ['titleblock_date', false, '图签与会签栏', '图签日期（默认保留）'],
    ['detect_company', true, '全图文字', '公司 / 设计院 / 机构名称（中文 + 英文）'],
    ['detect_phone', true, '全图文字', '手机号、座机、传真'],
    ['detect_email', true, '全图文字', '电子邮箱'],
    ['detect_idcard', true, '全图文字', '身份证号（校验位验证）'],
    ['detect_uscc', true, '全图文字', '统一社会信用代码（校验位验证）'],
    ['detect_account', true, '全图文字', '银行账号、QQ / 微信号'],
    ['detect_url', true, '全图文字', '网址'],
    ['coord_text', false, '全图文字', '测量坐标文字（默认保留）'],
    ['clear_signature_strokes', true, '图形与文件', '删除签名栏里的手写签名笔迹'],
    ['clear_logo', true, '图形与文件', '删除单位名称左侧的 Logo 图形'],
    ['clear_signature_blocks', true, '图形与文件', '清空签名、印章、Logo 类图块'],
    ['clean_metadata', true, '图形与文件', '清除作者、最后保存人、编辑时长等文件属性'],
    ['normalize_dates', true, '图形与文件', '创建 / 修改时间统一改为 2000-01-01'],
    ['strip_paths', true, '图形与文件', '外部参照、图片、打印机路径只留文件名'],
    ['remove_hyperlinks', true, '图形与文件', '清除超链接'],
    ['remove_thumbnail', true, '图形与文件', '删除缩略图和块预览图'],
    ['rename_symbols', true, '图形与文件', '图层名、块名、布局名里的敏感词一并替换'],
    ['remove_ole', false, '图形与文件', '删除 OLE 嵌入对象（可能是盖章扫描件，也可能是门窗表）']
  ];
  const DEF_WL = ['中国建筑标准设计研究院', '中国建筑工业出版社', '中国计划出版社', '住房和城乡建设部',
    '中华人民共和国住房和城乡建设部', '国家市场监督管理总局', '国家建筑标准设计'];
  const META_ONLY = ['clean_metadata', 'normalize_dates', 'strip_paths', 'remove_hyperlinks', 'remove_thumbnail'];
  const PRESET_OPTS = {
    standard: () => Object.fromEntries(OPTIONS.map(o => [o[0], o[1]])),
    strict: () => Object.fromEntries(OPTIONS.map(o => [o[0], true])),
    meta: () => Object.fromEntries(OPTIONS.map(o => [o[0], META_ONLY.includes(o[0])]))
  };
  const PRESETS = [['standard', '标准外发', '人员、单位、项目、签名'], ['strict', '严格', '再加地址、编号、日期'], ['meta', '只清理文件属性', '作者、路径、缩略图']];
  const GROUPS = [
    ['person', '人员姓名', '人员', ['person']],
    ['org', '单位名称', '单位', ['org']],
    ['project', '项目名称与地址', '项目与地址', ['project', 'address', 'projno']],
    ['contact', '电话与证件号', '电话与证件', ['phone', 'email', 'idcard', 'uscc', 'account', 'url', 'cert']],
    ['other', '自定义与其他', '其他', ['keyword', 'date', 'coord']]
  ];
  const groupOf = (cat) => (GROUPS.find(g => g[3].includes(cat)) || GROUPS[4])[0];
  const OK_ICON = '<svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true"><circle class="ic-ok-bg" cx="48" cy="48" r="46"></circle><path class="ic-ok" d="M29 49 L42 62 L68 35" fill="none" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"></path></svg>';
  const WARN_ICON = '<svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true"><circle class="ic-warn-bg" cx="48" cy="48" r="46"></circle><path class="ic-warn" d="M48 26 V54 M48 68 V69" stroke-width="7" stroke-linecap="round"></path></svg>';
  const MOON = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"></path></svg>';
  const SUN = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.6"></circle><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path></svg>';
  const store = {
    get(k, d) { try { const v = localStorage.getItem('drawveil.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('drawveil.' + k, JSON.stringify(v)); } catch (e) { /* 无痕模式等 */ } }
  };
  const S = {
    files: [], view: 'drop', from: 'drop',
    options: Object.assign(PRESET_OPTS.standard(), store.get('options', {})),
    keywords: store.get('keywords', []), whitelist: store.get('whitelist', DEF_WL),
    scan: null, terms: [], result: null, tab: 'all', q: '', ready: false, t0: 0
  };
  const save = () => { store.set('options', S.options); store.set('keywords', S.keywords); store.set('whitelist', S.whitelist); };
  const config = () => ({ options: S.options, keywords: S.keywords, whitelist: S.whitelist });
  function presetOf(o) {
    for (const [k] of PRESETS) { const p = PRESET_OPTS[k](); if (OPTIONS.every(x => !!o[x[0]] === !!p[x[0]])) return k; }
    return 'custom';
  }

  // ---------- 后台引擎 ----------
  const worker = new Worker('/pyworker.js?v=' + V);
  let seq = 0;
  const pending = new Map();
  worker.onmessage = (ev) => {
    const m = ev.data;
    if (m.type === 'log') { $('busy-line').textContent = String(m.text).trim(); return; }
    if (m.type === 'ready') { S.ready = true; renderFoot(); return; }
    if (m.type === 'fatal') { toast('脱敏引擎加载失败：' + m.error + '。请检查网络后刷新页面'); if (S.view === 'busy') show('drop'); return; }
    const p = pending.get(m.id);
    if (!p) return;
    pending.delete(m.id);
    if (m.type === 'result') p.resolve(m.result); else p.reject(new Error(m.error));
  };
  function call(cmd, args, transfer) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, cmd, args }, transfer || []);
    });
  }

  // ---------- 小部件 ----------
  let toastTimer = 0;
  function toast(text) {
    const t = $('toast'); t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 5000);
  }
  function download(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  }

  // ---------- 白天 / 黑夜 ----------
  const sysDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const curTheme = () => document.documentElement.dataset.theme || (sysDark && sysDark.matches ? 'dark' : 'light');
  function paintTheme() {
    const dark = curTheme() === 'dark', b = $('b-theme');
    b.innerHTML = dark ? SUN : MOON;
    b.setAttribute('aria-label', dark ? '切换到白天模式' : '切换到黑夜模式'); b.title = b.getAttribute('aria-label');
  }
  function setTheme(t) {
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
    paintTheme();
  }
  if (sysDark && sysDark.addEventListener) sysDark.addEventListener('change', paintTheme);

  // ---------- 视图 ----------
  const VIEWS = ['drop', 'busy', 'scan', 'review', 'done', 'set'];
  function show(v) {
    if (v === 'set' && S.view !== 'set') S.from = S.view === 'busy' ? 'drop' : S.view;
    S.view = v;
    VIEWS.forEach(k => { $('v-' + k).hidden = k !== v; });
    const back = { scan: '‹ 重新选择', review: '‹ 返回', set: '‹ 完成' }[v];
    $('b-back').hidden = !back; $('b-back').textContent = back || '';
    $('brand').hidden = !!back;
    $('b-gear').hidden = v === 'set' || v === 'busy';
    renderFoot();
    window.scrollTo(0, 0);
  }
  function goBack() {
    if (S.view === 'set') show(S.from || 'drop');
    else if (S.view === 'review') show('scan');
    else if (S.view === 'scan') show('drop');
  }
  function renderFoot() {
    const f = $('foot'), sep = '<span class="s">·</span>';
    if (S.view === 'drop') {
      const p = presetOf(S.options), pn = (PRESETS.find(x => x[0] === p) || [0, '自定义规则'])[1];
      f.innerHTML = '<button type="button" data-set="1">' + esc(pn) + '</button>' + sep + '<span>DWG 请先另存为 DXF，或用桌面版</span>' + sep +
        '<span>' + (S.ready ? '<span class="dot">●</span> 引擎已就绪' : '引擎加载中…') + '</span>';
    } else if (S.view === 'scan' && S.scan) {
      const n = S.scan.files.map(x => x.name);
      f.textContent = n.slice(0, 2).join('、') + (n.length > 2 ? ' 等 ' + n.length + ' 张' : '') + ' · 图纸没有离开这台电脑';
    } else if (S.view === 'done') {
      f.textContent = '报告和代号对照表含原文，只能内部留存，不要随图纸发出';
    } else f.innerHTML = '';
  }

  // ---------- ① 选择图纸 ----------
  async function addAndScan(list) {
    const all = [...list].filter(f => /\.(dxf|dwg)$/i.test(f.name));
    const dxf = all.filter(f => /\.dxf$/i.test(f.name));
    if (!all.length) { toast('没有找到 DXF 图纸'); return; }
    if (!dxf.length) { toast('网页版只能处理 DXF。DWG 请在 CAD 里另存为 DXF，或用桌面版直接处理'); return; }
    if (dxf.length < all.length) toast('跳过了 ' + (all.length - dxf.length) + ' 个 DWG：网页版只能处理 DXF');
    S.files = dxf.map(f => ({ name: f.webkitRelativePath ? f.webkitRelativePath.split('/').slice(1).join('_') || f.name : f.name, file: f, data: null }));
    scan();
  }
  async function readAll() {
    const out = [];
    for (const f of S.files) {
      if (!f.data) f.data = await f.file.arrayBuffer();
      out.push({ name: f.name, data: f.data.slice(0) });
    }
    return out;
  }
  function busy(title) {
    $('busy-title').textContent = title;
    $('busy-line').textContent = S.ready ? '' : '正在加载脱敏引擎（首次约 10MB，之后会被浏览器缓存）…';
    S.t0 = Date.now(); show('busy');
  }

  // ---------- ② 扫描 ----------
  async function scan() {
    busy('正在扫描');
    try {
      const files = await readAll();
      const res = await call('scan', { files, config: config() }, files.map(f => f.data));
      S.scan = Object.assign(res, { seconds: Math.max(0.1, (Date.now() - S.t0) / 1000).toFixed(1) });
      S.terms = res.terms.map(t => Object.assign({}, t));
      S.tab = 'all'; S.q = ''; $('rv-q').value = '';
      renderScan(); show('scan');
    } catch (e) { toast('扫描失败：' + e.message); show('drop'); }
  }
  const delOf = (files) => files.reduce((a, f) => a + Object.values(f.deletions || {}).reduce((x, y) => x + y, 0), 0);
  function renderScan() {
    const T = S.terms, sc = S.scan, F = sc.files;
    const total = T.reduce((a, t) => a + t.count, 0);
    const dels = S.options.clear_signature_strokes || S.options.clear_logo ? delOf(F) : 0;
    $('sc-total').textContent = total;
    $('sc-sub').textContent = total ? '处敏感信息，分布在 ' + F.length + ' 张图纸里' : '没有找到敏感信息';
    $('sc-meta').textContent = '用时 ' + sc.seconds + ' 秒 · 坐标、尺寸和图层不会改动';
    const sums = GROUPS.map(g => [g[1], T.filter(t => g[3].includes(t.cat)).reduce((a, t) => a + t.count, 0)]).filter(x => x[1]);
    const max = Math.max(1, ...sums.map(x => x[1]));
    let h = sums.map(([n, c]) => '<div class="bar"><span>' + esc(n) + '</span><div class="tr"><i style="width:' + Math.max(3, Math.round(c / max * 100)) + '%"></i></div><span class="n">' + c + ' 处</span></div>').join('');
    if (dels) h += (h ? '<div class="sep"></div>' : '') + '<div class="bar"><span>签名笔迹与 Logo</span><span class="hint">整块删除，表格线和图框线保留</span><span class="n">' + dels + ' 个</span></div>';
    $('sc-bars').innerHTML = h;
    const warns = F.filter(f => f.error).slice(0, 3).map(f => f.name + '：' + f.error);
    const tz = F.filter(f => (f.notes || []).some(n => /天正/.test(n))).length;
    if (tz) warns.push(tz + ' 张图含天正对象，里面的文字可能处理不到，完成后会提示');
    $('sc-warn').hidden = !warns.length; $('sc-warn').innerHTML = warns.map(esc).join('<br>');
    const okFiles = F.filter(f => !f.error).length;
    $('b-apply').textContent = total || dels ? '脱敏 ' + okFiles + ' 张图纸' : '清理 ' + okFiles + ' 张图纸的文件属性';
    $('b-apply').disabled = okFiles <= 0;
    $('b-review').hidden = !T.length;
  }

  // ---------- ③ 核对 ----------
  function visible() {
    return S.terms.filter(t => (S.tab === 'all' || groupOf(t.cat) === S.tab) && (!S.q || t.term.toLowerCase().includes(S.q) || String(t.replace).toLowerCase().includes(S.q)));
  }
  function renderReview() {
    const T = S.terms;
    $('rv-title').textContent = '核对 ' + T.reduce((a, t) => a + t.count, 0) + ' 处敏感信息';
    $('rv-tabs').innerHTML = [['all', '全部', T.length]].concat(GROUPS.map(g => [g[0], g[2], T.filter(t => g[3].includes(t.cat)).length]))
      .filter(x => x[0] === 'all' || x[2]).map(([k, n, c]) => '<button type="button" data-tab="' + k + '" aria-pressed="' + (S.tab === k) + '">' + esc(n) + ' ' + c + '</button>').join('');
    const L = visible();
    $('rv-list').innerHTML = L.length ? L.map(t => {
      const i = T.indexOf(t);
      return '<label class="row' + (t.enabled ? '' : ' off') + '"><input type="checkbox" data-en="' + i + '"' + (t.enabled ? ' checked' : '') + ' aria-label="替换 ' + esc(t.term) + '">' +
        '<span class="t" title="' + esc(t.term) + '">' + esc(t.term) + (t.warn ? '<small>' + esc(t.warn) + '</small>' : '') + '</span>' +
        '<span class="code">→<input type="text" data-rep="' + i + '" value="' + esc(t.enabled ? t.replace : '保留') + '"' + (t.enabled ? '' : ' disabled') + ' aria-label="' + esc(t.term) + ' 替换为"></span>' +
        '<span class="why">' + esc(t.rule) + ' · ' + t.count + ' 处</span></label>';
    }).join('') : '<div class="empty">没有符合条件的项</div>';
    const on = T.filter(t => t.enabled);
    $('rv-sum').textContent = '替换 ' + on.reduce((a, t) => a + t.count, 0) + ' 处 · 保留 ' + (T.length - on.length) + ' 项';
    $('b-apply2').textContent = $('b-apply').textContent;
  }

  // ---------- 执行 ----------
  async function apply() {
    busy('正在脱敏');
    try {
      const files = await readAll();
      const decisions = {};
      S.terms.forEach(t => { decisions[t.term] = { enabled: t.enabled, replace: t.replace }; });
      S.result = await call('apply', { files, config: config(), decisions }, files.map(f => f.data));
      renderDone(); show('done');
    } catch (e) { toast('脱敏失败：' + e.message); show('scan'); }
  }

  // ---------- ④ 完成 ----------
  function renderDone() {
    const R = S.result, F = R.files;
    const bad = F.filter(f => f.error || !f.geometry_ok || f.residual.length);
    const bin = F.filter(f => !f.error && f.binary_residual.length);
    $('dn-icon').innerHTML = !bad.length && !bin.length ? OK_ICON : WARN_ICON;
    $('dn-title').textContent = !bad.length ? F.length + ' 张图纸已脱敏' : (F.length - bad.length) + ' 张已完成，' + bad.length + ' 张需要看一下';
    $('dn-sub').textContent = '点下面的按钮下载' + (R.outputFiles.length > 1 ? '（ZIP 压缩包）' : '');
    const chg = S.terms.filter(t => t.enabled).reduce((a, t) => a + t.count, 0);
    const dels = delOf(F), geo = F.filter(f => f.geometry_ok).length, res = F.reduce((a, f) => a + f.residual.length, 0);
    const line = (cls, mark, text, val) => '<div class="' + cls + '"><span><span class="' + (cls || 'g') + '">' + mark + '</span>&nbsp; ' + esc(text) + '</span><span>' + esc(val) + '</span></div>';
    let h = line('', '✓', '替换敏感信息', chg + ' 处');
    if (dels) h += line('', '✓', '删除签名笔迹与 Logo', dels + ' 个图形');
    h += geo === F.length ? line('', '✓', '坐标、尺寸、标注与原图一致', geo + ' / ' + F.length) : line('b', '✗', '几何校验未通过', (F.length - geo) + ' 张');
    h += res ? line('b', '✗', '仍有残留文字', res + ' 处') : line('', '✓', '复查残留文字', '0 处');
    if (bin.length) h += line('w', '!', '天正对象里仍有原文', bin.length + ' 张');
    $('dn-checks').innerHTML = h;
    const iss = [];
    F.forEach(f => {
      const nm = f.output || f.name;
      if (f.error) iss.push(nm + '：' + f.error);
      else if (!f.geometry_ok) iss.push(nm + '：' + f.geometry);
      if (f.residual.length) iss.push(nm + ' 仍有：' + f.residual.join('、'));
      if (f.binary_residual.length) iss.push(nm + ' 的天正对象里仍有：' + f.binary_residual.join('、') + '。建议在天正里“图纸导出”为 T3 后再处理一次');
    });
    $('dn-issues').hidden = !iss.length; $('dn-issues').innerHTML = iss.map(x => '<li>' + esc(x) + '</li>').join('');
    $('b-dl').textContent = R.outputFiles.length === 1 ? '下载脱敏图纸' : '下载 ' + R.outputFiles.length + ' 张脱敏图纸';
    $('b-dl').disabled = !R.outputFiles.length;
  }

  // ---------- 设置 ----------
  function renderSettings() {
    const p = presetOf(S.options), open = new Set([...document.querySelectorAll('#v-set details[open]')].map(d => d.id));
    const groups = {};
    OPTIONS.forEach(o => (groups[o[2]] = groups[o[2]] || []).push(o));
    let h = '<h1>设置</h1>';
    h += '<section><h2>脱敏程度</h2><div class="presets">' + PRESETS.map(([k, n, d]) =>
      '<button type="button" data-preset="' + k + '" aria-pressed="' + (p === k) + '"><b>' + n + '</b><span>' + d + '</span></button>').join('') + '</div>' +
      (p === 'custom' ? '<p class="muted" style="font-size:12px;margin:8px 0 0">当前是自定义规则，在下方“详细规则”里调整</p>' : '') + '</section>';
    h += '<section class="rows">';
    h += '<details id="d-rules"' + (open.has('d-rules') ? ' open' : '') + '><summary>详细规则</summary><div class="dbody">' + Object.keys(groups).map(g =>
      '<div class="optgroup">' + esc(g) + '</div>' + groups[g].map(o => '<label class="opt"><input type="checkbox" data-o="' + o[0] + '"' + (S.options[o[0]] ? ' checked' : '') + '><span>' + esc(o[3]) + '</span></label>').join('')).join('') + '</div></details>';
    h += '<details id="d-words"' + (open.has('d-words') ? ' open' : '') + '><summary>自定义敏感词与白名单<span class="muted" style="margin-left:auto;margin-right:10px;font-size:13px">' + S.keywords.length + ' 个词</span></summary><div class="dbody">' +
      '<div class="optgroup">自定义敏感词：一行一个，可写成 原词=替换词，re: 开头为正则</div><textarea id="s-kw">' + esc(S.keywords.join('\n')) + '</textarea>' +
      '<div class="optgroup">白名单：这些词永远不替换</div><textarea id="s-wl">' + esc(S.whitelist.join('\n')) + '</textarea></div></details>';
    h += '<div class="srow"><div class="l">恢复默认设置<small>设置只保存在这个浏览器里</small></div><div class="r"><button type="button" class="btn" id="s-reset">恢复默认</button></div></div>';
    h += '</section><p class="muted" style="font-size:12px;margin:0">需要直接处理 DWG、监视文件夹自动脱敏，或者让同一个人在每批图纸里都用同一个代号，请用桌面版。</p>';
    $('v-set').innerHTML = h;
  }

  // ---------- 事件 ----------
  $('b-ring').onclick = () => $('fi').click();
  $('b-pick').onclick = () => $('fi').click();
  $('b-pickdir').onclick = () => $('fd').click();
  $('fi').onchange = (e) => { addAndScan(e.target.files); e.target.value = ''; };
  $('fd').onchange = (e) => { addAndScan(e.target.files); e.target.value = ''; };
  $('b-sample').onclick = async () => {
    busy('正在生成示例图纸');
    try {
      const list = await call('samples', {});
      S.files = list.map(s => ({ name: s.name, file: null, data: s.data }));
      scan();
    } catch (e) { toast('示例生成失败：' + e.message); show('drop'); }
  };
  $('b-back').onclick = goBack;
  $('b-theme').onclick = () => { const t = curTheme() === 'dark' ? 'light' : 'dark'; setTheme(t); store.set('theme', t); };
  $('b-gear').onclick = () => { renderSettings(); show('set'); };
  $('foot').onclick = (e) => { if (e.target.closest('[data-set]')) { renderSettings(); show('set'); } };
  $('b-apply').onclick = apply; $('b-apply2').onclick = apply;
  $('b-review').onclick = () => { renderReview(); show('review'); };
  $('rv-tabs').onclick = (e) => { const b = e.target.closest('[data-tab]'); if (b) { S.tab = b.dataset.tab; renderReview(); } };
  $('rv-q').oninput = (e) => { S.q = e.target.value.trim().toLowerCase(); renderReview(); };
  $('rv-list').onchange = (e) => { const en = e.target.dataset.en; if (en !== undefined) { S.terms[+en].enabled = e.target.checked; renderReview(); } };
  $('rv-list').oninput = (e) => { const r = e.target.dataset.rep; if (r !== undefined) S.terms[+r].replace = e.target.value; };
  $('b-dl').onclick = () => {
    const R = S.result;
    if (R.outputFiles.length === 1) download(new Blob([R.outputFiles[0].data], { type: 'application/dxf' }), R.outputFiles[0].name);
    else download(new Blob([R.drawingsZip], { type: 'application/zip' }), '图隐_脱敏图纸.zip');
  };
  $('b-report').onclick = () => {
    const w = window.open(URL.createObjectURL(new Blob([S.result.reportHtml], { type: 'text/html;charset=utf-8' })), '_blank');
    if (!w) toast('浏览器拦截了新窗口，可以改用“下载报告与对照表”');
  };
  $('b-repzip').onclick = () => download(new Blob([S.result.reportZip], { type: 'application/zip' }), '图隐_报告与对照表(含原文,勿外发).zip');
  $('b-again').onclick = () => { S.files = []; S.scan = null; S.result = null; show('drop'); };
  const set = $('v-set');
  set.onclick = (e) => {
    const pb = e.target.closest('[data-preset]');
    if (pb) { S.options = PRESET_OPTS[pb.dataset.preset](); save(); renderSettings(); return; }
    if (e.target.id === 's-reset' && confirm('把所有设置恢复为默认值？')) {
      S.options = PRESET_OPTS.standard(); S.keywords = []; S.whitelist = DEF_WL.slice(); save(); renderSettings();
    }
  };
  set.onchange = (e) => {
    const t = e.target, lines = (v) => v.split('\n').map(x => x.trim()).filter(Boolean);
    if (t.dataset.o) { S.options[t.dataset.o] = t.checked; save(); renderSettings(); }
    else if (t.id === 's-kw') { S.keywords = lines(t.value); save(); renderSettings(); }
    else if (t.id === 's-wl') { S.whitelist = lines(t.value); save(); }
  };
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') goBack(); });
  let depth = 0;
  const canDrop = () => S.view === 'drop' || S.view === 'done';
  document.addEventListener('dragenter', (e) => { e.preventDefault(); depth++; if (canDrop()) document.body.classList.add('dragging'); });
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; document.body.classList.remove('dragging'); } });
  document.addEventListener('drop', async (e) => {
    e.preventDefault(); depth = 0; document.body.classList.remove('dragging');
    if (!canDrop()) return;
    const items = [...(e.dataTransfer.items || [])].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
    if (items.some(x => x.isDirectory)) {
      const out = [];
      const walk = (en) => new Promise(res => {
        if (en.isFile) en.file(f => { out.push(f); res(); }, () => res());
        else { const r = en.createReader(), all = []; const rd = () => r.readEntries(async (es) => { if (!es.length) { for (const x of all) await walk(x); res(); } else { all.push(...es); rd(); } }, () => res()); rd(); }
      });
      for (const x of items) await walk(x);
      addAndScan(out);
    } else addAndScan(e.dataTransfer.files);
  });

  setTheme(store.get('theme', ''));
  show('drop');
})();
