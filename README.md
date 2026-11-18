# Eatsy

Centro de desarrollo en restaurantes y gastrobares: API en Python, panel de
gestión web y app móvil para clientes.

## Estructura del repositorio

| Ruta | Qué es |
| --- | --- |
| `app/` | API FastAPI (MySQL/Aiven, JWT, roles, catálogo, pedidos, reservas y auditoría). |
| `tests/` | Pruebas del backend con `unittest` (no necesitan base de datos). |
| `panel/` | Panel de gestión web en HTML, CSS y JavaScript, empaquetado con Vite. |
| `mobile/` | App Flutter de clientes (`lib/main.dart`). |
| `Dockerfile`, `nginx.conf` | Imagen del panel: Vite compila y nginx sirve la SPA en el puerto 8080. |

## API Python de Eatsy — MySQL

Esta API utiliza únicamente MySQL de Aiven. Incluye JWT, roles, catálogo de productos y auditoría de peticiones.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init
python -m app.cli create-user --usuario admin --nombre Nombre --apellido Apellido --rol admin
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En Windows también puedes usar los accesos directos de la raíz: `iniciar_api.cmd`
arranca la API (genera el secreto JWT la primera vez), `poblar_datos.cmd` crea
los datos de prueba y `correr_pruebas.cmd` ejecuta las pruebas.

En `.env` y en Render define los valores reales de Aiven y JWT: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL`, `DB_SSL_CA` y `JWT_SECRET_KEY`.

## Datos de prueba

`python -m app.seed_demo` (o `poblar_datos.cmd`) crea, si no existen, el
restaurante "Eatsy Demo" con la sucursal "Sede Centro", siete productos de menú
con fotos, un usuario `admin.eatsy` con membresía owner y un usuario
`cliente.eatsy` con correo verificado. Es idempotente y muestra las contraseñas
una sola vez; también acepta `DEMO_ADMIN_PASS` y `DEMO_CLIENT_PASS`.

## Panel de gestión web

El panel vive en `panel/` y consume la misma API. En desarrollo:

```sh
cd panel
npm install
npm run dev
```

Queda en `http://127.0.0.1:5500` (el CORS de la API acepta cualquier puerto de
`localhost`/`127.0.0.1`). La URL de la API se puede fijar al compilar con
`VITE_EATSY_API_URL` (ver `panel/.env.example`); si no se define, el panel usa
`http://127.0.0.1:8000` y permite cambiarla desde la pantalla de login.

Para producción, `docker build -t eatsy-panel .` compila el panel con Vite y lo
sirve con nginx en el puerto 8080. El panel también funciona sin Node si se
sirve `panel/` con cualquier servidor estático (por ejemplo Live Server).
Recuerda agregar el dominio público del panel a `CORS_ORIGINS` en el entorno de
la API; en local ya se aceptan todos los puertos de `localhost` y `127.0.0.1`.

## App móvil Flutter

```sh
cd mobile
flutter pub get
flutter run
```

En el emulador Android la API se ve en `http://10.0.2.2:8000`; para un celular
físico usa `flutter run --dart-define=EATSY_API_URL=http://IP_DE_TU_PC:8000`.
Detalles en `mobile/README.md`.

## Verificación de correo con Brevo

Configura `BREVO_API_KEY` y `CORREO_REMITENTE` en el entorno del servidor. El remitente debe estar registrado y verificado en Brevo y la cuenta debe poder enviar correos transaccionales. No guardes la clave en Git. `EMAIL_VERIFICATION_ENABLED` queda desactivado por defecto: el acceso existente sigue funcionando por usuario y el registro público responde 503 hasta activar el flujo nuevo.

Antes de desplegar esta versión, haz una copia de seguridad de MySQL y ejecuta la migración una sola vez sobre la base correcta:

```powershell
python -m app.cli migrate-customers
```

La migración crea las tablas de registros pendientes, correos verificados, límites de envío y verificación de acceso, y amplía la restricción de roles para incluir `customer`. No convierte ni elimina usuarios existentes. Las cuentas existentes sin correo verificado mantienen su acceso anterior, pero no pueden utilizar el desbloqueo por correo hasta contar con una vinculación verificada.

Tras completar la migración y configurar Brevo, establece `EMAIL_VERIFICATION_ENABLED=true` y reinicia el servicio. Valida primero en un entorno de pruebas.

`POST /auth/registro` inicia el registro y envía un código de seis dígitos válido por diez minutos. `POST /auth/verificar-correo` crea el usuario cliente. Después de cinco contraseñas incorrectas, un cliente con correo verificado debe solicitar y confirmar un código mediante `/auth/codigo-acceso` y `/auth/verificar-acceso`; luego debe iniciar sesión con su contraseña. El reenvío tiene una espera de un minuto y los códigos admiten hasta cinco intentos.

Prueba el flujo completo en un entorno de pruebas antes de desplegarlo: envío, recepción, expiración, reenvío, códigos erróneos, bloqueo y desbloqueo, así como el acceso de cuentas antiguas. Los límites de envío dependen de identificar correctamente la IP del cliente en el proxy de producción.

## Catálogo y pedidos en efectivo (en construcción)

El esquema incorpora restaurantes, sucursales, productos de menú, pedidos, artículos, membresías y eventos de cocina. La inicialización del esquema debe realizarse en una base de pruebas antes de aplicarla a la base existente; `init` crea tablas que faltan, pero no migra columnas de tablas existentes.

`POST /pedidos` está desactivado por defecto mediante `ORDERS_ENABLED=false`. Su implementación calcula los precios desde la base, asocia el pedido a un cliente y una sucursal, y deja el pago en efectivo pendiente. La creación de domicilios continúa deshabilitada mientras no exista cálculo de entrega y asignación de domiciliarios. No habilitar en producción hasta completar catálogo, permisos, POS, migraciones y pruebas integrales.

Los miembros autorizados de cada restaurante pueden consultar sus pedidos y registrar transiciones de cocina mediante `/gestion/restaurantes/{restaurant_id}/pedidos`. Los clientes pueden consultar su propio pedido e historial de estados. Estos endpoints no proporcionan todavía comunicaciones en tiempo real, registro de cobro en efectivo ni integración con Flutter.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

En el panel: `cd panel && npm run build` para comprobar que compila. En la app:
`cd mobile && flutter analyze && flutter test`.
