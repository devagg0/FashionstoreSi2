"""Ejecutar desde backend: python -m scripts.verify_stripe_test."""

from pydantic import ValidationError


def main() -> int:
    try:
        from app.services.stripe_service import StripeService

        StripeService().verify_test_connection()
    except ValidationError:
        print("Configuracion invalida: se requieren modo y claves Stripe TEST.")
        return 1
    except Exception:
        # Nunca imprimir excepciones del SDK: pueden incluir credenciales.
        print("No se pudo verificar Stripe TEST. No se creo ningun recurso.")
        return 1
    print("Stripe TEST verificado: GET /v1/balance, livemode=false. Sin pagos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
