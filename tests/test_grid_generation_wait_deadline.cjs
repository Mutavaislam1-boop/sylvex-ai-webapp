// Real deployed polling function, virtual time and synthetic GET responses only.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const sourcePath=process.env.S707_SOURCE || [path.join(root,'webapp/js/cabinet.js'),path.join(root,'studio/js/website-studio.js')].find(p=>fs.existsSync(p));
assert(sourcePath,'Set S707_SOURCE to the current client JS');
const source=fs.readFileSync(sourcePath,'utf8');
const start=source.indexOf('  async function waitGridGeneration('),next=source.indexOf('\n  async function executeGridNodeRequest(',start);
assert(start>=0&&next>start,'Existing Grid polling function boundaries');
const code=source.slice(start,next);
function harness(responses,options={}) {
  let clock=0,calls=0;const urls=[],statuses=[];
  const context=vm.createContext({
    Date:{now:()=>clock},Error,Promise,encodeURIComponent,
    translateGenerationError:(_err,fallback)=>fallback,
    setTimeout:(resolve,ms)=>{clock+=options.slowTimer?Math.max(ms,60000):ms;queueMicrotask(resolve)},
    fetch:async(url,request)=>{
      urls.push({url,request});calls++;
      return responses(calls,clock);
    },
  });
  vm.runInContext(code,context);
  return {run:()=>context.waitGridGeneration('synthetic/job',status=>statuses.push(status)),
          calls:()=>calls,elapsed:()=>clock,urls,statuses};
}
const response=job=>({ok:true,json:async()=>({ok:true,...job})});
test('responsive pending job stops at existing45-minute client deadline',async()=>{
  let tooLong;const exceeded=new Promise(resolve=>tooLong=resolve);
  const h=harness((calls)=>{
    if(calls>46){tooLong({kind:'overdue'});return new Promise(()=>{})}
    return response({status:'processing'});
  },{slowTimer:true});
  const outcome=await Promise.race([h.run().then(()=>({kind:'completed'}),error=>({kind:error.terminalStatus,error})),exceeded]);
  assert.equal(outcome.kind,'unconfirmed','Grid kept polling past the existing45-minute client deadline');
  assert.equal(outcome.error.jobId,'synthetic/job');
  assert.match(outcome.error.message,/статус|задач/);
  assert(h.calls()<=46);
  assert(h.urls.every(x=>!x.request.method||x.request.method==='GET'));
});
test('queued processing and provider_processing retain the same job until completed',async()=>{
  const states=['queued','processing','provider_processing','completed'];
  const h=harness(calls=>response({status:states[calls-1],result:{type:'image',images:['synthetic']}}));
  const result=await h.run();assert.equal(result.job_id,'synthetic/job');
  assert.deepEqual(h.statuses,states);assert.equal(h.calls(),4);
});
test('explicit provider failure terminates polling',async()=>{
  const h=harness(()=>response({status:'failed',error:{error:'synthetic provider failure'}}));
  await assert.rejects(h.run(),e=>e.terminalStatus==='failed');assert.equal(h.calls(),1);
});
test('explicit cancellation remains terminal',async()=>{
  const h=harness(()=>response({status:'cancelled'}));
  await assert.rejects(h.run(),e=>e.terminalStatus==='cancelled');assert.equal(h.calls(),1);
});
test('transient network outage retries only GET and returns existing completed job',async()=>{
  const h=harness(calls=>{if(calls<3)throw Error('synthetic network outage');return response({status:'completed',result:{type:'video',video_url:'synthetic'}})});
  const result=await h.run();assert.equal(result.generation_id,'synthetic/job');assert.equal(h.calls(),3);
  assert(h.urls.every(x=>x.url==='/api/public/prostudio/job/synthetic%2Fjob'&&!x.request.method));
});
test('persistent network outage already stops after bounded retries',async()=>{
  const h=harness(()=>{throw Error('synthetic network outage')});
  await assert.rejects(h.run(),/synthetic network outage/);assert.equal(h.calls(),81);
});
test('server error response followed by successful receipt does not resubmit generation',async()=>{
  const h=harness(calls=>calls===1?{ok:false,json:async()=>({ok:false})}:response({status:'completed',result:{type:'audio',audio_url:'synthetic'}}));
  const result=await h.run();assert.equal(result.job_id,'synthetic/job');assert.equal(h.calls(),2);
  assert(h.urls.every(x=>!x.request.method));
});
test('unconfirmed deadline preserves backend identity without cancel or retry POST',async()=>{
  let stop;const exceeded=new Promise(resolve=>stop=resolve);
  const h=harness(calls=>{if(calls>46){stop(null);return new Promise(()=>{})}return response({status:'provider_processing'})},{slowTimer:true});
  const error=await Promise.race([h.run().then(()=>null,e=>e),exceeded]);
  assert(error&&error.terminalStatus==='unconfirmed','Grid must leave an unresolved job unconfirmed');
  assert.equal(error.jobId,'synthetic/job');assert(h.urls.every(x=>!x.request.method));
});
function declaration(name) {
  const match=new RegExp('^  (?:async )?function '+name+'\\(','m').exec(source);
  assert(match,name+' exists');const rest=source.slice(match.index+match[0].length);
  const next=/^  (?:async )?function [a-zA-Z_$]/m.exec(rest);assert(next,name+' boundary');
  const text=source.slice(match.index,match.index+match[0].length+next.index);
  return text.slice(0,text.lastIndexOf('\n  }')+4);
}
function nodeContext(status) {
  const node={id:'n1',type:'image',settings:{},request_id:'stable-original-request',generation_id:'original-job',status};
  const state={projectId:'synthetic-project',nodes:[node],workflow:{}};
  const context=vm.createContext({Date,Promise,Map,JSON,studioGridNodeRuns:new Map(),studioGridJobsRestored:false,
    S:{user:{balance:100}},guestNeedsAccount:()=>false,loadStudioGridState:()=>state,
    resolveGridNodeInputs:()=>({}),validateGridNodeInputs:()=>({ok:true}),
    estimateGridNodeCost:async()=>5,ensureStudioGridProjectTitle:()=>{},saveStudioGridState:()=>{},
    renderStudioGrid:()=>{},toast:()=>{},translateGenerationError:e=>e.message});
  vm.runInContext(declaration('runGridNode')+'\n'+declaration('restoreStudioGridJobs'),context);
  return {node,context};
}
test('current node keeps request ID on unconfirmed wait; definitive failure still clears it',async()=>{
  for(const status of ['unconfirmed','failed']){
    const {node,context}=nodeContext('READY');
    const error=Object.assign(Error('synthetic status could not be confirmed'),{terminalStatus:status,jobId:'original-job'});
    context.executeGridNodeRequest=async()=>{throw error};
    await context.runGridNode('n1');
    assert.equal(node.generation_id,'original-job');
    assert.equal(node.request_id,status==='unconfirmed'?'stable-original-request':'');
  }
});
test('restored node keeps request ID on unconfirmed wait; definitive failure still clears it',async()=>{
  for(const status of ['unconfirmed','failed']){
    const {node,context}=nodeContext('RUNNING');
    const error=Object.assign(Error('synthetic status could not be confirmed'),{terminalStatus:status,jobId:'original-job'});
    context.waitGridGeneration=async()=>{throw error};
    context.restoreStudioGridJobs();await context.studioGridNodeRuns.get('n1');
    assert.equal(node.generation_id,'original-job');
    assert.equal(node.request_id,status==='unconfirmed'?'stable-original-request':'');
  }
});
