// Synthetic DOM and fetch only. No browser, server or network.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const web=path.join(__dirname,'../dovit_bridge/web');
const source=fs.readFileSync(path.join(web,'recovery.js'),'utf8');
const html=fs.readFileSync(path.join(web,'recovery.html'),'utf8');
class Element{
 constructor(){this.value='';this.children=[];this.dataset={};this.files=[];this.checked=false;this.disabled=false;this.hidden=true;this.isConnected=true;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
}
function fixture(overrides={}){
 const ids=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
 const translated=[...html.matchAll(/data-text="([^"]+)"/g)].map(m=>{const e=new Element();e.dataset.text=m[1];return e;});
 const calls=[];let applyFail=false,statusRestored=false,validationGate=null,applyGate=null;
 const document={activeElement:null,body:{},getElementById:id=>ids[id],createElement:()=>new Element(),documentElement:{},querySelectorAll:()=>translated};
 for(const element of Object.values(ids))element.focus=()=>{assert.notEqual(element.isConnected,false);document.activeElement=element;};
 const snapshot=()=>({recovery:true,token:'secret',current:{state:'invalid',revision:'initial'},backups:[{id:'opaque-id',name:'Backup',state:'valid'},{id:'cleanup',name:'Unsafe',state:'valid',contains_cleanup:true}],restored:statusRestored,...overrides});
 const context=vm.createContext({TextDecoder,Uint8Array,document,AbortSignal:{timeout:()=>null},
 fetch:async(url,options)=>{const body=options?.body?JSON.parse(options.body):null;calls.push({url,options,body});
 if(url.endsWith('/apply')){if(applyGate)await applyGate;if(applyFail)throw Error('lost');return {ok:true,json:async()=>({restored:true,restart_required:true})};}
 if(url.endsWith('/validate')){if(validationGate)await validationGate;return {ok:true,json:async()=>({validation_id:'validated',revision:'validated-revision',summary:{counts:{lights:1},names:[{category:'lights',name:'<script>private</script>'}],has_alarms:true,empty:true}})};}
 return {ok:true,json:async()=>snapshot()};}});
 vm.runInContext(source,context);
 return {ids,calls,context,document,run:code=>vm.runInContext(code,context),failApply(restored){applyFail=true;statusRestored=restored;},gate(value){validationGate=value;},gateApply(value){applyGate=value;}};
}
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
(async()=>{
 const f=fixture();await settle();const e=f.ids;
 assert.equal(f.calls.length,1);assert.equal(e.validate.disabled,false);assert.equal(e.apply.disabled,true);
 e.document.value='{"lights":{}}';e.document.oninput();await e.validate.onclick();
 assert.equal(f.calls.at(-1).body.document,e.document.value);
 assert.equal(f.calls.at(-1).options.headers['X-Dovit-Token'],'secret');
 assert.equal(e.review.hidden,false);e.confirm.checked=true;e.confirm.onchange();assert.equal(e.apply.disabled,true);
 assert.ok(e.summary.children[0].textContent.includes('Lichter: 1'));
 e['confirm-alarm'].checked=true;e['confirm-empty'].checked=true;e['confirm-empty'].onchange();assert.equal(e.apply.disabled,false);
 e.language.value='fr';e.language.onchange();assert.equal(e.document.value,'{"lights":{}}');assert.equal(e.confirm.checked,true);
 assert.ok(e.summary.children[0].textContent.includes('Éclairages: 1'));
 assert.ok(e.summary.children[2].children[0].textContent.startsWith('Éclairages:'));
 await e.apply.onclick();const sent=f.calls.find(c=>c.url.endsWith('/apply'));
 assert.deepEqual(sent.body,{revision:'validated-revision',validation_id:'validated',confirm:true,confirm_alarm:true,confirm_empty:true});
 assert.equal(e.restart.hidden,false);assert.equal(e.document.disabled,true);
 await e.apply.onclick();assert.equal(f.calls.filter(c=>c.url.endsWith('/apply')).length,1);
 assert.ok(f.calls.every(c=>/^api\/recovery(?:\/(validate|apply))?$/.test(c.url)));
 const b=fixture();await settle();b.ids.backup.value='opaque-id';b.ids.backup.onchange();await b.ids.validate.onclick();
 assert.equal(b.ids.backup.children.find(el=>el.value==='cleanup').disabled,true);
 assert.equal(b.calls.at(-1).body.backup,'opaque-id');assert.equal(b.ids.document.disabled,true);
 b.ids.backup.value='../typed-path';b.ids.backup.onchange();const count=b.calls.length;await b.ids.validate.onclick();assert.equal(b.calls.length,count);
 b.ids.backup.value='cleanup';b.ids.backup.onchange();await b.ids.validate.onclick();assert.equal(b.calls.length,count);
 const r=fixture();await settle();let read=0;
 for(const file of [{name:'bad.txt',size:1},{name:'huge.json',size:256*1024+1}]){
 r.ids.file.files=[{...file,arrayBuffer(){read++;return Promise.resolve(new ArrayBuffer(0));}}];await r.ids.file.onchange();}
 assert.equal(read,0,'Reject extension/size before reading');
 let resolve;r.ids.file.files=[{name:'good.json',size:2,arrayBuffer:()=>new Promise(yes=>resolve=yes)}];
 const pending=r.ids.file.onchange();assert.equal(r.ids.validate.disabled,true);
 r.ids.document.value='new draft';r.ids.document.oninput();resolve(Uint8Array.from([123,125]).buffer);await pending;
 assert.equal(r.ids.document.value,'new draft','Stale file read cannot overwrite pasted JSON');
 assert.equal(r.run('uploadBytes'),null);
 const bytes=Uint8Array.from([239,187,191,...Buffer.from('{\r\n"lights": {}\r\n}\r\n','utf8')]);
 r.ids.file.files=[{name:'original.json',size:bytes.length,arrayBuffer:async()=>bytes.buffer}];await r.ids.file.onchange();
 assert.equal(r.ids.document.value.charCodeAt(0),0xfeff,'Strict preview keeps BOM');
 // Model textarea newline normalization without dispatching an edit event.
 r.ids.document.value=r.ids.document.value.replace(/\r\n/g,'\n');
 await r.ids.validate.onclick();assert.deepEqual(r.calls.at(-1).body.file_bytes,Array.from(bytes));
 assert.equal(Object.hasOwn(r.calls.at(-1).body,'document'),false);
 await r.ids.validate.onclick();assert.deepEqual(r.calls.at(-1).body.file_bytes,Array.from(bytes),'Revalidation preserves original upload');
 r.ids.document.oninput();await r.ids.validate.onclick();assert.equal(Object.hasOwn(r.calls.at(-1).body,'file_bytes'),false);assert.equal(r.calls.at(-1).body.document,r.ids.document.value);
 r.ids.file.files=[{name:'bad.json',size:2,arrayBuffer:async()=>Uint8Array.from([195,40]).buffer}];await r.ids.file.onchange();
 assert.equal(r.run('uploadBytes'),null);assert.equal(r.run('statusKey'),'recovery_read_error','Malformed UTF-8 is rejected');
 r.ids.file.files=[{name:'original.json',size:bytes.length,arrayBuffer:async()=>bytes.buffer}];await r.ids.file.onchange();
 r.ids.backup.value='opaque-id';r.ids.backup.onchange();assert.equal(r.run('uploadBytes'),null,'Backup source clears upload capture');
 r.ids.backup.value='';r.ids.backup.onchange();
 await r.ids.validate.onclick();r.ids.document.oninput();assert.equal(r.ids.review.hidden,true);assert.equal(r.ids.confirm.checked,false);
 const stale=fixture();await settle();let finish;stale.gate(new Promise(yes=>finish=yes));
 const checking=stale.ids.validate.onclick();stale.ids.document.value='changed';stale.ids.document.oninput();finish();await checking;assert.equal(stale.ids.review.hidden,true);
 for(const restored of [false,true]){
 const u=fixture();await settle();await u.ids.validate.onclick();for(const id of ['confirm','confirm-alarm','confirm-empty'])u.ids[id].checked=true;u.ids.confirm.onchange();u.failApply(restored);
 await u.ids.apply.onclick();assert.equal(u.ids.apply.disabled,true);assert.equal(u.ids.document.disabled,true);assert.equal(u.ids.restart.hidden,!restored);
 assert.equal(u.calls.at(-1).url,'api/recovery');await u.ids.apply.onclick();assert.equal(u.calls.filter(c=>c.url.endsWith('/apply')).length,1);
 }
 assert.equal(new Set([...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1])).size,[...html.matchAll(/id="([^"]+)"/g)].length);
 assert.ok(!html.includes('app.js')&&!html.includes('i18n.js'));
 for(const action of ['validate','apply'])for(const fail of [false,true])for(const focusCase of ['primary','body','other','not-primary','disconnected']){
  const a=fixture();await settle();
  if(action==='apply'){await a.ids.validate.onclick();for(const id of ['confirm','confirm-alarm','confirm-empty'])a.ids[id].checked=true;a.ids.confirm.onchange();}
  const primary=a.ids[action],other=new Element();a.document.activeElement=focusCase==='not-primary'?other:primary;
  let finish,reject;const gate=new Promise((yes,no)=>{finish=yes;reject=no;});
  if(action==='apply')a.gateApply(gate);else a.gate(gate);
  const operation=primary.onclick();
  if(focusCase==='body')a.document.activeElement=a.document.body;
  if(focusCase==='other')a.document.activeElement=other;
  if(focusCase==='disconnected'){primary.isConnected=false;a.document.activeElement=other;}
  if(fail)reject(Error('recovery_invalid'));else finish();await operation;
  const expected=['primary','body'].includes(focusCase)?a.ids[fail?'status':action==='apply'?'restart-title':'review-title']:other;
  assert.equal(a.document.activeElement,expected,`Guarded recovery focus: ${action}/${fail}/${focusCase}`);
  if(action==='apply'){assert.equal(a.ids.apply.disabled,true);await a.ids.apply.onclick();assert.equal(a.calls.filter(c=>c.url.endsWith('/apply')).length,1);}
 }
 const reconciled=fixture();await settle();await reconciled.ids.validate.onclick();for(const id of ['confirm','confirm-alarm','confirm-empty'])reconciled.ids[id].checked=true;reconciled.ids.confirm.onchange();reconciled.document.activeElement=reconciled.ids.apply;reconciled.failApply(true);await reconciled.ids.apply.onclick();
 assert.equal(reconciled.document.activeElement,reconciled.ids['restart-title'],'GET-confirmed recovery focuses completion, not uncertainty');
 for(const state of ['missing','invalid','unreadable','oversized']){
  const s=fixture({current:{state,revision:['unreadable','oversized'].includes(state)?null:'revision'}});await settle();
  for(const locale of ['de','fr']){s.ids.language.value=locale;s.ids.language.onchange();assert.equal(s.ids['current-state'].textContent,s.run(`t('current_${state}')`));}
  if(['unreadable','oversized'].includes(state)){assert.equal(s.ids.validate.disabled,true);assert.equal(s.ids.file.disabled,true);assert.equal(s.ids.document.disabled,true);assert.equal(s.ids.backup.disabled,true);await s.ids.validate.onclick();assert.equal(s.calls.length,1);}
 }
 const pendingEdit=fixture({pending:true});await settle();assert.equal(pendingEdit.ids.validate.disabled,true);
 const firstInstall=fixture({current:{state:'missing',revision:'missing'}});await settle();
 assert.equal(firstInstall.ids['new-install'].hidden,false);
 firstInstall.ids['new-install'].onclick();
 assert.deepEqual(Object.keys(JSON.parse(firstInstall.ids.document.value)),['lights','shutters','thermostats','motions','contacts','alarms']);
 assert.equal(firstInstall.calls.length,1,'Preparing a new-install draft sends no mutation or command');
 assert.equal(firstInstall.ids.apply.disabled,true,'New install still requires validation and explicit empty consent');
 assert.equal(f.ids['new-install'].hidden,true,'Existing invalid file is never replaced by a new-install shortcut');
 for(const locale of ['de','fr']){pendingEdit.ids.language.value=locale;pendingEdit.ids.language.onchange();assert.equal(pendingEdit.ids.status.textContent,pendingEdit.run("t('recovery_pending')"));assert.ok(pendingEdit.run("t('inactive')").includes('MQTT'));}
 for(const language of ['de','fr']){
 f.run(`language='${language}'`);
 for(const key of ['source','invalid','size','cleanup','restart','unreadable','stale','pending','confirm','alarm_confirm','empty_confirm','storage','only','disabled','unknown']){
  assert.equal(f.run(`Object.hasOwn(catalog,'recovery_${key}')`),true);
  assert.ok(f.run(`t('recovery_${key}')`).length>0);
 }
 assert.equal(f.run("t('recovery_unexpected_server_error')"),f.run("t('recovery_error')"),'Unknown errors use translated generic fallback');
 }
 console.log('Recovery UI passed: consent, captured revision, opaque backups, file limits/races, DE/FR draft preservation, uncertainty lock. Offline only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
