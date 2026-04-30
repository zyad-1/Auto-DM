(function(){
"use strict";
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
function esc(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML;}
function timeAgo(iso){if(!iso)return"";const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return"just now";if(d<3600)return Math.floor(d/60)+"m ago";if(d<86400)return Math.floor(d/3600)+"h ago";return Math.floor(d/86400)+"d ago";}
function toast(msg,type="success"){const c=$("#toast-container"),el=document.createElement("div");el.className="toast toast-"+type;el.textContent=msg;c.appendChild(el);setTimeout(()=>{el.classList.add("hiding");setTimeout(()=>el.remove(),300)},3500);}
async function api(path,opts={}){
  const res=await fetch("/api"+path,{headers:{"Content-Type":"application/json",...(opts.headers||{})},...opts});
  if(res.status===401){window.location.href="/login";return;}
  const data=await res.json();
  if(!res.ok)throw new Error(data.detail||"Request failed");
  return data;
}

/* Health */
async function checkHealth(){try{const d=await fetch("/health").then(r=>r.json());$(".status-dot").className="status-dot "+(d.status==="ok"?"online":"offline");$(".status-text").textContent=d.status==="ok"?"System Online":"Offline";}catch{$(".status-dot").className="status-dot offline";$(".status-text").textContent="Offline";}}
checkHealth();setInterval(checkHealth,30000);

/* Sidebar Account Widget & Nav */
window.currentUser = null;
(async function loadUserContext(){
  try{
    const res = await fetch("/api/auth/me");
    if(res.ok){
      const user = await res.json();
      window.currentUser = user;
      
      // Admin nav link
      if(user.role === 'admin' && !document.querySelector('a[href="/admin"]')){
        const nav = document.getElementById('sidebar-nav-container') || document.querySelector('.sidebar-nav');
        if(nav){
          const adminLink = document.createElement('a');
          adminLink.className = 'nav-btn';
          adminLink.href = '/admin';
          adminLink.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg><span>Admin Panel</span>`;
          nav.appendChild(adminLink);
        }
      }
      
      // Render account widget
      const widget = $("#sidebar-account-widget");
      if(widget){
        const initials = user.full_name ? user.full_name.substring(0,2).toUpperCase() : user.email.substring(0,2).toUpperCase();
        let hash = 0;
        for (let i = 0; i < user.email.length; i++) hash = user.email.charCodeAt(i) + ((hash << 5) - hash);
        const color = `hsl(${Math.abs(hash) % 360}, 70%, 50%)`;
        widget.innerHTML = `
            <div class="sidebar-account-card">
                <div class="sac-avatar" style="background: ${color}">${esc(initials)}</div>
                <div class="sac-info">
                    <div class="sac-name">${esc(user.full_name || "User")}</div>
                    <div class="sac-email">${esc(user.email)}</div>
                </div>
            </div>
        `;
      }
    }
  }catch{}
})();

/* Mobile + Logout */
$("#hamburger").addEventListener("click",()=>$("#sidebar").classList.toggle("open"));
$("#btn-logout").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});window.location.href="/login";});

/* State */
let automations=[],chips=[],variations=[],ctaLinks=[],selectedPostId=null;

/* ─── List View ─── */
async function loadAutomations(){try{automations=await api("/campaigns");renderAutomations();}catch{}}
function renderKw(kw){return kw.split(",").map(k=>k.trim()).filter(Boolean).map(k=>'<span class="keyword-tag">'+esc(k)+"</span>").join("");}
function renderAutomations(){
  const grid=$("#automations-grid"),empty=$("#automations-empty");
  if(!automations.length){grid.innerHTML="";empty.style.display="block";return;}
  empty.style.display="none";
  grid.innerHTML=automations.map(c=>`
    <div class="campaign-card" data-id="${c.id}">
      <div class="campaign-card-header">
        <div class="campaign-card-info">
          <h3><span class="badge ${c.is_active?"badge-active":"badge-inactive"}">${c.is_active?"Active":"Inactive"}</span>
          <span class="badge badge-type">${c.campaign_type==="story_reply"?"Story":"Comment"}</span>
          ${c.cta_enabled?'<span class="badge badge-cta">CTA</span>':""}
          ${c.require_follow?'<span class="badge badge-follow">Follow✓</span>':""}
          Automation #${c.id}</h3>
          <span class="post-id-label">${c.campaign_type==="story_reply"?"Story: "+esc(c.story_id||"Any"):"Post: "+esc(c.post_id||"—")}</span>
        </div>
        <div class="campaign-card-actions">
          <button class="toggle ${c.is_active?"active":""}" data-action="toggle" data-id="${c.id}"></button>
          <button class="btn-icon" data-action="edit" data-id="${c.id}" title="Edit"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
          <button class="btn-icon danger" data-action="delete" data-id="${c.id}" title="Delete"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
        </div>
      </div>
      <div class="automation-kw-row">${renderKw(c.keywords)}</div>
      <div class="analytics-row">
        <div class="analytics-stat"><span class="analytics-value">${c.trigger_count||0}</span><span class="analytics-label">Triggers</span></div>
        <div class="analytics-stat"><span class="analytics-value">${c.reply_sent_count||0}</span><span class="analytics-label">Replies</span></div>
        <div class="analytics-stat"><span class="analytics-value">${c.dm_sent_count||0}</span><span class="analytics-label">DMs</span></div>
      </div>
    </div>`).join("");
  grid.querySelectorAll("[data-action]").forEach(b=>b.addEventListener("click",handleAction));
}
async function handleAction(e){
  const btn=e.currentTarget,action=btn.dataset.action,id=+btn.dataset.id;
  if(action==="toggle"){await api("/campaigns/"+id+"/toggle",{method:"PATCH"});toast("Toggled");loadAutomations();}
  else if(action==="delete"){if(!confirm("Delete this automation?"))return;await api("/campaigns/"+id,{method:"DELETE"});toast("Deleted");loadAutomations();}
  else if(action==="edit"){const c=automations.find(x=>x.id===id);if(c)openBuilder(c);}
}
loadAutomations();

/* ─── Builder ─── */
function openBuilder(c){
  $("#automation-list-view").style.display="none";
  $("#automation-builder-view").style.display="block";
  const form=$("#automation-form");form.reset();
  $("#post-preview").style.display="none";
  $("#post-selector-inline").style.display="none";
  $("#story-selector-inline").style.display="none";
  selectedPostId=null;

  if(c){
    $("#builder-title").textContent="Edit Automation #"+c.id;
    $("#automation-edit-id").value=c.id;
    setType(c.campaign_type||"comment");
    $("#input-post-id").value=c.post_id||"";
    $("#input-story-id").value=c.story_id||"";
    selectedPostId=c.post_id||null;
    chips=c.keywords?c.keywords.split(",").map(x=>x.trim()).filter(Boolean):[];
    renderChips();
    try{const p=JSON.parse(c.comment_reply_text||"[]");variations=Array.isArray(p)?p:c.comment_reply_text?[c.comment_reply_text]:[];}catch{variations=c.comment_reply_text?[c.comment_reply_text]:[];}
    const re=variations.length>0&&variations.some(v=>v.trim());
    $("#input-reply-enabled").checked=re;
    $("#reply-variations-container").style.display=re?"block":"none";
    if(!variations.length)variations.push("");
    renderVariations();
    $("#input-dm-text").value=c.dm_message_text||"";
    $("#input-opening-dm-enabled").checked=c.opening_dm_enabled||false;
    $("#opening-dm-fields").style.display=c.opening_dm_enabled?"block":"none";
    $("#input-opening-dm-text").value=c.opening_dm_text||"";
    $("#input-ask-email-enabled").checked=c.ask_email_enabled||false;
    $("#ask-email-fields").style.display=c.ask_email_enabled?"block":"none";
    $("#input-ask-email-msg").value=c.ask_email_message||"";
    $("#input-cta-enabled").checked=c.cta_enabled||false;
    $("#cta-fields").style.display=c.cta_enabled?"block":"none";
    ctaLinks=[];
    if(c.cta_enabled){try{const p=JSON.parse(c.cta_url);if(Array.isArray(p))ctaLinks=p;else if(c.cta_url)ctaLinks=[{title:c.cta_label,url:c.cta_url}];}catch{if(c.cta_url)ctaLinks=[{title:c.cta_label,url:c.cta_url}];}}
    renderCtaLinks();
    $("#input-require-follow").checked=c.require_follow||false;
    $("#follow-fields").style.display=c.require_follow?"block":"none";
    $("#input-not-following-msg").value=c.not_following_message||"";
  } else {
    $("#builder-title").textContent="New Automation";
    $("#automation-edit-id").value="";
    setType("comment");
    chips=[];renderChips();variations=[""];renderVariations();ctaLinks=[];renderCtaLinks();
    $("#input-reply-enabled").checked=false;$("#reply-variations-container").style.display="none";
    $("#input-opening-dm-enabled").checked=false;$("#opening-dm-fields").style.display="none";
    $("#input-ask-email-enabled").checked=false;$("#ask-email-fields").style.display="none";
    $("#input-cta-enabled").checked=false;$("#cta-fields").style.display="none";
    $("#input-require-follow").checked=false;$("#follow-fields").style.display="none";
  }
  updatePreview();
  window.scrollTo({top:0,behavior:"smooth"});
}
function closeBuilder(){$("#automation-builder-view").style.display="none";$("#automation-list-view").style.display="block";loadAutomations();}
$("#btn-new-automation").addEventListener("click",()=>openBuilder(null));
$("#btn-new-automation-empty").addEventListener("click",()=>openBuilder(null));
$("#btn-back-to-list").addEventListener("click",closeBuilder);
$("#btn-cancel-builder").addEventListener("click",closeBuilder);

/* Type tabs */
function setType(t){
  $("#input-campaign-type").value=t;
  $$(".type-tab").forEach(b=>b.classList.toggle("active",b.dataset.type===t));
  $("#comment-fields").style.display=t==="comment"?"block":"none";
  $("#story-fields").style.display=t==="story_reply"?"block":"none";
  $("#comment-reply-section").style.display=t==="comment"?"block":"none";
}
$$(".type-tab").forEach(t=>t.addEventListener("click",()=>setType(t.dataset.type)));

/* Toggles */
$("#input-cta-enabled").addEventListener("change",e=>{$("#cta-fields").style.display=e.target.checked?"block":"none";updatePreview();});
$("#input-require-follow").addEventListener("change",e=>{$("#follow-fields").style.display=e.target.checked?"block":"none";updatePreview();});
$("#input-reply-enabled").addEventListener("change",e=>{$("#reply-variations-container").style.display=e.target.checked?"block":"none";});
$("#input-opening-dm-enabled").addEventListener("change",e=>{$("#opening-dm-fields").style.display=e.target.checked?"block":"none";updatePreview();});
$("#input-ask-email-enabled").addEventListener("change",e=>{$("#ask-email-fields").style.display=e.target.checked?"block":"none";updatePreview();});

/* Chips */
const chipInput=$("#input-keyword-chip"),chipsC=$("#keyword-chips-container"),kwHidden=$("#input-keywords");
function renderChips(){$$(".chip",chipsC).forEach(e=>e.remove());chips.forEach((c,i)=>{const el=document.createElement("div");el.className="chip";el.innerHTML=esc(c)+'<button type="button" data-i="'+i+'"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';chipsC.insertBefore(el,chipInput);el.querySelector("button").onclick=()=>{chips.splice(i,1);renderChips();};});$("#keyword-counter").textContent=chips.length+"/20";kwHidden.value=chips.join(",");}
function addChip(v){v=v.trim().toLowerCase();if(v&&!chips.includes(v)&&chips.length<20){chips.push(v);renderChips();}}
chipInput.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===","){e.preventDefault();chipInput.value.split(",").forEach(addChip);chipInput.value="";}else if(e.key==="Backspace"&&!chipInput.value&&chips.length){chips.pop();renderChips();}});
$$(".chip-suggestion").forEach(s=>s.addEventListener("click",()=>addChip(s.dataset.kw)));

/* Variations */
function renderVariations(){const l=$("#variations-list");l.innerHTML="";variations.forEach((v,i)=>{const d=document.createElement("div");d.className="variation-item";d.innerHTML='<textarea rows="1" placeholder="Reply variation...">'+esc(v)+'</textarea><button type="button" class="btn-icon danger"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';l.appendChild(d);d.querySelector("textarea").addEventListener("input",e=>{variations[i]=e.target.value;updatePreview();});d.querySelector("button").addEventListener("click",()=>{variations.splice(i,1);renderVariations();updatePreview();});});$("#variation-counter").textContent=variations.length+"/5";$("#btn-add-variation").style.display=variations.length>=5?"none":"block";}
$("#btn-add-variation").addEventListener("click",()=>{if(variations.length<5){variations.push("");renderVariations();}});

/* CTA Links */
function renderCtaLinks(){const l=$("#cta-links-list");l.innerHTML="";ctaLinks.forEach((lk,i)=>{const d=document.createElement("div");d.className="link-item";d.innerHTML='<div class="link-item-info"><div class="link-item-title">'+esc(lk.title)+'</div><div class="link-item-url">'+esc(lk.url)+'</div></div><div class="link-item-actions"><button type="button" class="btn-icon" data-edit="'+i+'"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button><button type="button" class="btn-icon danger" data-del="'+i+'"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button></div>';l.appendChild(d);d.querySelector("[data-edit]").onclick=()=>openLinkModal(i);d.querySelector("[data-del]").onclick=()=>{ctaLinks.splice(i,1);renderCtaLinks();updatePreview();};});$("#btn-add-cta-link").style.display=ctaLinks.length>=3?"none":"block";}
$("#btn-add-cta-link").addEventListener("click",()=>openLinkModal(-1));
function openLinkModal(i){$("#link-form").reset();$("#link-edit-index").value=i;if(i>=0){$("#input-link-title").value=ctaLinks[i].title;$("#input-link-url").value=ctaLinks[i].url;$("#link-title-counter").textContent=ctaLinks[i].title.length+"/20";}else{$("#link-title-counter").textContent="0/20";}$("#link-modal-overlay").classList.add("open");}
$("#input-link-title").addEventListener("input",e=>{$("#link-title-counter").textContent=e.target.value.length+"/20";});
$("#link-form").addEventListener("submit",e=>{e.preventDefault();const i=+$("#link-edit-index").value,t=$("#input-link-title").value.trim(),u=$("#input-link-url").value.trim();if(!t||!u)return;if(i>=0)ctaLinks[i]={title:t,url:u};else ctaLinks.push({title:t,url:u});$("#link-modal-overlay").classList.remove("open");renderCtaLinks();updatePreview();});
$("#link-modal-close").addEventListener("click",()=>$("#link-modal-overlay").classList.remove("open"));

/* Post Browser */
function skeletonGrid(n){return Array(n).fill('<div class="post-grid-item skeleton-item"><div class="skeleton-thumb"></div><div class="skeleton-line"></div></div>').join("");}
$("#btn-browse-posts").addEventListener("click",async()=>{
  const sel=$("#post-selector-inline"),grid=$("#post-grid-inline");
  if(sel.style.display==="block"){sel.style.display="none";return;}
  sel.style.display="block";grid.innerHTML=skeletonGrid(6);
  try{
    const res=await fetch("/api/posts",{headers:{"Content-Type":"application/json"}});
    const data=await res.json();
    if(!res.ok){
      const err=data.detail||"";
      if(err.toLowerCase().includes("expired")||err.toLowerCase().includes("session")){
        grid.innerHTML='<div class="post-grid-error"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="var(--warning)" stroke-width="1.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><p>Instagram session expired.</p><a href="/dashboard?tab=settings" class="btn btn-sm btn-primary">Reconnect in Settings</a></div>';
      } else {grid.innerHTML='<div class="post-grid-error"><p>'+esc(err)+'</p></div>';}
      return;
    }
    if(!data.length){grid.innerHTML='<div class="post-grid-error"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="var(--text-muted)" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><p>No posts found.</p></div>';return;}
    grid.innerHTML=data.map(p=>{
      const thumb=p.thumbnail_url||p.media_url||"";
      const badge=p.media_type==="VIDEO"?"video":p.media_type==="CAROUSEL_ALBUM"?"carousel":"image";
      const sel=selectedPostId===p.id?" selected":"";
      return '<div class="post-grid-item'+sel+'" data-post-id="'+esc(p.id)+'"><div class="post-thumb-wrap"><img src="'+esc(thumb)+'" alt="" onerror="this.style.display=\'none\'"><span class="post-media-badge '+badge+'">'+esc(badge.toUpperCase())+'</span><div class="post-check-overlay"><svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div></div><div class="post-grid-meta"><span class="post-grid-date">'+timeAgo(p.timestamp)+'</span><p class="post-grid-caption">'+esc(p.caption||"No caption")+'</p></div></div>';
    }).join("");
    grid.querySelectorAll(".post-grid-item").forEach(item=>{item.addEventListener("click",()=>{
      grid.querySelectorAll(".post-grid-item").forEach(x=>x.classList.remove("selected"));
      item.classList.add("selected");
      selectedPostId=item.dataset.postId;
      $("#input-post-id").value=item.dataset.postId;
      const img=item.querySelector("img");
      if(img&&img.src){$("#preview-image").src=img.src;$("#preview-caption").textContent=item.querySelector(".post-grid-caption")?.textContent||"";$("#post-preview").style.display="flex";}
      toast("Post selected","info");
    });});
  }catch(e){grid.innerHTML='<div class="post-grid-error"><p>Failed to load posts.</p></div>';}
});
$("#btn-close-selector-inline").addEventListener("click",()=>{$("#post-selector-inline").style.display="none";});

/* Story Browser */
$("#btn-browse-stories").addEventListener("click",async()=>{
  const sel=$("#story-selector-inline"),grid=$("#story-grid-inline");
  if(sel.style.display==="block"){sel.style.display="none";return;}
  sel.style.display="block";grid.innerHTML=skeletonGrid(3);
  try{
    const res=await fetch("/api/stories",{headers:{"Content-Type":"application/json"}});
    const data=await res.json();
    if(!res.ok){const err=data.detail||"";if(err.toLowerCase().includes("expired")){grid.innerHTML='<div class="post-grid-error"><p>Instagram session expired.</p><a href="/dashboard?tab=settings" class="btn btn-sm btn-primary">Reconnect</a></div>';}else{grid.innerHTML='<div class="post-grid-error"><p>'+esc(err)+'</p></div>';}return;}
    if(!data.length){grid.innerHTML='<div class="post-grid-error"><p>No active stories.</p></div>';return;}
    grid.innerHTML=data.map(s=>'<div class="post-grid-item" data-story-id="'+esc(s.id)+'"><div class="post-thumb-wrap"><img src="'+esc(s.media_url||"")+'" alt="" onerror="this.style.display=\'none\'"><span class="post-media-badge video">STORY</span></div><div class="post-grid-meta"><span class="post-grid-date">'+timeAgo(s.timestamp)+'</span></div></div>').join("");
    grid.querySelectorAll(".post-grid-item").forEach(item=>{item.addEventListener("click",()=>{$("#input-story-id").value=item.dataset.storyId;sel.style.display="none";toast("Story selected","info");});});
  }catch{grid.innerHTML='<div class="post-grid-error"><p>Failed to load stories.</p></div>';}
});
$("#btn-close-story-selector-inline").addEventListener("click",()=>{$("#story-selector-inline").style.display="none";});

/* ─── Instagram Preview ─── */
function bubble(text,type,extra){
  if(!text&&type!=="placeholder")return"";
  let cls=type==="right"?"ig-bubble ig-bubble-right":"ig-bubble ig-bubble-left";
  if(type==="placeholder")cls+=" ig-bubble-placeholder";
  let html='<div class="'+cls+'">'+esc(text||"...")+'</div>';
  if(extra)html+=extra;
  html+='<span class="ig-bubble-ts '+(type==="right"?"ig-ts-right":"")+'">just now</span>';
  return html;
}
function updatePreview(){
  const body=$("#ig-chat-body");let html="";
  // User comment (right side)
  html+=bubble("Hey, I want the link!","right");
  // Opening DM
  if($("#input-opening-dm-enabled").checked){
    const m=$("#input-opening-dm-text").value.trim();
    html+=bubble(m||"","placeholder");
  }
  // Follow gate
  if($("#input-require-follow").checked){
    const m=$("#input-not-following-msg").value.trim();
    html+=bubble(m||"Follow us first!","left",'<div class="ig-follow-pill">Following</div>');
  }
  // Main DM
  const main=$("#input-dm-text").value.trim();
  let ctaHtml="";
  if($("#input-cta-enabled").checked&&ctaLinks.length){
    ctaHtml=ctaLinks.map(l=>'<div class="ig-cta-link"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg><span>'+esc(l.title)+'</span></div>').join("");
  }
  html+=bubble(main||"Your main message...","left",ctaHtml);
  // Ask email
  if($("#input-ask-email-enabled").checked){
    const m=$("#input-ask-email-msg").value.trim();
    html+=bubble(m||"","placeholder");
  }
  body.innerHTML=html;
  body.scrollTop=body.scrollHeight;
}
$$(".preview-trigger").forEach(el=>el.addEventListener("input",updatePreview));
$$("input[type='checkbox']").forEach(el=>el.addEventListener("change",updatePreview));
$("#input-dm-text").addEventListener("input",updatePreview);

/* ─── Form Submit ─── */
$("#automation-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const editId=$("#automation-edit-id").value;
  const type=$("#input-campaign-type").value;
  let replyText=null;
  if(type==="comment"&&$("#input-reply-enabled").checked){
    const valid=variations.map(v=>v.trim()).filter(Boolean);
    if(valid.length)replyText=JSON.stringify(valid);
  }
  const payload={
    campaign_type:type,
    post_id:type==="comment"?$("#input-post-id").value.trim():null,
    story_id:type==="story_reply"?($("#input-story-id").value.trim()||null):null,
    keywords:chips.join(","),
    comment_reply_text:replyText,
    dm_message_text:$("#input-dm-text").value.trim(),
    is_active:true,
    cta_enabled:$("#input-cta-enabled").checked,
    cta_label:$("#input-cta-enabled").checked&&ctaLinks.length?ctaLinks[0].title:null,
    cta_url:$("#input-cta-enabled").checked&&ctaLinks.length?JSON.stringify(ctaLinks):null,
    require_follow:$("#input-require-follow").checked,
    not_following_message:$("#input-not-following-msg").value.trim()||null,
    opening_dm_enabled:$("#input-opening-dm-enabled").checked,
    opening_dm_text:$("#input-opening-dm-text").value.trim()||null,
    ask_email_enabled:$("#input-ask-email-enabled").checked,
    ask_email_message:$("#input-ask-email-msg").value.trim()||null,
  };
  if(!payload.keywords||!payload.dm_message_text){toast("Fill in keywords and main DM message","error");return;}
  if(type==="comment"&&!payload.post_id){toast("Select or enter a Post ID","error");return;}
  try{
    if(editId){await api("/campaigns/"+editId,{method:"PUT",body:JSON.stringify(payload)});toast("Automation updated");}
    else{await api("/campaigns",{method:"POST",body:JSON.stringify(payload)});toast("Automation created");}
    closeBuilder();
  }catch{}
});

document.addEventListener("keydown",e=>{if(e.key==="Escape")$("#link-modal-overlay").classList.remove("open");});
updatePreview();
})();
