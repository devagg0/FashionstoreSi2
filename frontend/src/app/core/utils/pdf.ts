/**
 * Generador de PDF sin dependencias externas.
 * Emite documentos de texto (PDF 1.4, fuentes base-14 Helvetica con WinAnsiEncoding)
 * a partir de los datos ya cargados en el navegador; no realiza peticiones de red.
 */

export interface PdfColumn {
  header: string;
  /** Peso relativo de la columna; se normaliza sobre el ancho util de la pagina. */
  width: number;
  align?: 'left' | 'right';
}
export interface PdfTable {
  columns: PdfColumn[];
  rows: string[][];
  empty?: string;
}
export interface PdfEntry {
  label: string;
  value: string;
}
export interface PdfSection {
  heading: string;
  description?: string;
  kpis?: PdfEntry[];
  table?: PdfTable;
  notes?: string[];
}
export interface PdfReport {
  title: string;
  subtitle?: string;
  meta?: PdfEntry[];
  sections: PdfSection[];
  generatedAt?: Date;
}

type FontName = 'F1' | 'F2';

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN = 42;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;
const BOTTOM_LIMIT = 56;

const ESPRESSO = '0.169 0.149 0.145';
const MUTED = '0.44 0.42 0.41';
const TERRACOTTA = '0.784 0.490 0.333';
const LINEN = '0.957 0.922 0.882';
const LINE = '0.85 0.83 0.82';

const REGULAR_WIDTHS = [
  278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015,
  667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611,
  278, 278, 278, 469, 556, 333,
  556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500,
  334, 260, 334, 584,
];
const BOLD_WIDTHS = [
  278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975,
  722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611,
  333, 278, 333, 584, 556, 333,
  556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500,
  389, 280, 389, 584,
];
/** Anchos de los caracteres WinAnsi frecuentes en castellano. */
const REGULAR_HIGH: Record<number, number> = {
  0x85: 1000, 0x91: 191, 0x92: 191, 0x93: 333, 0x94: 333, 0x95: 350, 0x96: 556, 0x97: 1000,
  0xa1: 333, 0xaa: 370, 0xb0: 400, 0xb7: 278, 0xba: 365, 0xbf: 611,
  0xc1: 667, 0xc9: 667, 0xcd: 278, 0xd1: 722, 0xd3: 778, 0xda: 722, 0xdc: 722,
  0xe1: 556, 0xe7: 500, 0xe9: 556, 0xed: 278, 0xf1: 556, 0xf3: 556, 0xfa: 556, 0xfc: 556,
};
const BOLD_HIGH: Record<number, number> = {
  0x85: 1000, 0x91: 238, 0x92: 238, 0x93: 500, 0x94: 500, 0x95: 350, 0x96: 556, 0x97: 1000,
  0xa1: 333, 0xaa: 370, 0xb0: 400, 0xb7: 278, 0xba: 365, 0xbf: 611,
  0xc1: 722, 0xc9: 667, 0xcd: 278, 0xd1: 722, 0xd3: 778, 0xda: 722, 0xdc: 722,
  0xe1: 556, 0xe7: 556, 0xe9: 556, 0xed: 278, 0xf1: 611, 0xf3: 611, 0xfa: 611, 0xfc: 611,
};
/** Caracteres fuera de Latin-1 que WinAnsi si representa. */
const WIN_ANSI_EXTRA: Record<string, number> = {
  '\u20ac': 0x80, '\u2026': 0x85, '\u2018': 0x91, '\u2019': 0x92,
  '\u201c': 0x93, '\u201d': 0x94, '\u2022': 0x95, '\u2013': 0x96, '\u2014': 0x97,
};

/** Convierte a WinAnsi: cada caracter del resultado equivale a un byte del PDF. */
export function toWinAnsi(text: string): string {
  let out = '';
  for (const char of text) {
    const code = char.codePointAt(0)!;
    if (code <= 0xff) out += String.fromCharCode(code);
    else if (WIN_ANSI_EXTRA[char] !== undefined) out += String.fromCharCode(WIN_ANSI_EXTRA[char]);
    else out += '?';
  }
  return out;
}

function charWidth(code: number, font: FontName): number {
  const widths = font === 'F2' ? BOLD_WIDTHS : REGULAR_WIDTHS;
  if (code >= 32 && code <= 126) return widths[code - 32];
  const high = font === 'F2' ? BOLD_HIGH : REGULAR_HIGH;
  return high[code] ?? (font === 'F2' ? 611 : 556);
}

/** Ancho en puntos de un texto ya convertido a WinAnsi. */
export function textWidth(text: string, font: FontName, size: number): number {
  let total = 0;
  for (let index = 0; index < text.length; index += 1) total += charWidth(text.charCodeAt(index), font);
  return (total * size) / 1000;
}

/** Corta el texto e incorpora puntos suspensivos cuando excede el ancho disponible. */
export function clipText(text: string, font: FontName, size: number, maxWidth: number): string {
  if (textWidth(text, font, size) <= maxWidth) return text;
  const ellipsis = '\u2026';
  let cut = text;
  while (cut.length && textWidth(cut + ellipsis, font, size) > maxWidth) cut = cut.slice(0, -1);
  return cut ? cut + ellipsis : '';
}

/** Reparte el texto en lineas; las palabras mas largas que el ancho se cortan por caracter. */
export function wrapText(text: string, font: FontName, size: number, maxWidth: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split('\n')) {
    let current = '';
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      const candidate = current ? `${current} ${word}` : word;
      if (textWidth(candidate, font, size) <= maxWidth) {
        current = candidate;
        continue;
      }
      if (current) lines.push(current);
      let rest = word;
      while (textWidth(rest, font, size) > maxWidth && rest.length > 1) {
        let head = rest;
        while (head.length > 1 && textWidth(head, font, size) > maxWidth) head = head.slice(0, -1);
        lines.push(head);
        rest = rest.slice(head.length);
      }
      current = rest;
    }
    lines.push(current);
  }
  return lines.length ? lines : [''];
}

function escapePdfText(text: string): string {
  return text.replace(/([\\()])/g, '\\$1').replace(/[\r\n]/g, ' ');
}

interface TextOptions {
  font?: FontName;
  size?: number;
  color?: string;
  align?: 'left' | 'right';
  width?: number;
}

class PdfCanvas {
  private readonly pages: string[][] = [];
  private ops: string[] = [];
  y = PAGE_HEIGHT - MARGIN;

  constructor() {
    this.pages.push(this.ops);
  }

  newPage(): void {
    this.ops = [];
    this.pages.push(this.ops);
    this.y = PAGE_HEIGHT - MARGIN;
  }

  /** Abre una pagina nueva cuando el bloque solicitado no entra en lo que queda. */
  ensure(height: number): void {
    if (this.y - height < BOTTOM_LIMIT) this.newPage();
  }

  text(value: string, x: number, y: number, options: TextOptions = {}): void {
    const font = options.font ?? 'F1';
    const size = options.size ?? 9;
    const encoded = toWinAnsi(value);
    const left = options.align === 'right' && options.width !== undefined
      ? x + options.width - textWidth(encoded, font, size)
      : x;
    this.ops.push(
      'BT',
      `/${font} ${size} Tf`,
      `${options.color ?? ESPRESSO} rg`,
      `1 0 0 1 ${left.toFixed(2)} ${y.toFixed(2)} Tm`,
      `(${escapePdfText(encoded)}) Tj`,
      'ET',
    );
  }

  rect(x: number, y: number, width: number, height: number, color: string): void {
    this.ops.push(
      `${color} rg`,
      `${x.toFixed(2)} ${y.toFixed(2)} ${width.toFixed(2)} ${height.toFixed(2)} re f`,
    );
  }

  line(x1: number, y: number, x2: number, color = LINE, thickness = 0.6): void {
    this.ops.push(
      `${color} RG`, `${thickness} w`,
      `${x1.toFixed(2)} ${y.toFixed(2)} m ${x2.toFixed(2)} ${y.toFixed(2)} l S`,
    );
  }

  /** Escribe el pie en cada pagina, ya conocido el total. */
  finish(footer: string): string[][] {
    const active = this.ops;
    this.pages.forEach((ops, index) => {
      this.ops = ops;
      this.line(MARGIN, BOTTOM_LIMIT - 12, PAGE_WIDTH - MARGIN);
      this.text(footer, MARGIN, BOTTOM_LIMIT - 24, { size: 7.5, color: MUTED });
      this.text(`Pagina ${index + 1} de ${this.pages.length}`, MARGIN, BOTTOM_LIMIT - 24, {
        size: 7.5, color: MUTED, align: 'right', width: CONTENT_WIDTH,
      });
    });
    this.ops = active;
    return this.pages;
  }
}

function formatTimestamp(date: Date): string {
  const formatter = new Intl.DateTimeFormat('es-BO', {
    timeZone: 'America/La_Paz', dateStyle: 'medium', timeStyle: 'short',
  });
  return `${formatter.format(date)} (America/La_Paz)`;
}

function drawHeader(canvas: PdfCanvas, report: PdfReport, generatedAt: Date): void {
  canvas.rect(MARGIN, canvas.y - 4, 46, 4, TERRACOTTA);
  canvas.y -= 30;
  canvas.text(report.title, MARGIN, canvas.y, { font: 'F2', size: 19 });
  canvas.y -= 16;
  if (report.subtitle) {
    for (const line of wrapText(toWinAnsi(report.subtitle), 'F1', 9.5, CONTENT_WIDTH)) {
      canvas.text(line, MARGIN, canvas.y, { size: 9.5, color: MUTED });
      canvas.y -= 13;
    }
  }
  canvas.y -= 6;
  const entries = [...(report.meta ?? []), { label: 'Generado', value: formatTimestamp(generatedAt) }];
  const columnWidth = CONTENT_WIDTH / 2 - 8;
  for (let index = 0; index < entries.length; index += 2) {
    for (const [column, entry] of entries.slice(index, index + 2).entries()) {
      const x = MARGIN + column * (columnWidth + 16);
      const label = `${entry.label}: `;
      canvas.text(label, x, canvas.y, { font: 'F2', size: 8, color: MUTED });
      const offset = textWidth(toWinAnsi(label), 'F2', 8);
      canvas.text(clipText(toWinAnsi(entry.value), 'F1', 8, columnWidth - offset), x + offset, canvas.y, { size: 8 });
    }
    canvas.y -= 12;
  }
  canvas.y -= 6;
  canvas.line(MARGIN, canvas.y, PAGE_WIDTH - MARGIN);
  canvas.y -= 22;
}

function drawKpis(canvas: PdfCanvas, kpis: PdfEntry[]): void {
  const columns = 3;
  const gap = 10;
  const boxWidth = (CONTENT_WIDTH - gap * (columns - 1)) / columns;
  for (let index = 0; index < kpis.length; index += columns) {
    canvas.ensure(48);
    const top = canvas.y;
    for (const [column, kpi] of kpis.slice(index, index + columns).entries()) {
      const x = MARGIN + column * (boxWidth + gap);
      canvas.rect(x, top - 40, boxWidth, 40, LINEN);
      canvas.text(clipText(toWinAnsi(kpi.label), 'F1', 7.5, boxWidth - 16), x + 8, top - 15, { size: 7.5, color: MUTED });
      canvas.text(clipText(toWinAnsi(kpi.value), 'F2', 12, boxWidth - 16), x + 8, top - 31, { font: 'F2', size: 12 });
    }
    canvas.y = top - 40 - gap;
  }
  canvas.y -= 4;
}

function drawTable(canvas: PdfCanvas, table: PdfTable): void {
  const total = table.columns.reduce((sum, column) => sum + column.width, 0) || 1;
  const widths = table.columns.map(column => (column.width / total) * CONTENT_WIDTH);
  const offsets = widths.map((_, index) => MARGIN + widths.slice(0, index).reduce((sum, width) => sum + width, 0));

  const drawHeadings = () => {
    canvas.ensure(24);
    const top = canvas.y;
    canvas.rect(MARGIN, top - 18, CONTENT_WIDTH, 18, LINEN);
    table.columns.forEach((column, index) => {
      const padded = widths[index] - 12;
      canvas.text(clipText(toWinAnsi(column.header), 'F2', 7.5, padded), offsets[index] + 6, top - 12, {
        font: 'F2', size: 7.5, color: MUTED, align: column.align, width: padded,
      });
    });
    canvas.y = top - 18;
  };

  drawHeadings();
  if (!table.rows.length) {
    canvas.y -= 18;
    canvas.text(table.empty ?? 'Sin resultados.', MARGIN + 6, canvas.y + 4, { size: 8, color: MUTED });
    canvas.y -= 8;
    return;
  }

  for (const row of table.rows) {
    const cells = table.columns.map((column, index) => {
      const padded = widths[index] - 12;
      return wrapText(toWinAnsi(row[index] ?? ''), 'F1', 8, padded)
        .slice(0, 2)
        .map(line => clipText(line, 'F1', 8, padded));
    });
    const height = Math.max(...cells.map(lines => lines.length)) * 10 + 8;
    if (canvas.y - height < BOTTOM_LIMIT) {
      canvas.newPage();
      drawHeadings();
    }
    const top = canvas.y;
    cells.forEach((lines, index) => {
      lines.forEach((line, lineIndex) => {
        canvas.text(line, offsets[index] + 6, top - 12 - lineIndex * 10, {
          size: 8, align: table.columns[index].align, width: widths[index] - 12,
        });
      });
    });
    canvas.y = top - height;
    canvas.line(MARGIN, canvas.y, PAGE_WIDTH - MARGIN);
  }
  canvas.y -= 6;
}

function drawSection(canvas: PdfCanvas, section: PdfSection): void {
  canvas.ensure(70);
  canvas.rect(MARGIN, canvas.y - 11, 3, 11, TERRACOTTA);
  canvas.text(section.heading, MARGIN + 9, canvas.y - 9, { font: 'F2', size: 11.5 });
  canvas.y -= 24;
  if (section.description) {
    for (const line of wrapText(toWinAnsi(section.description), 'F1', 8, CONTENT_WIDTH)) {
      canvas.ensure(12);
      canvas.text(line, MARGIN, canvas.y, { size: 8, color: MUTED });
      canvas.y -= 11;
    }
    canvas.y -= 5;
  }
  if (section.kpis?.length) drawKpis(canvas, section.kpis);
  if (section.table) drawTable(canvas, section.table);
  for (const note of section.notes ?? []) {
    wrapText(toWinAnsi(note), 'F1', 8, CONTENT_WIDTH - 12).forEach((line, index) => {
      canvas.ensure(12);
      if (index === 0) canvas.text('\u2022', MARGIN, canvas.y, { size: 8, color: TERRACOTTA });
      canvas.text(line, MARGIN + 12, canvas.y, { size: 8, color: MUTED });
      canvas.y -= 11;
    });
  }
  canvas.y -= 18;
}

function assemble(pages: string[][]): Blob {
  const objects: string[] = [];
  const pageIds = pages.map((_, index) => 5 + index * 2);

  objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
  objects[2] = `<< /Type /Pages /Count ${pages.length} /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] >>`;
  objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
  objects[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
  pages.forEach((ops, index) => {
    const id = pageIds[index];
    const content = ops.join('\n');
    objects[id] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] `
      + `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${id + 1} 0 R >>`;
    objects[id + 1] = `<< /Length ${content.length} >>\nstream\n${content}\nendstream`;
  });

  const offsets: number[] = [];
  let pdf = '%PDF-1.4\n';
  for (let id = 1; id < objects.length; id += 1) {
    offsets[id] = pdf.length;
    pdf += `${id} 0 obj\n${objects[id]}\nendobj\n`;
  }
  const startxref = pdf.length;
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f\r\n`;
  for (let id = 1; id < objects.length; id += 1) {
    pdf += `${String(offsets[id]).padStart(10, '0')} 00000 n\r\n`;
  }
  pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${startxref}\n%%EOF\n`;

  const bytes = new Uint8Array(pdf.length);
  for (let index = 0; index < pdf.length; index += 1) bytes[index] = pdf.charCodeAt(index) & 0xff;
  return new Blob([bytes], { type: 'application/pdf' });
}

/** Construye el PDF del reporte a partir de los datos ya presentes en pantalla. */
export function buildReportPdf(report: PdfReport): Blob {
  const canvas = new PdfCanvas();
  drawHeader(canvas, report, report.generatedAt ?? new Date());
  for (const section of report.sections) drawSection(canvas, section);
  return assemble(canvas.finish(`FashionStore \u00b7 ${report.title}`));
}
