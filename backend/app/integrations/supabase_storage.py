"""Cliente minimo para almacenar imagenes publicas en Supabase Storage."""

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from app.core.config import settings


STORAGE_TIMEOUT_SECONDS = 20


class SupabaseStorageConfigurationError(Exception):
    """Falta o es invalida la configuracion privada de Storage."""


class SupabaseStorageUploadError(Exception):
    """Supabase Storage no pudo persistir el objeto."""


@dataclass(frozen=True)
class StoredObject:
    """Referencia al objeto persistido y a su URL publica."""

    path: str
    public_url: str


class SupabaseStorageClient:
    """Opera contra la API REST de Storage solo desde el backend."""

    def __init__(self, *, base_url: str, service_role_key: str, bucket: str) -> None:
        normalized_url = base_url.strip().rstrip("/")
        parsed_url = urlsplit(normalized_url)
        normalized_bucket = bucket.strip()
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise SupabaseStorageConfigurationError("SUPABASE_URL no es valida")
        if not service_role_key.strip():
            raise SupabaseStorageConfigurationError(
                "SUPABASE_SERVICE_ROLE_KEY no esta configurada"
            )
        if (
            not normalized_bucket
            or "/" in normalized_bucket
            or "\\" in normalized_bucket
        ):
            raise SupabaseStorageConfigurationError(
                "SUPABASE_STORAGE_BUCKET no es valido"
            )
        self.base_url = normalized_url
        self.service_role_key = service_role_key
        self.bucket = normalized_bucket

    @classmethod
    def from_settings(cls) -> "SupabaseStorageClient":
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", settings.SUPABASE_URL),
                ("SUPABASE_SERVICE_ROLE_KEY", settings.SUPABASE_SERVICE_ROLE_KEY),
                ("SUPABASE_STORAGE_BUCKET", settings.SUPABASE_STORAGE_BUCKET),
            )
            if value is None or not str(value).strip()
        ]
        if missing:
            raise SupabaseStorageConfigurationError(
                f"Falta configurar {', '.join(missing)}"
            )
        return cls(
            base_url=settings.SUPABASE_URL or "",
            service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
            bucket=settings.SUPABASE_STORAGE_BUCKET or "",
        )

    def upload_public_image(
        self, *, object_path: str, content: bytes, content_type: str
    ) -> StoredObject:
        encoded_bucket = quote(self.bucket, safe="")
        encoded_path = quote(object_path, safe="/")
        request = Request(
            f"{self.base_url}/storage/v1/object/{encoded_bucket}/{encoded_path}",
            data=content,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": content_type,
                "cache-control": "31536000",
                "x-upsert": "false",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=STORAGE_TIMEOUT_SECONDS) as response:
                if response.status not in {200, 201}:
                    raise SupabaseStorageUploadError
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise SupabaseStorageUploadError from error

        public_url = (
            f"{self.base_url}/storage/v1/object/public/"
            f"{encoded_bucket}/{encoded_path}"
        )
        return StoredObject(path=object_path, public_url=public_url)

    def remove(self, object_path: str) -> None:
        """Intenta compensar una carga si luego falla la escritura en PostgreSQL."""
        encoded_bucket = quote(self.bucket, safe="")
        encoded_path = quote(object_path, safe="/")
        request = Request(
            f"{self.base_url}/storage/v1/object/{encoded_bucket}/{encoded_path}",
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
            },
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=STORAGE_TIMEOUT_SECONDS):
                return
        except (HTTPError, URLError, TimeoutError, OSError):
            return
