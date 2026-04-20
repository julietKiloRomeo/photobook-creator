import { api, configureProject } from './api.js';

const THEME_COLORS=['#7F77DD','#1D9E75','#D85A30','#378ADD','#BA7517','#D4537E'];

let PHOTOS=[
  {id:'p1',label:'360 attempt #1',color:'#C4D4E8',date:'2026-01-14'},
  {id:'p2',label:'360 attempt #2',color:'#A8BFD8',date:'2026-01-14'},
  {id:'p3',label:'360 attempt #3',color:'#8CAABF',date:'2026-01-14'},
  {id:'p4',label:'Everest sunset wide',color:'#E8C8A0',date:'2026-01-12'},
  {id:'p5',label:'Everest sunset close',color:'#D4B48C',date:'2026-01-12'},
  {id:'p6',label:'Everest clouds',color:'#BFA078',date:'2026-01-12'},
  {id:'p7',label:'Black line',color:'#B0B0B0',date:'2026-01-15'},
  {id:'p8',label:'Jack faceplant',color:'#E8D4C0',date:'2026-01-15'},
  {id:'p9',label:'Snowy face closeup',color:'#F0E0D0',date:'2026-01-15'},
  {id:'p10',label:'Park morning',color:'#C8E0C0',date:'2026-01-15'},
  {id:'p11',label:'Snow drift',color:'#D8EEF8',date:'2026-01-15'},
  {id:'p12',label:'Hot choc hands',color:'#D4B890',date:'2026-01-15'},
  {id:'p13',label:'Train arrivals',color:'#C8C0D8',date:'2026-01-11'},
  {id:'p14',label:'Station platform',color:'#B8B0C8',date:'2026-01-11'},
  {id:'p15',label:'Taxi queue',color:'#A8A0B8',date:'2026-01-11'},
  {id:'p16',label:'Hotel lobby',color:'#E0D4C8',date:'2026-01-11'},
  {id:'p17',label:'Hotel view',color:'#D0C4B8',date:'2026-01-11'},
  {id:'p18',label:'Breakfast spread',color:'#E8D4A0',date:'2026-01-16'},
];

let STACKS=[
  {id:'s1',label:"Jack's 360 attempts",photos:['p1','p2','p3'],pick:null,date:'2026-01-14'},
  {id:'s2',label:'Everest at sunset',photos:['p4','p5','p6'],pick:null,date:'2026-01-12'},
  {id:'s3',label:'Black line in park',photos:['p7'],pick:'p7',date:'2026-01-15'},
  {id:'s4',label:'Jack in snow',photos:['p8','p9'],pick:null,date:'2026-01-15'},
  {id:'s5',label:'Park morning',photos:['p10','p11','p12'],pick:null,date:'2026-01-15'},
  {id:'s6',label:'Arrival day',photos:['p13','p14','p15','p16','p17','p18'],pick:null,date:'2026-01-11'},
];

let themes=[
  {id:'t1',title:'First day in the park',stacks:['s1','s3','s4','s5'],color:THEME_COLORS[0]},
  {id:'t2',title:'Mountain expedition',stacks:['s2'],color:THEME_COLORS[1]},
];
let unassigned=['s6'];
let tidCtr=3;
let activeLens='stacks';
let openStackId=null;
let tempPick=null;
let splitMode=false;
let splitSelection=new Set();
let duelIdx=0;
let duelStacks=[];
let duelState={};
let activeThemeId=null;
let activePage=null;
let pages={};
let slots={};
let pgCtr=0;
let curLayout='2x2';
let dragSid=null,dragFrom=null;
let clusterState={state:'final',operation_id:null};
const chapterByTheme={};
const chapterEnsurePromises={};
const UPLOAD_BATCH_SIZE = 100;
const STACKS_WINDOW_DEFAULT = 40;
const STACKS_WINDOW_STEP = 30;
const TIMELINE_WINDOW_DEFAULT = 80;
const TIMELINE_WINDOW_STEP = 60;
const THEME_WINDOW_DEFAULT = 6;
const THEME_WINDOW_STEP = 6;
const POOL_WINDOW_DEFAULT = 20;
const POOL_WINDOW_STEP = 20;
const BOOK_PAGES_WINDOW_DEFAULT = 40;
const BOOK_PAGES_WINDOW_STEP = 30;
const BOOK_PHOTOS_WINDOW_DEFAULT = 40;
const BOOK_PHOTOS_WINDOW_STEP = 30;
const UPLOAD_IDLE_TIP_DELAY_MS = 2000;
const UPLOAD_IDLE_TIP_ROTATE_MS = 2000;
const UPLOAD_IDLE_TIPS = {
  uploading: [
    'Packing negatives into the darkroom satchel.',
    'Checking every frame for proper exposure tags.',
    'Dusting film canisters before they hit the light table.',
    'Courier is jogging these shots into the lab.',
  ],
  indexing: [
    'Pinning each photo to the contact sheet ledger.',
    'Counting frames so no memory gets left behind.',
    'Labeling sleeves: day, location, and best guesses.',
    'Sorting boots, sunsets, and blurry victory laps.',
  ],
  provisional_clustering: [
    'Hanging quick proofs to spot obvious twins.',
    'Bundling near-matches into first-pass piles.',
    'Marking suspicious duplicates with pencil circles.',
    'Drafting rough stack borders before the fine cut.',
  ],
  refining: [
    'Arguing politely with the stack goblins.',
    'Tightening clusters until the stories line up.',
    'Running final checks on duplicate traps.',
    'Threading stacks into themes the book can carry.',
  ],
  generic: [
    'The safelight is on; patience improves the print.',
    'Nothing is frozen, the darkroom is just thinking.',
    'Good albums simmer before they click.',
    'Still developing. Great picks are worth the wait.',
  ],
};
let uploadLastRealUpdateAt = 0;
let uploadIdleCountdownTimer = null;
let uploadTipRotateTimer = null;
let uploadIdleActive = false;
let uploadTipPhase = 'uploading';
let uploadTipIndexByPhase = Object.create(null);
let uploadLastTipText = '';
let inspectSequenceIds = [];
let inspectSequenceIndex = 0;
let inspectMode = 'generic';
let showIgnoredStacks = false;
let stacksWindow = STACKS_WINDOW_DEFAULT;
let timelineWindow = TIMELINE_WINDOW_DEFAULT;
let poolWindow = POOL_WINDOW_DEFAULT;
const themeWindowById = {};
const bookPagesWindowByTheme = {};
const bookPhotosWindowByTheme = {};
const PROJECT_ID = (() => {
  const match = window.location.pathname.match(/^\/darkroom\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
})();
if(!PROJECT_ID){
  window.location.assign('/');
}
configureProject(PROJECT_ID);

function getP(pid){return PHOTOS.find(x=>x.id===pid)}
function getS(sid){return STACKS.find(x=>x.id===sid)}
function getPick(sid){
  const s=getS(sid);if(!s)return null;
  const pid=s.pick||s.previousPick||s.photos[0];
  return getP(pid);
}
function resolved(s){return s.pick!==null && !s.needsReview}
function isStackVisible(stack){
  if(!stack)return false;
  return showIgnoredStacks || !stack.ignored;
}
function visibleStacks(){
  return STACKS.filter((stack)=>isStackVisible(stack));
}
function parseStackDate(stack){
  const raw = stack?.date || '';
  const ts = new Date(raw).getTime();
  return Number.isFinite(ts) ? ts : 0;
}
function compareStackPriority(a,b){
  const aNeeds = Number(Boolean(a?.needsReview));
  const bNeeds = Number(Boolean(b?.needsReview));
  if(aNeeds!==bNeeds)return bNeeds-aNeeds;
  const aResolved = Number(Boolean(resolved(a)));
  const bResolved = Number(Boolean(resolved(b)));
  if(aResolved!==bResolved)return aResolved-bResolved;
  return parseStackDate(b)-parseStackDate(a);
}
function prioritizedVisibleStacks(){
  return [...visibleStacks()].sort(compareStackPriority);
}
function resolvedCount(){return visibleStacks().filter(resolved).length}
function themeOf(sid){return themes.find(t=>t.stacks.includes(sid))}
function visibleStackIds(){
  return new Set(visibleStacks().map((stack)=>String(stack.id)));
}
function getThemeWindow(tid){
  if(themeWindowById[tid]==null)themeWindowById[tid]=THEME_WINDOW_DEFAULT;
  return themeWindowById[tid];
}
function getBookPagesWindow(tid){
  if(bookPagesWindowByTheme[tid]==null)bookPagesWindowByTheme[tid]=BOOK_PAGES_WINDOW_DEFAULT;
  return bookPagesWindowByTheme[tid];
}
function getBookPhotosWindow(tid){
  if(bookPhotosWindowByTheme[tid]==null)bookPhotosWindowByTheme[tid]=BOOK_PHOTOS_WINDOW_DEFAULT;
  return bookPhotosWindowByTheme[tid];
}
function renderLimitRow({shown,total,onMore,onAll,label='items'}){
  if(total<=shown)return '';
  return `<div class="lens-limit-row"><span>Showing ${shown} of ${total} ${label}</span><div class="lens-limit-actions"><button class="mini-btn" type="button" onclick="${onMore}">Load more</button><button class="mini-btn" type="button" onclick="${onAll}">Show all</button></div></div>`;
}

function escAttr(value){
  return String(value??'')
    .replaceAll('&','&amp;')
    .replaceAll('"','&quot;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;');
}

function photoStyle(photo,fallback='var(--color-background-secondary)',fit='cover'){
  const base=`background:${photo?.color||fallback};`;
  if(!photo?.url)return base;
  const safeUrl=encodeURI(String(photo.url));
  return `${base}background-image:url(${safeUrl});background-size:${fit};background-position:center;background-repeat:no-repeat;`;
}

function ensureInspectPreview(){
  let overlay=document.getElementById('inspect-preview');
  if(overlay)return overlay;
  overlay=document.createElement('div');
  overlay.id='inspect-preview';
  overlay.className='inspect-preview';
  overlay.innerHTML='<div class="inspect-preview-frame"><img id="inspect-preview-img" alt="Large photo preview"/><div class="inspect-preview-caption" id="inspect-preview-caption"></div></div>';
  document.getElementById('app')?.appendChild(overlay);
  return overlay;
}

function setInspectSequence(ids,mode='generic'){
  inspectSequenceIds=(ids||[]).map((id)=>String(id)).filter((id)=>Boolean(getP(id)));
  inspectMode=mode;
  if(inspectSequenceIndex>=inspectSequenceIds.length){
    inspectSequenceIndex=0;
  }
}

function showInspectPreview(photo){
  if(!photo?.url)return;
  const overlay=ensureInspectPreview();
  const img=document.getElementById('inspect-preview-img');
  const cap=document.getElementById('inspect-preview-caption');
  if(img)img.src=String(photo.url);
  if(cap)cap.textContent=photo.label||'';
  const idx=inspectSequenceIds.indexOf(String(photo.id));
  if(idx>=0){
    inspectSequenceIndex=idx;
  }
  overlay.classList.add('show');
}

function hideInspectPreview(){
  const overlay=document.getElementById('inspect-preview');
  if(!overlay)return;
  overlay.classList.remove('show');
}

function bindInspectHover(element,photo){
  if(!element || !photo?.url)return;
  element.addEventListener('mouseenter',()=>showInspectPreview(photo));
  element.addEventListener('mouseleave',hideInspectPreview);
}

function bindDuelInspect(element,pid){
  if(!element)return;
  element.addEventListener('mouseenter',()=>{
    const photo=getP(pid);
    if(photo)showInspectPreview(photo);
  });
  element.addEventListener('contextmenu',(event)=>{
    event.preventDefault();
    cycleInspectDuel(1);
  });
}

function cycleInspectDuel(step=1,event){
  event?.preventDefault();
  if(inspectMode!=='duel' || inspectSequenceIds.length<2)return;
  inspectSequenceIndex=(inspectSequenceIndex+step+inspectSequenceIds.length)%inspectSequenceIds.length;
  const pid=inspectSequenceIds[inspectSequenceIndex];
  const photo=pid?getP(pid):null;
  if(photo){
    showInspectPreview(photo);
  }
}

function handleInspectKeys(event){
  const overlay=document.getElementById('inspect-preview');
  if(!overlay || !overlay.classList.contains('show'))return;
  if(event.key==='Escape'){
    event.preventDefault();
    hideInspectPreview();
    return;
  }
  if(inspectMode!=='duel')return;
  if(event.key==='ArrowRight' || event.key==='Tab'){
    cycleInspectDuel(1,event);
    return;
  }
  if(event.key==='ArrowLeft'){
    cycleInspectDuel(-1,event);
  }
}

function normalizePhoto(photo){
  const pid = String(photo.id);
  return {
    id:pid,
    label:photo.label||`Photo ${pid}`,
    color:photo.color||THEME_COLORS[Number(pid)%THEME_COLORS.length],
    date:photo.date||new Date().toISOString().slice(0,10),
    url:photo.image_url||api.referenceImageUrl(pid),
  };
}

function applyStacksFromApi(items){
  const nextPhotos=[];
  const seen=new Set();
  const nextStacks=(items||[]).map((item)=>{
    const photos=(item.photos||[]).map((photo)=>{
      const normalized=normalizePhoto(photo);
      if(!seen.has(normalized.id)){
        seen.add(normalized.id);
        nextPhotos.push(normalized);
      }
      return normalized.id;
    });
    return {
      id:String(item.id),
      label:item.label||`Stack ${item.id}`,
      photos,
      pick:item.pick_reference_id != null ? String(item.pick_reference_id) : null,
      previousPick:item.previous_pick_reference_id != null ? String(item.previous_pick_reference_id) : null,
      needsReview:Boolean(item.needs_review),
      ignored:Boolean(item.ignored),
      newIds:(item.new_reference_ids||[]).map((rid)=>String(rid)),
      date:item.date||new Date().toISOString().slice(0,10),
    };
  });
  PHOTOS=nextPhotos;
  STACKS=nextStacks;
}

function applyThemesFromApi(items){
  themes=(items||[]).map((theme)=>({
    id:String(theme.id),
    title:theme.title||'Theme',
    description:theme.description||'',
    color:theme.color||THEME_COLORS[0],
    stacks:(theme.stack_ids||[]).map((sid)=>String(sid)),
  }));
  const assigned = new Set(themes.flatMap((theme)=>theme.stacks));
  unassigned=STACKS.map((stack)=>String(stack.id)).filter((sid)=>!assigned.has(sid));
  if(!themes.length){
    themes=[{id:'local-default',title:'Highlights',description:'',stacks:[],color:THEME_COLORS[0]}];
    unassigned=STACKS.map((stack)=>String(stack.id));
  }
}

async function syncModelFromApi(){
  const [stackRes,themeRes]=await Promise.all([api.getStacks(),api.getThemes()]);
  if(stackRes.ok && Array.isArray(stackRes.data?.items)){
    applyStacksFromApi(stackRes.data.items);
    clusterState=stackRes.data?.cluster_state||{state:'final',operation_id:null};
  }else{
    PHOTOS=[];
    STACKS=[];
    clusterState={state:'final',operation_id:null};
  }

  if(themeRes.ok && Array.isArray(themeRes.data?.items)){
    applyThemesFromApi(themeRes.data.items);
  }else{
    themes=[{id:'local-default',title:'Highlights',description:'',stacks:[],color:THEME_COLORS[0]}];
    unassigned=STACKS.map((stack)=>String(stack.id));
  }
  updateLensLocks();
  if(!isClusterFinal() && (activeLens==='themes' || activeLens==='book')){
    activeLens='stacks';
    document.querySelectorAll('.lens').forEach(b=>b.classList.toggle('active',b.dataset.lens===activeLens));
    document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
    document.getElementById('panel-stacks').classList.add('active');
  }
}

function isClusterFinal(){
  return (clusterState?.state||'final')==='final';
}

function updateLensLocks(){
  const blocked=!isClusterFinal();
  const msg='Refining stacks... Themes and Book unlock when finished';
  document.querySelectorAll('.lens').forEach((btn)=>{
    const lens=btn.dataset.lens;
    if(lens==='themes' || lens==='book'){
      btn.classList.toggle('locked',blocked);
      btn.title=blocked?msg:'';
    }
  });
}

function applyBackendPages(tid,pageItems){
  const existingById=new Map((pages[tid]||[]).map(pg=>[Number(pg.id),pg]));
  pages[tid]=(pageItems||[]).map(item=>{
    const prev=existingById.get(Number(item.id));
    return {
      id:Number(item.id),
      num:Number(item.page_index),
      layout:prev?.layout||'2x2',
    };
  });
}

async function ensureThemeChapter(tid){
  if(!tid)return null;
  if(chapterEnsurePromises[tid])return chapterEnsurePromises[tid];

  const run=async()=>{
    let chapterId=chapterByTheme[tid]||null;
    const theme=themes.find(t=>t.id===tid);
    if(!chapterId){
      const createRes=await api.createChapter({
        name:theme?.title||'Theme chapter',
        page_count:Math.max((pages[tid]||[]).length,1),
      });
      if(createRes.ok && createRes.data && typeof createRes.data.id==='number'){
        chapterId=createRes.data.id;
      }
    }
    if(!chapterId)return null;
    chapterByTheme[tid]=chapterId;

    const pageRes=await api.getChapterPages(chapterId);
    if(pageRes.ok && Array.isArray(pageRes.data?.items)){
      applyBackendPages(tid,pageRes.data.items);
    }

    return chapterId;
  };

  chapterEnsurePromises[tid]=run()
    .finally(()=>{delete chapterEnsurePromises[tid];});

  return chapterEnsurePromises[tid];
}

function updateBadges(){
  const visible = visibleStacks();
  const rc=resolvedCount(),tot=visible.length;
  document.getElementById('lb-stacks').textContent=`${rc}/${tot}`;
  const left=visible.filter(s=>!resolved(s)&&s.photos.length>1).length;
  document.getElementById('lb-duel').textContent=left>0?`${left} left`:'done';
  document.getElementById('lb-themes').textContent=themes.length;
  let pgTotal=0;Object.values(pages).forEach(a=>pgTotal+=a.length);
  document.getElementById('lb-book').textContent=pgTotal+(pgTotal===1?' page':' pages');
  const pct=tot>0?Math.round(rc/tot*100):0;
  document.getElementById('stacks-fill').style.width=pct+'%';
  document.getElementById('stacks-label').textContent=`${rc} of ${tot} resolved`;
  const ignoredBtn=document.getElementById('ignored-toggle-btn');
  if(ignoredBtn){
    ignoredBtn.textContent=showIgnoredStacks?'Ignored: showing':'Ignored: hidden';
  }
}

function goLens(l){
  hideInspectPreview();
  setInspectSequence([], 'generic');
  if((l==='themes' || l==='book') && !isClusterFinal()){
    showToast('Refining stacks... Themes and Book are temporarily locked');
    return;
  }
  activeLens=l;
  document.querySelectorAll('.lens').forEach(b=>b.classList.toggle('active',b.dataset.lens===l));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('panel-'+l).classList.add('active');
  if(l==='stacks')renderStacks();
  if(l==='duel')renderDuel();
  if(l==='themes')renderThemes();
  if(l==='timeline')renderTimeline();
  if(l==='book')renderBook();
  updateBadges();
}

function rerenderActiveLens(){
  if(activeLens==='stacks')renderStacks();
  else if(activeLens==='duel')renderDuel();
  else if(activeLens==='themes')renderThemes();
  else if(activeLens==='timeline')renderTimeline();
  else if(activeLens==='book')renderBook();
  updateBadges();
}

function toggleShowIgnored(){
  showIgnoredStacks=!showIgnoredStacks;
  if(activeLens==='stacks')renderStacks();
  if(activeLens==='duel')renderDuel();
  if(activeLens==='themes')renderThemes();
  if(activeLens==='timeline')renderTimeline();
  if(activeLens==='book')renderBook();
  updateBadges();
}

function showMoreStacks(){stacksWindow+=STACKS_WINDOW_STEP;renderStacks();}
function showAllStacks(){stacksWindow=Number.MAX_SAFE_INTEGER;renderStacks();}
function showMoreTimeline(){timelineWindow+=TIMELINE_WINDOW_STEP;renderTimeline();}
function showAllTimeline(){timelineWindow=Number.MAX_SAFE_INTEGER;renderTimeline();}
function showMoreThemeStacks(tid){themeWindowById[tid]=getThemeWindow(tid)+THEME_WINDOW_STEP;renderThemes();}
function showAllThemeStacks(tid){themeWindowById[tid]=Number.MAX_SAFE_INTEGER;renderThemes();}
function showMorePool(){poolWindow+=POOL_WINDOW_STEP;renderThemes();}
function showAllPool(){poolWindow=Number.MAX_SAFE_INTEGER;renderThemes();}
function showMoreBookPages(tid){bookPagesWindowByTheme[tid]=getBookPagesWindow(tid)+BOOK_PAGES_WINDOW_STEP;renderPagesRow(tid);}
function showAllBookPages(tid){bookPagesWindowByTheme[tid]=Number.MAX_SAFE_INTEGER;renderPagesRow(tid);}
function showMoreBookPhotos(tid){bookPhotosWindowByTheme[tid]=getBookPhotosWindow(tid)+BOOK_PHOTOS_WINDOW_STEP;renderPPList(tid);}
function showAllBookPhotos(tid){bookPhotosWindowByTheme[tid]=Number.MAX_SAFE_INTEGER;renderPPList(tid);}

function renderStacks(){
  const g=document.getElementById('stacks-grid');g.innerHTML='';
  const ordered = prioritizedVisibleStacks();
  if(!ordered.length){
    g.innerHTML='<div class=\"section-meta\">No stacks yet. Upload files to begin.</div>';
    return;
  }
  const shownStacks = ordered.slice(0,Math.max(1,stacksWindow));
  shownStacks.forEach(s=>{
    const res=resolved(s);
    const pick=getPick(s.id);
    const theme=themeOf(s.id);
    const card=document.createElement('div');
    card.className='stack-card '+(res?'resolved':'unresolved')+(s.ignored?' ignored':'');
    card.onclick=()=>openStack(s.id);
    let fanHTML='';
    const count=s.photos.length;
    if((s.pick||s.previousPick) && pick){
      const p=pick;
      fanHTML=`<div style="position:absolute;inset:10px;border-radius:6px;${photoStyle(p)}display:flex;align-items:flex-end;padding:6px"><span style="font-size:9px;color:rgba(0,0,0,.4)">${escAttr(p?p.label:'')}</span></div>`;
    }else if(count===1){
      const p=getP(s.photos[0]);
      fanHTML=`<div style="position:absolute;inset:10px;border-radius:6px;${photoStyle(p)}"></div>`;
    }else{
      const offs=[[10,14,96,84],[18,22,96,84],[26,30,96,84]];
      s.photos.slice(0,3).forEach((pid,i)=>{
        const p=getP(pid);const[t,l,w,h]=offs[Math.min(i,2)];
        fanHTML+=`<div class="fan-img" style="top:${t}px;left:${l}px;width:${w}px;height:${h}px;z-index:${i+1};${photoStyle(p,'#ccc')}"></div>`;
      });
    }
    const badgeText=s.needsReview?`review needed (+${(s.newIds||[]).length})`:(res?'✓ resolved':'pick needed');
    card.innerHTML=`<div class="stack-photo-area">${fanHTML}
      <div class="stack-badge ${res?'badge-resolved':'badge-pending'}">${badgeText}</div>
    </div>
    <div class="stack-info">
      <div class="stack-name">${s.label}</div>
      <div class="stack-sub">
        <span>${count} shot${count!==1?'s':''}</span>
        ${theme?`<span class="theme-pill" style="border-left:3px solid ${theme.color}">${theme.title}</span>`:'<span style="color:var(--color-text-tertiary);font-size:10px">unassigned</span>'}
      </div>
    </div>`;
    g.appendChild(card);
  });
  const row=document.createElement('div');
  row.style.gridColumn='1 / -1';
  row.innerHTML=renderLimitRow({
    shown:shownStacks.length,
    total:ordered.length,
    onMore:'showMoreStacks()',
    onAll:'showAllStacks()',
    label:'stacks',
  });
  if(row.innerHTML)g.appendChild(row);
}

async function toggleIgnoreStack(){
  if(!openStackId)return;
  const current=getS(openStackId);
  const nextIgnored=!Boolean(current?.ignored);
  const result=await api.ignoreStack(openStackId,nextIgnored);
  if(!result.ok){
    showToast('Could not update ignore state');
    return;
  }
  await syncModelFromApi();
  if(nextIgnored && !showIgnoredStacks){
    closeModal();
  }else{
    openStack(openStackId);
  }
  rerenderActiveLens();
  showToast(nextIgnored?'Stack ignored':'Stack restored');
}

async function deleteCurrentStack(){
  if(!openStackId)return;
  const target=openStackId;
  const result=await api.deleteStack(target);
  if(!result.ok){
    showToast('Delete failed');
    return;
  }
  closeModal();
  await syncModelFromApi();
  rerenderActiveLens();
  showToast('Stack deleted');
}

function openStack(sid){
  const s=getS(sid);if(!s)return;
  setInspectSequence([], 'generic');
  openStackId=sid;tempPick=s.pick||s.previousPick;
  splitMode=false;
  splitSelection=new Set();
  document.getElementById('sm-title').textContent=s.label;
  const g=document.getElementById('sm-grid');g.innerHTML='';
  s.photos.forEach(pid=>{
    const p=getP(pid);if(!p)return;
    const d=document.createElement('div');
    d.className='photo-opt'+((tempPick===pid)?' sel':'');
    d.dataset.pid=pid;d.onclick=()=>selPick(pid);
    d.innerHTML=`<div class="photo-opt-img" style="${photoStyle(p,'#ccc','contain')}display:flex;align-items:flex-end;padding:5px"><span style="font-size:9px;color:rgba(0,0,0,.38)">${escAttr(p.label)}</span></div>
      <div class="photo-opt-lbl">${escAttr(p.label)}</div>
      <div class="checkmark"><div class="ck"></div></div>`;
    bindInspectHover(d.querySelector('.photo-opt-img'),p);
    g.appendChild(d);
  });
  updateSMFoot();
  const splitToggle=document.getElementById('sm-split-mode');
  if(splitToggle)splitToggle.textContent='Split mode';
  document.getElementById('stack-modal').style.display='flex';
}
function selPick(pid){
  if(splitMode){
    if(splitSelection.has(pid))splitSelection.delete(pid);
    else splitSelection.add(pid);
    document.querySelectorAll('.photo-opt').forEach((el)=>{
      el.classList.toggle('sel',splitSelection.has(el.dataset.pid));
    });
    updateSMFoot();
    return;
  }
  tempPick=pid;
  document.querySelectorAll('.photo-opt').forEach(e=>e.classList.toggle('sel',e.dataset.pid===pid));
  updateSMFoot();
}
function updateSMFoot(){
  const splitBtn=document.getElementById('sm-split');
  const splitToggle=document.getElementById('sm-split-mode');
  const confirmBtn=document.getElementById('sm-confirm');
  const ignoreBtn=document.getElementById('sm-ignore');
  const openStack=getS(openStackId);
  if(ignoreBtn && openStack){
    ignoreBtn.textContent=openStack.ignored?'Unignore stack':'Ignore stack';
  }
  if(splitMode){
    const count=splitSelection.size;
    const total=openStack?openStack.photos.length:0;
    document.getElementById('sm-sel-label').textContent=`${count} selected for split`;
    if(confirmBtn)confirmBtn.disabled=true;
    if(splitBtn)splitBtn.disabled=!(count>0 && count<total);
    if(splitToggle)splitToggle.textContent='Exit split mode';
    return;
  }

  const p=tempPick?getP(tempPick):null;
  if(openStack?.needsReview){
    const added=(openStack.newIds||[]).length;
    document.getElementById('sm-sel-label').textContent=p
      ?`Review stack (+${added} new): ${p.label}`
      :`Review required (+${added} new photos)`;
  }else{
    document.getElementById('sm-sel-label').textContent=p?`Selected: ${p.label}`:'None selected';
  }
  if(confirmBtn)confirmBtn.disabled=!tempPick;
  if(splitBtn)splitBtn.disabled=true;
  if(splitToggle)splitToggle.textContent='Split mode';
}
function confirmPick(){
  if(splitMode)return;
  const s=getS(openStackId);
  if(s&&tempPick){s.pick=tempPick;}
  if(openStackId&&tempPick){
    void api.pickDuel({stack_id:openStackId,reference_id:Number(tempPick)});
  }
  closeModal();
  if(activeLens==='stacks')renderStacks();
  else if(activeLens==='timeline')renderTimeline();
  updateBadges();
  duelStacks=buildDuelStacks();
}
function toggleSplitMode(){
  if(!openStackId)return;
  splitMode=!splitMode;
  splitSelection=new Set();
  if(splitMode){
    tempPick=null;
  }else{
    const s=getS(openStackId);
    tempPick=s?(s.pick||s.previousPick):null;
  }
  document.querySelectorAll('.photo-opt').forEach((el)=>{
    const pid=el.dataset.pid;
    el.classList.toggle('sel',splitMode?splitSelection.has(pid):pid===tempPick);
  });
  updateSMFoot();
}
async function splitSelected(){
  const s=getS(openStackId);
  if(!s || !splitMode)return;
  const selectedIds=Array.from(splitSelection).map((pid)=>Number(pid)).filter((pid)=>Number.isFinite(pid));
  if(!selectedIds.length || selectedIds.length>=s.photos.length)return;

  const result=await api.splitStack(openStackId,{
    reference_ids:selectedIds,
    label:'Split stack',
  });
  if(!result.ok){
    showToast('Split failed');
    return;
  }

  await syncModelFromApi();
  closeModal();
  if(activeLens==='stacks')renderStacks();
  if(activeLens==='themes')renderThemes();
  if(activeLens==='timeline')renderTimeline();
  if(activeLens==='book')renderBook();
  updateBadges();
  duelStacks=buildDuelStacks();
  showToast('Stack split');
}
function closeModal(){document.getElementById('stack-modal').style.display='none';hideInspectPreview();setInspectSequence([], 'generic');openStackId=null;tempPick=null;splitMode=false;splitSelection=new Set();}

function buildDuelStacks(){
  return visibleStacks()
    .filter(s=>!resolved(s)&&s.photos.length>1)
    .sort((a,b)=>Number(Boolean(b.needsReview))-Number(Boolean(a.needsReview)));
}

function renderDuel(){
  hideInspectPreview();
  duelStacks=buildDuelStacks();
  const wrap=document.getElementById('duel-wrap');wrap.innerHTML='';
  if(duelStacks.length===0){
    setInspectSequence([], 'generic');
    wrap.innerHTML=`<div class="duel-done"><div class="done-icon">✓</div><div class="done-title">All stacks resolved</div><div class="done-sub">Head to Themes or Book to continue</div></div>`;
    return;
  }
  if(duelIdx>=duelStacks.length)duelIdx=0;
  const s=duelStacks[duelIdx];
  const pips=duelStacks.map((ds,i)=>
    `<div class="duel-pip ${i<duelIdx?'done':i===duelIdx?'current':''}"></div>`).join('');
  const votes=duelState[s.id]||{};

  let pairA=s.photos[0],pairB=s.photos[1];
  if(s.needsReview && s.previousPick && s.photos.includes(s.previousPick)){
    pairA=s.previousPick;
    const candidate=(s.newIds||[]).find((pid)=>s.photos.includes(pid) && pid!==pairA);
    pairB=candidate||s.photos.find((pid)=>pid!==pairA)||pairB;
  }
  const pA=getP(pairA),pB=getP(pairB);
  setInspectSequence([pairA,pairB],'duel');
  const votesA=Object.values(votes).filter(v=>v===pairA).length;
  const votesB=Object.values(votes).filter(v=>v===pairB).length;
  const pickedA=s.pick===pairA,pickedB=s.pick===pairB;

  const collabAvatars=[
    {init:'MK',bg:'#E1F5EE',fg:'#085041',vote:pairA},
    {init:'JL',bg:'#FAECE7',fg:'#712B13',vote:pairB},
  ];

  function cardHTML(pid,p,picked,otherPicked,voteCount,avatars){
    const cls=`duel-card${picked?' winner':otherPicked?' loser':''}`;
    const avHTML=avatars.filter(a=>a.vote===pid).map(a=>`<div class="duel-voter" style="background:${a.bg};color:${a.fg}">${a.init}</div>`).join('');
    return`<div class="${cls}" onclick="pickDuel('${s.id}','${pid}')">
      <div class="duel-img" data-pid="${escAttr(pid)}" style="${photoStyle(p,'#ccc','contain')}">
        <div class="duel-img-label">${escAttr(p?p.label:'')}</div>
      </div>
      <div class="duel-footer">
        <div class="duel-voter-row">${avHTML}</div>
        <span style="font-size:11px;color:var(--color-text-tertiary)">${voteCount} vote${voteCount!==1?'s':''}</span>
        ${picked?`<span style="font-size:11px;color:#1D9E75;font-weight:500">✓ your pick</span>`:''}
      </div>
    </div>`;
  }

  const remainLabel=duelStacks.length-duelIdx+' remaining';
  wrap.innerHTML=`<div class="duel-progress" style="width:100%">
    <div class="duel-queue">${pips}</div>
    <span style="margin-left:auto">${remainLabel}</span>
    <button class="duel-skip" onclick="skipDuel()">Skip for now</button>
  </div>
  <div class="duel-stack-name">${s.label}</div>
  <div class="duel-hint">${s.needsReview?'New photos joined this stack. Confirm or replace the previous winner.':'Tap the photo you\'d pick for this stack'}</div>
  <div class="duel-compare-row">
    <button class="duel-compare-switch" type="button" onclick="cycleInspectDuel(1,event)" title="Switch preview">⇄</button>
    <span>Hover either photo, then use Tab/←/→ or right-click to switch.</span>
  </div>
  <div class="duel-arena">
    ${cardHTML(pairA,pA,pickedA,pickedB,votesA,collabAvatars)}
    <div class="duel-vs"><div class="vs-circle">vs</div></div>
    ${cardHTML(pairB,pB,pickedB,pickedA,votesB,collabAvatars)}
  </div>
  ${s.photos.length>2?`<div style="font-size:11px;color:var(--color-text-tertiary)">Showing 2 of ${s.photos.length} shots — <span style="cursor:pointer;color:#7F77DD" onclick="openStack('${s.id}')">see all in grid</span></div>`:''}`;
  wrap.querySelectorAll('.duel-img').forEach((el)=>{
    const pid=el.getAttribute('data-pid');
    if(!pid)return;
    bindDuelInspect(el,pid);
  });
}

function pickDuel(sid,pid){
  const s=getS(sid);if(!s)return;
  s.pick=pid;
  if(!duelState[sid])duelState[sid]={};
  duelState[sid]['you']=pid;
  void api.pickDuel({stack_id:sid,reference_id:Number(pid)});
  updateBadges();
  setTimeout(()=>{duelIdx++;if(duelIdx>=duelStacks.length)duelIdx=0;renderDuel();},420);
}
function skipDuel(){duelIdx=(duelIdx+1)%Math.max(duelStacks.length,1);renderDuel();}

function renderThemes(){
  const canvas=document.getElementById('themes-canvas');canvas.innerHTML='';
  const pool=document.getElementById('pool-chips');pool.innerHTML='';
  const visibleIds=visibleStackIds();
  themes.forEach(t=>{
    const orderedStacks=t.stacks
      .filter((sid)=>visibleIds.has(String(sid)))
      .sort((a,b)=>compareStackPriority(getS(a),getS(b)));
    const shownStacks=orderedStacks.slice(0,getThemeWindow(t.id));
    const block=document.createElement('div');block.className='theme-block';block.dataset.tid=t.id;
    block.innerHTML=`<div class="theme-head">
      <div class="theme-head-top">
        <div class="theme-color-dot" style="background:${t.color}"></div>
        <input class="theme-title-inp" value="${escAttr(t.title)}" onchange="renameTheme('${t.id}',this.value)"/>
        <span class="theme-count">${orderedStacks.length} stack${orderedStacks.length!==1?'s':''}</span>
        <button class="ibc" onclick="goLens('book');setActiveTheme('${t.id}')">→ book</button>
        <button class="ibc del" onclick="delTheme('${t.id}')">✕</button>
      </div>
      <input class="theme-desc-inp" placeholder="Describe theme for AI assignment" value="${escAttr(t.description||'')}" onchange="renameThemeDescription('${t.id}',this.value)"/>
    </div>
    <div class="theme-chips" id="tc-${t.id}" ondragover="dov(event,'${t.id}')" ondrop="ddr(event,'${t.id}')" ondragleave="dlv(event)"></div>
    <div class="drop-target" id="dt-${t.id}" ondragover="dov(event,'${t.id}')" ondrop="ddr(event,'${t.id}')" ondragleave="dlv(event)">Drop stacks here</div>`;
    canvas.appendChild(block);
    const chipsEl=block.querySelector(`#tc-${t.id}`);
    shownStacks.forEach(sid=>chipsEl.appendChild(makeChip(sid,t.id)));
    if(!shownStacks.length){
      chipsEl.innerHTML='<span style="font-size:12px;color:var(--color-text-tertiary)">No visible stacks</span>';
    }
    const dropEl=block.querySelector(`#dt-${t.id}`);
    if(dropEl){
      dropEl.insertAdjacentHTML(
        'afterend',
        renderLimitRow({
          shown:shownStacks.length,
          total:orderedStacks.length,
          onMore:`showMoreThemeStacks('${t.id}')`,
          onAll:`showAllThemeStacks('${t.id}')`,
          label:'stacks',
        }),
      );
    }
  });
  const addBtn=document.createElement('div');addBtn.className='add-theme-row';
  addBtn.innerHTML=`<button class="add-theme-btn" onclick="addTheme()">+ New theme</button>`;
  canvas.appendChild(addBtn);
  const orderedPool=unassigned
    .filter((sid)=>visibleIds.has(String(sid)))
    .sort((a,b)=>compareStackPriority(getS(a),getS(b)));
  const shownPool=orderedPool.slice(0,Math.max(1,poolWindow));
  shownPool.forEach(sid=>pool.appendChild(makeChip(sid,'pool')));
  if(!shownPool.length)pool.innerHTML=`<span style="font-size:12px;color:var(--color-text-tertiary)">All assigned</span>`;
  const poolBox=document.getElementById('pool-box');
  if(poolBox){
    const existing=poolBox.querySelector('.lens-limit-row');
    if(existing)existing.remove();
    poolBox.insertAdjacentHTML(
      'beforeend',
      renderLimitRow({
        shown:shownPool.length,
        total:orderedPool.length,
        onMore:'showMorePool()',
        onAll:'showAllPool()',
        label:'stacks',
      }),
    );
  }
}

function makeChip(sid,from){
  const s=getS(sid);if(!s)return document.createElement('span');
  const pick=getPick(sid);
  const day = Number.isNaN(new Date(s.date).getTime())
    ? ''
    : new Date(s.date).toLocaleDateString('default',{weekday:'short',day:'numeric'});
  const isPool=from==='pool';
  const res=resolved(s);
  const chip=document.createElement('div');
  chip.className=`theme-stack-card tl-card ${res?'resolved':'unresolved'}`;
  chip.draggable=true;
  chip.dataset.sid=sid;
  chip.dataset.from=from;
  const assignOptions = [
    `<button class="chip-assign-item" type="button" onclick="chipQuickAssign(event,'${sid}','${from}','pool')">Unassigned</button>`,
    ...themes.map((theme)=>`<button class="chip-assign-item" type="button" onclick="chipQuickAssign(event,'${sid}','${from}','${escAttr(theme.id)}')">${escAttr(theme.title)}</button>`),
    `<button class="chip-assign-item chip-assign-new" type="button" onclick="chipQuickAssignNew(event,'${sid}','${from}')">+ New theme…</button>`,
  ].join('');
  chip.innerHTML=`<div class="tl-thumb" style="${photoStyle(pick)}"></div>
    ${isPool?'<div class="theme-stack-badge">unassigned</div>':''}
    <div class="tl-info">
      <div class="tl-name">${escAttr(s.label)}</div>
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-top:1px">${escAttr(day)}</div>
    </div>
    ${isPool?'':`<button class="theme-stack-remove" title="Remove from theme" onclick="chipRemove(event,'${sid}','${from}')">✕</button>`}
    <div class="chip-qa" onclick="event.stopPropagation()">
      <button class="chip-qa-btn chip-qa-assign" type="button" onclick="chipToggleAssignMenu(event,this)">Assign</button>
      <div class="chip-assign-pop">${assignOptions}</div>
      <button class="chip-qa-btn" type="button" onclick="chipQuickIgnore(event,'${sid}')">${s.ignored?'Unignore':'Ignore'}</button>
      <button class="chip-qa-btn danger" type="button" onclick="chipQuickDelete(event,'${sid}')">Delete</button>
    </div>`;
  chip.onclick=()=>openStack(sid);
  chip.ondragstart=e=>{dragSid=sid;dragFrom=from;chip.classList.add('dragging');};
  chip.ondragend=()=>{chip.classList.remove('dragging');clearDrop();};
  return chip;
}
function dov(e,tid){e.preventDefault();document.querySelectorAll('.drop-target,.pool-drop').forEach(d=>d.classList.remove('over'));(document.getElementById('dt-'+tid)||document.getElementById('pool-drop'))?.classList.add('over');}
function dlv(e){if(!e.currentTarget.contains(e.relatedTarget))clearDrop();}
function clearDrop(){document.querySelectorAll('.drop-target,.pool-drop').forEach(d=>d.classList.remove('over'));}
function ddr(e,toTid){
  e.preventDefault();clearDrop();
  if(!dragSid||dragFrom===toTid){dragSid=null;dragFrom=null;return;}
  if(dragFrom==='pool')unassigned=unassigned.filter(x=>x!==dragSid);
  else{const t=themes.find(x=>x.id===dragFrom);if(t)t.stacks=t.stacks.filter(x=>x!==dragSid);}
  if(toTid==='pool')unassigned.push(dragSid);
  else{const t=themes.find(x=>x.id===toTid);if(t)t.stacks.push(dragSid);}
  void api.assignTheme({stack_id:String(dragSid),theme_id:toTid==='pool'?null:Number(toTid)});
  dragSid=null;dragFrom=null;
  renderThemes();updateBadges();
}
function chipRemove(event,sid,from){
  event?.stopPropagation();
  if(from==='pool')return;
  const t=themes.find(x=>x.id===from);if(t)t.stacks=t.stacks.filter(x=>x!==sid);
  void api.assignTheme({stack_id:String(sid),theme_id:null});
  unassigned.push(sid);renderThemes();
}
function normalizeStackFrom(sid,fallback='pool'){
  const theme=themeOf(sid);
  if(theme)return theme.id;
  if(unassigned.includes(sid))return 'pool';
  return fallback;
}
function closeAssignMenus(){
  document.querySelectorAll('.chip-assign-pop.open').forEach((el)=>el.classList.remove('open'));
}
function chipToggleAssignMenu(event,button){
  event?.stopPropagation();
  const pop=button?.nextElementSibling;
  if(!pop)return;
  const willOpen=!pop.classList.contains('open');
  closeAssignMenus();
  if(willOpen)pop.classList.add('open');
}
async function assignStackToTheme(sid,from,toTid){
  const source=normalizeStackFrom(sid,from);
  if(source===toTid)return;
  if(source==='pool')unassigned=unassigned.filter(x=>x!==sid);
  else{
    const srcTheme=themes.find(x=>x.id===source);
    if(srcTheme)srcTheme.stacks=srcTheme.stacks.filter(x=>x!==sid);
  }
  if(toTid==='pool'){
    if(!unassigned.includes(sid))unassigned.push(sid);
  }else{
    const targetTheme=themes.find(x=>x.id===toTid);
    if(targetTheme && !targetTheme.stacks.includes(sid))targetTheme.stacks.push(sid);
  }
  renderThemes();
  updateBadges();
  const result=await api.assignTheme({stack_id:String(sid),theme_id:toTid==='pool'?null:Number(toTid)});
  if(!result.ok){
    await syncModelFromApi();
    rerenderActiveLens();
    showToast('Could not assign stack');
  }
}
async function chipQuickAssign(event,sid,from,toTid){
  event?.stopPropagation();
  closeAssignMenus();
  await assignStackToTheme(sid,from,toTid);
}
async function chipQuickAssignNew(event,sid,from){
  event?.stopPropagation();
  closeAssignMenus();
  const created=await api.addTheme({title:'New theme'});
  if(!created.ok){
    showToast('Could not create theme');
    return;
  }
  await syncModelFromApi();
  const nextThemeId=String(created.data?.id||'');
  if(!nextThemeId){
    rerenderActiveLens();
    return;
  }
  await assignStackToTheme(sid,normalizeStackFrom(sid,from),nextThemeId);
}
async function chipAssignSelect(event,sid,from,value){
  event?.stopPropagation();
  if(!value)return;
  if(value==='__new__'){
    const created=await api.addTheme({title:'New theme'});
    if(!created.ok){
      showToast('Could not create theme');
      return;
    }
    await syncModelFromApi();
    const nextThemeId=String(created.data?.id||'');
    if(!nextThemeId){
      rerenderActiveLens();
      return;
    }
    await assignStackToTheme(sid,normalizeStackFrom(sid,from),nextThemeId);
    return;
  }
  await assignStackToTheme(sid,from,value);
}
async function chipQuickIgnore(event,sid){
  event?.stopPropagation();
  const stack=getS(sid);
  const nextIgnored=!Boolean(stack?.ignored);
  const result=await api.ignoreStack(sid,nextIgnored);
  if(!result.ok){
    showToast('Could not update ignore state');
    return;
  }
  await syncModelFromApi();
  rerenderActiveLens();
  showToast(nextIgnored?'Stack ignored':'Stack restored');
}
async function chipQuickDelete(event,sid){
  event?.stopPropagation();
  if(!window.confirm('Delete this stack and its source files?'))return;
  const result=await api.deleteStack(sid);
  if(!result.ok){
    showToast('Delete failed');
    return;
  }
  await syncModelFromApi();
  rerenderActiveLens();
  showToast('Stack deleted');
}
function renameTheme(tid,val){
  const t=themes.find(x=>x.id===tid);if(t)t.title=val;
  void api.patchTheme(Number(tid),{title:val});
  renderBookNav();
}
function renameThemeDescription(tid,val){
  const t=themes.find(x=>x.id===tid);if(t)t.description=val;
  void api.patchTheme(Number(tid),{description:val});
}
function delTheme(tid){
  const t=themes.find(x=>x.id===tid);if(t)unassigned.push(...t.stacks);
  themes=themes.filter(x=>x.id!==tid);
  void api.deleteTheme(Number(tid));
  renderThemes();renderBookNav();
}
async function addTheme(){
  const next='New theme';
  const created=await api.addTheme({title:next});
  if(created.ok){
    await syncModelFromApi();
  }
  renderThemes();updateBadges();
}
function reassignReasonMessage(reason){
  if(reason==='no_gateway_config')return 'AI gateway is not configured';
  if(reason==='llm_http_error')return 'AI request failed';
  if(reason==='schema_parse_failed')return 'AI returned invalid structured output';
  if(reason==='llm_refusal')return 'AI refused the request';
  if(reason==='no_llm_output')return 'AI returned no output';
  if(reason==='no_unassigned_stacks')return 'No unassigned stacks to process';
  if(reason==='no_confident_matches')return 'No confident matches for current unassigned stacks';
  return 'Unknown AI assignment outcome';
}
async function rerunThemeAssignment(){
  showUploadOverlay('Re-running AI assignment','Preparing themes and unassigned stacks',8,{
    phase:'refining',
    isRealUpdate:true,
    batchLabel:'Theme assignment',
    batchPercent:8,
  });
  let pulse=8;
  const pulseTimer=setInterval(()=>{
    pulse=Math.min(92,pulse+4);
    showUploadOverlay('Re-running AI assignment','Building contact sheets and asking model',pulse,{
      phase:'refining',
      isRealUpdate:false,
      batchLabel:'Theme assignment',
      batchPercent:pulse,
    });
  },350);

  const result=await api.reassignThemes();
  clearInterval(pulseTimer);
  if(!result.ok){
    const reason=String(result.data?.detail?.reason||'unknown');
    const detail=reassignReasonMessage(reason);
    showUploadOverlay('AI assignment failed',detail,100,{
      failed:true,
      phase:'failed',
      isRealUpdate:true,
      batchLabel:'Theme assignment',
      batchPercent:100,
    });
    await new Promise((resolve)=>setTimeout(resolve,1200));
    hideUploadOverlay();
    showToast(`AI re-assignment failed: ${detail}`);
    return;
  }

  showUploadOverlay('Re-running AI assignment','Applying assigned stacks to themes',97,{
    phase:'refining',
    isRealUpdate:true,
    batchLabel:'Theme assignment',
    batchPercent:97,
  });
  await syncModelFromApi();
  rerenderActiveLens();
  const assigned=Number(result.data?.summary?.assigned_stacks||0);
  const created=Number(result.data?.summary?.created_themes||0);
  const reason=String(result.data?.summary?.reason||'ok');
  const detail=assigned>0
    ?`Assigned ${assigned} stack${assigned!==1?'s':''}${created>0?` and created ${created} theme${created!==1?'s':''}`:''}`
    :reassignReasonMessage(reason);
  showUploadOverlay('AI assignment complete',detail,100,{
    phase:'completed',
    isRealUpdate:true,
    batchLabel:'Theme assignment',
    batchPercent:100,
  });
  await new Promise((resolve)=>setTimeout(resolve,900));
  hideUploadOverlay();
  if(assigned>0){
    showToast(`AI assigned ${assigned} stack${assigned!==1?'s':''}${created>0?` · +${created} theme${created!==1?'s':''}`:''}`);
  }else{
    showToast(`AI assigned 0 stacks: ${detail}`);
  }
}

function renderTimeline(){
  const wrap=document.getElementById('timeline-wrap');wrap.innerHTML='';
  const ordered=prioritizedVisibleStacks().slice(0,Math.max(1,timelineWindow));
  const byMonth={};
  ordered.forEach(s=>{
    const d=new Date(s.date);const key=d.toLocaleString('default',{month:'long',year:'numeric'});
    if(!byMonth[key])byMonth[key]=[];
    byMonth[key].push(s);
  });
  Object.entries(byMonth).sort((a,b)=>new Date(a[1][0].date)-new Date(b[1][0].date)).forEach(([month,stacks])=>{
    const sec=document.createElement('div');sec.className='tl-month';
    sec.innerHTML=`<div class="tl-month-label">${month}</div>`;
    const row=document.createElement('div');row.className='tl-row';
    stacks.sort((a,b)=>new Date(a.date)-new Date(b.date)).forEach(s=>{
      const res=resolved(s);const theme=themeOf(s.id);const pick=getPick(s.id);
      const card=document.createElement('div');
      card.className='tl-card '+(res?'resolved':'unresolved');
      card.onclick=()=>openStack(s.id);
      const d=new Date(s.date);const dayStr=d.toLocaleDateString('default',{weekday:'short',day:'numeric'});
      card.innerHTML=`<div class="tl-thumb" style="${photoStyle(pick)}"></div>
        <div class="tl-info">
          <div class="tl-name">${s.label}</div>
          <div class="tl-sub">
            ${theme?`<div class="tl-theme-dot" style="background:${theme.color}"></div><span style="font-size:10px;color:var(--color-text-tertiary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px">${theme.title}</span>`:'<span style="font-size:10px;color:var(--color-text-tertiary)">unassigned</span>'}
          </div>
          <div style="font-size:10px;color:var(--color-text-tertiary);margin-top:1px">${dayStr}</div>
        </div>`;
      row.appendChild(card);
    });
    sec.appendChild(row);wrap.appendChild(sec);
  });
  wrap.insertAdjacentHTML(
    'beforeend',
    renderLimitRow({
      shown:ordered.length,
      total:visibleStacks().length,
      onMore:'showMoreTimeline()',
      onAll:'showAllTimeline()',
      label:'stacks',
    }),
  );
}

function renderBook(){
  renderBookNav();
  if(!activeThemeId&&themes.length>0){
    setActiveTheme(themes[0].id);
  }else if(activeThemeId){
    setActiveTheme(activeThemeId);
  }
  if(activeThemeId)void ensureThemeChapter(activeThemeId);
}
function renderBookNav(){
  const nav=document.getElementById('book-nav');nav.innerHTML='<div class="book-nav-head">Themes</div>';
  const visibleIds=visibleStackIds();
  themes.forEach(t=>{
    const visibleThemeCount=t.stacks.filter((sid)=>visibleIds.has(String(sid))).length;
    const pg=(pages[t.id]||[]).length;
    const item=document.createElement('div');
    item.className='book-nav-item'+(activeThemeId===t.id?' active':'');
    item.innerHTML=`<div style="display:flex;align-items:center;gap:6px"><div style="width:8px;height:8px;border-radius:50%;background:${t.color};flex-shrink:0"></div>${t.title}</div><div class="book-nav-sub">${pg} page${pg!==1?'s':''} · ${visibleThemeCount} stack${visibleThemeCount!==1?'s':''}</div>`;
    item.onclick=()=>setActiveTheme(t.id);
    nav.appendChild(item);
  });
  updateBadges();
}
function setActiveTheme(tid){
  activeThemeId=tid;const t=themes.find(x=>x.id===tid);if(!t)return;
  renderBookNav();
  document.getElementById('book-head-title').textContent=t.title;
  if(!pages[tid])pages[tid]=[];
  renderPagesRow(tid);
  if((pages[tid]||[]).length>0){setActivePage(pages[tid][0].id,tid);}
  else{document.getElementById('page-editor-area').style.display='none';}
  void ensureThemeChapter(tid);
}
function renderPagesRow(tid){
  const row=document.getElementById('pages-row');row.innerHTML='';
  const allPages=(pages[tid]||[]);
  const shownPages=allPages.slice(0,getBookPagesWindow(tid));
  shownPages.forEach(pg=>{
    const card=document.createElement('div');card.className='pg-thumb'+(activePage===pg.id?' active-pg':'');
    const sl=slots[pg.id]||[];const lay=pg.layout||'2x2';
    const n=lay==='1x1'?1:lay==='2x1'?2:lay==='1+2'?3:4;
    let prevHTML='';
    const gcols=lay==='1x1'?'1fr':lay==='2x1'?'1fr 1fr':lay==='1+2'?'1fr 1fr':lay==='2x2'?'1fr 1fr':'1fr 1fr';
    const grows=lay==='2x2'||lay==='1+2'?'1fr 1fr':'1fr';
    for(let i=0;i<n;i++){
      const s=sl[i];const p=s&&s.type==='photo'?getP(s.pid):null;
      const span=lay==='1+2'&&i===0?'grid-row:1/3':'';
      prevHTML+=`<div style="${photoStyle(p)}border-radius:2px;${span}"></div>`;
    }
    card.innerHTML=`<div class="pg-preview" style="grid-template-columns:${gcols};grid-template-rows:${grows}">${prevHTML}</div>
      <div class="pg-foot">p.${pg.num}</div>`;
    card.onclick=()=>setActivePage(pg.id,tid);
    row.appendChild(card);
  });
  const add=document.createElement('button');add.className='add-pg';
  add.innerHTML=`<div style="width:24px;height:24px;border-radius:50%;border:1.5px solid var(--color-border-secondary);display:flex;align-items:center;justify-content:center;font-size:15px;color:var(--color-text-tertiary)">+</div><span>Add page</span>`;
  add.onclick=()=>addPage(tid);row.appendChild(add);
  row.insertAdjacentHTML(
    'beforeend',
    renderLimitRow({
      shown:shownPages.length,
      total:allPages.length,
      onMore:`showMoreBookPages('${tid}')`,
      onAll:`showAllBookPages('${tid}')`,
      label:'pages',
    }),
  );
}
async function addPage(tid){
  const chapterId=await ensureThemeChapter(tid);
  if(chapterId){
    const targetCount=(pages[tid]||[]).length+1;
    const syncRes=await api.syncChapterPages(chapterId,{page_count:targetCount});
    if(syncRes.ok && Array.isArray(syncRes.data?.items)){
      applyBackendPages(tid,syncRes.data.items);
    }
  }else{
    const id='pg'+(++pgCtr);const num=(pages[tid]||[]).length+1;
    if(!pages[tid])pages[tid]=[];pages[tid].push({id,num,layout:'2x2'});slots[id]=[];
  }

  const items=pages[tid]||[];
  const last=items[items.length-1];
  renderPagesRow(tid);
  if(last){
    if(!slots[last.id])slots[last.id]=[];
    setActivePage(last.id,tid);
  }
  renderBookNav();
}
function setActivePage(pid,tid){
  activePage=pid;
  const pg=(pages[tid]||[]).find(x=>x.id===pid);if(!pg)return;
  curLayout=pg.layout||'2x2';
  renderPageCanvas(pid,tid);
  renderPagesRow(tid);
  document.getElementById('page-editor-area').style.display='flex';
  renderPPList(tid);
  document.querySelectorAll('.lb').forEach(b=>b.classList.remove('on'));
  const lmap={'2x2':0,'1x1':1,'2x1':2,'1+2':3};
  document.querySelectorAll('.lb')[lmap[curLayout]||0]?.classList.add('on');
}
function renderPageCanvas(pid,tid){
  const canvas=document.getElementById('page-canvas');
  canvas.querySelectorAll('.slot').forEach(e=>e.remove());
  const sl=slots[pid]||[];
  const lay=curLayout;
  const n=lay==='1x1'?1:lay==='2x1'?2:lay==='1+2'?3:4;
  canvas.style.gridTemplateColumns=lay==='1x1'?'1fr':'1fr 1fr';
  canvas.style.gridTemplateRows=lay==='2x2'||lay==='1+2'?'1fr 1fr':'1fr';
  const lb=canvas.querySelector('.layout-bar');
  for(let i=n-1;i>=0;i--){
    const el=document.createElement('div');el.className='slot'+(sl[i]?' filled':'');
    el.dataset.idx=i;
    if(lay==='1+2'&&i===0)el.style.gridRow='1/3';
    const s=sl[i];const p=s&&s.type==='photo'?getP(s.pid):null;
    if(p){
      el.innerHTML=`<div style="width:100%;height:100%;${photoStyle(p)}display:flex;align-items:flex-end;padding:7px"><span style="font-size:9px;color:rgba(0,0,0,.35)">${escAttr(p.label)}</span></div><button class="slot-rm" onclick="rmSlot('${pid}',${i},event)">✕</button>`;
    }else if(s&&s.type==='text'){
      el.innerHTML=`<div style="width:100%;background:#E6F1FB;padding:8px 10px;font-size:11px;color:#185FA5">${s.text}</div><button class="slot-rm" onclick="rmSlot('${pid}',${i},event)">✕</button>`;
    }else{
      el.innerHTML=`<span class="slot-hint">+ drop photo</span>`;
    }
    el.ondragover=e=>{e.preventDefault();el.style.outline='2px solid #7F77DD';};
    el.ondragleave=()=>el.style.outline='';
    el.ondrop=e=>{
      e.preventDefault();el.style.outline='';
      const dpid=e.dataTransfer.getData('pid');
      if(dpid){if(!slots[pid])slots[pid]=[];while(slots[pid].length<=i)slots[pid].push(null);slots[pid][i]={type:'photo',pid:dpid};renderPageCanvas(pid,tid);renderPagesRow(tid);}
    };
    canvas.insertBefore(el,lb);
  }
}
function rmSlot(pid,idx,e){e.stopPropagation();if(slots[pid])slots[pid][idx]=null;renderPageCanvas(pid,activeThemeId);renderPagesRow(activeThemeId);}
function setLay(lay,btn){
  curLayout=lay;document.querySelectorAll('.lb').forEach(b=>b.classList.remove('on'));btn.classList.add('on');
  const pg=(pages[activeThemeId]||[]).find(x=>x.id===activePage);if(pg)pg.layout=lay;
  renderPageCanvas(activePage,activeThemeId);renderPagesRow(activeThemeId);
}
function renderPPList(tid){
  const t=themes.find(x=>x.id===tid);const list=document.getElementById('pp-list');list.innerHTML='';
  if(!t)return;
  const visibleIds=visibleStackIds();
  const ordered=t.stacks
    .filter((sid)=>visibleIds.has(String(sid)))
    .sort((a,b)=>compareStackPriority(getS(a),getS(b)));
  const shown=ordered.slice(0,getBookPhotosWindow(tid));
  shown.forEach(sid=>{
    const pick=getPick(sid);const s=getS(sid);if(!pick)return;
    const el=document.createElement('div');el.className='pp-item';el.draggable=true;
    el.innerHTML=`<div class="pp-img" style="${photoStyle(pick)}display:flex;align-items:flex-end;padding:3px"><span style="font-size:8px;color:rgba(0,0,0,.35)">${escAttr(pick.label)}</span></div>
      <div class="pp-name">${escAttr(s?s.label:'')}</div>`;
    el.ondragstart=e=>e.dataTransfer.setData('pid',pick.id);
    list.appendChild(el);
  });
  if(!shown.length){
    list.innerHTML='<span style="font-size:12px;color:var(--color-text-tertiary)">No visible theme photos</span>';
  }
  list.insertAdjacentHTML(
    'beforeend',
    renderLimitRow({
      shown:shown.length,
      total:ordered.length,
      onMore:`showMoreBookPhotos('${tid}')`,
      onAll:`showAllBookPhotos('${tid}')`,
      label:'photos',
    }),
  );
}
async function addTxt(){
  if(!activeThemeId)return;
  await ensureThemeChapter(activeThemeId);

  if(!activePage){
    const first=(pages[activeThemeId]||[])[0];
    if(first){
      setActivePage(first.id,activeThemeId);
    }
  }
  if(!activePage)return;

  if(!slots[activePage])slots[activePage]=[];
  const lay=curLayout;const n=lay==='1x1'?1:lay==='2x1'?2:lay==='1+2'?3:4;
  for(let i=0;i<n;i++){
    if(!slots[activePage][i]){
      const text='Our story...';
      slots[activePage][i]={type:'text',text};
      void api.addPageText(activePage,{
        item_type:'text',
        text,
        x:0.08,
        y:0.08,
        w:0.84,
        h:0.24,
        z:i,
      });
      renderPageCanvas(activePage,activeThemeId);
      renderPagesRow(activeThemeId);
      return;
    }
  }
}

function openShare(){document.getElementById('share-modal').style.display='flex';}
function selRole(el){document.querySelectorAll('.role-card').forEach(c=>c.classList.remove('sel-role'));el.classList.add('sel-role');}
function copyLink(){
  const inp=document.getElementById('share-url-inp');inp.select();
  try{document.execCommand('copy');}catch(e){}
  showToast('Link copied to clipboard');
}

function uploadStageTitle(phase){
  if(phase==='uploading')return 'Uploading folder';
  if(phase==='indexing')return 'Indexing files';
  if(phase==='provisional_clustering')return 'Publishing provisional stacks';
  if(phase==='refining')return 'Refining stacks and themes';
  if(phase==='completed')return 'Upload complete';
  if(phase==='failed')return 'Upload failed';
  return 'Working';
}

function uploadStageDetail(progress){
  if(progress?.phase==='indexing'){
    const done=Number(progress.files_done||0);
    const total=Number(progress.files_total||0);
    if(total>0){
      return `Indexed ${done}/${total} files`;
    }
  }
  if(progress?.phase==='provisional_clustering'){
    const visible=Number(progress.stacks_visible||0);
    return visible>0?`Stacks visible: ${visible}`:'Computing first stack pass';
  }
  if(progress?.phase==='refining'){
    return 'Applying duplicate, stack, and theme refinement';
  }
  if(progress?.phase==='failed'){
    return progress.error||'Upload failed';
  }
  return progress?.message||'Working...';
}

function chunkEntries(entries,size){
  if(!Array.isArray(entries) || !entries.length)return [];
  const safeSize=Math.max(1,Math.floor(size||1));
  const out=[];
  for(let i=0;i<entries.length;i+=safeSize){
    out.push(entries.slice(i,i+safeSize));
  }
  return out;
}

function overallPercentForBatch(batchIndex,batchTotal,batchPercent){
  const total=Math.max(1,Number(batchTotal||1));
  const idx=Math.max(0,Math.min(total-1,Number(batchIndex||0)));
  const frac=Math.max(0,Math.min(1,(Number(batchPercent||0))/100));
  return Math.round(((idx+frac)/total)*100);
}

function batchLabelFor(batchIndex,batchTotal){
  const total=Math.max(1,Number(batchTotal||1));
  const idx=Math.max(0,Math.min(total-1,Number(batchIndex||0)));
  return `Batch ${idx+1}/${total}`;
}

function tipPoolForPhase(phase){
  return UPLOAD_IDLE_TIPS[phase] || UPLOAD_IDLE_TIPS.generic;
}

function setUploadTip(text){
  const tipEl=document.getElementById('upload-progress-tip');
  if(!tipEl)return;
  if(!text){
    tipEl.textContent='';
    tipEl.classList.remove('show');
    tipEl.style.display='none';
    return;
  }
  tipEl.style.display='block';
  tipEl.textContent=text;
  tipEl.classList.add('show');
}

function nextUploadTip(){
  const phase=uploadTipPhase||'generic';
  const pool=tipPoolForPhase(phase);
  if(!pool.length){
    setUploadTip('');
    return;
  }
  const baseIndex=Number(uploadTipIndexByPhase[phase]||0);
  let idx=baseIndex%pool.length;
  let tip=pool[idx];
  if(pool.length>1 && tip===uploadLastTipText){
    idx=(idx+1)%pool.length;
    tip=pool[idx];
  }
  uploadTipIndexByPhase[phase]=(idx+1)%pool.length;
  uploadLastTipText=tip;
  setUploadTip(tip);
}

function stopUploadTipRotation(){
  if(uploadTipRotateTimer!==null){
    clearInterval(uploadTipRotateTimer);
    uploadTipRotateTimer=null;
  }
}

function stopUploadIdleCountdown(){
  if(uploadIdleCountdownTimer!==null){
    clearTimeout(uploadIdleCountdownTimer);
    uploadIdleCountdownTimer=null;
  }
}

function resetUploadTipState(){
  stopUploadTipRotation();
  stopUploadIdleCountdown();
  uploadIdleActive=false;
  uploadTipPhase='uploading';
  uploadLastRealUpdateAt=0;
  uploadLastTipText='';
  setUploadTip('');
}

function exitUploadIdleMode(){
  uploadIdleActive=false;
  stopUploadTipRotation();
  setUploadTip('');
}

function beginUploadIdleModeIfNeeded(){
  if(uploadIdleActive)return;
  uploadIdleActive=true;
  nextUploadTip();
  stopUploadTipRotation();
  uploadTipRotateTimer=setInterval(()=>{
    if(!uploadIdleActive)return;
    nextUploadTip();
  },UPLOAD_IDLE_TIP_ROTATE_MS);
}

function scheduleUploadIdleCountdown(){
  stopUploadIdleCountdown();
  const overlay=document.getElementById('upload-progress-overlay');
  if(!overlay || overlay.style.display!=='flex')return;
  uploadIdleCountdownTimer=setTimeout(()=>{
    uploadIdleCountdownTimer=null;
    const liveOverlay=document.getElementById('upload-progress-overlay');
    if(!liveOverlay || liveOverlay.style.display!=='flex')return;
    beginUploadIdleModeIfNeeded();
  },UPLOAD_IDLE_TIP_DELAY_MS);
}

function applyUploadActivityState({phase,isRealUpdate,failed}){
  uploadTipPhase=phase||uploadTipPhase;
  if(isRealUpdate){
    uploadLastRealUpdateAt=Date.now();
    exitUploadIdleMode();
    if(!(failed || phase==='completed' || phase==='failed')){
      scheduleUploadIdleCountdown();
    }
  }
  if(failed || phase==='completed' || phase==='failed'){
    resetUploadTipState();
    return;
  }
  if(!isRealUpdate){
    scheduleUploadIdleCountdown();
  }
}

function showUploadOverlay(title,detail,percent,{failed=false,phase='working',isRealUpdate=false,batchLabel='Batch 1/1',batchPercent=0}={}){
  const overlay=document.getElementById('upload-progress-overlay');
  if(!overlay)return;
  const pct=Math.max(0,Math.min(100,Math.round(percent)));
  const batchPct=Math.max(0,Math.min(100,Math.round(batchPercent)));
  overlay.style.display='flex';
  overlay.classList.toggle('failed',failed);
  const titleEl=document.getElementById('upload-progress-title');
  const pctEl=document.getElementById('upload-progress-percent');
  const fillEl=document.getElementById('upload-progress-fill');
  const batchLabelEl=document.getElementById('upload-progress-batch-label');
  const batchPctEl=document.getElementById('upload-progress-batch-percent');
  const batchFillEl=document.getElementById('upload-progress-batch-fill');
  const detailEl=document.getElementById('upload-progress-detail');
  if(titleEl)titleEl.textContent=title;
  if(pctEl)pctEl.textContent=`${pct}%`;
  if(fillEl)fillEl.style.width=`${pct}%`;
  if(batchLabelEl)batchLabelEl.textContent=batchLabel;
  if(batchPctEl)batchPctEl.textContent=`${batchPct}%`;
  if(batchFillEl)batchFillEl.style.width=`${batchPct}%`;
  if(detailEl)detailEl.textContent=detail;
  applyUploadActivityState({phase,isRealUpdate,failed});
}

function hideUploadOverlay(){
  const overlay=document.getElementById('upload-progress-overlay');
  if(!overlay)return;
  overlay.style.display='none';
  overlay.classList.remove('failed');
  resetUploadTipState();
}

async function refreshUiFromBackend(){
  await syncModelFromApi();
  renderStacks();
  if(activeLens==='themes')renderThemes();
  if(activeLens==='duel')renderDuel();
  if(activeLens==='timeline')renderTimeline();
  if(activeLens==='book')renderBook();
  updateBadges();
}

async function* walkDirectory(handle,prefix=''){
  for await (const entry of handle.values()){
    const rel=prefix?`${prefix}/${entry.name}`:entry.name;
    if(entry.kind==='file'){
      const file=await entry.getFile();
      yield {file,relativePath:rel};
      continue;
    }
    if(entry.kind==='directory'){
      yield* walkDirectory(entry,rel);
    }
  }
}

async function performUpload(entries){
  const batches=chunkEntries(entries,UPLOAD_BATCH_SIZE);
  if(!batches.length){
    hideUploadOverlay();
    showToast('No files to upload');
    return;
  }

  const runUploadBatch=async(batchEntries,batchIndex,batchTotal)=>{
    let batchProgressPercent=1;
    const label=batchLabelFor(batchIndex,batchTotal);
    const updateOverlay=(title,detail,phase,failed=false,isRealUpdate=true)=>{
      showUploadOverlay(
        title,
        detail,
        overallPercentForBatch(batchIndex,batchTotal,batchProgressPercent),
        {
          failed,
          phase,
          isRealUpdate,
          batchLabel:label,
          batchPercent:batchProgressPercent,
        },
      );
    };

    updateOverlay('Uploading folder',`Sending ${batchEntries.length} files`, 'uploading');
    const result=await api.uploadFiles(batchEntries,{
      onUploadProgress:(progress)=>{
        const pct=Math.max(1,Math.min(35,Math.round((progress?.progress||0)*35)));
        if(pct<=batchProgressPercent)return;
        batchProgressPercent=pct;
        const done=Number(progress?.files_done||0);
        const total=Number(progress?.files_total||batchEntries.length);
        const detail=total>0?`Uploaded ${done}/${total} files in current batch`:'Sending files to server';
        updateOverlay('Uploading folder',detail,'uploading');
      },
    });
    if(!result.ok){
      return {ok:false,error:'Could not upload current batch'};
    }
    if(result.status===409){
      return {ok:false,error:result.data?.detail||'Another upload is already running'};
    }

    const operationId=result.data?.operation_id;
    if(!operationId){
      return {ok:false,error:'Upload started without operation id'};
    }

    const completion = await new Promise((resolve)=>{
      let done=false;
      let syncInFlight=false;
      let lastSyncAt=0;
      const trySync=()=>{
        if(syncInFlight)return;
        const now=Date.now();
        if(now-lastSyncAt<1200)return;
        lastSyncAt=now;
        syncInFlight=true;
        void syncModelFromApi()
          .then(()=>{
            if(activeLens==='stacks')renderStacks();
            if(activeLens==='duel')renderDuel();
            updateBadges();
          })
          .finally(()=>{syncInFlight=false;});
      };
      const onProgress=(payload)=>{
        const phase=payload?.phase||'working';
        const percent=Number(payload?.percent);
        if(Number.isFinite(percent)){
          const mapped=35+Math.round((Math.max(0,Math.min(100,percent))/100)*65);
          batchProgressPercent=Math.max(batchProgressPercent,Math.min(100,mapped));
        }
        updateOverlay(uploadStageTitle(phase),uploadStageDetail(payload),phase,phase==='failed',true);
        if(phase==='indexing' || phase==='provisional_clustering' || phase==='refining'){
          trySync();
        }
      };

      const stopStream=api.streamOperationEvents(operationId,{
        onEvent:onProgress,
        onDone:(payload)=>{
          onProgress(payload);
          if(done)return;
          done=true;
          clearInterval(pollTimer);
          stopStream();
          resolve(payload||{status:'failed',phase:'failed',message:'Operation stream ended'});
        },
        onError:()=>{
          // Poll fallback handles transient SSE disconnects.
        },
      });

      const pollTimer=setInterval(async()=>{
        if(done)return;
        const snapshot=await api.getOperation(operationId);
        if(!snapshot.ok || !snapshot.data?.operation)return;
        const operation=snapshot.data.operation;
        onProgress(operation);
        if(operation.status==='completed' || operation.status==='failed'){
          done=true;
          clearInterval(pollTimer);
          stopStream();
          resolve(operation);
        }
      },1000);
    });
    return {ok:completion?.status==='completed',completion,error:completion?.error||completion?.message};
  };

  for(let batchIndex=0;batchIndex<batches.length;batchIndex++){
    const batchEntries=batches[batchIndex];
    const batchResult=await runUploadBatch(batchEntries,batchIndex,batches.length);
    if(!batchResult.ok){
      showUploadOverlay(
        'Upload failed',
        batchResult.error||'Upload failed',
        overallPercentForBatch(batchIndex,batches.length,100),
        {
          failed:true,
          phase:'failed',
          isRealUpdate:true,
          batchLabel:batchLabelFor(batchIndex,batches.length),
          batchPercent:100,
        },
      );
      await new Promise((resolve)=>setTimeout(resolve,1200));
      hideUploadOverlay();
      showToast('Upload failed');
      return;
    }
    await refreshUiFromBackend();
  }

  showUploadOverlay(
    'Upload complete',
    `Processed ${entries.length} files across ${batches.length} batch${batches.length===1?'':'es'}`,
    100,
    {
      phase:'completed',
      isRealUpdate:true,
      batchLabel:batchLabelFor(batches.length-1,batches.length),
      batchPercent:100,
    },
  );
  await new Promise((resolve)=>setTimeout(resolve,900));
  hideUploadOverlay();
  showToast('Upload complete');
}

async function doUpload(){
  if(typeof window.showDirectoryPicker==='function'){
    try{
      const dir=await window.showDirectoryPicker();
      const entries=[];
      for await (const item of walkDirectory(dir,dir.name)){
        entries.push(item);
      }
      if(!entries.length){
        showToast('No files found in selected folder');
        return;
      }
      await performUpload(entries);
      return;
    }catch(error){
      if(error && error.name==='AbortError')return;
      console.error('Directory upload failed, falling back to file input.',error);
    }
  }

  const input=document.getElementById('upload-input');
  if(input){
    input.click();
  }
}

async function handleUploadChange(event){
  const files=Array.from(event.target.files||[]);
  if(!files.length)return;
  const entries=files.map((file)=>({
    file,
    relativePath:file.webkitRelativePath||file.name,
  }));
  try{
    await performUpload(entries);
  }finally{
    event.target.value='';
  }
}

async function doReset(){
  const yes=window.confirm('Reset this project? This deletes uploads and generated state.');
  if(!yes)return;
  const reset=await api.resetProject();
  if(!reset.ok){
    showToast('Reset failed');
    return;
  }

  pages={};
  slots={};
  activePage=null;
  activeThemeId=null;
  await syncModelFromApi();
  goLens('stacks');
  showToast('Project reset');
}

function showToast(msg){
  let t=document.getElementById('_toast');
  if(!t){t=document.createElement('div');t.id='_toast';t.className='toast';document.getElementById('app').appendChild(t);}
  t.textContent=msg;t.style.opacity='1';
  clearTimeout(t._timer);t._timer=setTimeout(()=>{t.style.opacity='0';},2800);
}

async function bootstrap(){
  const uploadInput=document.getElementById('upload-input');
  if(uploadInput){
    uploadInput.addEventListener('change',handleUploadChange);
  }
  document.addEventListener('click',closeAssignMenus);
  window.addEventListener('keydown',handleInspectKeys);
  await api.getReferences();
  await syncModelFromApi();
  renderStacks();
  updateBadges();
}

Object.assign(window,{
  addTheme,
  addTxt,
  chipAssignSelect,
  chipQuickAssign,
  chipQuickAssignNew,
  chipQuickDelete,
  chipQuickIgnore,
  chipToggleAssignMenu,
  chipRemove,
  closeModal,
  confirmPick,
  copyLink,
  cycleInspectDuel,
  delTheme,
  ddr,
  dlv,
  dov,
  doUpload,
  doReset,
  deleteCurrentStack,
  goLens,
  openShare,
  openStack,
  pickDuel,
  renameTheme,
  renameThemeDescription,
  rerunThemeAssignment,
  rmSlot,
  selRole,
  setActiveTheme,
  setLay,
  skipDuel,
  splitSelected,
  showAllBookPages,
  showAllBookPhotos,
  showAllPool,
  showAllStacks,
  showAllThemeStacks,
  showAllTimeline,
  showMoreBookPages,
  showMoreBookPhotos,
  showMorePool,
  showMoreStacks,
  showMoreThemeStacks,
  showMoreTimeline,
  toggleIgnoreStack,
  toggleShowIgnored,
  toggleSplitMode,
});

void bootstrap();
