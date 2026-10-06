// Read-only setup facts, offline DOM, no network or device commands.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const web=path.join(__dirname,'../dovit_bridge/web');
const ids=Object.fromEntries(['setup-panel','setup-help','help-open','setup-overview','setup-next','setup-automatic','empty-inventory',
 ...['dovit','mqtt','devices','publishing','ha'].map(key=>'setup-'+key+'-status')].map(id=>[id,{dataset:{},textContent:'',addEventListener(){},click(){}}]));
let requests=0;
const context=vm.createContext({document:{getElementById:id=>ids[id]},$:id=>ids[id],t:key=>key,
 fetch(){requests++;throw Error('Network forbidden');},apiOnline:true,data:null});
vm.runInContext(fs.readFileSync(path.join(web,'setup.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const snapshot={connected:true,devices:[{category:'lights',name:'Office',classification:'confirmed'}],
 setup:{mqtt_connected:true,discovery_publishing:true,automatic_discovery:false}};
context.input=snapshot;
let model=run('setupModel(input,true)');
assert.equal(model.overview,'setup_overview_connected');
assert.equal(model.ha.state,'unknown','No fabricated HA acceptance');
assert.equal(model.next,'setup_next_ha');
snapshot.setup.mqtt_connected=false;
model=run('setupModel(input,true)');assert.equal(model.mqtt.state,'attention');assert.equal(model.next,'setup_next_mqtt');
snapshot.setup.mqtt_connected=true;snapshot.setup.discovery_publishing=false;
assert.equal(run('setupModel(input,true).next'),'setup_next_publish');
snapshot.setup.discovery_publishing=true;snapshot.setup.automatic_discovery=true;
assert.equal(run('setupModel(input,true).automatic'),true);
snapshot.devices=[{category:'clocks',classification:'confirmed'}];
assert.equal(run('setupModel(input,true).empty'),true,'System clock is not an installed house device');
assert.equal(run('setupModel(input,true).next'),'setup_next_devices');
snapshot.devices=[{category:'lights',classification:'inferred'}];
assert.equal(run('setupModel(input,true).devices.state'),'attention','TODO candidates are not confirmed');
assert.equal(run('setupModel(input,false).mqtt.state'),'unknown','Old snapshot is stale when API fails');
assert.equal(run('setupModel(input,false).next'),'setup_next_offline');
context.input={connected:true,devices:snapshot.devices};
assert.equal(run('setupModel(input,true).mqtt.state'),'unknown','Older snapshots do not invent MQTT status');
assert.equal(run('setupModel(input,true).next'),'setup_next_unknown');
context.input={connected:true,devices:[{category:'lights',name:'Older device'}],setup:{mqtt_connected:true,discovery_publishing:true}};
assert.equal(run('setupModel(input,true).devices.state'),'unknown','Missing classification is not a missing configuration');
assert.equal(run('setupModel(input,true).next'),'setup_next_unknown');
context.input={...snapshot,light_control:'simulation'};
assert.equal(run('setupModel(input,true).next'),'setup_next_simulation');
assert.equal(run('setupModel(input,true).dovit.label'),'ui_demo_status','Preview does not present a real connection failure');
assert.equal(run('setupModel(input,true).dovit.state'),'unknown');
assert.equal(run('setupModel(input,false).dovit.label'),'setup_unverified','Stale demo cannot hide API failure');
assert.equal(run('setupModel(null,false).dovit.state'),'unknown');
run('data={connected:true,inventory_configured:true,devices:[]};renderSetup()');
assert.equal(ids['setup-panel'].open,true,'First empty runtime opens guidance');
assert.equal(ids['empty-inventory'].hidden,false,'Valid empty inventory gets visible first-step guidance');
ids['setup-panel'].open=false;run('renderSetup()');assert.equal(ids['setup-panel'].open,false,'Polling preserves user disclosure');
run('data={inventory_configured:true,devices:[{category:"clocks",classification:"confirmed"}]};renderSetup()');
assert.equal(ids['empty-inventory'].hidden,false,'System clock does not hide onboarding');
run('data={inventory_configured:true,devices:[],observations:[{device_id:999,statetype:3}]};renderSetup()');
assert.equal(ids['empty-inventory'].hidden,false,'Unassigned observations are not configured devices');
run('data={inventory_configured:true,devices:[{category:"lights",classification:"inferred"}]};renderSetup()');
assert.equal(ids['empty-inventory'].hidden,true,'Existing candidate inventory is not a valid empty map');
run('data={inventory_configured:true,devices:[{category:"lights",classification:"confirmed"}],search:"no matches"};renderSetup()');
assert.equal(ids['empty-inventory'].hidden,true,'A filtered empty result cannot replace the actual inventory');
run('data={};renderSetup()');assert.equal(ids['empty-inventory'].hidden,true,'Missing inventory is not a new installation');
run('data=null;renderSetup()');assert.equal(ids['empty-inventory'].hidden,true,'Initial loading is not a new installation');
run('data={inventory_configured:false,devices:[]};renderSetup()');assert.equal(ids['empty-inventory'].hidden,true,'An unconfigured repair-only runtime is not a valid empty map');
run('data={devices:[]};renderSetup()');assert.equal(ids['empty-inventory'].hidden,true,'Legacy API without readiness cannot prove an empty valid map');
run('data={inventory_configured:true,devices:[]};apiOnline=false;renderSetup()');assert.equal(ids['setup-mqtt-status'].dataset.state,'unknown');
assert.equal(ids['empty-inventory'].hidden,true,'Stale empty data does not invite setup');
assert.equal(requests,0);
const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
assert.ok(html.indexOf('src="setup.js"')<html.indexOf('src="app.js"'));
assert.ok(!/\sonclick=/.test(html),'No inline script under CSP');
const catalog=fs.readFileSync(path.join(web,'i18n.js'),'utf8');
for(const key of ['ui_temperature_input','ui_temperature_test','ui_assignment_hint','ui_cover_mapping_hint','ui_assignment_review'])
 assert.ok(catalog.includes("'"+key+"'"),'Shared UI translation '+key);
const css=fs.readFileSync(path.join(web,'style.css'),'utf8');
assert.ok(css.includes('.main-header .product-name{display:inline;'),'Product name overrides legacy mobile hiding');
assert.ok(css.includes('grid-template-columns:repeat(2,minmax(0,1fr))'),'Compact desktop setup grid');
assert.ok(css.includes('.setup-steps{grid-template-columns:1fr}'),'Mobile setup keeps readable single-column facts');
for(const key of new Set(fs.readFileSync(path.join(web,'setup.js'),'utf8').match(/setup_[a-z_]+/g)))
 assert.ok(catalog.includes("'"+key+"'"),'Translated '+key);
function luminance(hex){return hex.match(/[0-9a-f]{2}/g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
for(const surface of ['ffffff','fffdf7','edf1e9'])assert.ok(contrast('6b8076',surface)>=3,'Control border contrast '+surface);
console.log('Setup readiness, unknown/stale/simulation states, disclosure and contrast tests passed. No network.');
context.input={setup:{mqtt_connected:true,discovery_publishing:true,mqtt_mode:'supervisor',mqtt_changed_at:1720000000}};
assert.equal(run('diagnosisModel(null,false).guidance'),'diagnosis_offline');
assert.equal(run('diagnosisModel(input,false).guidance'),'diagnosis_stale');
assert.equal(run('diagnosisModel({},true).guidance'),'diagnosis_unknown');
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_ready');
assert.equal(run('diagnosisModel(input,true).mode'),'diagnosis_mode_supervisor');
context.input.setup.mqtt_state='offline';
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_mqtt','Offline state overrides old connected boolean');
delete context.input.setup.mqtt_state;
for(const value of ['secret diagnostic payload','constructor','toString','__proto__']){
 context.input.setup.configuration_error=value;
 assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_configuration');
}
context.input.setup.configuration_error='supervisor_unavailable';
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_supervisor');
assert.equal(run('diagnosisModel({...input,simulation:true},true).guidance'),'diagnosis_simulation');
context.input.setup.configuration_error=null;context.input.setup.dovit_state='offline';
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_dovit');
context.input.setup.dovit_state='connected';context.input.setup.discovery_publishing=false;
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_publication');
for(const [state,key] of Object.entries({auth_rejected:'diagnosis_credentials',rejected:'diagnosis_rejected',
 unreachable:'diagnosis_mqtt',connecting:'diagnosis_connecting',connected:'diagnosis_ready',disconnected:'diagnosis_mqtt',stopped:'diagnosis_stopped'})){
 context.input.setup={mqtt_state:state,mqtt_connected:state==='connected',discovery_publishing:true,dovit_state:'connected'};
 assert.equal(run('diagnosisModel(input,true).guidance'),key,state);
}
context.input.setup={mqtt_state:'auth_rejected',mqtt_connected:false,dovit_state:'offline'};
assert.equal(run('diagnosisModel(input,true).guidance'),'diagnosis_credentials','Credentials take precedence over Dovit');
for(const [error,key] of Object.entries({mqtt_supervisor_token_missing:'diagnosis_supervisor_token',mqtt_supervisor_token_invalid:'diagnosis_supervisor_token',
 mqtt_supervisor_auth_rejected:'diagnosis_supervisor_auth',mqtt_service_unavailable:'diagnosis_service',mqtt_service_timeout:'diagnosis_service',
 mqtt_service_invalid_response:'diagnosis_service_response',mqtt_service_response_too_large:'diagnosis_service_response',mqtt_invalid_config:'diagnosis_configuration',invalid_configuration:'diagnosis_configuration'})){
 context.input.setup.configuration_error=error;
 assert.equal(run('diagnosisModel(input,true).guidance'),key,error);
}
for(const key of new Set(fs.readFileSync(path.join(web,'setup.js'),'utf8').match(/diagnosis_[a-z_]+/g)))
 assert.ok(catalog.includes("'"+key+"'"),'Translated '+key);
for(const id of ['diagnosis-guidance','diagnosis-mode','diagnosis-changed','wizard-current-feedback','wizard-runtime'])ids[id]={dataset:{},textContent:''};
context.setText=(element,key)=>{element.textContent=key;};context.language='de';
run('data={setup:{mqtt_state:"connecting",mqtt_connected:false}};apiOnline=true;renderDiagnosis()');
assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_connecting');
assert.equal(ids['wizard-runtime'].hidden,false,'Real runtime feedback is visible');
assert.equal(ids['wizard-current-feedback'].textContent,ids['diagnosis-guidance'].textContent,'Setup feedback reuses actual runtime diagnostic model');
assert.equal(ids['diagnosis-mode'].hidden,true,'An unknown mode is not a second general diagnosis');
assert.equal(ids['diagnosis-mode'].textContent,'');
for(const [mode,key] of [['manual','diagnosis_mode_manual'],['supervisor','diagnosis_mode_supervisor']]){
 context.selectedMode=mode;
 run('data={setup:{mqtt_mode:selectedMode,mqtt_state:"connecting"}};renderDiagnosis()');
 assert.equal(ids['diagnosis-mode'].hidden,false,'Known modes remain visible');
 assert.equal(ids['diagnosis-mode'].textContent,key);
}
run('apiOnline=false;renderDiagnosis()');assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_stale');
assert.equal(ids['wizard-runtime'].hidden,false,'Offline errors must not be concealed');
assert.equal(ids['diagnosis-mode'].hidden,true,'Old mode information is not shown as current');
assert.equal(ids['diagnosis-mode'].textContent,'');
assert.equal(ids['diagnosis-mode'].dataset.i18n,undefined,'Translation cannot revive a stale hidden mode');
run('data={simulation:true};apiOnline=true;renderDiagnosis()');
assert.equal(ids['wizard-runtime'].hidden,true,'Demo uses the central simulation warning instead of repeating runtime prose');
assert.equal(ids['diagnosis-guidance'].textContent,'diagnosis_simulation');
assert.equal(ids['diagnosis-mode'].hidden,true,'Demo has no duplicate unknown-status paragraph');
run('apiOnline=false;renderDiagnosis()');
assert.equal(ids['wizard-runtime'].hidden,false,'Demo server connectivity problems remain visible');
run('data={setup:{configuration_error:"mqtt_supervisor_auth_rejected"}};apiOnline=true;renderDiagnosis()');
assert.equal(ids['wizard-runtime'].hidden,false);
assert.equal(ids['wizard-current-feedback'].textContent,'diagnosis_supervisor_auth');
run('data={};renderDiagnosis()');
assert.equal(ids['diagnosis-guidance'].textContent,'diagnosis_unknown','The primary unknown-status explanation remains');
assert.equal(ids['diagnosis-mode'].hidden,true);
assert.equal(requests,0,'Current connection feedback is read-only');
