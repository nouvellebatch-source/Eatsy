export const money = value => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(value ?? 0);
export function receiptText(order, restaurant) {
  const lines = (order.items || []).map(item => {
    const extras = (item.additions || []).map(a => `    + ${a.quantity} × ${a.product_name} por unidad: ${money(a.unit_price)}`).join('\n');
    return `${item.quantity} × ${item.product_name}  ${money(item.unit_price)} c/u${extras ? '\n'+extras : ''}`;
  });
  const subtotal = (order.items || []).reduce((sum,item) => sum + item.quantity * (item.unit_price + (item.additions || []).reduce((s,a) => s+a.quantity*a.unit_price,0)),0);
  const discount = order.discount_amount || 0;
  const adjustment = order.total - subtotal + discount;
  return [restaurant, `COMPROBANTE DE COMPRA #${order.id}`, order.created_at ? `Fecha: ${order.created_at}` : '', ...lines, `Subtotal: ${money(subtotal)}`, `Descuento: -${money(discount)}`, ...(adjustment ? [`Otros cargos o ajustes: ${money(adjustment)}`] : []), `TOTAL: ${money(order.total)}`, `Pago: ${order.payment_method === 'cash' ? 'efectivo' : order.payment_method} · ${order.payment_status === 'pending' ? 'pendiente' : order.payment_status}`, 'Documento informativo; no es factura electrónica.', 'El estado pendiente no representa un pago recibido.'].filter(Boolean).join('\n');
}
export function ordersCsv(orders) {
  const safe = v => { const s=String(v ?? ''); return '"'+(/^[\s]*[=+\-@\t\r]/.test(s) ? "'"+s : s).replaceAll('"','""')+'"'; };
  return '\ufeff'+[['Pedido','Mesa','Estado','Pago','Total','Moneda','Fecha'],...orders.map(o=>[o.id,o.table_number,o.status,o.payment_status,o.total,o.currency,o.created_at])].map(row=>row.map(safe).join(',')).join('\r\n');
}
export function printReceipt(order, restaurant) {
  const w=window.open('','_blank');
  if(!w) throw new Error('Permite ventanas emergentes para imprimir el comprobante.');
  w.document.title=`Comprobante ${order.id}`;
  const pre=w.document.createElement('pre'); pre.style.cssText='white-space:pre-wrap;font:16px/1.6 sans-serif'; pre.textContent=receiptText(order,restaurant); w.document.body.appendChild(pre); w.focus(); w.print();
}
export function downloadOrders(orders) {
  const url=URL.createObjectURL(new Blob([ordersCsv(orders)],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a'); a.href=url; a.download='pedidos-eatsy.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
