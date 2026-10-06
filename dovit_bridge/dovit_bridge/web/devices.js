'use strict';
async function editorRequest(action, body) {
 const response=await fetch(action?`api/devices/${action}`:'api/devices',action?{
  method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':data.draft_token},
  body:JSON.stringify(body),signal:AbortSignal.timeout(5000)
 }:{cache:'no-store',signal:AbortSignal.timeout(5000)});
 const result=await response.json();
 if(!response.ok)throw Error(result.error||'edit_storage_error');
 return result;
}
async function editorStatus() {
 try {const state=await editorRequest();setText($('edit-status'),state.disabled?'edit_disabled':state.pending?'edit_pending':'edit_ready');$('edit-cancel').hidden=!state.pending;if(!state.disabled&&typeof jsonSyncPending==='function')jsonSyncPending(!!state.pending);}
 catch {setText($('edit-status'),'edit_storage_error');}
}
$('edit-cancel').onclick=async()=>{
 if(!window.confirm(t('edit_cancel_confirm')))return;
 try{await editorRequest('cancel',{confirm:true});await editorStatus();}catch{setText($('edit-status'),'edit_storage_error');}
};
editorStatus();

function managementButton(device){
 const button=node('button','','manage-button');
 button.dataset.deviceUid=device.uid;
 button.setAttribute('aria-label',`${t('manage_device')}: ${device.name}`);button.title=t('manage_device');
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
 const path=document.createElementNS('http://www.w3.org/2000/svg','path');
 path.setAttribute('d','M9 3h6l.5 3 2 1 2.8-1 3 5-2.3 2v2l2.3 2-3 5-2.8-1-2 1-.5 3H9l-.5-3-2-1-2.8 1-3-5L3 15v-2L.7 11l3-5 2.8 1 2-1L9 3z M16 14a4 4 0 1 1-8 0 4 4 0 0 1 8 0');
 svg.setAttribute('viewBox','-1 1 26 26');
 svg.append(path);button.append(svg);
 if(device.category==='unknown'){
  button.dataset.action='assign';button.append(node('span','edit_assign'));
  button.setAttribute('aria-label',`${t('edit_assign')}: ${device.name}`);button.title=t('edit_assign');
 }
 button.onclick=()=>device.category==='unknown'?openEditor(device):openManagement(device);return button;
}

function openManagement(device){
 const old=$('device-manager');if(old)old.remove();
 const dialog=node('dialog','');dialog.id='device-manager';
 const close=node('button','Schliessen','secondary');close.onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>{
  dialog.remove();
  if(!document.querySelectorAll('dialog[open]').length)restoreManagementFocus(device.uid);
 });
 const heading=node('div','','dialog-heading'),title=node('h2',device.name,undefined,true);
 title.id='device-manager-title';dialog.setAttribute('aria-labelledby',title.id);
 heading.append(title,node('p',names[device.category],'device-meta'));dialog.append(heading);
 if(device.read_only||device.category==='clocks')dialog.append(node('p','clock_read_only'));
 else if(device.category==='alarms')dialog.append(node('p','edit_alarm_locked'));
 else{
  const actions=node('div','','manager-actions'),edit=node('button',device.category==='unknown'?'edit_assign':'edit_device');
  edit.onclick=()=>openEditor(device,dialog);actions.append(edit);dialog.append(actions);
 }
 const testPanel=node('details','','manager-test');testPanel.append(node('summary','manage_test'));
 const testActions=node('div','','test-actions');
 if(device.category==='lights'&&data.light_control&&data.light_control!=='disabled'){
  const error=node('p','');error.setAttribute('role','alert');
  const availability=node('p','','control-availability');availability.setAttribute('role','status');
  testPanel.append(node('p',data.light_control==='simulation'?'light_sim':'light_live'));
  for(const action of ['ON','OFF']){const button=node('button',action==='ON'?'light_on':'light_off');
   registerControlButton(button,'light_control',availability);
   button.onclick=()=>{if(!updateControlButton(button))confirmLight(device,action,error);};testActions.append(button);}
  testPanel.append(testActions,availability,error);dialog.append(testPanel);
 }else if(['shutters','thermostats'].includes(device.category)){
  if(!data.device_control||data.device_control==='disabled')testPanel.append(node('p','control_disabled'));
  else{
   testPanel.append(node('p',data.device_control==='simulation'?'light_sim':'control_live'));
   const error=node('p','');error.setAttribute('role','alert');
   const availability=node('p','','control-availability');availability.setAttribute('role','status');
   const addTest=(action,label,value)=>{const button=node('button',label);registerControlButton(button,'device_control',availability);
    button.onclick=()=>{if(updateControlButton(button))return;try{openDeviceTest(device,action,typeof value==='function'?value():value);}catch(e){setText(error,e.message==='control_temperature'?e.message:'light_dialog_error');}};testActions.append(button);};
   if(device.category==='shutters'){
    testPanel.append(node('p','control_cover_hint'));
    for(const [action,label] of [['OPEN','control_open'],['STOP','control_stop'],['CLOSE','control_close']])addTest(action,label);
   }else{
    addTest('heat','control_heat');addTest('off','control_off');
    const label=node('label','ui_temperature_input'),input=node('input','');input.type='number';
    input.min=device.limits?.min_temp??5;input.max=device.limits?.max_temp??35;input.step=device.limits?.temp_step??.5;
    input.value='';input.required=true;label.append(input);testActions.append(label);
    addTest('TEMPERATURE','ui_temperature_test',()=>input.value===''?null:Number(input.value));
   }
   testPanel.append(testActions,availability,error);
  }
  dialog.append(testPanel);
 }else if(!['unknown','alarms','clocks'].includes(device.category))dialog.append(node('p',device.category==='lights'?'light_disabled':'ui_receive_only'));
 if(!device.read_only&&!['unknown','alarms','clocks'].includes(device.category)){
  const options=node('details','','manager-secondary'),remove=node('button','manage_remove','danger');
  options.append(node('summary','ui_more'));remove.onclick=()=>openRemoval(device,dialog);options.append(remove);dialog.append(options);
 }
 const footer=node('div','','dialog-footer');footer.append(close);
 dialog.append(commandDetails(device.uid),footer);document.body.append(dialog);
 try{dialog.showModal();}catch{dialog.remove();const error=$('gap');if(error)setText(error,'light_dialog_error');}
}

function openDeviceTest(device,action,value){
 if(action==='TEMPERATURE'&&(typeof value!=='number'||!Number.isFinite(value)
   ||value<(device.limits?.min_temp??5)||value>(device.limits?.max_temp??35)
   ||Math.abs(value/(device.limits?.temp_step??.5)-Math.round(value/(device.limits?.temp_step??.5)))>1e-6)){
  throw Error('control_temperature');
 }
 const dialog=node('dialog',''),status=node('p','');status.setAttribute('role','status');
 const requestId=lightRequestId();status.dataset.lightRequest=requestId;
 status.commandToken=data?.draft_token;
 const payload={category:device.category,id:Number(device.uid.split(':')[1]),action,value,confirm:true,request_id:requestId};
 const send=node('button','light_confirm'),close=node('button','Schliessen');
 const availability=node('p','','control-availability');availability.setAttribute('role','status');
 registerControlButton(send,'device_control',availability);
 status.commandMode=send.controlMode;
 const actionTitle=node('h3',controlActionKey(device.category,action),'test-action-title');
 const title=node('h2',device.name,undefined,true),notice=node('p',data.device_control==='simulation'?'light_sim':'control_live');
 title.id=`control-title-${requestId}`;actionTitle.id=`control-action-${requestId}`;notice.id=`control-warning-${requestId}`;
 dialog.setAttribute('aria-labelledby',title.id);
 dialog.setAttribute('aria-describedby',`${actionTitle.id} ${notice.id}`);
 if(action==='TEMPERATURE')actionTitle.append(node('span',` · ${value} °C`,undefined,true));
 const footer=node('div','','dialog-footer');close.className='secondary';footer.append(close,send);
 dialog.append(title,actionTitle,notice,
  commandDetails(`${device.uid} / ${action}${value===undefined?'':` / ${value} °C`}`),availability,footer,status);
 send.onclick=async()=>{
  if(updateControlButton(send)||send.dataset.controlSubmitted==='true')return;
  const wasFocused=document.activeElement===send;
  send.dataset.controlSubmitted='true';
  send.disabled=true;setTrackedCommandStatus(status,'light_requested');
  try{const response=await fetch('api/controls/command',{method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':data.draft_token},body:JSON.stringify(payload),signal:AbortSignal.timeout(5000)});
   const result=await response.json();setTrackedCommandStatus(status,response.ok?'light_'+result.command.status:result.error||'light_uncertain');
  }catch{setTrackedCommandStatus(status,'light_uncertain');}
  finally{restorePrimaryFocus(dialog,send,close,wasFocused);}
 };
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);
 try{dialog.showModal();}catch(error){dialog.remove();throw error;}
 return dialog;
}

async function openRemoval(device,dialog){
 const title=node('h2','manage_remove');title.id='device-removal-title';title.tabIndex=-1;
 dialog.setAttribute('aria-labelledby',title.id);
 dialog.replaceChildren(title,node('p',device.name,undefined,true),
  node('p',device.uid,undefined,true),node('p','manage_remove_warning'));
 title.focus?.();
 const message=node('p','');message.setAttribute('role','status');
 const label=node('label','manage_remove_confirm'),confirmed=node('input','');confirmed.type='checkbox';label.prepend(confirmed);
 const save=node('button','manage_remove_save','danger'),close=node('button','Schliessen');save.disabled=true;
 close.onclick=()=>dialog.close();dialog.append(label,save,message,close);
 let payload;
 try{const snapshot=await editorRequest();if(snapshot.disabled)throw Error('edit_disabled');if(snapshot.pending)throw Error('edit_pending');
  payload={source:device.uid,revision:snapshot.revision,operation:'delete'};
  await editorRequest('validate',payload);if(!dialog.isConnected)return;save.disabled=false;
 }catch(error){setText(message,error.message);return;}
 save.onclick=async()=>{
  if(!confirmed.checked){setText(message,'edit_confirm');return;}
  const wasFocused=document.activeElement===save;
  save.disabled=true;
  try{await editorRequest('save',{...payload,confirm:true,confirm_identity:true});confirmed.disabled=true;setText(message,'edit_pending');await editorStatus();}
  catch(error){setText(message,'edit_uncertain');await editorStatus();}
  finally{restorePrimaryFocus(dialog,save,close,wasFocused);}
 };
}

async function openEditor(device,existingDialog=null) {
 const old=$('device-editor');if(old&&old!==existingDialog)old.remove();
 const dialog=existingDialog||node('dialog','');dialog.replaceChildren();dialog.id='device-editor';
 const title=node('h2',device.category==='unknown'?'edit_assign':'edit_device');
 title.id='device-editor-title';title.tabIndex=-1;dialog.setAttribute('aria-labelledby',title.id);
 const message=node('p','');message.setAttribute('role','status');
 const close=node('button','Schliessen','secondary');close.onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>{
  dialog.remove();
  if(!existingDialog&&!document.querySelectorAll('dialog[open]').length)restoreManagementFocus(device.uid);
 });
 const footer=node('div','','dialog-footer');footer.append(close);
 dialog.append(title,node('p',device.category==='unknown'?'ui_assignment_help':'ui_edit_help'),message,footer);
 if(!existingDialog){
  document.body.append(dialog);
  try{dialog.showModal();}catch{dialog.remove();const error=$('gap');if(error)setText(error,'light_dialog_error');restoreManagementFocus(device.uid);return;}
 }
 title.focus?.();
 let snapshot;
 try {snapshot=await editorRequest();if(snapshot.disabled)throw Error('edit_disabled');if(snapshot.pending)throw Error('edit_pending');}
 catch(error){setText(message,error.message);return;}
 if(!dialog.isConnected)return;
 const source=device.category==='unknown'?null:device.uid;
 const key=source?source.split(':')[1]:device.endpoints[0][0];
 const original=source?snapshot.maps[device.category]?.[key]:null;
 if(source&&!original){setText(message,'edit_stale');return;}
 const form=node('form',''),category=node('select','');
 category.setAttribute('aria-label',t('Kategorie'));
 for(const name of ['lights','switches','motions','contacts','shutters','thermostats']){const option=node('option',names[name]);option.value=name;category.append(option);}
 for(const role of ['motion','contact']){
  const used=Object.hasOwn(snapshot.alarm_roles||{},role);
  const option=node('option','');option.value=`alarm_${role}`;option.disabled=used;
  option.textContent=t(`alarm_${role}`)+(used?` (${t('alarm_assigned')})`:'');category.append(option);
 }
 category.value=source?device.category:'lights';
 const categoryLabel=node('label','Kategorie');categoryLabel.append(category);
 const fields=node('div','','editor-fields'),result=node('pre','');
 const technical=node('details','','editor-technical'),technicalFields=node('div','','draft-fields');
 const technicalHint=node('p','ui_assignment_hint'),coverHint=node('p','ui_cover_mapping_hint');
 technical.append(node('summary','ui_technical'),technicalHint,coverHint,technicalFields);technical.open=device.category==='unknown';
 const review=node('section','','editor-review'),reviewDetails=node('details',''),readableReview=node('div','');review.hidden=true;
 reviewDetails.append(node('summary','json_details'),result);review.append(node('h3','ui_review'),readableReview,reviewDetails);
 const check=node('button','edit_check'),save=node('button','edit_save');check.type='submit';save.type='button';save.disabled=true;
 const confirmation=node('label','edit_confirm_label','check'),confirmed=node('input','');confirmed.type='checkbox';confirmation.prepend(confirmed);
 const identityLabel=node('label','edit_identity','check'),identity=node('input','');identity.type='checkbox';identityLabel.prepend(identity);identityLabel.hidden=true;
 let inputs={},validated=null,revision=0;
 function refreshSave(){save.disabled=!validated||!confirmed.checked||(!identityLabel.hidden&&!identity.checked);}
 confirmed.onchange=refreshSave;identity.onchange=refreshSave;
 function invalidate(){revision++;validated=null;save.disabled=true;review.hidden=true;reviewDetails.open=false;result.textContent='';confirmed.checked=false;identity.checked=false;identityLabel.hidden=true;setText(message,'');}
 function field(key,label,value,type='number') {const wrapper=node('label',label),input=node('input','');input.type=type;input.name=key;input.required=true;input.value=value??'';if(type==='number'){input.step=key.includes('temp')?'any':'1';}wrapper.append(input);(key==='name'?fields:technicalFields).append(wrapper);inputs[key]=input;}
 function rebuild(){
  coverHint.hidden=category.value!=='shutters';
  const name=inputs.name?.value??original?.name??'';
  fields.replaceChildren();technicalFields.replaceChildren();inputs={};
  const info=category.value===device.category?(original||{}):{};
  field('name','Geraetename',name,'text');
  field('id',category.value==='thermostats'?'Sollwert-ID':'Geraete-ID',key);
  field('statetype','Statetype',info.target?.statetype??info.statetype??device.endpoints[0]?.[1]??0);
  if(category.value.startsWith('alarm_')){
   fields.replaceChildren();technicalFields.replaceChildren();inputs={};
   field('name','Geraetename',name||t(category.value),'text');field('id','Geraete-ID',key);
   for(const part of ['state','text','trigger','command'])field(`${part}_statetype`,`alarm_${part}_statetype`,'');
   technicalFields.append(node('p','alarm_mapping_hint'));
  }
  if(category.value==='shutters')field('command_statetype','command_statetype',info.command_statetype??info.statetype??device.endpoints[0]?.[1]??0);
  if(category.value==='contacts'){
   const label=node('label','Kontaktart'),select=node('select','');
   for(const [value,name] of [['door','Tuer'],['window','Fenster'],['garage_door','Garagentor']]){const option=node('option',name);option.value=value;select.append(option);}
   select.value=info.device_class||'door';label.append(select);fields.append(label);inputs.device_class=select;
  }
  if(category.value==='thermostats'){
   field('current_id','Ist-Temperatur ID',info.current?.id);field('current_statetype','Ist-Temperatur Statetype',info.current?.statetype);
   field('mode_id','Heizmodus ID',info.mode?.id);field('mode_statetype','Heizmodus Statetype',info.mode?.statetype);
   field('min_temp','Minimum Celsius',info.min_temp??16);field('max_temp','Maximum Celsius',info.max_temp??26);field('temp_step','Sollwert-Schritt',info.temp_step??.5);
  }
  fields.append(technical);
  if(category.value!==device.category)technical.open=true;
  invalidate();
 }
 fields.oninput=invalidate;category.onchange=rebuild;
 form.addEventListener('invalid',event=>{if(event.target!==inputs.name)technical.open=true;},true);
 form.onsubmit=async event=>{
  event.preventDefault();invalidate();const current=revision;
  const edit={category:category.value};for(const [key,input] of Object.entries(inputs))edit[key]=input.type==='number'?Number(input.value):input.value;
  const payload={source,revision:snapshot.revision,device:edit};check.disabled=true;
  try{
   const answer=await editorRequest('validate',payload);if(current!==revision||!dialog.isConnected)return;
   const expectedCategory=edit.category.startsWith('alarm_')?'alarms':edit.category;
   if(answer.draft?.category!==expectedCategory||typeof answer.draft.configuration?.name!=='string'
    ||!answer.draft.configuration.name.trim())throw Error('review_unavailable');
   // A readable review is mandatory before consent can stage a change.
   try{
    if(typeof renderChangeReview!=='function'||!renderChangeReview(readableReview,answer.draft,answer.identity_changed))throw Error();
   }catch{throw Error('review_unavailable');}
   result.textContent=JSON.stringify(answer.draft,null,2);validated=payload;
   identityLabel.hidden=!answer.identity_changed;review.hidden=false;refreshSave();setText(message,source?'edit_review':'ui_assignment_review');
  }
  catch(error){if(current===revision){technical.open=true;setText(message,error.message);}}finally{check.disabled=false;}
 };
 save.onclick=async()=>{
  if(!validated||!confirmed.checked||(!identityLabel.hidden&&!identity.checked)){setText(message,'edit_confirm');return;}
  const wasFocused=document.activeElement===save;let staged=false;
  form.querySelectorAll('input,select,button').forEach(el=>el.disabled=true);
  try{await editorRequest('save',{...validated,confirm:true,confirm_identity:identity.checked});staged=true;validated=null;form.querySelectorAll('input,select,button').forEach(el=>el.disabled=true);setText(message,'edit_pending');await editorStatus();}
  catch(error){invalidate();setText(message,error.message==='Failed to fetch'?'edit_uncertain':error.message);await editorStatus();form.querySelectorAll('input,select,button').forEach(el=>el.disabled=false);save.disabled=true;}
  finally{restorePrimaryFocus(dialog,save,staged?close:check,wasFocused);}
 };
 review.append(confirmation,identityLabel,save);
 form.append(categoryLabel,fields,check,review);dialog.insertBefore(form,message);rebuild();
 if(document.activeElement===title)inputs.name.focus();
}
