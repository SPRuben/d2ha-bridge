// Offline DOM/transport stubs; never contacts HA or Dovit.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const web=path.join(__dirname,'../dovit_bridge/web');
const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
const tools=html.match(/<details id="json-tools">([\s\S]*?)<\/details>/)[1];
assert.ok(tools.includes('id="json-load"')&&tools.includes('id="json-format"'));
assert.ok(!tools.includes('id="json-check"')&&!tools.includes('id="json-save"'),'Primary actions stay outside tools');
const review=html.match(/<section id="json-review"[^>]* hidden>([\s\S]*?)<\/section>/)[1];
assert.ok(review.includes('id="json-save"')&&review.includes('id="json-confirm"'));
assert.ok(review.includes('<details id="json-details">'),'Technical payload is collapsed by default');
assert.ok(!review.includes('id="json-cancel"'),'Pending cancellation must remain accessible without validation');
const ids={};
function el(id){return ids[id]||(ids[id]={value:'',checked:false,hidden:false,disabled:false,dataset:{},
 children:[],handlers:{},append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
 setAttribute(key,value){this[key]=value;},removeAttribute(key){delete this[key];},
 addEventListener(key,handler){(this.handlers[key]??=[]).push(handler);},
 fire(key){for(const handler of this.handlers[key]||[])handler();},
 focus(){this.focused=true;document.activeElement=this;}});}
let snapshot={revision:'first',document:'{"lights":{}}',pending:false};
let requests=[],allowDiscard=true,resolveCheck=null,rejectCheck=null,delayCheck=false,identityChanged=false,failSave=false,saveFailurePending=false;
const listeners={};
const document={activeElement:null,body:{}};
const context=vm.createContext({document,$:el,t:key=>key,setText:(e,text)=>{e.textContent=text;},
 renderChangeReview:()=>true,
 window:{confirm:()=>allowDiscard,addEventListener:(name,handler)=>{listeners[name]=handler;}},editorStatus:async()=>{},
 editorRequest:async(action,body)=>{
  requests.push({action,body});
  if(action==='save'&&failSave){if(saveFailurePending)snapshot={...snapshot,pending:true};throw Error('save failed');}
  if(!action)return snapshot;
  if(action==='validate'){
   if(delayCheck)return await new Promise((resolve,reject)=>{resolveCheck=resolve;rejectCheck=reject;});
   return {draft:{changed:['lights:19'],removed:[]},identity_changed:identityChanged};
  }
  return {pending:action==='save'};
 }});
vm.runInContext(fs.readFileSync(path.join(web,'json-editor.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
(async()=>{
 await run('loadJson()');
 assert.equal(el('json-text').value,snapshot.document);
 assert.equal(el('json-check').disabled,false);
 assert.equal(el('json-save').disabled,true);
 assert.equal(el('json-review').hidden,true,'Review is absent until validation');
 assert.equal(el('json-format').disabled,true,'Formatting requires server validation');
 run("selectView('json')");assert.equal(el('graphic-panel').hidden,true);
 el('json-text').value='{"lights":{"19":{"name":"Test","statetype":0}}}';
 el('json-text').oninput();
 run("selectView('graphic');selectView('json')");
 assert.ok(el('json-text').value.includes('Test'),'Switching tabs preserves draft');
 allowDiscard=false;await run('loadJson()');assert.ok(el('json-text').value.includes('Test'));
 allowDiscard=true;
 await el('json-check').onclick();
 assert.equal(el('json-save').disabled,true,'Validation alone does not grant consent');
 el('json-confirm').checked=true;el('json-confirm').onchange();assert.equal(el('json-save').disabled,false);
 el('json-confirm').checked=false;el('json-confirm').onchange();assert.equal(el('json-save').disabled,true,'Revoking consent disables saving');
 assert.equal(el('json-review').hidden,false,'Successful validation reveals the next step');
 assert.equal(el('json-format').disabled,false);
 assert.equal(el('json-tools').open,false,'Tools close after successful validation');
 delete context.renderChangeReview;
 await el('json-check').onclick();assert.equal(el('json-status').textContent,'review_unavailable');
 assert.equal(el('json-review').hidden,true,'Missing readable report cannot grant JSON approval');
 el('json-confirm').checked=true;const missingReviewRequests=requests.length;await el('json-save').onclick();
 assert.equal(requests.length,missingReviewRequests,'Forced save without readable review is blocked');
 for(const helper of [()=>false,()=>undefined,()=>{throw Error('render failed');}]){
  context.renderChangeReview=helper;await el('json-check').onclick();
  assert.equal(run('jsonValidated'),null);assert.equal(el('json-save').disabled,true);
 }
 context.renderChangeReview=()=>true;await el('json-check').onclick();
 el('language').fire('change');assert.notEqual(run('jsonValidated'),null,'Language keeps validated text and consent model');
 context.renderChangeReview=()=>{throw Error('language render failed');};el('language').fire('change');
 assert.equal(run('jsonValidated'),null,'A language-render failure invalidates approval');
 assert.equal(el('json-status').textContent,'review_unavailable');
 context.renderChangeReview=()=>true;await el('json-check').onclick();
 el('json-format').onclick();
 assert.equal(el('json-review').hidden,true,'Formatting changes the draft and hides stale review');
 assert.equal(el('json-save').disabled,true,'Formatted text needs fresh validation');
 assert.equal(el('json-format').disabled,true);
 await el('json-check').onclick();
 assert.equal(el('json-review').hidden,false);
 const before=requests.length;await el('json-save').onclick();
 assert.equal(requests.length,before,'Save needs confirmation');
 el('json-confirm').checked=true;document.activeElement=el('json-save');await el('json-save').onclick();
 assert.equal(el('json-cancel').focused,true,'Keyboard focus returns to a visible action after staging');
 assert.equal(el('json-format').disabled,true);
 document.activeElement=null;
 const saved=requests.find(r=>r.action==='save');
 assert.equal(saved.body.operation,'replace_json');assert.equal(saved.body.revision,'first');assert.equal(saved.body.confirm,true);
 assert.equal(el('json-cancel').hidden,false);
 await el('json-cancel').onclick();
 assert.equal(el('json-save').disabled,true);
 assert.equal(run('jsonDirty'),true,'Cancelled saved JSON is unsaved again');
 const retained=el('json-text').value;
 allowDiscard=false;await run('loadJson()');allowDiscard=true;
 assert.equal(el('json-text').value,retained,'Reload respects discard refusal after cancellation');
 let prevented=false;listeners.beforeunload({preventDefault(){prevented=true;}});
 assert.equal(prevented,true,'Cancelled JSON warns before leaving');
 delayCheck=true;const pending=el('json-check').onclick();
 el('json-text').value='{}';el('json-text').oninput();
 resolveCheck({draft:{},identity_changed:false});await pending;
 assert.equal(el('json-save').disabled,true,'Old validation cannot validate new text');
 assert.equal(el('json-review').hidden,true,'Stale validation must not reveal review');
 assert.equal(el('json-summary').textContent,'','Old summaries are cleared on edits');
 assert.equal(el('json-details').open,false,'Old technical details collapse with invalidated review');
 delayCheck=false;identityChanged=true;
 await el('json-check').onclick();
 assert.equal(el('json-identity-label').hidden,false);
 el('json-confirm').checked=true;el('json-confirm').onchange();assert.equal(el('json-save').disabled,true,'Identity consent also required');const beforeIdentity=requests.length;
 await el('json-save').onclick();assert.equal(requests.length,beforeIdentity);
 el('json-identity').checked=true;el('json-identity').onchange();assert.equal(el('json-save').disabled,false);
 el('json-identity').checked=false;el('json-identity').onchange();assert.equal(el('json-save').disabled,true);
 el('json-identity').checked=true;el('json-identity').onchange();await el('json-save').onclick();
 assert.equal(requests.filter(r=>r.action==='save').at(-1).body.confirm_identity,true);
 // Exercise the real cross-panel status/cancel handlers with stubbed transport.
 const devices=fs.readFileSync(path.join(web,'devices.js'),'utf8');
 vm.runInContext(devices.slice(devices.indexOf('async function editorStatus()'),devices.indexOf('function managementButton')).replace(/editorStatus\(\);\s*$/,''),context);
 await run('editorStatus()');
 assert.equal(run('jsonPending'),false,'Graphical status clears JSON pending');
 assert.equal(run('jsonDirty'),true);
 assert.equal(el('json-check').disabled,false);
 el('json-text').value='{"local":"keep me"}';el('json-text').oninput();
 await el('json-check').onclick();
 snapshot={...snapshot,pending:true,document:'{"server":"do not load"}'};
 await run('editorStatus()');
 assert.equal(el('json-save').disabled,true,'Graphical staging invalidates JSON validation');
 assert.equal(el('json-review').hidden,true);
 assert.equal(el('json-format').disabled,true);
 assert.equal(el('json-check').disabled,true);
 assert.equal(el('json-cancel').hidden,false);
 snapshot={...snapshot,pending:false};await el('edit-cancel').onclick();
 assert.equal(el('json-check').disabled,false);
 assert.equal(el('json-cancel').hidden,true);
 assert.equal(el('json-text').value,'{"local":"keep me"}','Cross-panel changes preserve unsaved text');
 assert.equal(run('jsonRevision'),'first','Status sync does not rebase unsaved edits');
 delayCheck=true;const crossPanelCheck=el('json-check').onclick();
 snapshot={...snapshot,pending:true};await run('editorStatus()');
 snapshot={...snapshot,pending:false};await run('editorStatus()');
 resolveCheck({draft:{},identity_changed:false});await crossPanelCheck;delayCheck=false;
 assert.equal(el('json-save').disabled,true,'Pending transitions invalidate an in-flight validation');
 delayCheck=true;const oldFailure=el('json-check').onclick();
 el('json-text').value='{"new":"draft"}';el('json-text').oninput();
 rejectCheck(Error('old_validation_error'));await oldFailure;delayCheck=false;
 assert.equal(el('json-status').textContent,'json_dirty','Old validation failure must not overwrite new draft feedback');
 delayCheck=true;const oldPendingFailure=el('json-check').onclick();
 snapshot={...snapshot,pending:true};await run('editorStatus()');
 rejectCheck(Error('old_validation_error'));await oldPendingFailure;delayCheck=false;
 assert.equal(el('json-status').textContent,'edit_pending','Old validation failure must not overwrite pending feedback');
 snapshot={...snapshot,pending:false};await run('editorStatus()');
 await el('json-check').onclick();
 el('json-confirm').checked=true;el('json-identity').checked=true;failSave=true;
 document.activeElement=el('json-save');await el('json-save').onclick();
 assert.equal(el('json-check').focused,true,'Uncertain save returns keyboard focus to validation');
 assert.equal(el('json-review').hidden,true);
 await el('json-check').onclick();el('json-confirm').checked=true;el('json-identity').checked=true;
 document.activeElement={};el('json-check').focused=false;await el('json-save').onclick();
 assert.equal(el('json-check').focused,false,'Programmatic save must not steal unrelated focus');
 await el('json-check').onclick();el('json-confirm').checked=true;el('json-identity').checked=true;
 saveFailurePending=true;document.activeElement=el('json-save');
 await el('json-save').onclick();
 assert.equal(run('jsonPending'),true,'Uncertain save refreshes server-side pending state');
 assert.equal(el('json-cancel').hidden,false,'Possibly saved change can be cancelled');
 assert.equal(el('json-check').disabled,true,'Do not validate over a pending save');
 assert.equal(el('json-status').textContent,'edit_uncertain','Uncertainty remains explicit even when pending state was refreshed');
 // Exercise the real workspace adapter, not the removed hidden-tab focus path.
 const onboarding=fs.readFileSync(path.join(web,'onboarding.js'),'utf8');
 vm.runInContext(onboarding.slice(0,onboarding.indexOf('function setupErrorKey')),context);
 run("goWorkspace('diagnosis')");el('diagnosis-advanced').open=true;el('diagnosis-advanced').fire('toggle');
 assert.equal(el('json-panel').hidden,false);assert.equal(el('graphic-panel').hidden,true);
 const beforeReturn=requests.length,retainedDraft=el('json-text').value,retainedRevision=run('jsonRevision');
 el('json-return').focus();el('json-return').onclick();
 assert.equal(document.activeElement,el('nav-devices'),'Return focuses the visible main navigation');
 assert.equal(el('graphic-panel').hidden,false);assert.equal(el('diagnosis-panel').hidden,true);
 assert.equal(el('json-text').value,retainedDraft);assert.equal(run('jsonRevision'),retainedRevision);
 el('nav-diagnosis').onclick();assert.equal(el('json-panel').hidden,false,'Reopening the expanded editor does not lose the text');
 assert.equal(el('json-text').value,retainedDraft);assert.equal(requests.length,beforeReturn,'Navigation does not reload or stage a draft');
 assert.doesNotMatch(html,/role="tab(?:list|panel)?"|id="(?:graphic|json)-tab"/);
 console.log('JSON UI tests passed: visible return focus, preserved draft/revision, required readable review, consent, stale validation.');
})().catch(error=>{console.error(error);process.exitCode=1;});

// Status styling must never stay green after polling fails.
const statusContext=vm.createContext({document:{getElementById:el,querySelectorAll:()=>[]},setText:(e,text)=>{e.textContent=text;}});
const app=fs.readFileSync(path.join(web,'app.js'),'utf8');
vm.runInContext(app.slice(0,app.indexOf('function render(fresh')),statusContext);
vm.runInContext(app.slice(app.indexOf('function controlUnavailableReason'),app.indexOf('function confirmLight')),statusContext);
vm.runInContext('apiOnline=true;data={connected:true};renderConnection()',statusContext);
assert.equal(el('connection').dataset.state,'live');
vm.runInContext('data.connected=false;renderConnection()',statusContext);
assert.equal(el('connection').dataset.state,'waiting');
vm.runInContext('apiOnline=false;renderConnection()',statusContext);
assert.equal(el('connection').dataset.state,'offline');
assert.ok(app.includes('catch{apiOnline=false;renderConnection();}'));
