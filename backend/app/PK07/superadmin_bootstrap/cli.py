"""CLI manual para verificar o aplicar el bootstrap de SUPERADMIN.

Ejemplos:
    python -m app.PK07.superadmin_bootstrap.cli --email admin@dominio.com
    python -m app.PK07.superadmin_bootstrap.cli --email admin@dominio.com \
        --confirm-email admin@dominio.com --apply
"""

import argparse

from app.core.database import SessionLocal
from app.PK07.superadmin_bootstrap.service import (
    BootstrapRoleNotConfiguredError,
    BootstrapUserInactiveError,
    BootstrapUserNotEligibleError,
    BootstrapUserNotFoundError,
    InvalidBootstrapEmailError,
    SuperadminBootstrapPersistenceError,
    SuperadminBootstrapService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verifica o asigna SUPERADMIN a una cuenta ADMINISTRADOR existente."
    )
    parser.add_argument("--email", required=True, help="Correo exacto de la cuenta existente")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica el cambio; sin esta opciÃ³n solo verifica elegibilidad",
    )
    parser.add_argument(
        "--confirm-email",
        help="Debe coincidir con --email cuando se utiliza --apply",
    )
    return parser


def run(*, email: str, confirm_email: str | None, apply: bool) -> int:
    try:
        normalized_email = SuperadminBootstrapService.normalize_email(email)
        if apply:
            if confirm_email is None:
                print("ERROR: --confirm-email es obligatorio con --apply")
                return 2
            normalized_confirmation = SuperadminBootstrapService.normalize_email(
                confirm_email
            )
            if normalized_confirmation != normalized_email:
                print("ERROR: --confirm-email no coincide con --email")
                return 2

        with SessionLocal() as db:
            service = SuperadminBootstrapService(db)
            result = (
                service.assign(normalized_email)
                if apply
                else service.check(normalized_email)
            )
        print(f"status={result.status}")
        print(f"user_id={result.user_id}")
        print(f"email={result.email}")
        if not apply and result.status == "ELIGIBLE":
            print("dry_run=true")
        return 0
    except InvalidBootstrapEmailError:
        print("ERROR: correo invÃ¡lido")
    except BootstrapUserNotFoundError:
        print("ERROR: la cuenta no existe")
    except BootstrapUserInactiveError:
        print("ERROR: la cuenta estÃ¡ inactiva")
    except BootstrapRoleNotConfiguredError:
        print("ERROR: el rol SUPERADMIN no estÃ¡ activo o configurado")
    except BootstrapUserNotEligibleError:
        print("ERROR: la cuenta no es un ADMINISTRADOR empresarial activo")
    except SuperadminBootstrapPersistenceError:
        print("ERROR: no fue posible asignar SUPERADMIN")
    return 1


def main() -> None:
    arguments = build_parser().parse_args()
    raise SystemExit(
        run(
            email=arguments.email,
            confirm_email=arguments.confirm_email,
            apply=arguments.apply,
        )
    )


if __name__ == "__main__":
    main()
