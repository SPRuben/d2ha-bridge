// Offline UI logic tests: synthetic DOM and stubbed requests, no browser/network.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const web=path.join(__dirname,'../dovit_bridge/web');
class Element {
 constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.value='';this.isConnected=true;}
 append(...children){this.children.push(...children);}
 prepend(...children){this.children.unshift(...children);}
 insertBefore(child,before){this.children.splice(this.children.indexOf(before),0,child);}
 setAttribute(name,value){(this.attributes??={})[name]=value;}
 focus(){assert.ok(this.isConnected,'Never focus disconnected controls');context.document.activeElement=this;}
 addEventListener(event,callback){(this.listeners??={})[event]??=[];this.listeners[event].push(callback);}
 showModal(){this.open=true;} close(){this.open=false;for(const callback of this.listeners?.close||[])callback();}
 remove(){this.isConnected=false;this.open=false;for(const child of this.children)child.remove();}
 replaceChildren(...children){this.children=children;}
 querySelectorAll(selector){const all=this.children.flatMap(c=>[c,...c.querySelectorAll()]);return selector?all.filter(c=>selector.split(',').includes(c.tag)):all;}
}
const body=new Element('body');
const ids={'edit-status':new Element('p'),'edit-cancel':new Element('button')};
let saved=null,requests=[],saveGate=null,commandGate=null,returnedFocus=null,draftOverride=null;
const snapshot={revision:'abc',pending:false,alarm_roles:{motion:87,contact:88},maps:{lights:{19:{name:'Office',statetype:0}},shutters:{20:{name:'Window',statetype:1,command_statetype:0}}}};
const context=vm.createContext({
 $:id=>ids[id]||body.children.find(c=>c.id===id),node:(tag,text)=>new Element(tag,text),
 setText:(element,text)=>{element.textContent=text;},
 t:key=>key,names:{lights:'Light',motions:'Motion',contacts:'Contact',shutters:'Cover',thermostats:'Climate'},
 groupNames:{lights:'Lichter',motions:'Bewegungsmelder',contacts:'Kontakte',shutters:'Rolllaeden',thermostats:'Thermostate',alarms:'Alarm'},
 apiOnline:true,confirmLight:()=>{},lightRequestId:()=> '1bbde359-5769-4073-9874-3b7cd1a2860a',
 restoreManagementFocus:uid=>{returnedFocus=uid;},
 data:{draft_token:'test',light_control:'simulation'},document:{body,createElementNS:(_,tag)=>new Element(tag),querySelectorAll:()=>body.children.filter(c=>c.isConnected&&c.open)},window:{confirm:()=>true},AbortSignal:{timeout:()=>null},
 fetch:async(url,options={})=>{requests.push(url);let answer=snapshot;
  if(url.endsWith('/validate')){const raw=JSON.parse(options.body);
   const {category,id,...configuration}=raw.device||{};
   answer={draft:draftOverride||{category,device_id:id,configuration},identity_changed:raw.operation==='delete'||raw.source!==`${category}:${id}`};}
  if(url.endsWith('/save')){saved=JSON.parse(options.body);if(saveGate)await saveGate;answer={pending:true};}
  if(url.endsWith('/command')){saved=JSON.parse(options.body);if(commandGate)await commandGate;answer={command:{status:'transmitted'}};}
  return {ok:true,json:async()=>answer};}
});
const appSource=fs.readFileSync(path.join(web,'app.js'),'utf8');
vm.runInContext(appSource.slice(appSource.indexOf('function controlUnavailableReason'),appSource.indexOf('function confirmLight')),context);
vm.runInContext(fs.readFileSync(path.join(web,'change-review.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(web,'devices.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const form=()=>body.children.at(-1).children.find(c=>c.tag==='form');
const fields=()=>form().querySelectorAll().find(c=>c.tag==='div');
const input=name=>fields().querySelectorAll().find(c=>c.name===name);
const button=name=>form().querySelectorAll().find(c=>c.tag==='button'&&c.textContent===name);
(async()=>{
 const assign=run("managementButton({name:'Signal 999',category:'unknown',uid:'999:3'})");
 assert.equal(assign.dataset.action,'assign');
 assert.ok(assign.children.some(child=>child.tag==='span'&&child.textContent==='edit_assign'),'Unknown signal has a visible assignment label');
 assert.equal(assign.attributes['aria-label'],'edit_assign: Signal 999');
 const direct=run("managementButton({name:'Signal',category:'unknown',uid:'999:3',endpoints:[[999,3]]})");
 await direct.onclick();
 const directEditor=body.children.at(-1);
 assert.equal(directEditor.id,'device-editor');assert.equal(directEditor.open,true);
 assert.equal(input('id').value,999);
 directEditor.close();assert.equal(returnedFocus,'999:3');
 const modal=Element.prototype.showModal;
 Element.prototype.showModal=function(){throw Error('modal unavailable');};
 ids.gap=new Element('p');
 const beforeFailedOpen=requests.length;
 await direct.onclick();
 assert.equal(body.children.at(-1).isConnected,false);
 assert.equal(ids.gap.textContent,'light_dialog_error');
 assert.equal(requests.length,beforeFailedOpen,'Failed modal must not load an editor');
 Element.prototype.showModal=modal;
 const manage=run("managementButton({name:'Office',category:'lights',uid:'lights:19'})");
 assert.equal(manage.children.some(child=>child.tag==='span'),false,'Known devices retain one quiet management icon');
 run("openManagement({name:'Focus',category:'clocks',uid:'clocks:39',read_only:true,endpoints:[[39,111]]})");
 body.children.at(-1).close();assert.equal(returnedFocus,'clocks:39');
 returnedFocus=null;
 run("openManagement({name:'Focus',category:'clocks',uid:'clocks:39',read_only:true,endpoints:[[39,111]]})");
 const focusManager=body.children.at(-1),nested=new Element('dialog');nested.showModal();body.append(nested);
 focusManager.close();assert.equal(returnedFocus,null,'Closing must not steal focus from another modal');nested.remove();
 await run("openEditor({category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
 assert.equal(input('name').value,'Office');
 assert.equal(form().querySelectorAll().find(c=>c.tag==='section').hidden,true);
 assert.equal(fields().querySelectorAll().find(c=>c.tag==='details').open,false);
 input('name').value='Office renamed';fields().oninput();
 await form().onsubmit({preventDefault(){}});
 assert.equal(button('edit_save').disabled,true,'Validation alone cannot enable Save');
 assert.equal(form().querySelectorAll().find(c=>c.tag==='section').hidden,false);
 assert.equal(form().querySelectorAll().filter(c=>c.tag==='li').length,2,'Validated edit has an assignment and a restart explanation');
 await button('edit_save').onclick();assert.equal(saved,null,'Confirmation is mandatory');
 const confirm=form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0];confirm.checked=true;confirm.onchange();
 assert.equal(button('edit_save').disabled,false,'Confirmed validated edit enables Save');
 confirm.checked=false;confirm.onchange();assert.equal(button('edit_save').disabled,true,'Revoking consent disables Save');
 const renderer=run('renderChangeReview');
 context.renderChangeReview=undefined;
 await form().onsubmit({preventDefault(){}});
 confirm.checked=true;confirm.onchange();
 assert.equal(button('edit_save').disabled,true,'Missing readable review cannot enable Save');
 assert.equal(form().querySelectorAll().find(c=>c.tag==='section').hidden,true);
 assert.ok(body.children.at(-1).children.some(c=>c.textContent==='review_unavailable'));
 await button('edit_save').onclick();assert.equal(saved,null,'Missing renderer cannot stage changes');
 context.renderChangeReview=()=>{throw Error('unexpected renderer failure');};
 await form().onsubmit({preventDefault(){}});confirm.checked=true;confirm.onchange();
 assert.equal(button('edit_save').disabled,true,'Rendering failure leaves validation incomplete');
 assert.ok(body.children.at(-1).children.some(c=>c.textContent==='review_unavailable'));
 context.renderChangeReview=()=>false;
 await form().onsubmit({preventDefault(){}});confirm.checked=true;confirm.onchange();
 assert.equal(button('edit_save').disabled,true,'Empty renderer result cannot grant validation');
 context.renderChangeReview=renderer;
 for(const invalid of [{category:'lights'}, {category:'lights',configuration:{name:''}},
  {category:'contacts',configuration:{name:'Wrong category'}}]){
  draftOverride=invalid;await form().onsubmit({preventDefault(){}});confirm.checked=true;confirm.onchange();
  assert.equal(button('edit_save').disabled,true,'Incomplete or mismatched summary cannot enable Save');
  assert.equal(form().querySelectorAll().find(c=>c.tag==='section').hidden,true);
 }
 draftOverride=null;
 await form().onsubmit({preventDefault(){}});
 confirm.checked=true;confirm.onchange();
 let releaseSave;
 saveGate=new Promise(resolve=>{releaseSave=resolve;});
 const saving=button('edit_save').onclick();
 assert.ok(form().querySelectorAll().filter(c=>['input','select','button'].includes(c.tag)).every(c=>c.disabled),'All form controls freeze before save completes');
 releaseSave();await saving;saveGate=null;
 assert.equal(input('name').disabled,true,'Successful save keeps inputs frozen');
 assert.equal(saved.source,'lights:19');assert.equal(saved.device.name,'Office renamed');assert.equal(saved.confirm,true);
 assert.equal(saved.revision,'abc');
 await run("openEditor({category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
 await form().onsubmit({preventDefault(){}});
 const retryConfirm=form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0];retryConfirm.checked=true;retryConfirm.onchange();
 assert.equal(button('edit_save').disabled,false);
 let rejectSave;saveGate=new Promise((resolve,reject)=>{rejectSave=reject;});
 const failing=button('edit_save').onclick();
 assert.equal(input('name').disabled,true);
 rejectSave(Error('Failed to fetch'));await failing;saveGate=null;
 assert.equal(input('name').disabled,false,'Failed save unlocks inputs');
 assert.equal(form().querySelectorAll().find(c=>c.tag==='select').disabled,false);
 assert.equal(button('edit_check').disabled,false);
 assert.equal(button('edit_save').disabled,true,'Failed save requires revalidation');
 await run("openEditor({category:'shutters',uid:'shutters:20',endpoints:[[20,1]]})");
 assert.equal(input('statetype').value,1);assert.equal(input('command_statetype').value,0);
 assert.equal(fields().querySelectorAll().find(c=>c.textContent==='ui_cover_mapping_hint').hidden,false);
 await form().onsubmit({preventDefault(){}});assert.equal(button('edit_save').disabled,true);
 const coverConfirm=form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0];coverConfirm.checked=true;coverConfirm.onchange();
 assert.equal(button('edit_save').disabled,false);
 input('statetype').value=3;fields().oninput();
 assert.equal(form().querySelectorAll().find(c=>c.tag==='section').hidden,true);
 assert.equal(form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0].checked,false);assert.equal(button('edit_save').disabled,true,'Editing invalidates validation');
 await run("openEditor({category:'unknown',uid:'999:3',endpoints:[[999,3]]})");
 assert.equal(fields().querySelectorAll().find(c=>c.tag==='details').open,true);
 assert.equal(input('id').value,999);assert.equal(input('statetype').value,3);assert.equal(input('name').value,'');
 assert.equal(fields().querySelectorAll().find(c=>c.textContent==='ui_cover_mapping_hint').hidden,true);
 const assignmentCategory=form().querySelectorAll().find(c=>c.tag==='select');
 assignmentCategory.value='shutters';assignmentCategory.onchange();
 assert.equal(fields().querySelectorAll().find(c=>c.textContent==='ui_cover_mapping_hint').hidden,false);
 assignmentCategory.value='lights';assignmentCategory.onchange();
 assert.equal(fields().querySelectorAll().find(c=>c.textContent==='ui_cover_mapping_hint').hidden,true);
 input('name').value='Assigned test light';fields().oninput();
 await form().onsubmit({preventDefault(){}});
 assert.ok(body.children.at(-1).children.some(c=>c.textContent==='ui_assignment_review'));
 const assignmentConfirm=form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0];
 const identityConfirm=form().querySelectorAll().find(c=>c.textContent==='edit_identity').children[0];
 assignmentConfirm.checked=true;assignmentConfirm.onchange();
 assert.equal(button('edit_save').disabled,true,'Identity change needs separate consent');
 const previousSave=saved;await button('edit_save').onclick();assert.equal(saved,previousSave,'Programmatic click cannot bypass identity consent');
 identityConfirm.checked=true;identityConfirm.onchange();assert.equal(button('edit_save').disabled,false);
 identityConfirm.checked=false;identityConfirm.onchange();assert.equal(button('edit_save').disabled,true);
 fields().oninput();identityConfirm.checked=true;identityConfirm.onchange();
 assert.equal(button('edit_save').disabled,true,'Consent cannot revive invalidated validation');
 run("openManagement({name:'Office',category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
 let manager=body.children.at(-1);
 const disclosure=manager.children.filter(c=>c.tag==='details');
 assert.ok(disclosure.length>=3);
 assert.ok(disclosure.every(c=>!c.open),'Manager disclosures start closed');
 assert.ok(disclosure.some(c=>c.querySelectorAll().some(el=>el.textContent==='manage_remove')),'Deletion is behind secondary details');
 const beforeDisclosure=requests.length;for(const detail of disclosure)detail.open=true;
 assert.equal(requests.length,beforeDisclosure,'Opening disclosures sends nothing');
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='light_on'));
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='light_off'));
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='edit_device'));
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='manage_remove'));
 const countBefore=requests.length;
 run("managementButton({name:'Office',category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
 assert.equal(requests.length,countBefore,'Creating a management button sends nothing');
 await manager.querySelectorAll().find(c=>c.textContent==='manage_remove').onclick();
 assert.equal(manager.attributes['aria-labelledby'],'device-removal-title');
 const removalTitle=manager.querySelectorAll().find(c=>c.id===manager.attributes['aria-labelledby']);
 assert.ok(removalTitle);assert.equal(removalTitle.tabIndex,-1);assert.equal(context.document.activeElement,removalTitle);
 saved=null;
 const remove=manager.querySelectorAll().find(c=>c.textContent==='manage_remove_save');
 await remove.onclick();assert.equal(saved,null);
 manager.querySelectorAll().find(c=>c.textContent==='manage_remove_confirm').children[0].checked=true;
 await remove.onclick();assert.equal(saved.operation,'delete');assert.equal(saved.confirm_identity,true);
 run("openManagement({name:'Alarm',category:'alarms',uid:'alarms:87',endpoints:[[87,0]]})");
 manager=body.children.at(-1);
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='edit_alarm_locked'));
 assert.ok(!manager.querySelectorAll().some(c=>['light_on','edit_device','manage_remove'].includes(c.textContent)));
 run("openManagement({name:'Office',category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
 const transitioning=body.children.at(-1);
 await transitioning.querySelectorAll().find(c=>c.textContent==='edit_device').onclick();
 assert.equal(transitioning.attributes['aria-labelledby'],'device-editor-title');
 const editorTitle=transitioning.querySelectorAll().find(c=>c.id===transitioning.attributes['aria-labelledby']);
 assert.ok(editorTitle);assert.equal(editorTitle.tabIndex,-1);
 assert.equal(context.document.activeElement,input('name'),'Editor transition focuses the name after loading');
 run("openManagement({name:'Signal',category:'unknown',uid:'999:3',endpoints:[[999,3]]})");
 manager=body.children.at(-1);
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='edit_assign'));
 assert.ok(!manager.querySelectorAll().some(c=>['light_on','manage_remove'].includes(c.textContent)));
 run("openManagement({name:'Dovit',category:'clocks',uid:'clocks:39',read_only:true,endpoints:[[39,111]]})");
 manager=body.children.at(-1);
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='clock_read_only'));
 assert.ok(!manager.querySelectorAll().some(c=>['light_on','edit_device','manage_remove'].includes(c.textContent)));
 console.log('Device editor UI logic passed: prefill, confirmation, staging, invalidation, unknown endpoint. No network used.');
 await run("openEditor({category:'unknown',uid:'188:1',endpoints:[[188,1]]})");
 let select=form().querySelectorAll().find(c=>c.tag==='select');
 assert.equal(select.children.find(o=>o.value==='alarm_motion').disabled,true);
 assert.equal(select.children.find(o=>o.value==='alarm_contact').disabled,true);
 assert.ok(select.children.find(o=>o.value==='alarm_contact').textContent.includes('alarm_assigned'));
 delete snapshot.alarm_roles.contact;
 await run("openEditor({category:'unknown',uid:'188:1',endpoints:[[188,1]]})");
 select=form().querySelectorAll().find(c=>c.tag==='select');
 assert.equal(select.children.find(o=>o.value==='alarm_contact').disabled,false);
 select.value='alarm_contact';select.onchange();
 assert.equal(input('id').value,188);assert.ok(input('command_statetype'));assert.ok(input('trigger_statetype'));
 run("data.device_control='simulation';openManagement({name:'Cover',category:'shutters',uid:'shutters:20',endpoints:[[20,1]]})");
 manager=body.children.at(-1);
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='light_sim'));
 for(const label of ['control_open','control_stop','control_close'])assert.ok(manager.querySelectorAll().some(c=>c.textContent===label));
 const beforeTest=requests.length;
 run('apiOnline=false');
 manager.querySelectorAll().find(c=>c.textContent==='control_stop').onclick();
 assert.equal(requests.length,beforeTest);
 assert.equal(body.children.at(-1),manager,'Offline management cannot open a test');
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='control_api_offline'));
 run('apiOnline=true');
 manager.querySelectorAll().find(c=>c.textContent==='control_stop').onclick();
 assert.equal(requests.length,beforeTest,'Opening test sends no command');
 let testDialog=body.children.at(-1);
 assert.equal(testDialog.querySelectorAll().find(c=>c.dataset.lightRequest).commandMode,'simulation','Device feedback captures the dialog mode');
 run('apiOnline=false');
 await testDialog.querySelectorAll().find(c=>c.textContent==='light_confirm').onclick();
 assert.equal(requests.length,beforeTest,'Offline confirmation cannot send');
 run('apiOnline=true');
 await testDialog.querySelectorAll().find(c=>c.textContent==='light_confirm').onclick();
 assert.equal(saved.category,'shutters');assert.equal(saved.action,'STOP');assert.equal(saved.confirm,true);
 assert.equal(saved.id,20);assert.equal(saved.request_id,'1bbde359-5769-4073-9874-3b7cd1a2860a');
 run("openManagement({name:'Climate',category:'thermostats',uid:'thermostats:44',limits:{min_temp:16,max_temp:26,temp_step:.5},endpoints:[[44,1]]})");
 manager=body.children.at(-1);
 for(const label of ['control_heat','control_off','ui_temperature_test'])assert.ok(manager.querySelectorAll().some(c=>c.tag==='button'&&c.textContent===label));
 assert.ok(manager.querySelectorAll().some(c=>c.tag==='label'&&c.textContent==='ui_temperature_input'));
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='light_sim'));
 for(const category of ['shutters','thermostats']){
  run(`data.device_control='live';openManagement({name:'Live',category:'${category}',uid:'${category}:44',endpoints:[[44,1]]})`);
  assert.ok(body.children.at(-1).querySelectorAll().some(c=>c.textContent==='control_live'));
 }
 run("data.device_control='simulation'");
 const countDialogs=body.children.length;
 manager.querySelectorAll().find(c=>c.tag==='button'&&c.textContent==='ui_temperature_test').onclick();
 assert.equal(body.children.length,countDialogs,'Empty temperature must not open confirmation');
 assert.ok(manager.querySelectorAll().some(c=>c.textContent==='control_temperature'));
 for(const fail of [false,true])for(const focusCase of ['primary','body','other','not-primary','closed']){
  run("openDeviceTest({name:'Cover',category:'shutters',uid:'shutters:20'},'STOP')");
  const dialog=body.children.at(-1),descendants=dialog.querySelectorAll();
  for(const attribute of ['aria-labelledby','aria-describedby']){
   assert.ok(dialog.attributes[attribute]);
   for(const id of dialog.attributes[attribute].split(/\s+/))assert.ok(descendants.some(el=>el.id===id),'Device test accessible reference resolves');
  }
  assert.ok(dialog.attributes['aria-labelledby'].includes('1bbde359-5769-4073-9874-3b7cd1a2860a'),'Title uses request identity');
  const primary=descendants.find(c=>c.textContent==='light_confirm'),close=descendants.find(c=>c.tag==='button'&&c.textContent==='Schliessen');
  const other=new Element('input');context.document.activeElement=focusCase==='not-primary'?other:primary;
  let resolve,reject;commandGate=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const before=requests.length,sending=primary.onclick();
  if(focusCase==='body')context.document.activeElement=body;
  if(focusCase==='other')context.document.activeElement=other;
  if(focusCase==='closed'){dialog.close();context.document.activeElement=other;}
  if(fail)reject(Error('Failed to fetch'));else resolve();
  await sending;commandGate=null;
  assert.equal(context.document.activeElement,['primary','body'].includes(focusCase)?close:other,`Device test completion focus: ${fail}/${focusCase}`);
  assert.equal(requests.length,before+1);
 }
 for(const fail of [false,true])for(const focusCase of ['primary','body','other','not-primary','closed']){
  await run("openEditor({category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
  const editor=body.children.at(-1);
  await form().onsubmit({preventDefault(){}});
  const consent=form().querySelectorAll().find(c=>c.textContent==='edit_confirm_label').children[0];consent.checked=true;consent.onchange();
  const primary=button('edit_save'),check=button('edit_check');
  const close=editor.querySelectorAll().find(c=>c.tag==='button'&&c.textContent==='Schliessen');
  const other=new Element('input');context.document.activeElement=focusCase==='not-primary'?other:primary;
  let resolve,reject;saveGate=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const saving=primary.onclick();
  if(focusCase==='body')context.document.activeElement=body;
  if(focusCase==='other')context.document.activeElement=other;
  if(focusCase==='closed'){editor.close();context.document.activeElement=other;}
  if(fail)reject(Error('Failed to fetch'));else resolve();
  await saving;saveGate=null;
  assert.equal(context.document.activeElement,['primary','body'].includes(focusCase)?(fail?check:close):other,`Editor completion focus: ${fail}/${focusCase}`);
 }
 for(const fail of [false,true])for(const focusCase of ['primary','body','other','not-primary','closed']){
  run("openManagement({name:'Office',category:'lights',uid:'lights:19',endpoints:[[19,0]]})");
  const dialog=body.children.at(-1);
  await dialog.querySelectorAll().find(c=>c.textContent==='manage_remove').onclick();
  const primary=dialog.querySelectorAll().find(c=>c.textContent==='manage_remove_save');
  const close=dialog.querySelectorAll().find(c=>c.tag==='button'&&c.textContent==='Schliessen');
  dialog.querySelectorAll().find(c=>c.textContent==='manage_remove_confirm').children[0].checked=true;
  const other=new Element('input');context.document.activeElement=focusCase==='not-primary'?other:primary;
  let resolve,reject;saveGate=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const saving=primary.onclick();
  assert.equal(saved.operation,'delete');assert.equal(saved.confirm,true);assert.equal(saved.confirm_identity,true);
  if(focusCase==='body')context.document.activeElement=body;
  if(focusCase==='other')context.document.activeElement=other;
  if(focusCase==='closed'){dialog.close();context.document.activeElement=other;}
  if(fail)reject(Error('Failed to fetch'));else resolve();
  await saving;saveGate=null;
  assert.equal(context.document.activeElement,['primary','body'].includes(focusCase)?close:other,`Removal completion focus: ${fail}/${focusCase}`);
 }
 console.log('Control confirmations and unique alarm dropdown passed. No network used.');
})().catch(error=>{console.error(error);process.exitCode=1;});
