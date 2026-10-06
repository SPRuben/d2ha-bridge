'use strict';
const $ = id => document.getElementById(id);
const names = {switches:'Schalter',lights:'Licht',shutters:'Rollladen',thermostats:'Thermostat',motions:'Bewegungsmelder',contacts:'Kontakt',alarms:'Alarm',clocks:'clock_label',unknown:'Unbekannt'};
const groupNames = {switches:'Schalter',lights:'Lichter',shutters:'Rolllaeden',thermostats:'Thermostate',motions:'Bewegungsmelder',contacts:'Kontakte',alarms:'Alarm',clocks:'clock_group'};
function displayValue(device,state){
 if(device.category!=='clocks')return state.value;
 const parts=/^(\d{1,2});(\d{1,2})$/.exec(state.value);
 return parts&&Number(parts[1])<24&&Number(parts[2])<60
  ?`${parts[1].padStart(2,'0')}:${parts[2].padStart(2,'0')}`:state.value;
}
function stateSummary(device,state){
 const raw=String(state.value).trim();
 if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw))return '';
 const value=Number(raw);if(!Number.isFinite(value))return '';
 let key='';
 if(device.category==='switches')key=value===1?'state_switch_on':value===0?'state_switch_off':'';
 if(device.category==='lights')key=value>=.5?'state_light_on':'state_light_off';
 if(device.category==='motions')key=value>=.5?'state_motion_on':'state_motion_off';
 if(device.category==='contacts')key=value>=.5?'state_contact_open':'state_contact_closed';
 if(device.category==='shutters'){
  // Mirror confirmed protocol values; STOP does not establish an endpoint.
  key=({'1':'state_cover_opening','2':'state_cover_closing','0':'state_cover_stopped'})[raw]||
      ({'1.0':'state_cover_opening','2.0':'state_cover_closing','0.0':'state_cover_stopped'})[raw]||'';
 }
 if(device.category==='thermostats'){
  const role=(state.matches||[]).find(match=>match.uid===device.uid)?.role;
  if(role==='current'||role==='target')return `${t('state_'+role)}: ${raw.replace('.',',')}\u00a0\u00b0C`;
  if(role==='mode')key=value>=.5?'state_mode_heat':'state_mode_off';
 }
 return key?t(key):'';
}
function receivedTime(state){
 const parts=typeof state.time==='string'&&/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(state.time);
 if(!parts)return null;
 const [year,month,day,hour,minute,second]=parts.slice(1,7).map(Number);
 const leap=year%4===0&&(year%100!==0||year%400===0);
 const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
 const zone=parts[7];
 if(year<1||month<1||month>12||day<1||day>days[month-1]||hour>23||minute>59||second>59||
    zone!=='Z'&&(Number(zone.slice(1,3))>23||Number(zone.slice(4))>59))return null;
 const received=new Date(state.time);
 return Number.isFinite(received.getTime())?received:null;
}
function appendReceivedTime(container,state){
 const received=receivedTime(state),archived=state.kind==='historical'||state.provenance==='candidate_archive';
 const formatted=received?time(received):t('state_received_unknown');
 const label=archived?t('state_received_archive').replace('{time}',formatted):
  received?t('state_received_at').replace('{time}',formatted):formatted;
 const element=node(received?'time':'small',label,'device-received',true);
 if(received)element.dateTime=received.toISOString();
 if(archived)element.dataset.archived='true';
 container.append(element);
}
function appendStateSummary(card,device,states){
 if(!states.length||device.category==='unknown')return;
 const summaries=states.map(state=>({state,text:device.category==='clocks'?displayValue(device,state):stateSummary(device,state)})).filter(item=>item.text);
 const summary=node('div','','device-state');
 if(summaries.length){
  if(device.category!=='clocks')summary.append(node('small','state_last_reported'));
  // Each value keeps its endpoint's timestamp; newer thermostat reports do not refresh other values.
  for(const {state,text} of summaries){summary.append(node('p',text,undefined,true));appendReceivedTime(summary,state);}
 }else{
  summary.append(node('p','ui_received'));
  for(const state of states){
   if(states.length>1)summary.append(node('small',`ID ${state.device_id} / ST ${state.statetype}`,'device-received-endpoint',true));
   appendReceivedTime(summary,state);
  }
 }
 card.insertBefore(summary,card.children[2]||null);
}
function appendClassification(container,item,explain=false){
 const classification=item.classification;
 if(!['observed','inferred','confirmed'].includes(classification))return;
 const label=node('p','classification_'+classification,'classification-label');
 label.dataset.classification=classification;container.append(label);
 if(explain)container.append(node('p','classification_'+classification+'_hint','device-meta'));
}
function restoreManagementFocus(uid){
 if(!uid)return;
 const button=Array.from(document.querySelectorAll('.manage-button')).find(button=>button.dataset.deviceUid===uid);
 if(button)button.focus({preventScroll:true});
}
function renderDeviceGroups(shown,cards){
 const focusedUid=document.activeElement?.dataset.deviceUid;
 const focusedDetail=document.activeElement?.dataset.detailUid;
 const groups=[];
 for(const category of Object.keys(groupNames)){
  const members=cards.filter((_,i)=>shown[i].category===category);
  if(!members.length)continue;
  const section=node('section','','device-group');section.dataset.category=category;
  const heading=node('div','','section-head');heading.append(node('h3',groupNames[category]),node('span',String(members.length),undefined,true));
  const grid=node('div','','grid');grid.append(...members);section.append(heading,grid);groups.push(section);
 }
 $('devices').replaceChildren(...(groups.length?groups:[node('p','known_empty')]));
 const unknown=cards.filter((_,i)=>shown[i].category==='unknown');
 $('unknown-devices').replaceChildren(...(unknown.length?unknown:[node('p','unknown_empty')]));
 restoreManagementFocus(focusedUid);
 if(focusedDetail){
  const summary=Array.from(document.querySelectorAll('.device-details summary')).find(el=>el.dataset.detailUid===focusedDetail);
  if(summary)summary.focus({preventScroll:true});
 }
}
let data=null, cursor=0, session=null, baseline=null, active=false, apiOnline=false;
const deviceDetailsOpen=new Set();
const node=(tag,text,cls,raw=false)=>{const n=document.createElement(tag);if(raw||!text)n.textContent=text;else setText(n,text);if(cls)n.className=cls;return n;};
const time=t=>new Date(t).toLocaleString(language==='fr'?'fr-FR':'de-DE');
function renderConnection(){
 const simulation=data?.light_control==='simulation'||data?.device_control==='simulation';
 const status=$('connection');status.dataset.state=!apiOnline?'offline':simulation?'demo':data?.connected?'live':'waiting';
 setText(status,!apiOnline?'Verbindung unterbrochen · Werte eventuell veraltet':simulation?'ui_demo_status':data?.connected?'Live · Dovit verbunden':'Oberflaeche erreichbar · Dovit nicht verbunden');
 refreshControlButtons();
 if(typeof renderSetup==='function')renderSetup();
}
function render(fresh=false){
 if(!data)return;
 document.querySelectorAll('[data-light-request]').forEach(el=>{const command=(data.commands||[]).find(c=>c.request_id===el.dataset.lightRequest);setTrackedCommandStatus(el,command?'light_'+command.status:'');});
 const notice=document.querySelector('.notice');if(notice)setText(notice,data.device_control==='live'?'control_live':data.light_control==='live'?'light_live':data.light_control==='simulation'||data.device_control==='simulation'?'light_sim':'Nur beobachten. Diese Oberflaeche sendet keine Schaltbefehle.');
 let archive=$('archive');if(!archive){archive=node('p','');archive.id='archive';$('session').after(archive);}
 setText(archive,({saved:'Unbekannte Signale gespeichert.',ready:'Archiv bereit; Speicherung alle 5 Sekunden.',blocked:'Archiv beschaedigt oder nicht lesbar: Original erhalten, Speicherung gesperrt.',error:'Speicherfehler: Signale aktuell nur im Arbeitsspeicher.',disabled:'Vorschau: keine dauerhafte Speicherung.'})[data.persistence]||'');
 renderConnection();
 const query=$('search').value.toLocaleLowerCase(),category=$('category').value;
 const devices=[...data.devices,...data.states.filter(s=>!s.matches.length).map(s=>({uid:s.key,name:`Signal ${s.device_id}`,category:'unknown',endpoints:[[s.device_id,s.statetype,'state']]}))];
 const matches=d=>(!category||d.category===category)&&(`${d.name} ${d.uid} ${d.endpoints.map(e=>e[0]).join(' ')}`).toLocaleLowerCase().includes(query);
 const statesFor=d=>data.states.filter(s=>d.category==='unknown'?s.key===d.uid:s.matches.some(m=>m.uid===d.uid));
 const shown=devices.filter(matches).filter(d=>!active||statesFor(d).some(s=>s.seq>baseline));
 setText($('count'),`${shown.filter(d=>d.category!=='unknown').length} sichtbar`);
 setText($('unknown-count'),`${shown.filter(d=>d.category==='unknown').length} sichtbar`);
 const cards=shown.map(d=>{
  const c=node('article','',`card ${d.category==='unknown'?'unknown':''}`);
  c.append(node('small',names[d.category]),node('h3',d.name,undefined,true));
  const states=statesFor(d);
  appendClassification(c,d);
  if(!states.length)c.append(node('p','Noch keine Meldung seit Bridge-Start.'));
  const details=node('details','','device-details');
  details.open=deviceDetailsOpen.has(d.uid);
  details.ontoggle=()=>{if(details.open)deviceDetailsOpen.add(d.uid);else deviceDetailsOpen.delete(d.uid);};
  const summary=node('summary','ui_signals');summary.dataset.detailUid=d.uid;details.append(summary);
  if(['observed','inferred','confirmed'].includes(d.classification))details.append(node('p','classification_'+d.classification+'_hint','device-meta'));
  for(const s of states){
   const raw=node('p',`${s.device_id} / ST ${s.statetype}  →  ${displayValue(d,s)}`,undefined,true);
   const recorded=receivedTime(s);
   const received=node('small','');setText(received,`${recorded?time(recorded):t('state_received_unknown')} · ${s.count} Meldungen`);
   if(d.category==='unknown'){c.append(raw,received);appendClassification(c,s);}
   else{details.append(raw,received);if(s.classification!==d.classification)appendClassification(details,s);}
  }
  if(states.length&&d.category!=='unknown'){
   c.append(details);
  }
  if(fresh&&data.events.some(e=>e.seq>cursor&&e.kind==='change'&&(d.category==='unknown'?e.key===d.uid:e.matches.some(m=>m.uid===d.uid))))c.classList.add('pulse');
  return c;
 });
 cards.forEach((card,index)=>{
  const states=statesFor(shown[index]);
  appendStateSummary(card,shown[index],states);
  if(states.length&&states.every(s=>s.kind==='historical'))card.append(node('p','Archiviert: seit diesem Start noch nicht empfangen.'));
 });
 cards.forEach((card,index)=>card.append(managementButton(shown[index])));
 renderDeviceGroups(shown,cards);
 const visible=new Set(shown.map(d=>d.uid));
 const events=data.events.filter(e=>(!active||e.seq>baseline)&&($('repeats').checked||e.kind!=='repeat')&&(e.matches.length?e.matches.some(m=>visible.has(m.uid)):visible.has(e.key))).reverse();
 $('events').replaceChildren(...events.map(e=>{const row=node('div','','event');const title=e.matches.map(m=>data.devices.find(d=>d.uid===m.uid)?.name||m.uid).join(', ')||`Unbekanntes Signal ${e.device_id}`;const detail=node('div',e.matches.length?title:t(title),undefined,true);detail.append(node('small',`ID ${e.device_id} / ST ${e.statetype} · ${time(e.time)}`));row.append(node('span',e.kind==='change'?'Aenderung':e.kind==='first'?'Erstmeldung':'Wiederholt'),detail,node('span',`${e.previous===null?'?':e.previous} → ${e.value}`,undefined,true));return row;}));
}
$('observe').onclick=()=>{if(!data)return;active=!active;baseline=active?data.sequence:null;setText($('observe'),active?'Beobachtung beenden':'Beobachtung starten');setText($('session'),active?'Beobachtung aktiv: nur neue Meldungen ab jetzt. Keine physische Steuerung.':'Alle Meldungen im begrenzten Verlauf seit Bridge-Start.');render();};
for(const id of ['search','category','repeats'])$(id).addEventListener('input',()=>render());
async function poll(){try{const r=await fetch('api/snapshot',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();const next=await r.json();apiOnline=true;const restart=session!==null&&session!==next.session;const gap=!restart&&cursor>0&&next.events.length&&next.events[0].seq>cursor+1;data=next;if(restart){active=false;baseline=null;setText($('observe'),'Beobachtung starten');setText($('session'),'Bridge wurde neu gestartet. Beobachtung bitte erneut starten.');}if(gap||restart)setText($('gap'),restart?'Verlauf durch Neustart zurueckgesetzt.':'Verlaufsluecke: mehr Ereignisse als der Puffer speichern konnte.');render(session!==null&&!restart);cursor=data.sequence;session=data.session;}catch{apiOnline=false;renderConnection();}finally{setTimeout(poll,1000);}}
translateStatic();
$('language').value=language;
$('language').onchange=()=>{language=$('language').value;try{localStorage.setItem('dovit.language',language);}catch{}translateStatic();render();};
poll();

function lightRequestId(){
 // getRandomValues is also available on HTTP; preserve UUID v4 idempotency keys.
 const bytes=new Uint8Array(16);
 globalThis.crypto.getRandomValues(bytes);
 bytes[6]=(bytes[6]&0x0f)|0x40;
 bytes[8]=(bytes[8]&0x3f)|0x80;
 const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
 return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

function controlUnavailableReason(button){
 if(!apiOnline)return 'control_api_offline';
 const kind=button.dataset.controlKind,mode=data?.[kind];
 if(mode!==button.controlMode||data?.draft_token!==button.controlToken)return 'control_dialog_stale';
 if(!['simulation','live'].includes(mode))return kind==='light_control'?'light_disabled':'control_disabled';
 if(mode==='live'&&!data.connected)return 'control_dovit_offline';
 return '';
}
function updateControlButton(button){
 const reason=controlUnavailableReason(button);
 button.disabled=!!reason||button.dataset.controlSubmitted==='true';
 if(button.controlNotice){button.controlNotice.hidden=!reason;setText(button.controlNotice,reason);}
 return reason;
}
function registerControlButton(button,kind,notice=null){
 button.dataset.controlKind=kind;button.controlMode=data?.[kind];
 button.controlToken=data?.draft_token;button.controlNotice=notice;
 updateControlButton(button);
}
function refreshControlButtons(){
 document.querySelectorAll('[data-control-kind]').forEach(updateControlButton);
}
function setTrackedCommandStatus(element,key){
 if(element.commandToken!==data?.draft_token){
  if(['light_requested','light_transmitted','light_uncertain'].includes(element.dataset.commandLabel))setText(element,'control_tracking_lost');
  return;
 }
 if(key){
  element.dataset.commandLabel=key;
  const simulated=element.commandMode==='simulation'&&['light_requested','light_transmitted','light_observed','light_failed','light_timeout','light_uncertain'].includes(key);
  setText(element,simulated?key.replace('light_','simulation_'):key);
 }
}

function controlActionKey(category,action){
 if(category==='lights')return action==='ON'?'light_on':'light_off';
 return ({OPEN:'control_open',STOP:'control_stop',CLOSE:'control_close',heat:'control_heat',off:'control_off',TEMPERATURE:'control_temperature_label'})[action]||'manage_test';
}

function commandDetails(text){
 const details=node('details','','device-details');
 details.append(node('summary','ui_signals'),node('p',text,undefined,true));
 return details;
}

function restorePrimaryFocus(dialog,primary,target,wasFocused){
 if(wasFocused&&dialog.open&&dialog.isConnected!==false
   &&(document.activeElement===primary||document.activeElement===document.body))target.focus?.();
}

function confirmLight(device,action,errorTarget=null){
 try{openLightDialog(device,action);}
 catch{setText(errorTarget||$('gap'),'light_dialog_error');}
}

function openLightDialog(device,action){
 const dialog=node('dialog','');
 const title=node('h2',device.name,undefined,true);
 const notice=node('p',data.light_control==='simulation'?'light_sim':'light_live');
 const detail=commandDetails(`ID ${device.endpoints[0][0]} / ST ${device.endpoints[0][1]} / ${action} / ${action==='ON'?'1.0':'0.0'}`);
 const actionTitle=node('h3',controlActionKey('lights',action),'test-action-title');
 const send=node('button','light_confirm'),close=node('button','Schliessen'),status=node('p','');status.setAttribute('role','status');
 const availability=node('p','','control-availability');availability.setAttribute('role','status');
 registerControlButton(send,'light_control',availability);
 const requestId=lightRequestId();
 title.id=`light-title-${requestId}`;actionTitle.id=`light-action-${requestId}`;notice.id=`light-warning-${requestId}`;
 dialog.setAttribute('aria-labelledby',title.id);
 dialog.setAttribute('aria-describedby',`${actionTitle.id} ${notice.id}`);
 status.dataset.lightRequest=requestId;
 status.commandToken=data?.draft_token;
 status.commandMode=send.controlMode;
 send.onclick=async()=>{
  if(updateControlButton(send)||send.dataset.controlSubmitted==='true')return;
  const wasFocused=document.activeElement===send;
  send.dataset.controlSubmitted='true';send.disabled=true;setTrackedCommandStatus(status,'light_requested');
  try{const response=await fetch('api/lights/command',{method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':data.draft_token},body:JSON.stringify({id:device.endpoints[0][0],action,confirm:true,request_id:requestId}),signal:AbortSignal.timeout(5000)});const answer=await response.json();setTrackedCommandStatus(status,response.ok?'light_'+answer.command.status:(answer.error||'light_uncertain'));}
  catch{setTrackedCommandStatus(status,'light_uncertain');}
  finally{restorePrimaryFocus(dialog,send,close,wasFocused);}
 };
 const actions=node('div','','dialog-footer');actions.append(close,send);
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());dialog.append(title,actionTitle,notice,detail,availability,actions,status);document.body.append(dialog);
 try{dialog.showModal();}catch(error){dialog.remove();throw error;}
 return dialog;
}

function openDraft(endpoint){
 const previous=$('mapping-dialog');if(previous)previous.remove();
 const dialog=node('dialog','');dialog.id='mapping-dialog';
 const title=node('h2','Signal zuordnen');const hint=node('p','Nur Entwurf: keine Aktivierung, keine Schaltbefehle. Bestehende Zuordnungen werden nicht ersetzt.');
 const form=node('form','');const category=node('select','');category.dataset.i18nLabel='Kategorie';category.setAttribute('aria-label',t('Kategorie'));
 for(const key of ['lights','switches','motions','contacts','shutters','thermostats']){const option=node('option',names[key]);option.value=key;category.append(option);}
 const fields=node('div','','draft-fields'),result=node('pre',''),message=node('p','');message.setAttribute('role','status');
 const check=node('button','Entwurf pruefen'),save=node('button','Entwurf speichern'),close=node('button','Schliessen');
 check.type='submit';save.type=close.type='button';save.disabled=true;
 let validated=null, revision=0;
 const inputs={};
 function field(key,label,value,type='number') {const wrapper=node('label',label),input=node('input','');input.type=type;input.required=true;input.value=value;input.name=key;if(type==='number')input.step=key.includes('temp')?'any':'1';wrapper.append(input);fields.append(wrapper);inputs[key]=input;}
 function rebuild(){fields.replaceChildren();for(const k of Object.keys(inputs))delete inputs[k];field('name','Geraetename','','text');field('id',category.value==='thermostats'?'Sollwert-ID':'Geraete-ID',endpoint[0]);field('statetype','Statetype',endpoint[1]);if(category.value==='contacts'){const label=node('label','Kontaktart'),select=node('select','');for(const [value,name] of [['door','Tuer'],['window','Fenster'],['garage_door','Garagentor']]){const o=node('option',name);o.value=value;select.append(o);}label.append(select);fields.append(label);inputs.device_class=select;}if(category.value==='thermostats'){field('current_id','Ist-Temperatur ID','');field('current_statetype','Ist-Temperatur Statetype','');field('mode_id','Heizmodus ID','');field('mode_statetype','Heizmodus Statetype','');field('min_temp','Minimum Celsius',16);field('max_temp','Maximum Celsius',26);field('temp_step','Sollwert-Schritt',0.5);}const semantics=node('p',category.value==='shutters'?'Legacy: 1=Auf, 2=Ab, 0=Stopp. Statetype wird auch fuer Befehle verwendet. Keine Prozentkalibrierung.':category.value==='thermostats'?'Nur Heizen/Aus: Modus 1/0. IDs und Statetypes anhand der Mitschnitte bestaetigen.':'Bestehende Bridge-Semantik: Werte >= 0.5 sind EIN/aktiv, kleinere Werte AUS/inaktiv. Keine frei konfigurierbare Invertierung.');fields.append(semantics);invalidate();}
 function invalidate(){revision++;validated=null;save.disabled=true;result.textContent='';setText(message,'');}
 async function request(path,body){const r=await fetch(`api/drafts/${path}`,{method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':data.draft_token},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)}).catch(()=>{throw Error('request_error');});const answer=await r.json().catch(()=>{throw Error('request_error');});if(!r.ok)throw Error(answer.error||'Anfrage fehlgeschlagen');return answer;}
 form.oninput=invalidate;category.onchange=rebuild;
 form.onsubmit=async e=>{e.preventDefault();invalidate();const currentRevision=revision;const payload={category:category.value};for(const [key,input] of Object.entries(inputs))payload[key]=input.type==='number'?Number(input.value):input.value;check.disabled=true;try{const answer=await request('validate',payload);if(revision!==currentRevision)return;validated=payload;result.textContent=JSON.stringify(answer.draft,null,2);setText(message,data.draft_saving?'Geprueft. Speichern legt nur eine separate Entwurfsdatei an.':'Geprueft. In der Testvorschau ist Speichern deaktiviert.');save.disabled=!data.draft_saving;}catch(error){if(revision===currentRevision)setText(message,error.message);}finally{check.disabled=false;}};
 save.onclick=async()=>{if(!validated)return;save.disabled=true;try{const answer=await request('save',validated);setText(message,`Gespeichert: ${answer.filename}. Noch NICHT aktiv.`);validated=null;}catch(error){setText(message,error.message);save.disabled=false;}};
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());
 form.append(category,fields,check,save);dialog.append(title,hint,form,result,message,close);document.body.append(dialog);rebuild();dialog.showModal();
}
