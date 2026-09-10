import {createElement, Search, X, Check, ExternalLink} from 'lucide';

type Upstream = {url:string;revision?:string};
type Result = {record_id:string;package_id:string;version:string;name:string;summary:string;source:string;source_id:string;metadata_only:boolean;match_strength:string;ranking_score:number|null;snippets:{path:string;text:string}[];upstream?:Upstream|null};
type Package = {record_id:string;package_id:string;version:string;name:string;summary:string;source_kind:string;source_id:string;license:string|null;digest:string;details:Record<string,unknown>;evidence:unknown[];provenance:unknown;documents:{fields:{path:string;text:string}[]}[];upstream?:Upstream|null};
const $ = <T extends HTMLElement = HTMLElement>(id:string) => document.getElementById(id) as T;
const input = (id:string) => $<HTMLInputElement>(id).value;
const el = (tag:string, text?:string, className?:string) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
let snapshot='', results:Result[]=[], selected='', searchToken=0, detailToken=0;
const compared = new Map<string,{package?:Package}>();
const params = new URLSearchParams(location.search);
$<HTMLInputElement>('query').value=params.get('q')||'';
if(['registry','candidates','all'].includes(params.get('source')||''))$<HTMLSelectElement>('source').value=params.get('source')!;
$('search').append(createElement(Search));$('close-comparison').append(createElement(X));

async function api(path:string, body?:unknown){
 const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:`HTTP ${response.status}`);return value;
}
function logo(pid:string){
 const key=pid.startsWith('rtk')?'rtk':pid.startsWith('openai')?'codex':pid.startsWith('axios')?'axios':pid.startsWith('bitcoin')?'bitcoin':pid.startsWith('n8n')?'n8n':null;
 if(!key)return el('span','S','brandmark');const img=document.createElement('img');img.src=`/logos/${key}.png`;img.alt='';img.className='avatar';return img;
}
function badge(text:string, candidate=false){return el('span',text,'badge'+(candidate?' candidate':''));}
function upstreamView(value:Upstream|null|undefined, compact=false):HTMLElement{
 const node=el('div','', 'upstream');
 let url:URL;
 try{
  if(!value||typeof value.url!=='string'||value.url.length>2048||/[\s\p{Cc}\p{Cf}\p{Cs}\\]/u.test(value.url)||!/^https?:\/\//i.test(value.url))throw new Error();
  if(value.revision!==undefined&&(typeof value.revision!=='string'||!value.revision||value.revision.length>256||/[\s\p{Cc}\p{Cf}\p{Cs}]/u.test(value.revision)))throw new Error();
  url=new URL(value.url);
  if(!url.hostname||url.username||url.password||url.search||url.hash)throw new Error();
 }catch{if(!compact)node.append(el('span','Upstream unavailable','muted'));return node;}
 const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label','Upstream project');link.title=value!.url;link.append(createElement(ExternalLink),document.createTextNode(compact?`${url.host}${url.pathname}`:value!.url));node.append(link);
 if(!compact&&value!.revision)node.append(el('span','Declared revision','muted'),el('code',value!.revision));
 return node;
}
function renderValue(value:unknown):HTMLElement{
 const node=el('div','', 'field-value');
 if(value===null||value===undefined){node.append(el('span','Not declared','muted'));return node;}
 if(Array.isArray(value)){if(!value.length){node.textContent='No entries declared';return node;}const list=el('ul','', 'field-list');for(const item of value){const li=el('li');li.append(renderValue(item));list.append(li);}node.append(list);return node;}
 if(typeof value==='object'){const list=el('dl','', 'field-map');for(const [key,item]of Object.entries(value)){const row=el('div','', 'field-row');row.append(el('dt',key.replace(/([a-z])([A-Z])/g,'$1 $2').replaceAll('_',' '),'field-name'));const content=el('dd');content.append(renderValue(item));row.append(content);list.append(row);}node.append(list);return node;}
 node.textContent=String(value);return node;
}
function section(title:string,value:unknown){const node=el('section','', 'section');if(value&&typeof value==='object'&&!Array.isArray(value)){const entries=Object.entries(value);if(entries.length===1&&entries[0][0].toLowerCase()===title.toLowerCase())value=entries[0][1];}node.append(el('h3',title),renderValue(value));return node;}
function disclosure(title:string,value:unknown){const node=el('details');node.append(el('summary',title),el('pre',JSON.stringify(value,null,2)));return node;}
function showField(p:Package,path:string){
 const dialog=document.createElement('dialog');dialog.setAttribute('aria-label','Source field');
 const heading=el('div','', 'dialog-heading');const close=el('button') as HTMLButtonElement;close.setAttribute('aria-label','Close source field');close.append(createElement(X));close.onclick=()=>dialog.close();heading.append(el('h2','Source field'),close);
 const field=p.documents.flatMap(d=>d.fields).find(f=>f.path===path);
 const link=document.createElement('a');link.href=`/v1/packages/${encodeURIComponent(p.record_id)}?snapshot=${snapshot}`;link.target='_blank';link.rel='noopener';link.textContent='Source record';link.prepend(createElement(ExternalLink));
 dialog.append(heading,el('code',path),section('Value',field?.text),el('div',p.digest,'identity'),link,disclosure('Declared evidence references',p.evidence));
 dialog.onclose=()=>dialog.remove();document.body.append(dialog);dialog.showModal();
}
function updateCompare(){const button=$<HTMLButtonElement>('compare');button.textContent=`Compare (${compared.size})`;button.disabled=compared.size<2||[...compared.values()].some(slot=>!slot.package);}
async function loadPackage(id:string){return await api(`/v1/packages/${encodeURIComponent(id)}?snapshot=${snapshot}`) as Package;}
function renderResults(){
 $('results').replaceChildren();$('count').textContent=String(results.length);
 if(!results.length){$('results').append(el('div','No matches','empty'));return;}
 for(const result of results){
  const row=el('div','',`result${selected===result.record_id?' active':''}`);row.dataset.id=result.record_id;
  const open=el('button',undefined,'result-open') as HTMLButtonElement;open.type='button';open.setAttribute('aria-pressed',String(selected===result.record_id));
  const heading=el('div','', 'result-heading');heading.append(logo(result.package_id),el('h3',result.name));open.append(heading,el('div',`${result.package_id}@${result.version}`,'identity'),el('p',result.summary));
  open.onclick=()=>showDetail(result.record_id);row.append(open);
  const badges=el('div','', 'badges');badges.append(badge(result.source,result.source==='candidates'),badge(result.match_strength));if(result.metadata_only)badges.append(badge('Metadata only'));row.append(badges);
  if(result.upstream)row.append(upstreamView(result.upstream,true));
  const bottom=el('div','', 'result-bottom');const label=el('label');const check=document.createElement('input');check.type='checkbox';check.checked=compared.has(result.record_id);check.setAttribute('aria-label',`Compare ${result.package_id}`);
  check.onchange=async()=>{
   const id=result.record_id;
   if(!check.checked){compared.delete(id);updateCompare();return;}
   if(compared.size>=3){check.checked=false;$('notice').textContent='Comparison limit: 3 packages';return;}
   // Reserve a slot before fetching; its identity invalidates cancelled or replaced requests.
   const slot:{package?:Package}={};compared.set(id,slot);updateCompare();
   try{const p=await loadPackage(id);if(compared.get(id)!==slot)return;slot.package=p;}
   catch(e){if(compared.get(id)!==slot)return;compared.delete(id);renderResults();$('notice').textContent=String(e);}
   updateCompare();
  };
  label.append(check,document.createTextNode('Compare'));bottom.append(label,el('span',result.ranking_score===null?'Exact ID':`RRF ${result.ranking_score.toFixed(4)}`));row.append(bottom);$('results').append(row);
 }
}
async function showDetail(id:string){
 const token=++detailToken;selected=id;renderResults();$('detail').replaceChildren(el('div','Loading package','empty'));
 try{const p=await loadPackage(id);if(token!==detailToken)return;const detail=$('detail');detail.replaceChildren();
  const heading=el('div','', 'detail-heading');heading.append(logo(p.package_id),el('h2',p.name));detail.append(heading,el('div',`${p.package_id}@${p.version}`,'identity'),el('p',p.summary,'detail-summary'));
  const badges=el('div','', 'badges');badges.append(badge(p.source_kind,p.source_kind==='candidates'),badge(p.license||'License not declared'));detail.append(badges);
  detail.append(upstreamView(p.upstream));
  const actions=el('div','', 'detail-actions');const verify=el('button','Verify metadata') as HTMLButtonElement;verify.prepend(createElement(Check));const outcome=el('span','','verification');verify.onclick=async()=>{verify.disabled=true;outcome.textContent='Checking';try{const r=await api('/v1/verify',{record_id:id,snapshot});outcome.textContent=r.status;}catch(e){outcome.textContent=String(e);}finally{verify.disabled=false;}};actions.append(verify,outcome);detail.append(actions);
  const result=results.find(r=>r.record_id===id);if(result){const matches=el('section','', 'section');matches.append(el('h3','Matched source fields'));for(const s of result.snippets){const block=el('div','', 'snippet');const link=document.createElement('a');link.href='#source-field';link.textContent=s.path;link.onclick=e=>{e.preventDefault();showField(p,s.path);};block.append(el('p',s.text),link);matches.append(block);}detail.append(matches);}
  const specs=p.details.specs as Record<string,unknown>[]|undefined;
  if(specs){for(const spec of specs){detail.append(section('Purpose',spec.intent),section('Capabilities',spec.provides),section('Interfaces',spec.interfaces),section('Requirements',spec.requires),section('Constraints',spec.constraints),section('Side effects',spec.effects),section('Scope',spec.scope));}}
  else detail.append(section('Registry metadata',p.details.metadata));
  detail.append(disclosure('Evidence references',p.evidence),disclosure('Provenance',p.provenance),disclosure('Identity and digest',{package:p.package_id,version:p.version,source:p.source_id,digest:p.digest}));
  if(window.innerWidth<761)detail.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){if(token===detailToken)$('detail').replaceChildren(el('div',String(e),'empty'));}
}
async function search(){
 const query=input('query').trim();if(!query)return;const token=++searchToken;++detailToken;compared.clear();updateCompare();selected='';results=[];renderResults();
 $('notice').textContent='Searching';$<HTMLButtonElement>('search').disabled=true;
 const filters:Record<string,unknown>={source:input('source'),include_inactive:$<HTMLInputElement>('inactive').checked};
 for(const key of ['package','version','license','capability','intent'])if(input(`${key}-filter`).trim())filters[key]=input(`${key}-filter`).trim();
 try{const response=await api('/v1/search',{query,mode:input('mode'),filters});if(token!==searchToken)return;snapshot=response.snapshot;results=response.results;
  const url=new URL(location.href);url.searchParams.set('q',query);url.searchParams.set('source',input('source'));history.replaceState(null,'',url);
  $('notice').textContent=response.degraded?`BM25 fallback · ${response.diagnostic}`:`${response.results.length} results · ${response.mode} · ${Math.round(response.latency_ms)} ms`;
  renderResults();$('detail').replaceChildren(el('div','No package selected','empty'));if(results[0])await showDetail(results[0].record_id);
 }catch(e){if(token===searchToken){results=[];renderResults();$('notice').textContent=String(e);}}
 finally{if(token===searchToken)$<HTMLButtonElement>('search').disabled=false;}
}
$('search-form').onsubmit=e=>{e.preventDefault();void search();};
function comparisonValue(p:Package,key:string):unknown{
 if(key in p)return (p as unknown as Record<string,unknown>)[key];
 const specs=p.details.specs as Record<string,unknown>[]|undefined;
 if(specs)return specs.map(s=>s[key]);
 const metadata=p.details.metadata as Record<string,unknown>|undefined;
 const fields:Record<string,string>={intent:'provided_intents',provides:'provided_capabilities',requires:'required_capabilities'};
 return metadata?.[fields[key]||key];
}
$('compare').onclick=()=>{const packages=[...compared.values()].flatMap(slot=>slot.package?[slot.package]:[]);const table=document.createElement('table');const head=el('tr');head.append(el('th',''));for(const p of packages)head.append(el('th',p.name));table.append(head);
 for(const key of ['package_id','version','source_kind','upstream','license','intent','provides','interfaces','requires','constraints']){const row=el('tr');row.append(el('th',key));for(const p of packages){const cell=el('td');cell.append(key==='upstream'?upstreamView(p.upstream):renderValue(comparisonValue(p,key)));row.append(cell);}table.append(row);}
 $('comparison-content').replaceChildren(table);$<HTMLDialogElement>('comparison').showModal();};
$('close-comparison').onclick=()=>$<HTMLDialogElement>('comparison').close();
void api('/v1/status').then(s=>{$('status').textContent=`${s.packages} packages · ${s.provider?.model||'BM25'} · Local`;}).catch(e=>{$('status').textContent=String(e);});
if(input('query'))void search();
