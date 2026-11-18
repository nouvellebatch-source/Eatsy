import React, {useState, useEffect} from 'react';
import {request} from './api';

export function MenuImport({restaurant,token}) {
 const [revision,setRevision]=useState(0);
 const [file,setFile]=useState(null),[items,setItems]=useState([]),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const edit=(index,field,value)=>setItems(old=>old.map((item,i)=>i===index?{...item,[field]:value}:item));
 async function extract(e){e.preventDefault(); if(!file)return; setError('');setMessage('');setItems([]);setBusy(true);try {
   const data=await request(`/gestion/restaurantes/${restaurant}/carta/extraer?proveedor=local`,{token,method:'POST',body:file,timeoutMs:100000,headers:{'Content-Type':'application/pdf'}});
   setItems(data.items);setMessage(`Se leyeron ${data.pages} páginas (${data.ocr_pages} mediante OCR). Revisa y corrige cada propuesta antes de publicar.`);
 } catch(err){setError(err.message)} finally{setBusy(false)}}
 async function publish(){setError('');setMessage('');
  const parsed=items.map(x=>({...x,price:Number(x.price)}));
  if(items.some(x=>String(x.price).trim()==='')||parsed.some(x=>!x.name.trim()||!x.category.trim()||!Number.isSafeInteger(x.price)||x.price<0||x.price>1000000000)){setError('Revisa nombre, categoría y precio entero de cada producto.');return}
  if(!window.confirm(`¿Agregar ${items.length} productos revisados al catálogo de este restaurante?`))return;
  setBusy(true);try{const result=await request(`/gestion/restaurantes/${restaurant}/carta/publicar`,{token,method:'POST',body:JSON.stringify({items:parsed})});setItems([]);setRevision(n=>n+1);setMessage(`Se publicaron ${result.created} productos en el catálogo.`)}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 return <section><div className="section-title"><div><h2>Importar carta</h2><p>PDF de hasta 5 MB y 10 páginas. La lectura es una propuesta; comprueba precios y nombres antes de publicar.</p></div></div>
 <form onSubmit={extract}><label>Archivo PDF <input type="file" accept="application/pdf,.pdf" required onChange={e=>setFile(e.target.files[0]||null)}/></label> <button className="secondary" disabled={busy}>{busy?'Procesando…':'Leer carta'}</button></form>
 {error&&<div className="alert" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}
 <p><button className="secondary" type="button" disabled={busy||items.length>=100} onClick={()=>setItems(old=>[...old,{name:'',category:'General',price:'',description:''}])}>Añadir producto manualmente</button></p>
 {items.length>0&&<><p>Se agregarán al catálogo actual. Elimina las propuestas que no correspondan.</p><div className="menu-import-list">{items.map((item,i)=><div className="order" key={i}><label>Nombre<input value={item.name} maxLength={160} onChange={e=>edit(i,'name',e.target.value)}/></label><label>Categoría<input value={item.category} maxLength={100} onChange={e=>edit(i,'category',e.target.value)}/></label><label>Precio en pesos<input type="number" min="0" max="1000000000" step="1" value={item.price} onChange={e=>edit(i,'price',e.target.value)}/></label><label>Descripción<input value={item.description} maxLength={1000} onChange={e=>edit(i,'description',e.target.value)}/></label><button className="secondary" type="button" onClick={()=>setItems(old=>old.filter((_,n)=>n!==i))}>Quitar</button></div>)}</div><button className="primary" disabled={busy} onClick={publish}>Publicar productos revisados</button></>}
 <Catalog restaurant={restaurant} token={token} revision={revision}/>
 </section>
}

function Catalog({restaurant,token,revision}) {
 const [items,setItems]=useState([]),[offset,setOffset]=useState(0),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;request(`/gestion/restaurantes/${restaurant}/carta?limit=100&offset=${offset}`,{token}).then(data=>{if(active){setItems(data.map(x=>({...x,description:x.description||'',available:!!x.available})));setError('')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[restaurant,token,offset,revision]);
 const edit=(id,field,value)=>setItems(old=>old.map(x=>x.id===id?{...x,[field]:value}:x));
 async function save(item){setError('');setMessage('');const price=Number(item.price);if(!item.name.trim()||!item.category.trim()||String(item.price).trim()===''||!Number.isSafeInteger(price)||price<0||price>1000000000){setError('Revisa nombre, categoría y precio.');return}setBusy(true);try{await request(`/gestion/restaurantes/${restaurant}/carta/${item.id}`,{token,method:'PUT',body:JSON.stringify({name:item.name,description:item.description,category:item.category,price,available:item.available})});setMessage(`Producto ${item.id} actualizado.`)}catch(e){setError(e.message)}finally{setBusy(false)}}
 return <div><h2>Productos publicados</h2><p>Modifica sus datos o marca productos como no disponibles. Los pedidos anteriores conservan sus precios.</p>{error&&<div className="alert" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}<div className="menu-import-list">{items.map(item=><div className="order" key={item.id}><label>Nombre<input maxLength={160} value={item.name} onChange={e=>edit(item.id,'name',e.target.value)}/></label><label>Categoría<input maxLength={100} value={item.category} onChange={e=>edit(item.id,'category',e.target.value)}/></label><label>Precio en pesos<input type="number" min="0" max="1000000000" step="1" value={item.price} onChange={e=>edit(item.id,'price',e.target.value)}/></label><label>Descripción<input maxLength={1000} value={item.description} onChange={e=>edit(item.id,'description',e.target.value)}/></label><label><input type="checkbox" checked={item.available} onChange={e=>edit(item.id,'available',e.target.checked)}/> Disponible</label><button className="secondary" disabled={busy} onClick={()=>save(item)}>Guardar</button></div>)}</div><button className="secondary" disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-100))}>Anterior</button> <button className="secondary" disabled={items.length<100} onClick={()=>setOffset(x=>x+100)}>Siguiente</button></div>
}
