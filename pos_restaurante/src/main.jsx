import React, {useEffect, useState, useCallback, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {ChefHat, ClipboardList, LayoutDashboard, LogOut, RefreshCw, UtensilsCrossed, CalendarDays, Grid2X2, CircleHelp, Clock, Store, ChevronRight, BadgePercent, ChartNoAxesCombined} from 'lucide-react';
import {request, nextStatus, labels} from './api';
import {Finances, Promotions, Events} from './Commercial';
import './style.css';

const money = value => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(value ?? 0);
const stages = ['confirmed','preparing','cooked','ready'];

function App(){
 const [token,setToken]=useState(null), [user,setUser]=useState(null), [restaurants,setRestaurants]=useState([]);
 const [restaurant,setRestaurant]=useState(''), [page,setPage]=useState('inicio'), [orders,setOrders]=useState([]);
 const [error,setError]=useState(''), [busy,setBusy]=useState(false), [loading,setLoading]=useState(false), [last,setLast]=useState(null);
 const [username,setUsername]=useState(''), [password,setPassword]=useState('');
 const [authScreen,setAuthScreen]=useState('login'), [registrationEmail,setRegistrationEmail]=useState('');
 const requestVersion=useRef(0);
 const load=useCallback(async (quiet=false) => {
   if(!token || !restaurant) return;
   const version=++requestVersion.current;
   if(!quiet) setLoading(true);
   try { const data=await request(`/gestion/restaurantes/${restaurant}/pedidos?limit=100`,{token}); if(version===requestVersion.current){setOrders(data);setError('');setLast(new Date());} }
   catch(e){ if(version===requestVersion.current){setError(e.message);setOrders([]);setLast(null);} }
   finally { if(version===requestVersion.current)setLoading(false); }
 },[token,restaurant]);
 useEffect(()=>{if(!token)return; request('/restaurantes?limit=100').then(r=>{setRestaurants(r);if(r.length===1)setRestaurant(String(r[0].id));}).catch(e=>setError(e.message));},[token]);
 useEffect(()=>{load(); if(!token || !restaurant)return; const id=setInterval(()=>load(true),15000);return ()=>clearInterval(id);},[load,token,restaurant]);
 async function login(e){ e.preventDefault();setBusy(true);setError('');try{
   const result=await request('/auth/login',{method:'POST',body:JSON.stringify({usuario:username.trim(),contrasena:password})});
   setPassword('');setToken(result.access_token);setUser(result.usuario);setPage('inicio');
 }catch(e){setError(e.message);}finally{setBusy(false)} }
 async function advance(order){const target=nextStatus[order.status];if(!target)return;setBusy(true);setError('');try{
   await request(`/gestion/restaurantes/${restaurant}/pedidos/${order.id}/estado`,{token,method:'PATCH',body:JSON.stringify({status:target})});await load();
 }catch(e){setError(e.message);await load(true);}finally{setBusy(false)}}
 async function confirmPayment(order){if(!window.confirm(`¿Confirmas que recibiste ${money(order.total)} en efectivo para el pedido #${order.id}?`))return;setBusy(true);setError('');try{
   await request(`/gestion/restaurantes/${restaurant}/pedidos/${order.id}/pago`,{token,method:'PATCH'});await load();
 }catch(e){await load(true);setError(e.message);}finally{setBusy(false)}}
 const logout=()=>{requestVersion.current++;setToken(null);setUser(null);setRestaurant('');setRestaurants([]);setOrders([]);setPassword('');setError('');setLast(null);};
 if(!token)return <main className="login"><section className="login-brand"><div className="brand light">eatsy<span>.</span></div><div className="tag">POS PARA RESTAURANTES</div><h1>Una operación ágil,<br/>una mesa feliz.</h1><p>Comandas, cocina y equipo en un solo lugar.</p><div className="brand-note"><ChefHat size={23}/><div><b>Tu cocina, conectada</b><small>Pedidos y estados desde Eatsy</small></div></div></section><section className="login-form">
 {authScreen==='login' ? <><div className="eyebrow">BIENVENIDO A EATSY</div><h2>Ingresa a tu restaurante</h2><p>Usa tus credenciales de la operación.</p><form onSubmit={login}><label>USUARIO<input autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)} placeholder="Usuario de Eatsy"/></label><label>CONTRASEÑA<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Tu contraseña"/></label>{error&&<div className="alert" role="alert">{error}</div>}<button className="primary" disabled={busy}>{busy?'Ingresando…':'Entrar al POS'} <ChevronRight size={16}/></button></form><p className="footnote">El acceso a cada restaurante se valida con tu cuenta y sus permisos.</p><p className="signup-link">¿Aún no tienes cuenta? <button className="text-link" onClick={()=>{setError('');setAuthScreen('register')}}>Crear mi cuenta</button></p></> :
 <AccountRegistration screen={authScreen} setScreen={setAuthScreen} email={registrationEmail} setEmail={setRegistrationEmail} onComplete={()=>{setAuthScreen('login');setError('')}}/>}
 </section></main>;
 const restaurantName=restaurants.find(r=>String(r.id)===restaurant)?.name || 'Selecciona restaurante';
 const menu=[['inicio','Inicio',LayoutDashboard],['comandas','Comandas',ClipboardList],['cocina','Cocina',ChefHat],['mesas','Mesas',Grid2X2],['reservas','Reservas',CalendarDays],['descuentos','Descuentos',BadgePercent],['eventos','Eventos',CalendarDays],['finanzas','Finanzas',ChartNoAxesCombined],['guia','Guía de procesos',CircleHelp]];
 return <div className="app"><aside className="sidebar"><div className="brand light">eatsy<span>.</span></div><p className="sidebar-label">CENTRO DE CONTROL</p><div className="restaurant-label"><Store size={16}/> {restaurantName}</div><nav>{menu.map(([id,label,Icon])=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon size={17}/>{label}</button>)}</nav><button className="logout" onClick={logout}><LogOut size={17}/> Cerrar sesión</button></aside>
 <div className="main"><header><div><span className="eyebrow">RESTAURANTE / </span><b>{menu.find(x=>x[0]===page)?.[1]}</b></div><div className="head-right"><span className="live"><i/> {last?'Conectado':'Sin actualizar'}</span><span>{user?.nombre || user?.usuario}</span></div></header>
 <div className="content"><div className="toolbar"><div><span className="eyebrow">TU OPERACIÓN EN EATSY</span><h1>{page==='inicio'?'Tu restaurante, en orden':menu.find(x=>x[0]===page)?.[1]}</h1><p>Gestiona la operación con información conectada a Eatsy.</p></div><div className="controls"><label className="sr-only" htmlFor="restaurant">Restaurante</label><select id="restaurant" value={restaurant} onChange={e=>{requestVersion.current++;setRestaurant(e.target.value);setOrders([]);setError('');setLast(null);setLoading(false);}}><option value="">Selecciona restaurante</option>{restaurants.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select><button className="secondary icon-button" onClick={()=>load()} title="Actualizar"><RefreshCw size={17}/></button></div></div>
 {error&&<div className="alert" role="alert">{error}</div>}
 {!restaurant&&<div className="notice">Selecciona un restaurante para consultar su información.</div>}
 {page==='inicio'&&<><section className="hero"><div><span className="hero-tag">TU EQUIPO, CONECTADO</span><h2>Todo listo para<br/>un gran servicio.</h2><p>Consulta tus comandas y acompaña cada plato desde cocina.</p><button className="hero-button" onClick={()=>setPage('cocina')}>Ir a cocina <ChevronRight size={16}/></button></div><img src="/pos-ilustracion.png" alt="Ilustración de alimentos"/></section><div className="metrics"><Metric label="Pedidos consultados" value={restaurant&&!error?orders.length:'—'} icon={<ClipboardList/>}/><Metric label="En preparación" value={restaurant&&!error?orders.filter(x=>x.status==='preparing').length:'—'} icon={<ChefHat/>}/><Metric label="Listos para entrega" value={restaurant&&!error?orders.filter(x=>x.status==='ready').length:'—'} icon={<UtensilsCrossed/>}/></div><p className="caption">Indicadores calculados sobre los últimos 100 pedidos consultados, no ventas totales.</p><Board orders={orders.filter(o=>o.status!=='delivered').slice(0,4)} advance={advance} confirmPayment={confirmPayment} busy={busy} loading={loading} compact/></>}
 {page==='comandas'&&<Board orders={orders} advance={advance} confirmPayment={confirmPayment} busy={busy} loading={loading}/>}
 {page==='cocina'&&<><div className="section-title"><div><h2>Pase de cocina</h2><p>Actualización automática cada 15 segundos.</p></div><span className="pill">EN VIVO</span></div><div className="kanban">{stages.map(stage=><section className="lane" key={stage}><div className="lane-title">{labels[stage]} <span>{orders.filter(o=>o.status===stage).length}</span></div>{orders.filter(o=>o.status===stage).map(order=><OrderCard key={order.id} order={order} advance={advance} confirmPayment={confirmPayment} busy={busy}/>)}</section>)}</div></>}
 {page==='mesas'&&restaurant&&<Tables key={restaurant} token={token} restaurant={restaurant}/>}
 {page==='reservas'&&restaurant&&<Reservations key={restaurant} token={token} restaurant={restaurant}/>}
 {page==='descuentos'&&restaurant&&<Promotions key={restaurant} restaurant={restaurant} token={token}/>}
 {page==='eventos'&&restaurant&&<Events key={restaurant} restaurant={restaurant} token={token}/>}
 {page==='finanzas'&&restaurant&&<Finances key={restaurant} restaurant={restaurant} token={token}/>}
 {page==='guia'&&<div className="guide"><h2>Del pedido a la entrega</h2><p>Avanza cada comanda cuando el equipo complete el paso correspondiente.</p>{[['01','Confirmado','El pedido fue registrado automáticamente.'],['02','En preparación','La cocina comienza a preparar los productos.'],['03','Cocinado','La cocción ha terminado.'],['04','Listo','El pedido está listo para entregar.'],['05','Entregado','El equipo confirma la entrega en mesa o recogida.']].map(([n,title,desc])=><div className="guide-item" key={n}><span>{n}</span><div><b>{title}</b><p>{desc}</p></div></div>)}<div className="notice">El pago en efectivo permanece pendiente hasta contar con un registro de cobro conectado.</div></div>}
 </div></div></div>;
}
function AccountRegistration({screen,setScreen,email,setEmail,onComplete}){
 const [form,setForm]=useState({nombre:'',apellido:'',usuario:'',contrasena:'',confirmacion:''}),[code,setCode]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const field=(name,value)=>setForm(previous=>({...previous,[name]:value}));
 async function submit(e){e.preventDefault();setError('');setMessage('');
  if(form.contrasena!==form.confirmacion){setError('Las contraseñas no coinciden.');return;}
  if(form.contrasena.length<12||form.contrasena.length>128){setError('La contraseña debe tener entre 12 y 128 caracteres.');return;}
  setBusy(true);try{
   await request('/auth/registro',{method:'POST',body:JSON.stringify({nombre:form.nombre.trim(),apellido:form.apellido.trim(),usuario:form.usuario.trim(),correo:email.trim(),contrasena:form.contrasena})});
   setForm(previous=>({...previous,contrasena:'',confirmacion:''}));setScreen('verify');setMessage('Revisa tu correo e introduce el código de seis dígitos.');
  }catch(e){setError(e.message);}finally{setBusy(false)}
 }
 async function verify(e){e.preventDefault();setBusy(true);setError('');setMessage('');try{
   await request('/auth/verificar-correo',{method:'POST',body:JSON.stringify({correo:email.trim(),codigo:code.trim()})});
   setScreen('success');
  }catch(e){setError(e.message);}finally{setBusy(false)}
 }
 async function resend(){setBusy(true);setError('');setMessage('');try{
   await request('/auth/reenviar-codigo',{method:'POST',body:JSON.stringify({correo:email.trim()})});
   setMessage('Si existe un registro pendiente, recibirás un código. Revisa también spam.');
  }catch(e){setError(e.message);}finally{setBusy(false)}
 }
 return <><div className="eyebrow">CUENTA PARA TU EQUIPO</div>
 {screen==='success'?<><h2>Correo confirmado</h2><p>Tu cuenta fue creada. Un administrador de Eatsy debe vincularla al restaurante y asignarle un rol antes de que puedas utilizar el POS.</p><button className="primary account-action" onClick={onComplete}>Ir a iniciar sesión</button></>:
 screen==='register'?<><h2>Crea tu cuenta</h2><p>Regístrate y verifica tu correo. El acceso al restaurante requiere una asignación de permisos.</p><form onSubmit={submit} className="account-form">
 <div className="account-grid"><label>NOMBRE<input required maxLength={80} autoComplete="given-name" value={form.nombre} onChange={e=>field('nombre',e.target.value)}/></label><label>APELLIDO<input required maxLength={80} autoComplete="family-name" value={form.apellido} onChange={e=>field('apellido',e.target.value)}/></label></div>
 <label>USUARIO<input required maxLength={80} autoComplete="username" value={form.usuario} onChange={e=>field('usuario',e.target.value)}/></label>
 <label>CORREO ELECTRÓNICO<input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
 <label>CONTRASEÑA<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={form.contrasena} onChange={e=>field('contrasena',e.target.value)}/><small>Mínimo 12 caracteres.</small></label>
 <label>CONFIRMAR CONTRASEÑA<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={form.confirmacion} onChange={e=>field('confirmacion',e.target.value)}/></label>
 {error&&<div className="alert" role="alert">{error}</div>}<button className="primary" disabled={busy}>{busy?'Enviando…':'Crear cuenta y enviar código'}</button></form>
 <button className="text-link account-action" onClick={()=>{setError('');setScreen('verify')}}>Ya tengo un código</button></>:
 <><h2>Confirma tu correo</h2><p>Ingresa el código de seis dígitos que recibiste. Revisa spam si no lo encuentras.</p><form onSubmit={verify} className="account-form"><label>CORREO ELECTRÓNICO<input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><label>CÓDIGO DE VERIFICACIÓN<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e=>setCode(e.target.value)} placeholder="000000"/></label>{error&&<div className="alert" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}<button className="primary" disabled={busy}>{busy?'Verificando…':'Confirmar correo'}</button></form><button className="text-link account-action" disabled={busy||!email.includes('@')} onClick={resend}>Reenviar código</button></>}
 {screen!=='success'&&<p className="footnote"><button className="text-link" onClick={onComplete}>Volver a iniciar sesión</button></p>}</>;
}
function Metric({label,value,icon}){return <div className="metric"><div className="metric-icon">{icon}</div><span>{label}</span><strong>{value}</strong></div>}
function Tables({token,restaurant}){
 const [tables,setTables]=useState(null), [error,setError]=useState('');
 const refresh=useCallback(async ()=>{try {const data=await request(`/gestion/restaurantes/${restaurant}/mesas`,{token});setTables(data);setError('');}catch(e){setError(e.message);setTables(null);}},[restaurant,token]);
 useEffect(()=>{let active=true;let running=false;async function poll(){if(running)return;running=true;try{const data=await request(`/gestion/restaurantes/${restaurant}/mesas`,{token});if(active){setTables(data);setError('');}}catch(e){if(active){setError(e.message);setTables(null);}}finally{running=false;}}poll();const id=setInterval(poll,15000);return ()=>{active=false;clearInterval(id)}},[restaurant,token]);
 const branches=[...new Map((tables||[]).map(t=>[t.branch_id,t.branch_name])).entries()];
 return <section><div className="section-title"><div><h2>Mapa de salón</h2><p>Mostramos la persona del pedido activo más reciente de cada mesa. La ocupación no está confirmada.</p></div><button className="secondary" onClick={refresh}><RefreshCw size={16}/></button></div>
 {error?<div className="alert" role="alert">{error}</div>:tables===null?<p>Cargando mesas…</p>:tables.length===0?<div className="empty small">No hay mesas registradas.</div>:branches.map(([id,branch])=><div key={id}><h3 className="table-branch">{branch}</h3><div className="table-grid">{tables.filter(t=>t.branch_id===id).map((t,index)=><article className={'table-card '+(t.active_orders?'has-orders':'')} style={{animationDelay:`${Math.min(index,15)*35}ms`}} key={t.id}>
 <span className="table-customer">{t.customer_names || (t.reservation_name ? `Reserva: ${t.reservation_name}` : 'Sin pedido activo')}</span><div className="table-visual"><Grid2X2 size={24}/></div><strong>Mesa {t.table_number}</strong><small>{t.capacity} personas</small>{t.reservation_name&&t.customer_names&&<small>Reserva: {t.reservation_name}</small>}{t.active_orders>0&&<span className="table-order">{t.active_orders} pedido(s) activo(s)<br/>Total: {money(t.total_orders)}<br/>Pagado: {money(t.total_paid)}</span>}</article>)}</div></div>)}
 </section>
}
function Reservations({token,restaurant}){
 const [reservations,setReservations]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=useCallback(async()=>{try{setReservations(await request(`/gestion/restaurantes/${restaurant}/reservas`,{token}));setError('')}catch(e){setError(e.message);setReservations(null)}},[token,restaurant]);
 useEffect(()=>{load();const id=setInterval(load,15000);return ()=>clearInterval(id)},[load]);
 async function cancel(item){if(!window.confirm(`¿Cancelar la reserva de ${item.customer_name} para la mesa ${item.table_number}?`))return;
   setBusy(true);try{await request(`/gestion/restaurantes/${restaurant}/reservas/${item.id}/cancelar`,{token,method:'PATCH'});await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
 const date=value=>new Date(value.endsWith('Z')?value:value+'Z').toLocaleString('es-CO');
 return <section><div className="section-title"><div><h2>Reservas registradas</h2><p>Los clientes crean sus reservas desde Eatsy. Horarios en la zona horaria de este dispositivo.</p></div><button className="secondary" onClick={load}>Actualizar</button></div>
 {error?<div className="alert" role="alert">{error}</div>:reservations===null?<p>Cargando reservas…</p>:reservations.length===0?<div className="empty small">Aún no hay reservas.</div>:reservations.map(item=><article className="order reservation-card" key={item.id}><div><b>{item.customer_name} · Mesa {item.table_number}</b><p>{item.party_size} personas · {date(item.starts_at)} — {date(item.ends_at)}</p><small>{item.status==='confirmed'?'Confirmada':'Cancelada'}</small></div>{item.status==='confirmed'&&<button className="secondary" disabled={busy} onClick={()=>cancel(item)}>Cancelar</button>}</article>)}</section>
}
function Unavailable({icon,title,text}){return <div className="empty"><div className="empty-icon">{icon}</div><h2>{title}</h2><p>{text}</p></div>}
function Board({orders,advance,confirmPayment,busy,loading,compact}){return <section><div className="section-title"><div><h2>{compact?'Comandas recientes':'Comandas'}</h2><p>Pedidos reales de tu restaurante.</p></div></div>{loading?<p>Cargando pedidos…</p>:orders.length===0?<div className="empty small">No hay pedidos para mostrar.</div>:<div className="cards">{orders.map(o=><OrderCard key={o.id} order={o} advance={advance} confirmPayment={confirmPayment} busy={busy}/>)}</div>}</section>}
function OrderCard({order,advance,confirmPayment,busy}){const canAdvance=nextStatus[order.status] && !(order.fulfillment==='delivery' && order.status==='ready');return <article className="order"><div className="order-head"><div><span className="order-id">PEDIDO #{order.id}</span><h3>{order.fulfillment==='dine_in'?`Mesa ${order.table_number || '—'}`:order.fulfillment==='pickup'?'Recoger en tienda':'Domicilio'}</h3></div><span className={'status '+order.status}>{labels[order.status]||order.status}</span></div><div className="order-time"><Clock size={14}/> {order.created_at ? new Date(order.created_at.endsWith('Z')?order.created_at:order.created_at+'Z').toLocaleString('es-CO'):'Hora no disponible'}</div><ul>{(order.items||[]).map((item,i)=><li key={i}><b>{item.quantity}×</b> {item.product_name}{item.additions?.length>0&&<ul className="extras">{item.additions.map((a,j)=><li key={j}>+ {a.quantity}× {a.product_name} por unidad</li>)}</ul>}</li>)}</ul>{order.discount_amount>0&&<div className="order-note">Código {order.discount_code} · descuento {money(order.discount_amount)}</div>}{order.customer_note&&<div className="order-note">Nota: {order.customer_note}</div>}<div className="order-footer"><div><b>{money(order.total)}</b><small>Efectivo · {order.payment_status==='pending'?'pendiente':order.payment_status}</small></div>{order.payment_method==='cash'&&order.payment_status==='pending'&&<button className="action" disabled={busy} onClick={()=>confirmPayment(order)}>Confirmar efectivo</button>}{canAdvance&&<button className="action" disabled={busy} onClick={()=>advance(order)}>{labels[nextStatus[order.status]]} <ChevronRight size={14}/></button>}</div></article>}

createRoot(document.getElementById('root')).render(<App/>);
