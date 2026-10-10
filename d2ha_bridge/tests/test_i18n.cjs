// Pure translation/DOM-contract tests; no browser or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../dovit_bridge/web');
const source = fs.readFileSync(path.join(web, 'i18n.js'), 'utf8');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const elements=[];
const context=vm.createContext({navigator:{language:'fr-LU'},localStorage:{getItem:()=>null},
 Node:{TEXT_NODE:3},document:{documentElement:{},querySelectorAll:selector=>selector==='[data-i18n]'?elements:[]}});
vm.runInContext(source,context);
const evaluate=code=>vm.runInContext(code,context);
assert.equal(evaluate('language'),'fr');
for(const key of [...html.matchAll(/data-i18n(?:-placeholder|-label)?="([^"]+)"/g)].map(m=>m[1])){
 assert.equal(evaluate(`Object.hasOwn(messages,${JSON.stringify(key)})`),true,key);
}
assert.equal(evaluate("t('Geraete suchen')"),'Rechercher un appareil');
for(const language of ['de','fr']){
 evaluate(`language=${JSON.stringify(language)}`);
 for(const classification of ['observed','inferred','confirmed']){
  for(const suffix of ['', '_hint']){
   const key='classification_'+classification+suffix;
   assert.notEqual(evaluate(`t(${JSON.stringify(key)})`),key);
  }
 }
 for(const status of ['requested','transmitted','observed','failed','timeout','uncertain']){
  const key='simulation_'+status;
  assert.notEqual(evaluate(`t(${JSON.stringify(key)})`),key);
 }
}
evaluate("language='fr'");
assert.equal(evaluate("t('light_transmitted')"),'Commande envoyée ; exécution non confirmée. En attente d’un état correspondant.');
evaluate("language='de'");
assert.equal(evaluate("t('light_transmitted')"),'Befehl gesendet; Ausführung unbestätigt. Warte auf passenden Status.');
evaluate("language='fr'");
assert.equal(evaluate("t('3 sichtbar')"),'3 affiché(s)');
assert.equal(evaluate("t('Endpunkt (99, 0) ist bereits zugeordnet')"),'Point de données (99, 0) déjà affecté');
assert.equal(evaluate("t('temp_step: endliche Zahl erforderlich')"),'temp_step : nombre fini obligatoire');
assert.equal(evaluate("t('Wohnzimmer 123')"),'Wohnzimmer 123');
const input={value:'Keep my draft'};
const label={dataset:{i18n:'Geraetename'},firstChild:{nodeType:3,nodeValue:'Geraetename'},children:[input]};
elements.push(label);
evaluate('translateStatic()');
assert.equal(label.firstChild.nodeValue,'Nom de l’appareil');
assert.equal(label.children[0],input);
assert.equal(input.value,'Keep my draft');
const checkbox={nodeType:1,checked:true};
const consentText={nodeType:3,nodeValue:'old label'};
const consent={dataset:{i18n:'edit_confirm_label'},firstChild:checkbox,childNodes:[checkbox,consentText],children:[checkbox]};
elements.push(consent);evaluate('translateStatic()');
assert.equal(consentText.nodeValue,evaluate("t('edit_confirm_label')"));
assert.equal(checkbox.checked,true,'Translation preserves consent checkbox before its text');
evaluate("language='de';translateStatic()");
assert.equal(label.firstChild.nodeValue,'Gerätename');
assert.equal(evaluate('document.documentElement.lang'),'de');
for(const pair of Object.values(evaluate('messages'))){assert.equal(pair.length,2);assert.ok(pair.every(v=>typeof v==='string'&&v.length));}
const fallback=vm.createContext({navigator:{language:'de-DE'},localStorage:{getItem(){throw Error('blocked');}}});
vm.runInContext(source,fallback);
assert.equal(vm.runInContext('language',fallback),'de');
// Raw names and JSON preview containers must not become translatable UI strings.
context.document.createElement=()=>({dataset:{},textContent:''});
const app=fs.readFileSync(path.join(web,'app.js'),'utf8');
evaluate(app.slice(0,app.indexOf('function render(fresh')));
assert.equal(evaluate("node('h3','Licht',undefined,true).textContent"),'Licht');
assert.equal(evaluate("node('h3','Licht',undefined,true).dataset.i18n"),undefined);
assert.equal(evaluate("node('pre','').dataset.i18n"),undefined);
evaluate("language='fr'");
assert.equal(evaluate("node('button','Entwurf speichern').textContent"),'Enregistrer le brouillon');
const saved=vm.createContext({navigator:{language:'de-DE'},localStorage:{getItem:()=> 'fr'}});
vm.runInContext(source,saved);
assert.equal(vm.runInContext('language',saved),'fr');
console.log('i18n tests passed: catalog, dynamic errors, locale fallback, form preservation');
