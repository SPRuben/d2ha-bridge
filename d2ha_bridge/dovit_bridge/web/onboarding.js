'use strict';
const setupKeys=['dovit_host','dovit_port','mqtt_mode','mqtt_host','mqtt_port','mqtt_user','mqtt_tls','mqtt_protocol','publish_discovery'];
let wizardRevision=null,wizardStep=0,wizardBusy=false,wizardLoaded=false,wizardDirty=false,wizardPending=false,wizardSimulation=false,wizardDamaged=false,wizardStorageBlocked=false,wizardAutomaticDiscovery=null;
let workspaceView='devices';
const selectEditorView=selectView;
$('advanced-editor-slot').append($('json-panel'));
function renderWorkspaceHeading(){
 setText($('workspace-title'),workspaceView==='devices'?'main_title':workspaceView==='setup'?'main_setup_title':'main_diagnosis_title');
 setText($('workspace-subtitle'),workspaceView==='devices'?'main_subtitle':workspaceView==='setup'?'main_setup_subtitle':'main_diagnosis_subtitle');
}
function goWorkspace(view){
 if(!['devices','setup','diagnosis'].includes(view))return;
 workspaceView=view;
 $('graphic-panel').hidden=view!=='devices';
 $('onboarding-panel').hidden=view!=='setup';
 $('diagnosis-panel').hidden=view!=='diagnosis';
 $('control-notice').hidden=view==='setup';
 renderWorkspaceHeading();
 for(const key of ['devices','setup','diagnosis']){
  const button=$('nav-'+key);
  if(view===key)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
 }
 if(view==='diagnosis'&&$('diagnosis-advanced').open)selectEditorView('json');
}
// The advanced editor keeps its draft; returning targets the visible main navigation.
selectView=function(view){
 if(!['graphic','json'].includes(view))return;
 if(view==='json')$('diagnosis-advanced').open=true;
 if(view==='graphic')selectEditorView(view);
 goWorkspace(view==='json'?'diagnosis':'devices');
};
for(const key of ['devices','setup','diagnosis'])$('nav-'+key).onclick=()=>{
 if(key==='devices')selectView('graphic');else goWorkspace(key);
};
$('setup-go-devices').onclick=()=>{selectView('graphic');$('nav-devices').focus();};
$('json-return').onclick=()=>{selectView('graphic');$('nav-devices').focus();};
$('diagnosis-advanced').addEventListener('toggle',()=>{
 if($('diagnosis-advanced').open&&workspaceView==='diagnosis')selectEditorView('json');
});
$('empty-setup').onclick=()=>{goWorkspace('setup');$('nav-setup').focus();};
$('empty-help').onclick=()=>$('help-open').click();
function setupErrorKey(error){
 const keys={setup_stale:'wizard_conflict',setup_invalid_host:'wizard_invalid_host',setup_invalid_port:'wizard_invalid_port',
  setup_recovery_confirm:'wizard_recovery_required',setup_storage_error:'wizard_storage_error',setup_conflict:'wizard_conflict',revision_conflict:'wizard_conflict',setup_invalid:'wizard_invalid',
  invalid_settings:'wizard_invalid',setup_disabled:'wizard_disabled',invalid_token:'wizard_token'};
 return typeof error==='string'&&Object.hasOwn(keys,error)?keys[error]:'wizard_error';
}
function readSetupSettings(){
 return Object.fromEntries(setupKeys.map(key=>{
  const input=$('setting-'+key);
  return [key,input.type==='checkbox'?input.checked:key.endsWith('_port')?Number(input.value):input.value];
 }));
}
function setupPayload(){
 const payload={revision:wizardRevision,settings:readSetupSettings(),confirm:true};
 const password=$('setting-mqtt_pass').value;
 if(password&&payload.settings.mqtt_mode==='manual')payload.mqtt_pass=password;
 if(wizardDamaged&&$('wizard-recovery-confirm').checked)payload.confirm_recovery=true;
 return payload;
}
function renderWizardReview(){
 const review=$('wizard-review');review.replaceChildren();
 const settings=readSetupSettings();
 for(const key of setupKeys){
  if(settings.mqtt_mode==='supervisor'&&key.startsWith('mqtt_')&&key!=='mqtt_mode')continue;
  const label=node('dt','field_'+key),value=node('dd','');
  value.textContent=key==='mqtt_mode'?t(settings[key]==='supervisor'?'wizard_supervisor':'wizard_manual'):
   typeof settings[key]==='boolean'?t(settings[key]?'wizard_yes':'wizard_no'):String(settings[key]);
  review.append(label,value);
 }
 const add=(label,value)=>review.append(node('dt',label),node('dd',value));
 add('wizard_automatic_setting',wizardAutomaticDiscovery===null?'wizard_automatic_unknown':wizardAutomaticDiscovery?'wizard_yes':'wizard_no');
 const publication=settings.publish_discovery||wizardAutomaticDiscovery===true?'wizard_publication_planned':
  wizardAutomaticDiscovery===false?'wizard_publication_off':'wizard_publication_unknown';
 add('wizard_publication_result',publication);
 add('wizard_ha_result','setup_ha_unverified');
}
function refreshWizard(){
 document.querySelectorAll('[data-wizard-step]').forEach(el=>{el.hidden=Number(el.dataset.wizardStep)!==wizardStep;});
 document.querySelectorAll('[data-step]').forEach(el=>{
  if(Number(el.dataset.step)===wizardStep)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');
 });
 $('mqtt-manual').hidden=$('setting-mqtt_mode').value!=='manual';
 for(const key of ['mqtt_host','mqtt_port'])$('setting-'+key).required=$('setting-mqtt_mode').value==='manual';
 $('wizard-back').disabled=wizardStep===0||wizardBusy;
 $('wizard-next').hidden=wizardStep===3;
 $('wizard-next').disabled=!wizardLoaded||wizardBusy||wizardStorageBlocked;
 $('wizard-save').hidden=wizardStep!==3;
 $('wizard-save').disabled=!wizardLoaded||wizardBusy||wizardPending||wizardStorageBlocked||!$('wizard-confirm').checked
  ||wizardDamaged&&!$('wizard-recovery-confirm').checked;
 $('wizard-damaged-warning').hidden=!wizardDamaged&&!wizardStorageBlocked;
 setText($('wizard-damaged-warning'),wizardStorageBlocked?'wizard_storage_blocked':'wizard_damaged_warning');
 $('wizard-recovery-consent').hidden=!wizardDamaged||wizardStorageBlocked;
 $('wizard-reload').disabled=wizardBusy;
 // Lock settings during a request and after staging, without replacing focused inputs on polling.
 for(const key of [...setupKeys,'mqtt_pass'])$('setting-'+key).disabled=!wizardLoaded||wizardBusy||wizardPending||wizardStorageBlocked;
 $('wizard-confirm').disabled=!wizardLoaded||wizardBusy||wizardPending||wizardStorageBlocked;
 $('wizard-recovery-confirm').disabled=!wizardDamaged||!wizardLoaded||wizardBusy||wizardPending||wizardStorageBlocked;
 if(wizardStep===3)renderWizardReview();
}
async function loadSetup(){
 if(wizardBusy||wizardDirty&&!window.confirm(t('wizard_discard')))return;
 wizardBusy=true;refreshWizard();
 try{
  const response=await fetch('api/setup',{cache:'no-store',signal:AbortSignal.timeout(5000)});
  if(!response.ok)throw Error('wizard_error');
  const snapshot=await response.json();
  const storageBlocked=snapshot.writable===false&&snapshot.storage_error==='setup_storage_error'&&snapshot.revision===null;
  if(!storageBlocked&&typeof snapshot.revision!=='string'||snapshot.writable!==undefined&&typeof snapshot.writable!=='boolean'
   ||snapshot.writable===false&&!storageBlocked||snapshot.damaged!==undefined&&typeof snapshot.damaged!=='boolean'
   ||snapshot.automatic_discovery!==undefined&&typeof snapshot.automatic_discovery!=='boolean'||!snapshot.settings||setupKeys.some(key=>
   typeof snapshot.settings[key]!==(['mqtt_tls','publish_discovery'].includes(key)?'boolean':key.endsWith('_port')?'number':'string'))
   ||!['manual','supervisor'].includes(snapshot.settings.mqtt_mode)||!['3.1','3.1.1','5'].includes(snapshot.settings.mqtt_protocol))throw Error('wizard_error');
  for(const key of setupKeys){const input=$('setting-'+key);if(input.type==='checkbox')input.checked=snapshot.settings[key];else input.value=snapshot.settings[key];}
  // Never copy a password or arbitrary server fields into the form or diagnostics.
  $('setting-mqtt_pass').value='';$('wizard-confirm').checked=false;$('wizard-recovery-confirm').checked=false;
  wizardRevision=snapshot.revision;wizardPending=snapshot.pending===true;wizardSimulation=snapshot.simulation===true;
  wizardDamaged=snapshot.damaged===true;
  wizardStorageBlocked=storageBlocked;
  wizardAutomaticDiscovery=typeof snapshot.automatic_discovery==='boolean'?snapshot.automatic_discovery:null;
  $('wizard-simulation').hidden=!wizardSimulation;
  wizardLoaded=true;wizardDirty=false;
  setText($('wizard-password-state'),storageBlocked?'wizard_password_unknown':snapshot.password_set===true?'wizard_password_set':'wizard_password_unset');
  setText($('wizard-status'),storageBlocked?'wizard_storage_error':wizardPending?'wizard_pending':'wizard_loaded');
  if(storageBlocked)goWorkspace('setup');
 }catch{wizardLoaded=false;wizardAutomaticDiscovery=null;setText($('wizard-status'),'wizard_error');}
 finally{wizardBusy=false;refreshWizard();}
}
$('onboarding-form').addEventListener('input',()=>{
 wizardDirty=true;$('wizard-confirm').checked=false;$('wizard-recovery-confirm').checked=false;setText($('wizard-status'),'wizard_draft');refreshWizard();
});
$('setting-mqtt_mode').addEventListener('change',refreshWizard);
$('wizard-confirm').addEventListener('input',event=>{event.stopPropagation();refreshWizard();});
$('wizard-recovery-confirm').addEventListener('input',event=>{event.stopPropagation();refreshWizard();});
$('wizard-back').onclick=()=>{if(!wizardBusy&&wizardStep>0){wizardStep--;refreshWizard();$('wizard-next').focus();}};
function wizardStepValid(){
 const fields=wizardStep===0?['dovit_host','dovit_port']:
  wizardStep===1&&$('setting-mqtt_mode').value==='manual'?['mqtt_host','mqtt_port']:[];
 for(const key of fields){
  const input=$('setting-'+key);
  if(!input.disabled&&typeof input.reportValidity==='function'&&!input.reportValidity())return false;
 }
 return true;
}
$('wizard-next').onclick=()=>{
 if(wizardLoaded&&!wizardBusy&&!wizardStorageBlocked&&wizardStep<3&&wizardStepValid()){
  wizardStep++;refreshWizard();(wizardStep===3?$('wizard-confirm'):$('wizard-back')).focus();
 }
};
$('wizard-reload').onclick=loadSetup;
$('onboarding-form').addEventListener('submit',async event=>{
 event.preventDefault();
 if(wizardStep!==3||!wizardLoaded||wizardBusy||wizardPending||wizardStorageBlocked||!$('wizard-confirm').checked
  ||wizardDamaged&&!$('wizard-recovery-confirm').checked)return;
 if(typeof data?.draft_token!=='string'||!data.draft_token){setText($('wizard-status'),'wizard_token');return;}
 const body=JSON.stringify(setupPayload());
 if(new TextEncoder().encode(body).byteLength>8192){
  $('wizard-confirm').checked=false;$('wizard-recovery-confirm').checked=false;setText($('wizard-status'),'wizard_body_too_large');refreshWizard();return;
 }
 wizardBusy=true;refreshWizard();
 try{
  const response=await fetch('api/setup',{method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':data.draft_token},
   body,signal:AbortSignal.timeout(5000)});
  const answer=await response.json();
  if(!response.ok){
   const key=response.status===409?'wizard_conflict':setupErrorKey(answer.error);
   if(key==='wizard_conflict'||key==='wizard_recovery_required')wizardLoaded=false;
   setText($('wizard-status'),key);return;
  }
  if(answer.pending!==true||typeof answer.revision!=='string')throw Error();
  wizardRevision=answer.revision;wizardPending=true;wizardDirty=false;wizardDamaged=false;
  setText($('wizard-status'),'wizard_pending');
 }catch{
  // A timeout may follow a successful atomic save. Require a read before another write.
  wizardLoaded=false;setText($('wizard-status'),'wizard_uncertain');
 }finally{$('setting-mqtt_pass').value='';$('wizard-confirm').checked=false;$('wizard-recovery-confirm').checked=false;wizardBusy=false;refreshWizard();}
});
$('language').addEventListener('change',()=>{renderWorkspaceHeading();if(wizardStep===3)renderWizardReview();});
window.addEventListener('beforeunload',event=>{if(wizardDirty){event.preventDefault();event.returnValue='';}});
goWorkspace('devices');loadSetup();
