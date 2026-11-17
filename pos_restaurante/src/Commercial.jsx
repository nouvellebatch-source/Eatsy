import React, {useCallback,useEffect,useState} from 'react';
import {request} from './api';
const money=n=>new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n||0);
const localDate=value=>new Date(value.endsWith('Z')?value:value+'Z').toLocaleString('es-CO');
export function Finances({restaurant,token}){
 const [data,setData]=useState(null),[error,setError]=useState('');
 const load=useCallback(async()=>{try{setData(await request(`/gestion/restaurantes/${restaurant}/finanzas`,{token}));setError('')}catch(e){setData(null);setError(e.message)}},[restaurant,token]);
 useEffect(()=>{load();const id=setInterval(load,30000);return()=>clearInterval(id)},[load]);
 return <section><div className="section-title"><div><h2>Ingresos confirmados</h2><p>Solo pagos en efectivo registrados por caja. Corte diario en horario de Colombia.</p></div><button className="secondary" onClick={load}>Actualizar</button></div>
 {error?<div className="alert" role="alert">{error}</div>:!data?<p>Cargando finanzas…</p>:<><div className="metrics"><div className="metric"><span>Total recibido</span><strong>{money(data.revenue)}</strong></div><div className="metric"><span>Pagos confirmados</span><strong>{data.paid_count}</strong></div><div className="metric"><span>Promedio por pago</span><strong>{money(data.paid_count?Math.round(data.revenue/data.paid_count):0)}</strong></div></div><p className="caption">Acumulado histórico; no incluye pagos pendientes, devoluciones ni gastos.</p><div className="guide"><h2>Últimos días con pagos</h2>{data.days.length===0?<p>Aún no hay pagos confirmados.</p>:data.days.map(d=><div className="guide-item" key={d.day}><span>{d.day}</span><div><b>{money(d.revenue)}</b><p>{d.payments} pago(s)</p></div></div>)}</div></>}
 </section>
}
export function Promotions({restaurant,token}){
 const [items,setItems]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [form,setForm]=useState({code:'',title:'',percent_off:'10',starts_at:'',ends_at:''});
 const change=(key,value)=>setForm(v=>({...v,[key]:value}));
 const load=useCallback(async()=>{try{setItems(await request(`/gestion/restaurantes/${restaurant}/promociones`,{token}));setError('')}catch(e){setItems(null);setError(e.message)}},[restaurant,token]);
 useEffect(()=>{load()},[load]);
 async function create(e){e.preventDefault();setBusy(true);setError('');try{
  const start=new Date(form.starts_at),end=new Date(form.ends_at);
  if(Number.isNaN(start.getTime())||Number.isNaN(end.getTime())||end<=start)throw new Error('Comprueba el horario de la promoción.');
  await request(`/gestion/restaurantes/${restaurant}/promociones`,{token,method:'POST',body:JSON.stringify({
   code:form.code.trim().toUpperCase(),title:form.title.trim(),percent_off:Number(form.percent_off),starts_at:start.toISOString(),ends_at:end.toISOString()})});
  setForm({code:'',title:'',percent_off:'10',starts_at:'',ends_at:''});await load();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 async function disable(item){if(!window.confirm(`¿Desactivar la promoción ${item.code}?`))return;setBusy(true);try{
  await request(`/gestion/restaurantes/${restaurant}/promociones/${item.id}/desactivar`,{token,method:'PATCH'});await load();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <div className="reservations"><section className="guide"><h2>Crear promoción</h2><p>El descuento se calcula en la API al confirmar el pedido.</p>
 <form className="reservation-form" onSubmit={create}>
 <label>Nombre<input required maxLength="120" value={form.title} onChange={e=>change('title',e.target.value)}/></label>
 <label>Código<input required maxLength="40" pattern="[A-Za-z0-9_-]+" value={form.code} onChange={e=>change('code',e.target.value)} placeholder="Ej. PIZZA10"/></label>
 <label>Descuento (%)<input required type="number" min="1" max="100" value={form.percent_off} onChange={e=>change('percent_off',e.target.value)}/></label>
 <label>Inicio<input required type="datetime-local" value={form.starts_at} onChange={e=>change('starts_at',e.target.value)}/></label>
 <label>Final<input required type="datetime-local" value={form.ends_at} onChange={e=>change('ends_at',e.target.value)}/></label>
 {error&&<div className="alert" role="alert">{error}</div>}<button className="primary" disabled={busy||!items}>{busy?'Guardando…':'Crear promoción'}</button></form></section>
 <section><div className="section-title"><div><h2>Promociones</h2><p>Las promociones vigentes se muestran en la aplicación.</p></div><button className="secondary" onClick={load}>Actualizar</button></div>
 {items===null?<div className="alert">{error||'Cargando…'}</div>:items.length===0?<div className="empty small">Aún no hay promociones.</div>:items.map(item=><article className="order reservation-card" key={item.id}><div><b>{item.title} · {item.percent_off}%</b><p>Código: {item.code}</p><p>{localDate(item.starts_at)} — {localDate(item.ends_at)}</p><small>{item.active?'Habilitada':'Desactivada'}</small></div>{item.active&&<button className="secondary" disabled={busy} onClick={()=>disable(item)}>Desactivar</button>}</article>)}</section></div>;
}
export function Events({restaurant,token}){
 const [items,setItems]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [form,setForm]=useState({title:'',description:'',starts_at:'',ends_at:''});
 const change=(k,v)=>setForm(old=>({...old,[k]:v}));
 const load=useCallback(async()=>{try{setItems(await request(`/gestion/restaurantes/${restaurant}/eventos`,{token}));setError('')}catch(e){setItems(null);setError(e.message)}},[restaurant,token]);
 useEffect(()=>{load()},[load]);
 async function create(e){e.preventDefault();setBusy(true);setError('');try{
  const start=new Date(form.starts_at),end=new Date(form.ends_at);
  if(Number.isNaN(start.getTime())||Number.isNaN(end.getTime())||end<=start)throw new Error('Comprueba el horario del evento.');
  await request(`/gestion/restaurantes/${restaurant}/eventos`,{token,method:'POST',body:JSON.stringify({title:form.title.trim(),description:form.description.trim(),starts_at:start.toISOString(),ends_at:end.toISOString()})});
  setForm({title:'',description:'',starts_at:'',ends_at:''});await load();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 async function disable(item){if(!window.confirm(`¿Desactivar el evento ${item.title}?`))return;setBusy(true);try{
  await request(`/gestion/restaurantes/${restaurant}/eventos/${item.id}/desactivar`,{token,method:'PATCH'});await load();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <div className="reservations"><section className="guide"><h2>Crear evento</h2><p>Los eventos próximos aparecerán en el menú de Flutter.</p><form className="reservation-form" onSubmit={create}>
 <label>Nombre<input required maxLength="120" value={form.title} onChange={e=>change('title',e.target.value)}/></label>
 <label>Descripción<input required maxLength="500" value={form.description} onChange={e=>change('description',e.target.value)}/></label>
 <label>Inicio<input required type="datetime-local" value={form.starts_at} onChange={e=>change('starts_at',e.target.value)}/></label>
 <label>Final<input required type="datetime-local" value={form.ends_at} onChange={e=>change('ends_at',e.target.value)}/></label>
 {error&&<div className="alert" role="alert">{error}</div>}<button className="primary" disabled={busy||!items}>{busy?'Guardando…':'Crear evento'}</button></form></section>
 <section><div className="section-title"><div><h2>Eventos</h2><p>Horarios en la zona horaria de este dispositivo.</p></div><button className="secondary" onClick={load}>Actualizar</button></div>
 {items===null?<div className="alert">{error||'Cargando…'}</div>:items.length===0?<div className="empty small">Aún no hay eventos.</div>:items.map(item=><article className="order reservation-card" key={item.id}><div><b>{item.title}</b><p>{item.description}</p><p>{localDate(item.starts_at)} — {localDate(item.ends_at)}</p><small>{item.active?'Habilitado':'Desactivado'}</small></div>{item.active&&<button className="secondary" disabled={busy} onClick={()=>disable(item)}>Desactivar</button>}</article>)}</section></div>;
}
