// Offline presentation regression: no network and no physical controls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const web=path.join(__dirname,'../dovit_bridge/web');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};}
 append(...children){this.children.push(...children);}
 insertBefore(child,before){const index=this.children.indexOf(before);this.children.splice(index<0?this.children.length:index,0,child);}
}
const context=vm.createContext({navigator:{language:'de'},localStorage:{getItem:()=>null},
 document:{getElementById:()=>null,createElement:tag=>new Element(tag)}});
const run=code=>vm.runInContext(code,context);
run(fs.readFileSync(path.join(web,'i18n.js'),'utf8'));
const app=fs.readFileSync(path.join(web,'app.js'),'utf8');
run(app.slice(0,app.indexOf('function render(fresh')));
function summary(category,value,role,locale='de'){
 context.device={category,uid:category+':19'};
 context.state={value,matches:role?[{uid:context.device.uid,role}]:[]};
 run(`language='${locale}'`);
 return run('stateSummary(device,state)');
}
assert.equal(summary('lights','1'),'Eingeschaltet');
assert.equal(summary('switches','1'),'Ein');
assert.equal(summary('switches','0'),'Aus');
assert.equal(summary('switches','1',null,'fr'),'Activé');
assert.equal(summary('switches','0',null,'fr'),'Désactivé');
assert.equal(summary('switches','0.5'),'');
assert.equal(summary('lights','0'),'Ausgeschaltet');
assert.equal(summary('lights','0.5',null,'fr'),'Allum\u00e9');
assert.equal(summary('motions','0.49'),'Keine Bewegung');
assert.equal(summary('motions','1',null,'fr'),'Mouvement d\u00e9tect\u00e9');
assert.equal(summary('contacts','1'),'Kontakt offen');
assert.equal(summary('contacts','0',null,'fr'),'Contact ferm\u00e9');
assert.equal(summary('shutters','1.0'),'F\u00e4hrt hoch');
assert.equal(summary('shutters','2',null,'fr'),'Descente en cours');
assert.equal(summary('shutters','0'),'Gestoppt \u00b7 keine Positionsmeldung');
assert.equal(summary('shutters','3'),'');
assert.equal(summary('shutters','1e0'),'','Do not extend legacy cover protocol semantics');
assert.equal(summary('thermostats','21.123','current'),'Ist-Temperatur: 21,123\u00a0\u00b0C');
assert.equal(summary('thermostats','22.5','target','fr'),'Temp\u00e9rature de consigne: 22,5\u00a0\u00b0C');
assert.equal(summary('thermostats','1','mode'),'Heizmodus: Heizen');
assert.equal(summary('thermostats','0','mode','fr'),'Mode : arr\u00eat');
assert.equal(summary('thermostats','21.8'),'','Endpoint role is required');
context.state.matches=[{uid:'thermostats:999',role:'current'}];
assert.equal(run('stateSummary(device,state)'),'','Do not use another thermostat role');
for(const category of ['lights','motions','contacts','thermostats']){
 for(const invalid of ['',' ','NaN','Infinity','1e999','0x10','abc','<script>']){
  assert.equal(summary(category,invalid,'current'),'');
 }
}
for(const category of ['alarms','unknown','clocks'])assert.equal(summary(category,'1','state'),'');
run("language='de';var card=node('article','');var raw=node('p','19 / ST 0 -> 1',undefined,true);card.append(node('small','Licht'),node('h3','Office',undefined,true),raw);appendStateSummary(card,{category:'lights'},[{value:'1',kind:'historical'}]);");
assert.equal(run('card.children[2].children[0].textContent'),'Zuletzt gemeldet');
assert.equal(run('card.children[2].children[1].textContent'),'Eingeschaltet');
assert.equal(run('card.children[3]===raw'),true,'Keep raw diagnostics intact');
assert.equal(run('raw.textContent'),'19 / ST 0 -> 1');
assert.equal(run('card.children[2].children[1].dataset.i18n'),undefined);
assert.equal(run('card.children[2].children[2].textContent'),'Archivierter Empfang: Empfangszeit unbekannt');

function receivedCard(category,states,locale='de'){
 context.device={category,uid:category+':19'};
 context.states=states.map(state=>({...state,matches:state.role?[{uid:context.device.uid,role:state.role}]:state.matches||[]}));
 run(`language='${locale}';card=node('article','');card.append(node('small',''),node('h3','Office',undefined,true));appendStateSummary(card,device,states)`);
 return run('card').children[2];
}
const iso='2026-10-03T09:10:11.123+00:00';
for(const locale of ['de','fr']){
 const block=receivedCard('lights',[{value:'1',time:iso}],locale);
 const received=block.children[2];
 const label=locale==='fr'?'Re\u00e7u : ':'Empfangen: ';
 assert.equal(received.tag,'time');
 assert.equal(received.dateTime,new Date(iso).toISOString(),'Machine-readable reception time is canonical UTC');
 assert.equal(received.textContent,label+new Date(iso).toLocaleString(locale==='fr'?'fr-FR':'de-DE'),'Visible time uses the current language and browser timezone');
 assert.equal(received.dataset.i18n,undefined,'Interpolated time is literal text, not an i18n key');
 assert.equal(received.className,'device-received');
 const sameInstant=receivedCard('lights',[{value:'1',time:'2026-10-03T11:10:11.123+02:00'}],locale).children[2];
 assert.equal(sameInstant.textContent,received.textContent,'Explicit source timezone never changes the represented instant');
}
const thermostat=receivedCard('thermostats',[
 {value:'21.8',role:'current',time:'2026-10-03T09:10:11.123+00:00'},
 {value:'22.5',role:'target',time:'2026-10-02T08:00:00.000+00:00'},
 {value:'1',role:'mode',time:'2026-09-30T07:00:00.000+00:00',kind:'historical'}
]);
assert.equal(thermostat.children[1].textContent,'Ist-Temperatur: 21,8\u00a0\u00b0C');
assert.equal(thermostat.children[3].textContent,'Soll-Temperatur: 22,5\u00a0\u00b0C');
assert.equal(thermostat.children[5].textContent,'Heizmodus: Heizen');
assert.deepEqual(thermostat.children.filter(el=>el.tag==='time').map(el=>el.dateTime),[
 '2026-10-03T09:10:11.123Z','2026-10-02T08:00:00.000Z','2026-09-30T07:00:00.000Z'
],'Every displayed thermostat endpoint retains its own reception time');
assert.equal(thermostat.children[6].dataset.archived,'true');
assert.ok(thermostat.children[6].textContent.startsWith('Archivierter Empfang: '));
for(const invalid of [undefined,null,0,-1,123,true,'','Invalid Date','<script>','2026-10-03T09:10:11',
 '2026-02-30T09:10:11Z','2025-02-29T09:10:11Z','2026-00-03T09:10:11Z','2026-13-03T09:10:11Z',
 '2026-10-00T09:10:11Z','2026-10-03T24:10:11Z','2026-10-03T09:60:11Z','2026-10-03T09:10:60Z',
 '2026-10-03T09:10:11+24:00','2026-10-03T09:10:11+00:60','0000-10-03T09:10:11Z']){
 const block=receivedCard('lights',[{value:'1',time:invalid}]);
 assert.equal(block.children[2].tag,'small');
 assert.equal(block.children[2].textContent,'Empfangszeit unbekannt','Missing/invalid time is never converted to an epoch or guessed date');
 assert.equal(block.children[2].dateTime,undefined);
}
assert.equal(receivedCard('lights',[{value:'1',time:'2028-02-29T09:10:11.123456Z'}]).children[2].dateTime,'2028-02-29T09:10:11.123Z');
const archived=receivedCard('lights',[{value:'0',time:iso,provenance:'candidate_archive'}],'fr').children[2];
assert.equal(archived.dataset.archived,'true','Archived provenance is explicit even without a historical kind');
assert.ok(archived.textContent.startsWith('R\u00e9ception archiv\u00e9e : '));
const archiveUnknown=receivedCard('lights',[{value:'1',kind:'historical'}],'fr').children[2];
assert.equal(archiveUnknown.textContent,'R\u00e9ception archiv\u00e9e : Heure de r\u00e9ception inconnue');
const clock=receivedCard('clocks',[{value:'9;05',time:iso}]);
assert.equal(clock.children[0].textContent,'09:05','Dovit clock value is distinct from reception time');
assert.equal(clock.children[1].dateTime,new Date(iso).toISOString());
const alarm=receivedCard('alarms',[
 {value:'unexpected',device_id:19,statetype:1,time:iso},
 {value:'<script>',device_id:19,statetype:2,time:'2026-10-02T08:00:00Z'}
]);
assert.equal(alarm.children[0].textContent,'Signal empfangen','Unsupported values remain uninterpreted');
assert.equal(alarm.children[1].textContent,'ID 19 / ST 1');
assert.equal(alarm.children[3].textContent,'ID 19 / ST 2','Multiple uninterpreted signal receptions are distinguished by endpoint');
assert.equal(receivedCard('unknown',[{value:'1',time:iso}]),undefined,'Unknown cards keep their separate diagnostics presentation');
assert.equal(receivedCard('lights',[]),undefined,'No reception is fabricated before the first report');
const nativeDate=context.Date||Date;
let localFormatting;
context.Date=class extends Date{
 toLocaleString(locale,options){localFormatting={locale,options};return 'browser-local-time';}
};
assert.equal(receivedCard('lights',[{value:'1',time:iso}],'fr').children[2].textContent,'Re\u00e7u : browser-local-time');
assert.equal(localFormatting.locale,'fr-FR');
assert.equal(localFormatting.options,undefined,'No forced UTC or arbitrary timezone overrides the browser setting');
context.Date=nativeDate;
console.log('State labels passed: DE/FR, individual reception times, archive/invalid timestamps, browser timezone, raw diagnostics, precision and no inferred cover endpoint.');
