import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const start=source.indexOf('  async function payStoreProduct(');
const end=source.indexOf('\n  }',start)+4;
const pay=source.slice(start,end);

test('Telegram rejects Crypto methods before fetching or opening any invoice', async()=>{
 for(const method of ['crypto','crypto_pay','paypal']){
  const messages=[];
  const context={S:{},guestNeedsAccount:()=>false,isBrowserApp:()=>false,STORE_METHODS:{stars:'telegram_stars'},
    STORE_ERRORS:{telegram_stars_only:'Stars only'},
    toast:m=>messages.push(m),fetch:()=>assert.fail('no provider request'),
    pendingStoreProduct:{product_id:'pack_500'},getTelegramId:()=>101};
  vm.createContext(context);vm.runInContext(pay+';this.run=payStoreProduct;',context);
  await context.run(method);
  assert.ok(messages.length);
 }
});

test('The retired adapter and provider links are absent from the served payment UI',()=>{
 assert.doesNotMatch(source,/payments\/crypto|pay\.crypt\.bot|t\.me\/CryptoBot|function openPaymentUrl/);
 assert.match(source,/const STORE_METHODS = \{ stars: 'telegram_stars' \}/);
 assert.match(source,/payments\/stripe\/checkout/);
 assert.match(source,/payments\/stripe\/portal/);
});
