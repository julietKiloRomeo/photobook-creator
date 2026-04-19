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
const chapterByTheme={};
const chapterEnsurePromises={};
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
function getPick(sid){const s=getS(sid);if(!s)return null;const pid=s.pick||s.photos[0];return getP(pid)}
function resolved(s){return s.pick!==null}
function resolvedCount(){return STACKS.filter(resolved).length}
function themeOf(sid){return themes.find(t=>t.stacks.includes(sid))}

function escAttr(value){
  return String(value??'')
    .replaceAll('&','&amp;')
    .replaceAll('"','&quot;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;');
}

function photoStyle(photo,fallback='var(--color-background-secondary)'){
  const base=`background:${photo?.color||fallback};`;
  if(!photo?.url)return base;
  const safeUrl=encodeURI(String(photo.url));
  return `${base}background-image:url(${safeUrl});background-size:cover;background-position:center;background-repeat:no-repeat;`;
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
      pick:item.pick_reference_id?String(item.pick_reference_id):null,
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
    color:theme.color||THEME_COLORS[0],
    stacks:(theme.stack_ids||[]).map((sid)=>String(sid)),
  }));
  const assigned = new Set(themes.flatMap((theme)=>theme.stacks));
  unassigned=STACKS.map((stack)=>String(stack.id)).filter((sid)=>!assigned.has(sid));
  if(!themes.length){
    themes=[{id:'local-default',title:'Highlights',stacks:[],color:THEME_COLORS[0]}];
    unassigned=STACKS.map((stack)=>String(stack.id));
  }
}

async function syncModelFromApi(){
  const [stackRes,themeRes]=await Promise.all([api.getStacks(),api.getThemes()]);
  if(stackRes.ok && Array.isArray(stackRes.data?.items)){
    applyStacksFromApi(stackRes.data.items);
  }else{
    PHOTOS=[];
    STACKS=[];
  }

  if(themeRes.ok && Array.isArray(themeRes.data?.items)){
    applyThemesFromApi(themeRes.data.items);
  }else{
    themes=[{id:'local-default',title:'Highlights',stacks:[],color:THEME_COLORS[0]}];
    unassigned=STACKS.map((stack)=>String(stack.id));
  }
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
  const rc=resolvedCount(),tot=STACKS.length;
  document.getElementById('lb-stacks').textContent=`${rc}/${tot}`;
  const left=STACKS.filter(s=>!resolved(s)&&s.photos.length>1).length;
  document.getElementById('lb-duel').textContent=left>0?`${left} left`:'done';
  document.getElementById('lb-themes').textContent=themes.length;
  let pgTotal=0;Object.values(pages).forEach(a=>pgTotal+=a.length);
  document.getElementById('lb-book').textContent=pgTotal+(pgTotal===1?' page':' pages');
  const pct=Math.round(rc/tot*100);
  document.getElementById('stacks-fill').style.width=pct+'%';
  document.getElementById('stacks-label').textContent=`${rc} of ${tot} resolved`;
}

function goLens(l){
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

function renderStacks(){
  const g=document.getElementById('stacks-grid');g.innerHTML='';
  if(!STACKS.length){
    g.innerHTML='<div class=\"section-meta\">No stacks yet. Upload files to begin.</div>';
    return;
  }
  STACKS.forEach(s=>{
    const res=resolved(s);
    const pick=getPick(s.id);
    const theme=themeOf(s.id);
    const card=document.createElement('div');
    card.className='stack-card '+(res?'resolved':'unresolved');
    card.onclick=()=>openStack(s.id);
    let fanHTML='';
    const count=s.photos.length;
    if(res&&s.pick){
      const p=getP(s.pick);
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
    card.innerHTML=`<div class="stack-photo-area">${fanHTML}
      <div class="stack-badge ${res?'badge-resolved':'badge-pending'}">${res?'✓ resolved':'pick needed'}</div>
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
}

function openStack(sid){
  const s=getS(sid);if(!s)return;
  openStackId=sid;tempPick=s.pick;
  document.getElementById('sm-title').textContent=s.label;
  const g=document.getElementById('sm-grid');g.innerHTML='';
  s.photos.forEach(pid=>{
    const p=getP(pid);if(!p)return;
    const d=document.createElement('div');
    d.className='photo-opt'+(s.pick===pid?' sel':'');
    d.dataset.pid=pid;d.onclick=()=>selPick(pid);
    d.innerHTML=`<div class="photo-opt-img" style="${photoStyle(p)}display:flex;align-items:flex-end;padding:5px"><span style="font-size:9px;color:rgba(0,0,0,.38)">${escAttr(p.label)}</span></div>
      <div class="photo-opt-lbl">${escAttr(p.label)}</div>
      <div class="checkmark"><div class="ck"></div></div>`;
    g.appendChild(d);
  });
  updateSMFoot();
  document.getElementById('stack-modal').style.display='flex';
}
function selPick(pid){
  tempPick=pid;
  document.querySelectorAll('.photo-opt').forEach(e=>e.classList.toggle('sel',e.dataset.pid===pid));
  updateSMFoot();
}
function updateSMFoot(){
  const p=tempPick?getP(tempPick):null;
  document.getElementById('sm-sel-label').textContent=p?`Selected: ${p.label}`:'None selected';
  document.getElementById('sm-confirm').disabled=!tempPick;
}
function confirmPick(){
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
function closeModal(){document.getElementById('stack-modal').style.display='none';openStackId=null;tempPick=null;}

function buildDuelStacks(){return STACKS.filter(s=>!resolved(s)&&s.photos.length>1);}

function renderDuel(){
  duelStacks=buildDuelStacks();
  const wrap=document.getElementById('duel-wrap');wrap.innerHTML='';
  if(duelStacks.length===0){
    wrap.innerHTML=`<div class="duel-done"><div class="done-icon">✓</div><div class="done-title">All stacks resolved</div><div class="done-sub">Head to Themes or Book to continue</div></div>`;
    return;
  }
  if(duelIdx>=duelStacks.length)duelIdx=0;
  const s=duelStacks[duelIdx];
  const pips=duelStacks.map((ds,i)=>
    `<div class="duel-pip ${i<duelIdx?'done':i===duelIdx?'current':''}"></div>`).join('');
  const votes=duelState[s.id]||{};

  let pairA=s.photos[0],pairB=s.photos[1];
  const pA=getP(pairA),pB=getP(pairB);
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
      <div class="duel-img" style="${photoStyle(p,'#ccc')}">
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
  <div class="duel-hint">Tap the photo you'd pick for this stack</div>
  <div class="duel-arena">
    ${cardHTML(pairA,pA,pickedA,pickedB,votesA,collabAvatars)}
    <div class="duel-vs"><div class="vs-circle">vs</div></div>
    ${cardHTML(pairB,pB,pickedB,pickedA,votesB,collabAvatars)}
  </div>
  ${s.photos.length>2?`<div style="font-size:11px;color:var(--color-text-tertiary)">Showing 2 of ${s.photos.length} shots — <span style="cursor:pointer;color:#7F77DD" onclick="openStack('${s.id}')">see all in grid</span></div>`:''}`;
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
  themes.forEach(t=>{
    const block=document.createElement('div');block.className='theme-block';block.dataset.tid=t.id;
    block.innerHTML=`<div class="theme-head">
      <div class="theme-color-dot" style="background:${t.color}"></div>
      <input class="theme-title-inp" value="${t.title}" onchange="renameTheme('${t.id}',this.value)"/>
      <span class="theme-count">${t.stacks.length} stack${t.stacks.length!==1?'s':''}</span>
      <button class="ibc" onclick="goLens('book');setActiveTheme('${t.id}')">→ book</button>
      <button class="ibc del" onclick="delTheme('${t.id}')">✕</button>
    </div>
    <div class="theme-chips" id="tc-${t.id}" ondragover="dov(event,'${t.id}')" ondrop="ddr(event,'${t.id}')" ondragleave="dlv(event)"></div>
    <div class="drop-target" id="dt-${t.id}" ondragover="dov(event,'${t.id}')" ondrop="ddr(event,'${t.id}')" ondragleave="dlv(event)">Drop stacks here</div>`;
    canvas.appendChild(block);
    const chipsEl=block.querySelector(`#tc-${t.id}`);
    t.stacks.forEach(sid=>chipsEl.appendChild(makeChip(sid,t.id)));
  });
  const addBtn=document.createElement('div');addBtn.className='add-theme-row';
  addBtn.innerHTML=`<button class="add-theme-btn" onclick="addTheme()">+ New theme</button>`;
  canvas.appendChild(addBtn);
  unassigned.forEach(sid=>pool.appendChild(makeChip(sid,'pool')));
  if(!unassigned.length)pool.innerHTML=`<span style="font-size:12px;color:var(--color-text-tertiary)">All assigned</span>`;
}

function makeChip(sid,from){
  const s=getS(sid);if(!s)return document.createElement('span');
  const theme=themeOf(sid);
  const chip=document.createElement('div');chip.className='chip';chip.draggable=true;chip.dataset.sid=sid;chip.dataset.from=from;
  chip.innerHTML=`<div class="chip-dot" style="background:${theme?theme.color:'var(--color-border-secondary)'}"></div>
    <span class="chip-lbl">${s.label}</span>
    <span class="chip-x" onclick="chipRemove('${sid}','${from}')">✕</span>`;
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
function chipRemove(sid,from){
  if(from==='pool')return;
  const t=themes.find(x=>x.id===from);if(t)t.stacks=t.stacks.filter(x=>x!==sid);
  void api.assignTheme({stack_id:String(sid),theme_id:null});
  unassigned.push(sid);renderThemes();
}
function renameTheme(tid,val){
  const t=themes.find(x=>x.id===tid);if(t)t.title=val;
  void api.patchTheme(Number(tid),{title:val});
  renderBookNav();
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

function renderTimeline(){
  const wrap=document.getElementById('timeline-wrap');wrap.innerHTML='';
  const byMonth={};
  STACKS.forEach(s=>{
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
  themes.forEach(t=>{
    const pg=(pages[t.id]||[]).length;
    const item=document.createElement('div');
    item.className='book-nav-item'+(activeThemeId===t.id?' active':'');
    item.innerHTML=`<div style="display:flex;align-items:center;gap:6px"><div style="width:8px;height:8px;border-radius:50%;background:${t.color};flex-shrink:0"></div>${t.title}</div><div class="book-nav-sub">${pg} page${pg!==1?'s':''}</div>`;
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
  (pages[tid]||[]).forEach(pg=>{
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
  t.stacks.forEach(sid=>{
    const pick=getPick(sid);const s=getS(sid);if(!pick)return;
    const el=document.createElement('div');el.className='pp-item';el.draggable=true;
    el.innerHTML=`<div class="pp-img" style="${photoStyle(pick)}display:flex;align-items:flex-end;padding:3px"><span style="font-size:8px;color:rgba(0,0,0,.35)">${escAttr(pick.label)}</span></div>
      <div class="pp-name">${escAttr(s?s.label:'')}</div>`;
    el.ondragstart=e=>e.dataTransfer.setData('pid',pick.id);
    list.appendChild(el);
  });
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

function summarizeUpload(result){
  const stored=result?.stored??0;
  const images=result?.supported_images??0;
  const ignored=result?.ignored??0;
  return `Uploaded ${stored} file${stored===1?'':'s'} (${images} image${images===1?'':'s'}, ${ignored} ignored)`;
}

async function applyUploadResult(result){
  if(!result.ok){
    showToast('Upload failed');
    return;
  }

  await syncModelFromApi();
  renderStacks();
  if(activeLens==='themes')renderThemes();
  if(activeLens==='timeline')renderTimeline();
  if(activeLens==='book')renderBook();
  updateBadges();
  showToast(summarizeUpload(result.data?.upload||{}));
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
      const result=await api.uploadFiles(entries);
      await applyUploadResult(result);
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
  const result=await api.uploadFiles(entries);
  await applyUploadResult(result);
  event.target.value='';
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
  await api.getReferences();
  await syncModelFromApi();
  renderStacks();
  updateBadges();
}

Object.assign(window,{
  addTheme,
  addTxt,
  chipRemove,
  closeModal,
  confirmPick,
  copyLink,
  delTheme,
  ddr,
  dlv,
  dov,
  doUpload,
  doReset,
  goLens,
  openShare,
  openStack,
  pickDuel,
  renameTheme,
  rmSlot,
  selRole,
  setActiveTheme,
  setLay,
  skipDuel,
});

void bootstrap();
