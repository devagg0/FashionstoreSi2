// Run after a production build: node scripts/cu30-responsive.mjs
// Uses installed Chrome/Edge and isolated mocked API responses, without dependencies.
import { createServer } from 'node:http';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, extname, sep } from 'node:path';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';

const browserPath = process.env.CHROME_PATH ?? ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
assert(browserPath, 'Set CHROME_PATH to a Chromium browser executable');
const root = resolve('dist/frontend/browser');
const server = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const file = pathname.includes('.') ? resolve(root, '.' + pathname) : join(root, 'index.html');
    if (!file.startsWith(root + sep)) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' })[extname(file)] ?? 'application/octet-stream');
    res.end(await readFile(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), 'fashionstore-cu30-'));
const browser = spawn(browserPath, ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch { await new Promise(r => setTimeout(r, 100)); }
  }
  assert(port, 'Browser debugging port unavailable');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => socket.addEventListener('open', r, { once: true }));
  let id = 0;
  const pending = new Map();
  const send = (method, params = {}) => new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
  const long = 'Nombre extenso para comprobar el formato responsive del reporte';
  const data = {
    zona_horaria: 'America/La_Paz', generado_en: '2026-09-19T12:00:00Z', criterio_estado: 'PERSISTIDO',
    filtros: { tipo_fecha: 'CREACION', periodo: 'DIA' },
    kpis: { total_reservas: 18, unidades_reservadas: 44, reservas_pendientes: 4, reservas_confirmadas: 3, reservas_atendidas: 8, reservas_canceladas: 2, reservas_expiradas: 1, clientes_con_reservas: 9 },
    por_estado: [
      { estado: 'PENDIENTE', total_reservas: 4, unidades_reservadas: 9 }, { estado: 'CONFIRMADA', total_reservas: 3, unidades_reservadas: 7 },
      { estado: 'ATENDIDA', total_reservas: 8, unidades_reservadas: 21 }, { estado: 'CANCELADA', total_reservas: 2, unidades_reservadas: 5 },
      { estado: 'EXPIRADA', total_reservas: 1, unidades_reservadas: 2 },
    ],
    por_sucursal: [{ id_sucursal: 1, nombre_sucursal: long, total_reservas: 12, unidades_reservadas: 30, clientes_con_reservas: 6 },
                   { id_sucursal: 2, nombre_sucursal: 'Norte', total_reservas: 6, unidades_reservadas: 14, clientes_con_reservas: 3 }],
    serie_periodica: Array.from({ length: 12 }, (_, i) => ({ inicio_periodo: `2026-09-${String(i + 1).padStart(2, '0')}`, total_reservas: i % 5, unidades_reservadas: (i % 4) + 1 })),
    productos_mas_reservados: [{ id_producto: 1, nombre_producto: long, total_reservas: 9, unidades_reservadas: 22 }, { id_producto: 2, nombre_producto: 'Camisa', total_reservas: 5, unidades_reservadas: 11 }],
    categorias_mas_reservadas: [{ id_categoria: 1, nombre_categoria: long, total_reservas: 11, unidades_reservadas: 28 }, { id_categoria: 2, nombre_categoria: 'Accesorios', total_reservas: 7, unidades_reservadas: 16 }],
    advertencias: { reservas_vencidas_sin_actualizar: 2 },
  };
  socket.addEventListener('message', async event => {
    const message = JSON.parse(event.data);
    if (message.id) { const p = pending.get(message.id); pending.delete(message.id); message.error ? p.reject(message.error) : p.resolve(message.result); }
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      const body = /\/(branches|categories|products)(\?|$)/.test(request.url)
        ? { success: true, data: [], pagination: { page: 1, total_pages: 0 } } : { success: true, data };
      await send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: origin }, { name: 'Access-Control-Allow-Headers', value: 'authorization,content-type' }], body: Buffer.from(JSON.stringify(body)).toString('base64') });
    }
  });
  await send('Page.enable');
  await send('Fetch.enable', { patterns: [{ urlPattern: '*fashionstoresi2.onrender.com*' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fashionstore_access_token','responsive-test'); localStorage.setItem('fashionstore_user',JSON.stringify({id_usuario:1,nombre:'Test',apellido:'Admin',correo:'test@example.invalid',rol:'ADMINISTRADOR'}));` });
  await send('Page.navigate', { url: origin + '/admin/reporte-reservas' });
  const evaluate = async expression => (await send('Runtime.evaluate', { expression, returnByValue: true })).result.value;
  for (let i = 0; i < 100 && !(await evaluate("document.querySelectorAll('.kpi').length === 8")); i++) await new Promise(r => setTimeout(r, 100));
  assert.equal(await evaluate("document.querySelectorAll('.kpi').length"), 8, 'Report must render');
  assert.equal(await evaluate("document.querySelectorAll('.warning').length"), 1, 'Expired reservations warning must render');
  assert.equal(await evaluate("document.querySelector('.admin-layout, aside, nav').textContent.includes('Reporte de reservas')"), true, 'Menu entry must exist');
  for (const width of [1440, 768, 390, 320]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    await new Promise(r => setTimeout(r, 200));
    const metrics = await evaluate(`(() => {
      const report = document.querySelector('.reservations-report');
      const bad = [...report.querySelectorAll('*')].filter(e => !e.closest('.table-scroll, .bars, .legend') && !e.classList.contains('visually-hidden') && e.getBoundingClientRect().width > 1 && e.scrollWidth > e.clientWidth + 2);
      const donut = document.querySelector('.donut-holder').getBoundingClientRect();
      const card = document.querySelector('.chart--donut').getBoundingClientRect();
      return {
        width: innerWidth,
        pageOverflow: document.documentElement.scrollWidth > innerWidth + 2,
        columns: getComputedStyle(document.querySelector('.kpi-grid')).gridTemplateColumns.split(' ').length,
        chartColumns: getComputedStyle(document.querySelector('.chart-grid')).gridTemplateColumns.split(' ').length,
        charts: document.querySelectorAll('.chart').length,
        donutCentered: Math.abs((donut.left + donut.right) / 2 - (card.left + card.right) / 2) < 12,
        donutHeight: Math.round(donut.height),
        overflow: bad.map(e => e.tagName + '.' + e.className),
      };
    })()`);
    assert.deepEqual(metrics.overflow, [], JSON.stringify(metrics));
    assert.equal(metrics.pageOverflow, false, `Page must not scroll horizontally at ${width}px`);
    assert.equal(metrics.columns, width <= 640 ? 1 : width <= 1100 ? 2 : 4);
    assert.equal(metrics.chartColumns, width <= 1100 ? 1 : 2);
    assert.equal(metrics.charts, 5);
    if (width <= 1100) assert.equal(metrics.donutCentered, true, `Donut must be centered at ${width}px`);
    assert.ok(metrics.donutHeight > 120, `Donut needs a readable height at ${width}px`);
    console.log(`PASS responsive ${width}px: ${metrics.columns} KPI columns, ${metrics.chartColumns} chart columns, donut ${metrics.donutHeight}px, no horizontal overflow`);
  }
  await send('Browser.close');
} finally {
  socket?.close(); browser.kill(); server.close();
  await new Promise(r => setTimeout(r, 500));
  assert(resolve(profile).startsWith(resolve(tmpdir()) + sep + 'fashionstore-cu30-'));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
}
