Get-ExecutionPolicyimport 'dart:convert';
import 'dart:io' show Platform;
import 'dart:math' show Random;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:material_ui/material_ui.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

// ---------------------------------------------------------------- Config
// Emulador Android: 10.0.2.2 es el PC. Celular fisico: pon la IP de tu PC
// y arranca la API con: uvicorn app.main:app --host 0.0.0.0
// Tambien se puede fijar sin tocar el codigo:
//   flutter run --dart-define=EATSY_API_URL=http://192.168.1.50:8000
const String apiUrlOverride = String.fromEnvironment('EATSY_API_URL');

String get apiUrl {
  if (apiUrlOverride.isNotEmpty) return apiUrlOverride;
  if (!kIsWeb && Platform.isAndroid) return 'http://10.0.2.2:8000';
  return 'http://127.0.0.1:8000';
}

// Codigo de la mesa para pedidos en tienda (fulfillment dine_in).
const String mesaDefault = String.fromEnvironment('MESA', defaultValue: 'M1');

const marca = Color(0xFFD9480F);
const marcaSuave = Color(0xFFFFF1E8);
const fondo = Color(0xFFFFFAF6);

final Random _rnd = Random.secure();

/// Genera la clave de idempotencia que exige POST /pedidos (formato UUID v4).
String uuidV4() {
  final b = List<int>.generate(16, (_) => _rnd.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  final h = b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

// ---------------------------------------------------------------- Sesion
/// Token JWT de POST /auth/login, guardado en el dispositivo.
class Sesion {
  static String? token;
  static Map<String, dynamic>? usuario;

  static Future<void> cargar() async {
    final p = await SharedPreferences.getInstance();
    token = p.getString('eatsy_token');
    final u = p.getString('eatsy_usuario');
    if (u != null) usuario = jsonDecode(u) as Map<String, dynamic>;
  }

  static Future<void> guardar(String t, Map<String, dynamic> u) async {
    token = t;
    usuario = u;
    final p = await SharedPreferences.getInstance();
    await p.setString('eatsy_token', t);
    await p.setString('eatsy_usuario', jsonEncode(u));
  }

  static Future<void> salir() async {
    token = null;
    usuario = null;
    final p = await SharedPreferences.getInstance();
    await p.remove('eatsy_token');
    await p.remove('eatsy_usuario');
  }
}

// ---------------------------------------------------------------- Modelos
class Producto {
  final int id;
  final String nombre, descripcion;
  final int precio;
  final bool disponible;
  final String? imagen; // URL de la API o nombre de asset en la demo
  const Producto(this.id, this.nombre, this.descripcion, this.precio, this.disponible, [this.imagen]);
}

class Categoria {
  final int id;
  final String nombre;
  final List<Producto> productos;
  const Categoria(this.id, this.nombre, this.productos);
}

class Contexto {
  final int? restauranteId, sedeId;
  final String restaurante, sede, mesa;
  final List<Categoria> menu;
  final bool enLinea;
  const Contexto(this.restauranteId, this.sedeId, this.restaurante, this.sede, this.mesa, this.menu, {this.enLinea = false});

  List<Producto> get todos => [for (final c in menu) ...c.productos];
}

// Menú de respaldo cuando la API está apagada.
const contextoDemo = Contexto(null, null, 'Eatsy · Restaurante Demo', 'Sede Centro', mesaDefault, [
  Categoria(1, 'Entradas', [
    Producto(1, 'Empanadas de carne', 'Tres empanadas con ají casero.', 12000, true, 'p1.jpg'),
    Producto(2, 'Ceviche de camarón', 'Camarón fresco con limón y cilantro.', 28000, true, 'p2.jpg'),
  ]),
  Categoria(2, 'Platos fuertes', [
    Producto(3, 'Arroz con coco y pescado', 'Pescado frito, arroz con coco y patacón.', 42000, true, 'p3.jpg'),
    Producto(4, 'Bandeja paisa', 'La clásica, completa.', 38000, false, 'p4.jpg'),
  ]),
  Categoria(3, 'Bebidas', [
    Producto(5, 'Limonada de coco', 'Cremosa y bien fría.', 9000, true, 'p5.jpg'),
    Producto(6, 'Jugo de lulo', 'Natural, en agua o en leche.', 8000, true, 'p6.jpg'),
  ]),
]);

String pesos(int n) {
  final s = n.toString().replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => '.');
  return '\$$s';
}

Widget imagenProducto(String? src, {BoxFit fit = BoxFit.cover}) {
  if (src == null || src.isEmpty) {
    return const ColoredBox(color: marcaSuave, child: Icon(Icons.restaurant_rounded, color: marca, size: 40));
  }
  if (src.startsWith('http')) {
    return Image.network(src, fit: fit, errorBuilder: (_, __, ___) => const ColoredBox(color: marcaSuave, child: Icon(Icons.restaurant_rounded, color: marca, size: 40)));
  }
  return Image.asset('assets/img/$src', fit: fit);
}

// ---------------------------------------------------------------- API
/// Menú real: GET /restaurantes -> sucursales -> /restaurantes/{id}/productos.
/// Si la API está apagada o vacía, usa la demostración.
Future<Contexto> cargarContexto() async {
  try {
    final rs = await http.get(Uri.parse('$apiUrl/restaurantes?limit=1')).timeout(const Duration(seconds: 5));
    if (rs.statusCode == 200) {
      final restaurantes = jsonDecode(utf8.decode(rs.bodyBytes)) as List;
      if (restaurantes.isNotEmpty) {
        final r = restaurantes.first as Map<String, dynamic>;
        final rid = r['id'] as int;
        String sede = r['name'] as String;
        int? sedeId;
        try {
          final bs = await http.get(Uri.parse('$apiUrl/restaurantes/$rid/sucursales')).timeout(const Duration(seconds: 5));
          final sucursales = jsonDecode(utf8.decode(bs.bodyBytes)) as List;
          if (sucursales.isNotEmpty) {
            final b = sucursales.first as Map<String, dynamic>;
            sede = b['name'] as String;
            sedeId = b['id'] as int;
          }
        } catch (_) {/* sin sucursales: se pide con restaurante_id nulo */}
        final ps = await http
            .get(Uri.parse('$apiUrl/restaurantes/$rid/productos?limit=100'))
            .timeout(const Duration(seconds: 5));
        if (ps.statusCode == 200) {
          final filas = jsonDecode(utf8.decode(ps.bodyBytes)) as List;
          final grupos = <String, List<Producto>>{};
          for (final f in filas) {
            final j = f as Map<String, dynamic>;
            final cat = ((j['category'] ?? 'Otros') as String).trim();
            grupos.putIfAbsent(cat, () => []).add(Producto(
                  j['id'] as int,
                  j['name'] as String,
                  (j['description'] ?? '') as String,
                  (j['price'] as num).toInt(),
                  true, // la API solo devuelve disponibles
                  j['image_url'] as String?,
                ));
          }
          final categorias = grupos.keys.toList()..sort((a, b) => a.compareTo(b));
          if (categorias.isNotEmpty) {
            return Contexto(
              rid,
              sedeId,
              r['name'] as String,
              sede,
              mesaDefault,
              [for (final (i, c) in categorias.indexed) Categoria(i + 1, c, grupos[c]!)],
              enLinea: true,
            );
          }
        }
      }
    }
  } catch (_) {/* API apagada: usamos la demo */}
  return contextoDemo;
}

/// POST /pedidos con el contrato real de la API (requiere sesión de cliente).
/// Devuelve null si el pedido se creó, o el mensaje de error.
Future<String?> enviarPedido(Contexto ctx, Map<int, int> carrito) async {
  if (ctx.restauranteId == null || ctx.sedeId == null) {
    return 'Menú de demostración: arranca la API para pedir de verdad';
  }
  try {
    final r = await http
        .post(
          Uri.parse('$apiUrl/pedidos'),
          headers: {
            'Content-Type': 'application/json',
            if (Sesion.token != null) 'Authorization': 'Bearer ${Sesion.token}',
          },
          body: jsonEncode({
            'restaurant_id': ctx.restauranteId,
            'branch_id': ctx.sedeId,
            'idempotency_key': uuidV4(),
            'fulfillment': 'dine_in',
            'table_number': ctx.mesa,
            'payment_method': 'cash',
            'items': [
              for (final e in carrito.entries)
                {'product_id': e.key, 'quantity': e.value, 'additions': <Map<String, dynamic>>[]},
            ],
          }),
        )
        .timeout(const Duration(seconds: 6));
    if (r.statusCode == 201) return null;
    if (r.statusCode == 401) return 'Tu sesión expiró. Inicia sesión de nuevo.';
    final j = jsonDecode(utf8.decode(r.bodyBytes));
    if (j is Map && j['detail'] is String) return j['detail'] as String;
    return 'No se pudo enviar el pedido (error ${r.statusCode})';
  } catch (_) {
    return 'Sin conexión con el restaurante';
  }
}

// Favoritos guardados en el dispositivo (una lista de ids por clave).
Future<Set<int>> leerFavs(String clave) async {
  final p = await SharedPreferences.getInstance();
  return (p.getStringList(clave) ?? []).map(int.parse).toSet();
}

Future<void> guardarFavs(String clave, Set<int> ids) async {
  final p = await SharedPreferences.getInstance();
  await p.setStringList(clave, ids.map((e) => e.toString()).toList());
}

// ---------------------------------------------------------------- App
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Sesion.cargar();
  runApp(const EatsyApp());
}

class EatsyApp extends StatelessWidget {
  const EatsyApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Eatsy',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: marca),
          scaffoldBackgroundColor: fondo,
        ),
        home: const Cargador(),
      );
}

/// Carga el menu y decide la vista: celular = cliente, pantalla ancha = administrador.
class Cargador extends StatelessWidget {
  const Cargador({super.key});

  @override
  Widget build(BuildContext context) => FutureBuilder<Contexto>(
        future: cargarContexto(),
        builder: (context, s) {
          if (!s.hasData) return const Scaffold(body: Center(child: CircularProgressIndicator()));
          final ancho = MediaQuery.of(context).size.width;
          return ancho >= 760 ? PantallaAdmin(ctx: s.data!) : PantallaCliente(ctx: s.data!);
        },
      );
}

// ---------------------------------------------------------------- Login
class PantallaLogin extends StatefulWidget {
  const PantallaLogin({super.key});

  @override
  State<PantallaLogin> createState() => _PantallaLoginState();
}

class _PantallaLoginState extends State<PantallaLogin> {
  final _usuario = TextEditingController();
  final _clave = TextEditingController();
  bool _cargando = false;
  String? _error;

  @override
  void dispose() {
    _usuario.dispose();
    _clave.dispose();
    super.dispose();
  }

  Future<void> entrar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final r = await http
          .post(
            Uri.parse('$apiUrl/auth/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'usuario': _usuario.text.trim(), 'contrasena': _clave.text}),
          )
          .timeout(const Duration(seconds: 6));
      final j = jsonDecode(utf8.decode(r.bodyBytes));
      if (r.statusCode == 200 && j is Map && j['access_token'] != null) {
        await Sesion.guardar(j['access_token'] as String, (j['usuario'] as Map).cast<String, dynamic>());
        if (mounted) Navigator.of(context).pop(true);
        return;
      }
      _error = j is Map && j['detail'] is String ? j['detail'] as String : 'No se pudo iniciar sesión.';
    } catch (_) {
      _error = 'Sin conexión con la API en $apiUrl';
    }
    if (mounted) setState(() => _cargando = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: fondo,
        appBar: AppBar(backgroundColor: fondo, surfaceTintColor: Colors.transparent, elevation: 0),
        body: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Container(
              width: 380,
              padding: const EdgeInsets.all(26),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(26),
                boxShadow: const [BoxShadow(color: Color(0x0D33251F), blurRadius: 18, offset: Offset(0, 6))],
              ),
              child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const Text('eatsy.', style: TextStyle(color: marca, fontSize: 30, letterSpacing: -1.4, fontWeight: FontWeight.w900)),
                const SizedBox(height: 4),
                const Text('Inicia sesión para pedir en mesa.', style: TextStyle(color: Color(0xFF81766F), fontSize: 13)),
                const SizedBox(height: 20),
                TextField(
                  controller: _usuario,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(labelText: 'Usuario', border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(14)))),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _clave,
                  obscureText: true,
                  onSubmitted: (_) => entrar(),
                  decoration: const InputDecoration(labelText: 'Contraseña', border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(14)))),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!, style: const TextStyle(color: Color(0xFFB3261E), fontWeight: FontWeight.w700, fontSize: 13)),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _cargando ? null : entrar,
                  style: FilledButton.styleFrom(backgroundColor: marca, foregroundColor: Colors.white, padding: const EdgeInsets.symmetric(vertical: 14)),
                  child: Text(_cargando ? 'Entrando...' : 'Entrar'),
                ),
              ]),
            ),
          ),
        ),
      );
}

// ---------------------------------------------------------------- Cliente
class PantallaCliente extends StatefulWidget {
  final Contexto ctx;
  const PantallaCliente({super.key, required this.ctx});

  @override
  State<PantallaCliente> createState() => _PantallaClienteState();
}

class _PantallaClienteState extends State<PantallaCliente> {
  static const clave = 'favoritos_cliente';
  int pestana = 0, categoria = 0;
  Set<int> favs = {};
  final Map<int, int> carrito = {};
  bool enviando = false;

  @override
  void initState() {
    super.initState();
    leerFavs(clave).then((v) => setState(() => favs = v));
  }

  Future<void> pedir() async {
    if (Sesion.token == null) {
      final entro = await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => const PantallaLogin()));
      if (entro != true || !mounted) return;
    }
    setState(() => enviando = true);
    final error = await enviarPedido(widget.ctx, carrito);
    if (!mounted) return;
    if (error == 'Tu sesión expiró. Inicia sesión de nuevo.') await Sesion.salir();
    setState(() {
      enviando = false;
      if (error == null) carrito.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error ?? 'Pedido enviado a cocina')));
  }

  void alternarFav(int id) {
    setState(() => favs.contains(id) ? favs.remove(id) : favs.add(id));
    guardarFavs(clave, favs);
  }

  Widget tarjeta(Producto p) {
    final esFav = favs.contains(p.id);
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        boxShadow: const [BoxShadow(color: Color(0x0D33251F), blurRadius: 18, offset: Offset(0, 6))],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Stack(children: [
          SizedBox(
            height: 112,
            width: double.infinity,
            child: imagenProducto(p.imagen),
          ),
          Positioned(
            top: 8,
            right: 8,
            child: IconButton(
              tooltip: esFav ? 'Quitar de favoritos' : 'Agregar a favoritos',
              onPressed: () => alternarFav(p.id),
              style: IconButton.styleFrom(backgroundColor: Colors.white, foregroundColor: esFav ? marca : const Color(0xFF6F625B)),
              icon: Icon(esFav ? Icons.favorite : Icons.favorite_border, size: 19),
            ),
          ),
        ]),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(p.nombre, maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, height: 1.15)),
              const SizedBox(height: 4),
              Text(p.descripcion, maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFF81766F), fontSize: 11, height: 1.25)),
              const Spacer(),
              Row(children: [
                Expanded(child: Text(pesos(p.precio), style: const TextStyle(color: Color(0xFF29231F), fontWeight: FontWeight.w800))),
                IconButton(
                  tooltip: p.disponible ? 'Agregar al pedido' : 'Agotado',
                  onPressed: p.disponible ? () => setState(() => carrito[p.id] = (carrito[p.id] ?? 0) + 1) : null,
                  style: IconButton.styleFrom(backgroundColor: p.disponible ? marcaSuave : const Color(0xFFF0ECE9), foregroundColor: marca),
                  icon: Icon(p.disponible ? Icons.add_rounded : Icons.remove, size: 20),
                ),
              ]),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget inicio() {
    final cats = widget.ctx.menu;
    final productos = widget.ctx.todos.where((p) {
      if (categoria == 0) return true;
      return cats.any((c) => c.id == categoria && c.productos.any((item) => item.id == p.id));
    }).toList();
    return ListView(padding: const EdgeInsets.fromLTRB(20, 14, 20, 20), children: [
      Row(children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: marcaSuave, borderRadius: BorderRadius.circular(15)),
          child: const Icon(Icons.place_rounded, color: marca),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('PIDE EN', style: TextStyle(fontSize: 10, letterSpacing: 1.4, color: Color(0xFF8C7D74), fontWeight: FontWeight.w800)),
          Text('${widget.ctx.restaurante} · Mesa ${widget.ctx.mesa}', maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
        ])),
      ]),
      const SizedBox(height: 22),
      const Text('¿Qué se te antoja\nhoy?', style: TextStyle(fontSize: 32, height: 1.08, letterSpacing: -0.8, fontWeight: FontWeight.w900)),
      const SizedBox(height: 7),
      const Text('Encuentra tu próximo favorito.', style: TextStyle(color: Color(0xFF81766F), fontSize: 14)),
      const SizedBox(height: 20),
      Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFFD9480F), Color(0xFFF0783D)], begin: Alignment.topLeft, end: Alignment.bottomRight),
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('HECHO AL MOMENTO', style: TextStyle(color: Colors.white70, fontSize: 10, letterSpacing: 1.5, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            const Text('Un buen antojo\nlo cambia todo.', style: TextStyle(color: Colors.white, fontSize: 20, height: 1.12, fontWeight: FontWeight.w900)),
            const SizedBox(height: 6),
            Text(widget.ctx.sede, style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ])),
          const SizedBox(width: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Image.asset('assets/img/p7.jpg', width: 84, height: 84, fit: BoxFit.cover),
          ),
        ]),
      ),
      const SizedBox(height: 24),
      SizedBox(
        height: 40,
        child: ListView(scrollDirection: Axis.horizontal, children: [
          for (final c in [const Categoria(0, 'Todo', []), ...cats])
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(c.nombre),
                selected: categoria == c.id,
                showCheckmark: false,
                selectedColor: marca,
                backgroundColor: Colors.white,
                labelStyle: TextStyle(color: categoria == c.id ? Colors.white : const Color(0xFF564941), fontWeight: FontWeight.w700),
                side: BorderSide(color: categoria == c.id ? marca : const Color(0xFFEDE5DF)),
                onSelected: (_) => setState(() => categoria = c.id),
              ),
            ),
        ]),
      ),
      const SizedBox(height: 22),
      Text(categoria == 0 ? 'Popular en el menú' : cats.firstWhere((c) => c.id == categoria).nombre,
          style: const TextStyle(fontSize: 20, letterSpacing: -0.3, fontWeight: FontWeight.w900)),
      const SizedBox(height: 12),
      GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 0.76,
        children: productos.map(tarjeta).toList(),
      ),
    ]);
  }

  Widget favoritos() {
    final lista = widget.ctx.todos.where((p) => favs.contains(p.id)).toList();
    return ListView(padding: const EdgeInsets.fromLTRB(20, 28, 20, 20), children: [
      const Text('Favoritos', style: TextStyle(fontSize: 30, letterSpacing: -0.7, fontWeight: FontWeight.w900)),
      const SizedBox(height: 6),
      Text(
        lista.isEmpty ? 'Guarda aquí los platos que más te gustan.' : '${lista.length} ${lista.length == 1 ? 'favorito' : 'favoritos'} para cuando vuelva el antojo.',
        style: const TextStyle(color: Color(0xFF81766F), fontSize: 14),
      ),
      if (lista.isEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 42),
          child: Container(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 28),
            decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(26)),
            child: Column(children: [
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(color: marcaSuave, borderRadius: BorderRadius.circular(30)),
                child: const Icon(Icons.favorite_rounded, color: marca, size: 40),
              ),
              const SizedBox(height: 18),
              const Text('Todavía no hay favoritos', textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
              const SizedBox(height: 8),
              const Text('Toca el corazón de un plato y lo encontrarás aquí cuando vuelvan las ganas.',
                  textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF81766F), height: 1.4)),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: () => setState(() => pestana = 0),
                style: FilledButton.styleFrom(backgroundColor: marca, foregroundColor: Colors.white, padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14)),
                child: const Text('Explorar el menú'),
              ),
            ]),
          ),
        )
      else ...[
        const SizedBox(height: 22),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 0.76,
          children: lista.map(tarjeta).toList(),
        ),
        const SizedBox(height: 14),
        const Center(child: Text('Un corazón hoy. Un buen plato después.',
            style: TextStyle(color: Color(0xFF81766F), fontSize: 12))),
      ],
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final lineas = widget.ctx.todos.where((p) => carrito[p.id] != null).toList();
    final n = lineas.fold<int>(0, (s, p) => s + carrito[p.id]!);
    final total = lineas.fold<int>(0, (s, p) => s + carrito[p.id]! * p.precio);
    final sesionAbierta = Sesion.token != null;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: fondo,
        foregroundColor: const Color(0xFF29231F),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        toolbarHeight: 54,
        title: const Text('eatsy.', style: TextStyle(color: marca, fontSize: 25, letterSpacing: -1.2, fontWeight: FontWeight.w900)),
        actions: [
          if (sesionAbierta)
            IconButton(
              tooltip: 'Cerrar sesión',
              onPressed: () async {
                await Sesion.salir();
                setState(() {});
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sesión cerrada')));
              },
              icon: const Icon(Icons.logout_rounded, size: 20),
            ),
        ],
      ),
      body: pestana == 0 ? inicio() : favoritos(),
      bottomNavigationBar: Column(mainAxisSize: MainAxisSize.min, children: [
        if (n > 0)
          Container(
            decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: Color(0xFFF0E9E3)))),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Row(children: [
              const Icon(Icons.shopping_bag_outlined, color: marca),
              const SizedBox(width: 10),
              Expanded(child: Text('$n ${n == 1 ? 'producto' : 'productos'} en tu pedido',
                  style: const TextStyle(color: Color(0xFF564941), fontWeight: FontWeight.w700))),
              Text(pesos(total), style: const TextStyle(color: Color(0xFF29231F), fontWeight: FontWeight.w900)),
              if (widget.ctx.enLinea) ...[
                const SizedBox(width: 12),
                FilledButton(
                  onPressed: enviando ? null : pedir,
                  style: FilledButton.styleFrom(backgroundColor: marca, foregroundColor: Colors.white),
                  child: Text(enviando ? 'Enviando...' : sesionAbierta ? 'Pedir' : 'Pedir (inicia sesión)'),
                ),
              ],
            ]),
          ),
        NavigationBar(
          backgroundColor: Colors.white,
          indicatorColor: marcaSuave,
          elevation: 0,
          selectedIndex: pestana,
          onDestinationSelected: (i) => setState(() => pestana = i),
          destinations: [
            const NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home_rounded), label: 'Inicio'),
            NavigationDestination(
              icon: const Icon(Icons.favorite_border),
              selectedIcon: const Icon(Icons.favorite_rounded),
              label: favs.isEmpty ? 'Favoritos' : 'Favoritos (${favs.length})',
            ),
          ],
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------- Administrador
class PantallaAdmin extends StatefulWidget {
  final Contexto ctx;
  const PantallaAdmin({super.key, required this.ctx});

  @override
  State<PantallaAdmin> createState() => _PantallaAdminState();
}

class _PantallaAdminState extends State<PantallaAdmin> {
  static const clave = 'favoritos_admin';
  int seccion = 0;
  Set<int> fijados = {};
  late final Map<int, bool> disponible = {for (final p in widget.ctx.todos) p.id: p.disponible};

  // Datos de ejemplo: la gestion de cocina vive en el panel web (eatsy_web).
  static const pedidos = [
    ['#1042', 'M1', 'EN_PREPARACION', 54000],
    ['#1041', 'M4', 'LISTO', 28000],
    ['#1040', 'M2', 'ENTREGADO', 71000],
    ['#1039', 'M3', 'PAGADO', 17000],
  ];

  @override
  void initState() {
    super.initState();
    leerFavs(clave).then((v) => setState(() => fijados = v));
  }

  Widget kpi(String titulo, String valor) => Expanded(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(titulo, style: const TextStyle(color: Colors.black54)),
              Text(valor, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
            ]),
          ),
        ),
      );

  Widget inicio() => ListView(padding: const EdgeInsets.all(24), children: [
        const Text('Inicio', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Row(children: [
          kpi('Ventas de hoy', pesos(170000)),
          kpi('Pedidos', '4'),
          kpi('Ticket promedio', pesos(42500)),
          kpi('En cocina', '1'),
        ]),
        const SizedBox(height: 16),
        const Text('Pedidos recientes', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        Card(
          child: SizedBox(
            width: double.infinity,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Pedido')),
                DataColumn(label: Text('Mesa')),
                DataColumn(label: Text('Estado')),
                DataColumn(label: Text('Total')),
              ],
              rows: [
                for (final p in pedidos)
                  DataRow(cells: [
                    DataCell(Text(p[0] as String)),
                    DataCell(Text(p[1] as String)),
                    DataCell(Chip(label: Text(p[2] as String))),
                    DataCell(Text(pesos(p[3] as int))),
                  ]),
              ],
            ),
          ),
        ),
      ]);

  Widget favoritos() {
    final todos = widget.ctx.todos;
    final fijadosLista = todos.where((p) => fijados.contains(p.id)).toList();
    return ListView(padding: const EdgeInsets.all(24), children: [
      const Text('Favoritos', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
      const Text('Productos fijados para tenerlos a la mano. Cambia su disponibilidad (RF-012).',
          style: TextStyle(color: Colors.black54)),
      const SizedBox(height: 12),
      if (fijadosLista.isEmpty)
        const Padding(padding: EdgeInsets.all(32), child: Center(child: Text('No hay productos fijados. Usa la estrella.'))),
      for (final p in fijadosLista) fila(p),
      const Divider(height: 32),
      const Text('Todos los productos', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      for (final p in todos.where((p) => !fijados.contains(p.id))) fila(p),
    ]);
  }

  Widget fila(Producto p) {
    final fijado = fijados.contains(p.id);
    return Card(
      child: ListTile(
        leading: IconButton(
          tooltip: fijado ? 'Quitar de favoritos' : 'Fijar',
          icon: Icon(fijado ? Icons.star : Icons.star_border, color: fijado ? Colors.amber : Colors.grey),
          onPressed: () {
            setState(() => fijado ? fijados.remove(p.id) : fijados.add(p.id));
            guardarFavs(clave, fijados);
          },
        ),
        title: Text(p.nombre),
        subtitle: Text(pesos(p.precio)),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(disponible[p.id]! ? 'Disponible' : 'Agotado'),
          Switch(value: disponible[p.id]!, onChanged: (v) => setState(() => disponible[p.id] = v)),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Row(children: [
          NavigationRail(
            selectedIndex: seccion,
            onDestinationSelected: (i) => setState(() => seccion = i),
            labelType: NavigationRailLabelType.all,
            leading: const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: Text('Eatsy', style: TextStyle(color: marca, fontWeight: FontWeight.w900, fontSize: 20)),
            ),
            destinations: const [
              NavigationRailDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: Text('Inicio')),
              NavigationRailDestination(icon: Icon(Icons.star_border), selectedIcon: Icon(Icons.star), label: Text('Favoritos')),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: seccion == 0 ? inicio() : favoritos()),
        ]),
      );
}
