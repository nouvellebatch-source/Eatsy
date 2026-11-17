# Eatsy POS restaurante

Aplicación React para personal autorizado del restaurante. La sesión permanece en memoria y se pierde al recargar o cerrar la página.

```powershell
cd pos_restaurante
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Abre la dirección que muestra Vite e inicia sesión con un usuario del restaurante. El gerente y el POS de La Santa pueden acceder según sus membresías. La API debe tener `ORDERS_ENABLED=true`. La comanda consulta los últimos 100 pedidos cada 15 segundos; los botones actualizan el estado con la API. El gerente o cajero puede registrar manualmente que recibió el efectivo; no se realiza ninguna transferencia electrónica.

Opcionalmente copia `.env.example` como `.env.local` y ajusta `VITE_EATSY_API_URL`. No coloques credenciales en variables `VITE_`, ya que son públicas en el navegador.

Para alojar el POS en un dominio web, agrega su origen exacto a `CORS_ORIGINS` de la API en Render. El soporte de desarrollo local está configurado para localhost y 127.0.0.1. Sirve `dist/` a través de HTTPS; `npm run build` crea esa carpeta.

## Despliegue en Coolify

El POS se publica como una imagen Docker estática, servida por Nginx en el puerto interno `8080`. El proxy de Coolify se encarga de HTTPS y del dominio: no expongas puertos del servidor manualmente.

1. Sube el contenido de este proyecto a un repositorio Git, incluyendo `Dockerfile` y `nginx.conf`. Si el repositorio contiene toda la carpeta `eatsy_flutter`, configura en Coolify el **Base directory** como `/pos_restaurante`; si contiene solo el POS, déjalo en `/`.
2. En Coolify crea un recurso **Application** desde ese repositorio y elige **Dockerfile** como tipo de compilación. Deja el Dockerfile en `Dockerfile` y el puerto publicado en `8080`.
3. Añade una variable de compilación (Build Variable): `VITE_EATSY_API_URL=https://api.tu-dominio.com`. No uses una URL interna como `http://api:8000`: el navegador del cajero debe poder llegar a esa dirección. Las variables `VITE_` son visibles en el bundle, por lo que nunca deben contener contraseñas, tokens ni claves.
4. Asigna, por ejemplo, `pos.tu-dominio.com` al recurso y despliega. Coolify emitirá el certificado TLS si el DNS A/AAAA del subdominio ya apunta al servidor.
5. En la API configura `CORS_ORIGINS=https://pos.tu-dominio.com` (sin barra final) y `ORDERS_ENABLED=true`, y vuelve a desplegar/reiniciar la API. Si conservas la API en Render, estos valores se definen allí; si también la llevas a Coolify, se definen como variables de ese servicio.

Después del despliegue comprueba el acceso, inicia sesión con una cuenta de restaurante y confirma que se cargan pedidos y que una transición de estado se guarda. Si la API usa Aiven, mantén sus credenciales solo en el servicio de API, nunca en el POS.

## Registro y vinculación al restaurante

1. En la pantalla de acceso selecciona **Crear mi cuenta**, completa los datos y confirma el código que llega por correo. El registro usa la API existente y requiere que Brevo esté configurado y funcionando en Render.
2. La cuenta verificada se crea sin acceso a ningún restaurante. El administrador de Eatsy debe verificar la relación de la persona con el restaurante y ejecutar, desde `api_python` con acceso MySQL:

```powershell
..\venv\Scripts\python.exe -m app.cli assign-restaurant-role --usuario USUARIO --restaurante la-santa-pizza-bar-grill --rol cashier
```

Los roles disponibles son `owner`, `cashier`, `kitchen` y `courier`. El comando exige que el correo esté verificado y no modifica una membresía existente ni cambia el rol global de la cuenta. El POS permite consultar pedidos a `owner`, `cashier` y `kitchen`; `courier` no accede a la comanda. Después la persona puede iniciar sesión.

Este flujo vincula personal a restaurantes existentes. Todavía no crea automáticamente restaurantes nuevos ni envía solicitudes de vinculación al administrador.

El mapa muestra pedidos activos por mesa, no confirma la ocupación física. Los clientes crean sus reservas desde Flutter; el POS las consulta y puede cancelarlas. Las reservas evitan horarios superpuestos en una misma mesa y utilizan la zona horaria del dispositivo.

El gerente puede crear promociones porcentuales y eventos con fecha de inicio y fin. Los códigos vigentes se muestran en Flutter y la API calcula el descuento al registrar el pedido. Finanzas suma únicamente importes de pagos en efectivo confirmados, usando la fecha de confirmación en hora de Colombia. No calcula gastos, devoluciones ni utilidades. Los indicadores de inicio solo cubren los 100 pedidos consultados. La imagen de portada es ilustrativa.
