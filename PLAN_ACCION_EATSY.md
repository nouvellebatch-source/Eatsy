# Plan de acción para mejorar Eatsy

Fecha: 18 de noviembre de 2026. Fuente: revisión del SRS y código local de Flutter, POS React y API.

## Alcance y criterios

Se priorizan mejoras que pueden verificarse en el código existente. Las pasarelas de pago y la automatización de WhatsApp quedan excluidas. El comprobante será informativo y no se presentará como factura electrónica ni confirmación de pago. Se conservan los cambios locales existentes y no se modifican datos de producción.

## Etapas

- [x] Corregir la prueba de catálogo que falló y verificar el conjunto de pruebas de la API.
- [x] Incorporar importación de cartas PDF: extraer texto, usar OCR en páginas escaneadas cuando Tesseract esté instalado, presentar propuestas editables y publicar solo mediante confirmación del responsable del restaurante.
- [x] Añadir comprobante imprimible con productos, precios, descuentos, total y estado del pago a las comandas del POS.
- [x] Mejorar consulta operativa con búsqueda por identificador o mesa y exportación de los pedidos cargados, indicando sus límites.
- [x] Ejecutar pruebas útiles para autorización, límites, lectura de carta y datos del comprobante; compilar React y ejecutar pruebas Flutter.
- [x] Documentar instalación, dependencias, resultados y limitaciones; actualizar los estados del plan al finalizar.

## Límites

Las metas cuantitativas de disponibilidad, tiempos, recuperación y escalabilidad requieren infraestructura y mediciones reales; no se declaran cumplidas solo por modificar código. Las pruebas de base de datos y servicios externos necesitan un entorno de integración configurado. No se implementan facturación electrónica, webhooks de pago ni WhatsApp.

## Resultado de ejecución

- API: 51 pruebas aprobadas, incluidas comprobaciones de permisos por restaurante, límite de archivo, publicación y lectura de PDF con texto. La prueba de catálogo se corrigió para usar la firma actual.
- OCR de imagen: se verificó la llamada mediante una prueba simulada. El ejecutable Tesseract y los datos de idioma no estaban instalados en este equipo; instalar y ejecutar una prueba real con un PDF escaneado antes de habilitarlo en el servidor.
- POS: compilación correcta y 2 pruebas de cálculo del comprobante y seguridad de CSV. Se añadieron edición y disponibilidad de productos, por páginas de 100.
- Flutter: 22 pruebas aprobadas. La aplicación cliente no recibió nuevos cambios en esta etapa; debe volver a consultar el catálogo para observar modificaciones.
- Los cambios están en la copia local y no se han desplegado. No se usó una base de datos MySQL real ni se verificó el flujo completo desde un navegador autenticado.

## Pendientes y prioridades siguientes

1. Validar en un entorno de pruebas la importación real con Tesseract, documentos escaneados, MySQL, membresías y publicaciones concurrentes; considerar idempotencia para evitar duplicaciones al reintentar.
2. Implementar generación de QR y apertura de contexto de mesa; comprobar autorización y enlaces recuperables.
3. Mejorar historial y repetición de pedidos con validación de precios y disponibilidad reales; ampliar filtros y exportación más allá de 100 pedidos.
4. Diseñar y probar gestión de sedes y mesas, versiones de carta, carga segura de imágenes, auditoría de cambios y permisos adicionales.
5. Especificar y validar cola, prioridad y ETA con la operación del restaurante antes de prometer estimaciones.
6. Medir rendimiento, accesibilidad, compatibilidad, copias de seguridad y recuperación en infraestructura real.
7. Continúan excluidas las pasarelas, la automatización de WhatsApp y la facturación electrónica. La gestión de documentos fiscales y la adjunción de archivos tampoco se implementaron; el comprobante actual es informativo.

## Continuación 18 de noviembre de 2026

- Se agregó Mistral OCR como opción elegida expresamente para lectura de cartas y facturas en PDF. La clave queda en `MISTRAL_API_KEY` del servidor y el POS informa que se envía el documento completo. La lectura de facturas muestra texto editable en pantalla y no guarda archivos, registra gastos ni confirma pagos. Falta configurar la clave y realizar una prueba real con Mistral y con una factura autorizada.
- La API de comandas permite búsqueda por pedido o mesa y paginación. El POS exporta hasta 1.000 resultados; la descarga por páginas no representa una instantánea consistente bajo escrituras simultáneas.
- El historial permite preparar la repetición de un pedido propio con productos disponibles y precios actuales. Se requiere revisión del carrito; el backend vuelve a comprobar disponibilidad y precios al enviar el nuevo pedido.
- Quedan pendientes los QR y enlaces de mesa, almacenamiento y vinculación de facturas, la importación idempotente de cartas, auditoría más amplia y las pruebas integrales con MySQL, despliegue y servicios externos. Las pasarelas de pago, automatización de WhatsApp y facturación electrónica continúan fuera de alcance.

Validación de la continuación: 58 pruebas de API y 23 de Flutter aprobadas; 2 pruebas del POS aprobadas y compilación React correcta. `flutter analyze` terminó con 29 observaciones informativas de estilo, sin errores de compilación. Las pruebas de Mistral usan respuestas simuladas.

## Alternativa gratuita de OCR

Se sustituyó Tesseract en el flujo local por RapidOCR y ONNX Runtime, sin claves de API. El POS usa este flujo local para cartas y facturas; la integración opcional de Mistral ya no se ofrece en sus pantallas. La versión fijada incorpora los modelos. Se verificó localmente un PDF creado a partir de una imagen: se reconocieron un producto y su precio, y se omitió la línea TOTAL de la propuesta. La calidad varía según resolución, diseño y escritura; se exige revisión humana. Debe verificarse la instalación y los recursos del servidor antes de desplegar.

## Preparación para publicación

La rama de OCR se preparó desde la versión pública actual e incluye la API y el POS. La copia móvil del repositorio es un proyecto diferente de la aplicación Flutter local; por eso la repetición de pedidos desarrollada en la copia local no está incluida en esta rama. La validación en producción y la instalación de dependencias del servidor siguen pendientes hasta confirmar el despliegue.
