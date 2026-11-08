from typing import Annotated, Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DeliveryModality = Literal["ENTREGA_EN_TIENDA", "DELIVERY_SIMULADO"]
RequestKind = Literal["DEVOLUCION", "CAMBIO"]

class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

class CancellationRequest(StrictRequest):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

class ReturnLine(StrictRequest):
    id_detalle_venta: int = Field(gt=0)
    cantidad: int = Field(gt=0, strict=True)
    id_variante_reemplazo: int | None = Field(default=None, gt=0)
    cantidad_reemplazo: int | None = Field(default=None, gt=0, strict=True)

class ReturnRequest(CancellationRequest):
    tipo: RequestKind | None = None
    modalidad_entrega: DeliveryModality | None = None
    lineas: list[ReturnLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({x.id_detalle_venta for x in self.lineas}) != len(self.lineas):
            raise ValueError("Lineas duplicadas")
        has_replacement = [x.id_variante_reemplazo is not None for x in self.lineas]
        if self.tipo is None:
            if all(has_replacement):
                self.tipo = "CAMBIO"
            elif not any(has_replacement):
                self.tipo = "DEVOLUCION"
            else:
                raise ValueError("No se puede mezclar lineas de cambio y devolucion en una misma solicitud")
        if self.tipo == "CAMBIO":
            if not all(has_replacement):
                raise ValueError("Para CAMBIO debe indicar id_variante_reemplazo en cada linea")
            for line in self.lineas:
                if line.cantidad_reemplazo is not None and line.cantidad_reemplazo != line.cantidad:
                    raise ValueError("La cantidad de reemplazo debe coincidir con la cantidad solicitada")
        else:
            if any(has_replacement) or any(x.cantidad_reemplazo is not None for x in self.lineas):
                raise ValueError("DEVOLUCION no admite variante de reemplazo")
        return self

class ExchangeRequest(ReturnRequest):
    tipo: Literal["CAMBIO"] = "CAMBIO"

class ReviewLine(StrictRequest):
    id_variante_producto: int = Field(gt=0)
    cantidad_reintegrar: int = Field(ge=0, strict=True)
    importe_restitucion: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

class ReviewRequest(StrictRequest):
    resultado: Literal["APROBADA", "RECHAZADA"]
    lineas: list[ReviewLine] = Field(default_factory=list, max_length=100)

class InitialReviewRequest(StrictRequest):
    resultado: Literal["ACEPTADA", "RECHAZADA"]
    motivo_rechazo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def validate_rejection_reason(self):
        if self.resultado == "RECHAZADA" and not self.motivo_rechazo:
            raise ValueError("El motivo de rechazo es obligatorio al rechazar la solicitud")
        return self

class DeliveryModalitySelectionRequest(StrictRequest):
    modalidad_entrega: DeliveryModality

class ReceiveItemRequest(StrictRequest):
    observaciones: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

class InspectionRequest(StrictRequest):
    resultado: Literal["APROBADA", "RECHAZADA"]
    estado_fisico: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    etiquetas_intactas: bool
    correspondencia_compra: bool
    observaciones: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    motivo_rechazo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def validate_rejection_reason(self):
        if self.resultado == "RECHAZADA" and not self.motivo_rechazo:
            raise ValueError("El motivo de rechazo es obligatorio al rechazar la solicitud")
        return self

class ProcessRequest(StrictRequest):
    referencia_manual: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None
    medio_pago: Literal["EFECTIVO", "QR", "TARJETA"] | None = None
    reintegrar_stock_original: bool | None = None

class ProcessExchangeRequest(StrictRequest):
    medio_pago: Literal["EFECTIVO", "QR", "TARJETA"] | None = None
    referencia_manual: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None
    reintegrar_stock_original: bool | None = None

class ConfirmPaymentRequest(StrictRequest):
    medio_pago: Literal["EFECTIVO", "QR", "TARJETA"]
    referencia_manual: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None

class StripeConfirmRequest(StrictRequest):
    session_id: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None

class CheckoutSessionResponse(BaseModel):
    success: bool = True
    data: dict

class ReturnResponse(BaseModel):
    success: bool = True
    data: dict

class ReturnListResponse(BaseModel):
    success: bool = True
    data: list[dict]
