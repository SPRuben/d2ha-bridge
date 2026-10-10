'use strict';
let jsonRevision=null,jsonDirty=false,jsonValidated=null,jsonReviewDraft=null,jsonLoaded=false,jsonPending=false,jsonBusy=false,jsonPendingVersion=0;
function jsonRefreshConsent(){
 $('json-save').disabled=jsonBusy||jsonPending||!jsonValidated||jsonValidated.document!==$('json-text').value
  ||!$('json-confirm').checked||(!$('json-identity-label').hidden&&!$('json-identity').checked);
}
$('json-confirm').onchange=jsonRefreshConsent;
$('json-identity').onchange=jsonRefreshConsent;
function jsonInvalidate(){
 jsonValidated=null;jsonReviewDraft=null;$('json-save').disabled=true;$('json-confirm').checked=false;$('json-identity').checked=false;
 $('json-identity-label').hidden=true;
 $('json-review').hidden=true;$('json-details').open=false;$('json-summary').textContent='';$('json-format').disabled=true;
}
function jsonPendingState(pending){
 if(jsonPending!==pending)jsonPendingVersion++;
 jsonPending=pending;$('json-cancel').hidden=!pending;$('json-check').disabled=pending;
}
function jsonSyncPending(pending){
 if(!jsonLoaded||pending===jsonPending)return;
 if(jsonPending&&!pending)jsonDirty=true;
 jsonPendingState(pending);jsonInvalidate();
 setText($('json-status'),pending?'edit_pending':jsonDirty?'json_dirty':'json_loaded');
}
async function loadJson(){
 if(jsonBusy||jsonDirty&&!window.confirm(t('json_discard')))return;
 jsonBusy=true;$('json-load').disabled=true;$('json-text').disabled=true;$('json-format').disabled=true;
 try{
  const snapshot=await editorRequest();if(snapshot.disabled)throw Error('edit_disabled');
  $('json-text').value=snapshot.document;jsonRevision=snapshot.revision;jsonLoaded=true;jsonDirty=false;
  jsonInvalidate();jsonPendingState(snapshot.pending);$('json-text').disabled=false;
  setText($('json-status'),snapshot.pending?'edit_pending':'json_loaded');
 }catch(error){setText($('json-status'),error.message);}
 finally{jsonBusy=false;$('json-load').disabled=false;$('json-text').disabled=!jsonLoaded;$('json-format').disabled=!jsonValidated||jsonPending;}
}
function selectView(view){
 if(!['graphic','json'].includes(view))return;
 const isJson=view==='json';$('graphic-panel').hidden=isJson;$('json-panel').hidden=!isJson;
 if(isJson&&!jsonLoaded)loadJson();
}
$('json-load').onclick=loadJson;
$('json-text').oninput=()=>{jsonDirty=true;jsonInvalidate();setText($('json-status'),'json_dirty');};
$('json-format').onclick=()=>{
 if(jsonBusy||jsonPending)return;
 // Formatting happens only after server validation, so duplicate keys cannot disappear silently.
 if(!jsonValidated||jsonValidated.document!==$('json-text').value){setText($('json-status'),'json_check_first');return;}
 $('json-text').value=JSON.stringify(JSON.parse($('json-text').value),null,2)+'\n';
 jsonDirty=true;jsonInvalidate();setText($('json-status'),'json_dirty');
};
$('json-check').onclick=async()=>{
 if(jsonBusy||!jsonLoaded||jsonPending)return;
 const payload={operation:'replace_json',revision:jsonRevision,document:$('json-text').value};
 const pendingVersion=jsonPendingVersion;
 jsonInvalidate();jsonBusy=true;$('json-check').disabled=true;
 try{
  const answer=await editorRequest('validate',payload);
  if(payload.document!==$('json-text').value||pendingVersion!==jsonPendingVersion)return;
  if(!Array.isArray(answer.draft?.changed)||!Array.isArray(answer.draft?.removed)
   ||typeof renderChangeReview!=='function'||renderChangeReview($('json-readable-review'),answer.draft,answer.identity_changed)!==true)
   throw Error('review_unavailable');
  jsonValidated=payload;jsonReviewDraft={draft:answer.draft,identityChanged:answer.identity_changed};
  $('json-summary').textContent=JSON.stringify(answer.draft,null,2);
  $('json-review').hidden=false;$('json-tools').open=false;$('json-format').disabled=false;
  $('json-identity-label').hidden=!answer.identity_changed;jsonRefreshConsent();
  setText($('json-status'),'json_valid');
 }catch(error){
  if(payload.document===$('json-text').value&&pendingVersion===jsonPendingVersion)setText($('json-status'),error.message);
 }
 finally{jsonBusy=false;$('json-check').disabled=jsonPending;jsonRefreshConsent();}
};
$('json-save').onclick=async()=>{
 if(jsonBusy||jsonPending||!jsonValidated||jsonValidated.document!==$('json-text').value)return;
 if(!$('json-confirm').checked||!$('json-identity-label').hidden&&!$('json-identity').checked){setText($('json-status'),'edit_confirm');return;}
 const payload={...jsonValidated,confirm:true,confirm_identity:$('json-identity').checked};
 const restoreFocus=document.activeElement===$('json-save');
 jsonBusy=true;$('json-text').disabled=true;$('json-save').disabled=true;$('json-format').disabled=true;
 try{
  await editorRequest('save',payload);jsonDirty=false;jsonInvalidate();jsonPendingState(true);
  setText($('json-status'),'edit_pending');await editorStatus();
 }catch{jsonInvalidate();await editorStatus();setText($('json-status'),'edit_uncertain');}
 finally{
  jsonBusy=false;$('json-text').disabled=false;
  if(restoreFocus&&(document.activeElement===$('json-save')||document.activeElement===document.body)){
   $(jsonPending?'json-cancel':'json-check').focus();
  }
 }
};
$('json-cancel').onclick=async()=>{
 if(jsonBusy||!window.confirm(t('edit_cancel_confirm')))return;
 jsonBusy=true;
 try{await editorRequest('cancel',{confirm:true});jsonDirty=true;jsonPendingState(false);jsonInvalidate();setText($('json-status'),'json_dirty');await editorStatus();}
 catch(error){setText($('json-status'),error.message);}
 finally{jsonBusy=false;}
};
window.addEventListener('beforeunload',event=>{if(jsonDirty){event.preventDefault();event.returnValue='';}});
$('language').addEventListener('change',()=>{
 if(!jsonValidated||!jsonReviewDraft)return;
 try{
  if(renderChangeReview($('json-readable-review'),jsonReviewDraft.draft,jsonReviewDraft.identityChanged)!==true)throw Error();
 }catch{jsonInvalidate();setText($('json-status'),'review_unavailable');}
});
