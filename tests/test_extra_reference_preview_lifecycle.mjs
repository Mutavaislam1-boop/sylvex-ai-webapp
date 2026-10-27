import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const start=source.indexOf('async function onQuickImageExtraFile(');
const end=source.indexOf('async function onQuickImageDetailFile(',start);

function harness(upload){
  const classes=new Set(),button={style:{},classList:{add:v=>classes.add(v),remove:v=>classes.delete(v)}};
  let blobCreates=0;
  const state={extraUploads:{}},messages=[];
  const ctx=vm.createContext({quickImageDetailState:state,document:{querySelector:()=>button},
    uploadProStudioMediaFile:upload,toast:message=>messages.push(message),
    URL:{createObjectURL:()=>{++blobCreates;return 'blob:unreleased';}}});
  vm.runInContext(source.slice(start,end),ctx);
  return {ctx,state,button,classes,messages,blobCreates:()=>blobCreates};
}

test('repeated extra-reference replacements reuse confirmed storage URLs without leaking blobs',async()=>{
  let calls=0;
  const h=harness(async()=>`https://storage.test/generated/ref-${++calls}.png?signature=dummy`);
  for(let i=0;i<10;i++)await h.ctx.onQuickImageExtraFile({target:{files:[{name:'fixture.png'}]}},'reference');
  assert.equal(calls,10);
  assert.equal(h.blobCreates(),0);
  assert.equal(h.state.extraUploads.reference,'https://storage.test/generated/ref-10.png?signature=dummy');
  assert.equal(h.button.style.backgroundImage,`url("${h.state.extraUploads.reference}")`);
  assert.equal(h.classes.has('uploading'),false);
});

test('a failed replacement keeps the previously confirmed reference and preview',async()=>{
  let fail=false;
  const h=harness(async()=>{if(fail)throw new Error('Could not upload');return 'https://storage.test/generated/good.png';});
  const event={target:{files:[{name:'fixture.png'}]}};
  await h.ctx.onQuickImageExtraFile(event,'reference');
  const preview=h.button.style.backgroundImage;
  fail=true;await h.ctx.onQuickImageExtraFile(event,'reference');
  assert.equal(h.state.extraUploads.reference,'https://storage.test/generated/good.png');
  assert.equal(h.button.style.backgroundImage,preview);
  assert.equal(h.classes.has('uploading'),false);
  assert.deepEqual(h.messages,['Could not upload']);
});
