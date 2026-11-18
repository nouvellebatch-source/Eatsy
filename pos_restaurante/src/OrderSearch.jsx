import React, {useCallback,useEffect,useState} from 'react';
import {request} from './api';
import {downloadOrders} from './operations';

export function OrderSearch({restaurant,token,renderBoard}) {
 const [term,setTerm]=useState(''),[query,setQuery]=useState(''),[offset,setOffset]=useState(0),[orders,setOrders]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=useCallback(async()=>{setBusy(true);setError('');try{setOrders(await request(`/gestion/restaurantes/${restaurant}/pedidos?limit=100&offset=${offset}&q=${encodeURIComponent(query)}`,{token}))}catch(e){setError(e.message);setOrders([])}finally{setBusy(false)}},[restaurant,token,offset,query]);
 useEffect(()=>{load()},[load]);
 async function exportAll(){setBusy(true);setError('');try{
  let all=[];for(let start=0;start<1000;start+=100){const page=await request(`/gestion/restaurantes/${restaurant}/pedidos?limit=100&offset=${start}&q=${encodeURIComponent(query)}`,{token});all=all.concat(page);if(page.length<100)break}
  downloadOrders(all);if(all.length===1000)setError('El archivo contiene hasta 1.000 pedidos; utiliza una búsqueda para acotar los resultados.');
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <section><form className="section-title" onSubmit={e=>{e.preventDefault();setOffset(0);setQuery(term.trim())}}><label>Buscar por número de pedido o mesa <input value={term} onChange={e=>setTerm(e.target.value)} inputMode="numeric" placeholder="Número"/></label><button className="secondary" disabled={busy}>Buscar</button><button type="button" className="secondary" disabled={busy} onClick={exportAll}>Exportar resultados CSV</button></form><p className="caption">Se consultan 100 pedidos por página. La exportación incluye hasta 1.000 resultados.</p>{error&&<div className="alert" role="alert">{error}</div>}{renderBoard(orders,busy,load)}<button className="secondary" disabled={busy||offset===0} onClick={()=>setOffset(x=>Math.max(0,x-100))}>Anterior</button> <button className="secondary" disabled={busy||orders.length<100} onClick={()=>setOffset(x=>x+100)}>Siguiente</button></section>
}
