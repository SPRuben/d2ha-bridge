// Offline card disclosure regression. No polling, network, or physical commands.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.value='';this.classList={add(){}};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 insertBefore(child,before){const i=this.children.indexOf(before);this.children.splice(i<0?this.children.length:i,0,child);}
 focus(options){document.activeElement=this;this.focusOptions=options;}
}
const descendants=el=>el.children.flatMap(child=>[child,...descendants(child)]);
const ids=Object.fromEntries(['devices','unknown-devices','archive','session','connection','search','category','count','unknown-count','events','repeats'].map(id=>[id,new Element('div')]));
const document={activeElement:null,getElementById:id=>ids[id],createElement:tag=>new Element(tag),querySelector:()=>null,
 querySelectorAll:selector=>Object.values(ids).flatMap(descendants).filter(el=>selector==='.manage-button'?el.dataset.deviceUid:selector==='.device-details summary'?el.dataset.detailUid:false)};
let commands=0;
const context=vm.createContext({document,language:'de',t:key=>key,setText:(el,text)=>{el.textContent=text;},
 refreshControlButtons(){},setTrackedCommandStatus(){},fetch(){commands++;throw Error('Unexpected network');},
 managementButton:device=>{const el=new Element('button');el.dataset.deviceUid=device.uid;return el;}});
const source=fs.readFileSync(path.join(__dirname,'../dovit_bridge/web/app.js'),'utf8');
vm.runInContext(source.slice(0,source.indexOf("$('observe').onclick")),context);
const run=code=>vm.runInContext(code,context);
run("data={connected:true,devices:[{uid:'lights:19',name:'Office',category:'lights',endpoints:[[19,0]]}],states:[{key:'19:0',device_id:19,statetype:0,value:'1',time:'2026-10-03T09:10:11.123+00:00',count:7,matches:[{uid:'lights:19'}]}],events:[]};render()");
const detail=()=>descendants(ids.devices).find(el=>el.tag==='details');
const summary=()=>detail().children[0];
assert.equal(detail().open,false,'Raw diagnostics start collapsed');
assert.ok(detail().children.some(el=>el.textContent.includes('19 / ST 0')&&el.textContent.endsWith('1')),'Exact raw endpoint and value retained');
assert.ok(detail().children.some(el=>el.textContent.includes('7 Meldungen')),'Reception diagnostics retained');
const visibleState=()=>descendants(ids.devices).find(el=>el.className==='device-state');
assert.equal(visibleState().children.find(el=>el.className==='device-received').dateTime,'2026-10-03T09:10:11.123Z','Known reception time is visible outside collapsed raw details');
detail().open=true;detail().ontoggle();summary().focus();
const oldSummary=summary();run('render()');
assert.equal(detail().open,true,'Open diagnostics survive snapshot rendering');
assert.notEqual(summary(),oldSummary);
assert.equal(document.activeElement,summary(),'Summary focus follows the same device');
assert.equal(summary().focusOptions.preventScroll,true);
detail().open=false;detail().ontoggle();run('render()');
assert.equal(detail().open,false,'Closed diagnostics stay closed');
const input=new Element('input');document.activeElement=input;run('render()');
assert.equal(document.activeElement,input,'Rendering does not steal editor focus');
run("data.states.push({key:'999:3',device_id:999,statetype:3,value:'raw-unknown',time:0,count:1,matches:[]});render()");
assert.ok(descendants(ids['unknown-devices']).some(el=>el.textContent?.includes('raw-unknown')),'Unknown raw diagnostics remain visible');
assert.equal(commands,0,'Opening and rendering diagnostic details send no requests');
context.previousData=run('data');
context.receivedSnapshot={connected:true,events:[],devices:[
 {uid:'thermostats:44',name:'Thermostat',category:'thermostats',endpoints:[[44,1],[44,2],[44,3]]},
 {uid:'clocks:39',name:'Dovit',category:'clocks',endpoints:[[39,111]]},
 {uid:'alarms:87',name:'Alarm',category:'alarms',endpoints:[[87,10],[87,11]]}
],states:[
 {key:'44:1',device_id:44,statetype:1,value:'21.8',time:'2026-10-03T09:10:11Z',count:1,matches:[{uid:'thermostats:44',role:'current'}]},
 {key:'44:2',device_id:44,statetype:2,value:'22.5',time:null,count:1,matches:[{uid:'thermostats:44',role:'target'}]},
 {key:'44:3',device_id:44,statetype:3,value:'1',time:'2026-09-30T07:00:00Z',count:1,kind:'historical',matches:[{uid:'thermostats:44',role:'mode'}]},
 {key:'39:111',device_id:39,statetype:111,value:'15;44',time:'2026-10-03T09:00:00Z',count:1,matches:[{uid:'clocks:39',role:'time'}]},
 {key:'87:10',device_id:87,statetype:10,value:'unexpected',time:'2026-10-03T08:00:00Z',count:1,matches:[{uid:'alarms:87',role:'state'}]},
 {key:'87:11',device_id:87,statetype:11,value:'text',time:'invalid',count:1,matches:[{uid:'alarms:87',role:'text'}]}
]};
run('data=receivedSnapshot;render()');
const cardFor=uid=>descendants(ids.devices).find(el=>el.tag==='article'&&el.children.some(child=>child.dataset.deviceUid===uid));
const stateFor=uid=>cardFor(uid).children.find(el=>el.className==='device-state');
const thermostatState=stateFor('thermostats:44');
const receptions=thermostatState.children.filter(el=>el.className==='device-received');
assert.equal(receptions.length,3,'Thermostat renders one reception label per readable value');
assert.equal(receptions[0].dateTime,'2026-10-03T09:10:11.000Z');
assert.equal(receptions[1].dateTime,undefined,'Missing target time does not borrow the current temperature timestamp');
assert.equal(receptions[1].textContent,'state_received_unknown');
assert.equal(receptions[2].dateTime,'2026-09-30T07:00:00.000Z');
assert.equal(receptions[2].dataset.archived,'true');
assert.equal(cardFor('thermostats:44').children.some(el=>el.textContent?.startsWith('Archiviert:')),false,'One archived endpoint does not classify the entire thermostat as archive-only');
assert.equal(stateFor('clocks:39').children[0].textContent,'15:44','System clock display is distinct from receipt time');
assert.equal(stateFor('clocks:39').children[1].dateTime,'2026-10-03T09:00:00.000Z');
assert.equal(stateFor('alarms:87').children[1].textContent,'ID 87 / ST 10','Unreadable state values retain separate reception endpoint labels');
assert.equal(stateFor('alarms:87').children[3].textContent,'ID 87 / ST 11');
assert.equal(stateFor('alarms:87').children[4].textContent,'state_received_unknown');
assert.ok(descendants(ids.devices).filter(el=>el.tag==='details').every(el=>el.open===false),'Visible reception times do not force raw diagnostics open');
assert.equal(document.activeElement,input,'Reception rendering preserves unrelated editor focus');
assert.equal(commands,0,'Reception times are a passive presentation of snapshot evidence');
run('data=previousData;render()');
for(const classification of ['observed','inferred','confirmed']){
 context.classification=classification;
 run('data.devices[0].classification=classification;data.states[0].classification=classification;render()');
 const labels=descendants(ids.devices).filter(el=>el.dataset.classification===classification);
 assert.equal(labels.length,1,'Matching device/state classifications are shown once');
 assert.ok(labels.every(el=>el.textContent==='classification_'+classification));
 assert.ok(descendants(ids.devices).some(el=>el.textContent==='classification_'+classification+'_hint'));
}
run("data.devices[0].classification='confirmed';data.states[0].classification='observed';render()");
assert.equal(descendants(ids.devices).filter(el=>el.dataset.classification).length,2,'Different endpoint evidence is retained');
run("data.devices[0].classification='unsupported';data.states[0].classification='unsupported';render()");
assert.equal(descendants(ids.devices).filter(el=>el.dataset.classification).length,0,'Unknown metadata never invents confirmation');
assert.equal(commands,0,'Classification rendering remains passive');
run("apiOnline=true;data.connected=false;data.device_control='simulation';renderConnection()");
assert.equal(ids.connection.dataset.state,'demo');
assert.equal(ids.connection.textContent,'ui_demo_status');
run('data.connected=true;renderConnection()');
assert.equal(ids.connection.dataset.state,'demo','Simulation never claims a live connection');
run('apiOnline=false;renderConnection()');
assert.equal(ids.connection.dataset.state,'offline','API loss overrides demo status');
run("apiOnline=true;delete data.device_control;renderConnection()");
assert.equal(ids.connection.dataset.state,'live','Real connection status remains intact');
run("data.connected=false;data.light_control='simulation';renderConnection()");
assert.equal(ids.connection.dataset.state,'demo','Light simulation is also explicit');
assert.equal(commands,0,'Demo status sends no commands');
console.log('Main UX disclosure, raw diagnostics and render focus passed. No network.');
const web=path.join(__dirname,'../dovit_bridge/web');
const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
assert.ok(!html.includes('<label>Deutsch / Français'),'Language choice has no redundant visible label');
assert.ok(html.includes('aria-label="Sprache / Langue"'),'Language choice retains accessible name');
const css=fs.readFileSync(path.join(web,'mapping.css'),'utf8');
assert.ok(css.includes('.card.unknown .manage-button{position:static;display:flex;'),'Assign button is separated from observed badge');
assert.ok(css.includes('max-width:100%'),'Assign action fits narrow cards');
assert.ok(css.includes('.device-state p{overflow-wrap:normal}'),'Nonbreaking temperature unit is respected');
assert.ok(css.includes('.device-state .device-received{display:block;'),'Reception time is placed on its own small line');
