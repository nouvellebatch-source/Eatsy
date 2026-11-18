# Eatsy — app móvil

Este proyecto ya está integrado en el repositorio. La guía completa está en
[`README.md`](README.md).

Resumen:

```sh
cd mobile
flutter pub get
flutter run
```

Con el emulador Android la API se ve en `http://10.0.2.2:8000`; con un celular
físico usa `flutter run --dart-define=EATSY_API_URL=http://IP_DE_TU_PC:8000`.

El panel de gestión web vive en `../panel/` y la API en la raíz del repositorio.
