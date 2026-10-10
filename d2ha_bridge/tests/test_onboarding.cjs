// Synthetic contract fixture only: no server, broker, socket or physical device.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const web=path.join(__dirname,'../dovit_bridge/web');
class Element{
 constructor(){this.dataset={};this.value='';this.checked=false;this.type='text';this.children=[];this.handlers={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 setAttribute(key,value){this[key]=value;}
 removeAttribute(key){delete this[key];}
 addEventListener(key,handler){(this.handlers[key]??=[]).push(handler);}
 async fire(key,event={}){for(const handler of this.handlers[key]||[])await handler({preventDefault(){},stopPropagation(){},...event});}
 focus(){document.activeElement=this;}
}
const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
const css=fs.readFileSync(path.join(web,'style.css'),'utf8');
const source=fs.readFileSync(path.join(web,'onboarding.js'),'utf8');
const catalog=fs.readFileSync(path.join(web,'i18n.js'),'utf8');
const ids=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(match=>[match[1],new Element()]));
for(const key of ['dovit_port','mqtt_port'])ids['setting-'+key].type='number';
for(const key of ['mqtt_tls','publish_discovery'])ids['setting-'+key].type='checkbox';
const steps=Array.from({length:4},(_,i)=>Object.assign(new Element(),{dataset:{wizardStep:String(i)}}));
const progress=Array.from({length:4},(_,i)=>Object.assign(new Element(),{dataset:{step:String(i)}}));
const document={activeElement:null,getElementById:id=>ids[id],querySelectorAll:key=>key==='[data-wizard-step]'?steps:progress};
const calls=[],window={confirm:()=>true,addEventListener(){}};
const settings={dovit_host:'dovit.local',dovit_port:4000,mqtt_mode:'supervisor',mqtt_host:'broker',mqtt_port:1883,
 mqtt_user:'user',mqtt_tls:false,mqtt_protocol:'3.1.1',publish_discovery:false};
let reply={revision:'rev-1',settings,password_set:true,pending:false,simulation:true,mqtt_pass:'NEVER COPY THIS'};
let status=200,fail=false,views=[];
const context=vm.createContext({document,window,AbortSignal:{timeout:()=>undefined},TextEncoder:require('node:util').TextEncoder,console,Object,Date,
 $:id=>ids[id],t:key=>key,setText:(el,key)=>{el.dataset.i18n=key;el.textContent=key;},node:(tag,key)=>Object.assign(new Element(),{tagName:tag.toUpperCase(),textContent:key}),
 data:{draft_token:'session-token'},apiOnline:true,language:'de',recordView:view=>views.push(view),
 fetch:async(url,options)=>{calls.push({url,options});if(fail)throw Error('secret error');return {ok:status===200,status,json:async()=>reply};}});
const run=code=>vm.runInContext(code,context);
run('function selectView(view){recordView(view);}');
vm.runInContext(fs.readFileSync(path.join(web,'setup.js'),'utf8'),context);
vm.runInContext(source,context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function assertStepState(step){
 assert.equal(run('wizardStep'),step);
 for(let i=0;i<4;i++){
  assert.equal(steps[i].hidden,i!==step);
  assert.equal(progress[i]['aria-current'],i===step?'step':undefined);
 }
 assert.equal(ids['wizard-back'].disabled,step===0);
 assert.equal(ids['wizard-next'].hidden,step===3);
 assert.equal(ids['wizard-save'].hidden,step!==3);
}
(async()=>{
 assert.equal(run('wizardLoaded'),false);assert.equal(run('wizardBusy'),true);
 for(const action of ['back','next','save','reload'])assert.equal(ids['wizard-'+action].disabled,true,'Loading locks '+action);
 await flush();assert.equal(calls.length,1);assert.equal(calls[0].url,'api/setup');
 assert.equal(ids['setting-mqtt_pass'].value,'');assert.equal(ids['wizard-status'].textContent,'wizard_loaded');
 assert.equal(run('wizardSimulation'),true);assert.equal(ids['wizard-simulation'].hidden,false);
 assert.equal(run('wizardDirty'),false);assertStepState(0);
 assert.equal(ids['wizard-next'].disabled,false);assert.equal(ids['wizard-save'].disabled,true);assert.equal(ids['wizard-reload'].disabled,false);
 context.data.simulation=true;run('renderDiagnosis()');
 assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_simulation');
 assert.equal(ids['wizard-status'].textContent,'wizard_loaded','Runtime simulation does not replace draft state');
 delete context.data.simulation;context.data.setup={mqtt_state:'auth_rejected',mqtt_connected:false};run('renderDiagnosis()');
 assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_credentials','Actual runtime errors stay available');
 ids['wizard-current-details'].open=false;run('refreshWizard()');
 assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_credentials','Collapsed explanation does not replace runtime errors');
 assert.notEqual(ids['wizard-current-feedback'].hidden,true);
 assert.equal(ids['wizard-current-details'].open,false);
 assert.equal(ids['wizard-damaged-warning'].hidden,true,'Legacy snapshot without damaged remains normal');
 assert.equal(ids['wizard-recovery-consent'].hidden,true);
 assert.equal(ids['graphic-panel'].hidden,false);assert.equal(ids['diagnosis-panel'].hidden,true);
 assert.equal(ids['workspace-title'].dataset.i18n,'main_title');assert.equal(ids['workspace-subtitle'].dataset.i18n,'main_subtitle');
 ids['nav-setup'].onclick();
 assert.equal(ids['workspace-title'].dataset.i18n,'main_setup_title');assert.equal(ids['workspace-subtitle'].dataset.i18n,'main_setup_subtitle');
 assert.equal(ids['control-notice'].hidden,true,'Setup has its own central safety warning');
 assert.equal(ids['wizard-simulation'].hidden,false,'Isolated simulation warning remains visible');
 const validityCalls=[];
 for(const key of ['dovit_host','dovit_port','mqtt_host','mqtt_port']){
  ids['setting-'+key].nativeValid=true;
  ids['setting-'+key].reportValidity=function(){validityCalls.push(key);return this.nativeValid;};
 }
 ids['setting-dovit_host'].nativeValid=false;ids['wizard-next'].onclick();
 assert.equal(run('wizardStep'),0,'Required Dovit host blocks Next');assert.deepEqual(validityCalls,['dovit_host']);
 ids['setting-dovit_host'].nativeValid=true;ids['setting-dovit_port'].nativeValid=false;
 ids['wizard-next'].onclick();assert.equal(run('wizardStep'),0,'Invalid Dovit port blocks Next');
 ids['setting-dovit_port'].nativeValid=true;ids['wizard-next'].onclick();assertStepState(1);
 ids['setting-mqtt_mode'].value='manual';await ids['setting-mqtt_mode'].fire('change');
 assert.equal(ids['setting-mqtt_host'].required,true);assert.equal(ids['setting-mqtt_port'].required,true);
 ids['setting-mqtt_host'].nativeValid=false;ids['wizard-next'].onclick();assert.equal(run('wizardStep'),1,'Required manual host blocks Next');
 ids['setting-mqtt_host'].nativeValid=true;ids['setting-mqtt_port'].nativeValid=false;
 ids['wizard-next'].onclick();assert.equal(run('wizardStep'),1,'Invalid manual MQTT port blocks Next');
 ids['setting-mqtt_port'].nativeValid=true;ids['wizard-next'].onclick();assert.equal(run('wizardStep'),2,'Valid manual host/port permit Next');
 run('wizardStep=1;refreshWizard()');ids['setting-mqtt_port'].nativeValid=false;
 const supervisorChecks=validityCalls.length;
 ids['setting-mqtt_mode'].value='supervisor';await ids['setting-mqtt_mode'].fire('change');
 assert.equal(ids['setting-mqtt_host'].required,false);assert.equal(ids['setting-mqtt_port'].required,false);
 ids['wizard-next'].onclick();assert.equal(run('wizardStep'),2,'Supervisor opt-in skips hidden manual fields');
 assert.equal(validityCalls.length,supervisorChecks);assert.equal(calls.length,1,'All native checks are local');
 ids['setting-mqtt_port'].nativeValid=true;
 run('wizardStep=0;refreshWizard()');
 for(let i=0;i<3;i++)ids['wizard-next'].onclick();
 assertStepState(3);assert.equal(ids['wizard-save'].disabled,true);
 ids['wizard-confirm'].checked=true;await ids['wizard-confirm'].fire('input');assert.equal(ids['wizard-save'].disabled,false);
 assert.equal(run('wizardDirty'),false,'Consent alone does not change the settings draft');
 ids['wizard-confirm'].checked=false;await ids['wizard-confirm'].fire('input');assert.equal(ids['wizard-save'].disabled,true);
 assert.equal(calls.length,1,'Next is entirely local');
 await ids['onboarding-form'].fire('submit');assert.equal(calls.length,1,'No save without consent');
 const reviewValue=key=>{
  const children=ids['wizard-review'].children,index=children.findIndex(child=>child.textContent===key);
  assert.notEqual(index,-1,'Review label exists: '+key);return children[index+1].textContent;
 };
 assert.equal(reviewValue('wizard_automatic_setting'),'wizard_automatic_unknown','Older API cannot imply automatic search is off');
 assert.equal(reviewValue('wizard_publication_result'),'wizard_publication_unknown');
 for(const automatic of [false,true])for(const publish of [false,true]){
  reply={revision:'rev-1',settings:{...settings,publish_discovery:publish},automatic_discovery:automatic,password_set:true,pending:false,simulation:true};
  await run('loadSetup()');
  assert.equal(reviewValue('field_publish_discovery'),publish?'wizard_yes':'wizard_no','User selection remains distinct');
  assert.equal(reviewValue('wizard_automatic_setting'),automatic?'wizard_yes':'wizard_no','Read-only discovery is shown separately');
  assert.equal(reviewValue('wizard_publication_result'),automatic||publish?'wizard_publication_planned':'wizard_publication_off');
  assert.equal(reviewValue('wizard_ha_result'),'setup_ha_unverified','Planned publication is not HA uptake');
  assert.equal(Object.hasOwn(run('setupPayload()').settings,'enable_discovery'),false);
  assert.equal(Object.hasOwn(run('setupPayload()').settings,'automatic_discovery'),false);
 }
 reply={revision:'rev-1',settings:{...settings,publish_discovery:true},password_set:true,pending:false};await run('loadSetup()');
 assert.equal(reviewValue('wizard_publication_result'),'wizard_publication_planned','Explicit publishing is sufficient without inventing automatic discovery');
 reply={revision:'rev-1',settings,automatic_discovery:'false'};await run('loadSetup()');
 assert.equal(run('wizardLoaded'),false,'Malformed read-only discovery fails closed');
 reply={revision:'rev-1',settings,password_set:true,pending:false,simulation:true};await run('loadSetup()');
 ids['setting-dovit_host'].value='draft.local';
 await ids['onboarding-form'].fire('input');assert.equal(ids['wizard-confirm'].checked,false);
 assert.equal(ids['wizard-status'].textContent,'wizard_draft');assert.equal(run('wizardDirty'),true);
 assert.equal(ids['wizard-simulation'].hidden,false,'Draft status does not remove the central simulation warning');
 ids['setting-mqtt_pass'].value='draft-password';window.confirm=()=>false;
 const beforeDiscard=calls.length;await run('loadSetup()');
 assert.equal(calls.length,beforeDiscard,'Declining discard does not reload');assert.equal(run('wizardRevision'),'rev-1');
 assert.equal(ids['setting-dovit_host'].value,'draft.local');assert.equal(ids['setting-mqtt_pass'].value,'draft-password');
 assert.equal(ids['wizard-status'].textContent,'wizard_draft');window.confirm=()=>true;
 ids['language'].value='fr';await ids.language.fire('change');
 assert.equal(ids['setting-dovit_host'].value,'draft.local','Language preserves draft');
 assert.equal(ids['setting-mqtt_pass'].value,'draft-password','Language preserves the unsubmitted password');
 assert.equal(ids['wizard-status'].dataset.i18n,'wizard_draft','Draft status remains translatable');
 ids['setup-go-devices'].onclick();assert.equal(ids['graphic-panel'].hidden,false);
 assert.equal(ids['control-notice'].hidden,false,'Device controls retain their safety warning');
 ids['nav-setup'].onclick();assert.equal(ids['setting-dovit_host'].value,'draft.local');
 run("selectView('json')");assert.equal(ids['diagnosis-panel'].hidden,false);assert.equal(ids['diagnosis-advanced'].open,true);
 assert.equal(ids['workspace-title'].dataset.i18n,'main_diagnosis_title');assert.equal(ids['workspace-subtitle'].dataset.i18n,'main_diagnosis_subtitle');
 assert.equal(ids['graphic-panel'].hidden,true);assert.equal(views.at(-1),'json');
 assert.ok(ids['advanced-editor-slot'].children.includes(ids['json-panel']));
 ids['json-return'].onclick();assert.equal(document.activeElement,ids['nav-devices'],'JSON return focuses visible navigation');
 assert.equal(ids['graphic-panel'].hidden,false);assert.equal(ids['diagnosis-panel'].hidden,true);
 assert.equal(ids['nav-devices']['aria-current'],'page');assert.equal(ids['workspace-title'].dataset.i18n,'main_title');
 ids['empty-setup'].onclick();assert.equal(document.activeElement,ids['nav-setup']);
 assert.equal(ids['onboarding-panel'].hidden,false);assert.equal(ids['setting-dovit_host'].value,'draft.local','Empty-state CTA preserves the local draft');
 ids['nav-diagnosis'].onclick();assert.equal(ids['diagnosis-panel'].hidden,false);assert.equal(views.at(-1),'json','Reopening diagnosis retains advanced editor navigation');
 await ids.language.fire('change');assert.equal(ids['workspace-title'].dataset.i18n,'main_diagnosis_title','Language does not reset workspace title');
 for(const value of ['secret server string','constructor','toString','__proto__']){
  context.error=value;assert.equal(run('setupErrorKey(error)'),'wizard_error');
 }
 assert.equal(run("setupErrorKey('setup_conflict')"),'wizard_conflict');
 reply={error:'secret password details'};status=400;ids['wizard-confirm'].checked=true;
 await ids['onboarding-form'].fire('submit');
 assert.equal(ids['wizard-status'].textContent,'wizard_error');assert.equal(ids['wizard-confirm'].checked,false);
 const payload=JSON.parse(calls.at(-1).options.body);
 assert.equal(payload.revision,'rev-1');assert.equal(payload.confirm,true);assert.equal(payload.settings.publish_discovery,false);
 assert.equal(Object.hasOwn(payload,'mqtt_pass'),false);assert.equal(calls.at(-1).options.headers['X-Dovit-Token'],'session-token');
 assert.equal(Object.hasOwn(payload,'confirm_recovery'),false,'Normal save does not send recovery consent');
 assert.deepEqual(Object.keys(payload.settings),Object.keys(settings));
 status=409;ids['wizard-confirm'].checked=true;await ids['onboarding-form'].fire('submit');
 assert.equal(ids['wizard-status'].textContent,'wizard_conflict');
 assert.equal(run('wizardLoaded'),false,'Conflict requires a fresh read');
 reply={revision:'rev-staged',settings,password_set:true,pending:true,simulation:true};status=200;await run('loadSetup()');
 assert.equal(ids['wizard-status'].textContent,'wizard_pending','Staged simulation shows pending, not a duplicate warning');
 assert.equal(ids['wizard-simulation'].hidden,false);assert.equal(ids['wizard-save'].disabled,true);
 for(const key of Object.keys(settings))assert.equal(ids['setting-'+key].disabled,true,'Pending settings remain locked: '+key);
 reply={revision:'rev-1',settings,password_set:true,pending:false,simulation:true};status=200;await run('loadSetup()');
 for(const protocol of ['3.1','3.1.1','5']){
  reply={revision:'rev-1',settings:{...settings,mqtt_protocol:protocol},password_set:true,pending:false};
  await run('loadSetup()');assert.equal(run('wizardLoaded'),true);assert.equal(ids['setting-mqtt_protocol'].value,protocol);
  assert.equal(ids['wizard-status'].textContent,'wizard_loaded');assert.equal(ids['wizard-simulation'].hidden,true,'Normal runtime hides simulation warning');
 }
 for(const [error,key] of Object.entries({setup_invalid_host:'wizard_invalid_host',setup_invalid_port:'wizard_invalid_port',setup_storage_error:'wizard_storage_error',setup_stale:'wizard_conflict'})){
  reply={error};status=400;ids['wizard-confirm'].checked=true;
  await ids['onboarding-form'].fire('submit');assert.equal(ids['wizard-status'].textContent,key);
  assert.equal(ids['wizard-confirm'].checked,false);
 }
 assert.equal(run('wizardLoaded'),false,'HTTP 400 setup_stale requires fresh settings');
 const staleCalls=calls.length;ids['wizard-confirm'].checked=true;await ids['onboarding-form'].fire('submit');
 assert.equal(calls.length,staleCalls,'Cannot resave a stale revision');
 status=200;reply={revision:'rev-1',settings,password_set:true,pending:false};await run('loadSetup()');
 const baseBytes=Buffer.byteLength(JSON.stringify(run('setupPayload()')),'utf8');
 ids['setting-mqtt_user'].value='u'.repeat(8192-baseBytes+settings.mqtt_user.length);
 assert.equal(Buffer.byteLength(JSON.stringify(run('setupPayload()')),'utf8'),8192);
 reply={error:'setup_invalid'};status=400;ids['wizard-confirm'].checked=true;
 const boundaryCalls=calls.length;await ids['onboarding-form'].fire('submit');assert.equal(calls.length,boundaryCalls+1,'8192 bytes can reach server validation');
 ids['setting-mqtt_user'].value+='x';ids['wizard-confirm'].checked=true;
 await ids['onboarding-form'].fire('submit');assert.equal(calls.length,boundaryCalls+1,'8193 bytes blocked before network');
 assert.equal(ids['wizard-status'].textContent,'wizard_body_too_large');assert.equal(ids['wizard-confirm'].checked,false);
 ids['setting-mqtt_user'].value='é'.repeat(5000);ids['wizard-confirm'].checked=true;
 await ids['onboarding-form'].fire('submit');assert.equal(calls.length,boundaryCalls+1,'UTF-8 byte limit, not character count');
 reply={revision:'rev-1',settings,password_set:true,pending:false};status=200;await run('loadSetup()');
 ids['setting-mqtt_mode'].value='manual';ids['setting-mqtt_pass'].value='new-secret';
 ids['setting-publish_discovery'].checked=true;reply={pending:true,revision:'rev-2'};status=200;ids['wizard-confirm'].checked=true;
 await ids['onboarding-form'].fire('submit');
 assert.equal(JSON.parse(calls.at(-1).options.body).mqtt_pass,'new-secret');
 assert.equal(JSON.parse(calls.at(-1).options.body).settings.publish_discovery,true);
 assert.equal(ids['setting-mqtt_pass'].value,'');assert.equal(ids['wizard-status'].textContent,'wizard_pending');
 assert.equal(ids['wizard-save'].disabled,true);assert.equal(run('wizardRevision'),'rev-2');
 const before=calls.length;await ids['onboarding-form'].fire('submit');assert.equal(calls.length,before);
 reply={revision:'rev-3',settings,password_set:true,pending:false,simulation:false};await run('loadSetup()');
 reply={revision:'opaque-damaged-revision',settings,password_set:false,pending:false,damaged:true};await run('loadSetup()');
 assert.equal(ids['wizard-damaged-warning'].hidden,false);assert.equal(ids['wizard-recovery-consent'].hidden,false);
 assert.equal(ids['wizard-recovery-confirm'].checked,false);assert.equal(ids['setting-dovit_host'].value,settings.dovit_host);
 assert.equal(ids['wizard-save'].disabled,true);assert.equal(Object.hasOwn(run('setupPayload()'),'confirm_recovery'),false);
 const damagedCalls=calls.length;
 for(const [confirm,recovery] of [[false,false],[true,false],[false,true]]){
  ids['wizard-confirm'].checked=confirm;ids['wizard-recovery-confirm'].checked=recovery;
  run('refreshWizard()');assert.equal(ids['wizard-save'].disabled,true);
  await ids['onboarding-form'].fire('submit');assert.equal(calls.length,damagedCalls,'Both consents required even on forced submit');
 }
 ids['wizard-confirm'].checked=true;ids['wizard-recovery-confirm'].checked=true;run('refreshWizard()');
 assert.equal(ids['wizard-save'].disabled,false);
 await ids.language.fire('change');assert.equal(ids['wizard-recovery-confirm'].checked,true,'Language preserves recovery consent and draft');
 await ids['onboarding-form'].fire('input');
 assert.equal(ids['wizard-confirm'].checked,false);assert.equal(ids['wizard-recovery-confirm'].checked,false,'Settings edit invalidates both consents');
 ids['wizard-confirm'].checked=true;ids['wizard-recovery-confirm'].checked=true;await run('loadSetup()');
 assert.equal(ids['wizard-confirm'].checked,false);assert.equal(ids['wizard-recovery-confirm'].checked,false,'Reload resets both consents');
 ids['wizard-confirm'].checked=true;ids['wizard-recovery-confirm'].checked=true;
 reply={error:'setup_recovery_confirm'};status=400;await ids['onboarding-form'].fire('submit');
 assert.equal(ids['wizard-status'].textContent,'wizard_recovery_required');assert.equal(run('wizardLoaded'),false);
 assert.equal(ids['wizard-confirm'].checked,false);assert.equal(ids['wizard-recovery-confirm'].checked,false);
 const rejectedRecovery=JSON.parse(calls.at(-1).options.body);
 assert.equal(rejectedRecovery.confirm,true);assert.equal(rejectedRecovery.confirm_recovery,true);
 assert.equal(rejectedRecovery.revision,'opaque-damaged-revision','Revision remains opaque and unchanged');
 status=200;reply={revision:'damaged-reread',settings,password_set:false,pending:false,damaged:true};await run('loadSetup()');
 ids['wizard-confirm'].checked=true;ids['wizard-recovery-confirm'].checked=true;
 reply={pending:true,revision:'repaired-revision'};await ids['onboarding-form'].fire('submit');
 assert.equal(JSON.parse(calls.at(-1).options.body).confirm_recovery,true);
 assert.equal(ids['wizard-status'].textContent,'wizard_pending');assert.equal(ids['wizard-save'].disabled,true);
 assert.equal(ids['wizard-recovery-confirm'].checked,false);assert.equal(ids['wizard-damaged-warning'].hidden,true);
 reply={revision:'rev-3',settings,password_set:true,pending:false,damaged:false};await run('loadSetup()');
 ids['wizard-recovery-confirm'].checked=true;
 assert.equal(Object.hasOwn(run('setupPayload()'),'confirm_recovery'),false,'Hidden consent never grants recovery on normal setup');
 assert.equal(ids['wizard-recovery-consent'].hidden,true);
 reply={revision:null,settings,password_set:null,pending:false,damaged:true,writable:false,storage_error:'setup_storage_error'};
 await run('loadSetup()');
 assert.equal(run('wizardStorageBlocked'),true);
 assert.equal(ids['onboarding-panel'].hidden,false,'Unpreservable storage opens useful setup diagnostics');
 assert.equal(ids['wizard-status'].textContent,'wizard_storage_error');
 assert.equal(ids['wizard-damaged-warning'].dataset.i18n,'wizard_storage_blocked');
 assert.equal(ids['wizard-password-state'].textContent,'wizard_password_unknown','Cannot claim absence of unreadable credentials');
 assert.equal(ids['wizard-recovery-consent'].hidden,true,'No offered consent can authorize dropping an unreadable original');
 for(const key of [...Object.keys(settings),'mqtt_pass'])assert.equal(ids['setting-'+key].disabled,true,'Storage error locks '+key);
 assert.equal(ids['wizard-next'].disabled,true);assert.equal(ids['wizard-save'].disabled,true);
 const blockedCalls=calls.length;ids['wizard-confirm'].checked=true;ids['wizard-recovery-confirm'].checked=true;
 await ids['onboarding-form'].fire('submit');assert.equal(calls.length,blockedCalls,'Forced submit cannot replace unpreservable setup');
 await ids.language.fire('change');assert.equal(ids['wizard-damaged-warning'].dataset.i18n,'wizard_storage_blocked');
 reply={revision:'rev-readable-again',settings,password_set:true,pending:false,damaged:false,writable:true,storage_error:null};
 await run('loadSetup()');assert.equal(run('wizardStorageBlocked'),false);assert.equal(ids['wizard-damaged-warning'].hidden,true);
 assert.equal(run('wizardPending'),false);ids['wizard-confirm'].checked=true;fail=true;
 await ids['onboarding-form'].fire('submit');assert.equal(ids['wizard-status'].textContent,'wizard_uncertain');
 assert.equal(ids['wizard-save'].disabled,true);assert.equal(run('wizardLoaded'),false);
 assert.ok(calls.every(call=>call.url==='api/setup'),'No commands, restart, validation, transports or other routes');
 const onboarding=html.match(/<section id="onboarding-panel"[\s\S]*?<\/form><\/section>/)[0];
 const list=onboarding.match(/<ol class="wizard-progress"([^>]*)>([\s\S]*?)<\/ol>/);
 assert.match(list[1],/\brole="list"/,'Explicit list semantics survive marker removal');
 const stepLabels=[...list[2].matchAll(/<li data-step="(\d)" data-i18n="([^"]+)"><\/li>/g)];
 assert.equal(stepLabels.length,4);
 assert.equal((onboarding.match(/data-i18n="wizard_simulation"/g)||[]).length,1,'One central setup simulation warning');
 const details=onboarding.match(/<details id="wizard-current-details"([^>]*)>([\s\S]*?)<\/details>/);
 assert.ok(details);assert.doesNotMatch(details[1],/\bopen\b/,'Runtime explanation is collapsed by default');
 assert.match(details[2],/<summary data-i18n="wizard_current_details">/);
 assert.match(details[2],/data-i18n="wizard_current_hint"/);
 assert.doesNotMatch(details[2],/id="wizard-(?:current-feedback|status|damaged-warning)"/,'Feedback and errors are not collapsed');
 const aside=onboarding.match(/<aside([^>]*)>([\s\S]*?)<\/aside>/);
 assert.doesNotMatch(aside[1],/\bhidden\b/);
 assert.ok(aside[2].indexOf('id="wizard-current-feedback"')<aside[2].indexOf('<details'));
 for(const id of ['wizard-current-feedback','wizard-status']){
  const attrs=onboarding.match(new RegExp('<p id="'+id+'"([^>]*)>'))[1];
  assert.match(attrs,/role="status"/);assert.doesNotMatch(attrs,/\bhidden\b/);
 }
 const cssRule=selector=>{
  const escaped=selector.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const rule=css.match(new RegExp(escaped+'\\{([^}]*)\\}'));
  assert.ok(rule,'Scoped CSS rule: '+selector);return rule[1];
 };
 assert.match(cssRule('#onboarding-panel .wizard-progress'),/(?:^|;)list-style:none(?:;|$)/);
 assert.doesNotMatch(css,/\.wizard-progress[^{}]*::(?:before|after|marker)\s*\{[^}]*content\s*:/,'No generated duplicate numbering');
 for(const [id,kind] of [['back','secondary'],['reload','secondary'],['next','primary'],['save','primary']]){
  const attrs=onboarding.match(new RegExp('<button id="wizard-'+id+'"([^>]*)>'))[1];
  assert.match(attrs,new RegExp('class="wizard-'+kind+'"'));
 }
 const primary=cssRule('#onboarding-panel .wizard-actions .wizard-primary');
 assert.match(primary,/background:var\(--ink\)/);assert.match(primary,/color:var\(--surface\)/);
 const secondary=cssRule('#onboarding-panel .wizard-actions .wizard-secondary');
 assert.match(secondary,/background:transparent/);assert.match(secondary,/color:var\(--ink\)/);
 const disabled=cssRule('#onboarding-panel .wizard-actions button:disabled');
 assert.match(disabled,/background:var\(--soft\)/);assert.match(disabled,/color:var\(--muted\)/);
 assert.match(disabled,/border-style:dashed/);assert.match(disabled,/cursor:not-allowed/);assert.doesNotMatch(disabled,/opacity:/);
 assert.match(cssRule('#onboarding-panel button'),/min-height:44px/);assert.match(cssRule('#onboarding-panel button'),/min-width:44px/);
 assert.match(cssRule('#onboarding-panel .wizard-actions'),/flex-wrap:wrap/);
 assert.match(cssRule('#onboarding-panel .wizard-actions button'),/flex:1 1 160px/,'Mobile controls wrap with readable widths');
 assert.match(cssRule('#wizard-current-details>summary'),/min-height:44px/);
 assert.doesNotMatch(css,/#wizard-(?:current-feedback|status)[^{}]*\{[^}]*(?:display:none|visibility:hidden|opacity:0)/);
 const copyContext=vm.createContext({navigator:{language:'de'},localStorage:{getItem:()=>null}});
 vm.runInContext(catalog,copyContext);
 const messages=vm.runInContext('messages',copyContext);
 const keys=new Set([...source.match(/wizard_[a-z_]+/g),...[...onboarding.matchAll(/data-i18n="([^"]+)"/g)].map(match=>match[1])]);
 for(const key of keys){assert.equal(messages[key]?.length,2,key);assert.ok(messages[key].every(text=>typeof text==='string'&&text.length),key);}
 for(const [column,locale] of ['de','fr'].entries()){
  vm.runInContext('language='+JSON.stringify(locale),copyContext);
  for(const [index,match] of stepLabels.entries()){
   assert.equal(Number(match[1]),index);
   const label=messages[match[2]][column];assert.ok(label.startsWith((index+1)+' \u00b7 '));
   assert.equal((label.match(/\b[1-4]\b/g)||[]).length,1,'Exactly one accessible number: '+locale+' '+label);
  }
  for(const key of ['wizard_loaded','wizard_draft','wizard_pending','wizard_current_details','diagnosis_simulation'])
   assert.equal(vm.runInContext('t('+JSON.stringify(key)+')',copyContext),messages[key][column]);
  assert.match(messages.wizard_loaded[column],column===0?/geladen.*lokaler Entwurf/:/chargés.*brouillon local/);
  assert.doesNotMatch(messages.wizard_loaded[column]+messages.wizard_draft[column],/Simulation|[Nn]eustart|redémarrage/);
  const hint=messages.wizard_hint[column];assert.ok(hint.length<200,'Compact main wizard hint: '+locale);
  assert.match(hint,column===0?/nächsten manuellen Neustart/:/prochain redémarrage manuel/);
  assert.match(hint,column===0?/Keine Verbindungstests, Schaltbefehle oder automatischen Neustarts/:/Aucun test de connexion, commande ou redémarrage automatique/);
  assert.match(messages.wizard_simulation[column],/Dovit.*MQTT/);assert.match(messages.wizard_simulation[column],/HA/);
  assert.match(messages.wizard_simulation[column],column===0?/isolierte Testkonfiguration/:/configuration de test isolée/);
  assert.ok(messages.diagnosis_simulation[column].length<80,'Runtime simulation feedback is compact: '+locale);
  assert.match(messages.diagnosis_simulation[column],column===0?/unbestätigt/:/non confirmée/);
  assert.match(messages.wizard_current_hint[column],column===0?/laufende Bridge.*Pflichtfelder.*keine Anfrage/:/passerelle en cours.*champs obligatoires.*sans envoyer de requête/);
  assert.match(messages.wizard_current_title[column],column===0?/nur lesen/:/lecture seule/);
 }
 assert.ok(html.includes('D2HA / 3.1.1'));assert.ok(html.includes('autocomplete="new-password"'));
 assert.doesNotMatch(html,/role="tab(?:list|panel)?"|id="(?:graphic|json)-tab"/,'No nested tabs that focus a hidden workspace');
 assert.match(html,/<section id="json-panel" aria-labelledby="json-title"/);
 assert.match(html,/<button id="json-return" type="button"/,'Native keyboard-operable return action');
 assert.match(html,/<section id="empty-inventory"[^>]* hidden>/);
 for(const key of ['main_title','main_subtitle','main_setup_title','main_setup_subtitle','main_diagnosis_title','main_diagnosis_subtitle','main_navigation','json_return_devices','empty_inventory_title','empty_inventory_hint','empty_inventory_restore','empty_inventory_setup','unknown_filter'])
  assert.ok(messages[key]?.every(text=>typeof text==='string'&&text.length),'DE/FR orientation: '+key);
 assert.match(messages.wizard_supervisor[0],/Home-Assistant-MQTT-Dienst.*automatisch/);
 assert.match(messages.wizard_supervisor[1],/Service MQTT de Home Assistant.*automatique/);
 assert.match(messages.Statetype[0],/Signalart.*Statetype/);assert.match(messages.Statetype[1],/Type de signal.*Statetype/);
 assert.equal(messages.unknown_devices[0],'Nicht zugeordnete Signale');assert.equal(messages.unknown_devices[1],'Signaux non affectés');
 assert.ok(html.includes('<option value="3.1">3.1</option>'));
 assert.ok(html.indexOf('<option value="manual"')<html.indexOf('<option value="supervisor"'),'Manual remains initial mode; Supervisor explicitly opt-in');
 assert.ok(catalog.includes('enable_discovery'));assert.ok(catalog.includes('publish_discovery ausgeschaltet'));
 console.log('Onboarding/navigation, single numbering, DE/FR copy, collapsed runtime details, action states/CSS, consent, password, revision and uncertain-save tests passed offline.');
})().catch(error=>{console.error(error);process.exitCode=1;});
