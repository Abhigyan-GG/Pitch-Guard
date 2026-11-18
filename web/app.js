'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timeLabel = seconds => { const s = Math.max(0, Number(seconds) || 0); return `${Math.floor(s/60)}:${Math.floor(s%60).toString().padStart(2,'0')}`; };
const state = { annotations: null, humanDirty: false, profiles: {}, advice: null, upload: null, image: null, points: [], keyframes: [], picker: null, job: null, result: null, index: 0, playing: false, imageToken: 0, pollToken: 0 };
const circleWorld = [[52.5,24.85],[61.65,34],[52.5,43.15],[43.35,34]];
const ratings = [['passing','Passing & ball retention'],['stamina','Running capacity'],['wingers','Wide attacking players'],['strikers','Striker options'],['centre_backs','Centre-back depth']];
let noticeTimer;
function notify(message, error=false) {
  clearTimeout(noticeTimer); $('notice').textContent=message; $('notice').classList.toggle('error',error); $('notice').hidden=false;
  if (!error) noticeTimer=setTimeout(()=>{$('notice').hidden=true;},8000);
}
async function api(path, options={}) {
  const response=await fetch(path,{...options,headers:{...(options.body && typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers}});
  if (!response.ok) {
    let detail; try { detail=(await response.json()).detail; } catch { detail=response.statusText; }
    if (Array.isArray(detail)) detail=detail.map(e=>`${e.loc.slice(1).join(' ')}: ${e.msg}`).join('; ');
    throw new Error(typeof detail==='string'?detail:`Request failed (${response.status})`);
  }
  return response.status===204?null:response.json();
}
function showView(view) {
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==`${view}-view`);
  document.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  location.hash=view;
  if (view==='sessions') loadSessions().catch(e=>notify(e.message,true));
  if (view!=='analysis') stopPlayback();
}
function pitchSvg(own=[], opponent=[], options={}) {
  const circle=(p,team,index)=>`<g><circle cx="${p[0]}" cy="${p[1]}" r="1.55" fill="${team==='own'?'#b0edc9':'#f1aa67'}" stroke="#173d2b" stroke-width=".3"/><text x="${p[0]}" y="${p[1]+.65}" font-size="1.85" font-family="Arial" fill="#153a2c" text-anchor="middle">${escapeHtml(options.labels?.[team]?.[index]??index+1)}</text></g>`;
  const lines=(options.lanes||[]).map(l=>`<line x1="${l.from[0]}" y1="${l.from[1]}" x2="${l.to[0]}" y2="${l.to[1]}" stroke="#9fcab0" stroke-opacity=".35" stroke-width=".3"/>`).join('');
  const ghosts=(options.roles||[]).map(r=>`<g><line x1="${r.xy[0]}" y1="${r.xy[1]}" x2="${r.target[0]}" y2="${r.target[1]}" stroke="#e4d587" stroke-width=".35" stroke-dasharray="1 1"/><circle cx="${r.target[0]}" cy="${r.target[1]}" r="1.3" fill="none" stroke="#c7d4bc" stroke-width=".3" stroke-dasharray=".8 .8"/></g>`).join('');
  return `<svg class="pitch-svg" viewBox="-3 -3 111 74" role="img" aria-label="${escapeHtml(options.label||'Pitch view: your team in mint, opposition in orange')}"><defs><pattern id="stripes" width="21" height="68" patternUnits="userSpaceOnUse"><rect width="10.5" height="68" fill="#ffffff" opacity=".025"/></pattern></defs><rect x="0" y="0" width="105" height="68" fill="url(#stripes)"/><g stroke="#a1c5aa" stroke-width=".35" fill="none" opacity=".65"><rect width="105" height="68"/><line x1="52.5" y1="0" x2="52.5" y2="68"/><circle cx="52.5" cy="34" r="9.15"/><rect x="0" y="13.84" width="16.5" height="40.32"/><rect x="88.5" y="13.84" width="16.5" height="40.32"/><rect x="0" y="24.84" width="5.5" height="18.32"/><rect x="99.5" y="24.84" width="5.5" height="18.32"/></g><circle cx="52.5" cy="34" r=".5" fill="#b2d0b3"/>${lines}${ghosts}${opponent.map((p,i)=>circle(p,'opponent',i)).join('')}${own.map((p,i)=>circle(p,'own',i)).join('')}</svg>`;
}
function renderAdvice(data) {
  const best=data.recommended; state.advice=data;
  $('plan-output').innerHTML=`<article class="panel recommend-card"><div><span class="recommend-tag">RECOMMENDED FOR YOUR MATCHUP</span><div class="formation-number">${escapeHtml(best.formation)}</div><p class="recommend-copy">${escapeHtml(best.reason)}</p><p class="score-label">${best.score} suitability points · a coaching heuristic</p><button class="primary" id="use-plan">Use as our video reference ↗</button></div><div class="pitch-section"><div class="pitch-label"><span><i class="dot-own"></i>Your ${escapeHtml(best.formation)}</span><span><i class="dot-opponent"></i>Their ${escapeHtml(data.opponent.formation)}</span></div>${pitchSvg(best.anchors,data.opponent.anchors)}<p class="small muted" style="margin:10px 0 0">Starting positions are illustrative. Both teams change shape during play.</p></div></article><div class="alternatives"><p class="section-eyebrow">OTHER SYSTEMS TO CONSIDER</p><div class="alternative-grid">${data.alternatives.map(a=>`<article class="panel alternative"><h3>${escapeHtml(a.formation)}</h3><p>${escapeHtml(a.tradeoff)}</p><small>${a.score} suitability points</small></article>`).join('')}</div></div>`;
  $('opponent-details').innerHTML=`<div class="opposition-grid"><article class="panel"><h3 class="card-title">Their ${escapeHtml(data.opponent.formation)} · strengths</h3><ul class="bullet-list">${data.opponent.strengths.map(s=>`<li>${escapeHtml(s)}</li>`).join('')}</ul></article><article class="panel"><h3 class="card-title">Where that shape can be exposed</h3><ul class="bullet-list">${data.opponent.risks.map(s=>`<li>${escapeHtml(s)}</li>`).join('')}</ul></article><article class="panel"><h3 class="card-title">Your talking points</h3><ul class="bullet-list">${data.plan.map(s=>`<li>${escapeHtml(s)}</li>`).join('')}</ul></article></div><details><summary>Why this recommendation?</summary><p class="small muted">${escapeHtml(data.basis)} Your familiar system receives a small bonus. Systems that demand more than your squad ratings receive a penalty.</p><div class="table-scroll"><table><thead><tr><th>System</th><th>Objective fit</th><th>Matchup</th><th>Familiarity</th><th>Squad penalty</th><th>Total (base 35)</th></tr></thead><tbody>${data.ranking.map(r=>`<tr><td>${escapeHtml(r.formation)}</td><td>${r.components.objective_fit}</td><td>+${r.components.matchup}</td><td>+${r.components.familiarity}</td><td>${r.components.squad_penalty}</td><td>${r.score}</td></tr>`).join('')}</tbody></table></div><p class="source-note">The scoring is PitchGuard's own heuristic. General coaching references: ${data.sources.map(s=>`<a href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer">${escapeHtml(s.title)} ↗</a>`).join('')}</p></details>`;
  $('use-plan').onclick=()=>{ $('analysis-formation').value=best.formation; showView('analysis');notify(`Using ${best.formation} as your video reference.`); };
}
async function getAdvice(event) {
  event?.preventDefault(); const button=$('recommend-button');button.disabled=true;
  try { renderAdvice(await api('/api/advice',{method:'POST',body:JSON.stringify({opponent:$('opponent').value,current:$('current').value,objective:$('objective').value,squad:Object.fromEntries(ratings.map(([k])=>[k,Number($(`rating-${k}`).value)]))})})); }
  catch(e){notify(e.message,true);} finally{button.disabled=false;}
}
function instructions() {
  const circle=$('calibration-type').value==='circle';
  const order=circle?['top of circle','right of circle','bottom of circle','left of circle']:['top-left pitch corner','top-right pitch corner','bottom-right pitch corner','bottom-left pitch corner'];
  $('point-count').textContent=`${state.points.length} of 4 landmarks`;
  $('calibration-instruction').textContent=state.picker?`Click the middle of ${state.picker==='own'?'your':'the opposition'} shirt to sample its colour.`:state.points.length<4?`Mark ${order[state.points.length]} (${state.points.length+1}/4). ${circle?'Use the four outer extremes of the centre circle.':'Use actual pitch corners, not image corners.'}`:'Four points selected. Save them at this time, or start analysis if this is the start frame.';
  $('points-json').value=state.points.length?JSON.stringify(state.points.map(p=>p.map(v=>Math.round(v)))):'';
  $('analyse-button').disabled=!state.upload||state.points.length!==4;
}
function drawCalibration() {
  const canvas=$('calibration-canvas'),ctx=canvas.getContext('2d');
  if (!state.image)return;
  canvas.width=state.image.naturalWidth;canvas.height=state.image.naturalHeight;
  ctx.drawImage(state.image,0,0);
  const scale=canvas.width/960;
  if (state.points.length>1){ctx.beginPath();ctx.moveTo(...state.points[0]);state.points.slice(1).forEach(p=>ctx.lineTo(...p));if(state.points.length===4)ctx.closePath();ctx.strokeStyle='#f4de7b';ctx.lineWidth=3*scale;ctx.stroke();}
  for(const [i,p]of state.points.entries()){ctx.beginPath();ctx.arc(...p,13*scale,0,Math.PI*2);ctx.fillStyle='#f9e58b';ctx.fill();ctx.fillStyle='#173c2b';ctx.font=`bold ${13*scale}px Arial`;ctx.textAlign='center';ctx.fillText(String(i+1),p[0],p[1]+4*scale);}
  instructions();
}
let calibrationToken=0;
async function loadCalibrationFrame() {
  if (!state.upload)return;
  const token=++calibrationToken;
  const t=Number($('calibration-time').value);$('calibration-time-label').value=timeLabel(t);
  const image=new Image(); image.src=`/api/uploads/${state.upload.id}/frame?time_s=${t}`;
  try { await image.decode();if(token!==calibrationToken)return;state.image=image;$('calibration-placeholder').hidden=true;drawCalibration(); }
  catch{if(token===calibrationToken)notify('Could not load this video frame.',true);}
}
function renderKeyframes() {
  $('keyframe-list').innerHTML=state.keyframes.map((k,i)=>`<span class="keyframe-chip">${timeLabel(k.time_s)} · ${k.world_points?'circle':'pitch'}<button data-remove-key="${i}" aria-label="Remove calibration at ${timeLabel(k.time_s)}">×</button></span>`).join('');
  document.querySelectorAll('[data-remove-key]').forEach(b=>b.onclick=()=>{state.keyframes.splice(Number(b.dataset.removeKey),1);renderKeyframes();});
}
async function useUpload(meta, demo=false) {
  stopPlayback();state.pollToken++;state.imageToken++;state.job=null;state.upload=meta;state.image=null;state.points=[];state.keyframes=[];state.picker=null;state.result=null;
  state.annotations=null;state.humanDirty=false;
  $('calibration-placeholder').hidden=false;
  $('review-workspace').hidden=true;$('job-progress').hidden=true;$('calibration-panel').hidden=false;
  $('upload-info').hidden=false;$('upload-info').textContent=`${meta.name} · ${meta.video.width} × ${meta.video.height} · ${timeLabel(meta.video.duration_s)}`;
  $('start-time').value=0;$('end-time').value=meta.video.duration_s.toFixed(2);
  $('calibration-time').max=Math.max(0,meta.video.duration_s-.1);$('calibration-time').value=0;
  $('calibration-type').value='corners';
  if(demo){state.points=[[110,70],[850,105],[925,550],[35,550]];$('detector').value='markers';$('own-colour').value='#e62d2d';$('opponent-colour').value='#1e5fe6';$('analysis-formation').value='4-3-3';$('sample-fps').value='5';}
  else if(meta.name.toLowerCase().includes('top view')){$('detector').value='overhead';$('calibration-type').value='circle';}
  else $('detector').value='players';
  detectorHint();renderKeyframes();instructions();await loadCalibrationFrame();
}
async function useExample(id){const meta=await api(`/api/examples/${encodeURIComponent(id)}`,{method:'POST'});await useUpload(meta,id==='demo');}
function detectorHint(){ $('detector-hint').textContent={players:'Uses a pretrained person detector. Clear wide views work best.',overhead:'Segments distinct kit colours. Pick clean shirt pixels; inspect detections for merged or split players.',markers:'Only for generated red and blue circles. This mode does not detect people.'}[$('detector').value]; }
function uploadVideo(file) {
  if(!file)return;const progress=$('upload-progress');progress.hidden=false;progress.value=0;
  const request=new XMLHttpRequest();request.open('POST','/api/uploads');
  request.upload.onprogress=e=>{if(e.lengthComputable)progress.value=e.loaded/e.total*100;};
  request.onload=async()=>{progress.hidden=true;try{const data=JSON.parse(request.responseText);if(request.status>=400)throw new Error(data.detail||'Upload failed');await useUpload(data);notify('Clip loaded. Choose two kit colours and mark visible landmarks.');}catch(e){notify(e.message,true);}};
  request.onerror=()=>{progress.hidden=true;notify('Upload interrupted. Check that the local server is running.',true);};
  const form=new FormData();form.append('file',file);request.send(form);
}
function saveKeyframe(){
  if(state.points.length!==4){notify('Select four landmarks first.',true);return;}
  const t=Number($('calibration-time').value);
  const key={time_s:t,corners:state.points.map(p=>[...p]),world_points:$('calibration-type').value==='circle'?circleWorld:null};
  state.keyframes=state.keyframes.filter(k=>Math.abs(k.time_s-t)>.01);state.keyframes.push(key);state.keyframes.sort((a,b)=>a.time_s-b.time_s);renderKeyframes();notify(`Saved calibration at ${timeLabel(t)}.`);
}
async function analyse(event){
  event.preventDefault();if(!state.upload)return;
  try {
    const start=Number($('start-time').value),end=Number($('end-time').value)||null;
    const keys=state.keyframes.filter(k=>k.time_s>=start&&(!end||k.time_s<end));
    const first=keys.find(k=>Math.abs(k.time_s-start)<.05);
    if(!first&&Math.abs(Number($('calibration-time').value)-start)>.05)throw new Error('Save landmarks at the analysis start time, then add later keyframes.');
    const corners=first?.corners||state.points;
    const world=first?first.world_points:($('calibration-type').value==='circle'?circleWorld:null);
    const config={formation:$('analysis-formation').value,direction:Number($('direction').value),detector:$('detector').value,
      own_colour:$('own-colour').value,opponent_colour:$('opponent-colour').value,confidence:Number($('detection-confidence').value),
      overhead_tolerance:Number($('colour-tolerance').value),sample_fps:Number($('sample-fps').value),start_s:start,end_s:end,
      corners,world_points:world,compensate_camera:$('camera-moving').checked,keyframes:keys.filter(k=>k!==first),
      possession:$('possession').value,possession_segments:JSON.parse($('possession-json').value||'[]'),
      thresholds:{deviation_m:Number($('deviation').value),persistence_s:Number($('persistence').value)}};
    $('analyse-button').disabled=true;
    const job=await api('/api/jobs',{method:'POST',body:JSON.stringify({upload_id:state.upload.id,config})});
    state.job=job;$('review-workspace').hidden=true;watchJob(job.id);
  }catch(e){notify(e.message,true);instructions();}
}
async function watchJob(id){
  const token=++state.pollToken;$('job-progress').hidden=false;$('cancel-job').hidden=false;
  try{
    while(token===state.pollToken){
      const job=await api(`/api/jobs/${id}`);state.job=job;
      $('analysis-progress').value=job.progress;$('job-message').textContent=job.message;
      $('progress-title').textContent=job.status==='queued'?'Waiting for the analysis worker':'Analysing your clip';
      if(job.status==='completed'){await loadResult(job.id);break;}
      if(['failed','cancelled','interrupted'].includes(job.status)){$('cancel-job').hidden=true;notify(job.message,job.status==='failed');instructions();break;}
      await new Promise(resolve=>setTimeout(resolve,900));
    }
  }catch(e){notify(e.message,true);instructions();}
}
async function loadResult(id){
  stopPlayback();const result=await api(`/api/jobs/${id}/result`);state.job=await api(`/api/jobs/${id}`);state.result=result;state.index=0;
  state.upload=await api(`/api/uploads/${state.job.upload_id}`);
  const config=result.manifest.configuration;
  state.points=config.corners.map(p=>[...p]);state.keyframes=[{time_s:config.start_s,corners:config.corners,world_points:config.world_points},...config.keyframes];
  for(const [id,value]of Object.entries({'analysis-formation':config.formation,'direction':config.direction,'detector':config.detector,'own-colour':config.own_colour,'opponent-colour':config.opponent_colour,'detection-confidence':config.confidence,'colour-tolerance':config.overhead_tolerance,'sample-fps':config.sample_fps,'start-time':config.start_s,'end-time':config.end_s||state.upload.video.duration_s,'possession':config.possession,'deviation':config.thresholds.deviation_m,'persistence':config.thresholds.persistence_s}))$(id).value=value;
  $('camera-moving').checked=config.compensate_camera;$('possession-json').value=config.possession_segments.length?JSON.stringify(config.possession_segments):'';
  $('calibration-type').value=config.world_points?'circle':'corners';$('calibration-time').max=state.upload.video.duration_s-.1;$('calibration-time').value=config.start_s;
  $('upload-info').hidden=false;$('upload-info').textContent=`${state.upload.name} · ${state.upload.video.width} × ${state.upload.video.height}`;
  renderKeyframes();detectorHint();loadCalibrationFrame();
  $('job-progress').hidden=true;$('calibration-panel').hidden=true;$('review-workspace').hidden=false;instructions();
  $('summary-stats').innerHTML=[['Review moments',result.summary.events],['Team-shape coverage',`${Math.round(result.summary.formation_coverage*100)}%`],['Camera verified',`${Math.round(result.summary.camera_coverage*100)}%`]].map(([label,value])=>`<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join('');
  $('analysis-warnings').innerHTML=result.warnings.map(w=>`<div class="notice" style="margin:12px 0 0">${escapeHtml(w)}</div>`).join('');
  $('review-scrubber').max=Math.max(0,result.timeline.length-1);$('review-scrubber').value=0;
  $('event-filter').value='all';renderEvents();renderChart();renderReviewFrame();await loadHumanReview();
  $('export-links').innerHTML=[['result.json','Review & notes · JSON'],['tracks.csv','Player observations · CSV'],['annotated.avi','Annotated video · AVI'],['manifest.json','Run settings · JSON']].map(([file,label])=>`<a class="secondary" href="/api/jobs/${id}/export/${file}" download>${label} ↓</a>`).join('');
}
function stopPlayback(){state.playing=false;$('play-review').textContent='Play review';}
async function renderReviewFrame(){
  if(!state.result)return;const row=state.result.timeline[state.index];if(!row)return;
  $('review-scrubber').value=state.index;$('review-clock').textContent=timeLabel(row.time_s)+` · ${row.time_s.toFixed(2)}s`;
  $('frame-status').textContent=row.camera.valid?row.shape.reason:row.camera.reason;
  const own=row.observations.filter(o=>o.team==='own'&&o.xy),opponent=row.observations.filter(o=>o.team==='opponent'&&o.xy);
  $('review-pitch').innerHTML=pitchSvg(own.map(o=>o.xy),opponent.map(o=>o.xy),{labels:{own:own.map(o=>o.track_id??'?'),opponent:opponent.map(o=>o.track_id??'?')},lanes:$('show-lanes').checked?row.shape.lanes:[],roles:row.shape.roles,label:`Measured pitch locations at ${row.time_s} seconds. ${own.length} own and ${opponent.length} opponent players.`});
  const token=++state.imageToken;const image=new Image();image.src=`/api/uploads/${state.job.upload_id}/frame?time_s=${row.time_s}`;
  try{await image.decode();if(token!==state.imageToken)return;
    const canvas=$('review-canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const scale=canvas.width/960;
    for(const o of row.observations){const colour={own:'#a9ebc4',opponent:'#ffa76b',unknown:'#c3c9c2'}[o.team];const [x1,y1,x2,y2]=o.box;ctx.strokeStyle=colour;ctx.lineWidth=2*scale;ctx.strokeRect(x1,y1,x2-x1,y2-y1);ctx.font=`${12*scale}px Arial`;const text=`${o.team} #${o.track_id??'?'}${o.xy?'':' · unprojected'}`;const tw=ctx.measureText(text).width;ctx.fillStyle='#142f24d9';ctx.fillRect(x1,Math.max(0,y1-20*scale),tw+9*scale,18*scale);ctx.fillStyle=colour;ctx.fillText(text,x1+3*scale,Math.max(14*scale,y1-6*scale));}
  }catch{if(token===state.imageToken)notify('Could not render the selected match frame.',true);}
}
async function playReview(){
  if(state.playing){stopPlayback();return;}
  if(!state.result)return;
  if(state.index>=state.result.timeline.length-1)state.index=0;
  state.playing=true;$('play-review').textContent='Pause review';
  while(state.playing&&state.index<state.result.timeline.length-1){
    const before=performance.now();const delta=state.result.timeline[state.index+1].time_s-state.result.timeline[state.index].time_s;
    state.index++;await renderReviewFrame();await new Promise(resolve=>setTimeout(resolve,Math.max(0,delta*1000-(performance.now()-before))));
  }
  stopPlayback();
}
function renderChart(){
  const rows=state.result.timeline,start=rows[0].time_s,end=rows.at(-1).time_s;const x=t=>38+(t-start)/Math.max(end-start,.1)*250;const y=v=>140-v;
  const series=key=>{let path='';let connected=false;for(const r of rows){if(r.shape.valid){path+=`${connected?'L':'M'}${x(r.time_s).toFixed(1)},${y(r.shape.metrics[key]).toFixed(1)} `;connected=true;}else connected=false;}return path;};
  const ticks=[0,30,60,90].map(v=>`<line x1="38" y1="${y(v)}" x2="288" y2="${y(v)}" stroke="#dce1d5"/><text x="28" y="${y(v)+3}" text-anchor="end" font-size="9" fill="#778374">${v}</text>`).join('');
  const events=state.result.events.map(e=>`<circle cx="${x(e.start_s)}" cy="153" r="3" fill="#c37a3c"><title>${escapeHtml(e.title)} at ${timeLabel(e.start_s)}</title></circle>`).join('');
  $('shape-chart').innerHTML=`<svg class="chart-svg" viewBox="0 0 310 188" role="img" aria-label="Team width and depth in metres across the analysed interval; circles mark coaching observations"><text x="9" y="16" font-size="9" fill="#778374">m</text>${ticks}<path d="${series('width_m')}" stroke="#347b5b" stroke-width="2" fill="none"/><path d="${series('depth_m')}" stroke="#c98344" stroke-width="2" stroke-dasharray="4 2" fill="none"/>${events}<text x="38" y="170" font-size="9" fill="#778374">${timeLabel(start)}</text><text x="288" y="170" text-anchor="end" font-size="9" fill="#778374">${timeLabel(end)}</text><text x="38" y="185" font-size="9" fill="#347b5b">— Width</text><text x="120" y="185" font-size="9" fill="#a16b38">┄ Depth</text></svg>`;
}
function renderEvents(){
  if(!state.result)return;const filter=$('event-filter').value;const events=state.result.events.filter(e=>filter==='all'||e.review.status===filter);
  if(!events.length){$('event-list').innerHTML=`<div class="panel empty">${state.result.events.length?'No observations match this filter.':'No sustained issues were flagged in the available observations. This does not establish that the team played without flaws.'}</div>`;return;}
  $('event-list').innerHTML=events.map(e=>`<article class="event-card" id="card-${e.id}"><div class="event-meta"><span class="mono">${timeLabel(e.start_s)}–${timeLabel(e.end_s)}</span><span class="pill ${escapeHtml(e.review.status)}">${escapeHtml(e.review.status)}</span><span>${e.peak_value} ${escapeHtml(e.unit)} · threshold ${e.threshold}</span>${e.track_ids.length?`<span>Track ${e.track_ids.join(', ')}</span>`:''}</div><h3>${escapeHtml(e.title)}</h3><p>${escapeHtml(e.coach)}</p><div class="coaching-cue"><strong>FOR THE PLAYER</strong><p>${escapeHtml(e.player)}</p></div><details><summary>Exercise for the next session</summary><p>${escapeHtml(e.drill)}</p><p class="muted small">${escapeHtml(e.evidence)}</p></details><div class="button-row"><button class="secondary" data-jump="${e.start_s}">View this moment ↗</button><button class="tiny" data-review-open="${e.id}">Add a coaching review</button></div><form class="review-fields" id="review-form-${e.id}" data-review-id="${e.id}" hidden><div><label for="verdict-${e.id}">Your judgement</label><select id="verdict-${e.id}"><option value="unreviewed">Not reviewed</option><option value="confirmed">Confirmed issue</option><option value="dismissed">Intended / dismiss</option><option value="uncertain">Uncertain observation</option></select></div><div><label for="reviewer-${e.id}">Reviewer name (optional)</label><input type="text" id="reviewer-${e.id}" maxlength="120" value="${escapeHtml(e.review.reviewer||'')}"></div><div class="review-notes"><label for="notes-${e.id}">Context, player cue or training note</label><textarea id="notes-${e.id}" maxlength="3000">${escapeHtml(e.review.notes)}</textarea></div><button class="primary" type="submit">Save review</button></form></article>`).join('');
  for(const e of events){$(`verdict-${e.id}`).value=e.review.status;}
  document.querySelectorAll('[data-jump]').forEach(button=>button.onclick=()=>{stopPlayback();const t=Number(button.dataset.jump);state.index=state.result.timeline.reduce((best,row,i)=>Math.abs(row.time_s-t)<Math.abs(state.result.timeline[best].time_s-t)?i:best,0);renderReviewFrame();$('review-canvas').scrollIntoView({block:'center',behavior:'auto'});});
  document.querySelectorAll('[data-review-open]').forEach(button=>button.onclick=()=>{const form=$(`review-form-${button.dataset.reviewOpen}`);form.hidden=!form.hidden;if(!form.hidden)form.querySelector('select').focus();});
  document.querySelectorAll('[data-review-id]').forEach(form=>form.onsubmit=async event=>{event.preventDefault();const id=form.dataset.reviewId;try{const saved=await api(`/api/jobs/${state.job.id}/events/${id}/review`,{method:'PUT',body:JSON.stringify({status:$(`verdict-${id}`).value,reviewer:$(`reviewer-${id}`).value,notes:$(`notes-${id}`).value})});state.result.events[state.result.events.findIndex(e=>e.id===id)]=saved;renderEvents();notify('Coaching review saved. Your notes are included in the JSON export.');}catch(e){notify(e.message,true);}});
}
const manualKindLabels={role_drift:'Departure from reference shape',unit_gap:'Gap between units',defensive_gap:'Open defensive channel',stretched_shape:'Stretched team',support_isolation:'Distant support',shape_disruption:'Abrupt shape change'};
function markHumanDirty(resetAttestation=true){
  state.humanDirty=true;
  if(resetAttestation)$('labels-attested').checked=false;
  $('human-review-status').textContent='Unsaved changes ? save your review to keep them.';
  $('human-review-status').classList.add('label-unsaved');
}
function labelBounds(start,end){
  if(!state.result||!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw new Error('End time must follow start time.');
  const summary=state.result.summary;
  if(start<summary.start_s||end>summary.end_s)throw new Error('Use times inside the analysed interval.');
}
function renderHumanItems(){
  if(!state.annotations)return;
  $('reviewed-periods').innerHTML=state.annotations.reviewed_periods.map((p,i)=>`<div class="label-item"><span>Reviewed ${p.start_s.toFixed(2)}?${p.end_s.toFixed(2)}s</span><button type="button" class="tiny" data-remove-period="${i}" aria-label="Remove reviewed period ${i+1}">Remove</button></div>`).join('');
  $('manual-events').innerHTML=state.annotations.manual_events.map(e=>`<article class="label-item"><div><strong>${escapeHtml(manualKindLabels[e.kind])}</strong><div class="small muted">${e.start_s.toFixed(2)}?${e.end_s.toFixed(2)}s ? ${escapeHtml(e.judgement)}</div><p class="small">${escapeHtml(e.notes)}</p></div><div class="button-row"><button type="button" class="tiny" data-label-jump="${e.start_s}">View moment</button><button type="button" class="tiny danger" data-remove-manual="${e.id}">Remove</button></div></article>`).join('');
  document.querySelectorAll('[data-remove-period]').forEach(b=>b.onclick=()=>{state.annotations.reviewed_periods.splice(Number(b.dataset.removePeriod),1);markHumanDirty();renderHumanItems();});
  document.querySelectorAll('[data-remove-manual]').forEach(b=>b.onclick=()=>{state.annotations.manual_events=state.annotations.manual_events.filter(e=>e.id!==b.dataset.removeManual);markHumanDirty();renderHumanItems();});
  document.querySelectorAll('[data-label-jump]').forEach(b=>b.onclick=()=>{stopPlayback();const t=Number(b.dataset.labelJump);state.index=state.result.timeline.reduce((best,row,i)=>Math.abs(row.time_s-t)<Math.abs(state.result.timeline[best].time_s-t)?i:best,0);renderReviewFrame();$('review-canvas').scrollIntoView({block:'center'});});
}
async function loadHumanReview(){
  const labels=await api(`/api/jobs/${state.job.id}/annotations`);state.annotations=labels;state.humanDirty=false;
  $('label-reviewer').value=labels.reviewer;$('label-role').value=labels.reviewer_role;$('label-clip-id').value=labels.clip_id;$('labels-attested').checked=labels.attested;
  $('period-start').value=state.result.summary.start_s;$('period-end').value=state.result.summary.end_s;
  $('manual-start').value=state.result.summary.start_s;$('manual-end').value=Math.min(state.result.summary.start_s+.5,state.result.summary.end_s);
  $('human-review-status').classList.remove('label-unsaved');
  $('human-review-status').textContent=labels.revision?`Saved revision ${labels.revision} ? ${labels.attested?'review confirmed':'draft review'}`:'No human labels saved yet.';
  $('export-human-labels').href=`/api/jobs/${state.job.id}/export/human-labels.json`;$('export-human-labels').hidden=!labels.revision;
  renderHumanItems();
}
function addManualEvent(event){
  event.preventDefault();if(!state.annotations)return;
  try{const start=Number($('manual-start').value),end=Number($('manual-end').value);labelBounds(start,end);
    state.annotations.manual_events.push({id:crypto.randomUUID(),kind:$('manual-kind').value,judgement:$('manual-judgement').value,start_s:start,end_s:end,notes:$('manual-notes').value});
    $('manual-notes').value='';markHumanDirty();renderHumanItems();
  }catch(e){notify(e.message,true);}
}
function addReviewedPeriod(event){
  event.preventDefault();if(!state.annotations)return;
  try{const start=Number($('period-start').value),end=Number($('period-end').value);labelBounds(start,end);
    if(state.annotations.reviewed_periods.some(p=>start<p.end_s&&end>p.start_s))throw new Error('Reviewed periods must not overlap. Remove or adjust the existing period first.');
    state.annotations.reviewed_periods.push({start_s:start,end_s:end});state.annotations.reviewed_periods.sort((a,b)=>a.start_s-b.start_s);markHumanDirty();renderHumanItems();
  }catch(e){notify(e.message,true);}
}
async function saveHumanReview(){
  if(!state.annotations)return;const button=$('save-human-review');button.disabled=true;
  try{const body={expected_revision:state.annotations.revision,clip_id:$('label-clip-id').value,reviewer:$('label-reviewer').value,reviewer_role:$('label-role').value,
      reviewed_periods:state.annotations.reviewed_periods,manual_events:state.annotations.manual_events,attested:$('labels-attested').checked};
    const saved=await api(`/api/jobs/${state.job.id}/annotations`,{method:'PUT',body:JSON.stringify(body)});state.annotations=saved;state.humanDirty=false;
    $('human-review-status').classList.remove('label-unsaved');$('human-review-status').textContent=`Saved revision ${saved.revision} ? ${saved.attested?'review confirmed':'draft review'}`;
    $('export-human-labels').href=`/api/jobs/${state.job.id}/export/human-labels.json`;$('export-human-labels').hidden=false;
    notify('Your own observations and reviewed periods are saved separately from automatic findings.');
  }catch(e){notify(e.message,true);}finally{button.disabled=false;}
}
async function loadSessions(){
  const jobs=await api('/api/jobs');
  $('session-list').innerHTML=jobs.length?jobs.map(job=>`<article class="panel session-card"><div class="session-name"><h3>${escapeHtml(job.name)}</h3><p>${escapeHtml(job.status)} · ${new Date(job.created_utc).toLocaleString()}${job.summary?` · ${job.summary.events} review moments`:''}</p></div><div class="button-row">${job.status==='completed'?`<button class="secondary" data-open-job="${job.id}">Open review ↗</button>`:['running','queued'].includes(job.status)?`<button class="secondary" data-watch-job="${job.id}">View progress</button>`:''}${!['running','queued'].includes(job.status)?`<button class="tiny danger" data-delete-job="${job.id}">Delete session</button>`:''}</div></article>`).join(''):'<div class="panel empty">Your first review belongs here. Start with the demo or upload a match clip.</div>';
  document.querySelectorAll('[data-open-job]').forEach(button=>button.onclick=async()=>{showView('analysis');try{await loadResult(button.dataset.openJob);}catch(e){notify(e.message,true);}});
  document.querySelectorAll('[data-watch-job]').forEach(button=>button.onclick=()=>{showView('analysis');watchJob(button.dataset.watchJob);});
  document.querySelectorAll('[data-delete-job]').forEach(button=>button.onclick=async()=>{if(!confirm('Delete this local analysis and its review notes?'))return;try{await api(`/api/jobs/${button.dataset.deleteJob}`,{method:'DELETE'});await loadSessions();}catch(e){notify(e.message,true);}});
  const uploads=await api('/api/uploads');
  if(uploads.length){$('session-list').insertAdjacentHTML('beforeend','<div class="section-heading"><h2>Local video records</h2></div>'+uploads.map(u=>`<article class="panel session-card"><div class="session-name"><h3>${escapeHtml(u.name)}</h3><p>${u.example?'Workspace reference · original file is preserved':'Uploaded copy · stored on this computer'}</p></div><button class="tiny danger" data-delete-upload="${u.id}">Delete video record</button></article>`).join(''));document.querySelectorAll('[data-delete-upload]').forEach(button=>button.onclick=async()=>{if(!confirm('Delete this local upload? Associated sessions must be deleted first.'))return;try{await api(`/api/uploads/${button.dataset.deleteUpload}`,{method:'DELETE'});await loadSessions();}catch(e){notify(e.message,true);}});}
}
async function init(){
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>showView(button.dataset.view));
  for(const id of ['help-button','help-top'])$(id).onclick=()=>$('help-dialog').showModal();
  document.querySelectorAll('.close-dialog').forEach(button=>button.onclick=()=>$('help-dialog').close());
  $('advice-form').onsubmit=getAdvice;
  $('manual-event-form').onsubmit=addManualEvent;$('reviewed-period-form').onsubmit=addReviewedPeriod;
  $('save-human-review').onclick=saveHumanReview;
  for(const id of ['label-reviewer','label-role','label-clip-id'])$(id).oninput=()=>markHumanDirty();
  $('labels-attested').onchange=()=>markHumanDirty(false);
  $('manual-use-current').onclick=()=>{if(!state.result)return;const t=state.result.timeline[state.index].time_s;$('manual-start').value=t;$('manual-end').value=Math.min(t+.5,state.result.summary.end_s);};
  $('squad-ratings').innerHTML=ratings.map(([key,label])=>`<div class="rating-row"><div class="rating-label"><label for="rating-${key}">${label}</label><output id="rating-value-${key}">3 / 5</output></div><input type="range" id="rating-${key}" min="1" max="5" value="3"></div>`).join('');
  ratings.forEach(([key])=>$(`rating-${key}`).oninput=()=>$(`rating-value-${key}`).value=`${$(`rating-${key}`).value} / 5`);
  $('demo-button').onclick=()=>useExample('demo').catch(e=>notify(e.message,true));
  $('load-example').onclick=()=>{if(!$('example-select').value){notify('Choose a workspace clip first.',true);return;}useExample($('example-select').value).catch(e=>notify(e.message,true));};
  $('video-file').onchange=event=>uploadVideo(event.target.files[0]);
  $('dropzone').ondragover=event=>{event.preventDefault();};$('dropzone').ondrop=event=>{event.preventDefault();uploadVideo(event.dataTransfer.files[0]);};
  $('detector').onchange=detectorHint;
  $('calibration-canvas').onclick=event=>{if(!state.image)return;const canvas=$('calibration-canvas'),rect=canvas.getBoundingClientRect();const p=[(event.clientX-rect.left)/rect.width*canvas.width,(event.clientY-rect.top)/rect.height*canvas.height];if(state.picker){const scratch=document.createElement('canvas');scratch.width=state.image.naturalWidth;scratch.height=state.image.naturalHeight;const ctx=scratch.getContext('2d');ctx.drawImage(state.image,0,0);const pixel=ctx.getImageData(Math.min(scratch.width-1,Math.floor(p[0])),Math.min(scratch.height-1,Math.floor(p[1])),1,1).data;$(`${state.picker==='own'?'own':'opponent'}-colour`).value='#'+[...pixel].slice(0,3).map(v=>v.toString(16).padStart(2,'0')).join('');state.picker=null;instructions();return;}if(state.points.length===4){notify('Clear or undo a point to edit this calibration.');return;}state.points.push(p);drawCalibration();};
  $('pick-own').onclick=()=>{state.picker='own';instructions();};$('pick-opponent').onclick=()=>{state.picker='opponent';instructions();};
  $('reset-points').onclick=()=>{state.points=[];state.picker=null;drawCalibration();instructions();};$('undo-point').onclick=()=>{state.points.pop();drawCalibration();instructions();};
  $('calibration-type').onchange=()=>{state.points=[];drawCalibration();instructions();};
  $('calibration-time').onchange=()=>{state.points=[];loadCalibrationFrame();};$('calibration-time').oninput=()=>$('calibration-time-label').value=timeLabel($('calibration-time').value);
  $('save-keyframe').onclick=saveKeyframe;
  $('apply-points').onclick=()=>{try{const points=JSON.parse($('points-json').value);if(!Array.isArray(points)||points.length!==4||points.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v))))throw new Error('Use four numeric [x, y] pairs.');state.points=points;drawCalibration();instructions();}catch(e){notify(e.message,true);}};
  $('analysis-form').onsubmit=analyse;
  $('cancel-job').onclick=async()=>{try{if(state.job)await api(`/api/jobs/${state.job.id}/cancel`,{method:'POST'});}catch(e){notify(e.message,true);}};
  $('new-analysis').onclick=()=>{$('calibration-panel').hidden=false;instructions();};
  $('event-filter').onchange=renderEvents;$('show-lanes').onchange=renderReviewFrame;
  $('review-scrubber').oninput=()=>{stopPlayback();state.index=Number($('review-scrubber').value);renderReviewFrame();};
  $('previous-frame').onclick=()=>{stopPlayback();state.index=Math.max(0,state.index-1);renderReviewFrame();};
  $('next-frame').onclick=()=>{stopPlayback();state.index=Math.min((state.result?.timeline.length||1)-1,state.index+1);renderReviewFrame();};
  $('play-review').onclick=playReview;$('refresh-sessions').onclick=()=>loadSessions().catch(e=>notify(e.message,true));
  try{
    const [health,profiles,examples]=await Promise.all([api('/api/health'),api('/api/formations'),api('/api/examples')]);state.profiles=profiles;
    $('service-state').textContent=health.model_ready?'Local engine ready':'Demo & overhead ready';
    const options=Object.keys(profiles).map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
    for(const id of ['opponent','current','analysis-formation'])$(id).innerHTML=options;
    $('opponent').value='4-4-2';$('current').value='4-3-3';$('analysis-formation').value='4-3-3';
    $('example-select').innerHTML='<option value="">Choose a clip…</option>'+examples.map(e=>`<option value="${e.id}">${escapeHtml(e.name)}</option>`).join('');
    await getAdvice();const view=location.hash.slice(1);showView(['planner','analysis','sessions'].includes(view)?view:'planner');
  }catch(e){$('service-state').textContent='Engine unavailable';notify(e.message,true);}
}
init();
