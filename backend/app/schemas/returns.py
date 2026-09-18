from typing import Annotated, Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

class CancellationRequest(StrictRequest):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

class ReturnLine(StrictRequest):
    id_detalle_venta: int = Field(gt=0)
    cantidad: int = Field(gt=0, strict=True)

class ReturnRequest(CancellationRequest):
    lineas: list[ReturnLine] = Field(min_length=1, max_length=100)
    @model_validator(mode="after")
    def unique(self):
        if len({x.id_detalle_venta for x in self.lineas}) != len(self.lineas):
            raise ValueError("Lineas duplicadas")
        return self

class ReviewLine(StrictRequest):
    id_variante_producto: int = Field(gt=0)
    cantidad_reintegrar: int = Field(ge=0, strict=True)
    importe_restitucion: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

class ReviewRequest(StrictRequest):
    resultado: Literal["APROBADA", "RECHAZADA"]
    lineas: list[ReviewLine] = Field(default_factory=list, max_length=100)

class ProcessRequest(StrictRequest):
    referencia_manual: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None

class ReturnResponse(BaseModel):
    success: bool = True
    data: dict

class ReturnListResponse(BaseModel):
    success: bool = True
    data: list[dict]
