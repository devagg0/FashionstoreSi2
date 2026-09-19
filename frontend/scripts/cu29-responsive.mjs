// Run after a production build: node scripts/cu29-responsive.mjs
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
const profile = await mkdtemp(join(tmpdir(), 'fashionstore-cu29-'));
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
  const kpis = { total_productos: 1, total_variantes: 1, total_registros_inventario: 1, unidades_actuales: 5, unidades_reservadas: 7, unidades_disponibles: -2, registros_agotados: 0, registros_bajo_stock: 0, productos_con_agotados: 0, productos_con_bajo_stock: 0, registros_con_stock_minimo_cero: 0 };
  const named = { nombre: 'Nombre extenso para comprobar el formato responsive', estado: false };
  const data = { generado_en: '2026-09-19T00:00:00Z', filtros: { estado_stock: null }, kpis, por_sucursal: [{ ...kpis, ...named, id_sucursal: 1 }], por_categoria: [{ ...kpis, ...named, id_categoria: 1 }], detalle: { pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 }, items: [{ id_inventario_sucursal: 1, sucursal: { ...named, id_sucursal: 1 }, categoria: { ...named, id_categoria: 1 }, producto: { ...named, id_producto: 1 }, variante: { sku: 'SKU-LARGO-123456', talla: 'M', color: 'Azul', estado: false }, stock_actual: 5, stock_reservado: 7, stock_disponible: -2, stock_minimo: 3, estado_stock: null, faltante_hasta_minimo: 5 }] }, advertencias: [{ codigo: 'STOCK_DISPONIBLE_NEGATIVO', mensaje: 'Se conserva el saldo real.', registros: 1, alcance: 'FILTROS_SIN_ESTADO_STOCK' }] };
  socket.addEventListener('message', async event => {
    const message = JSON.parse(event.data);
    if (message.id) { const p = pending.get(message.id); pending.delete(message.id); message.error ? p.reject(message.error) : p.resolve(message.result); }
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      const body = request.url.endsWith('/branches') || request.url.includes('/branches?') || request.url.includes('/categories?') || request.url.includes('/products?')
        ? { success: true, data: [], pagination: { page: 1, total_pages: 0 } } : { success: true, data };
      await send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: origin }, { name: 'Access-Control-Allow-Headers', value: 'authorization,content-type' }], body: Buffer.from(JSON.stringify(body)).toString('base64') });
    }
  });
  await send('Page.enable');
  await send('Fetch.enable', { patterns: [{ urlPattern: '*fashionstoresi2.onrender.com*' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fashionstore_access_token','responsive-test'); localStorage.setItem('fashionstore_user',JSON.stringify({id_usuario:1,nombre:'Test',apellido:'Admin',correo:'test@example.invalid',rol:'ADMINISTRADOR'}));` });
  await send('Page.navigate', { url: origin + '/admin/reporte-inventario' });
  const evaluate = async expression => (await send('Runtime.evaluate', { expression, returnByValue: true })).result.value;
  for (let i = 0; i < 100 && !(await evaluate("document.querySelectorAll('.kpi').length === 10")); i++) await new Promise(r => setTimeout(r, 100));
  assert.equal(await evaluate("document.querySelectorAll('.kpi').length"), 10, 'Report must render');
  for (const width of [1440, 768, 390, 320]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    await new Promise(r => setTimeout(r, 150));
    const metrics = await evaluate(`(() => {
      const report = document.querySelector('.inventory-report');
      const bad = [...report.querySelectorAll('*')].filter(e => !e.closest('.table-scroll') && !e.classList.contains('visually-hidden') && e.getBoundingClientRect().width > 1 && e.scrollWidth > e.clientWidth + 2);
      return { width: innerWidth, columns: getComputedStyle(document.querySelector('.kpi-grid')).gridTemplateColumns.split(' ').length, overflow: bad.map(e => e.tagName + '.' + e.className), charts: document.querySelectorAll('.chart').length };
    })()`);
    assert.deepEqual(metrics.overflow, [], JSON.stringify(metrics));
    assert.equal(metrics.columns, width <= 640 ? 1 : width <= 1100 ? 3 : 5);
    assert.equal(metrics.charts, 3);
    console.log(`PASS responsive ${width}px: ${metrics.columns} KPI columns, no horizontal overflow`);
  }
  await send('Browser.close');
} finally {
  socket?.close(); browser.kill(); server.close();
  await new Promise(r => setTimeout(r, 500));
  assert(resolve(profile).startsWith(resolve(tmpdir()) + sep + 'fashionstore-cu29-'));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
}
