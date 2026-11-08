"""CU24. Orden de bloqueos: venta, devolucion, pagos, inventarios."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError
from app.models.returns import Return, ReturnDetail, Refund
from app.models.payment import Payment
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.branch import Branch
from app.models.employee_branch import EmployeeBranch
from app.models.user import User
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.repositories.returns import ReturnsRepository
from app.services.payments import PaymentsService, PaymentError
from app.services.stripe_service import StripeConnectionError
from app.core.config import settings

class ReturnsService(PaymentsService):
    RETURN_WINDOW_HOURS = 72

    def __init__(self, db, stripe_service=None):
        super().__init__(db, stripe_service)
        self.returns = ReturnsRepository(db)

    def _transaction(self, operation):
        try:
            result = operation()
            self.db.commit()
            return result
        except PaymentError:
            self.db.rollback()
            raise
        except StripeConnectionError as exc:
            self.db.rollback()
            raise PaymentError(503, str(exc) or "Stripe TEST no disponible o resultado incierto; reintente la misma operacion") from None
        except IntegrityError as exc:
            self.db.rollback()
            orig = str(getattr(exc, "orig", exc)).lower()
            if "uq_devolucion_cancelacion_activa" in orig:
                raise PaymentError(409, "Ya existe una solicitud de cancelacion activa para esta compra") from None
            if "clave_idempotencia" in orig:
                raise PaymentError(409, "Conflicto de idempotencia: ya existe una solicitud registrada con esta clave") from None
            if "ck_devolucion_estado" in orig or "ck_devolucion_resolucion" in orig:
                raise PaymentError(409, "La transicion de estado de la solicitud no es valida") from None
            raise PaymentError(409, "Conflicto de integridad en la solicitud; actualice el detalle antes de reintentar") from None
        except DataError:
            self.db.rollback()
            raise PaymentError(422, "Uno de los datos de la solicitud excede la longitud o formato permitido") from None
        except DBAPIError:
            self.db.rollback()
            raise PaymentError(503, "Error de comunicacion o bloqueo temporal en la base de datos. Actualice la vista e intente nuevamente.") from None
        except Exception:
            self.db.rollback()
            raise PaymentError(500, "No fue posible procesar la solicitud de cambio o devolucion") from None

    def _sale(self, user, sale_id, staff=False, for_update=True):
        sale = self.repository.lock_sale(sale_id) if for_update else self.db.get(Sale, sale_id)
        if sale is None:
            raise PaymentError(404, "Compra no encontrada")
        user_empresa = getattr(user, "id_empresa", None) or getattr(user, "empresa_id", None)
        sale_empresa = getattr(sale, "empresa_id", None)
        if user_empresa is not None and sale_empresa is not None and user_empresa != sale_empresa:
            raise PaymentError(404 if not staff else 403, "Compra no encontrada" if not staff else "Empresa o venta no autorizada")
        if not staff:
            client = self.clients.get_client(user.id_usuario)
            if user.rol.upper() != "CLIENTE" or client is None or sale.id_cliente != client.id_cliente:
                raise PaymentError(404, "Compra no encontrada")
            client_empresa = getattr(client, "id_empresa", None) or getattr(client, "empresa_id", None)
            if user_empresa is not None and client_empresa is not None and client_empresa != user_empresa:
                raise PaymentError(403, "Cliente no pertenece a la empresa activa")
        else:
            self._assignment(user, sale.id_sucursal, sale=sale)
        return sale

    def _check_72h_window(self, sale):
        completed_at = sale.fecha_completada or sale.fecha_venta
        now = self.now()
        if completed_at is None:
            return False, None, None, now
        deadline = completed_at + timedelta(hours=self.RETURN_WINDOW_HOURS)
        return (completed_at <= now <= deadline), completed_at, deadline, now

    def _assignment(self, user, branch_id, sale=None, row=None):
        role = user.rol.upper()
        if role not in {"CAJERO", "ENCARGADO_SUCURSAL", "ENCARGADO", "ADMINISTRADOR"}:
            raise PaymentError(403, "Se requiere personal autorizado")
        employee = self.staff.get_employee(user.id_usuario)
        branches = self.staff.branches(employee.id_empleado, for_update=True) if employee else []
        assignment = next((b for b in branches if b["id_sucursal"] == branch_id), None)
        if assignment is not None:
            return assignment["id_empleado_sucursal"]
        if role == "ADMINISTRADOR":
            branch = self.db.get(Branch, branch_id)
            if branch is None or not branch.estado:
                raise PaymentError(403, "Sucursal no encontrada o inactiva")
            user_empresa = getattr(user, "id_empresa", None) or getattr(user, "empresa_id", None)
            branch_empresa = getattr(branch, "empresa_id", None)
            if user_empresa is not None and branch_empresa is not None and user_empresa != branch_empresa:
                raise PaymentError(403, "La sucursal no pertenece a su empresa")
            if sale is not None and getattr(sale, "id_empleado_sucursal", None):
                eb = self.db.get(EmployeeBranch, sale.id_empleado_sucursal)
                if eb is not None and eb.id_sucursal == branch_id and eb.estado:
                    return eb.id_empleado_sucursal
            if row is not None:
                for uid in (row.id_usuario_inspector, row.id_usuario_receptor, row.id_usuario_evaluador):
                    if uid:
                        emp = self.staff.get_employee(uid)
                        if emp:
                            eb_list = self.staff.branches(emp.id_empleado)
                            match = next((b for b in eb_list if b["id_sucursal"] == branch_id), None)
                            if match is not None:
                                return match["id_empleado_sucursal"]
            fallback_eb = self.db.scalar(
                select(EmployeeBranch.id_empleado_sucursal)
                .where(
                    EmployeeBranch.id_sucursal == branch_id,
                    EmployeeBranch.estado.is_(True),
                )
                .order_by(EmployeeBranch.id_empleado_sucursal.asc())
            )
            if fallback_eb is not None:
                return fallback_eb
            outbound = self.repository.lock_movement(sale.id_venta) if sale is not None else None
            if outbound is not None and outbound.id_empleado_sucursal is not None:
                return outbound.id_empleado_sucursal
            return None
        raise PaymentError(403, "Se requiere asignacion activa a la sucursal")

    def _context_return(self, user, return_id, staff=False, for_update=True):
        row = self.db.get(Return, return_id)
        if row is None:
            raise PaymentError(404, "Devolucion no encontrada")
        sale = self._sale(user, row.id_venta, staff, for_update=for_update)
        if not staff and row.id_usuario_solicitante != user.id_usuario:
            raise PaymentError(404, "Devolucion no encontrada")
        ret = self.returns.lock(return_id) if for_update else row
        return sale, ret

    @staticmethod
    def _build_progress_timeline(row, sale, payment, refunds, monto_reembolsar, estado_reembolso):
        timeline = []
        # Paso 1: Solicitud registrada
        timeline.append({
            "paso": 1,
            "clave": "SOLICITUD_REGISTRADA",
            "titulo": "Solicitud registrada",
            "estado": "COMPLETADO",
            "fecha": row.created_at,
            "descripcion": f"Solicitud de {row.tipo} registrada correctamente.",
        })

        # Paso 2: Evaluación inicial
        if row.fecha_evaluacion_inicial:
            es_rechazo_inicial = (row.estado == "RECHAZADA" and not row.fecha_inspeccion)
            timeline.append({
                "paso": 2,
                "clave": "EVALUACION_INICIAL",
                "titulo": "Evaluación inicial por cajero",
                "estado": "RECHAZADO" if es_rechazo_inicial else "COMPLETADO",
                "fecha": row.fecha_evaluacion_inicial,
                "descripcion": f"Solicitud rechazada. Motivo: {row.motivo_rechazo}" if es_rechazo_inicial else "Solicitud aceptada inicialmente por el personal.",
            })
        else:
            timeline.append({
                "paso": 2,
                "clave": "EVALUACION_INICIAL",
                "titulo": "Evaluación inicial por cajero",
                "estado": "ACTUAL" if row.estado == "SOLICITADA" else "PENDIENTE",
                "fecha": None,
                "descripcion": "Pendiente de evaluación inicial por el personal de tienda.",
            })

        if row.tipo != "CANCELACION":
            # Paso 3: Modalidad de entrega
            if row.fecha_seleccion_modalidad or row.modalidad_entrega:
                mod_desc = "Entrega en tienda física" if row.modalidad_entrega == "ENTREGA_EN_TIENDA" else "Delivery simulado"
                timeline.append({
                    "paso": 3,
                    "clave": "MODALIDAD_ENTREGA",
                    "titulo": "Modalidad de entrega",
                    "estado": "COMPLETADO",
                    "fecha": row.fecha_seleccion_modalidad,
                    "descripcion": f"Modalidad seleccionada: {mod_desc}.",
                })
            else:
                timeline.append({
                    "paso": 3,
                    "clave": "MODALIDAD_ENTREGA",
                    "titulo": "Modalidad de entrega",
                    "estado": "ACTUAL" if row.estado == "ACEPTADA_INICIALMENTE" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": "Pendiente de que el cliente elija la modalidad de entrega.",
                })

            # Paso 4: Recepción de prenda en tienda
            if row.fecha_recepcion:
                timeline.append({
                    "paso": 4,
                    "clave": "RECEPCION_PRENDA",
                    "titulo": "Recepción de la prenda",
                    "estado": "COMPLETADO",
                    "fecha": row.fecha_recepcion,
                    "descripcion": "Prenda recibida físicamente en tienda.",
                })
            else:
                timeline.append({
                    "paso": 4,
                    "clave": "RECEPCION_PRENDA",
                    "titulo": "Recepción de la prenda",
                    "estado": "ACTUAL" if row.estado == "PENDIENTE_ENTREGA" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": "Esperando llegada y recepción física de la prenda en la sucursal.",
                })

            # Paso 5: Inspección física de la prenda
            if row.fecha_inspeccion:
                es_rechazo_insp = (row.estado == "RECHAZADA")
                timeline.append({
                    "paso": 5,
                    "clave": "INSPECCION_FISICA",
                    "titulo": "Inspección física",
                    "estado": "RECHAZADO" if es_rechazo_insp else "COMPLETADO",
                    "fecha": row.fecha_inspeccion,
                    "descripcion": (f"Inspección no superada ({row.estado_fisico or 'RECHAZADA'}). Motivo: {row.motivo_rechazo}") if es_rechazo_insp else f"Prenda inspeccionada favorablemente ({row.estado_fisico or 'OPTIMO'}).",
                })
            else:
                timeline.append({
                    "paso": 5,
                    "clave": "INSPECCION_FISICA",
                    "titulo": "Inspección física",
                    "estado": "ACTUAL" if row.estado == "RECIBIDA" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": "Pendiente de verificación e inspección física de la prenda.",
                })

        # Paso 6: Resolución financiera
        if row.tipo == "CAMBIO":
            dif = row.diferencia_definitiva
            if row.estado_pago_adicional == "CONFIRMADO":
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Pago de diferencia de precio",
                    "estado": "COMPLETADO",
                    "fecha": row.updated_at,
                    "descripcion": f"Cobro adicional de Bs {row.monto_adicional_cobrado or dif} confirmado ({row.medio_pago_adicional or 'tienda'}).",
                })
            elif dif is not None and dif > Decimal("0.00"):
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Pago de diferencia de precio",
                    "estado": "ACTUAL" if row.estado == "APROBADA" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": f"Cobro adicional pendiente de Bs {dif} (pago online con Stripe o en tienda).",
                })
            elif row.estado in ("APROBADA", "PROCESADA"):
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Resolución económica",
                    "estado": "COMPLETADO",
                    "fecha": row.updated_at,
                    "descripcion": "Sin diferencia económica adicional requerida.",
                })
            else:
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Resolución económica",
                    "estado": "PENDIENTE",
                    "fecha": None,
                    "descripcion": "Pendiente de fijación de importe definitivo.",
                })
        else:
            if estado_reembolso == "CONFIRMADO":
                ref_aprobado = next((r for r in refunds if getattr(r, "estado", None) == "APROBADO"), None)
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Reembolso económico",
                    "estado": "COMPLETADO",
                    "fecha": getattr(ref_aprobado, "fecha_aprobacion", None) or row.updated_at,
                    "descripcion": f"Reembolso de Bs {monto_reembolsar} aprobado y confirmado.",
                })
            elif estado_reembolso == "FALLIDO":
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Reembolso económico",
                    "estado": "RECHAZADO",
                    "fecha": row.updated_at,
                    "descripcion": "Reembolso fallido; requiere conciliación.",
                })
            elif monto_reembolsar > Decimal("0.00"):
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Reembolso económico",
                    "estado": "ACTUAL" if row.estado == "APROBADA" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": f"Reembolso de Bs {monto_reembolsar} pendiente de confirmación.",
                })
            else:
                timeline.append({
                    "paso": 6,
                    "clave": "RESOLUCION_FINANCIERA",
                    "titulo": "Reembolso económico",
                    "estado": "COMPLETADO" if row.estado == "PROCESADA" else "PENDIENTE",
                    "fecha": None,
                    "descripcion": "Sin restitución económica aplicable.",
                })

        # Paso 7: Cierre y procesamiento
        if row.estado == "PROCESADA":
            timeline.append({
                "paso": 7,
                "clave": "PROCESAMIENTO_FINAL",
                "titulo": "Solicitud procesada",
                "estado": "COMPLETADO",
                "fecha": row.fecha_procesamiento,
                "descripcion": "Prenda de reemplazo entregada e inventario actualizado." if row.tipo == "CAMBIO" else "Devolución cerrada y registrada exitosamente.",
            })
        elif row.estado == "RECHAZADA":
            timeline.append({
                "paso": 7,
                "clave": "PROCESAMIENTO_FINAL",
                "titulo": "Solicitud cerrada por rechazo",
                "estado": "RECHAZADO",
                "fecha": row.fecha_resolucion or row.updated_at,
                "descripcion": f"Solicitud no procesada debido al rechazo: {row.motivo_rechazo or 'Rechazada'}.",
            })
        else:
            is_actual = (
                row.estado == "APROBADA"
                and (row.tipo != "CAMBIO" or row.estado_pago_adicional != "PENDIENTE")
            )
            timeline.append({
                "paso": 7,
                "clave": "PROCESAMIENTO_FINAL",
                "titulo": "Cierre definitivo",
                "estado": "ACTUAL" if is_actual else "PENDIENTE",
                "fecha": None,
                "descripcion": "Pendiente de procesamiento y cierre por el personal de tienda.",
            })

        return timeline

    def _data_return(self, row, preloaded=None):
        def data(obj):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        sale = preloaded["sale"] if preloaded and "sale" in preloaded else self.db.get(Sale, row.id_venta)
        payment = preloaded["payment"] if preloaded and "payment" in preloaded else self._original_payment(row.id_venta)
        safe_payment = {name: getattr(payment, name) for name in (
            "id_pago", "medio", "proveedor", "entorno", "estado", "monto", "moneda"
        )} if (payment and not isinstance(payment, dict)) else (payment if isinstance(payment, dict) else None)
        details = preloaded["details"] if preloaded and "details" in preloaded else self.returns.details(row.id_devolucion)
        refunds = preloaded["refunds"] if preloaded and "refunds" in preloaded else self.returns.refunds(row.id_devolucion)
        sale_items = (
            preloaded["sale_items"]
            if preloaded and "sale_items" in preloaded
            else ({x.id_variante_producto: x for x in self.repository.items(row.id_venta)} if sale else {})
        )
        variant_ids = list(
            {d.id_variante_producto for d in details}
            | {d.id_variante_reemplazo for d in details if d.id_variante_reemplazo is not None}
        )
        catalog = (
            preloaded["catalog"]
            if preloaded and "catalog" in preloaded
            else self.returns.catalog_metadata(variant_ids, sale.id_sucursal if sale else None)
        )
        branch = (
            preloaded["branch"]
            if preloaded and "branch" in preloaded
            else self.returns.branch_info(sale.id_sucursal if sale else None)
        )
        client_info = (
            preloaded["client"]
            if preloaded and "client" in preloaded
            else None
        )
        if client_info is None and row.id_usuario_solicitante:
            try:
                u = self.db.get(User, row.id_usuario_solicitante)
                if u:
                    client_info = {"nombre": u.nombre, "apellido": u.apellido or ""}
            except Exception:
                pass

        evaluator_info = preloaded.get("evaluator") if preloaded and "evaluator" in preloaded else None
        if evaluator_info is None and row.id_usuario_evaluador:
            try:
                u = self.db.get(User, row.id_usuario_evaluador)
                if u:
                    evaluator_info = {"id_usuario": u.id_usuario, "nombre": u.nombre, "apellido": u.apellido or ""}
            except Exception:
                pass

        receptor_info = preloaded.get("receptor") if preloaded and "receptor" in preloaded else None
        if receptor_info is None and row.id_usuario_receptor:
            try:
                u = self.db.get(User, row.id_usuario_receptor)
                if u:
                    receptor_info = {"id_usuario": u.id_usuario, "nombre": u.nombre, "apellido": u.apellido or ""}
            except Exception:
                pass

        inspector_info = preloaded.get("inspector") if preloaded and "inspector" in preloaded else None
        if inspector_info is None and row.id_usuario_inspector:
            try:
                u = self.db.get(User, row.id_usuario_inspector)
                if u:
                    inspector_info = {"id_usuario": u.id_usuario, "nombre": u.nombre, "apellido": u.apellido or ""}
            except Exception:
                pass

        enriched_lines = []
        for d in details:
            line_dict = data(d)
            sale_item = sale_items.get(d.id_variante_producto)
            orig_meta = catalog.get(d.id_variante_producto, {})
            repl_meta = catalog.get(d.id_variante_reemplazo, {}) if d.id_variante_reemplazo is not None else None
            valor_orig = (
                d.precio_original_reconocido
                if d.precio_original_reconocido is not None and d.precio_original_reconocido > 0
                else d.importe_restitucion
            )
            valor_repl = d.precio_reemplazo_estimado or Decimal("0.00")
            dif = d.diferencia_precio_estimada or Decimal("0.00")
            adicional = dif if (row.tipo == "CAMBIO" and dif > Decimal("0.00")) else Decimal("0.00")
            saldo_favor = (
                abs(dif)
                if (row.tipo == "CAMBIO" and dif < Decimal("0.00"))
                else (d.importe_restitucion if row.tipo == "DEVOLUCION" else Decimal("0.00"))
            )
            resultado_linea = (
                "IMPORTE_ADICIONAL"
                if adicional > Decimal("0.00")
                else ("SALDO_A_FAVOR" if saldo_favor > Decimal("0.00") else "SIN_DIFERENCIA")
            )
            line_dict.update({
                "id_detalle_venta": sale_item.id_detalle_venta if sale_item else None,
                "importe_adicional_estimado": adicional,
                "saldo_a_favor_estimado": saldo_favor,
                "resultado_economico": resultado_linea,
                "prenda_original": {
                    **orig_meta,
                    "id_variante_producto": d.id_variante_producto,
                    "cantidad": d.cantidad,
                    "precio_unitario_compra": sale_item.precio_unitario if sale_item else None,
                    "descuento_unitario_compra": sale_item.descuento_unitario if sale_item else None,
                    "valor_reconocido": valor_orig,
                },
                "prenda_reemplazo": (
                    {
                        **(repl_meta or {}),
                        "id_variante_producto": d.id_variante_reemplazo,
                        "cantidad": d.cantidad_reemplazo,
                        "valor_reemplazo": valor_repl,
                    }
                    if d.id_variante_reemplazo is not None
                    else None
                ),
            })
            enriched_lines.append(line_dict)

        total_original = sum(
            (
                (
                    d.precio_original_reconocido
                    if d.precio_original_reconocido is not None and d.precio_original_reconocido > 0
                    else d.importe_restitucion
                )
                for d in details
            ),
            Decimal("0.00"),
        )
        total_reemplazo = sum(((d.precio_reemplazo_estimado or Decimal("0.00")) for d in details), Decimal("0.00"))
        total_diferencia = (
            (total_reemplazo - total_original).quantize(Decimal("0.01"))
            if row.tipo == "CAMBIO"
            else Decimal("0.00")
        )
        importe_adicional = (
            total_diferencia
            if (row.tipo == "CAMBIO" and total_diferencia > Decimal("0.00"))
            else Decimal("0.00")
        )
        saldo_a_favor = (
            abs(total_diferencia)
            if (row.tipo == "CAMBIO" and total_diferencia < Decimal("0.00"))
            else (
                sum((d.importe_restitucion for d in details), Decimal("0.00"))
                if row.tipo == "DEVOLUCION"
                else (sale.total if (row.tipo == "CANCELACION" and sale and safe_payment) else Decimal("0.00"))
            )
        )
        resultado_economico = (
            "IMPORTE_ADICIONAL"
            if importe_adicional > Decimal("0.00")
            else ("SALDO_A_FAVOR" if saldo_a_favor > Decimal("0.00") else "SIN_DIFERENCIA")
        )
        monto_reembolsar = (
            sum((d.importe_restitucion for d in details), Decimal("0.00"))
            if row.tipo == "DEVOLUCION"
            else (
                sale.total
                if (row.tipo == "CANCELACION" and sale and safe_payment)
                else (abs(total_diferencia) if (row.tipo == "CAMBIO" and total_diferencia < Decimal("0.00")) else Decimal("0.00"))
            )
        )
        if any(getattr(x, "estado", None) == "APROBADO" for x in refunds):
            estado_reembolso = "CONFIRMADO"
        elif any(getattr(x, "estado", None) == "RECHAZADO" for x in refunds):
            estado_reembolso = "FALLIDO"
        elif any(getattr(x, "estado", None) == "PENDIENTE" for x in refunds) or (
            row.tipo == "DEVOLUCION" and row.estado not in ("RECHAZADA", "PROCESADA") and monto_reembolsar > Decimal("0.00")
        ):
            estado_reembolso = "PENDIENTE"
        else:
            estado_reembolso = "NO_APLICA"
        apta_reintegro_stock = bool(
            (row.estado_fisico or "OPTIMO").upper() not in {"DANADO", "DEFECTUOSO", "NO_APTO", "CON_DESGASTE"}
            and row.etiquetas_intactas is not False
        )
        return {
            **data(row),
            "codigo_solicitud": f"SOL-{row.id_devolucion:05d}",
            "id_sucursal": sale.id_sucursal if sale else None,
            "id_cliente": sale.id_cliente if sale else None,
            "cliente": client_info,
            "evaluador": evaluator_info,
            "receptor": receptor_info,
            "inspector": inspector_info,
            "numero_venta": sale.numero_venta if sale else None,
            "sucursal": branch,
            "diferencia_precio_estimada": total_diferencia,
            "importe_adicional_estimado": importe_adicional,
            "saldo_a_favor_estimado": saldo_a_favor,
            "monto_reembolsar": monto_reembolsar,
            "estado_reembolso": estado_reembolso,
            "apta_reintegro_stock": apta_reintegro_stock,
            "historial_progreso": self._build_progress_timeline(
                row, sale, safe_payment, refunds, monto_reembolsar, estado_reembolso
            ),
            "resumen_economico": {
                "moneda": sale.moneda if sale else "BOB",
                "valor_original_reconocido": total_original,
                "valor_reemplazo_estimado": total_reemplazo,
                "diferencia_precio_estimada": total_diferencia,
                "importe_adicional_estimado": importe_adicional,
                "saldo_a_favor_estimado": saldo_a_favor,
                "resultado_economico": resultado_economico,
            },
            "pago": safe_payment,
            "lineas": enriched_lines,
            "reembolsos": [data(x) for x in refunds],
        }

    def _batch_data_returns(self, rows):
        if not rows:
            return []
        return_ids = [r.id_devolucion for r in rows]
        sale_ids = list({r.id_venta for r in rows if r.id_venta})
        user_ids = list({
            uid for r in rows
            for uid in (r.id_usuario_solicitante, r.id_usuario_evaluador, r.id_usuario_receptor, r.id_usuario_inspector)
            if uid
        })

        sales_map = {
            s.id_venta: s
            for s in self.db.scalars(select(Sale).where(Sale.id_venta.in_(sale_ids))).all()
        } if sale_ids else {}

        branch_ids = list({s.id_sucursal for s in sales_map.values() if s.id_sucursal})
        branches_map = {}
        if branch_ids:
            for b in self.db.scalars(select(Branch).where(Branch.id_sucursal.in_(branch_ids))).all():
                branches_map[b.id_sucursal] = {
                    "id_sucursal": b.id_sucursal,
                    "nombre": b.nombre,
                    "direccion": b.direccion,
                    "telefono": b.telefono,
                }

        payments_map = {}
        if sale_ids:
            for p in self.db.scalars(
                select(Payment).where(
                    Payment.id_venta.in_(sale_ids),
                    Payment.estado.in_(("APROBADO", "REEMBOLSADO"))
                )
            ).all():
                if p.id_venta not in payments_map:
                    payments_map[p.id_venta] = {
                        name: getattr(p, name)
                        for name in ("id_pago", "medio", "proveedor", "entorno", "estado", "monto", "moneda")
                    }

        details_map = {}
        if return_ids:
            for d in self.db.scalars(
                select(ReturnDetail).where(ReturnDetail.id_devolucion.in_(return_ids)).order_by(ReturnDetail.id_variante_producto)
            ).all():
                details_map.setdefault(d.id_devolucion, []).append(d)

        refunds_map = {}
        if return_ids:
            for ref in self.db.scalars(
                select(Refund).where(Refund.id_devolucion.in_(return_ids))
            ).all():
                refunds_map.setdefault(ref.id_devolucion, []).append(ref)

        sale_items_map = {}
        if sale_ids:
            for item in self.db.scalars(
                select(SaleDetail).where(SaleDetail.id_venta.in_(sale_ids))
            ).all():
                sale_items_map.setdefault(item.id_venta, {})[item.id_variante_producto] = item

        all_variant_ids = set()
        for d_list in details_map.values():
            for d in d_list:
                all_variant_ids.add(d.id_variante_producto)
                if d.id_variante_reemplazo is not None:
                    all_variant_ids.add(d.id_variante_reemplazo)

        catalog_map = self.returns.catalog_metadata(list(all_variant_ids)) if all_variant_ids else {}

        clients_map = {}
        if user_ids:
            try:
                for uid, nom, ape in self.db.execute(
                    select(User.id_usuario, User.nombre, User.apellido).where(User.id_usuario.in_(user_ids))
                ).all():
                    clients_map[uid] = {"nombre": nom, "apellido": ape or ""}
            except Exception:
                pass

        results = []
        for r in rows:
            sale = sales_map.get(r.id_venta)
            b_info = branches_map.get(sale.id_sucursal) if (sale and sale.id_sucursal) else None
            results.append(self._data_return(
                r,
                preloaded={
                    "sale": sale,
                    "payment": payments_map.get(r.id_venta),
                    "details": details_map.get(r.id_devolucion, []),
                    "refunds": refunds_map.get(r.id_devolucion, []),
                    "sale_items": sale_items_map.get(r.id_venta, {}),
                    "catalog": catalog_map,
                    "branch": b_info,
                    "client": clients_map.get(r.id_usuario_solicitante),
                    "evaluator": clients_map.get(r.id_usuario_evaluador),
                    "receptor": clients_map.get(r.id_usuario_receptor),
                    "inspector": clients_map.get(r.id_usuario_inspector),
                }
            ))
        return results

    def get_return(self, user, return_id, staff=False):
        return self._transaction(lambda: self._data_return(self._context_return(user, return_id, staff, for_update=False)[1]))

    def list_client_returns(self, user, tipo=None, estado=None, sale_id=None, modalidad_entrega=None, limit=20, offset=0):
        def operation():
            if user.rol.upper() != "CLIENTE":
                raise PaymentError(403, "Se requiere rol CLIENTE")
            client = self.clients.get_client(user.id_usuario)
            if client is None:
                raise PaymentError(403, "La cuenta no tiene un perfil CLIENTE asociado")
            empresa_id = getattr(user, "id_empresa", None) or getattr(user, "empresa_id", None) or getattr(client, "empresa_id", None)
            rows = self.returns.client_returns(
                client.id_cliente,
                empresa_id=empresa_id,
                tipo=tipo,
                estado=estado,
                sale_id=sale_id,
                modalidad_entrega=modalidad_entrega,
                limit=limit,
                offset=offset,
            )
            return self._batch_data_returns(rows)
        return self._transaction(operation)

    def exchange_options(self, user, sale_id):
        def operation():
            sale = self._sale(user, sale_id, staff=False)
            eligible_72h, completed_at, deadline, now = self._check_72h_window(sale)
            items = self.repository.items(sale_id)
            catalog = self.returns.catalog_metadata(
                [x.id_variante_producto for x in items], sale.id_sucursal
            )
            branch = self.returns.branch_info(sale.id_sucursal)
            lineas_compra = []
            has_available_units = False
            for item in items:
                used_qty = int(self.returns.used(sale_id, item.id_variante_producto) or 0)
                avail_qty = max(0, item.cantidad - used_qty)
                if avail_qty > 0:
                    has_available_units = True
                _, valor_disp = (
                    self._line_limit(sale, item, items, avail_qty, used_qty)
                    if avail_qty > 0
                    else (Decimal("0.00"), Decimal("0.00"))
                )
                _, valor_unit = (
                    self._line_limit(sale, item, items, 1, used_qty)
                    if avail_qty > 0
                    else self._line_limit(sale, item, items, 1, 0)
                )
                meta = catalog.get(item.id_variante_producto, {})
                lineas_compra.append({
                    "id_detalle_venta": item.id_detalle_venta,
                    "id_variante_producto": item.id_variante_producto,
                    "id_producto": meta.get("id_producto"),
                    "nombre_producto": meta.get("nombre_producto"),
                    "sku": meta.get("sku"),
                    "id_talla": meta.get("id_talla"),
                    "talla": meta.get("talla"),
                    "id_color": meta.get("id_color"),
                    "color": meta.get("color"),
                    "codigo_hex": meta.get("codigo_hex"),
                    "cantidad_comprada": item.cantidad,
                    "cantidad_usada": used_qty,
                    "cantidad_disponible": avail_qty,
                    "precio_unitario": item.precio_unitario,
                    "descuento_unitario": item.descuento_unitario,
                    "subtotal_linea": item.subtotal_linea,
                    "valor_unitario_reconocido": valor_unit,
                    "valor_disponible_reconocido": valor_disp,
                })

            available_variants = []
            for variant, product, size, color, inv in self.returns.available_exchange_variants(
                sale.id_sucursal, getattr(sale, "empresa_id", None)
            ):
                available_variants.append({
                    "id_variante_producto": variant.id_variante_producto,
                    "id_producto": product.id_producto,
                    "nombre_producto": product.nombre,
                    "sku": variant.sku,
                    "id_talla": size.id_talla,
                    "talla": size.nombre,
                    "id_color": color.id_color,
                    "color": color.nombre,
                    "codigo_hex": color.codigo_hex,
                    "precio_unitario": product.precio,
                    "stock_disponible": max(0, inv.stock_actual - inv.stock_reservado),
                })

            motivo_no_elegible = None
            if sale.estado != "COMPLETADA":
                motivo_no_elegible = "Solo puede solicitarse cambio o devolucion de una compra COMPLETADA"
            elif not eligible_72h:
                motivo_no_elegible = "El plazo de 72 horas posteriores a la finalizacion de la compra ha expirado"
            elif not has_available_units:
                motivo_no_elegible = "Todas las unidades de esta compra ya tienen una solicitud activa o procesada"

            horas_restantes = (
                round(max(0.0, (deadline - now).total_seconds() / 3600.0), 2)
                if deadline and eligible_72h
                else 0.0
            )
            return {
                "id_venta": sale.id_venta,
                "numero_venta": sale.numero_venta,
                "estado_venta": sale.estado,
                "moneda": sale.moneda,
                "id_sucursal": sale.id_sucursal,
                "sucursal": branch,
                "fecha_completada": completed_at,
                "fecha_limite_solicitud": deadline,
                "plazo_horas": self.RETURN_WINDOW_HOURS,
                "dentro_plazo_72h": bool(sale.estado == "COMPLETADA" and eligible_72h),
                "elegible_cambio_devolucion": bool(
                    sale.estado == "COMPLETADA" and eligible_72h and has_available_units
                ),
                "horas_restantes": horas_restantes,
                "motivo_no_elegible": motivo_no_elegible,
                "tipos_solicitud": ["CAMBIO", "DEVOLUCION"],
                "modalidades_entrega": ["ENTREGA_EN_TIENDA", "DELIVERY_SIMULADO"],
                "modalidad_entrega_pendiente": True,
                "mensaje_modalidad": "La modalidad de entrega se elegirá después de que el cajero acepte inicialmente la solicitud (CU16).",
                "lineas_compra": lineas_compra,
                "variantes_reemplazo_disponibles": available_variants,
            }
        return self._transaction(operation)

    def list_returns(self, user, estado=None, limit=20, offset=0, tipo=None, modalidad_entrega=None, id_sucursal=None):
        def operation():
            role = user.rol.upper()
            if role not in {"CAJERO", "ENCARGADO_SUCURSAL", "ENCARGADO", "ADMINISTRADOR"}:
                raise PaymentError(403, "Se requiere personal autorizado")
            employee = self.staff.get_employee(user.id_usuario)
            branches = self.staff.branches(employee.id_empleado) if employee else []
            branch_ids = [b["id_sucursal"] for b in branches]

            if role in {"CAJERO", "ENCARGADO_SUCURSAL", "ENCARGADO"} and not branch_ids:
                return []

            stmt = select(Return).join(Sale, Sale.id_venta == Return.id_venta)
            if branch_ids:
                if id_sucursal is not None:
                    if id_sucursal not in branch_ids:
                        raise PaymentError(403, "Sucursal no autorizada para el usuario")
                    stmt = stmt.where(Sale.id_sucursal == id_sucursal)
                else:
                    stmt = stmt.where(Sale.id_sucursal.in_(branch_ids))
            elif id_sucursal is not None:
                branch = self.db.get(Branch, id_sucursal)
                if branch is None:
                    raise PaymentError(404, "Sucursal no encontrada")
                user_empresa = getattr(user, "id_empresa", None) or getattr(user, "empresa_id", None)
                branch_empresa = getattr(branch, "empresa_id", None)
                if user_empresa is not None and branch_empresa is not None and user_empresa != branch_empresa:
                    raise PaymentError(403, "Sucursal no pertenece a su empresa")
                stmt = stmt.where(Sale.id_sucursal == id_sucursal)

            user_empresa = getattr(user, "id_empresa", None) or getattr(user, "empresa_id", None)
            if user_empresa is not None:
                stmt = stmt.where(Sale.empresa_id == user_empresa)
            if estado:
                stmt = stmt.where(Return.estado == estado)
            if tipo:
                stmt = stmt.where(Return.tipo == tipo)
            if modalidad_entrega:
                stmt = stmt.where(Return.modalidad_entrega == modalidad_entrega)
            rows = self.db.scalars(stmt.order_by(Return.created_at.desc(), Return.id_devolucion.desc())
                .limit(limit).offset(offset)).all()
            return self._batch_data_returns(rows)
        return self._transaction(operation)

    @staticmethod
    def _line_limit(sale, item, items, quantity, previous=0):
        # Incluye descuento global: repartir centavos por linea y unidad;
        # la ultima porcion recupera el residuo para una devolucion total exacta.
        total_lines = sum((x.subtotal_linea for x in items), Decimal(0))
        if total_lines <= 0 or sale.total < 0 or sale.total > total_lines:
            raise PaymentError(409, "Importes de venta inconsistentes")
        before = sum((x.subtotal_linea for x in items if x.id_variante_producto < item.id_variante_producto), Decimal(0))
        def prefix(value):
            return (sale.total * value / total_lines).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        allocation = prefix(before + item.subtotal_linea) - prefix(before)
        def units(n):
            capped_n = min(item.cantidad, max(0, n))
            denom = item.cantidad if item.cantidad > 0 else 1
            return (allocation * capped_n / denom).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        portion = units(previous + quantity) - units(previous)
        portion = max(Decimal("0.00"), min(portion, allocation, sale.total))
        return allocation, portion

    def request(self, user, sale_id, payload, key, cancellation=False):
        def operation():
            sale = self._sale(user, sale_id)
            kind = "CANCELACION" if cancellation else (getattr(payload, "tipo", None) or "DEVOLUCION")
            modality = getattr(payload, "modalidad_entrega", None) if not cancellation else None
            previous = self.db.scalar(select(Return).where(Return.clave_idempotencia == key))
            if previous:
                if (previous.id_venta != sale_id or previous.tipo != kind or previous.motivo != payload.motivo
                        or previous.id_usuario_solicitante != user.id_usuario
                        or previous.modalidad_entrega != modality):
                    raise PaymentError(409, "Clave de idempotencia usada por otra solicitud")
                expected = sorted(
                    (
                        x.id_detalle_venta,
                        x.cantidad,
                        getattr(x, "id_variante_reemplazo", None),
                        (getattr(x, "cantidad_reemplazo", None) or x.cantidad) if kind == "CAMBIO" else 0,
                    )
                    for x in payload.lineas
                ) if not cancellation else []
                items = self.repository.items(sale_id)
                ids = {x.id_variante_producto: x.id_detalle_venta for x in items}
                actual = sorted(
                    (ids[x.id_variante_producto], x.cantidad, x.id_variante_reemplazo, x.cantidad_reemplazo)
                    for x in self.returns.details(previous.id_devolucion)
                )
                if expected != actual:
                    raise PaymentError(409, "Clave de idempotencia usada por otra solicitud")
                return self._data_return(previous)
            if cancellation:
                if sale.estado != "PENDIENTE":
                    raise PaymentError(409, "Solo puede cancelarse una venta PENDIENTE")
                active = self.db.scalar(select(Return).where(Return.id_venta == sale_id,
                    Return.tipo == kind, Return.estado != "RECHAZADA"))
                if active:
                    raise PaymentError(409, "La venta ya tiene una cancelacion activa")
                movement = self.repository.lock_movement(sale_id)
                if movement and movement.estado == "CONFIRMADO":
                    raise PaymentError(409, "Ya existe una salida fisica; corresponde devolucion")
            else:
                if sale.estado != "COMPLETADA":
                    raise PaymentError(409, "Solo puede devolverse una venta COMPLETADA")
                eligible_72h, _, _, _ = self._check_72h_window(sale)
                if not eligible_72h:
                    raise PaymentError(
                        409,
                        "El plazo de 72 horas posteriores a la finalizacion de la compra ha expirado para solicitar cambios o devoluciones",
                    )
            items = self.repository.items(sale_id)
            selected = []
            if not cancellation:
                by_id = {x.id_detalle_venta: x for x in items}
                requested_by_line: dict[int, int] = {}
                for line in payload.lineas:
                    item = by_id.get(line.id_detalle_venta)
                    if item is None:
                        raise PaymentError(404, "Línea de compra no encontrada")
                    if not isinstance(line.cantidad, int) or line.cantidad <= 0:
                        raise PaymentError(422, "La cantidad solicitada debe ser un número entero mayor a 0")
                    requested_by_line[line.id_detalle_venta] = requested_by_line.get(line.id_detalle_venta, 0) + line.cantidad

                for det_id, total_qty in requested_by_line.items():
                    item = by_id[det_id]
                    used = self.returns.used(sale_id, item.id_variante_producto)
                    available_qty = max(0, item.cantidad - used)
                    if total_qty > available_qty:
                        raise PaymentError(
                            422,
                            f"La cantidad solicitada ({total_qty}) supera las unidades disponibles ({available_qty}) para cambio o devolución",
                        )
                desired = sorted((by_id[line.id_detalle_venta].id_variante_producto, line.cantidad) for line in payload.lineas)
                active_rows = self.db.scalars(select(Return).where(
                    Return.id_venta == sale_id,
                    Return.tipo.in_(("DEVOLUCION", "CAMBIO")),
                    Return.estado.in_(("SOLICITADA", "APROBADA")),
                )).all()
                for active_row in active_rows:
                    actual = sorted((d.id_variante_producto, d.cantidad) for d in self.returns.details(active_row.id_devolucion))
                    if desired == actual:
                        raise PaymentError(409, "Ya existe una solicitud activa para estas lineas y cantidades")
                if kind == "CAMBIO":
                    requested_by_replacement: dict[int, int] = {}
                    sale_empresa = getattr(sale, "empresa_id", None)
                    for line in payload.lineas:
                        item = by_id[line.id_detalle_venta]
                        repl_id = getattr(line, "id_variante_reemplazo", None)
                        repl_qty = getattr(line, "cantidad_reemplazo", None) or line.cantidad
                        if repl_id is None or repl_qty != line.cantidad:
                            raise PaymentError(422, "Variante o cantidad de reemplazo invalida para cambio")
                        if repl_id == item.id_variante_producto:
                            raise PaymentError(422, "Para CAMBIO debe elegir otra talla, color o producto diferente al original")
                        repl_info = self.returns.replacement_variant(repl_id, sale.id_sucursal)
                        if repl_info is None:
                            raise PaymentError(404, "Variante de reemplazo no encontrada")
                        variant = repl_info["variant"]
                        product = repl_info["product"]
                        size = repl_info["size"]
                        color = repl_info["color"]
                        inventory = repl_info["inventory"]
                        if (
                            not variant.estado
                            or not product.estado
                            or not size.estado
                            or not color.estado
                            or (
                                sale_empresa is not None
                                and (
                                    getattr(variant, "empresa_id", sale_empresa) != sale_empresa
                                    or getattr(product, "empresa_id", sale_empresa) != sale_empresa
                                )
                            )
                        ):
                            raise PaymentError(422, "La variante de reemplazo no se encuentra activa o autorizada")
                        requested_by_replacement[repl_id] = requested_by_replacement.get(repl_id, 0) + repl_qty
                        available_stock = (
                            (inventory.stock_actual - inventory.stock_reservado)
                            if (inventory is not None and inventory.stock_actual >= inventory.stock_reservado)
                            else 0
                        )
                        if available_stock < requested_by_replacement[repl_id]:
                            raise PaymentError(409, "Stock insuficiente en la sucursal para la variante de reemplazo seleccionada")
                        selected.append((item, line.cantidad, repl_id, repl_qty, Decimal(product.precio)))
                else:
                    for line in payload.lineas:
                        item = by_id[line.id_detalle_venta]
                        selected.append((item, line.cantidad, None, 0, Decimal("0.00")))
            now = self.now()
            empresa_id = getattr(sale, "empresa_id", 1) or 1
            row = self.returns.add(
                Return,
                empresa_id=empresa_id,
                id_venta=sale_id,
                tipo=kind,
                estado="SOLICITADA",
                modalidad_entrega=modality,
                motivo=payload.motivo,
                id_usuario_solicitante=user.id_usuario,
                clave_idempotencia=key,
                created_at=now,
                updated_at=now,
            )
            for item, quantity, repl_id, repl_qty, repl_unit_price in selected:
                _, maximum = self._line_limit(sale, item, items, quantity, self.returns.used(sale_id, item.id_variante_producto))
                if kind == "CAMBIO":
                    valor_reemplazo = (repl_unit_price * Decimal(repl_qty)).quantize(Decimal("0.01"))
                    diferencia = (valor_reemplazo - maximum).quantize(Decimal("0.01"))
                    importe_restitucion = abs(diferencia) if diferencia < Decimal("0.00") else Decimal("0.00")
                    importe_restitucion = min(importe_restitucion, sale.total)
                else:
                    valor_reemplazo = Decimal("0.00")
                    diferencia = Decimal("0.00")
                    importe_restitucion = min(maximum, sale.total)
                self.returns.add(
                    ReturnDetail,
                    empresa_id=empresa_id,
                    id_devolucion=row.id_devolucion,
                    id_venta=sale_id,
                    id_variante_producto=item.id_variante_producto,
                    cantidad=quantity,
                    cantidad_reintegrar=0,
                    importe_restitucion=importe_restitucion,
                    id_variante_reemplazo=repl_id,
                    cantidad_reemplazo=repl_qty,
                    precio_original_reconocido=maximum,
                    precio_reemplazo_estimado=valor_reemplazo,
                    diferencia_precio_estimada=diferencia,
                    created_at=now,
                    updated_at=now,
                )
            return self._data_return(row)
        return self._transaction(operation)

    def _original_payment(self, sale_id, *, lock=False):
        statement = select(Payment).where(Payment.id_venta == sale_id,
            Payment.estado.in_(("APROBADO", "REEMBOLSADO")))
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        rows = self.db.scalars(statement).all()
        if len(rows) > 1:
            raise PaymentError(409, "La venta tiene varios pagos cobrados; requiere conciliacion")
        return rows[0] if rows else None

    def _paid(self, sale):
        return self._original_payment(sale.id_venta, lock=True)

    def review(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede resolver su propia solicitud")
            if row.estado != "SOLICITADA":
                raise PaymentError(409, "La solicitud ya fue revisada")
            details = self.returns.details(return_id)
            if payload.resultado == "RECHAZADA":
                if payload.lineas:
                    raise PaymentError(422, "Un rechazo no admite importes ni reintegros")
            elif row.tipo == "CANCELACION":
                if payload.lineas or sale.estado != "PENDIENTE":
                    raise PaymentError(409, "Cancelacion incompatible con la venta")
            else:
                if sale.estado != "COMPLETADA":
                    raise PaymentError(409, "Venta no completada")
                approved = {x.id_variante_producto: x for x in payload.lineas}
                if len(approved) != len(payload.lineas) or set(approved) != {x.id_variante_producto for x in details}:
                    raise PaymentError(422, "Debe revisar todas las lineas exactamente una vez")
                for detail in details:
                    line = approved[detail.id_variante_producto]
                    # Preservar el limite calculado por el servidor al solicitar;
                    # el personal solo puede reducirlo, nunca redistribuirlo.
                    maximum = detail.importe_restitucion
                    if line.cantidad_reintegrar > detail.cantidad or line.importe_restitucion > maximum:
                        raise PaymentError(422, "Reintegro o importe supera lo autorizado por la compra")
                    detail.cantidad_reintegrar = line.cantidad_reintegrar
                    detail.importe_restitucion = line.importe_restitucion
                    detail.updated_at = self.now()
            now = self.now()
            row.estado = payload.resultado
            row.id_usuario_resolutor = user.id_usuario
            row.fecha_resolucion = now
            row.updated_at = now
            if row.estado == "APROBADA":
                payment = self._paid(sale)
                amount = sale.total if row.tipo == "CANCELACION" else sum((d.importe_restitucion for d in details), Decimal(0))
                if amount > 0 and payment is None and row.tipo != "CANCELACION":
                    raise PaymentError(409, "No existe pago aprobado para reembolsar")
                if payment and amount > 0:
                    if payment.moneda != sale.moneda or amount + self.returns.reserved_money(payment.id_pago) > payment.monto:
                        raise PaymentError(409, "El reembolso supera el saldo pagado")
                    self.returns.add(Refund, id_venta=sale.id_venta, id_pago=payment.id_pago,
                        id_devolucion=return_id, estado="PENDIENTE", monto=amount,
                        clave_idempotencia=uuid4(), created_at=now, updated_at=now)
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def initial_review(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, staff=True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede evaluar su propia solicitud")
            if row.estado != "SOLICITADA":
                raise PaymentError(
                    409,
                    f"Solo se pueden evaluar inicialmente solicitudes en estado SOLICITADA (estado actual: {row.estado})"
                )
            now = self.now()
            if payload.resultado == "RECHAZADA":
                if not payload.motivo_rechazo or not payload.motivo_rechazo.strip():
                    raise PaymentError(422, "El motivo de rechazo es obligatorio al rechazar la solicitud")
                row.estado = "RECHAZADA"
                row.motivo_rechazo = payload.motivo_rechazo.strip()
                row.id_usuario_resolutor = user.id_usuario
                row.fecha_resolucion = now
            elif payload.resultado in ("ACEPTADA", "ACEPTADA_INICIALMENTE"):
                row.estado = "ACEPTADA_INICIALMENTE"
            else:
                raise PaymentError(422, f"Resultado de evaluación no válido: {payload.resultado}")

            row.id_usuario_evaluador = user.id_usuario
            row.fecha_evaluacion_inicial = now
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def select_delivery_modality(self, user, return_id, payload):
        def operation():
            row = self.returns.lock(return_id)
            if row is None:
                raise PaymentError(404, "Solicitud de cambio o devolución no encontrada")
            sale = self._sale(user, row.id_venta, staff=False)
            if row.id_usuario_solicitante != user.id_usuario:
                raise PaymentError(403, "No tiene permisos para modificar esta solicitud")
            if row.estado != "ACEPTADA_INICIALMENTE":
                raise PaymentError(
                    409,
                    f"La solicitud debe estar en estado ACEPTADA_INICIALMENTE para seleccionar la modalidad de entrega (estado actual: {row.estado})"
                )
            if payload.modalidad_entrega not in ("ENTREGA_EN_TIENDA", "DELIVERY_SIMULADO"):
                raise PaymentError(422, "Modalidad de entrega inválida")

            now = self.now()
            row.modalidad_entrega = payload.modalidad_entrega
            row.estado = "PENDIENTE_ENTREGA"
            row.fecha_seleccion_modalidad = now
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def receive_item(self, user, return_id, payload=None):
        def operation():
            sale, row = self._context_return(user, return_id, staff=True)
            if row.estado != "PENDIENTE_ENTREGA":
                raise PaymentError(
                    409,
                    f"Solo se puede confirmar la recepción física si la solicitud está PENDIENTE_ENTREGA (estado actual: {row.estado})"
                )

            now = self.now()
            row.estado = "RECIBIDA"
            row.fecha_recepcion = now
            row.id_usuario_receptor = user.id_usuario
            obs = getattr(payload, "observaciones", None) if payload else None
            if obs and obs.strip():
                row.observaciones_inspeccion = obs.strip()
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def inspect_item(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, staff=True)
            if row.estado != "RECIBIDA":
                raise PaymentError(
                    409,
                    f"La prenda debe estar en estado RECIBIDA para registrar la inspección física (estado actual: {row.estado})"
                )

            now = self.now()
            row.estado_fisico = payload.estado_fisico.strip()
            row.etiquetas_intactas = bool(payload.etiquetas_intactas)
            row.correspondencia_compra = bool(payload.correspondencia_compra)
            if payload.observaciones and payload.observaciones.strip():
                row.observaciones_inspeccion = payload.observaciones.strip()
            row.fecha_inspeccion = now
            row.id_usuario_inspector = user.id_usuario

            if payload.resultado == "RECHAZADA":
                if not payload.motivo_rechazo or not payload.motivo_rechazo.strip():
                    raise PaymentError(422, "El motivo de rechazo es obligatorio al rechazar la solicitud en la inspección")
                row.estado = "RECHAZADA"
                row.motivo_rechazo = payload.motivo_rechazo.strip()
                row.id_usuario_resolutor = user.id_usuario
                row.fecha_resolucion = now
            elif payload.resultado == "APROBADA":
                row.estado = "APROBADA"
                row.id_usuario_resolutor = user.id_usuario
                row.fecha_resolucion = now
            else:
                raise PaymentError(422, f"Resultado de inspección inválido: {payload.resultado}")

            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def _close_pending_payments(self, sale):
        for payment in self.db.scalars(select(Payment).where(Payment.id_venta == sale.id_venta,
                Payment.estado == "PENDIENTE").with_for_update()).all():
            if payment.proveedor == "STRIPE":
                self._stripe_payment(payment)
                ref = payment.referencia_externa
                if ref is None:
                    raise PaymentError(409, "Pago Stripe sin referencia requiere conciliacion antes de cancelar")
                if ref.startswith("cs_test_"):
                    session = self.stripe.retrieve_checkout_session(ref)
                    self._validate_checkout(sale, payment, session)
                    if session["status"] == "open":
                        session = self.stripe.expire_checkout_session(ref, payment.clave_idempotencia)
                        self._validate_checkout(sale, payment, session)
                    if session["status"] != "expired" or session["payment_status"] != "unpaid":
                        raise PaymentError(409, "Checkout cobrado o incierto; sincronice el pago")
                elif ref.startswith("pi_"):
                    intent = self.stripe.retrieve_payment_intent(ref)
                    self._validate_intent(sale, payment, intent)
                    if intent["status"] != "canceled":
                        intent = self.stripe.cancel_payment_intent(ref, payment.clave_idempotencia)
                        self._validate_intent(sale, payment, intent)
                    if intent["status"] != "canceled":
                        raise PaymentError(409, "PaymentIntent aun cobrable")
                else:
                    raise PaymentError(409, "Referencia Stripe invalida")
            payment.estado = "CANCELADO"
            payment.updated_at = self.now()

    def _refund_intent(self, sale, payment):
        self._stripe_payment(payment)
        reference = payment.referencia_externa or ""
        if reference.startswith("cs_test_"):
            session = self.stripe.retrieve_checkout_session(reference)
            self._validate_checkout(sale, payment, session)
            if self._field(session, "status") != "complete" or self._field(session, "payment_status") != "paid":
                raise PaymentError(409, "Checkout no cobrado")
            intent = self._field(session, "payment_intent")
            reference = intent if isinstance(intent, str) else self._field(intent, "id", "")
        if not reference.startswith("pi_"):
            raise PaymentError(409, "PaymentIntent no verificable")
        intent = self.stripe.retrieve_payment_intent(reference)
        metadata = self._field(intent, "metadata", {})
        expected = {"id_venta": str(sale.id_venta), "id_pago": str(payment.id_pago),
                    "clave_idempotencia": str(payment.clave_idempotencia)}
        if (self._field(intent, "livemode") is not False or self._field(intent, "id") != reference
                or self._field(intent, "status") != "succeeded" or self._field(intent, "amount_received") != int(payment.monto * 100)
                or self._field(intent, "currency") != payment.moneda.lower()
                or any(self._field(metadata, k) != v for k, v in expected.items())):
            raise PaymentError(409, "Pago Stripe TEST no verificable")
        return reference

    def _stripe_refund(self, sale, payment, refund):
        intent_id = self._refund_intent(sale, payment)
        intent = self.stripe.retrieve_payment_intent(intent_id)
        if self._field(intent, "livemode") is not False:
            raise PaymentError(409, "PaymentIntent debe pertenecer a TEST")
        charge_id = self._field(intent, "latest_charge")
        if not isinstance(charge_id, str) or not charge_id.startswith("ch_"):
            raise PaymentError(409, "Cargo original no verificable")
        charge = self.stripe.retrieve_charge(charge_id)
        if (self._field(charge, "livemode") is not False or self._field(charge, "id") != charge_id
                or self._field(charge, "payment_intent") != intent_id
                or self._field(charge, "paid") is not True or self._field(charge, "captured") is not True
                or self._field(charge, "currency") != payment.moneda.lower()
                or self._field(charge, "amount") != int(payment.monto * 100)
                or not isinstance(self._field(charge, "amount_refunded"), int)
                or not 0 <= self._field(charge, "amount_refunded") <= int(payment.monto * 100)):
            raise PaymentError(409, "Cargo Stripe TEST no verificable")
        def valid(remote):
            return (str(self._field(remote, "id", "")).startswith("re_")
                and self._field(remote, "payment_intent") == intent_id
                and self._field(remote, "charge") == charge_id
                and self._field(remote, "amount") == int(refund.monto * 100)
                and self._field(remote, "currency") == payment.moneda.lower()
                and self._field(remote, "status") in {"succeeded", "pending", "requires_action", "failed", "canceled"})
        if refund.referencia_externa:
            remote = self.stripe.retrieve_refund(refund.referencia_externa)
            if not valid(remote) or self._field(remote, "id") != refund.referencia_externa:
                raise PaymentError(409, "Reembolso Stripe TEST no verificable")
            return remote
        existing = self.stripe.list_refunds(intent_id)
        candidates = []
        accounted_total = 0
        unaccounted = False
        for remote in existing:
            claimed = self.db.scalar(select(Refund).where(Refund.id_pago == payment.id_pago,
                Refund.referencia_externa == self._field(remote, "id"), Refund.id_reembolso != refund.id_reembolso))
            if claimed is not None:
                if (claimed.estado == "APROBADO" and self._field(remote, "status") == "succeeded"
                        and self._field(remote, "payment_intent") == intent_id
                        and self._field(remote, "charge") == charge_id
                        and self._field(remote, "currency") == payment.moneda.lower()
                        and self._field(remote, "amount") == int(claimed.monto * 100)):
                    accounted_total += self._field(remote, "amount")
                else:
                    unaccounted = True
                continue
            if not valid(remote):
                unaccounted = True
                continue
            metadata = self._field(remote, "metadata", {})
            linked = (self._field(metadata, "id_reembolso") == str(refund.id_reembolso)
                and self._field(metadata, "clave_idempotencia") == str(refund.clave_idempotencia))
            # Recuperacion legacy inequivoca: unico refund total del pago y
            # ninguna otra autorizacion local que pueda ser su propietaria.
            legacy = (len(existing) == 1 and refund.monto == payment.monto
                and self._field(remote, "status") == "succeeded"
                and self._field(charge, "amount_refunded") == int(payment.monto * 100)
                and self.returns.reserved_money(payment.id_pago, refund.id_reembolso) == 0)
            if linked or legacy:
                candidates.append(remote)
            else:
                unaccounted = True
        if len(candidates) == 1:
            if (self._field(candidates[0], "status") == "succeeded"
                    and self._field(charge, "amount_refunded") < int(refund.monto * 100)):
                raise PaymentError(409, "Refund succeeded no coincide con el saldo reembolsado del cargo")
            return candidates[0]
        refunded = self._field(charge, "amount_refunded")
        if (candidates or unaccounted or refunded != accounted_total
                or refunded + int(refund.monto * 100) > int(payment.monto * 100)):
            # Nunca adivinar la atribucion ni recrear ante un cargo ya reembolsado.
            raise PaymentError(409, "Reembolsos existentes requieren conciliacion; no crear otro Refund")
        if self.now() - refund.created_at >= timedelta(hours=23):
            raise PaymentError(409, "Reembolso sin referencia requiere conciliacion; no recrear")
        remote = self.stripe.create_refund(payment_intent=intent_id,
            amount=int(refund.monto * 100), key=refund.clave_idempotencia, refund_id=refund.id_reembolso)
        if not valid(remote):
            raise PaymentError(409, "Reembolso Stripe TEST no verificable")
        return remote

    def _validate_inventory(self, sale, row, details):
        if row.tipo == "CANCELACION":
            held = sale.stock_comprometido or sale.id_reserva is not None
            items = self.repository.items(sale.id_venta) if held else []
            if held and not items:
                raise PaymentError(409, "Venta comprometida sin detalles")
            if sale.id_reserva is not None:
                reservation = self.staff.get_reservation(sale.id_reserva, for_update=True)
                if reservation is None or reservation.estado != "ATENDIDA" or reservation.id_sucursal != sale.id_sucursal:
                    raise PaymentError(409, "Reserva asociada inconsistente")
            expected = {x.id_variante_producto: x.cantidad for x in items}
        else:
            sold = {x.id_variante_producto: x for x in self.repository.items(sale.id_venta)}
            for detail in details:
                item = sold.get(detail.id_variante_producto)
                if (item is None or detail.cantidad <= 0 or detail.cantidad_reintegrar < 0
                        or detail.cantidad_reintegrar > detail.cantidad
                        or self.returns.used(sale.id_venta, detail.id_variante_producto) > item.cantidad):
                    raise PaymentError(409, "Unidades devueltas inconsistentes")
            expected = {x.id_variante_producto: x.cantidad_reintegrar for x in details if x.cantidad_reintegrar > 0}
            if expected:
                outbound = self.repository.lock_movement(sale.id_venta)
                if (outbound is None or outbound.estado != "CONFIRMADO" or outbound.tipo_movimiento != "VENTA"
                        or outbound.id_sucursal_origen != sale.id_sucursal):
                    raise PaymentError(409, "No existe salida fisica confirmada")
                movement_items = {x.id_variante_producto: x.cantidad for x in self.repository.movement_items(outbound.id_movimiento_inventario)}
                if movement_items != {k: v.cantidad for k, v in sold.items()}:
                    raise PaymentError(409, "Salida fisica incompatible con la venta")
        inventories = {i.id_variante_producto: i for i in self.staff.inventories(
            sale.id_sucursal, list(expected), for_update=True)} if expected else {}
        for variant, quantity in expected.items():
            inv = inventories.get(variant)
            if (inv is None or inv.stock_actual < inv.stock_reservado
                    or (row.tipo == "CANCELACION" and inv.stock_reservado < quantity)):
                raise PaymentError(409, "Inventario inexistente o inconsistente")

    def process(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede procesar su propia solicitud")
            if row.tipo == "DEVOLUCION" and user.rol.upper() not in {"ADMINISTRADOR", "ENCARGADO_SUCURSAL", "ENCARGADO"}:
                raise PaymentError(403, "Solo ADMINISTRADOR o ENCARGADO autorizado pueden procesar devoluciones y reembolsos")
            if row.estado == "PROCESADA":
                return self._data_return(row)
            if row.estado != "APROBADA":
                raise PaymentError(409, "Debe aprobar la solicitud antes de procesar")
            details = self.returns.details(return_id)
            assignment = self._assignment(user, sale.id_sucursal, sale=sale, row=row)
            if row.tipo == "CAMBIO":
                return self._process_exchange(user, sale, row, details, assignment, payload)
            if row.tipo == "CANCELACION":
                if sale.estado != "PENDIENTE":
                    raise PaymentError(409, "La venta ya no puede cancelarse")
                movement = self.repository.lock_movement(sale.id_venta)
                if movement and movement.estado == "CONFIRMADO":
                    raise PaymentError(409, "Ya hubo salida fisica")
                self._close_pending_payments(sale)
            elif sale.estado != "COMPLETADA":
                raise PaymentError(409, "Venta no completada")

            refunds = self.returns.refunds(return_id)
            if len(refunds) > 1:
                raise PaymentError(409, "Multiples reembolsos requieren conciliacion")
            refund = refunds[0] if refunds else None

            if row.tipo == "DEVOLUCION":
                if not details:
                    raise PaymentError(409, "La solicitud de devolucion no contiene lineas")
                if refund is None and (row.fecha_recepcion is None or row.fecha_inspeccion is None or row.correspondencia_compra is False):
                    raise PaymentError(
                        409,
                        "La prenda debe haber sido recibida e inspeccionada satisfactoriamente antes de procesar la devolucion y el reembolso",
                    )
                if row.correspondencia_compra is False:
                    raise PaymentError(409, "La prenda no supero la verificacion de correspondencia con la compra original")
                items = self.repository.items(sale.id_venta)
                sold = {x.id_variante_producto: x for x in items}
                prenda_apta = (
                    (row.estado_fisico or "OPTIMO").upper() not in {"DANADO", "DEFECTUOSO", "NO_APTO", "CON_DESGASTE"}
                    and (row.etiquetas_intactas is not False)
                )
                for detail in details:
                    item = sold.get(detail.id_variante_producto)
                    if item is None or detail.cantidad <= 0:
                        raise PaymentError(409, "Unidades devueltas inconsistentes")
                    total_used = self.returns.used(sale.id_venta, detail.id_variante_producto)
                    if total_used > item.cantidad:
                        raise PaymentError(409, "Unidades devueltas inconsistentes")
                    previous_used = max(0, total_used - detail.cantidad)
                    allocation, max_portion = self._line_limit(sale, item, items, detail.cantidad, previous_used)
                    if detail.importe_restitucion is None or detail.importe_restitucion < Decimal("0.00"):
                        raise PaymentError(409, "Importe de restitucion invalido")
                    if detail.importe_restitucion > max_portion or detail.importe_restitucion > allocation:
                        raise PaymentError(409, "El importe de reembolso supera lo efectivamente pagado por la linea")
                    if not prenda_apta or payload.reintegrar_stock_original is False:
                        detail.cantidad_reintegrar = 0
                        detail.updated_at = self.now()
                    elif payload.reintegrar_stock_original is True or (
                        payload.reintegrar_stock_original is None and detail.cantidad_reintegrar == 0 and refund is None
                    ):
                        detail.cantidad_reintegrar = detail.cantidad
                        detail.updated_at = self.now()
                self.db.flush()

            self._validate_inventory(sale, row, details)
            payment = self._paid(sale)
            required_amount = sale.total if row.tipo == "CANCELACION" else sum(
                (d.importe_restitucion for d in details), Decimal(0))
            if required_amount > 0 and payment is None and (refund or row.tipo == "DEVOLUCION"):
                raise PaymentError(409, "No existe pago aprobado asociado a la venta para reembolsar")
            if refund is None and row.tipo == "DEVOLUCION" and required_amount > Decimal("0.00"):
                if (
                    payment is None
                    or payment.moneda != sale.moneda
                    or required_amount > sale.total
                    or required_amount + self.returns.reserved_money(payment.id_pago) > payment.monto
                ):
                    raise PaymentError(409, "El reembolso supera el saldo disponible del pago original")
                now_ref = self.now()
                refund = self.returns.add(
                    Refund,
                    empresa_id=getattr(sale, "empresa_id", None) or getattr(row, "empresa_id", None) or 1,
                    id_venta=sale.id_venta,
                    id_pago=payment.id_pago,
                    id_devolucion=return_id,
                    estado="PENDIENTE",
                    monto=required_amount,
                    clave_idempotencia=uuid4(),
                    id_usuario_responsable=user.id_usuario,
                    created_at=now_ref,
                    updated_at=now_ref,
                )
            if refund:
                authorized = sale.total if row.tipo == "CANCELACION" else sum((d.importe_restitucion for d in details), Decimal(0))
                if (payment is None or refund.id_pago != payment.id_pago or refund.monto > authorized
                        or refund.monto + self.returns.reserved_money(payment.id_pago, refund.id_reembolso) > payment.monto
                        or refund.estado == "RECHAZADO"):
                    raise PaymentError(409, "Reembolso incompatible o saldo insuficiente")
                if refund.estado == "PENDIENTE":
                    remote = None
                    if payment.proveedor == "STRIPE":
                        if payload.referencia_manual:
                            raise PaymentError(422, "Stripe no admite referencia manual")
                        remote = self._stripe_refund(sale, payment, refund)
                        refund.referencia_externa = self._field(remote, "id")
                        refund.updated_at = self.now()
                        remote_status = self._field(remote, "status")
                        if remote_status != "succeeded":
                            # Persistir referencia incluso si sigue pendiente o fallo.
                            # No crear un segundo reembolso para esta autorizacion.
                            if remote_status in {"failed", "canceled"}:
                                refund.estado = "RECHAZADO"
                            self.db.flush()
                            return self._data_return(row)
                    elif (payment.proveedor, payment.entorno, payment.medio) in {
                            ("MANUAL", "LOCAL", "EFECTIVO"),
                            ("MANUAL", "LOCAL", "QR"),
                            ("MANUAL", "LOCAL", "TARJETA"),
                    }:
                        if not payload.referencia_manual:
                            raise PaymentError(422, "Debe registrar comprobante de reembolso manual")
                        refund.referencia_externa = payload.referencia_manual
                    else:
                        raise PaymentError(409, "Medio de reembolso no admitido")
                    refund.estado = "APROBADO"
                    refund.fecha_aprobacion = (datetime.fromtimestamp(self._field(remote, "created"), timezone.utc).replace(tzinfo=None)
                        if payment.proveedor == "STRIPE" and isinstance(self._field(remote, "created"), (int, float)) else self.now())
                    refund.id_usuario_responsable = user.id_usuario
                    refund.updated_at = self.now()
                # SessionLocal usa autoflush=False: persistir el estado antes
                # de consultar sumas y marcar el pago totalmente reembolsado.
                self.db.flush()
                if self.returns.reserved_money(payment.id_pago) == payment.monto:
                    # Solo los importes ya APROBADOS cuentan como dinero devuelto.
                    approved = self.db.scalar(select(func.coalesce(
                        func.sum(Refund.monto), 0)).where(
                            Refund.id_pago == payment.id_pago, Refund.estado == "APROBADO"))
                    if approved == payment.monto:
                        payment.estado = "REEMBOLSADO"
                        payment.updated_at = self.now()
            elif payment and (sale.total if row.tipo == "CANCELACION" else sum(d.importe_restitucion for d in details)) > 0:
                raise PaymentError(409, "Falta el reembolso autorizado")
            now = self.now()
            if row.fecha_resolucion is not None and now < row.fecha_resolucion:
                now = row.fecha_resolucion
            if row.tipo == "CANCELACION":
                if sale.stock_comprometido or sale.id_reserva is not None:
                    items = self.repository.items(sale.id_venta)
                    inventories = {i.id_variante_producto: i for i in self.staff.inventories(
                        sale.id_sucursal, [x.id_variante_producto for x in items], for_update=True)}
                    if not items:
                        raise PaymentError(409, "Venta sin detalles")
                    for item in items:
                        inv = inventories.get(item.id_variante_producto)
                        if inv is None or inv.stock_reservado < item.cantidad or inv.stock_reservado > inv.stock_actual:
                            raise PaymentError(409, "Stock comprometido inconsistente")
                        inv.stock_reservado -= item.cantidad
                        inv.updated_at = now
                if movement:
                    movement.estado = "ANULADO"
                    movement.updated_at = now
                sale.stock_comprometido = False
                sale.estado = "ANULADA"
                sale.updated_at = now
            else:
                sold = {x.id_variante_producto: x for x in self.repository.items(sale.id_venta)}
                for detail in details:
                    if self.returns.used(sale.id_venta, detail.id_variante_producto) > sold[detail.id_variante_producto].cantidad:
                        raise PaymentError(409, "Unidades devueltas inconsistentes")
                reintegrate = [x for x in details if x.cantidad_reintegrar > 0]
                if reintegrate and row.id_movimiento_inventario is None:
                    outbound = self.repository.lock_movement(sale.id_venta)
                    if outbound is None or outbound.estado != "CONFIRMADO" or outbound.tipo_movimiento != "VENTA":
                        raise PaymentError(409, "No existe salida fisica confirmada")
                    if assignment is None:
                        assignment = outbound.id_empleado_sucursal
                    if assignment is None:
                        raise PaymentError(403, "Se requiere personal asignado a la sucursal para registrar el movimiento de inventario")
                    inventories = {i.id_variante_producto: i for i in self.staff.inventories(
                        sale.id_sucursal, [x.id_variante_producto for x in reintegrate], for_update=True)}
                    for detail in reintegrate:
                        inv = inventories.get(detail.id_variante_producto)
                        if inv is None or inv.stock_actual < inv.stock_reservado:
                            raise PaymentError(409, "Inventario inexistente o inconsistente")
                        inv.stock_actual += detail.cantidad_reintegrar
                        inv.updated_at = now
                    empresa_id = getattr(sale, "empresa_id", None) or getattr(row, "empresa_id", None) or 1
                    entry = self.returns.add(
                        InventoryMovement,
                        empresa_id=empresa_id,
                        id_sucursal_destino=sale.id_sucursal,
                        id_empleado_sucursal=assignment,
                        tipo_movimiento="ENTRADA",
                        estado="CONFIRMADO",
                        motivo=f"Devolucion CU24 {return_id}",
                        fecha_movimiento=now,
                        created_at=now,
                        updated_at=now,
                    )
                    for detail in reintegrate:
                        self.returns.add(
                            InventoryMovementDetail,
                            empresa_id=empresa_id,
                            id_movimiento_inventario=entry.id_movimiento_inventario,
                            id_variante_producto=detail.id_variante_producto,
                            cantidad=detail.cantidad_reintegrar,
                        )
                    row.id_movimiento_inventario = entry.id_movimiento_inventario
            if row.id_usuario_resolutor is None:
                row.id_usuario_resolutor = user.id_usuario
            if row.fecha_resolucion is None:
                row.fecha_resolucion = now
            row.estado = "PROCESADA"
            row.fecha_procesamiento = now
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def confirm_exchange_difference(self, user, return_id):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede confirmar la diferencia de su propia solicitud")
            if row.tipo != "CAMBIO":
                raise PaymentError(409, "Esta operación es únicamente para solicitudes de tipo CAMBIO")
            if row.estado != "APROBADA":
                raise PaymentError(409, "La solicitud debe estar APROBADA para confirmar la diferencia definitiva")
            if not row.fecha_recepcion or not row.fecha_inspeccion:
                raise PaymentError(409, "La prenda debe haber sido recibida e inspeccionada físicamente antes de confirmar la diferencia")

            details = self.returns.details(return_id)
            if not details:
                raise PaymentError(409, "La solicitud de cambio no contiene detalles")

            repl_variant_ids = [d.id_variante_reemplazo for d in details if d.id_variante_reemplazo is not None]
            if len(repl_variant_ids) != len(details):
                raise PaymentError(409, "Cada línea de cambio debe especificar una variante de reemplazo válida")

            repl_variants = {
                v.id_variante_producto: v
                for v in self.db.scalars(
                    select(ProductVariant).where(ProductVariant.id_variante_producto.in_(repl_variant_ids))
                ).all()
            }
            prod_ids = [v.id_producto for v in repl_variants.values()]
            products = {
                p.id_producto: p
                for p in self.db.scalars(
                    select(Product).where(Product.id_producto.in_(prod_ids))
                ).all()
            }

            inventories_repl = {
                i.id_variante_producto: i
                for i in self.staff.inventories(sale.id_sucursal, repl_variant_ids, for_update=True)
            }

            now = self.now()
            total_original = Decimal("0.00")
            total_reemplazo = Decimal("0.00")

            for d in details:
                v = repl_variants.get(d.id_variante_reemplazo)
                if v is None or not v.estado:
                    raise PaymentError(409, f"La prenda de reemplazo #{d.id_variante_reemplazo} no está disponible o está inactiva")
                p = products.get(v.id_producto)
                if p is None or not p.estado:
                    raise PaymentError(409, f"El producto de reemplazo #{v.id_producto} no está activo en el catálogo")
                if getattr(v, "empresa_id", None) != sale.empresa_id:
                    raise PaymentError(403, "La prenda de reemplazo no pertenece a la misma empresa")

                inv = inventories_repl.get(d.id_variante_reemplazo)
                disponible = (inv.stock_actual - inv.stock_reservado) if inv else 0
                if disponible < d.cantidad_reemplazo:
                    raise PaymentError(
                        409,
                        f"Stock insuficiente para la prenda de reemplazo '{p.nombre}' (disponible: {disponible}, requerido: {d.cantidad_reemplazo})"
                    )

                precio_orig = d.precio_original_reconocido or Decimal("0.00")
                precio_repl = (p.precio * d.cantidad_reemplazo).quantize(Decimal("0.01"))
                d.precio_reemplazo_estimado = precio_repl
                d.diferencia_precio_estimada = precio_repl - precio_orig
                d.updated_at = now

                total_original += precio_orig
                total_reemplazo += precio_repl

            diferencia_definitiva = (total_reemplazo - total_original).quantize(Decimal("0.01"))
            row.diferencia_definitiva = diferencia_definitiva

            if diferencia_definitiva > Decimal("0.00"):
                if row.estado_pago_adicional != "CONFIRMADO":
                    row.estado_pago_adicional = "PENDIENTE"
            else:
                row.estado_pago_adicional = "NO_APLICA"
                row.monto_adicional_cobrado = Decimal("0.00")

            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def create_exchange_stripe_checkout(self, user, return_id, return_target="web"):
        def operation():
            sale, row = self._context_return(user, return_id, False)
            if row.id_usuario_solicitante != user.id_usuario:
                raise PaymentError(403, "No tiene permisos para pagar esta solicitud")
            if row.tipo != "CAMBIO":
                raise PaymentError(409, "Esta operación es únicamente para solicitudes de tipo CAMBIO")
            if row.estado != "APROBADA":
                raise PaymentError(409, "La solicitud debe estar APROBADA para pagar la diferencia")
            if row.diferencia_definitiva is None or row.diferencia_definitiva <= Decimal("0.00"):
                raise PaymentError(409, "La solicitud no tiene un cobro adicional pendiente")
            if row.estado_pago_adicional == "CONFIRMADO":
                raise PaymentError(409, "El pago de la diferencia ya fue confirmado previamente")

            details = self.returns.details(return_id)
            for d in details:
                if d.id_variante_reemplazo:
                    invs = self.staff.inventories(sale.id_sucursal, [d.id_variante_reemplazo])
                    inv = invs[0] if invs else None
                    disponible = (inv.stock_actual - inv.stock_reservado) if inv else 0
                    if disponible < d.cantidad_reemplazo:
                        raise PaymentError(409, "Stock insuficiente en la sucursal para la prenda de reemplazo")

            if row.stripe_session_id:
                session = self.stripe.retrieve_checkout_session(row.stripe_session_id)
                status = self._field(session, "status")
                payment_status = self._field(session, "payment_status")
                if status == "complete" and payment_status == "paid":
                    raise PaymentError(
                        409,
                        "El pago en Stripe ya fue completado para esta solicitud. Verifique y confirme el pago existente sin iniciar otro cobro."
                    )
                if status == "open" and payment_status == "unpaid":
                    return {
                        "session_id": self._field(session, "id"),
                        "url": self._field(session, "url"),
                    }

            key = uuid4()
            if return_target == "mobile":
                base = f"{settings.STRIPE_CHECKOUT_MOBILE_RETURN_BASE_URL}?id_venta={sale.id_venta}&return_id={row.id_devolucion}"
            else:
                base = f"{settings.STRIPE_CHECKOUT_RETURN_BASE_URL}/mis-compras/{sale.id_venta}?return_id={row.id_devolucion}"
            success_url = f"{base}&checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{base}&checkout=cancel"

            amount_cents = int((row.diferencia_definitiva * 100).to_integral_value())
            session = self.stripe.create_exchange_checkout_session(
                amount=amount_cents,
                currency=sale.moneda,
                sale_id=sale.id_venta,
                return_id=row.id_devolucion,
                key=key,
                success_url=success_url,
                cancel_url=cancel_url,
            )

            session_id = self._field(session, "id")
            row.stripe_session_id = session_id
            row.updated_at = self.now()
            self.db.flush()
            return {
                "session_id": session_id,
                "url": self._field(session, "url"),
            }
        return self._transaction(operation)

    def confirm_exchange_stripe_payment(self, user, return_id, payload=None, staff=False):
        def operation():
            sale, row = self._context_return(user, return_id, staff)
            if not staff and row.id_usuario_solicitante != user.id_usuario:
                raise PaymentError(403, "No tiene permisos para consultar esta solicitud")
            if row.tipo != "CAMBIO":
                raise PaymentError(409, "Esta operación es únicamente para solicitudes de tipo CAMBIO")
            if row.estado_pago_adicional == "CONFIRMADO":
                return self._data_return(row)
            if row.diferencia_definitiva is None or row.diferencia_definitiva <= Decimal("0.00"):
                raise PaymentError(409, "Esta solicitud no tiene cobro adicional pendiente")

            provided_session_id = (getattr(payload, "session_id", None) or "").strip()
            if provided_session_id and row.stripe_session_id and provided_session_id != row.stripe_session_id:
                raise PaymentError(409, "La sesión enviada no coincide con la sesión de Stripe registrada para esta solicitud")
            session_id = row.stripe_session_id or provided_session_id
            if not session_id:
                raise PaymentError(409, "No existe una sesión de Stripe Checkout asociada a esta solicitud")

            session = self.stripe.retrieve_checkout_session(session_id)
            if not session:
                raise PaymentError(409, "No se pudo recuperar la sesión de Stripe Checkout")

            if self._field(session, "livemode") is True:
                raise PaymentError(409, "La sesión de Stripe no pertenece al entorno TEST")

            status = self._field(session, "status")
            payment_status = self._field(session, "payment_status")
            if status != "complete" or payment_status != "paid":
                raise PaymentError(
                    409,
                    f"El pago en Stripe aún no está confirmado (estado: {status}, pago: {payment_status}). Complete la transacción antes de confirmar."
                )

            amount_received = self._field(session, "amount_total")
            expected_amount = int((row.diferencia_definitiva * 100).to_integral_value())
            if amount_received != expected_amount:
                raise PaymentError(409, f"El importe cobrado en Stripe ({amount_received}) no coincide con la diferencia calculada ({expected_amount})")

            currency = str(self._field(session, "currency", "") or "").lower()
            if currency and currency != (sale.moneda or "BOB").lower():
                raise PaymentError(409, "La moneda de la sesión Stripe no coincide con la moneda de la venta")

            meta = self._field(session, "metadata")
            meta_return_id = self._field(meta, "id_devolucion") if meta is not None else None
            meta_sale_id = self._field(meta, "id_venta") if meta is not None else None
            if meta_return_id and str(meta_return_id) != str(row.id_devolucion):
                raise PaymentError(403, "La sesión de Stripe no corresponde a esta solicitud de cambio")
            if meta_sale_id and str(meta_sale_id) != str(sale.id_venta):
                raise PaymentError(403, "La sesión de Stripe no corresponde a esta venta")

            pi = self._field(session, "payment_intent")
            pi_ref = pi if isinstance(pi, str) else (self._field(pi, "id") if pi is not None else None)
            if pi is not None and not isinstance(pi, str):
                pi_status = self._field(pi, "status")
                pi_amount_received = self._field(pi, "amount_received")
                if pi_status and pi_status != "succeeded":
                    raise PaymentError(409, f"El PaymentIntent en Stripe aún no figura como completado ({pi_status})")
                if pi_amount_received is not None and pi_amount_received != expected_amount:
                    raise PaymentError(409, "Stripe no recibió el importe completo en el PaymentIntent")

            now = self.now()
            row.stripe_session_id = self._field(session, "id") or session_id
            row.estado_pago_adicional = "CONFIRMADO"
            row.monto_adicional_cobrado = row.diferencia_definitiva
            row.medio_pago_adicional = "TARJETA"
            row.referencia_pago_adicional = pi_ref or session_id
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def confirm_exchange_store_payment(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede confirmar el pago de su propia solicitud")
            if row.tipo != "CAMBIO":
                raise PaymentError(409, "Esta operación es únicamente para solicitudes de tipo CAMBIO")
            if row.estado != "APROBADA":
                raise PaymentError(409, "La solicitud debe estar APROBADA para registrar el pago")
            if row.estado_pago_adicional == "CONFIRMADO":
                return self._data_return(row)
            if row.diferencia_definitiva is None or row.diferencia_definitiva <= Decimal("0.00"):
                raise PaymentError(409, "La solicitud no tiene un cobro adicional pendiente")

            medio = payload.medio_pago
            if medio not in {"EFECTIVO", "TARJETA", "QR"}:
                raise PaymentError(422, "Método de pago presencial inválido")

            ref = (payload.referencia_manual or "").strip()
            if medio in {"TARJETA", "QR"} and not ref:
                raise PaymentError(422, f"Para cobro en caja con {medio} debe ingresar el número de comprobante o referencia de la transacción confirmada")
            if medio == "EFECTIVO" and not ref:
                ref = f"EFECTIVO-CAJA-{user.id_usuario}"

            now = self.now()
            row.estado_pago_adicional = "CONFIRMADO"
            row.monto_adicional_cobrado = row.diferencia_definitiva
            row.medio_pago_adicional = medio
            row.referencia_pago_adicional = ref
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def process_exchange(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede procesar su propia solicitud")
            if row.estado == "PROCESADA":
                return self._data_return(row)
            if row.estado != "APROBADA":
                raise PaymentError(409, "Debe aprobar la solicitud antes de procesar el cambio")
            if row.tipo != "CAMBIO":
                raise PaymentError(409, "Esta operación es únicamente para solicitudes de tipo CAMBIO")
            details = self.returns.details(return_id)
            assignment = self._assignment(user, sale.id_sucursal)
            return self._process_exchange(user, sale, row, details, assignment, payload)
        return self._transaction(operation)

    def _process_exchange(self, user, sale, row, details, assignment, payload):
        if sale.estado != "COMPLETADA":
            raise PaymentError(409, "Solo se pueden procesar cambios de compras COMPLETADAS")
        if not row.fecha_recepcion or not row.fecha_inspeccion or not row.id_usuario_inspector:
            raise PaymentError(409, "La prenda debe haber sido recibida e inspeccionada físicamente antes de procesar el cambio")
        if not details:
            raise PaymentError(409, "La solicitud de cambio no contiene detalles")

        now = self.now()
        repl_variant_ids = [d.id_variante_reemplazo for d in details if d.id_variante_reemplazo is not None]
        if len(repl_variant_ids) != len(details):
            raise PaymentError(409, "Cada línea de cambio debe especificar una variante de reemplazo válida")

        repl_variants = {
            v.id_variante_producto: v
            for v in self.db.scalars(
                select(ProductVariant).where(ProductVariant.id_variante_producto.in_(repl_variant_ids))
            ).all()
        }
        prod_ids = [v.id_producto for v in repl_variants.values()]
        products = {
            p.id_producto: p
            for p in self.db.scalars(
                select(Product).where(Product.id_producto.in_(prod_ids))
            ).all()
        }

        inventories_repl = {
            i.id_variante_producto: i
            for i in self.staff.inventories(sale.id_sucursal, repl_variant_ids, for_update=True)
        }

        total_original = Decimal("0.00")
        total_reemplazo = Decimal("0.00")

        for d in details:
            v = repl_variants.get(d.id_variante_reemplazo)
            if v is None or not v.estado:
                raise PaymentError(409, f"La prenda de reemplazo #{d.id_variante_reemplazo} no está disponible o está inactiva")
            p = products.get(v.id_producto)
            if p is None or not p.estado:
                raise PaymentError(409, f"El producto de reemplazo #{v.id_producto} no está activo en el catálogo")
            if getattr(v, "empresa_id", None) != sale.empresa_id:
                raise PaymentError(403, "La prenda de reemplazo no pertenece a la misma empresa")

            inv = inventories_repl.get(d.id_variante_reemplazo)
            disponible = (inv.stock_actual - inv.stock_reservado) if inv else 0
            if disponible < d.cantidad_reemplazo:
                raise PaymentError(
                    409,
                    f"Stock insuficiente para la prenda de reemplazo '{p.nombre}' (disponible: {disponible}, requerido: {d.cantidad_reemplazo})"
                )

            precio_orig = d.precio_original_reconocido or Decimal("0.00")
            precio_repl = (p.precio * d.cantidad_reemplazo).quantize(Decimal("0.01"))
            d.precio_reemplazo_estimado = precio_repl
            d.diferencia_precio_estimada = precio_repl - precio_orig
            d.updated_at = now

            total_original += precio_orig
            total_reemplazo += precio_repl

        diferencia_definitiva = (total_reemplazo - total_original).quantize(Decimal("0.01"))
        row.diferencia_definitiva = diferencia_definitiva

        if diferencia_definitiva > Decimal("0.00"):
            cobro_adicional = diferencia_definitiva
            if row.estado_pago_adicional == "CONFIRMADO":
                cobro_adicional = row.monto_adicional_cobrado or diferencia_definitiva
            else:
                medio_pago = getattr(payload, "medio_pago", None)
                if not medio_pago or medio_pago not in {"EFECTIVO", "QR", "TARJETA"}:
                    raise PaymentError(422, "Debe seleccionar un método de pago en caja para el cobro adicional (EFECTIVO, QR o TARJETA)")
                ref = (getattr(payload, "referencia_manual", None) or "").strip()
                if medio_pago in {"QR", "TARJETA"} and not ref:
                    raise PaymentError(422, f"Para cobro adicional con {medio_pago} debe ingresar el número de comprobante o referencia de la transacción confirmada")
                if medio_pago == "EFECTIVO" and not ref:
                    ref = f"EFECTIVO-CAJA-{user.id_usuario}"
                row.monto_adicional_cobrado = cobro_adicional
                row.medio_pago_adicional = medio_pago
                row.referencia_pago_adicional = ref if ref else None
                row.estado_pago_adicional = "CONFIRMADO"

        elif diferencia_definitiva < Decimal("0.00"):
            row.estado_pago_adicional = "NO_APLICA"
            saldo_a_favor = abs(diferencia_definitiva)
            row.monto_adicional_cobrado = Decimal("0.00")
            original_payment = self._paid(sale)
            if original_payment is None:
                raise PaymentError(409, "No existe pago aprobado asociado a la compra original para reembolsar saldo a favor")
            if saldo_a_favor + self.returns.reserved_money(original_payment.id_pago) > original_payment.monto:
                raise PaymentError(409, "El saldo a favor supera el importe efectivamente pagado por la compra original")

            ref = (getattr(payload, "referencia_manual", None) or "").strip()
            if original_payment.proveedor == "STRIPE":
                refunds = self.returns.refunds(row.id_devolucion)
                refund = refunds[0] if refunds else None
                if not refund:
                    refund = self.returns.add(
                        Refund, id_venta=sale.id_venta, id_pago=original_payment.id_pago,
                        id_devolucion=row.id_devolucion, estado="PENDIENTE", monto=saldo_a_favor,
                        clave_idempotencia=uuid4(), created_at=now, updated_at=now
                    )
                    self.db.flush()
                remote = self._stripe_refund(sale, original_payment, refund)
                refund.referencia_externa = remote["id"]
                refund.updated_at = now
                if remote["status"] == "succeeded":
                    refund.estado = "APROBADO"
                    refund.fecha_aprobacion = now
                    refund.id_usuario_responsable = user.id_usuario
                elif remote["status"] in {"failed", "canceled"}:
                    refund.estado = "RECHAZADO"
            else:
                if not ref:
                    raise PaymentError(422, "Debe registrar comprobante o referencia para la devolución del saldo a favor en caja")
                refunds = self.returns.refunds(row.id_devolucion)
                if refunds:
                    refund = refunds[0]
                    refund.monto = saldo_a_favor
                    refund.estado = "APROBADO"
                    refund.referencia_externa = ref
                    refund.id_usuario_responsable = user.id_usuario
                    refund.fecha_aprobacion = now
                    refund.updated_at = now
                else:
                    self.returns.add(
                        Refund, id_venta=sale.id_venta, id_pago=original_payment.id_pago,
                        id_devolucion=row.id_devolucion, estado="APROBADO", monto=saldo_a_favor,
                        clave_idempotencia=uuid4(), referencia_externa=ref,
                        id_usuario_responsable=user.id_usuario, fecha_aprobacion=now,
                        created_at=now, updated_at=now
                    )
        else:
            row.monto_adicional_cobrado = Decimal("0.00")
            row.medio_pago_adicional = None
            row.referencia_pago_adicional = None

        reintegrar_param = getattr(payload, "reintegrar_stock_original", None)
        es_apta = (row.estado_fisico == "OPTIMO" and bool(row.etiquetas_intactas)) if reintegrar_param is None else bool(reintegrar_param)

        if es_apta:
            orig_variant_ids = [d.id_variante_producto for d in details]
            inventories_orig = {
                i.id_variante_producto: i
                for i in self.staff.inventories(sale.id_sucursal, orig_variant_ids, for_update=True)
            }
            entry_mov = self.returns.add(
                InventoryMovement, id_sucursal_destino=sale.id_sucursal,
                id_empleado_sucursal=assignment, tipo_movimiento="ENTRADA", estado="CONFIRMADO",
                motivo=f"Cambio CU17 SOL-{row.id_devolucion:05d} - Entrada prenda original",
                fecha_movimiento=now, created_at=now, updated_at=now
            )
            self.db.flush()
            for d in details:
                inv_o = inventories_orig.get(d.id_variante_producto)
                if inv_o is not None:
                    inv_o.stock_actual += d.cantidad
                    inv_o.updated_at = now
                d.cantidad_reintegrar = d.cantidad
                self.returns.add(
                    InventoryMovementDetail,
                    id_movimiento_inventario=entry_mov.id_movimiento_inventario,
                    id_variante_producto=d.id_variante_producto,
                    cantidad=d.cantidad,
                )
        else:
            for d in details:
                d.cantidad_reintegrar = 0

        salida_mov = self.returns.add(
            InventoryMovement, id_sucursal_origen=sale.id_sucursal,
            id_empleado_sucursal=assignment, tipo_movimiento="SALIDA", estado="CONFIRMADO",
            motivo=f"Cambio CU17 SOL-{row.id_devolucion:05d} - Salida prenda reemplazo",
            fecha_movimiento=now, created_at=now, updated_at=now
        )
        self.db.flush()
        for d in details:
            inv_r = inventories_repl[d.id_variante_reemplazo]
            inv_r.stock_actual -= d.cantidad_reemplazo
            inv_r.updated_at = now
            self.returns.add(
                InventoryMovementDetail,
                id_movimiento_inventario=salida_mov.id_movimiento_inventario,
                id_variante_producto=d.id_variante_reemplazo,
                cantidad=d.cantidad_reemplazo,
            )

        row.id_movimiento_inventario = salida_mov.id_movimiento_inventario
        row.estado = "PROCESADA"
        row.fecha_procesamiento = now
        row.fecha_entrega_reemplazo = now
        row.id_usuario_resolutor = user.id_usuario
        row.updated_at = now
        self.db.flush()
        return self._data_return(row)
