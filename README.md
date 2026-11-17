# Eatsy

Centro de desarrollo en restaurantes y gastrobares.

## API Python de Eatsy — MySQL

Esta API utiliza únicamente MySQL de Aiven. Incluye JWT, roles, catálogo de productos y auditoría de peticiones.

```powershell
cd api_python
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init
python -m app.cli create-user --usuario admin --nombre Nombre --apellido Apellido --rol admin
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En `.env` y en Render define los valores reales de Aiven y JWT: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL`, `DB_SSL_CA` y `JWT_SECRET_KEY`.

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
