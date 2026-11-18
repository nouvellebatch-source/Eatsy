# Eatsy — aplicación móvil (Flutter)

App de clientes de Eatsy: menú, favoritos, carrito y pedidos contra la API del
repositorio. Todo el código de la app está en `lib/main.dart` (Dart); `android/`,
`ios/`, `linux/`, `macos/` y `windows/` son la infraestructura de plataforma que
genera Flutter.

## Requisitos

- Flutter 3.x estable (`flutter --version`).
- Android Studio con los plugins Flutter y Dart, o un emulador/dispositivo listo.

## Ejecutar

```sh
cd mobile
flutter pub get
flutter run
```

La app apunta a `http://10.0.2.2:8000` en el emulador Android (es el `localhost`
del PC) y a `http://127.0.0.1:8000` en escritorio. Para un celular físico en la
misma Wi-Fi, pasa la IP del PC sin editar el código:

```sh
flutter run --dart-define=EATSY_API_URL=http://192.168.1.50:8000
```

Primero debe estar corriendo la API (`iniciar_api.cmd` en la raíz del repo) y,
para pedir de verdad, hay que iniciar sesión con la cuenta cliente que crea
`poblar_datos.cmd`.

## Estructura

- `lib/main.dart`: pantallas, estado de sesión y llamadas a la API.
- `assets/img/`: fotos de los productos de demostración.
- `pubspec.yaml`: dependencias (`http`, `shared_preferences`, `material_ui`).
- `android/`: manifiesto con permiso de Internet y tráfico sin cifrar para
  desarrollo local; en producción la API debe ir por HTTPS.

## Pruebas y análisis

```sh
flutter analyze
flutter test
```
