'use strict';

// Deliberately restricted Markdown: all source text is inserted as text nodes,
// never as HTML. Only these bundled tutorial images may be embedded.
const manualImages=new Set([
 'devices-overview','setup-dovit','setup-mqtt','setup-publication',
 'device-assignment','diagnosis','json-review','recovery'
].flatMap(name=>['de','fr'].map(locale=>'images/'+name+'-'+locale+'.jpg')));
function manualInline(element, text) {
 for (const part of text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g)) {
  if (part.startsWith('`') && part.endsWith('`')) {
   const code=document.createElement('code');code.textContent=part.slice(1,-1);element.append(code);
  } else if(part.startsWith('**') && part.endsWith('**')) {
   const strong=document.createElement('strong');strong.textContent=part.slice(2,-2);element.append(strong);
  } else element.append(document.createTextNode(part));
 }
}

function renderManual(text, body, contents) {
 body.replaceChildren();contents.replaceChildren();
 let paragraph=[], code=null, list=null, table=null, headingNumber=0;
 const flush=()=>{if(paragraph.length){const p=document.createElement('p');manualInline(p,paragraph.join(' '));body.append(p);paragraph=[];}};
 for(const line of text.split(/\r?\n/)){
  if(line.startsWith('```')){flush();list=null;table=null;if(code){body.append(code);code=null;}else{code=document.createElement('pre');}continue;}
  if(code){code.textContent+=line+'\n';continue;}
  const screenshot=line.match(/^!\[([^\]]*)\]\((images\/[^()\s]+)\)$/);
  if(screenshot&&manualImages.has(screenshot[2])){
   flush();list=null;table=null;
   const figure=document.createElement('figure');figure.className='manual-screenshot';
   const image=document.createElement('img');image.src='manuals/'+screenshot[2];image.alt=screenshot[1];
   image.loading='lazy';image.decoding='async';
   const caption=document.createElement('figcaption');caption.textContent=screenshot[1];
   figure.append(image,caption);body.append(figure);continue;
  }
  const heading=line.match(/^(#{1,3}) (.+)$/);
  if(heading){flush();list=null;table=null;const h=document.createElement('h'+heading[1].length);h.textContent=heading[2];h.id='manual-section-'+headingNumber++;body.append(h);if(heading[1].length>1){const button=document.createElement('button');button.type='button';button.textContent=heading[2];button.onclick=()=>{h.scrollIntoView({block:'start'});h.tabIndex=-1;h.focus({preventScroll:true});};contents.append(button);}continue;}
  if(line.startsWith('|')){flush();list=null;if(/^\|[\s:|\-]+\|$/.test(line))continue;if(!table){table=document.createElement('table');body.append(table);}const row=document.createElement('tr');const tag=table.children.length?'td':'th';for(const cell of line.slice(1,-1).split('|')){const td=document.createElement(tag);manualInline(td,cell.trim());row.append(td);}table.append(row);continue;}
  table=null;
  const item=line.match(/^(?:- |\d+\. )(.+)$/);
  if(item){flush();const kind=line.startsWith('-')?'ul':'ol';if(!list||list.tagName.toLowerCase()!==kind){list=document.createElement(kind);body.append(list);}const li=document.createElement('li');manualInline(li,item[1]);list.append(li);continue;}
  if(!line.trim()){flush();list=null;continue;}
  if(list&&line.startsWith('  ')){manualInline(list.lastChild,' '+line.trim());continue;}
  list=null;paragraph.push(line);
 }
 flush();if(code)body.append(code);
}

$('help-open').onclick=()=>{
 const dialog=document.createElement('dialog');dialog.className='manual-dialog';dialog.setAttribute('aria-labelledby','manual-title');
 const title=node('h2',t('help_title'),undefined,true);title.id='manual-title';
 const select=document.createElement('select');select.setAttribute('aria-label',t('help_select'));
 for(const [value,label] of [['USER_DE.md','help_de'],['USER_FR.md','help_fr'],['DEVELOPER.md','help_dev']]){const option=node('option',t(label),undefined,true);option.value=value;select.append(option);}
 select.value=language==='fr'?'USER_FR.md':'USER_DE.md';
 const close=node('button',t('Schliessen'),undefined,true);close.type='button';close.onclick=()=>dialog.close();
 const notice=node('p',t('help_notice'),undefined,true), status=node('p','');status.setAttribute('role','status');
 const layout=document.createElement('div');layout.className='manual-layout';
 const contents=document.createElement('nav');contents.setAttribute('aria-label',t('help_contents'));
 const body=document.createElement('article');body.className='manual-body';layout.append(contents,body);
 dialog.append(title,select,close,notice,status,layout);document.body.append(dialog);
 let requestNumber=0, controller=null;
 async function load(){const request=++requestNumber;controller?.abort();controller=new AbortController();body.replaceChildren();contents.replaceChildren();status.textContent=t('help_loading');
  try{const response=await fetch('manuals/'+select.value,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error();const text=await response.text();if(request!==requestNumber||!dialog.open)return;body.lang=select.value==='USER_FR.md'?'fr':'de';contents.lang=body.lang;renderManual(text,body,contents);status.textContent='';dialog.scrollTop=0;}
  catch{if(request===requestNumber&&dialog.open)status.textContent=t('help_error');}
 }
 select.onchange=load;dialog.addEventListener('close',()=>{requestNumber++;controller?.abort();dialog.remove();$('help-open').focus();});dialog.showModal();load();
};
