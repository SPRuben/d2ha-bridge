'use strict';
const catalog={
 language:['Sprache','Langue'],eyebrow:['LOKALE WIEDERHERSTELLUNG','RESTAURATION LOCALE'],title:['Gerätedatei wiederherstellen','Restaurer le fichier des appareils'],
 intro:['Nur die Gerätedatei wird wiederhergestellt. Keine Gerätebefehle und kein automatischer Neustart.','Seul le fichier des appareils est restauré. Aucune commande d’appareil ni aucun redémarrage automatique.'],
 source:['1. Quelle auswählen','1. Choisir une source'],backup:['Server-Backup','Sauvegarde du serveur'],own:['Eigene JSON-Datei oder Text','Fichier JSON ou texte personnel'],file:['JSON hochladen','Importer du JSON'],file_hint:['Nur .json, maximal 256 KiB. Inhalt vor dem Anwenden prüfen.','Uniquement .json, maximum 256 Kio. Vérifiez le contenu avant application.'],document:['JSON einfügen','Coller du JSON'],validate:['Quelle prüfen','Vérifier la source'],review:['2. Prüfergebnis bestätigen','2. Confirmer la vérification'],confirm:['Ich möchte diese geprüfte Gerätedatei wiederherstellen.','Je souhaite restaurer ce fichier vérifié.'],alarm:['Ich bestätige die enthaltenen Alarmzuordnungen.','Je confirme les affectations d’alarme incluses.'],empty:['Ich bestätige eine leere Gerätedatei ohne Zuordnungen.','Je confirme un fichier vide sans affectations.'],apply:['Geprüfte Datei wiederherstellen','Restaurer le fichier vérifié'],restart_title:['Nächster Schritt','Prochaine étape'],restart:['Wiederherstellung gespeichert. Starte die Bridge selbst neu, wenn du bereit bist. Diese Seite führt keinen Neustart aus.','Restauration enregistrée. Redémarrez vous-même le pont lorsque vous êtes prêt. Cette page ne redémarre rien.'],
 loading:['Status wird geladen …','Chargement du statut…'],ready:['Quelle auswählen und prüfen.','Choisissez et vérifiez une source.'],changed:['Quelle geändert. Erneut prüfen.','Source modifiée. Vérifiez à nouveau.'],reading:['Datei wird gelesen …','Lecture du fichier…'],checking:['Quelle wird geprüft …','Vérification de la source…'],checked:['Quelle geprüft. Bestätigungen erforderlich.','Source vérifiée. Confirmations requises.'],applying:['Wiederherstellung angefordert. Nicht erneut senden.','Restauration demandée. Ne renvoyez pas la requête.'],uncertain:['Antwort unklar. Nicht erneut anwenden. Status prüfen lassen, bevor du neu startest oder diese Seite neu lädst.','Réponse incertaine. Ne réappliquez pas. Faites vérifier le statut avant de redémarrer ou recharger cette page.'],counts:['Anzahl je Kategorie','Nombre par catégorie'],names:['Gerätenamen','Noms des appareils'],
 recovery_file_invalid:['Bitte eine .json-Datei bis 256 KiB auswählen.','Choisissez un fichier .json de 256 Kio maximum.'],recovery_read_error:['Datei nicht lesbar.','Fichier illisible.'],recovery_error:['Wiederherstellung nicht möglich. Quelle und Serverstatus prüfen.','Restauration impossible. Vérifiez la source et le statut du serveur.'],recovery_invalid:['Ungültige Gerätedatei.','Fichier des appareils invalide.'],recovery_stale:['Dateistand geändert. Quelle erneut prüfen.','Version modifiée. Vérifiez à nouveau la source.'],recovery_disabled:['Wiederherstellung nicht verfügbar.','Restauration indisponible.'],recovery_token:['Sitzung ungültig. Status prüfen.','Session invalide. Vérifiez le statut.'],recovery_backup:['Backup nicht verfügbar oder ungültig.','Sauvegarde indisponible ou invalide.']
};
Object.assign(catalog,{
 new_install:['Neue Installation vorbereiten','Préparer une nouvelle installation'],
 new_install_hint:['Nur für eine wirklich neue Anlage ohne vorhandene Zuordnungen. Nach einer Wiederherstellung zuerst deine Sicherung wählen. Dieser Button bereitet nur einen leeren Entwurf vor; Prüfung und Bestätigungen bleiben erforderlich.','Uniquement pour une installation réellement nouvelle sans affectations. Après une restauration, choisissez d’abord votre sauvegarde. Ce bouton prépare seulement un brouillon vide ; vérification et confirmations restent obligatoires.'],
 recovery_source:['Genau eine gültige Quelle auswählen.','Choisissez une seule source valide.'],
 recovery_size:['Die Gerätedatei ist zu groß (maximal 256 KiB).','Le fichier est trop volumineux (maximum 256 Kio).'],
 recovery_cleanup:['Quelle enthält nicht unterstützte Bereinigungsdaten. Andere Quelle wählen.','La source contient des données de nettoyage non prises en charge. Choisissez une autre source.'],
 recovery_restart:['Wiederherstellung beendet. Bridge manuell neu starten.','Restauration terminée. Redémarrez le pont manuellement.'],
 recovery_unreadable:['Quelle nicht lesbar. Andere Quelle wählen.','Source illisible. Choisissez une autre source.'],
 recovery_pending:['Eine bestehende Geräteänderung ist vorgemerkt und bleibt erhalten. Bitte manuell klären; die Wiederherstellung verwirft keinen Entwurf.','Une modification d’appareils est déjà en attente et reste préservée. Résolvez-la manuellement ; la restauration ne supprime aucun brouillon.'],
 recovery_confirm:['Bitte die Wiederherstellung ausdrücklich bestätigen.','Veuillez confirmer explicitement la restauration.'],
 recovery_alarm_confirm:['Bitte die Alarmzuordnungen bestätigen.','Veuillez confirmer les affectations d’alarme.'],
 recovery_empty_confirm:['Bitte die leere Gerätedatei bestätigen.','Veuillez confirmer le fichier vide.'],
 recovery_storage:['Speichern fehlgeschlagen. Status prüfen, nicht blind erneut anwenden.','Échec d’enregistrement. Vérifiez le statut ; ne réappliquez pas aveuglément.'],
 recovery_only:['Diese Aktion ist nur im Wiederherstellungsmodus verfügbar.','Cette action est disponible uniquement en mode restauration.'],
 recovery_unknown:['Quelle unbekannt. Andere Quelle wählen.','Source inconnue. Choisissez une autre source.'],
 names_truncated:['Namensliste gekürzt; Kategorie-Anzahlen gelten für die gesamte Datei.','Liste des noms abrégée ; les nombres par catégorie concernent le fichier entier.'],
 backup_valid:['prüfbar','à vérifier'],backup_unavailable:['nicht verfügbar','indisponible'],
 inactive:['Dovit- und MQTT-Verbindungen sind im Wiederherstellungsmodus inaktiv.','Les connexions Dovit et MQTT sont inactives en mode restauration.'],
 current_missing:['Aktuelle Gerätedatei fehlt.','Le fichier actuel des appareils est absent.'],
 current_invalid:['Aktuelle Gerätedatei ist ungültig.','Le fichier actuel des appareils est invalide.'],
 current_unreadable:['Aktuelle Gerätedatei ist nicht lesbar. Vor der Wiederherstellung manuell klären.','Le fichier actuel est illisible. Résolvez ce problème manuellement avant la restauration.'],
 current_oversized:['Aktuelle Gerätedatei ist zu groß. Vor der Wiederherstellung manuell klären.','Le fichier actuel est trop volumineux. Résolvez ce problème manuellement avant la restauration.'],
 current_valid:['Aktuelle Gerätedatei ist lesbar.','Le fichier actuel des appareils est lisible.'],
 current_unknown:['Status der aktuellen Gerätedatei nicht verfügbar.','Statut du fichier actuel indisponible.'],
 category_switches:['Schalter','Interrupteurs'],category_lights:['Lichter','Éclairages'],category_shutters:['Rollläden','Volets'],category_thermostats:['Thermostate','Thermostats'],category_motions:['Bewegungsmelder','Détecteurs de mouvement'],category_contacts:['Kontakte','Contacts'],category_alarms:['Alarm','Alarmes'],category_clocks:['Uhren','Horloges'],category_unknown:['Weitere Geräte','Autres appareils']
});
const $=id=>document.getElementById(id);
let language='de',snapshot=null,validated=null,uploadBytes=null,generation=0,busy=false,locked=false,reading=false,statusKey='loading';
const t=key=>(catalog[key]||catalog.recovery_error)[language==='fr'?1:0];
function status(key){statusKey=key;$('status').textContent=t(key);}
function recoveryFocus(primary,target,wasFocused){
 if(wasFocused&&primary.isConnected!==false&&target.isConnected!==false
  &&(document.activeElement===primary||document.activeElement===document.body))target.focus();
}
function currentState(){if(snapshot){const key='current_'+snapshot.current.state;$('current-state').textContent=t(Object.hasOwn(catalog,key)?key:'current_unknown');}}
function categoryName(key){return t(Object.hasOwn(catalog,'category_'+key)?'category_'+key:'category_unknown');}
function translate(){document.documentElement.lang=language;document.querySelectorAll('[data-text]').forEach(el=>el.textContent=t(el.dataset.text));for(const option of $('backup').children){if(option.dataset.backupName)option.textContent=option.dataset.backupName+' · '+t(option.dataset.stateKey);}currentState();status(statusKey);if(validated)renderSummary(validated.summary);}
function controls(){
 const first=$('new-install');first.hidden=!snapshot||snapshot.current.state!=='missing';first.disabled=locked||busy||!snapshot;
 $('new-install-hint').hidden=first.hidden;
 for(const id of ['backup','file','document','validate'])$(id).disabled=locked||busy||!snapshot;
 $('validate').disabled=locked||busy||reading||!snapshot;
 $('file').disabled=$('document').disabled=locked||busy||!snapshot||!!$('backup').value;
 for(const id of ['confirm','confirm-alarm','confirm-empty'])$(id).disabled=locked||busy;
 $('apply').disabled=locked||busy||!validated||!$('confirm').checked||(validated.summary.has_alarms&&!$('confirm-alarm').checked)||(validated.summary.empty&&!$('confirm-empty').checked);
}
function invalidate(preserveUpload=false){generation++;reading=false;if(!preserveUpload)uploadBytes=null;validated=null;$('review').hidden=true;$('summary').replaceChildren();for(const id of ['confirm','confirm-alarm','confirm-empty'])$(id).checked=false;status('changed');controls();}
async function request(path,body){
 const response=await fetch('api/recovery'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Dovit-Token':snapshot.token},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)}:{cache:'no-store',signal:AbortSignal.timeout(5000)});
 const result=await response.json();if(!response.ok)throw Error(result.error||'recovery_error');return result;
}
function restored(){locked=true;$('restart').hidden=false;$('review').hidden=true;status('restart');controls();}
async function load(){try{const result=await request('');if(result.recovery!==true)throw Error('recovery_disabled');snapshot=result;currentState();if(result.restored){restored();return;}
 if(result.current.revision===null&&['unreadable','oversized'].includes(result.current.state)){locked=true;status(result.current.state==='unreadable'?'recovery_unreadable':'recovery_size');controls();return;}
 if(result.pending){locked=true;status('recovery_pending');controls();return;}
 for(const backup of result.backups||[]){const option=document.createElement('option');option.value=backup.id;option.disabled=!!backup.contains_cleanup||backup.state!=='valid';option.dataset.backupName=backup.name;option.dataset.stateKey=backup.contains_cleanup?'recovery_cleanup':backup.state==='valid'?'backup_valid':'backup_unavailable';option.textContent=backup.name+' · '+t(option.dataset.stateKey);$('backup').append(option);}status('ready');
 }catch(error){status(error.message);}controls();}
function renderSummary(summary){
 const root=$('summary');root.replaceChildren();const counts=document.createElement('p');counts.textContent=t('counts')+': '+Object.entries(summary.counts||{}).map(([key,value])=>categoryName(key)+': '+value).join(', ');root.append(counts);
 const title=document.createElement('p');title.textContent=t('names');root.append(title);const list=document.createElement('ul');for(const item of summary.names||[]){const li=document.createElement('li');li.textContent=categoryName(item.category)+': '+item.name;list.append(li);}root.append(list);
 if(summary.names_truncated){const note=document.createElement('p');note.textContent=t('names_truncated');root.append(note);}
}
$('language').onchange=()=>{language=$('language').value;translate();};
$('new-install').onclick=()=>{
 if(locked||busy||!snapshot||snapshot.current.state!=='missing')return;
 $('backup').value='';$('file').value='';invalidate();
 $('document').value=JSON.stringify({lights:{},shutters:{},thermostats:{},motions:{},contacts:{},alarms:{}},null,2);
 $('document').focus();
};
$('backup').onchange=()=>{if(locked)return;invalidate();};
$('document').oninput=()=>{if(locked)return;$('file').value='';invalidate();};
$('file').onchange=async()=>{
 if(locked)return;invalidate();const current=generation,file=$('file').files[0];if(!file)return;$('document').value='';
 if(!/\.json$/i.test(file.name)||file.size>256*1024){status('recovery_file_invalid');return;}
 reading=true;status('reading');controls();
 try{
  const buffer=await file.arrayBuffer();if(current!==generation||locked)return;
  const bytes=new Uint8Array(buffer);if(bytes.length>256*1024){status('recovery_file_invalid');return;}
  const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
  uploadBytes=Array.from(bytes);$('document').value=text;status('changed');
 }
 catch{if(current===generation)status('recovery_read_error');}
 finally{if(current===generation){reading=false;controls();}}
};
$('validate').onclick=async()=>{
 if(busy||locked||reading||!snapshot)return;
 const wasFocused=document.activeElement===$('validate');let focusTarget=null;
 invalidate(true);const current=generation;
 const payload={revision:snapshot.current.revision};if($('backup').value){if(!(snapshot.backups||[]).some(b=>b.id===$('backup').value&&b.state==='valid'&&!b.contains_cleanup)){status('recovery_backup');return;}payload.backup=$('backup').value;}else if(uploadBytes!==null)payload.file_bytes=uploadBytes;else payload.document=$('document').value;
 busy=true;status('checking');controls();
 try{const result=await request('/validate',payload);if(current!==generation||locked)return;validated=result;renderSummary(result.summary);$('alarm-row').hidden=!result.summary.has_alarms;$('empty-row').hidden=!result.summary.empty;$('review').hidden=false;status('checked');focusTarget=$('review-title');}
 catch(error){if(current===generation){status(error.message);focusTarget=$('status');}}
 finally{busy=false;controls();if(focusTarget)recoveryFocus($('validate'),focusTarget,wasFocused);}
};
for(const id of ['confirm','confirm-alarm','confirm-empty'])$(id).onchange=controls;
$('apply').onclick=async()=>{
 controls();if($('apply').disabled)return;
 const wasFocused=document.activeElement===$('apply');
 const payload={revision:validated.revision,validation_id:validated.validation_id,confirm:true};if(validated.summary.has_alarms)payload.confirm_alarm=true;if(validated.summary.empty)payload.confirm_empty=true;
 locked=true;busy=true;generation++;status('applying');controls();
 try{const result=await request('/apply',payload);if(result.restored!==true||result.restart_required!==true)throw Error('recovery_error');restored();}
 catch{status('uncertain');try{const result=await request('');if(result.recovery===true&&result.restored===true)restored();}catch{status('uncertain');}}
 finally{busy=false;controls();recoveryFocus($('apply'),$($('restart').hidden?'status':'restart-title'),wasFocused);}
};
translate();controls();load();
