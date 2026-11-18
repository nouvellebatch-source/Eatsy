import test from 'node:test';
import assert from 'node:assert/strict';
import {receiptText,ordersCsv} from './operations.js';

test('comprobante calcula adicionales por cada producto y conserva el total real',()=>{
 const order={id:1,items:[{product_name:'Pizza',quantity:2,unit_price:10000,additions:[{product_name:'Queso',quantity:1,unit_price:2000}]}],total:23000,discount_amount:1000,payment_method:'cash',payment_status:'pending'};
 const receipt=receiptText(order,'Restaurante');
 assert.match(receipt,/24\.000/);assert.match(receipt,/23\.000/);assert.match(receipt,/pendiente/);assert.match(receipt,/no es factura electrónica/);
});
test('CSV neutraliza fórmulas y escapa comillas',()=>{
 const csv=ordersCsv([{id:5,table_number:'=1+1',status:'ok',payment_status:'pending',total:5000,currency:'COP'}]);
 assert.match(csv,/"'=1\+1"/);
});
