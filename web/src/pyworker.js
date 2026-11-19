/* 图隐 DrawVeil · 在浏览器后台线程里运行 Python 脱敏引擎（Pyodide），图纸只在本机内存中处理 */
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.2/full/';
importScripts(PYODIDE + 'pyodide.js');
let py = null, E = null, samplesSrc = '';
const say = (text) => postMessage({ type: 'log', text: String(text) });

const ready = (async () => {
  say('正在加载脱敏引擎（首次约 10MB，之后会被浏览器缓存）…');
  py = await loadPyodide({ indexURL: PYODIDE, stdout: say, stderr: say });
  const v = self.location.search || '';
  const [eng, smp] = await Promise.all([
    fetch('/engine.py' + v).then(r => { if (!r.ok) throw new Error('引擎下载失败 ' + r.status); return r.text(); }),
    fetch('/samples.py' + v).then(r => r.ok ? r.text() : '')
  ]);
  samplesSrc = smp;
  py.FS.mkdirTree('/home/pyodide');
  py.FS.writeFile('/home/pyodide/drawveil_engine.py', eng);
  py.runPython('import sys\nsys.path.insert(0, "/home/pyodide")\nimport drawveil_engine as E');
  E = py.globals.get('E');
  postMessage({ type: 'ready' });
})().catch(e => { postMessage({ type: 'fatal', error: String(e && e.message || e) }); throw e; });

function writeInputs(files) {
  E.web_reset();
  for (const f of files) py.FS.writeFile('/drawveil/in/' + f.name, new Uint8Array(f.data));
}

onmessage = async (ev) => {
  const { id, cmd, args } = ev.data;
  try {
    await ready;
    let result, transfer = [];
    if (cmd === 'samples') {
      E.web_reset();
      const names = JSON.parse(E.web_samples(samplesSrc));
      result = names.map(n => {
        const d = py.FS.readFile('/drawveil/in/' + n);
        transfer.push(d.buffer);
        return { name: n, data: d.buffer };
      });
    } else if (cmd === 'scan') {
      writeInputs(args.files);
      result = JSON.parse(E.web_scan(JSON.stringify(args.config), say));
    } else if (cmd === 'apply') {
      writeInputs(args.files);
      result = JSON.parse(E.web_apply(JSON.stringify(args.config), JSON.stringify(args.decisions), say));
      const read = (p) => { const d = py.FS.readFile(p); transfer.push(d.buffer); return d.buffer; };
      result.drawingsZip = read('/drawveil/drawings.zip');
      result.reportZip = read('/drawveil/report.zip');
      result.reportHtml = py.FS.readFile(result.report_html, { encoding: 'utf8' });
      result.outputFiles = result.outputs.map(n => ({ name: n, data: read('/drawveil/out/' + n) }));
    } else {
      throw new Error('未知命令 ' + cmd);
    }
    postMessage({ type: 'result', id, result }, transfer);
  } catch (e) {
    postMessage({ type: 'error', id, error: String(e && e.message || e) });
  }
};
