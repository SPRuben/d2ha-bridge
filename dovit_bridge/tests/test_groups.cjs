// Synthetic DOM only. No network or device commands.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 focus(options){document.activeElement=this;this.focusOptions=options;}
}
const ids={devices:new Element('div'),'unknown-devices':new Element('div')};
const descendants=element=>element.children.flatMap(child=>child instanceof Element?[child,...descendants(child)]:[]);
const document={activeElement:null,getElementById:id=>ids[id],createElement:tag=>new Element(tag),
 querySelectorAll:()=>Object.values(ids).flatMap(descendants).filter(el=>el.dataset.deviceUid)};
const context=vm.createContext({document,
 setText:(el,text)=>{el.textContent=text;}});
const source=fs.readFileSync(path.join(__dirname,'../dovit_bridge/web/app.js'),'utf8');
vm.runInContext(source.slice(0,source.indexOf('function render(fresh')),context);
const run=code=>vm.runInContext(code,context);
run("renderDeviceGroups([{category:'clocks'},{category:'lights'},{category:'unknown'},{category:'lights'}],['clock','a','unknown','b'])");
assert.deepEqual(ids.devices.children.map(s=>s.dataset.category),['lights','clocks']);
assert.deepEqual(ids.devices.children[0].children[1].children,['a','b']);
assert.deepEqual(ids['unknown-devices'].children,['unknown']);
run("renderDeviceGroups([{category:'clocks'}],['clock'])");
assert.equal(ids.devices.children.length,1);
assert.equal(ids['unknown-devices'].children[0].textContent,'unknown_empty');
run('renderDeviceGroups([],[])');
assert.equal(ids.devices.children[0].textContent,'known_empty');
// Poll replacement preserves the same device, including unknown signals.
for(const category of ['lights','unknown']){
 const card=()=>{const c=new Element('article'),button=new Element('button');button.dataset.deviceUid='device:19';c.append(button);return c;};
 context.shown=[{category}];context.cards=[card()];run('renderDeviceGroups(shown,cards)');
 document.activeElement=context.cards[0].children[0];
 const previous=document.activeElement;context.cards=[card()];run('renderDeviceGroups(shown,cards)');
 assert.notEqual(document.activeElement,previous);
 assert.equal(document.activeElement,context.cards[0].children[0]);
 assert.equal(document.activeElement.focusOptions.preventScroll,true);
 const modalInput=new Element('input');document.activeElement=modalInput;
 context.cards=[card()];run('renderDeviceGroups(shown,cards)');
 assert.equal(document.activeElement,modalInput,'Polling must not steal dialog/input focus');
 document.activeElement=context.cards[0].children[0];run('renderDeviceGroups([],[])');
 assert.equal(document.querySelectorAll().length,0,'Removed device has no replacement focus target');
}
for(const [raw,expected] of [['15;44','15:44'],['0;5','00:05'],['23;59','23:59'],['24;00','24;00'],['12;60','12;60'],['-1;3','-1;3'],['abc','abc']]){
 context.raw=raw;
 assert.equal(run("displayValue({category:'clocks'},{value:raw})"),expected);
 assert.equal(run("displayValue({category:'lights'},{value:raw})"),raw);
}
console.log('Groups and clock display passed. No network used.');
