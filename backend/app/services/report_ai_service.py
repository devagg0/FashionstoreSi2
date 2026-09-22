"""Analisis con IA generativa de los reportes administrativos (CU28, CU29 y CU30).

No consulta la base de datos ni recalcula indicadores: resume los datos ya
calculados por cada reporte (los mismos que el dashboard tiene en pantalla)
y se los entrega a Gemini para obtener una lectura ejecutiva.
"""

from app.integrations.gemini import GeminiAnalysisError, GeminiClient
from app.schemas.admin_inventory_report import InventoryReportData
from app.schemas.admin_reservations_report import ReservationsReportData
from app.schemas.admin_sales_report import SalesReportData


GEMINI_MODEL_LABEL = "gemini-2.0-flash"


class ReportAIUnavailableError(Exception):
    """El servicio de IA no pudo generar el analisis solicitado."""


class ReportAIService:
    """Construye el prompt de cada reporte y delega la generacion a Gemini."""

    def __init__(self, client: GeminiClient | None = None):
        self.client = client or GeminiClient()

    def analyze_sales(self, data: SalesReportData, pregunta: str | None = None) -> str:
        return self._analyze(self._sales_prompt(data), pregunta)

    def analyze_inventory(self, data: InventoryReportData, pregunta: str | None = None) -> str:
        return self._analyze(self._inventory_prompt(data), pregunta)

    def analyze_reservations(self, data: ReservationsReportData, pregunta: str | None = None) -> str:
        return self._analyze(self._reservations_prompt(data), pregunta)

    def _analyze(self, prompt: str, pregunta: str | None) -> str:
        if pregunta:
            # Consulta hablada del administrador (voz a texto), transcrita en el frontend.
            prompt += (
                "\nAdemas de ese resumen, responde de forma breve y directa esta pregunta del "
                f"administrador, formulada por voz: \"{pregunta.strip()}\"\n"
            )
        try:
            return self.client.generate_analysis(prompt=prompt)
        except GeminiAnalysisError as exc:
            raise ReportAIUnavailableError("No fue posible generar el analisis con IA") from exc

    @staticmethod
    def _sales_prompt(data: SalesReportData) -> str:
        k = data.kpis
        canales = ", ".join(f"{c.canal}: {c.importe_vendido} Bs" for c in data.por_canal) or "sin datos"
        sucursales = ", ".join(f"{s.nombre_sucursal}: {s.importe_vendido} Bs" for s in data.por_sucursal) or "sin datos"
        productos = ", ".join(
            f"{p.nombre_producto} ({p.unidades_vendidas} u.)" for p in data.productos_mas_vendidos[:5]
        ) or "sin datos"
        return (
            "Eres un analista de retail de moda en Bolivia. Analiza el siguiente reporte de ventas "
            "y entrega un resumen ejecutivo breve (maximo 6 puntos) con hallazgos y recomendaciones "
            "accionables. Responde en espanol, en texto plano, sin markdown.\n\n"
            f"Cantidad de ventas: {k.cantidad_ventas}\n"
            f"Importe vendido: {k.importe_vendido} {data.moneda}\n"
            f"Descuentos: {k.descuentos} {data.moneda}\n"
            f"Ticket promedio: {k.ticket_promedio}\n"
            f"Unidades vendidas: {k.unidades_vendidas}\n"
            f"Clientes identificados: {k.clientes_identificados}\n"
            f"Ventas sin cliente: {k.ventas_sin_cliente}\n"
            f"Por canal: {canales}\n"
            f"Por sucursal: {sucursales}\n"
            f"Productos mas vendidos: {productos}\n"
        )

    @staticmethod
    def _inventory_prompt(data: InventoryReportData) -> str:
        k = data.kpis
        sucursales = ", ".join(f"{s.nombre}: {s.unidades_disponibles} disp." for s in data.por_sucursal) or "sin datos"
        categorias = ", ".join(f"{c.nombre}: {c.unidades_disponibles} disp." for c in data.por_categoria) or "sin datos"
        advertencias = "; ".join(w.mensaje for w in data.advertencias) or "ninguna"
        return (
            "Eres un analista de inventario de una tienda de moda en Bolivia. Analiza el siguiente "
            "reporte de inventario y entrega un resumen ejecutivo breve (maximo 6 puntos) señalando "
            "riesgos de quiebre de stock y recomendaciones de reposicion. Responde en espanol, en "
            "texto plano, sin markdown.\n\n"
            f"Total productos: {k.total_productos}\n"
            f"Total variantes: {k.total_variantes}\n"
            f"Unidades actuales: {k.unidades_actuales}\n"
            f"Unidades reservadas: {k.unidades_reservadas}\n"
            f"Unidades disponibles: {k.unidades_disponibles}\n"
            f"Registros agotados: {k.registros_agotados}\n"
            f"Registros bajo stock: {k.registros_bajo_stock}\n"
            f"Productos con faltantes: {k.productos_con_agotados}\n"
            f"Productos con bajo stock: {k.productos_con_bajo_stock}\n"
            f"Por sucursal: {sucursales}\n"
            f"Por categoria: {categorias}\n"
            f"Advertencias: {advertencias}\n"
        )

    @staticmethod
    def _reservations_prompt(data: ReservationsReportData) -> str:
        k = data.kpis
        estados = ", ".join(f"{e.estado}: {e.total_reservas}" for e in data.por_estado) or "sin datos"
        sucursales = ", ".join(f"{s.nombre_sucursal}: {s.total_reservas}" for s in data.por_sucursal) or "sin datos"
        productos = ", ".join(
            f"{p.nombre_producto} ({p.total_reservas})" for p in data.productos_mas_reservados[:5]
        ) or "sin datos"
        return (
            "Eres un analista de operaciones de una tienda de moda en Bolivia. Analiza el siguiente "
            "reporte de reservas y entrega un resumen ejecutivo breve (maximo 6 puntos) sobre demanda, "
            "cumplimiento de atencion y riesgos de cancelacion o expiracion. Responde en espanol, en "
            "texto plano, sin markdown.\n\n"
            f"Total de reservas: {k.total_reservas}\n"
            f"Unidades reservadas: {k.unidades_reservadas}\n"
            f"Pendientes: {k.reservas_pendientes}\n"
            f"Confirmadas: {k.reservas_confirmadas}\n"
            f"Atendidas: {k.reservas_atendidas}\n"
            f"Canceladas: {k.reservas_canceladas}\n"
            f"Expiradas: {k.reservas_expiradas}\n"
            f"Clientes con reservas: {k.clientes_con_reservas}\n"
            f"Vencidas sin actualizar: {data.advertencias.reservas_vencidas_sin_actualizar}\n"
            f"Por estado: {estados}\n"
            f"Por sucursal: {sucursales}\n"
            f"Productos mas reservados: {productos}\n"
        )
