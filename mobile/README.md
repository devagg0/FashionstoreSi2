# FashionStore Mobile

Infraestructura Flutter para consumir la API FastAPI de FashionStore. La URL
se define en compilación mediante `API_URL`; no es necesario editar archivos
Dart al cambiar de entorno.

## Configuración de la API

`ApiConfig` usa `http://10.0.2.2:8000` por defecto en debug para el emulador
Android. También se puede indicar cualquier entorno explícitamente:

```powershell
flutter run -d emulator-5554 --dart-define=API_URL=http://10.0.2.2:8000
```

Una compilación release exige HTTPS. Para generar la APK conectada a Render:

```powershell
flutter build apk --release --dart-define=API_URL=https://fashionstoresi2.onrender.com
```

No agregue `/health` ni otra ruta a `API_URL`: debe contener solo el origen del
backend, sin query parameters ni fragmentos.

## Celular Android físico

Hay dos alternativas para desarrollo:

1. Con el teléfono y el PC en la misma red, inicie FastAPI escuchando en todas
   las interfaces y use la IPv4 local del PC (por ejemplo, `192.168.1.50`):

   ```powershell
   flutter run -d DEVICE_ID --dart-define=API_URL=http://192.168.1.50:8000
   ```

   El firewall debe permitir el puerto 8000. La IP debe obtenerse con
   `ipconfig`; el ejemplo no es una dirección fija del proyecto.

2. Con USB y depuración USB habilitada, redirija el puerto mediante ADB. En
   este caso `127.0.0.1` en el teléfono llega al puerto 8000 del PC:

   ```powershell
   adb reverse tcp:8000 tcp:8000
   flutter run -d DEVICE_ID --dart-define=API_URL=http://127.0.0.1:8000
   ```

`localhost` y `127.0.0.1` siempre representan el dispositivo donde se ejecuta
la app. En el emulador no representan el PC; `10.0.2.2` es el alias especial
del emulador Android para el host. Una IP LAN identifica al PC dentro de la red
local. La URL de Render identifica el backend público y usa HTTPS.

El manifest principal permite Internet pero bloquea HTTP. El manifest de debug
habilita cleartext para las URLs locales anteriores; la APK release permanece
restringida a HTTPS.

## Token y servicio HTTP

`SecureTokenStorage` guarda, obtiene y elimina el JWT mediante
`flutter_secure_storage` (almacenamiento cifrado respaldado por Android
Keystore). `ApiService` agrega automáticamente `Authorization: Bearer <token>`
cuando existe un token. Para login, registro y endpoints públicos se debe usar
`includeAuth: false`.

El servicio central soporta GET, POST, PATCH y DELETE, JSON, headers, query
parameters, timeout y errores tipados. Debe cerrarse con `close()` cuando deje
de utilizarse.

## Comprobaciones

Prueba real y segura contra el endpoint público `/health` de Render:

```powershell
flutter test test/live_api_connectivity_test.dart --dart-define=RUN_LIVE_API_TEST=true --dart-define=API_URL=https://fashionstoresi2.onrender.com
```

Validaciones del proyecto:

```powershell
flutter analyze
flutter test
flutter build apk --debug --dart-define=API_URL=http://10.0.2.2:8000
```
