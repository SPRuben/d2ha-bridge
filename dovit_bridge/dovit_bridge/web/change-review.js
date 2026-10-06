'use strict';
function changeReviewEntry(uid,entries){
 const entry=Array.isArray(entries)?entries.find(item=>item&&typeof item==='object'&&!Array.isArray(item)&&item.uid===uid):null;
 const match=/^(lights|shutters|motions|contacts|thermostats):(0|[1-9][0-9]*)$/.exec(uid);
 if(!entry||!match||Number(match[2])>2147483647||entry.category!==match[1]||entry.device_id!==match[2])return uid;
 if(entry.name!==undefined&&(typeof entry.name!=='string'||!entry.name.trim()||entry.name.length>80||/[\u0000-\u001f]/.test(entry.name)))return uid;
 const label=t(groupNames[entry.category]||entry.category);
 return label+(entry.name===undefined?'':': '+entry.name)+' ('+uid+')';
}

function changeReviewLines(draft,identityChanged){
 const lines=[];
 if(Array.isArray(draft?.changed)&&Array.isArray(draft?.removed)){
  lines.push(t('review_changed').replace('{count}',String(draft.changed.length)));
  lines.push(t('review_removed').replace('{count}',String(draft.removed.length)));
  for(const kind of ['changed','removed'])for(const uid of draft[kind]){
   if(typeof uid==='string'&&uid.trim())lines.push(t('review_'+kind+'_entry').replace('{entry}',()=>changeReviewEntry(uid,draft[kind+'_entries'])));
  }
 }else if(draft?.configuration){
  const label=t(groupNames[draft.category]||'Kategorie');
  lines.push(t('review_assignment').replace('{category}',()=>label).replace('{name}',()=>String(draft.configuration.name||'')));
 }
 if(draft?.covers_reset_to_legacy?.length)lines.push(t('review_legacy').replace('{count}',String(draft.covers_reset_to_legacy.length)));
 if(identityChanged)lines.push(t('review_identity'));
 lines.push(t('review_restart'));
 return lines;
}

function renderChangeReview(container,draft,identityChanged){
 container.replaceChildren();
 if(!draft||typeof draft!=='object'||Array.isArray(draft))return false;
 if('changed' in draft||'removed' in draft){
  if(!Array.isArray(draft.changed)||!Array.isArray(draft.removed))return false;
  const identifiers=[...draft.changed,...draft.removed];
  if(new Set(identifiers).size!==identifiers.length||!identifiers.every(uid=>typeof uid==='string'
   &&/^(lights|shutters|motions|contacts|thermostats):(0|[1-9][0-9]*)$/.test(uid)&&Number(uid.split(':')[1])<=2147483647))return false;
 }else if(!draft.configuration)return false;
 const list=node('ul','','change-review');
 for(const line of changeReviewLines(draft,identityChanged))list.append(node('li',line,undefined,true));
 container.append(list);
 return list.children.length>0;
}
