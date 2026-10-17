import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const css=readFileSync(new URL('../webapp/css/cabinet.css',import.meta.url),'utf8');
const controller=source.slice(source.indexOf('let openHistoryActionMenu='),source.indexOf("const EDIT_SESSION_GUEST_OWNER="));

function menuHarness(){
  const listeners={},timers=[],menus=[];
  const document={
    addEventListener(type,handler){(listeners[type]||(listeners[type]=[])).push(handler)},
    querySelectorAll(){return menus.filter(menu=>menu.open)},
  };
  const context=vm.createContext({document,clearTimeout(){},setTimeout(handler,delay){timers.push({handler,delay});return timers.length}});
  vm.runInContext(controller+'\nthis.api={installHistoryActionMenuController,closeHistoryActionMenu};',context);
  const makeMenu=()=>{
    const row={contains(target){return target===row||target===menu||target===summary||target===button}};
    const menu={open:false,parentElement:row,closest(){return row},removeAttribute(name){if(name==='open')this.open=false}};
    const summary={parentElement:menu,closest(selector){if(selector==='.history-item-menu>summary')return this;if(selector==='.history-item-menu')return menu;return null}};
    const button={closest(selector){if(selector==='button')return this;if(selector==='.history-item-menu')return menu;return null}};
    menus.push(menu);return{menu,row,summary,button};
  };
  const fire=(type,target,extra={})=>(listeners[type]||[]).forEach(handler=>handler({target,preventDefault(){},...extra}));
  context.api.installHistoryActionMenuController();
  return{makeMenu,fire,timers};
}

test('one shared history menu controller toggles, replaces and closes menus',()=>{
  const h=menuHarness(),first=h.makeMenu(),second=h.makeMenu(),outside={closest:()=>null};
  h.fire('click',first.summary);assert.equal(first.menu.open,true);
  h.fire('click',second.summary);assert.equal(first.menu.open,false);assert.equal(second.menu.open,true);
  h.fire('click',second.summary);assert.equal(second.menu.open,false);
  h.fire('click',first.summary);h.fire('pointerdown',outside);assert.equal(first.menu.open,false);
  h.fire('click',first.summary);h.fire('click',first.button);assert.equal(first.menu.open,false);
});

test('history menu schedules the requested inactivity close after pointer leaves its row',()=>{
  const h=menuHarness(),entry=h.makeMenu(),outside={};
  h.fire('click',entry.summary);
  h.fire('pointerout',entry.summary,{relatedTarget:outside});
  assert.equal(h.timers.at(-1).delay,1000);
  h.timers.at(-1).handler();assert.equal(entry.menu.open,false);
});

test('Pro Studio, Grid and Edit expose the same three history actions',()=>{
  for(const prefix of ['manageConversationHistory','data-grid-project-action','data-edit-session-action']){
    assert.match(source,new RegExp(prefix+'[\\s\\S]{0,1200}rename'));
    assert.match(source,new RegExp(prefix+'[\\s\\S]{0,1200}pin'));
    assert.match(source,new RegExp(prefix+'[\\s\\S]{0,1200}delete'));
  }
});

test('compact menu control is contextual on pointer devices',()=>{
  assert.match(css,/\.history-item-menu>summary\{[^}]*width:22px;height:22px[^}]*font-size:10px/);
  assert.match(css,/@media \(hover:hover\) and \(pointer:fine\)[\s\S]*?\.history-item-menu>summary\{opacity:0;pointer-events:none\}/);
  assert.match(css,/\.history-item-menu\[open\]>summary\{opacity:\.78;pointer-events:auto\}/);
});

test('pinned histories use a real pin icon and long-hover themed titles',()=>{
  assert.match(source,/function historyPinIcon\(\)/);
  assert.match(source,/data-history-title=/);
  assert.match(css,/\.history-pin\{[^}]*width:11px;height:11px/);
  assert.match(css,/\.history-title-tooltip\{[^}]*border-radius:9px[^}]*background:var\(--st-bg-2,var\(--sx-bg/);
});

test('latest mode navigation owns active state and stale Grid frames are ignored',()=>{
  assert.match(source,/let studioModeNavigationRevision=0,studioWorkspaceMode='studio',studioModeNavigationIntent=''/);
  assert.match(source,/function navigateStudioMode\(mode,e\)/);
  assert.match(source,/studioModeNavigationIntent=mode/);
  assert.match(source,/const publishNavigation=!options\.preserveStudioMode&&!studioModeNavigationIntent/);
  assert.match(source,/if\(revision!==studioModeNavigationRevision\|\|studioWorkspaceMode!=='grid'\|\|!studio\?\.classList\.contains\('grid-mode'\)\)return/);
  assert.doesNotMatch(source,/links\.forEach\(\(\{link,active\}\)=>link\.classList\.toggle\('is-active',active\)\)/);
});

test('website Edit is not also registered as a Mini App overlay history step',()=>{
  assert.match(source,/\['edit-workspace', \(\) => !isWebEmbed\(\)&&document\.body\.classList\.contains\('edit-workspace-open'\)/);
});
