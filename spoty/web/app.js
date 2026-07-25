// Spoty - webview frontend mantığı. Python köprüsü: window.pywebview.api

let API = null;
const $ = (id) => document.getElementById(id);
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }
function esc(s) { return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
// Durum çubuğu (toast): kısa bildirim + isteğe bağlı tek aksiyon düğmesi.
//   setStatus('Video indirildi')
//   setStatus('İndirme hatası: ...', { kind:'error' })
//   setStatus('Video indirildi', { action:'Klasörü aç', onAction:()=>API.open_video_folder() })
let _statusTimer = null;
function setStatus(m, opt) {
  const e = $('status'); if (!e) return;
  if (_statusTimer) { clearTimeout(_statusTimer); _statusTimer = null; }
  if (!m) { e.classList.remove('show'); return; }

  opt = opt || {};
  e.className = 'statusbar' + (opt.kind ? ' ' + opt.kind : '');
  e.innerHTML = '';
  e.appendChild(el('div', 'st-msg', esc(m)));

  if (opt.action && opt.onAction) {
    const b = el('button', 'st-act', esc(opt.action));
    b.onclick = () => { setStatus(''); opt.onAction(); };
    e.appendChild(b);
  }
  const x = el('button', 'st-close', ICONS.close);
  x.onclick = () => setStatus('');
  e.appendChild(x);

  e.classList.add('show');
  // hata ve aksiyonlu mesajlar daha uzun kalsın
  const ms = opt.kind === 'error' ? 9000 : (opt.action ? 8000 : 4000);
  _statusTimer = setTimeout(() => e.classList.remove('show'), ms);
}

const state = { view: 'library', pid: null, plName: '', activeIds: [], npVisible: true, lastSeek: 0, shuffle: false, repeat: false, isPlaying: false, playingScope: null };
// playingScope: 'library' | <playlist pid> | null  (o an çalan kaynağı belirtir)
function curScope() { return state.view === 'library' ? 'library' : (state.view === 'playlist' ? state.pid : null); }

function setCover(imgEl, uri) {
  if (uri) { imgEl.src = uri; imgEl.style.visibility = 'visible'; }
  else { imgEl.removeAttribute('src'); imgEl.style.visibility = 'hidden'; }
}

// ---------- sidebar ----------
function renderPlaylists(pls) {
  const box = $('plList'); box.innerHTML = '';
  if (!pls.length) { box.appendChild(el('div', null, '<span style="color:var(--faint);font-size:12px;padding:6px">Henüz liste yok</span>')); return; }
  for (const pl of pls) {
    const row = el('div', 'pl-row');
    const tile = el('div', 'tile', `${esc(pl.letter)}<span class="plov">${ICONS.playSmall}</span>`);
    tile.style.background = pl.color; tile.title = 'Listeyi çal';
    tile.onclick = (e) => { e.stopPropagation(); playPlaylist(pl.id, pl.name); };
    const info = el('div', null, `<div class="pl-name ellipsis">${esc(pl.name)}</div><div class="pl-count">${pl.count} parça</div>`);
    info.style.minWidth = '0';
    row.append(tile, info);
    row.onclick = () => showPlaylist(pl.id, pl.name);
    box.appendChild(row);
  }
}
async function refreshSidebar() { renderPlaylists(await API.get_playlists()); }

// bir listeyi baştan, sırayla çal (queue = listenin tüm şarkıları)
async function playPlaylist(pid, name) {
  const tracks = await API.get_playlist_tracks(pid);
  if (!tracks.length) return;
  state.playingScope = pid;
  const now = await API.play(tracks[0].id, tracks.map(t => t.id), `${name} listesinden çalınıyor`);
  updateNowPlaying(now);
  if (state.view === 'playlist' && state.pid === pid) refreshView();
}

// kütüphaneyi baştan, sırayla çal
async function playLibrary() {
  const tracks = await API.get_library();
  if (!tracks.length) return;
  state.playingScope = 'library';
  const now = await API.play(tracks[0].id, tracks.map(t => t.id), 'Kütüphaneden çalınıyor');
  updateNowPlaying(now);
  if (state.view === 'library') refreshView();
}

// ---------- başlık ----------
function setHeader(eyebrow, title, meta, showDel, showCol) {
  $('eyebrow').textContent = eyebrow;
  $('title').textContent = title;
  $('meta').textContent = meta || '';
  $('delPl').style.display = showDel ? 'flex' : 'none';
  $('colhead').style.display = showCol ? 'flex' : 'none';
  $('navLib').classList.toggle('active', state.view === 'library');
}
function metaText(tracks) {
  if (!tracks.length) return 'Boş';
  const total = tracks.reduce((a, t) => a + (t.duration || 0), 0);
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60);
  const dur = h ? `${h} sa ${m} dk` : (m ? `${m} dk` : `${total} sn`);
  return `${tracks.length} şarkı · ${dur}`;
}

// ---------- şarkı listesi ----------
function renderTracks(tracks, mode) {
  state.activeIds = tracks.map(t => t.id);
  const rows = $('rows'); rows.innerHTML = '';
  if (!tracks.length) { renderEmpty(mode); return; }
  let playingRow = null;
  tracks.forEach((t, i) => {
    const row = el('div', 'row' + (t.playing ? ' playing' : ''));
    row.dataset.tid = t.id;
    const idHtml = t.playing ? ICONS.note : String(i + 1);
    const hoverIcon = (t.playing && state.isPlaying) ? ICONS.pauseSmall : ICONS.playSmall;
    const idx = el('div', 'idx', `<span class="id">${idHtml}</span><span class="ih">${hoverIcon}</span>`);
    const thumb = el('div', 'thumb');
    if (t.cover) { thumb.style.backgroundImage = `url(${t.cover})`; thumb.style.backgroundSize = 'cover'; }
    else { thumb.innerHTML = ICONS.note; thumb.style.color = '#5a5a5a'; }
    const info = el('div', 'info', `<div class="r-title ellipsis">${esc(t.title)}</div><div class="r-artist ellipsis">${esc(t.artist || '—')}</div>`);
    const dur = el('div', 'r-dur', t.duration_str);
    const acts = el('div', 'acts');
    acts.append(actBtn('edit', 'Yeniden adlandır', () => showRename(t)));
    if (mode === 'library') {
      acts.append(actBtn('plus', 'Listeye ekle', () => showAddToPlaylist(t)));
      acts.append(actBtn('trash', 'Sil', () => confirmDelete(t)));
    } else {
      acts.append(actBtn('close', 'Listeden çıkar', () => removeFromPlaylist(t.id)));
    }
    if (mode === 'playlist') {
      const grip = el('div', 'grip', ICONS.grip); grip.title = 'Sürükleyip sırala';
      grip.addEventListener('mousedown', (e) => startGripDrag(e, row));
      grip.addEventListener('click', (e) => e.stopPropagation());
      row.append(grip, idx, thumb, info, dur, acts);
    } else {
      row.append(idx, thumb, info, dur, acts);
    }
    row.onclick = () => { if (t.playing) togglePlayRow(); else playTrack(t.id); };
    rows.appendChild(row);
    if (t.playing) playingRow = row;
  });
  if (playingRow) playingRow.scrollIntoView({ block: 'nearest' });
}
function actBtn(icon, title, fn) {
  const b = el('span', 'a', ICONS[icon]); b.title = title; b.draggable = false;
  b.onclick = (e) => { e.stopPropagation(); fn(); };
  return b;
}
function renderEmpty(mode) {
  const rows = $('rows');
  const wrap = el('div', 'empty');
  wrap.appendChild(el('div', 'circle', `<span style="color:#5a5a5a">${bigNote()}</span>`));
  if (mode === 'library') {
    wrap.appendChild(el('div', 'et', 'Kütüphanen henüz boş'));
    wrap.appendChild(el('div', 'ed', 'Yukarıdaki arama kutusuna bir şarkı adı ya da bağlantı yapıştır; indirdiğin parçalar burada birikecek.'));
    const b = el('button', 'btn-green', 'İlk şarkını ara'); b.onclick = () => $('search').focus();
    wrap.appendChild(b);
  } else {
    wrap.appendChild(el('div', 'et', 'Bu liste boş'));
    wrap.appendChild(el('div', 'ed', 'Kütüphandeki bir şarkının ＋ düğmesiyle bu listeye ekleyebilirsin.'));
  }
  rows.appendChild(wrap);
}
function bigNote() { return '<svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>'; }

// ---------- görünümler ----------
async function showLibrary() {
  state.view = 'library'; state.pid = null;
  const tracks = await API.get_library();
  setHeader('İNDİRİLENLER', 'Kütüphane', metaText(tracks), false, tracks.length > 0);
  $('playPl').style.display = tracks.length ? 'flex' : 'none';
  updatePlayPlIcon();
  renderTracks(tracks, 'library');
}
async function showPlaylist(pid, name) {
  state.view = 'playlist'; state.pid = pid; state.plName = name;
  const tracks = await API.get_playlist_tracks(pid);
  setHeader('ÇALMA LİSTESİ', name, metaText(tracks), true, tracks.length > 0);
  $('playPl').style.display = tracks.length ? 'flex' : 'none';
  updatePlayPlIcon();
  renderTracks(tracks, 'playlist');
}
async function refreshView() {
  if (state.view === 'library') return showLibrary();
  if (state.view === 'playlist') return showPlaylist(state.pid, state.plName);
}

// ---------- çalma ----------
async function playTrack(id) {
  state.playingScope = (state.view === 'playlist') ? state.pid : 'library';
  const src = state.view === 'playlist' ? `${state.plName} listesinden çalınıyor` : 'Kütüphaneden çalınıyor';
  const now = await API.play(id, state.activeIds, src);
  updateNowPlaying(now);
  refreshView();
}
function updateNowPlaying(now) {
  if (!now || !now.id) return;
  $('pbTitle').textContent = now.title || '—';
  $('pbArtist').textContent = now.artist || '';
  $('npTitle').textContent = now.title || '—';
  $('npArtist').textContent = now.artist || '';
  setCover($('pbCover'), now.cover);
  setCover($('npCover'), now.cover);
  const ctx = $('npContext');
  if (now.source) { ctx.style.display = 'flex'; ctx.innerHTML = `<span style="color:var(--green)">${ICONS.note}</span> ${esc(now.source)}`; }
  else ctx.style.display = 'none';
  setPlayIcon(now.is_playing);
}
function clearNowPlaying() {
  $('pbTitle').textContent = '—'; $('pbArtist').textContent = '';
  $('npTitle').textContent = '—'; $('npArtist').textContent = '';
  setCover($('pbCover'), null); setCover($('npCover'), null);
  $('npContext').style.display = 'none'; setPlayIcon(false);
}
function setPlayIcon(p) {
  state.isPlaying = p;
  $('cPlay').innerHTML = p ? ICONS.pause : ICONS.play;
  // çalan satırın hover ikonu: çalarken duraklat (‖), duraklatılmışsa oynat (▶)
  const ih = document.querySelector('.row.playing .ih');
  if (ih) ih.innerHTML = p ? ICONS.pauseSmall : ICONS.playSmall;
  updatePlayPlIcon();
}
async function togglePlayRow() { setPlayIcon(await API.toggle()); }
// liste başlığındaki büyük çal düğmesi: bu liste çalıyorsa ‖, değilse ▶
function updatePlayPlIcon() {
  const btn = $('playPl');
  if (!btn || btn.style.display === 'none') return;
  const sc = curScope();
  const isThis = sc != null && state.playingScope === sc;
  btn.innerHTML = (isThis && state.isPlaying) ? ICONS.pause : ICONS.play;
}

// ---------- arama / indirme (açılır panel + spinner) ----------
function setSearchLoading(on) { $('ic-search').innerHTML = on ? '<div class="spinner"></div>' : ICONS.search; }
function openSearchPanel() { $('searchPanel').classList.add('show'); }
function closeSearchPanel() { stopPreview(); $('searchPanel').classList.remove('show'); $('searchPanel').innerHTML = ''; }

async function doSearch() {
  const text = $('search').value.trim(); if (!text) return;
  if (text.startsWith('http://') || text.startsWith('https://')) {
    openSearchPanel();      // mp3 mi mp4 mü diye sor (eskiden doğrudan mp3 inerdi)
    renderLinkChoice(text);
    return;
  }
  openSearchPanel();
  $('searchPanel').innerHTML = '<div class="sp-loading"><div class="spinner"></div></div>';
  setSearchLoading(true);
  const r = await API.search(text);
  setSearchLoading(false);
  if (r.error) { $('searchPanel').innerHTML = `<div class="sp-empty">Arama hatası: ${esc(r.error)}</div>`; return; }
  renderSearchResults(r.results || []);
}

function renderSearchResults(results) {
  const p = $('searchPanel'); p.innerHTML = '';
  if (!results.length) { p.innerHTML = '<div class="sp-empty">Sonuç bulunamadı.</div>'; return; }
  for (const r of results) {
    const row = el('div', 'sp-row');
    const thumb = el('div', 'thumb', `${ICONS.note}<span class="pvov">${ICONS.playSmall}</span>`);
    thumb.title = 'Önizle (ilk 6 sn)';
    thumb.onclick = () => previewToggle(r, thumb);
    const info = el('div', 'info', `<div class="rt ellipsis">${esc(r.title)}</div><div class="rs ellipsis">${esc(r.source + (r.uploader ? ' · ' + r.uploader : ''))}</div>`);
    const dur = el('div', 'rd', r.duration_str);
    const vbtn = el('button', 'dlv', ICONS.video); vbtn.title = 'Video indir (mp4, en iyi kalite)';
    vbtn.onclick = () => downloadVideoFromPanel(r, vbtn);
    const btn = el('button', 'dl', ICONS.download); btn.title = 'Müzik indir (mp3)';
    btn.onclick = () => downloadFromPanel(r, btn);
    row.append(thumb, info, dur, vbtn, btn);
    p.appendChild(row);
  }
}

// Yapıştırılan bağlantı için tek satırlık seçim: mp3 mi, mp4 mü?
function renderLinkChoice(url) {
  const p = $('searchPanel'); p.innerHTML = '';
  const row = el('div', 'sp-row');
  const thumb = el('div', 'thumb', ICONS.note);
  const info = el('div', 'info',
    `<div class="rt ellipsis">Bu bağlantı</div><div class="rs ellipsis">${esc(url)}</div>`);
  const target = { url, title: url };
  const vbtn = el('button', 'dlv', ICONS.video); vbtn.title = 'Video indir (mp4, en iyi kalite)';
  vbtn.onclick = () => downloadVideoFromPanel(target, vbtn);
  const btn = el('button', 'dl', ICONS.download); btn.title = 'Müzik indir (mp3)';
  btn.onclick = () => downloadFromPanel(target, btn);
  row.append(thumb, info, vbtn, btn);
  p.appendChild(row);
}

async function downloadFromPanel(r, btn) {
  stopPreview();
  btn.disabled = true; btn.style.background = '#2a2a2a'; btn.innerHTML = '<div class="spinner"></div>';
  const res = await API.download(r.url);
  if (res.error) { btn.disabled = false; btn.style.background = ''; btn.innerHTML = ICONS.download; setStatus('İndirme hatası: ' + res.error, { kind: 'error' }); }
  else {
    btn.style.background = 'transparent'; btn.style.color = 'var(--green)'; btn.innerHTML = ICONS.check;
    await refreshSidebar(); showLibrary();
    setStatus('Kütüphaneye eklendi: ' + (res.title || ''), { kind: 'ok' });
  }
}

// mp4 indirme: kütüphaneye EKLENMEZ, video/ klasörüne iner.
// İş bitince buton "klasörü aç" düğmesine dönüşür (status barı yok).
async function downloadVideoFromPanel(r, btn) {
  stopPreview();
  btn.disabled = true; btn.classList.add('busy'); btn.innerHTML = '<div class="spinner"></div>';
  const res = await API.download_video(r.url);
  if (res.error) {
    btn.disabled = false; btn.classList.remove('busy');
    btn.classList.add('failed'); btn.innerHTML = ICONS.video;
    btn.title = 'Video indirme hatası: ' + res.error;
    setStatus('Video indirme hatası: ' + res.error, { kind: 'error' });
    return;
  }
  btn.disabled = false; btn.classList.remove('busy'); btn.classList.add('done');
  btn.innerHTML = ICONS.folder;
  const note = res.not_mp4
    ? `Video indi (${res.resolution}) — kodek mp4'e çevrilemedi, .${res.ext} olarak kaydedildi`
    : `Video indi (${res.resolution}, mp4)`;
  btn.title = note + '. Klasörü açmak için tıkla.';
  btn.onclick = () => API.open_video_folder();
  setStatus(note, {
    kind: res.not_mp4 ? '' : 'ok',
    action: 'Klasörü aç',
    onAction: () => API.open_video_folder(),
  });
}

// ---- önizleme (indirmeden ilk ~6 sn) — küçük resmin üstündeki ▶ ----
let activePv = null, pvTimer = null;
async function previewToggle(r, thumb) {
  if (activePv === thumb) { stopPreview(); return; }   // aynı resme tekrar tıkla -> durdur
  resetPreviewBtn();
  const ov = thumb.querySelector('.pvov');
  thumb.classList.add('previewing'); ov.innerHTML = '<div class="spinner"></div>';
  const res = await API.preview(r.url);
  if (!res || res.error) { thumb.classList.remove('previewing'); ov.innerHTML = ICONS.playSmall; return; }
  ov.innerHTML = ICONS.stopSmall; activePv = thumb;
  pvTimer = setTimeout(resetPreviewBtn, ((res.dur || 6) * 1000) + 600);  // klip bitince ▶'e dön
}
function stopPreview() { try { API.stop_preview(); } catch (e) {} resetPreviewBtn(); }
function resetPreviewBtn() {
  if (pvTimer) { clearTimeout(pvTimer); pvTimer = null; }
  if (activePv) {
    activePv.classList.remove('previewing');
    const ov = activePv.querySelector('.pvov'); if (ov) ov.innerHTML = ICONS.playSmall;
    activePv = null;
  }
}

// ---------- diyaloglar ----------
function openModal(node) { const ov = $('overlay'); ov.innerHTML = ''; ov.appendChild(node); ov.classList.add('show'); ov.onclick = (e) => { if (e.target === ov) closeModal(); }; }
function closeModal() { $('overlay').classList.remove('show'); $('overlay').innerHTML = ''; }

function showInput(title, label, onOk) {
  const d = el('div', 'dialog', `<h3>${esc(title)}</h3><label>${esc(label)}</label><input id="mIn"><div class="btns"><button class="b cancel">İptal</button><button class="b ok">Oluştur</button></div>`);
  openModal(d);
  const inp = d.querySelector('#mIn');
  d.querySelector('.cancel').onclick = closeModal;
  const ok = () => { const v = inp.value.trim(); if (v) { closeModal(); onOk(v); } };
  d.querySelector('.ok').onclick = ok;
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') ok(); });
  setTimeout(() => inp.focus(), 30);
}
function showConfirm(msg, okText, onOk) {
  const d = el('div', 'dialog', `<h3>Emin misin?</h3><div class="sub">${esc(msg)}</div><div class="btns"><button class="b cancel">İptal</button><button class="b ok">${esc(okText)}</button></div>`);
  openModal(d);
  d.querySelector('.cancel').onclick = closeModal;
  d.querySelector('.ok').onclick = () => { closeModal(); onOk(); };
}
function showRename(t) {
  const d = el('div', 'dialog', `<h3>Şarkıyı yeniden adlandır</h3><label>Başlık</label><input id="mT"><label>Sanatçı</label><input id="mA"><div class="btns"><button class="b cancel">İptal</button><button class="b ok">Kaydet</button></div>`);
  openModal(d);
  const ti = d.querySelector('#mT'), ar = d.querySelector('#mA');
  ti.value = t.title || ''; ar.value = t.artist || '';
  d.querySelector('.cancel').onclick = closeModal;
  const save = async () => { const tt = ti.value.trim(); if (!tt) return; closeModal(); const res = await API.rename_track(t.id, tt, ar.value.trim()); if (res && res.now) updateNowPlaying(res.now); refreshView(); setStatus('Yeniden adlandırıldı'); };
  d.querySelector('.ok').onclick = save;
  ti.addEventListener('keydown', e => { if (e.key === 'Enter') save(); });
  ar.addEventListener('keydown', e => { if (e.key === 'Enter') save(); });
  setTimeout(() => { ti.focus(); ti.select(); }, 30);
}
async function showAddToPlaylist(t) {
  const pls = await API.get_playlists();
  const members = await API.playlists_for_track(t.id);
  const d = el('div', 'dialog', `<h3>Çalma listesine ekle</h3><div class="sub">"${esc((t.title || '').slice(0, 34))}" şu listeye eklenecek</div><div class="picklist" id="mPick"></div><div class="newpl" id="mNew">${ICONS.plus} Yeni çalma listesi oluştur</div>`);
  openModal(d);
  const pick = d.querySelector('#mPick');
  if (!pls.length) pick.innerHTML = '<div style="color:var(--faint);padding:6px">(Henüz liste yok, aşağıdan oluştur)</div>';
  for (const pl of pls) {
    const isMember = members.includes(pl.id);
    const row = el('div', 'pl-pick' + (isMember ? ' member' : ''));
    const tile = el('div', 'tile', pl.letter); tile.style.background = pl.color;
    row.append(tile, el('div', 'pn ellipsis', esc(pl.name)), el('div', 'pi', isMember ? ICONS.check : ICONS.plus));
    if (!isMember) row.onclick = async () => { await API.add_to_playlist(pl.id, t.id); closeModal(); await refreshSidebar(); if (state.view === 'playlist' && state.pid === pl.id) showPlaylist(pl.id, pl.name); setStatus('Şarkı listeye eklendi'); };
    pick.appendChild(row);
  }
  d.querySelector('#mNew').onclick = () => { closeModal(); showInput('Yeni Çalma Listesi', 'Liste adı', async (name) => { const pid = await API.create_playlist(name); await API.add_to_playlist(pid, t.id); await refreshSidebar(); setStatus('Liste oluşturuldu, şarkı eklendi'); }); };
}
function confirmDelete(t) {
  showConfirm(`"${(t.title || '').slice(0, 40)}" kütüphaneden ve diskten tamamen silinsin mi?`, 'Sil', async () => {
    const res = await API.delete_track(t.id);
    if (res && res.cleared) clearNowPlaying();
    await refreshSidebar(); refreshView(); setStatus('Silindi');
  });
}
async function removeFromPlaylist(tid) { await API.remove_from_playlist(state.pid, tid); await refreshSidebar(); showPlaylist(state.pid, state.plName); }
function newPlaylist() { showInput('Yeni Çalma Listesi', 'Liste adı', async (name) => { await API.create_playlist(name); await refreshSidebar(); setStatus('Liste oluşturuldu: ' + name); }); }
function delPlaylist() { if (state.pid == null) return; showConfirm('Bu çalma listesi silinsin mi? (Şarkılar kalır)', 'Sil', async () => { await API.delete_playlist(state.pid); await refreshSidebar(); showLibrary(); setStatus('Liste silindi'); }); }

// ---------- sürükle-bırak: soldaki ≡ tutamaktan, YALNIZ DİKEY ----------
let gdrag = null;
function startGripDrag(e, row) {
  e.preventDefault(); e.stopPropagation();
  const rowList = [...$('rows').querySelectorAll('.row')];
  gdrag = { row, startY: e.clientY, startIndex: rowList.indexOf(row),
            h: row.offsetHeight || 57, rowList, target: rowList.indexOf(row) };
  row.classList.add('row-dragging');
  document.body.style.cursor = 'grabbing';
  document.addEventListener('mousemove', onGripMove);
  document.addEventListener('mouseup', onGripUp);
}
function onGripMove(e) {
  if (!gdrag) return;
  const dy = e.clientY - gdrag.startY;
  gdrag.row.style.transform = `translateY(${dy}px)`;   // X sabit -> yalnız dikey
  let target = gdrag.startIndex + Math.round(dy / gdrag.h);
  target = Math.max(0, Math.min(gdrag.rowList.length - 1, target));
  gdrag.target = target;
  // aradaki satırları kaydırıp boşluk aç (canlı his)
  gdrag.rowList.forEach((r, i) => {
    if (r === gdrag.row) return;
    let shift = 0;
    if (gdrag.startIndex < target && i > gdrag.startIndex && i <= target) shift = -gdrag.h;
    else if (gdrag.startIndex > target && i >= target && i < gdrag.startIndex) shift = gdrag.h;
    r.style.transform = shift ? `translateY(${shift}px)` : '';
  });
}
async function onGripUp() {
  document.removeEventListener('mousemove', onGripMove);
  document.removeEventListener('mouseup', onGripUp);
  document.body.style.cursor = '';
  if (!gdrag) return;
  const d = gdrag; gdrag = null;
  d.rowList.forEach(r => { r.style.transform = ''; });
  d.row.classList.remove('row-dragging');
  if (d.target === d.startIndex) return;
  const ids = d.rowList.map(r => parseInt(r.dataset.tid));
  const [moved] = ids.splice(d.startIndex, 1);
  ids.splice(d.target, 0, moved);
  state.activeIds = ids;
  await API.reorder_playlist(state.pid, ids);
  showPlaylist(state.pid, state.plName);
}

// ---------- ilerleme yoklaması ----------
async function poll() {
  try {
    const p = await API.progress();
    if (p.advanced) { updateNowPlaying(p.advanced); refreshView(); }
    setPlayIcon(p.playing);
    if (Date.now() - state.lastSeek > 400) {
      const v = p.dur > 0 ? p.pos / p.dur : 0;
      setBar($('seekFill'), $('seekKnob'), v);
      $('tCur').textContent = fmt(p.pos);
    }
    $('tTot').textContent = fmt(p.dur);
    window._dur = p.dur;
  } catch (e) {}
}

// ---------- çubuklar ----------
function bindBar(barEl, fillEl, knobEl, onChange) {
  function ratioFrom(e) { const r = barEl.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); }
  function apply(e) { const v = ratioFrom(e); setBar(fillEl, knobEl, v); onChange(v); }
  barEl.addEventListener('mousedown', (e) => {
    apply(e);
    const move = (ev) => apply(ev);
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}
function setBar(fillEl, knobEl, v) { fillEl.style.width = (v * 100) + '%'; knobEl.style.left = (v * 100) + '%'; }

// ---------- kurulum ----------
async function init() {
  injectStaticIcons();
  setPlayIcon(false);
  $('npToggle').style.color = 'var(--green)';
  const data = await API.get_initial();
  renderPlaylists(data.playlists);
  await showLibrary();
  setBar($('volFill'), $('volKnob'), data.volume);
  if (data.now) updateNowPlaying(data.now);

  $('cPlay').onclick = async () => setPlayIcon(await API.toggle());
  $('cNext').onclick = async () => { const n = await API.next(); if (n) { updateNowPlaying(n); refreshView(); } };
  $('cPrev').onclick = async () => { const n = await API.prev(); if (n) { updateNowPlaying(n); refreshView(); } };
  $('cShuffle').onclick = async () => { state.shuffle = await API.set_shuffle(!state.shuffle); $('cShuffle').classList.toggle('active', state.shuffle); };
  $('cRepeat').onclick = async () => { state.repeat = await API.set_repeat(!state.repeat); $('cRepeat').classList.toggle('active', state.repeat); };
  $('navLib').onclick = () => showLibrary();
  $('npClose').onclick = toggleNp;
  $('npToggle').onclick = toggleNp;
  $('newPl').onclick = newPlaylist;
  $('delPl').onclick = delPlaylist;
  $('playPl').innerHTML = ICONS.play;
  $('playPl').onclick = async () => {
    if (state.playingScope === curScope()) setPlayIcon(await API.toggle());  // bu kaynak çalıyorsa duraklat/devam
    else if (state.view === 'library') playLibrary();                        // değilse baştan çal
    else playPlaylist(state.pid, state.plName);
  };
  $('ic-search').onclick = doSearch;
  $('search').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  $('search').addEventListener('input', () => { if (!$('search').value.trim()) closeSearchPanel(); });
  document.addEventListener('mousedown', (e) => {
    const p = $('searchPanel');
    if (!p.classList.contains('show')) return;
    if (p.contains(e.target) || $('search').contains(e.target) || $('ic-search').contains(e.target)) return;
    closeSearchPanel();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSearchPanel(); });

  bindBar($('seek'), $('seekFill'), $('seekKnob'), (v) => { state.lastSeek = Date.now(); if (window._dur) API.seek(v * window._dur); $('tCur').textContent = fmt(v * (window._dur || 0)); });
  bindBar($('vol'), $('volFill'), $('volKnob'), (v) => API.set_volume(v));

  setInterval(poll, 300);
}
function toggleNp() {
  state.npVisible = !state.npVisible;
  $('nowplaying').classList.toggle('hidden', !state.npVisible);
  $('npToggle').style.color = state.npVisible ? 'var(--green)' : 'var(--sub)';
}

window.addEventListener('pywebviewready', () => { API = window.pywebview.api; init(); });
