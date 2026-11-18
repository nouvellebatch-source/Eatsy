const LS_URL = 'eatsy_api_url';
const LS_TOKEN = 'eatsy_token';
const LS_USER = 'eatsy_user';
const LS_REST = 'eatsy_restaurante';

// URL de la API compilada en el bundle (Vite). Si no se define, se usa la API local.
// `import.meta.env` no existe cuando el panel se sirve sin Vite, de ahí el fallback.
const entorno = import.meta.env || {};
const API_POR_DEFECTO = String(entorno.VITE_EATSY_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const ESTADOS = {
  pending_acceptance: { texto: 'Pendiente', clase: 'alerta' },
  confirmed: { texto: 'Confirmado', clase: 'marca' },
  preparing: { texto: 'En cocina', clase: 'marca' },
  cooked: { texto: 'Cocinado', clase: 'info' },
  ready: { texto: 'Listo', clase: 'ok' },
  delivered: { texto: 'Entregado', clase: 'ok' },
};

const SIGUIENTE = {
  pending_acceptance: 'confirmed',
  confirmed: 'preparing',
  preparing: 'cooked',
  cooked: 'ready',
  ready: 'delivered',
};

const TITULOS = {
  panel: ['Panel', 'Resumen de pedidos y catálogo.'],
  menu: ['Catálogo', 'Productos de la tienda: precios, stock e imágenes.'],
  pedidos: ['Pedidos', 'Comandas del restaurante y avance en cocina.'],
};

const estado = {
  base: localStorage.getItem(LS_URL) || API_POR_DEFECTO,
  token: localStorage.getItem(LS_TOKEN) || '',
  usuario: JSON.parse(localStorage.getItem(LS_USER) || 'null'),
  restaurantes: [],
  restauranteId: Number(localStorage.getItem(LS_REST)) || null,
  productos: [],
  pedidos: [],
  pedidosError: '',
  ultimoError: '',
  vista: 'panel',
  filtroCategoria: '',
  filtroEstado: 'TODOS',
};

async function api(metodo, ruta, cuerpo) {
  estado.ultimoError = '';
  try {
    const r = await fetch(estado.base + ruta, {
      method: metodo,
      headers: {
        'Content-Type': 'application/json',
        ...(estado.token ? { Authorization: 'Bearer ' + estado.token } : {}),
      },
      body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    });
    if (r.status === 401) {
      salir('Tu sesión expiró. Inicia sesión de nuevo.');
      return null;
    }
    if (r.status === 204) return null;
    const j = await r.json().catch(() => null);
    if (!r.ok) {
      estado.ultimoError = detalle(j);
      aviso(estado.ultimoError);
      return null;
    }
    return j;
  } catch (_) {
    estado.ultimoError = 'No se pudo conectar con la API en ' + estado.base + ' (¿está corriendo?)';
    aviso(estado.ultimoError);
    return null;
  }
}

function detalle(j) {
  if (!j || j.detail === undefined) return 'Error del servidor.';
  if (typeof j.detail === 'string') return j.detail;
  if (Array.isArray(j.detail)) {
    return j.detail.map((d) => String(d.msg || JSON.stringify(d)).replace(/^Value error,\s*/i, '')).join(' · ');
  }
  return 'Error del servidor.';
}

function pesos(n) {
  return '$' + Number(n || 0).toLocaleString('es-CO');
}

function esc(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function aviso(mensaje) {
  const caja = document.getElementById('aviso');
  caja.textContent = mensaje;
  caja.hidden = false;
  clearTimeout(aviso.timer);
  aviso.timer = setTimeout(() => { caja.hidden = true; }, 3200);
}

function fecha(fechaIso) {
  return String(fechaIso ?? '').slice(0, 16).replace('T', ' ');
}

function tipoEntrega(p) {
  if (p.fulfillment === 'dine_in') return 'Mesa ' + (p.table_number ?? '—');
  if (p.fulfillment === 'delivery') return 'Domicilio';
  return 'Recoger';
}

function textoItems(pedido) {
  return pedido.items.map((i) => {
    const extras = (i.additions || []).map((a) => ` +${a.quantity}× ${a.product_name}`).join('');
    return `${i.quantity}× ${i.product_name}${extras}`;
  }).join(' · ');
}

function cambiarVista(nombre) {
  estado.vista = nombre;
  history.replaceState(null, '', '#' + nombre);
  document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('activo', b.dataset.vista === nombre));
  document.querySelectorAll('.vista').forEach((s) => s.classList.toggle('activa', s.id === 'vista-' + nombre));
  document.getElementById('titulo').textContent = TITULOS[nombre][0];
  document.getElementById('subtitulo').textContent = TITULOS[nombre][1];
  render();
}

function render() {
  if (estado.vista === 'panel') renderPanel();
  if (estado.vista === 'menu') renderMenu();
  if (estado.vista === 'pedidos') renderPedidos();
}

async function refrescar() {
  const prods = await api('GET', '/productos?limit=100');
  if (prods) estado.productos = prods;

  if (estado.restauranteId) {
    const pedidos = await api('GET', `/gestion/restaurantes/${estado.restauranteId}/pedidos?limit=50`);
    if (pedidos) {
      estado.pedidos = pedidos;
      estado.pedidosError = '';
    } else if (estado.ultimoError) {
      estado.pedidosError = estado.ultimoError;
    }
  } else {
    estado.pedidos = [];
    estado.pedidosError = '';
  }
  render();
}

function renderPanel() {
  const pedidos = estado.pedidos;
  const ventas = pedidos.reduce((s, p) => s + Number(p.total || 0), 0);
  const porCobrar = pedidos.filter((p) => p.payment_status === 'pending').reduce((s, p) => s + Number(p.total || 0), 0);
  const enCocina = pedidos.filter((p) => ['confirmed', 'preparing', 'cooked'].includes(p.status)).length;
  const listos = pedidos.filter((p) => p.status === 'ready').length;
  const agotados = estado.productos.filter((p) => Number(p.stock) === 0).length;

  document.getElementById('vista-panel').innerHTML = `
    <div class="kpis">
      <div class="kpi"><span>Pedidos cargados</span><strong>${pedidos.length}</strong><em>Últimos 50 del restaurante</em></div>
      <div class="kpi"><span>Ventas</span><strong>${pesos(ventas)}</strong><em>Efectivo por cobrar: ${pesos(porCobrar)}</em></div>
      <div class="kpi"><span>En cocina</span><strong>${enCocina}</strong><em class="${enCocina ? 'baja' : ''}">${enCocina ? 'Comandas activas' : 'Cocina al día'}</em></div>
      <div class="kpi"><span>Listos para servir</span><strong>${listos}</strong><em>${agotados} productos sin stock</em></div>
    </div>

    <div class="tarjeta">
      <div class="tarjeta-head">
        <div><h2>Pedidos recientes</h2><p>Comandas del restaurante seleccionado.</p></div>
        <button class="btn btn-suave btn-mini" data-ir="pedidos">Ver todos</button>
      </div>
      <table>
        <thead><tr><th>Pedido</th><th>Tipo</th><th>Fecha</th><th>Estado</th><th class="num">Total</th></tr></thead>
        <tbody>
          ${pedidos.length ? pedidos.slice(0, 8).map((p) => `
            <tr>
              <td class="fuerte">#${p.id}</td>
              <td>${esc(tipoEntrega(p))}</td>
              <td>${esc(fecha(p.created_at))}</td>
              <td><span class="badge ${ESTADOS[p.status]?.clase ?? ''}">${ESTADOS[p.status]?.texto ?? esc(p.status)}</span></td>
              <td class="num fuerte">${pesos(p.total)} ${esc(p.currency ?? '')}</td>
            </tr>`).join('') : '<tr><td colspan="5"><div class="vacio"><strong>Sin pedidos</strong>Los pedidos de este restaurante aparecerán aquí.</div></td></tr>'}
        </tbody>
      </table>
    </div>

    <div class="tarjeta">
      <div class="tarjeta-head">
        <div><h2>Catálogo de la tienda</h2><p>${estado.productos.length} productos · ${agotados} sin stock.</p></div>
        <button class="btn btn-mini" data-ir="menu">Gestionar catálogo</button>
      </div>
      <table>
        <thead><tr><th>Producto</th><th>Categoría</th><th>Estado</th><th class="num">Precio</th></tr></thead>
        <tbody>
          ${estado.productos.slice(0, 8).map((p) => `
            <tr>
              <td class="fuerte">${esc(p.nombre)}</td>
              <td>${esc(p.categoria)}</td>
              <td><span class="badge ${Number(p.stock) > 0 ? 'ok' : 'alerta'}">${Number(p.stock) > 0 ? 'Disponible' : 'Agotado'}</span></td>
              <td class="num">${pesos(p.precio)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function renderMenu() {
  const categorias = [...new Set(estado.productos.map((p) => p.categoria))].sort((a, b) => a.localeCompare(b, 'es'));
  const lista = estado.productos.filter((p) => !estado.filtroCategoria || p.categoria === estado.filtroCategoria);
  document.getElementById('vista-menu').innerHTML = `
    <div class="tarjeta-head">
      <div class="filtros">
        <button class="chip ${estado.filtroCategoria === '' ? 'activo' : ''}" data-cat="">Todo</button>
        ${categorias.map((c) => `<button class="chip ${estado.filtroCategoria === c ? 'activo' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}
      </div>
      <button class="btn" id="btn-nuevo">Nuevo producto</button>
    </div>
    ${estado.productos.length ? `
    <div class="productos">
      ${lista.map((p) => `
        <article class="producto ${Number(p.stock) > 0 ? '' : 'agotado'}">
          ${p.imagen_url ? `<img src="${esc(p.imagen_url)}" alt="${esc(p.nombre)}">` : ''}
          <div class="cuerpo">
            <h3>${esc(p.nombre)}</h3>
            <p>${esc(p.descripcion)}</p>
            <div class="pie">
              <span class="precio">${pesos(p.precio)}</span>
              <span class="badge ${Number(p.stock) > 0 ? 'ok' : 'alerta'}">${Number(p.stock) > 0 ? 'Disponible' : 'Agotado'}</span>
            </div>
            <div class="fila-suave"><small>Stock: ${p.stock}</small></div>
            <div class="acciones">
              <button class="btn btn-suave btn-mini" data-editar="${p.id}">Editar</button>
              <button class="btn btn-suave btn-mini" data-borrar="${p.id}">Eliminar</button>
            </div>
          </div>
        </article>`).join('')}
    </div>` : `
    <div class="tarjeta"><div class="vacio">
      <strong>Catálogo vacío</strong>
      Crea el primer producto con "Nuevo producto". Requiere una cuenta con rol admin.
    </div></div>`}`;
}

function renderPedidos() {
  const cont = document.getElementById('vista-pedidos');
  if (!estado.restauranteId) {
    cont.innerHTML = '<div class="tarjeta"><div class="vacio"><strong>Sin restaurante seleccionado</strong>Elige un restaurante en la parte superior.</div></div>';
    return;
  }
  if (estado.pedidosError) {
    cont.innerHTML = `<div class="tarjeta"><div class="vacio"><strong>No se pudieron cargar los pedidos</strong>${esc(estado.pedidosError)}</div></div>`;
    return;
  }
  const lista = estado.pedidos.filter((p) => estado.filtroEstado === 'TODOS' || p.status === estado.filtroEstado);
  cont.innerHTML = `
    <div class="tarjeta-head">
      <div class="filtros">
        <button class="chip ${estado.filtroEstado === 'TODOS' ? 'activo' : ''}" data-estado-filtro="TODOS">Todos</button>
        ${Object.keys(ESTADOS).map((k) => `<button class="chip ${estado.filtroEstado === k ? 'activo' : ''}" data-estado-filtro="${k}">${ESTADOS[k].texto}</button>`).join('')}
      </div>
    </div>
    <div class="tarjeta">
      <table>
        <thead><tr><th>Pedido</th><th>Tipo</th><th>Fecha</th><th>Ítems</th><th class="num">Total</th><th>Estado</th></tr></thead>
        <tbody>
          ${lista.length ? lista.map((p) => {
            const siguiente = SIGUIENTE[p.status];
            return `
            <tr>
              <td class="fuerte">#${p.id}</td>
              <td>${esc(tipoEntrega(p))}</td>
              <td>${esc(fecha(p.created_at))}</td>
              <td><span title="${esc(textoItems(p))}">${esc(textoItems(p).slice(0, 60))}${textoItems(p).length > 60 ? '…' : ''}</span></td>
              <td class="num fuerte">${pesos(p.total)} ${esc(p.currency ?? '')}</td>
              <td>
                <span class="badge ${ESTADOS[p.status]?.clase ?? ''}">${ESTADOS[p.status]?.texto ?? esc(p.status)}</span>
                ${siguiente ? `<button class="btn btn-mini" data-avanzar="${p.id}" data-status="${siguiente}">Avanzar a ${ESTADOS[siguiente].texto}</button>` : ''}
              </td>
            </tr>`;
          }).join('') : '<tr><td colspan="6"><div class="vacio"><strong>Sin pedidos en este estado</strong>Cambia el filtro para ver otras comandas.</div></td></tr>'}
        </tbody>
      </table>
    </div>`;
}

function abrirModal(producto) {
  const esNuevo = !producto;
  const p = producto ?? { nombre: '', descripcion: '', precio: 0, stock: 0, categoria: '', imagen_url: '' };
  const categorias = [...new Set(estado.productos.map((x) => x.categoria))].sort((a, b) => a.localeCompare(b, 'es'));
  document.getElementById('modal-titulo').textContent = esNuevo ? 'Nuevo producto' : 'Editar producto';
  document.getElementById('form-producto').innerHTML = `
    <datalist id="lista-categorias">${categorias.map((c) => `<option value="${esc(c)}"></option>`).join('')}</datalist>
    <div class="campo">
      <label for="f-nombre">Nombre</label>
      <input id="f-nombre" name="nombre" required maxlength="80" value="${esc(p.nombre)}" placeholder="Ej. Patacón con queso">
    </div>
    <div class="campo">
      <label for="f-desc">Descripción</label>
      <textarea id="f-desc" name="descripcion" maxlength="256" required placeholder="Ingredientes o detalle breve">${esc(p.descripcion)}</textarea>
    </div>
    <div class="campo-doble">
      <div class="campo">
        <label for="f-precio">Precio (COP)</label>
        <input id="f-precio" name="precio" type="number" min="0" step="1" required value="${p.precio}">
      </div>
      <div class="campo">
        <label for="f-stock">Stock</label>
        <input id="f-stock" name="stock" type="number" min="0" step="1" required value="${p.stock}">
      </div>
    </div>
    <div class="campo-doble">
      <div class="campo">
        <label for="f-cat">Categoría</label>
        <input id="f-cat" name="categoria" list="lista-categorias" required maxlength="80" value="${esc(p.categoria)}" placeholder="Ej. Platos">
      </div>
      <div class="campo">
        <label for="f-img">Foto (URL)</label>
        <input id="f-img" name="imagen_url" type="url" required maxlength="2048" value="${esc(p.imagen_url)}" placeholder="https://…">
      </div>
    </div>
    <div class="modal-pie">
      <button type="button" class="btn btn-suave" id="modal-cancelar">Cancelar</button>
      <button type="submit" class="btn">${esNuevo ? 'Crear producto' : 'Guardar cambios'}</button>
    </div>`;
  const modal = document.getElementById('modal');
  modal.hidden = false;
  modal.dataset.id = esNuevo ? '' : String(p.id);
  document.getElementById('f-nombre').focus();
}

function cerrarModal() {
  document.getElementById('modal').hidden = true;
}

document.getElementById('nav').addEventListener('click', (e) => {
  const boton = e.target.closest('[data-vista]');
  if (boton) cambiarVista(boton.dataset.vista);
});

document.addEventListener('click', async (e) => {
  const t = e.target;

  const ir = t.closest('[data-ir]');
  if (ir) return cambiarVista(ir.dataset.ir);

  const cat = t.closest('[data-cat]');
  if (cat) { estado.filtroCategoria = cat.dataset.cat; return renderMenu(); }

  const filtro = t.closest('[data-estado-filtro]');
  if (filtro) { estado.filtroEstado = filtro.dataset.estadoFiltro; return renderPedidos(); }

  if (t.closest('#btn-nuevo')) return abrirModal(null);

  const editar = t.closest('[data-editar]');
  if (editar) {
    const p = estado.productos.find((x) => x.id === Number(editar.dataset.editar));
    return abrirModal(p);
  }

  const borrar = t.closest('[data-borrar]');
  if (borrar) {
    const p = estado.productos.find((x) => x.id === Number(borrar.dataset.borrar));
    if (!p || !confirm(`¿Eliminar "${p.nombre}" del catálogo?`)) return;
    await api('DELETE', '/productos/' + p.id);
    await refrescar();
    aviso('Producto eliminado');
    return;
  }

  const avanzar = t.closest('[data-avanzar]');
  if (avanzar) {
    const id = Number(avanzar.dataset.avanzar);
    await api('PATCH', `/gestion/restaurantes/${estado.restauranteId}/pedidos/${id}/estado`, { status: avanzar.dataset.status });
    await refrescar();
    aviso(`Pedido #${id}: ${ESTADOS[avanzar.dataset.status].texto}`);
    return;
  }

  if (t.closest('#btn-salir')) return salir();

  if (t.closest('#modal-cerrar') || t.closest('#modal-cancelar')) return cerrarModal();
  if (t.id === 'modal') return cerrarModal();
});

document.getElementById('form-producto').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const id = document.getElementById('modal').dataset.id;
  const cuerpo = {
    nombre: String(f.get('nombre')).trim(),
    descripcion: String(f.get('descripcion')).trim(),
    precio: Number(f.get('precio')),
    stock: Number(f.get('stock')),
    categoria: String(f.get('categoria')).trim(),
    imagen_url: String(f.get('imagen_url')).trim(),
  };
  if (!cuerpo.nombre) return aviso('El nombre es obligatorio');
  if (!cuerpo.descripcion) return aviso('La descripción es obligatoria');
  if (!Number.isInteger(cuerpo.precio) || cuerpo.precio < 0) return aviso('El precio debe ser un entero sin decimales');
  if (!Number.isInteger(cuerpo.stock) || cuerpo.stock < 0) return aviso('El stock debe ser un entero sin decimales');
  if (!cuerpo.categoria) return aviso('La categoría es obligatoria');

  const ok = id ? await api('PUT', '/productos/' + id, cuerpo) : await api('POST', '/productos', cuerpo);
  if (ok === null) return;
  cerrarModal();
  await refrescar();
  aviso(id ? 'Producto actualizado' : 'Producto creado');
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') cerrarModal();
});

document.getElementById('restaurante').addEventListener('change', (e) => {
  estado.restauranteId = Number(e.target.value) || null;
  localStorage.setItem(LS_REST, estado.restauranteId ? String(estado.restauranteId) : '');
  estado.pedidos = [];
  estado.pedidosError = '';
  refrescar();
});

function mostrarLogin() {
  document.getElementById('app').hidden = true;
  document.getElementById('login').hidden = false;
}

function mostrarApp() {
  document.getElementById('login').hidden = true;
  document.getElementById('app').hidden = false;
  const u = estado.usuario ?? {};
  document.getElementById('usuario-info').innerHTML =
    `<strong>${esc([u.nombre, u.apellido].filter(Boolean).join(' ') || u.usuario || 'Usuario')}</strong><span>${esc(u.usuario ?? '')} · ${esc(u.rol ?? '')}</span>`;
}

function salir(mensaje) {
  localStorage.removeItem(LS_TOKEN);
  localStorage.removeItem(LS_USER);
  estado.token = '';
  estado.usuario = null;
  estado.productos = [];
  estado.pedidos = [];
  mostrarLogin();
  if (mensaje) aviso(mensaje);
}

async function cargarRestaurantes() {
  const lista = await api('GET', '/restaurantes?limit=100');
  estado.restaurantes = Array.isArray(lista) ? lista : [];
  const sel = document.getElementById('restaurante');
  if (!estado.restaurantes.length) {
    sel.innerHTML = '<option value="">Sin restaurantes</option>';
    estado.restauranteId = null;
    return;
  }
  sel.innerHTML = estado.restaurantes.map((r) => `<option value="${r.id}" ${r.id === estado.restauranteId ? 'selected' : ''}>${esc(r.name)}</option>`).join('');
  if (!estado.restaurantes.some((r) => r.id === estado.restauranteId)) {
    estado.restauranteId = estado.restaurantes[0].id;
    sel.value = String(estado.restauranteId);
    localStorage.setItem(LS_REST, String(estado.restauranteId));
  }
}

document.getElementById('form-login').addEventListener('submit', async (e) => {
  e.preventDefault();
  const error = document.getElementById('login-error');
  error.hidden = true;
  const base = document.getElementById('api-url').value.trim().replace(/\/+$/, '');
  const usuario = document.getElementById('login-usuario').value.trim();
  const contrasena = document.getElementById('login-clave').value;
  try {
    const r = await fetch(base + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, contrasena }),
    });
    const j = await r.json().catch(() => null);
    if (!r.ok || !j?.access_token) {
      error.textContent = detalle(j) || 'No se pudo iniciar sesión.';
      error.hidden = false;
      return;
    }
    estado.base = base;
    estado.token = j.access_token;
    estado.usuario = j.usuario;
    localStorage.setItem(LS_URL, base);
    localStorage.setItem(LS_TOKEN, estado.token);
    localStorage.setItem(LS_USER, JSON.stringify(j.usuario));
    await iniciar();
  } catch (_) {
    error.textContent = 'No se pudo conectar con la API en ' + base + ' (¿está corriendo?)';
    error.hidden = false;
  }
});

async function iniciar() {
  mostrarApp();
  await cargarRestaurantes();
  const inicial = location.hash.replace('#', '');
  cambiarVista(['panel', 'menu', 'pedidos'].includes(inicial) ? inicial : 'panel');
  refrescar();
}

document.getElementById('fecha').textContent = new Date().toLocaleDateString('es-CO', {
  weekday: 'long', day: 'numeric', month: 'long',
});

setInterval(() => {
  if (estado.token && !document.getElementById('app').hidden && document.getElementById('modal').hidden && !document.hidden) refrescar();
}, 5000);

document.getElementById('api-url').value = estado.base;

if (estado.token && estado.usuario) {
  iniciar();
} else {
  mostrarLogin();
}
