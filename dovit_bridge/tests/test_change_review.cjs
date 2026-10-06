const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const web=path.join(__dirname,'../dovit_bridge/web');
const context=vm.createContext({navigator:{language:'de'},localStorage:{getItem:()=>null},groupNames:{lights:'Lichter'},
 document:{createElement:tag=>({tag,dataset:{},children:[],append(child){this.children.push(child);}})}});
vm.runInContext(fs.readFileSync(path.join(web,'i18n.js'),'utf8'),context);
const app=fs.readFileSync(path.join(web,'app.js'),'utf8');
vm.runInContext(app.slice(app.indexOf('const node='),app.indexOf('const time=')),context);
vm.runInContext(fs.readFileSync(path.join(web,'change-review.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
context.draft={changed:['lights:19'],removed:['lights:21'],covers_reset_to_legacy:['shutters:20']};
for(const lang of ['de','fr']){
 run('language='+JSON.stringify(lang));const lines=run('changeReviewLines(draft,true)');
 assert.equal(lines.length,7);assert.ok(lines[0].includes('1'));assert.ok(lines[1].includes('1'));assert.ok(lines[4].includes('1'));
 assert.ok(lines[2].includes('lights:19'),'Legacy summaries retain the changed identifier without metadata');
 assert.ok(lines[3].includes('lights:21'),'Legacy summaries retain the removed identifier without metadata');
 assert.ok(!lines.some(line=>line.includes('review_')));
}
const unsafe='<img src=x onerror=alert(1)>';context.draft={category:'lights',configuration:{name:unsafe}};
const container={replaceChildren(){this.children=[];},append(child){this.children.push(child);}};context.container=container;
assert.equal(run('renderChangeReview(container,draft,false)'),true,'Actual node factory creates a nonempty readable review');
assert.ok(container.children[0].children[0].textContent.includes(unsafe),'Names stay plain text');
assert.ok(!container.children.some(child=>child.innerHTML),'No markup injection');
for(const [lang,prefix,category] of [['de','Zuordnung:','Lichter'],['fr','Affectation :','Éclairages']]){
 run('language='+JSON.stringify(lang));
 context.draft={category:'lights',device_id:'999',configuration:{name:'TEST',statetype:3}};
 assert.equal(run('renderChangeReview(container,draft,false)'),true);
 const list=container.children[0];assert.equal(list.className,'change-review');assert.equal(list.children.length,2);
 assert.ok(list.children[0].textContent.startsWith(prefix));assert.ok(list.children[0].textContent.includes(category));
 assert.ok(list.children[0].textContent.includes('TEST'),'Validated name is always visible');
 assert.ok(list.children.every(child=>child.tag==='li'&&child.textContent.length>0));
 assert.ok(!list.children.some(child=>child.hidden||child.innerHTML),'Review lines are visible plain text');
 assert.ok(run("t('review_unavailable')").includes(lang==='de'?'gesperrt':'bloqué'));
}
for(const [lang,changedPrefix,removedPrefix,category] of [['de','Neu oder angepasst:','Entfernen:','Lichter'],['fr','Ajout ou modification :','Retrait :','Éclairages']]){
 run('language='+JSON.stringify(lang));
 const literalName='New $& $\' {entry} <img src=x onerror=alert(1)>';
 context.draft={changed:['lights:19','lights:22'],removed:['lights:21'],
  changed_entries:[{uid:'lights:19',category:'lights',device_id:'19',name:literalName},
   {uid:'lights:22',category:'lights',device_id:'22',name:'review_restart'}],
  removed_entries:[{uid:'lights:21',category:'lights',device_id:'21',name:'Old light'}]};
 assert.equal(run('renderChangeReview(container,draft,true)'),true);
 const list=container.children[0],texts=list.children.map(child=>child.textContent);
 assert.equal(texts.length,7);
 assert.equal(texts[2],changedPrefix+' '+category+': '+literalName+' (lights:19).');
 assert.equal(texts[3],changedPrefix+' '+category+': review_restart (lights:22).','Device names are never interpreted as translation keys');
 assert.equal(texts[4],removedPrefix+' '+category+': Old light (lights:21).');
 assert.ok(list.children.every(child=>!child.innerHTML&&!child.hidden),'Affected devices remain visible text-only nodes');
 context.draft.changed_entries[0].name='Changed after validation';
 assert.equal(run('renderChangeReview(container,draft,true)'),true,'The retained summary can be rerendered in the selected language');
 assert.ok(container.children[0].children[2].textContent.includes('Changed after validation'));
}
run("language='de'");
for(const changedEntries of [undefined,null,{},['not metadata'],[{uid:'lights:99',category:'lights',device_id:'99',name:'Spoofed'}],
 [{uid:'lights:19',category:'alarms',device_id:'19',name:'Spoofed'}],
 [{uid:'lights:19',category:'lights',device_id:'99',name:'Spoofed'}],
 [{uid:'lights:19',category:'lights',device_id:19,name:'Spoofed'}],
 [{uid:'lights:19',category:'lights',device_id:'19',name:{text:'Spoofed'}}],
 [{uid:'lights:19',category:'lights',device_id:'19',name:'Bad\nname'}]]){
 context.draft={changed:['lights:19'],removed:[],changed_entries:changedEntries};
 const lines=run('changeReviewLines(draft,false)');
 assert.equal(lines.length,4);assert.equal(lines[2],'Neu oder angepasst: lights:19.','Malformed optional metadata cannot invent a name or category');
}
context.draft={changed:['lights:19'],removed:[],changed_entries:[{uid:'lights:19',category:'lights',device_id:'19'}]};
assert.equal(run('changeReviewLines(draft,false)[2]'),'Neu oder angepasst: Lichter (lights:19).','A nameless legacy entry still has a category and identity');
context.draft={changed:[null,17,{}],removed:[],changed_entries:[{uid:'lights:19',category:'lights',device_id:'19',name:'Spoofed'}]};
assert.equal(run('changeReviewLines(draft,false).length'),3,'Malformed legacy identifiers do not create named entries');
context.draft={changed:['alarms:87'],removed:[],changed_entries:[{uid:'alarms:87',category:'alarms',device_id:'87',name:'Spoofed alarm'}]};
assert.equal(run('changeReviewLines(draft,false)[2]'),'Neu oder angepasst: alarms:87.','Protected-category metadata is never accepted as validated human details');
for(const invalid of [null,{},[],{changed:['lights:19']},{changed:[],removed:null},{changed:[17],removed:[]},
 {changed:['lights:19','lights:19'],removed:[]},{changed:['lights:19'],removed:['lights:19']},
 {changed:['lights:019'],removed:[]},{changed:['lights:2147483648'],removed:[]},{changed:['alarms:87'],removed:[]}]){
 context.draft=invalid;
 assert.equal(run('renderChangeReview(container,draft,false)'),false,'Malformed or protected summaries never enable staging');
 assert.equal(container.children.length,0,'Failure leaves no stale readable review');
}
assert.equal(run('changeReviewLines(null,false).length'),1,'Absent old payload makes no invented count');
context.draft={category:'shutters',configuration:{name:'Cover',position_mode:'legacy'}};
assert.equal(run('changeReviewLines(draft,false).length'),2,'Already legacy does not invent a reset warning');
context.draft.covers_reset_to_legacy=['shutters:20'];
assert.equal(run('changeReviewLines(draft,false).length'),3,'Explicit single-cover reset is explained');
assert.equal(run('changeReviewLines({changed:[],removed:[]},false).length'),3,'No-op count and restart semantics stay explicit');
context.draft={changed:[],removed:[],changed_entries:[{uid:'lights:19',category:'lights',device_id:'19',name:'Not changed'}],removed_entries:[]};
assert.equal(run('changeReviewLines(draft,false).length'),3,'No-op does not list unrelated metadata');
assert.equal(run('renderChangeReview(container,draft,false)'),true,'Valid no-op remains reviewable with explicit zero counts');
console.log('Readable DE/FR changed/removed device details, legacy/malformed metadata fallback, identity/legacy warnings and text-only names passed.');
