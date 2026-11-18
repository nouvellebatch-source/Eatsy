# Anexos técnicos de Eatsy

Scripts extraídos del esquema local de la API el 18 de noviembre de 2026. Son para MySQL y una base de pruebas nueva; no ejecutarlos en producción ni sobre una base existente sin respaldo y revisión de migraciones. Seleccione una base vacía y ejecute `01_esquema.sql` seguido de `02_datos_prueba.sql`. No incluyen credenciales ni datos personales reales. La inicialización oficial equivalente es `python -m app.cli init`; `CREATE TABLE IF NOT EXISTS` no actualiza tablas previas. Las tablas de domicilios presentes en el esquema no prueban que la funcionalidad esté habilitada.

## Instalación

Repositorio: https://github.com/nouvellebatch-source/Eatsy . La revisión se hizo contra archivos locales que pueden diferir de la rama publicada.

API (Python): crear entorno virtual, instalar `pip install -r requirements.txt`, copiar `.env.example` a `.env`, configurar MySQL y JWT sin publicar secretos, ejecutar `python -m app.cli init`, `python -m app.cli create-user --usuario admin --nombre Nombre --apellido Apellido --rol admin`, y `uvicorn app.main:app --host 127.0.0.1 --port 8000`. Activar únicamente las opciones necesarias de pedidos y verificación, después de configurar dependencias y probar. El envío de correo requiere Brevo. Para una base existente revise primero las migraciones documentadas por el proyecto.

Flutter: en la carpeta móvil ejecutar `flutter pub get` y `flutter run`; para pruebas `flutter test`. POS React: en `pos_restaurante` ejecutar `npm ci`, copiar `.env.example` a `.env.local` y configurar la URL pública de API; ejecutar `npm run dev` o `npm run build`. Configure CORS y HTTPS. El POS depende de una cuenta y membresía autorizadas y de la API. El material adjunto contiene manifiestos de dependencias, no el código completo de las aplicaciones.

Verificación: 22 pruebas Flutter aprobadas; la compilación React aprobó. La API ejecutó 43 pruebas con 1 error en test_menu_filter_is_parameterized_and_scoped por discrepancia de argumentos. No se probó MySQL real, Brevo, producción ni el flujo completo.
