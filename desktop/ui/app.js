/* 图隐 DrawVeil 桌面版 · 简洁版界面 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- 与 Python 通信 ----------
  let native = false;
  const bridge = (name, ...args) => {
    if (native) return window.pywebview.api[name](...args);
    return fetch('/api/' + name, { method: 'POST', body: JSON.stringify(args) }).then(r => r.json()).then(j => {
      if (!j.ok) throw new Error(j.error);
      return j.result;
    });
  };
  const call = async (name, ...args) => {
    try { return await bridge(name, ...args); } catch (e) { toast(String(e && e.message || e)); throw e; }
  };

  // ---------- 常量 ----------
  const OK_ICON = '<svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true"><circle class="ic-ok-bg" cx="48" cy="48" r="46"></circle><path class="ic-ok" d="M29 49 L42 62 L68 35" fill="none" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"></path></svg>';
  const WARN_ICON = '<svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true"><circle class="ic-warn-bg" cx="48" cy="48" r="46"></circle><path class="ic-warn" d="M48 26 V54 M48 68 V69" stroke-width="7" stroke-linecap="round"></path></svg>';
  const MOON = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"></path></svg>';
  const SUN = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.6"></circle><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path></svg>';
  const META_ONLY = ['clean_metadata', 'normalize_dates', 'strip_paths', 'remove_hyperlinks', 'remove_thumbnail'];
  const GROUPS = [
    ['person', '人员姓名', ['person']],
    ['org', '单位名称', ['org']],
    ['project', '项目名称与地址', ['project', 'address', 'projno']],
    ['contact', '电话与证件号', ['phone', 'email', 'idcard', 'uscc', 'account', 'url', 'cert']],
    ['other', '自定义与其他', ['keyword', 'date', 'coord']]
  ];
  const groupOf = (cat) => (GROUPS.find(g => g[2].includes(cat)) || GROUPS[4])[0];
  const PRESETS = [['standard', '标准外发', '人员、单位、项目、签名'], ['strict', '严格', '再加地址、编号、日期'], ['meta', '只清理文件属性', '作者、路径、缩略图']];

  const S = { st: null, seq: 0, view: 'drop', from: 'drop', terms: [], scan: null, result: null, tab: 'all', q: '', lastJob: null, busyKind: '' };

  const FORCE = (location.search.match(/plat=(mac|win)/) || [])[1];   // 仅用于预览两套外观
  const win = () => (FORCE || (S.st && S.st.platform)) === 'win';
  const finder = () => win() ? '资源管理器' : '访达';

  // ---------- 小部件 ----------
  let toastTimer = 0;
  function toast(text) {
    const t = $('toast'); t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 4200);
  }
  function ask(title, text, value) {
    return new Promise(resolve => {
      $('md-title').textContent = title; $('md-text').textContent = text || '';
      const inp = $('md-input'); inp.hidden = value === undefined; inp.value = value || '';
      $('modal').hidden = false; setTimeout(() => (value === undefined ? $('md-ok') : inp).focus(), 30);
      const done = (ok) => { $('modal').hidden = true; $('md-ok').onclick = $('md-cancel').onclick = inp.onkeydown = null; resolve(ok ? (value === undefined ? true : inp.value.trim()) : null); };
      $('md-ok').onclick = () => done(true); $('md-cancel').onclick = () => done(false);
      inp.onkeydown = (e) => { if (e.key === 'Enter') done(true); if (e.key === 'Escape') done(false); };
    });
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

  // ---------- 视图切换 ----------
  const VIEWS = ['drop', 'busy', 'scan', 'review', 'done', 'set'];
  function show(v) {
    if (v === 'set' && S.view !== 'set') S.from = S.view === 'busy' ? 'drop' : S.view;
    S.view = v;
    if (v === 'busy') S.busyAt = Date.now();
    VIEWS.forEach(k => { $('v-' + k).hidden = k !== v; });
    const back = { scan: '‹ 重新选择', review: '‹ 返回', done: '', set: '‹ 完成' }[v];
    $('b-back').hidden = !back; $('b-back').textContent = back || '';
    $('b-gear').hidden = v === 'set' || v === 'busy';
    renderFoot();
  }
  function goBack() {
    if (S.view === 'set') { show(S.from || 'drop'); renderFoot(); }
    else if (S.view === 'review') show('scan');
    else if (S.view === 'scan' || S.view === 'done') show('drop');
  }

  function presetOf(opts) {
    const def = S.st.defaults.options, keys = Object.keys(def);
    if (keys.every(k => !!opts[k] === !!def[k])) return 'standard';
    if (keys.every(k => opts[k])) return 'strict';
    if (keys.every(k => !!opts[k] === META_ONLY.includes(k))) return 'meta';
    return 'custom';
  }
  function outLabel() {
    const s = S.st.settings;
    return s.output_mode === 'fixed' && s.output_dir ? '输出到 ' + s.output_dir.split(/[\\/]/).pop() : '输出到原文件旁';
  }
  function renderFoot() {
    const f = $('foot'), s = S.st ? S.st.settings : null;
    if (!s) { f.innerHTML = ''; return; }
    const sep = '<span class="s">·</span>';
    if (S.view === 'drop') {
      const p = presetOf(s.options), pn = (PRESETS.find(x => x[0] === p) || [0, '自定义规则'])[1];
      f.innerHTML = '<button type="button" data-set="1">' + esc(pn) + '</button>' + sep + '<button type="button" data-set="1">' + esc(outLabel()) + '</button>' + sep +
        '<button type="button" data-set="1">' + (S.st.oda ? '<span class="dot">●</span> DWG 可用' : S.st.libredwg ? '<span class="dot warn">●</span> DWG 可用（内置转换器）' : '<span class="dot bad">●</span> DWG 需要 ODA 转换器') + '</button>' + sep +
        '<button type="button" data-set="1">监视文件夹 ' + (s.watch_enabled && s.watch_dir ? '开' : '关') + '</button>';
    } else if (S.view === 'scan' && S.scan) {
      f.textContent = (S.scan.names || []).slice(0, 2).join('、') + (S.scan.files > 2 ? ' 等 ' + S.scan.files + ' 张' : '') +
        (s.reuse_mapping ? ' · 同一个人在每批图纸里用同一个代号' : '');
    } else if (S.view === 'done') {
      f.textContent = '报告和代号对照表含原文，单独保存在「' + (s.report_dir || '').split(/[\\/]/).slice(-1)[0] + '」，不要随图纸发出';
    } else f.innerHTML = '';
  }

  // ---------- ① 选择图纸 ----------
  async function pick(folder) {
    let paths = [];
    if (native) {
      const r = await call(folder ? 'pick_folder' : 'pick_files');
      paths = r ? (Array.isArray(r) ? r : [r]) : [];
    } else {
      const v = await ask(folder ? '选择文件夹' : '选择图纸', '浏览器模式下请输入路径，多个用英文分号隔开', '');
      paths = v ? v.split(';').map(x => x.trim()).filter(Boolean) : [];
    }
    if (paths.length) start(paths);
  }
  async function start(paths) {
    S.busyKind = 'scan'; $('busy-title').textContent = '正在扫描'; $('busy-line').textContent = '';
    show('busy');
    try { S.st = await bridge('start_session', paths); } catch (e) { toast(String(e.message || e)); show('drop'); }
  }

  // ---------- ② 扫描结果 ----------
  function renderScan() {
    const T = S.terms, sc = S.scan;
    const total = T.reduce((a, t) => a + t.count, 0);
    const dels = Object.values(sc.deleted || {}).reduce((a, b) => a + b, 0);
    $('sc-total').textContent = total;
    $('sc-sub').textContent = total ? '处敏感信息，分布在 ' + sc.files + ' 张图纸里' : '没有找到敏感信息';
    $('sc-meta').textContent = '用时 ' + (sc.seconds || 0) + ' 秒 · 坐标、尺寸和图层不会改动';
    const sums = GROUPS.map(g => [g[1], T.filter(t => g[2].includes(t.cat)).reduce((a, t) => a + t.count, 0)]).filter(x => x[1]);
    const max = Math.max(1, ...sums.map(x => x[1]));
    let h = sums.map(([n, c]) => '<div class="bar"><span>' + esc(n) + '</span><div class="tr"><i style="width:' + Math.max(3, Math.round(c / max * 100)) + '%"></i></div><span class="n">' + c + ' 处</span></div>').join('');
    if (dels) h += (h ? '<div class="sep"></div>' : '') + '<div class="bar"><span>签名笔迹与 Logo</span><span class="hint">整块删除，表格线和图框线保留</span><span class="n">' + dels + ' 个</span></div>';
    $('sc-bars').innerHTML = h;
    const warns = (sc.errors || []).slice(0, 3);
    if (sc.tangent) warns.push(sc.tangent + ' 张图含天正对象，里面的文字可能处理不到，完成后会提示');
    $('sc-warn').hidden = !warns.length; $('sc-warn').innerHTML = warns.map(esc).join('<br>');
    const okFiles = sc.files - (sc.errors || []).length;
    $('b-apply').textContent = total || dels ? '脱敏 ' + okFiles + ' 张图纸' : '清理 ' + okFiles + ' 张图纸的文件属性';
    $('b-apply').disabled = okFiles <= 0;
    $('b-review').hidden = !T.length;
  }

  // ---------- ③ 逐项核对 ----------
  function visible() {
    return S.terms.filter(t => (S.tab === 'all' || groupOf(t.cat) === S.tab) && (!S.q || t.term.toLowerCase().includes(S.q) || String(t.replace).toLowerCase().includes(S.q)));
  }
  function renderReview(keepList) {
    const T = S.terms;
    $('rv-title').textContent = '核对 ' + T.reduce((a, t) => a + t.count, 0) + ' 处敏感信息';
    $('rv-tabs').innerHTML = [['all', '全部', T.length]].concat(GROUPS.map(g => [g[0], g[1].replace('名称与地址', '与地址').replace('名称', '').replace('姓名', '').replace('电话与证件号', '电话与证件'), T.filter(t => g[2].includes(t.cat)).length]))
      .filter(x => x[0] === 'all' || x[2]).map(([k, n, c]) => '<button type="button" data-tab="' + k + '" aria-pressed="' + (S.tab === k) + '">' + esc(n) + ' ' + c + '</button>').join('');
    if (!keepList) {
      const V = visible();
      $('rv-list').innerHTML = V.length ? V.map(t => {
        const i = T.indexOf(t), nf = (t.files || []).length;
        return '<label class="row' + (t.enabled ? '' : ' off') + '"><input type="checkbox" data-en="' + i + '"' + (t.enabled ? ' checked' : '') + ' aria-label="替换 ' + esc(t.term) + '">' +
          '<span class="t" title="' + esc(t.term) + '">' + esc(t.term) + (t.warn ? '<small>' + esc(t.warn) + '</small>' : '') + '</span>' +
          '<span class="code">→<input type="text" data-rep="' + i + '" value="' + esc(t.enabled ? t.replace : '保留') + '"' + (t.enabled ? '' : ' disabled') + ' aria-label="' + esc(t.term) + ' 替换为"></span>' +
          '<span class="why">' + esc(t.rule) + ' · ' + (nf > 1 ? nf + ' 张图' : t.count + ' 处') + '</span></label>';
      }).join('') : '<div class="empty">没有符合条件的项</div>';
    }
    const on = T.filter(t => t.enabled);
    $('rv-sum').textContent = '替换 ' + on.reduce((a, t) => a + t.count, 0) + ' 处 · 保留 ' + (T.length - on.length) + ' 项';
    $('b-apply2').textContent = $('b-apply').textContent;
  }

  // ---------- 执行 ----------
  async function apply() {
    const d = {};
    S.terms.forEach(t => { d[t.term] = { enabled: t.enabled, replace: t.replace }; });
    S.busyKind = 'apply'; $('busy-title').textContent = '正在脱敏'; $('busy-line').textContent = '';
    show('busy');
    try { await bridge('apply', d); } catch (e) { toast(String(e.message || e)); show('scan'); }
  }

  // ---------- ④ 完成 ----------
  function renderDone() {
    const R = S.result, F = R.files;
    const bad = F.filter(f => f.error || !f.geometry_ok || f.residual.length);
    const bin = F.filter(f => !f.error && f.binary_residual.length);
    const allOk = !bad.length;
    $('dn-icon').innerHTML = allOk && !bin.length ? OK_ICON : WARN_ICON;
    const okN = F.length - bad.length;
    $('dn-title').textContent = allOk ? F.length + ' 张图纸已脱敏' : okN + ' 张已完成，' + bad.length + ' 张需要看一下';
    const s = S.st.settings;
    $('dn-sub').textContent = s.output_mode === 'fixed' && s.output_dir ? '保存在 ' + s.output_dir : '保存在原文件旁的「脱敏输出」文件夹';
    const chg = S.terms.filter(t => t.enabled).reduce((a, t) => a + t.count, 0);
    const dels = Object.values((S.scan && S.scan.deleted) || {}).reduce((a, b) => a + b, 0);
    const geo = F.filter(f => f.geometry_ok).length, res = F.reduce((a, f) => a + f.residual.length, 0);
    const line = (cls, mark, text, val) => '<div class="' + cls + '"><span><span class="' + (cls || 'g') + '">' + mark + '</span>&nbsp; ' + esc(text) + '</span><span>' + esc(val) + '</span></div>';
    let h = line('', '✓', '替换敏感信息', chg + ' 处');
    if (dels) h += line('', '✓', '删除签名笔迹与 Logo', dels + ' 个图形');
    h += geo === F.length ? line('', '✓', '坐标、尺寸、标注与原图一致', geo + ' / ' + F.length) : line('b', '✗', '几何校验未通过', (F.length - geo) + ' 张');
    h += res ? line('b', '✗', '仍有残留文字', res + ' 处') : line('', '✓', '复查残留文字', '0 处');
    if (bin.length) h += line('w', '!', '天正对象里仍有原文', bin.length + ' 张');
    $('dn-checks').innerHTML = h;
    const iss = [];
    F.forEach(f => {
      const nm = (f.output || f.rel).split(/[\\/]/).pop();
      if (f.error) iss.push(nm + '：' + f.error);
      else if (!f.geometry_ok) iss.push(nm + '：' + f.geometry);
      if (f.residual.length) iss.push(nm + ' 仍有：' + f.residual.join('、'));
      if (f.binary_residual.length) iss.push(nm + ' 的天正对象里仍有：' + f.binary_residual.join('、') + '。建议在天正里“图纸导出”为 T3 后再处理一次');
    });
    $('dn-issues').hidden = !iss.length; $('dn-issues').innerHTML = iss.map(x => '<li>' + esc(x) + '</li>').join('');
    $('b-show').textContent = '在' + finder() + '中显示';
    $('b-show').disabled = !F.some(f => f.output);
  }

  // ---------- 设置 ----------
  function sw(id, on, dis) { return '<input type="checkbox" class="switch" id="' + id + '"' + (on ? ' checked' : '') + (dis ? ' disabled' : '') + '>'; }
  function renderSettings() {
    const st = S.st, s = st.settings, p = presetOf(s.options);
    const open = new Set([...document.querySelectorAll('#v-set details[open]')].map(d => d.id));
    const groups = {};
    st.options.forEach(o => (groups[o[2]] = groups[o[2]] || []).push(o));
    const sel = (id, opts, v) => '<select id="' + id + '">' + opts.map(([k, n]) => '<option value="' + k + '"' + (k === v ? ' selected' : '') + '>' + esc(n) + '</option>').join('') + '</select>';
    let h = '<h1>设置</h1>';
    h += '<section><h2>脱敏程度</h2><div class="presets">' + PRESETS.map(([k, n, d]) =>
      '<button type="button" data-preset="' + k + '" aria-pressed="' + (p === k) + '"><b>' + n + '</b><span>' + d + '</span></button>').join('') + '</div>' +
      (p === 'custom' ? '<p class="muted" style="font-size:12px;margin:8px 0 0">当前是自定义规则，在下方“详细规则”里调整</p>' : '') + '</section>';
    h += '<section class="rows">';
    h += '<div class="srow"><div class="l">脱敏后的图纸放在' + (s.output_mode === 'fixed' ? '<small class="mono">' + esc(s.output_dir || '还没有选择文件夹') + '</small>' : '') + '</div><div class="r">' +
      (s.output_mode === 'fixed' ? '<button type="button" class="btn" id="s-outdir">更改…</button>' : '') + sel('s-outmode', [['beside', '原文件旁「脱敏输出」'], ['fixed', '指定的文件夹']], s.output_mode === 'fixed' ? 'fixed' : 'beside') + '</div></div>';
    h += '<div class="srow"><div class="l">输出格式</div><div class="r">' + sel('s-format', [['same', '和原文件相同'], ['dxf', '都存为 DXF'], ['dwg', '都存为 DWG']], s.output_format || 'same') +
      sel('s-dwgver', [['same', 'DWG 与原图相同']].concat(['ACAD2018', 'ACAD2013', 'ACAD2010', 'ACAD2007', 'ACAD2004', 'ACAD2000'].map(v => [v, 'DWG ' + v.slice(4)])), s.dwg_version || 'same') + '</div></div>';
    h += '<div class="srow"><div class="l">DWG 转换器<small>' + (st.oda ? '<span class="dot">●</span> ODA ' + esc(st.odaVersion) + ' 已连接，DWG 按所选版本原样写回' :
        st.libredwg ? '<span class="dot warn">●</span> 正在用内置 LibreDWG：只能写 DWG 2000，复杂图纸可能有偏差。装上免费的 ODA File Converter 质量更好' :
        '<span class="dot bad">●</span> 没找到。免费下载 ODA File Converter，装好后点“检测”') + '</small></div><div class="r">' +
      (st.oda ? '' : '<button type="button" class="btn" id="s-odadl">下载 ODA</button>') +
      '<button type="button" class="btn" id="s-odapick">浏览…</button><button type="button" class="btn" id="s-odadetect">检测</button></div></div>';
    h += '<label class="srow"><span class="l">同一个人在每批图纸里用同一个代号<small>关掉后，每批图纸从 人员01 重新编号</small></span>' + sw('s-reuse', s.reuse_mapping) + '</label>';
    h += '<div class="srow"><div class="l">监视文件夹<small class="mono">' + (s.watch_dir ? esc(s.watch_dir) + ' → ' + esc(s.watch_out_dir || '已脱敏') : '放进去的图纸会自动脱敏') + '</small></div><div class="r">' +
      '<button type="button" class="btn" id="s-watchdir">' + (s.watch_dir ? '更改…' : '选择…') + '</button>' + sw('s-watch', s.watch_enabled && s.watch_dir, !s.watch_dir) + '</div></div>';
    h += '<label class="srow"><span class="l">处理完自动在' + finder() + '中显示</span>' + sw('s-reveal', s.reveal_after) + '</label>';
    h += '</section><section class="rows">';
    h += '<details id="d-rules"' + (open.has('d-rules') ? ' open' : '') + '><summary>详细规则</summary><div class="dbody">' + Object.keys(groups).map(g =>
      '<div class="optgroup">' + esc(g) + '</div>' + groups[g].map(o => '<label class="opt"><input type="checkbox" data-o="' + o[0] + '"' + (s.options[o[0]] ? ' checked' : '') + '><span>' + esc(o[3]) + '</span></label>').join('')).join('') + '</div></details>';
    h += '<details id="d-words"' + (open.has('d-words') ? ' open' : '') + '><summary>自定义敏感词与白名单<span class="muted" style="margin-left:auto;margin-right:10px;font-size:13px">' + (s.keywords || []).length + ' 个词</span></summary><div class="dbody">' +
      '<div class="optgroup">自定义敏感词：一行一个，可写成 原词=替换词，re: 开头为正则</div><textarea id="s-kw">' + esc((s.keywords || []).join('\n')) + '</textarea>' +
      '<div class="optgroup">白名单：这些词永远不替换</div><textarea id="s-wl">' + esc((s.whitelist || []).join('\n')) + '</textarea></div></details>';
    h += '<details id="d-adv"' + (open.has('d-adv') ? ' open' : '') + '><summary>代号格式与报告</summary><div class="dbody">' +
      '<div class="optgroup">代号格式（{n:02d} 表示两位编号）</div><div class="codes">' + Object.entries(st.cats).filter(([k]) => k !== 'coord').map(([k, n]) =>
        '<label>' + esc(n) + '<input class="field" data-code="' + k + '" value="' + esc(s.pseudonyms[k] || '') + '"></label>').join('') + '</div>' +
      '<div class="codes"><label>文件名后缀<input class="field" id="s-suffix" value="' + esc(s.output_suffix || '_脱敏') + '"></label><label>签名 / 印章图块的块名规则<input class="field mono" id="s-sig" value="' + esc(s.signature_block_pattern || '') + '"></label></div>' +
      '<div class="srow"><div class="l">报告与代号对照表（含原文）<small class="mono">' + esc(s.report_dir) + '</small></div><div class="r"><button type="button" class="btn" id="s-repdir">更改…</button></div></div>' +
      '<div class="srow"><div class="l">代号库<small>导出所有批次用过的代号，内部留存</small></div><div class="r"><button type="button" class="btn" id="s-export">导出</button></div></div>' +
      '<div class="srow"><div class="l muted" style="font-size:12px">图隐 DrawVeil ' + esc(st.version) + '</div><div class="r"><button type="button" class="btn" id="s-reset">恢复默认设置</button></div></div>' +
      '</div></details></section>';
    $('v-set').innerHTML = h;
  }
  async function save(part, rerender) {
    S.st = await call('save_settings', part);
    if (rerender !== false) renderSettings();
    renderFoot();
  }
  async function pickDir() {
    if (native) return await call('pick_folder');
    return await ask('选择文件夹', '浏览器模式下请输入文件夹路径', '');
  }

  // ---------- 轮询 ----------
  async function poll() {
    try {
      const p = await bridge('poll', S.seq);
      S.seq = p.seq;
      if (p.logs.length) $('busy-line').textContent = p.logs[p.logs.length - 1].text.trim();
      const j = p.job;
      if (S.lastJob === null) S.lastJob = j && j.status !== 'running' ? j.id + j.status : '';
      if (j && j.status === 'running' && (j.kind === 'scan' || j.kind === 'apply') && S.view !== 'busy') {
        S.busyKind = j.kind; $('busy-title').textContent = j.kind === 'scan' ? '正在扫描' : '正在脱敏'; show('busy');
      }
      // 拖进来的不是图纸等情况：没有任务开始，就回到首页
      if (S.view === 'busy' && Date.now() - S.busyAt > 4000 && !(j && j.status === 'running') && S.lastJob === (j ? j.id + j.status : '')) {
        show('drop'); toast('没有找到 DWG / DXF 图纸');
      }
      if (j && j.status !== 'running' && S.lastJob !== j.id + j.status) {
        S.lastJob = j.id + j.status;
        if (j.status === 'error') {
          toast((j.kind === 'apply' ? '脱敏' : j.kind === 'scan' ? '扫描' : '自动脱敏') + '出错：' + j.error);
          if (S.view === 'busy') show(j.kind === 'apply' ? 'scan' : 'drop');
        } else if (j.kind === 'scan') {
          S.scan = Object.assign({}, j.result, { seconds: j.seconds || Math.max(0.1, (Date.now() - S.busyAt) / 1000).toFixed(1) });
          S.scan.tangent = p.files.filter(f => (f.notes || []).some(n => /天正/.test(n))).length;
          S.terms = j.result.terms.map(t => Object.assign({}, t));
          S.tab = 'all'; S.q = ''; $('rv-q').value = '';
          renderScan(); show('scan');
        } else if (j.kind === 'apply') {
          S.result = j.result; renderDone(); show('done');
        } else if (j.kind === 'watch') {
          const r = j.result || {};
          toast('监视文件夹：已自动脱敏 ' + (r.ok || 0) + ' / ' + (r.total || 0) + ' 张图纸');
        }
        S.st = await bridge('get_state');
      }
    } catch (e) { /* 窗口关闭中 */ }
    setTimeout(poll, 600);
  }

  // ---------- 事件 ----------
  function bind() {
    $('b-ring').onclick = () => pick(false);
    $('b-pick').onclick = () => pick(false);
    $('b-pickdir').onclick = () => pick(true);
    $('b-back').onclick = goBack;
    $('b-theme').onclick = () => { const t = curTheme() === 'dark' ? 'light' : 'dark'; setTheme(t); bridge('save_settings', { theme: t }).then(st => { S.st = st; }).catch(() => {}); };
    $('b-gear').onclick = () => { renderSettings(); show('set'); };
    $('foot').onclick = (e) => { if (e.target.closest('[data-set]')) { renderSettings(); show('set'); } };
    $('b-apply').onclick = apply; $('b-apply2').onclick = apply;
    $('b-review').onclick = () => { renderReview(); show('review'); };
    $('rv-tabs').onclick = (e) => { const b = e.target.closest('[data-tab]'); if (b) { S.tab = b.dataset.tab; renderReview(); } };
    $('rv-q').oninput = (e) => { S.q = e.target.value.trim().toLowerCase(); renderReview(); };
    $('rv-list').onchange = (e) => {
      const en = e.target.dataset.en;
      if (en !== undefined) { S.terms[+en].enabled = e.target.checked; renderReview(); }
    };
    $('rv-list').oninput = (e) => { const r = e.target.dataset.rep; if (r !== undefined) { S.terms[+r].replace = e.target.value; } };
    $('b-show').onclick = () => { const f = S.result.files.find(x => x.output); if (f) call('reveal', f.output); };
    $('b-report').onclick = () => call('open_path', S.result.report_html);
    $('b-again').onclick = () => show('drop');
    // 设置
    const set = $('v-set');
    set.onclick = async (e) => {
      const pb = e.target.closest('[data-preset]');
      if (pb) {
        const v = pb.dataset.preset, def = S.st.defaults.options, o = {};
        Object.keys(def).forEach(k => { o[k] = v === 'standard' ? def[k] : v === 'strict' ? true : META_ONLY.includes(k); });
        return save({ options: o, preset: v });
      }
      const id = e.target.id;
      if (id === 's-outdir' || id === 's-repdir') {
        const d = await pickDir(); if (d) save(id === 's-outdir' ? { output_dir: d, output_mode: 'fixed' } : { report_dir: d });
      } else if (id === 's-watchdir') {
        const d = await pickDir(); if (d) save({ watch_dir: d, watch_enabled: true });
      } else if (id === 's-odadl') {
        await call('open_oda_download');
      } else if (id === 's-odapick' || id === 's-odadetect') {
        let path = S.st.settings.oda_converter || '';
        if (id === 's-odapick') { path = native ? await call('pick_oda') : await ask('ODA File Converter', '输入程序路径', path); if (!path) return; }
        const r = await call('detect_oda', path);
        S.st = await call('save_settings', { oda_converter: r.path || path });
        renderSettings(); renderFoot();
        toast(r.path ? '已连接 ODA File Converter ' + (r.version || '') : '没有找到 ODA File Converter');
      } else if (id === 's-export') {
        await call('export_mapping'); toast('代号库已导出到报告文件夹');
      } else if (id === 's-reset') {
        if (await ask('恢复默认设置', '所有设置都会回到初始值，已经处理过的图纸不受影响。')) { S.st = await call('reset_settings'); setTheme(S.st.settings.theme); renderSettings(); renderFoot(); }
      }
    };
    set.onchange = async (e) => {
      const t = e.target, s = S.st.settings;
      if (t.dataset.o) { const o = Object.assign({}, s.options, { [t.dataset.o]: t.checked }); return save({ options: o, preset: presetOf(o) }); }
      if (t.dataset.code) { const ps = Object.assign({}, s.pseudonyms); if (t.value.trim()) ps[t.dataset.code] = t.value.trim(); return save({ pseudonyms: ps }, false); }
      const lines = (v) => v.split('\n').map(x => x.trim()).filter(Boolean);
      switch (t.id) {
        case 's-outmode':
          if (t.value === 'fixed' && !s.output_dir) { const d = await pickDir(); if (!d) { t.value = 'beside'; return; } return save({ output_mode: 'fixed', output_dir: d }); }
          return save({ output_mode: t.value });
        case 's-format': return save({ output_format: t.value }, false);
        case 's-dwgver': return save({ dwg_version: t.value }, false);
        case 's-reuse': return save({ reuse_mapping: t.checked }, false);
        case 's-watch': return save({ watch_enabled: t.checked }, false);
        case 's-reveal': return save({ reveal_after: t.checked }, false);
        case 's-kw': return save({ keywords: lines(t.value) });
        case 's-wl': return save({ whitelist: lines(t.value) }, false);
        case 's-suffix': return save({ output_suffix: t.value.trim() || '_脱敏' }, false);
        case 's-sig': return save({ signature_block_pattern: t.value }, false);
      }
    };
    // 键盘
    document.addEventListener('keydown', (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === ',') { e.preventDefault(); renderSettings(); show('set'); }
      else if (mod && e.key.toLowerCase() === 'o' && (S.view === 'drop' || S.view === 'done')) { e.preventDefault(); pick(false); }
      else if (e.key === 'Escape' && $('modal').hidden) goBack();
    });
    // 拖放：原生窗口里由 Python 读取完整路径并开始扫描
    let depth = 0;
    document.addEventListener('dragenter', (e) => { e.preventDefault(); depth++; if (S.view === 'drop' || S.view === 'done') document.body.classList.add('dragging'); });
    document.addEventListener('dragover', (e) => e.preventDefault());
    document.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; document.body.classList.remove('dragging'); } });
    document.addEventListener('drop', (e) => {
      e.preventDefault(); depth = 0; document.body.classList.remove('dragging');
      if (!native) toast('浏览器模式下不能拖放，请点“选择图纸”输入路径');
      else if (S.view === 'drop' || S.view === 'done') { S.busyKind = 'scan'; $('busy-title').textContent = '正在扫描'; $('busy-line').textContent = ''; show('busy'); }
    });
  }

  async function startApp() {
    bind();
    S.st = await bridge('get_state');
    setTheme(S.st.settings.theme);
    document.body.className = 'plat-' + (FORCE || S.st.platform) + (native ? ' native' : '');
    show('drop');
    poll();
  }
  let started = false;
  const go = () => { if (!started) { started = true; startApp(); } };
  if (/mode=browser/.test(location.search)) go();
  else if (window.pywebview && window.pywebview.api) { native = true; go(); }
  else window.addEventListener('pywebviewready', () => { native = true; go(); });
})();
