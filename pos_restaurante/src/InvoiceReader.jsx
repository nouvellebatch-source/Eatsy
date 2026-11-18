import React,{useState} from 'react';
import {request} from './api';

export function InvoiceReader({restaurant,token}) {
 const [file,setFile]=useState(null),[text,setText]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function read(e){e.preventDefault();if(!file)return;setText('');setError('');setBusy(true);try{
  const result=await request(`/gestion/restaurantes/${restaurant}/facturas/leer?proveedor=local`,{token,method:'POST',body:file,timeoutMs:100000,headers:{'Content-Type':'application/pdf'}});setText(result.text||'');if(!result.text)setError('No se encontró texto en el documento.');
 }catch(err){setError(err.message)}finally{setBusy(false)}}
 return <section><h2>Leer factura o comprobante</h2><p>Consulta el texto de un PDF de hasta 5 MB y 10 páginas. La lectura no registra pagos, gastos ni adjunta el documento a un pedido.</p>
 <form onSubmit={read}><label>Archivo PDF <input type="file" accept="application/pdf,.pdf" required onChange={e=>setFile(e.target.files[0]||null)}/></label> <button className="secondary" disabled={busy}>{busy?'Leyendo…':'Leer documento'}</button></form>
 {error&&<div className="alert" role="alert">{error}</div>}{text&&<label>Texto reconocido: revisa y corrige los datos antes de usarlos<textarea style={{display:'block',width:'100%',minHeight:350,marginTop:12}} value={text} onChange={e=>setText(e.target.value)}/></label>}</section>
}
