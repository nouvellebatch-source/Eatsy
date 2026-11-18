import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'main.dart' as eatsy;

/// Alternate customer experience entry point, built alongside the existing app
/// so the legacy client and admin views remain untouched.
class EatsyCustomerExperience extends StatefulWidget {
  const EatsyCustomerExperience({super.key});

  @override
  State<EatsyCustomerExperience> createState() => _EatsyCustomerExperienceState();
}

class _EatsyCustomerExperienceState extends State<EatsyCustomerExperience> {
  late Future<eatsy.Contexto> _context;
  bool _darkMode = false;
  bool _delivery = false;
  int _tab = 0;
  final Set<int> _favorites = {};
  final Map<int, int> _cart = {};
  final TextEditingController _search = TextEditingController();

  @override
  void initState() {
    super.initState();
    _context = eatsy.cargarContexto();
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _darkMode = prefs.getBool('eatsy_dark_mode') ?? false;
      _favorites
        ..clear()
        ..addAll((prefs.getStringList('eatsy_customer_favorites') ?? []).map(int.parse));
    });
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  ThemeData _theme(Brightness brightness) {
    final colors = ColorScheme.fromSeed(
      seedColor: const Color(0xFFD9480F),
      brightness: brightness,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: colors,
      scaffoldBackgroundColor: brightness == Brightness.dark
          ? const Color(0xFF171412)
          : const Color(0xFFFFFAF6),
      appBarTheme: const AppBarTheme(backgroundColor: Colors.transparent),
    );
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Eatsy',
        debugShowCheckedModeBanner: false,
        theme: _theme(_darkMode ? Brightness.dark : Brightness.light),
        home: FutureBuilder<eatsy.Contexto>(
          future: _context,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Scaffold(body: Center(child: CircularProgressIndicator()));
            }
            return _CustomerShell(
              contextData: snapshot.data!,
              tab: _tab,
              darkMode: _darkMode,
              delivery: _delivery,
              favorites: _favorites,
              cart: _cart,
              search: _search,
              onTab: (value) => setState(() => _tab = value),
              onDarkMode: (value) async {
                final prefs = await SharedPreferences.getInstance();
                await prefs.setBool('eatsy_dark_mode', value);
                if (mounted) setState(() => _darkMode = value);
              },
              onDelivery: (value) => setState(() => _delivery = value),
              onFavorite: _toggleFavorite,
              onAdd: (product) => setState(() => _cart[product.id] = (_cart[product.id] ?? 0) + 1),
              onQuantity: (product, quantity) => setState(() {
                if (quantity <= 0) {
                  _cart.remove(product.id);
                } else {
                  _cart[product.id] = quantity;
                }
              }),
            );
          },
        ),
      );

  Future<void> _toggleFavorite(int id) async {
    setState(() => _favorites.contains(id) ? _favorites.remove(id) : _favorites.add(id));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('eatsy_customer_favorites', _favorites.map((id) => '$id').toList());
  }
}

class _CustomerShell extends StatelessWidget {
  const _CustomerShell({
    required this.contextData,
    required this.tab,
    required this.darkMode,
    required this.delivery,
    required this.favorites,
    required this.cart,
    required this.search,
    required this.onTab,
    required this.onDarkMode,
    required this.onDelivery,
    required this.onFavorite,
    required this.onAdd,
    required this.onQuantity,
  });

  final eatsy.Contexto contextData;
  final int tab;
  final bool darkMode;
  final bool delivery;
  final Set<int> favorites;
  final Map<int, int> cart;
  final TextEditingController search;
  final ValueChanged<int> onTab;
  final ValueChanged<bool> onDarkMode;
  final ValueChanged<bool> onDelivery;
  final ValueChanged<int> onFavorite;
  final ValueChanged<eatsy.Producto> onAdd;
  final void Function(eatsy.Producto, int) onQuantity;

  int get total => contextData.todos.fold<int>(
        0,
        (sum, p) => sum + p.precio * (cart[p.id] ?? 0),
      );

  @override
  Widget build(BuildContext context) {
    final views = <Widget>[
      _home(context),
      _favorites(context),
      _orders(context),
      _profile(context),
    ];
    return Scaffold(
      appBar: AppBar(
        title: const Text('eatsy.', style: TextStyle(color: Color(0xFFD9480F), fontWeight: FontWeight.w900)),
        actions: [
          IconButton(
            tooltip: 'Iniciar sesión',
            icon: const Icon(Icons.person_outline_rounded),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const eatsy.PantallaLogin())),
          ),
        ],
      ),
      body: views[tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: onTab,
        destinations: [
          const NavigationDestination(icon: Icon(Icons.explore_outlined), label: 'Explore'),
          NavigationDestination(icon: const Icon(Icons.favorite_border), label: 'Favorites${favorites.isEmpty ? '' : ' (${favorites.length})'}'),
          const NavigationDestination(icon: Icon(Icons.receipt_long_outlined), label: 'Orders'),
          const NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
        ],
      ),
      bottomSheet: cart.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: FilledButton.icon(
                  onPressed: () => _checkout(context),
                  icon: const Icon(Icons.shopping_bag_outlined),
                  label: Text('View order · ${eatsy.pesos(total)}'),
                ),
              ),
            ),
    );
  }

  Widget _home(BuildContext context) {
    final query = search.text.trim().toLowerCase();
    final products = contextData.todos.where((p) =>
        p.nombre.toLowerCase().contains(query) || p.descripcion.toLowerCase().contains(query)).toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 100),
      children: [
        SegmentedButton<bool>(
          segments: const [
            ButtonSegment(value: false, label: Text('Delivery address'), icon: Icon(Icons.delivery_dining)),
            ButtonSegment(value: true, label: Text('Pedidos - Mesa 04'), icon: Icon(Icons.restaurant)),
          ],
          selected: {delivery},
          onSelectionChanged: (value) => onDelivery(value.first),
        ),
        const SizedBox(height: 12),
        Text(delivery ? 'Delivering to' : 'Tu mesa, al día', style: Theme.of(context).textTheme.titleLarge),
        Text(delivery ? 'Add your address at checkout' : '${contextData.restaurante} · Mesa 04'),
        const SizedBox(height: 18),
        TextField(
          controller: search,
          onChanged: (_) => (context as Element).markNeedsBuild(),
          decoration: InputDecoration(
            hintText: 'Search & filters',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(onPressed: () {}, icon: const Icon(Icons.tune)),
            filled: true,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
          ),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            gradient: const LinearGradient(colors: [Color(0xFFD9480F), Color(0xFFF0783D)]),
          ),
          child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('20% OFF', style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w900)),
            Text('Todo listo para tu mesa', style: TextStyle(color: Colors.white, fontSize: 17)),
          ]),
        ),
        const SizedBox(height: 20),
        Text('Categories', style: Theme.of(context).textTheme.titleLarge),
        Wrap(spacing: 8, children: [
          for (final category in contextData.menu)
            Chip(label: Text(category.nombre)),
        ]),
        const SizedBox(height: 8),
        Text('Popular near you', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        if (products.isEmpty)
          const Center(child: Padding(padding: EdgeInsets.all(30), child: Text('No products found.')))
        else
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: products.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2, crossAxisSpacing: 12, mainAxisSpacing: 12, childAspectRatio: .68,
            ),
            itemBuilder: (context, index) => _productCard(context, products[index]),
          ),
      ],
    );
  }

  Widget _productCard(BuildContext context, eatsy.Producto product) => Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => _ProductDetail(product: product, onAdd: onAdd),
          )),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: SizedBox(width: double.infinity, child: eatsy.imagenProducto(product.imagen))),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(product.nombre, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
                Text(eatsy.pesos(product.precio)),
                Row(children: [
                  IconButton(
                    onPressed: () => onFavorite(product.id),
                    icon: Icon(favorites.contains(product.id) ? Icons.favorite : Icons.favorite_border, color: const Color(0xFFD9480F)),
                  ),
                  const Spacer(),
                  IconButton.filled(onPressed: product.disponible ? () => onAdd(product) : null, icon: const Icon(Icons.add)),
                ]),
              ]),
            ),
          ]),
        ),
      );

  Widget _favorites(BuildContext context) {
    final products = contextData.todos.where((p) => favorites.contains(p.id)).toList();
    if (products.isEmpty) {
      return const _EmptyState(title: 'No Favorites', message: 'Save the dishes you love and find them here.');
    }
    return ListView(padding: const EdgeInsets.all(20), children: [
      Text('Favorites', style: Theme.of(context).textTheme.headlineMedium),
      for (final product in products) _productCard(context, product),
    ]);
  }

  Widget _orders(BuildContext context) => FutureBuilder<List<dynamic>>(
        future: _loadOrders(),
        builder: (context, snapshot) {
          final orders = snapshot.data ?? const [];
          if (snapshot.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());
          if (orders.isEmpty) return const _EmptyState(title: 'No Active Orders', message: 'Your orders will show up here.');
          return ListView(padding: const EdgeInsets.all(20), children: [
            Text('Order History', style: Theme.of(context).textTheme.headlineMedium),
            for (final order in orders)
              Card(child: ListTile(
                title: Text('Pedido #10-${order['id']}'),
                subtitle: Text('${order['status']} · ${eatsy.pesos((order['total'] as num?)?.toInt() ?? 0)}'),
              )),
          ]);
        },
      );

  Future<List<dynamic>> _loadOrders() async {
    if (eatsy.Sesion.token == null) return const [];
    try {
      final response = await http.get(
        Uri.parse('${eatsy.apiUrl}/mis-pedidos?limit=50'),
        headers: {'Authorization': 'Bearer ${eatsy.Sesion.token}'},
      ).timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) return const [];
      return jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
    } catch (_) {
      return const [];
    }
  }

  Widget _profile(BuildContext context) {
    final user = eatsy.Sesion.usuario ?? const <String, dynamic>{};
    final name = [user['nombre'], user['apellido']].whereType<String>().where((s) => s.isNotEmpty).join(' ');
    return ListView(padding: const EdgeInsets.all(20), children: [
      Text('My Profile', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 18),
      CircleAvatar(radius: 38, child: Text(name.isEmpty ? 'A' : name[0].toUpperCase())),
      const SizedBox(height: 8),
      Center(child: Text(name.isEmpty ? 'Alex Morgan' : name, style: Theme.of(context).textTheme.titleLarge)),
      const SizedBox(height: 20),
      SwitchListTile(
        title: const Text('Dark mode'),
        value: darkMode,
        onChanged: onDarkMode,
      ),
      ListTile(leading: const Icon(Icons.location_on_outlined), title: Text(delivery ? 'Delivery address' : 'Pedidos - Mesa 04')),
      ListTile(leading: const Icon(Icons.credit_card), title: const Text('Payment method · •••• 4342')),
      if (eatsy.Sesion.token == null)
        FilledButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const eatsy.PantallaLogin())),
          child: const Text('Sign in'),
        ),
    ]);
  }

  void _checkout(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => _Checkout(
        contextData: contextData,
        cart: cart,
        delivery: delivery,
        onQuantity: onQuantity,
      ),
    ));
  }
}

class _ProductDetail extends StatefulWidget {
  const _ProductDetail({required this.product, required this.onAdd});
  final eatsy.Producto product;
  final ValueChanged<eatsy.Producto> onAdd;

  @override
  State<_ProductDetail> createState() => _ProductDetailState();
}

class _ProductDetailState extends State<_ProductDetail> {
  int _quantity = 1;
  final Set<String> _extras = {};

  @override
  Widget build(BuildContext context) {
    final total = widget.product.precio * _quantity;
    return Scaffold(
      appBar: AppBar(title: const Text('Product details')),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        ClipRRect(borderRadius: BorderRadius.circular(24), child: SizedBox(height: 230, child: eatsy.imagenProducto(widget.product.imagen))),
        const SizedBox(height: 16),
        Text(widget.product.nombre, style: Theme.of(context).textTheme.headlineMedium),
        Text(widget.product.descripcion),
        const SizedBox(height: 20),
        Text('Add extras', style: Theme.of(context).textTheme.titleLarge),
        for (final extra in ['Cheese', 'Slice of tomato'])
          CheckboxListTile(
            title: Text(extra),
            value: _extras.contains(extra),
            onChanged: (value) => setState(() => value == true ? _extras.add(extra) : _extras.remove(extra)),
          ),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconButton(onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null, icon: const Icon(Icons.remove_circle_outline)),
          Text('$_quantity', style: Theme.of(context).textTheme.titleLarge),
          IconButton(onPressed: () => setState(() => _quantity++), icon: const Icon(Icons.add_circle_outline)),
        ]),
      ]),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton(
            onPressed: () {
              for (var i = 0; i < _quantity; i++) {
                widget.onAdd(widget.product);
              }
              Navigator.pop(context);
            },
            child: Text('Add to order · ${eatsy.pesos(total)}'),
          ),
        ),
      ),
    );
  }
}

class _Checkout extends StatefulWidget {
  const _Checkout({required this.contextData, required this.cart, required this.delivery, required this.onQuantity});
  final eatsy.Contexto contextData;
  final Map<int, int> cart;
  final bool delivery;
  final void Function(eatsy.Producto, int) onQuantity;

  @override
  State<_Checkout> createState() => _CheckoutState();
}

class _CheckoutState extends State<_Checkout> {
  bool _submitting = false;

  int get _total => widget.contextData.todos.fold<int>(0, (sum, p) => sum + p.precio * (widget.cart[p.id] ?? 0));

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Checkout')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          Text('Delivery address', style: Theme.of(context).textTheme.titleLarge),
          ListTile(leading: const Icon(Icons.place), title: Text(widget.delivery ? 'Add your delivery address' : 'Pedidos - Mesa 04'), subtitle: Text(widget.delivery ? 'Address required for delivery' : widget.contextData.restaurante)),
          Text('Your order', style: Theme.of(context).textTheme.titleLarge),
          for (final product in widget.contextData.todos.where((p) => (widget.cart[p.id] ?? 0) > 0))
            ListTile(
              title: Text(product.nombre),
              subtitle: Text('${eatsy.pesos(product.precio)} each'),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                IconButton(onPressed: () => widget.onQuantity(product, (widget.cart[product.id] ?? 0) - 1), icon: const Icon(Icons.remove)),
                Text('${widget.cart[product.id]}'),
                IconButton(onPressed: () => widget.onQuantity(product, (widget.cart[product.id] ?? 0) + 1), icon: const Icon(Icons.add)),
              ]),
            ),
          const Divider(),
          const ListTile(leading: Icon(Icons.credit_card), title: Text('Payment method'), trailing: Text('•••• 4342')),
          ListTile(title: const Text('Total'), trailing: Text(eatsy.pesos(_total), style: const TextStyle(fontWeight: FontWeight.bold))),
          if (widget.delivery)
            const Text('Delivery is not enabled by the Eatsy API yet. Choose dine-in to place a real order.'),
        ]),
        bottomNavigationBar: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: FilledButton(
              onPressed: _submitting || widget.delivery ? null : _placeOrder,
              child: Text(_submitting ? 'Placing order…' : 'Place order · ${eatsy.pesos(_total)}'),
            ),
          ),
        ),
      );

  Future<void> _placeOrder() async {
    if (eatsy.Sesion.token == null) {
      final signedIn = await Navigator.of(context).push<bool>(MaterialPageRoute<bool>(builder: (_) => const eatsy.PantallaLogin()));
      if (signedIn != true || !mounted) return;
    }
    setState(() => _submitting = true);
    final error = await eatsy.enviarPedido(widget.contextData, widget.cart);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (error != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error)));
      return;
    }
    await Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => const _OrderConfirmed()));
  }
}

class _OrderConfirmed extends StatelessWidget {
  const _OrderConfirmed();

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.check_circle, color: Color(0xFFD9480F), size: 84),
              const SizedBox(height: 20),
              Text('Order Confirmed!', style: Theme.of(context).textTheme.headlineMedium),
              const Text('A good meal, on its way.', textAlign: TextAlign.center),
              const SizedBox(height: 20),
              FilledButton(onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst), child: const Text('Back to Explore')),
            ]),
          ),
        ),
      );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.title, required this.message});
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.restaurant_menu, size: 54, color: Color(0xFFD9480F)),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            Text(message, textAlign: TextAlign.center),
          ]),
        ),
      );
}
