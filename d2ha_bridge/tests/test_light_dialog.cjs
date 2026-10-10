// Offline regression: HTTP-style crypto API, synthetic DOM, no network/device I/O.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {randomFillSync}=require('node:crypto');
const app=fs.readFileSync(path.join(__dirname,'../dovit_bridge/web/app.js'),'utf8');
const source=app.slice(app.indexOf('function lightRequestId'),app.indexOf('function openDraft'));
function fixture(crypto,brokenDialog=false){
 const elements=[],requests=[],gap={};
 const document={activeElement:null,body:{append(){}},querySelectorAll:()=>elements.filter(el=>el.dataset.controlKind&&el.isConnected)};
 let gate=null;
 const context=vm.createContext({crypto,Uint8Array,AbortSignal:{timeout:()=>null},
  data:{light_control:'simulation',draft_token:'test'},apiOnline:true,$:()=>gap,
  setText:(element,text)=>{element.text=text;},
  node:(tag,text)=>{const el={tag,text,dataset:{},children:[],attributes:{},isConnected:true,
   setAttribute(name,value){this.attributes[name]=value;},
   addEventListener(event,callback){(this.listeners??={})[event]??=[];this.listeners[event].push(callback);},
   focus(){assert.ok(this.isConnected,'Never focus a disconnected element');document.activeElement=this;},
   append(...children){this.children.push(...children);},
   remove(){this.removed=true;this.isConnected=false;for(const child of this.children)child.remove();},
   showModal(){if(brokenDialog)throw Error('unsupported');this.open=true;},
   close(){this.open=false;for(const callback of this.listeners?.close||[])callback();}};
   elements.push(el);return el;},
  document,
  fetch:async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});if(gate)await gate;return {ok:true,json:async()=>({command:{status:'observed'}})};}
 });
 vm.runInContext(source,context);
 return {context,elements,requests,gap,document,setGate:value=>{gate=value;},run:code=>vm.runInContext(code,context)};
}
(async()=>{
 const test=fixture({getRandomValues:bytes=>randomFillSync(bytes)}); // randomUUID absent on HTTP
 const ids=new Set();
 for(let i=0;i<1000;i++){const id=test.run('lightRequestId()');assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);ids.add(id);}
 assert.equal(ids.size,1000);
 test.run("confirmLight({name:'Office',endpoints:[[19,0]]},'ON')");
 assert.equal(test.elements.find(el=>el.tag==='dialog').open,true);
 assert.equal(test.requests.length,0,'Opening the dialog must not send');
 const technical=test.elements.find(el=>el.tag==='details');
 assert.ok(technical);
 assert.ok(!technical.open,'Command diagnostics start collapsed');
 assert.ok(technical.children.some(el=>el.text.includes('ID 19 / ST 0 / ON / 1.0')),'Raw command diagnostics are retained');
 technical.open=true;
 assert.equal(test.requests.length,0,'Opening technical details sends no command');
 const send=test.elements.find(el=>el.text==='light_confirm');await send.onclick();
 assert.equal(send.disabled,true);
 assert.equal(test.requests[0].body.action,'ON');assert.equal(test.requests[0].body.confirm,true);
 assert.equal(test.requests[0].url,'api/lights/command');
 const key=test.requests[0].body.request_id;
 await send.onclick();assert.equal(test.requests.length,1,'Repeated invocation cannot submit twice');
 assert.equal(test.requests[0].body.request_id,key);
 const result=test.elements.find(el=>el.dataset.lightRequest);test.context.result=result;
 assert.equal(result.commandMode,'simulation','Dialog captures its consent mode');
 assert.equal(result.text,'simulation_observed','Synthetic observation is not a real device status');
 test.run("data.light_control='live';setTrackedCommandStatus(result,'light_transmitted')");
 assert.equal(result.text,'simulation_transmitted','Feedback uses captured mode, not current mode');
 for(const status of ['requested','observed','failed','timeout','uncertain']){
  test.run(`setTrackedCommandStatus(result,'light_${status}')`);
  assert.equal(result.text,'simulation_'+status);
 }
 test.run("result.commandMode='live'");
 test.run("setTrackedCommandStatus(result,'light_transmitted')");
 assert.equal(result.text,'light_transmitted','Sending alone must not claim an observed device state');
 test.run("setTrackedCommandStatus(result,'light_observed')");
 assert.equal(result.text,'light_observed','Matching observation is a distinct status');
 test.run("setTrackedCommandStatus(result,'light_transmitted');data.draft_token='restarted';setTrackedCommandStatus(result,'')");
 assert.equal(result.text,'control_tracking_lost');
 test.run("setTrackedCommandStatus(result,'light_observed')");assert.equal(result.text,'control_tracking_lost','Late response from old session is ignored');
 test.run("data.draft_token='test';setTrackedCommandStatus(result,'light_observed');data.draft_token='another';setTrackedCommandStatus(result,'')");
 assert.equal(result.text,'light_observed','An already observed result remains historical evidence');
 test.run("data.draft_token='test'");
 test.context.send=send;
 test.run('apiOnline=false;updateControlButton(send)');assert.equal(send.disabled,true);
 test.run('apiOnline=true;updateControlButton(send)');assert.equal(send.disabled,true,'Submitted button stays disabled on reconnect');

 const offline=fixture({getRandomValues:bytes=>randomFillSync(bytes)});
 offline.run("data.light_control='live';data.connected=true;var dialog=openLightDialog({name:'Office',endpoints:[[19,0]]},'OFF')");
 const confirm=offline.elements.find(el=>el.text==='light_confirm');offline.context.confirm=confirm;
 assert.equal(confirm.disabled,false);
 offline.run('data.connected=false;refreshControlButtons()');
 assert.equal(confirm.disabled,true);assert.equal(confirm.controlNotice.text,'control_dovit_offline');
 await confirm.onclick();assert.equal(offline.requests.length,0);
 offline.run('data.connected=true;updateControlButton(confirm)');assert.equal(confirm.disabled,false);
 offline.run("data.draft_token='new-runtime';updateControlButton(confirm)");
 assert.equal(confirm.disabled,true);assert.equal(confirm.controlNotice.text,'control_dialog_stale');
 await confirm.onclick();assert.equal(offline.requests.length,0);

 const simulation=fixture({getRandomValues:bytes=>randomFillSync(bytes)});
 simulation.run("var dialog=openLightDialog({name:'Office',endpoints:[[19,0]]},'ON')");
 const simSend=simulation.elements.find(el=>el.text==='light_confirm');simulation.context.simSend=simSend;
 simulation.run('apiOnline=false;updateControlButton(simSend)');assert.equal(simSend.disabled,true);
 assert.equal(simSend.controlNotice.text,'control_api_offline');
 await simSend.onclick();assert.equal(simulation.requests.length,0);
 simulation.run('apiOnline=true;updateControlButton(simSend)');assert.equal(simSend.disabled,false);
 simulation.run("data.light_control='live';data.connected=true;updateControlButton(simSend)");
 assert.equal(simSend.disabled,true,'Simulation consent cannot silently become a live command');
 await simSend.onclick();assert.equal(simulation.requests.length,0);
 for(const crypto of [undefined,{}, {getRandomValues(){throw Error('unavailable');}}]){
  const failure=fixture(crypto);failure.run("confirmLight({name:'Office',endpoints:[[19,0]]},'OFF')");
  assert.equal(failure.gap.text,'light_dialog_error');assert.equal(failure.requests.length,0);
 }
 const broken=fixture({getRandomValues:bytes=>randomFillSync(bytes)},true);
 broken.run("confirmLight({name:'Office',endpoints:[[19,0]]},'OFF')");
 assert.equal(broken.elements.find(el=>el.tag==='dialog').removed,true);
 assert.equal(broken.gap.text,'light_dialog_error');assert.equal(broken.requests.length,0);
 const labelled=fixture({getRandomValues:bytes=>randomFillSync(bytes)});
 for(const action of ['ON','OFF'])labelled.run(`openLightDialog({name:'Office',endpoints:[[19,0]]},'${action}')`);
 const dialogs=labelled.elements.filter(el=>el.tag==='dialog');
 for(const dialog of dialogs){
  const descendants=el=>el.children.flatMap(child=>[child,...descendants(child)]);
  for(const attribute of ['aria-labelledby','aria-describedby']){
   assert.ok(dialog.attributes[attribute],attribute+' must be set');
   for(const id of dialog.attributes[attribute].split(/\s+/))assert.ok(descendants(dialog).some(el=>el.id===id),'Accessible reference resolves within its dialog');
  }
 }
 assert.notEqual(dialogs[0].attributes['aria-labelledby'],dialogs[1].attributes['aria-labelledby'],'Concurrent test titles are unique');
 assert.notEqual(dialogs[0].attributes['aria-describedby'],dialogs[1].attributes['aria-describedby'],'Concurrent warning IDs are unique');
 for(const fail of [false,true])for(const focusCase of ['primary','body','other','not-primary','closed']){
  const f=fixture({getRandomValues:bytes=>randomFillSync(bytes)});
  f.run("openLightDialog({name:'Office',endpoints:[[19,0]]},'ON')");
  const dialog=f.elements.find(el=>el.tag==='dialog'),primary=f.elements.find(el=>el.text==='light_confirm');
  const close=f.elements.find(el=>el.tag==='button'&&el!==primary);
  const other={isConnected:true};
  f.document.activeElement=focusCase==='not-primary'?other:primary;
  let resolve,reject;f.setGate(new Promise((yes,no)=>{resolve=yes;reject=no;}));
  const sending=primary.onclick();
  if(focusCase==='body')f.document.activeElement=f.document.body;
  if(focusCase==='other')f.document.activeElement=other;
  if(focusCase==='closed'){dialog.close();f.document.activeElement=other;}
  if(fail)reject(Error('Failed to fetch'));else resolve();
  await sending;
  assert.equal(f.document.activeElement,['primary','body'].includes(focusCase)?close:other,`Command completion focus: ${fail}/${focusCase}`);
  assert.equal(f.requests.length,1);
 }
 console.log('Light dialog tests passed: HTTP crypto, UUID v4, confirmation, stable request ID, safe failures. No network.');
})().catch(error=>{console.error(error);process.exitCode=1;});
