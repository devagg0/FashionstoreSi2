import { Injectable } from '@angular/core';
import { PdfReport, buildReportPdf } from '../utils/pdf';

export interface GeneratedPdf {
  blob: Blob;
  filename: string;
  generatedAt: Date;
}

/**
 * Exportacion compartida de los reportes administrativos (CU28, CU29 y CU30).
 * Trabaja solo con los datos ya cargados en el componente: no consulta la API.
 */
@Injectable({ providedIn: 'root' })
export class ReportPdfService {
  /** Genera el documento en memoria; la descarga es un paso aparte. */
  generate(report: PdfReport, slug: string): GeneratedPdf {
    const generatedAt = report.generatedAt ?? new Date();
    return {
      blob: buildReportPdf({ ...report, generatedAt }),
      filename: this.filename(slug, generatedAt),
      generatedAt,
    };
  }

  /** Entrega al navegador un PDF ya generado. */
  download(file: GeneratedPdf): void {
    const url = URL.createObjectURL(file.blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = file.filename;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  /** Nombre estable con la marca de tiempo local de La Paz. */
  filename(slug: string, generatedAt: Date): string {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/La_Paz',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(generatedAt);
    const value = (type: string) => parts.find(part => part.type === type)?.value ?? '00';
    return `${slug}-${value('year')}${value('month')}${value('day')}-${value('hour')}${value('minute')}.pdf`;
  }
}
