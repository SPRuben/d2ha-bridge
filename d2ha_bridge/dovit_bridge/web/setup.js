'use strict';
let setupInitiallyRendered=false;
document.getElementById('setup-help').addEventListener('click',()=>document.getElementById('help-open').click());

function setupModel(snapshot,online){
 const simulation=snapshot?.light_control==='simulation'||snapshot?.device_control==='simulation';
 const known=(snapshot?.devices||[]).filter(device=>device.category!=='clocks');
 const assigned=known.filter(device=>device.classification==='confirmed');
 const assignmentsKnown=known.every(device=>['confirmed','inferred'].includes(device.classification));
 const status=snapshot?.setup;
 const mqtt=typeof status?.mqtt_connected==='boolean'?status.mqtt_connected:null;
 const publishing=typeof status?.discovery_publishing==='boolean'?status.discovery_publishing:null;
 const automatic=status?.automatic_discovery===true;
 const state=value=>!online||simulation?'unknown':value===null?'unknown':value?'good':'attention';
 const dovit=online&&typeof snapshot?.connected==='boolean'?snapshot.connected:null;
 let next='setup_next_ha';
 if(!online)next='setup_next_offline';
 else if(simulation)next='setup_next_simulation';
 else if(dovit!==true)next='setup_next_dovit';
 else if(mqtt===false)next='setup_next_mqtt';
 else if(mqtt===null)next='setup_next_unknown';
 else if(!assignmentsKnown)next='setup_next_unknown';
 else if(!assigned.length)next='setup_next_devices';
 else if(publishing===false)next='setup_next_publish';
 else if(publishing===null)next='setup_next_unknown';
 return {
  empty:known.length===0,
  overview:!online?'setup_overview_offline':simulation?'setup_overview_simulation':
   dovit===true&&mqtt===true?'setup_overview_connected':'setup_overview_attention',
  dovit:{state:state(dovit),label:online&&simulation?'ui_demo_status':!online||dovit===null?'setup_unverified':dovit?'setup_connected':'setup_disconnected'},
  mqtt:{state:state(mqtt),label:online&&simulation?'setup_unverified':!online||mqtt===null?'setup_unverified':mqtt?'setup_connected':'setup_disconnected'},
  devices:{state:!online||!assignmentsKnown?'unknown':assigned.length?'good':'attention',label:!online||!assignmentsKnown?'setup_unverified':assigned.length?'setup_devices_present':'setup_devices_missing'},
  publishing:{state:state(publishing),label:!online||publishing===null?'setup_unverified':publishing?'setup_publish_on':'setup_publish_off'},
  automatic:online&&automatic, next,
  ha:{state:'unknown',label:'setup_ha_unverified'}
 };
}

function renderSetup(){
 const panel=$('setup-panel');if(!panel)return;
 const model=setupModel(data,apiOnline);
 const empty=$('empty-inventory');
 if(empty)empty.hidden=!(apiOnline&&data?.inventory_configured===true&&Array.isArray(data?.devices)&&model.empty);
 // Auto-open only once for genuinely empty runtime inventories; never change a user's disclosure.
 if(!setupInitiallyRendered&&data&&apiOnline){panel.open=model.empty;setupInitiallyRendered=true;}
 for(const key of ['dovit','mqtt','devices','publishing','ha']){
  const element=$('setup-'+key+'-status');
  element.dataset.state=model[key].state;
  const text=t(model[key].label);if(element.textContent!==text)element.textContent=text;
 }
 for(const [id,key] of [['setup-overview',model.overview],['setup-next',model.next]]){
  const element=$(id),text=t(key);if(element.textContent!==text)element.textContent=text;
 }
 $('setup-automatic').hidden=!model.automatic;
 renderDiagnosis();
}

function diagnosisModel(snapshot,online){
 const status=snapshot?.setup;
 if(!online)return {guidance:snapshot?'diagnosis_stale':'diagnosis_offline',mode:null,changed:null};
 if(snapshot?.simulation===true||snapshot?.device_control==='simulation'||snapshot?.light_control==='simulation')
  return {guidance:'diagnosis_simulation',mode:null,changed:null};
 const errors={mqtt_credentials:'diagnosis_credentials',mqtt_unavailable:'diagnosis_mqtt',
  supervisor_unavailable:'diagnosis_supervisor',mqtt_supervisor_token_missing:'diagnosis_supervisor_token',
  mqtt_supervisor_token_invalid:'diagnosis_supervisor_token',mqtt_supervisor_auth_rejected:'diagnosis_supervisor_auth',
  mqtt_service_unavailable:'diagnosis_service',mqtt_service_timeout:'diagnosis_service',
  mqtt_service_invalid_response:'diagnosis_service_response',mqtt_service_response_too_large:'diagnosis_service_response',
  mqtt_invalid_config:'diagnosis_configuration',invalid_configuration:'diagnosis_configuration',setup_storage_error:'wizard_storage_error'};
 const error=status?.configuration_error;
 let guidance='diagnosis_unknown';
 if(error)guidance=typeof error==='string'&&Object.hasOwn(errors,error)?errors[error]:'diagnosis_configuration';
 else if(status?.mqtt_state==='auth_rejected')guidance='diagnosis_credentials';
 else if(status?.mqtt_state==='rejected')guidance='diagnosis_rejected';
 else if(status?.mqtt_state==='unreachable')guidance='diagnosis_mqtt';
 else if(status?.mqtt_state==='connecting')guidance='diagnosis_connecting';
 else if(status?.mqtt_state==='stopped')guidance='diagnosis_stopped';
 else if(status?.dovit_state==='disconnected'||status?.dovit_state==='offline')guidance='diagnosis_dovit';
 else if(status?.mqtt_state==='disconnected'||status?.mqtt_state==='offline'||status?.mqtt_connected===false)guidance='diagnosis_mqtt';
 else if(status?.mqtt_connected===true&&status?.discovery_publishing===false)guidance='diagnosis_publication';
 else if(status?.mqtt_connected===true&&status?.discovery_publishing===true)guidance='diagnosis_ready';
 const changed=typeof status?.mqtt_changed_at==='string'||typeof status?.mqtt_changed_at==='number'?status.mqtt_changed_at:null;
 return {guidance,mode:status?.mqtt_mode==='supervisor'?'diagnosis_mode_supervisor':status?.mqtt_mode==='manual'?'diagnosis_mode_manual':null,changed};
}
function renderDiagnosis(){
 const target=$('diagnosis-guidance');if(!target)return;
 const model=diagnosisModel(data,apiOnline);
 const feedback=$('wizard-current-feedback');if(feedback)setText(feedback,model.guidance);
 const runtime=$('wizard-runtime');if(runtime)runtime.hidden=model.guidance==='diagnosis_simulation';
 setText(target,model.guidance);
 const mode=$('diagnosis-mode');mode.hidden=model.mode===null;
 if(model.mode!==null)setText(mode,model.mode);
 else {mode.textContent='';delete mode.dataset.i18n;}
 const stamp=typeof model.changed==='number'&&Math.abs(model.changed)<1e12?model.changed*1000:model.changed;
 const changed=stamp===null?null:new Date(stamp);
 $('diagnosis-changed').textContent=changed&&!Number.isNaN(changed.getTime())?t('diagnosis_changed')+' '+changed.toLocaleString(language==='fr'?'fr-FR':'de-DE'):'';
}
