const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
// Small DOM contract double: the renderer must only create safe elements/text.
class Element {
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.textContent='';}
 append(...children){this.children.push(...children);}
 replaceChildren(){this.children=[];}
 get lastChild(){return this.children.at(-1);}
 set innerHTML(value){throw Error('Manual rendering must never parse HTML');}
}
const allowed=new Set(['p','code','strong','pre','h1','h2','h3','button','table','tr','th','td','ul','ol','li','figure','img','figcaption']);
const context=vm.createContext({document:{createElement(tag){assert.ok(allowed.has(tag),tag);return new Element(tag);},createTextNode(text){return {textContent:text};}}});
const source=fs.readFileSync(path.join(__dirname,'../dovit_bridge/web/help.js'),'utf8');
vm.runInContext(source.split("$('help-open').onclick")[0],context);
context.body=new Element('article');context.contents=new Element('nav');
context.sample='# Title\n\n## Section\n\nHello **bold** and `code`.\n\n| A | B |\n| --- | --- |\n| x | y |\n\n1. Item\n\n```html\n<script>bad()</script>\n```\n\n<img src=x onerror=bad()>\n';
vm.runInContext('renderManual(sample,body,contents)',context);
assert.equal(context.contents.children.length,1);
assert.equal(context.body.children.filter(e=>e.tagName==='TABLE').length,1);
assert.equal(context.body.children.find(e=>e.tagName==='TABLE').children.length,2);
assert.equal(context.body.children.find(e=>e.tagName==='PRE').textContent,'<script>bad()</script>\n');
assert.ok(context.body.children.some(e=>e.tagName==='OL'));
assert.ok(context.body.children.some(e=>e.tagName==='P'&&e.children.some(c=>c.textContent==='<img src=x onerror=bad()>')));
const render=sample=>{
 context.sample=sample;vm.runInContext('renderManual(sample,body,contents)',context);return context.body;
};
const descendants=element=>[element,...(element.children||[]).flatMap(descendants)];
const stems=['devices-overview','setup-dovit','setup-mqtt','setup-publication','device-assignment','diagnosis','json-review','recovery'];
const paths=stems.flatMap(stem=>['de','fr'].map(locale=>'images/'+stem+'-'+locale+'.jpg'));
assert.equal(paths.length,16);
for(const imagePath of paths){
 const description=imagePath.endsWith('-fr.jpg')?'Simulation : éclairage du bureau':'Simulation: Bürolicht zuordnen';
 const body=render('!['+description+']('+imagePath+')');
 assert.equal(body.children.length,1,imagePath);
 const figure=body.children[0];assert.equal(figure.tagName,'FIGURE');assert.equal(figure.className,'manual-screenshot');
 assert.deepEqual(figure.children.map(child=>child.tagName),['IMG','FIGCAPTION']);
 const [image,caption]=figure.children;
 assert.equal(image.src,'manuals/'+imagePath,'Image stays relative to the Ingress page');
 assert.equal(image.alt,description);assert.equal(caption.textContent,description);
 assert.equal(image.loading,'lazy');assert.equal(image.decoding,'async');
 assert.equal(caption.children.length,0,'Captions remain plain text');
}
const unsafePaths=[
 'https://example.org/devices-overview-de.jpg','http://example.org/a.jpg','//example.org/a.jpg',
 'javascript:alert(1)','data:image/jpeg;base64,AAAA','/manuals/images/devices-overview-de.jpg',
 'manuals/images/devices-overview-de.jpg','images/../devices-overview-de.jpg',
 'images/%2e%2e/devices-overview-de.jpg','images/devices-overview-de.svg',
 'images/devices-overview-de.jpg?tracking=yes','images/devices-overview-de.jpg#fragment',
 'images/devices-overview-en.jpg','images/devices-overview-de.JPG','images/not-allowed-de.jpg',
 'images/devices-overview-de.jpg" onerror="alert(1)','images\\devices-overview-de.jpg',
 'images//devices-overview-de.jpg','images/devices-overview-de.png'
];
for(const imagePath of unsafePaths){
 const body=render('![Untrusted]('+imagePath+')');
 assert.equal(descendants(body).filter(element=>element.tagName==='IMG').length,0,imagePath);
}
for(const markup of [
 '<img src="manuals/images/devices-overview-de.jpg" onerror="bad()">',
 '<script>bad()</script>',
 'Before ![Caption](images/devices-overview-de.jpg)',
 '![Caption](images/devices-overview-de.jpg) after',
 '  ![Caption](images/devices-overview-de.jpg)',
 '![Caption](images/devices-overview-de.jpg "unapproved title")'
]){
 const body=render(markup);
 assert.equal(descendants(body).filter(element=>element.tagName==='IMG').length,0,markup);
}
const literalCaption='<script>alert("x")</script> & **plain** `code` <img src=x onerror=bad()> <b>français</b>';
const literalFigure=render('!['+literalCaption+'](images/devices-overview-de.jpg)').children[0];
assert.equal(literalFigure.children[0].alt,literalCaption);
assert.equal(literalFigure.children[1].textContent,literalCaption);
assert.equal(literalFigure.children[1].children.length,0,'Caption markup is never parsed or formatted');
assert.equal(Object.hasOwn(literalFigure.children[0],'onerror'),false);
let body=render('First paragraph\n![Caption](images/devices-overview-de.jpg)\nFollowing paragraph');
assert.deepEqual(body.children.map(element=>element.tagName),['P','FIGURE','P'],'Images flush paragraph boundaries');
body=render('- First item\n![Caption](images/devices-overview-de.jpg)\n- Second item');
assert.deepEqual(body.children.map(element=>element.tagName),['UL','FIGURE','UL'],'An image ends the previous list');
assert.equal(body.children[0].children.length,1);assert.equal(body.children[2].children.length,1);
body=render('| Heading |\n| --- |\n| First |\n![Caption](images/devices-overview-de.jpg)\n| Next |');
assert.deepEqual(body.children.map(element=>element.tagName),['TABLE','FIGURE','TABLE'],'An image ends the previous table');
body=render('```markdown\n![Caption](images/devices-overview-de.jpg)\n```');
assert.equal(body.children[0].tagName,'PRE');assert.equal(descendants(body).filter(element=>element.tagName==='IMG').length,0,'Code blocks keep image syntax literal');
const css=fs.readFileSync(path.join(__dirname,'../dovit_bridge/web/help.css'),'utf8');
assert.match(css,/\.manual-screenshot img\{[^}]*max-width:100%[^}]*height:auto/,'Tutorial images shrink without distortion');
for(const name of ['USER_DE.md','USER_FR.md','DEVELOPER.md']){
 context.sample=fs.readFileSync(path.join(__dirname,'../dovit_bridge/manuals',name),'utf8');
 vm.runInContext('renderManual(sample,body,contents)',context);
 assert.ok(context.contents.children.length>=5,name);
 assert.equal(context.body.children[0].tagName,'H1');
}
console.log('Manual renderer tests passed: three manuals, 16 local JPEGs, captions, Ingress paths, blocked URLs/markup, paragraph/list/table boundaries.');
