/* Application de révision — front vanilla, aucune dépendance. */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
));

const APP = {
  state: null,
  stats: null,
  courseCache: {},
  session: null,
  exam: null,
  view: 'today',
};

/* ------------------------------------------------------------------ API */
async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* réponse vide */ }
  if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
  return data;
}

function toast(message, kind = '') {
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.textContent = message;
  $('#toasts').append(node);
  setTimeout(() => { node.style.opacity = '0'; setTimeout(() => node.remove(), 250); }, kind === 'error' ? 7000 : 3500);
}

/* --------------------------------------------------------------- Router */
function go(view) {
  APP.view = view;
  $$('#tabs button').forEach((btn) => btn.classList.toggle('active', btn.dataset.view === view));
  $$('.view').forEach((section) => section.classList.toggle('active', section.id === `view-${view}`));
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (view === 'stats') loadStats();
  if (view === 'courses') renderCourses();
  if (view === 'settings') renderSettings();
  if (view === 'review' || view === 'exam') fillCourseSelects();
}

/* ------------------------------------------------------------ Chargement */
async function refresh() {
  APP.state = await api('/api/state');
  $('#streak-chip').innerHTML = `🔥 <b>${APP.state.streak}</b>`;
  $('#due-chip').innerHTML = `⏰ <b>${APP.state.due}</b>`;
  $('#tagline').textContent = APP.state.ai_available ? `IA · ${APP.state.model}` : 'mode hors-ligne';
  renderToday();
  renderCourses();
  fillCourseSelects();
}

/* ------------------------------------------------------- Vue Aujourd'hui */
function renderToday() {
  const { missions, courses, due, settings } = APP.state;
  const daily = missions.find((m) => m.id === 'daily') || { done: 0, total: settings.daily_goal };
  const ratio = daily.total ? Math.min(1, daily.done / daily.total) : 0;
  $('#ring-fill').style.strokeDashoffset = String(327 - 327 * ratio);
  $('#goal-done').textContent = daily.done;
  $('#goal-total').textContent = daily.total;

  const total = courses.reduce((sum, c) => sum + c.counts.cards, 0);
  if (!courses.length) {
    $('#hero-title').textContent = 'Commence par un cours';
    $('#hero-sub').textContent = 'Importe un PDF, un DOCX, un PPTX, une photo de tableau ou colle tes notes.';
  } else if (!total) {
    $('#hero-title').textContent = 'Génère tes cartes';
    $('#hero-sub').textContent = 'Tes cours sont importés : lance la génération de flashcards et de QCM.';
  } else if (due) {
    $('#hero-title').textContent = `${due} carte${due > 1 ? 's' : ''} à réviser`;
    $('#hero-sub').textContent = daily.done >= daily.total
      ? 'Objectif du jour atteint — tout bonus est du bonus 💪'
      : `Encore ${Math.max(0, daily.total - daily.done)} cartes pour l'objectif du jour.`;
  } else {
    $('#hero-title').textContent = 'File à jour ✅';
    $('#hero-sub').textContent = 'Rien d\'urgent. Entraînement libre ou examen blanc ?';
  }
  $('#btn-start-due').disabled = !total;
  $('#btn-quick-quiz').disabled = !total;

  $('#missions').innerHTML = missions.map((mission) => {
    const done = mission.done >= mission.total;
    const bar = mission.total > 1
      ? `<div class="mini-bar"><i style="width:${Math.round(100 * mission.done / mission.total)}%"></i></div>`
      : '';
    return `<li class="${done ? 'done' : ''}" data-action="${mission.action}" data-course="${mission.course_id || ''}">
      <span class="check">${done ? '✓' : ''}</span>
      <span class="m-label">${esc(mission.label)}
        ${mission.total > 1 ? `<small class="muted">${mission.done}/${mission.total}</small>` : ''}${bar}</span>
    </li>`;
  }).join('') || '<li class="muted">Rien à faire aujourd\'hui.</li>';

  $('#today-courses').innerHTML = courses.length ? courses.slice(0, 12).map((course) => `
    <div class="mini-course" data-course="${course.id}">
      <b>${esc(course.title.slice(0, 34))}</b>
      <div class="muted small">${esc(course.subject || 'sans matière')}</div>
      <div class="mini-bar"><i style="width:${course.progress}%"></i></div>
      <div class="muted small">${course.counts.cards} cartes · ${course.counts.due} dues</div>
    </div>`).join('') : '<p class="empty">Aucun cours pour l\'instant.</p>';
}

/* ------------------------------------------------------------ Vue Cours */
function renderCourses() {
  if (!APP.state) return;
  const query = ($('#course-search').value || '').toLowerCase();
  const list = APP.state.courses.filter((course) => !query
    || course.title.toLowerCase().includes(query) || (course.subject || '').toLowerCase().includes(query));
  $('#courses-list').innerHTML = list.length ? list.map((course) => `
    <div class="course-row" data-course="${course.id}">
      <span class="badge-kind">${esc(course.kind)}</span>
      <div class="course-main">
        <b>${esc(course.title)}</b>
        <div class="course-meta">
          ${course.subject ? `<span class="pill">${esc(course.subject)}</span>` : ''}
          <span>${course.counts.cards} cartes</span>
          ${course.counts.due ? `<span class="pill due">${course.counts.due} dues</span>` : '<span class="pill ok">à jour</span>'}
          <span>${course.progress}% maîtrisé</span>
          ${course.exam_date ? `<span class="pill">examen ${esc(course.exam_date)}</span>` : ''}
        </div>
      </div>
      <span class="muted">›</span>
    </div>`).join('') : '<p class="empty">Aucun cours. Ajoute-en un ci-dessus.</p>';
}

async function openCourse(courseId) {
  go('courses');
  const pane = $('#course-detail');
  pane.classList.remove('hidden');
  $('#courses-list-pane').classList.add('hidden');
  pane.innerHTML = '<div class="card"><div class="row"><span class="spinner"></span> Chargement…</div></div>';
  let data;
  try {
    data = await api(`/api/courses/${courseId}`);
  } catch (err) {
    toast(err.message, 'error');
    closeCourse();
    return;
  }
  APP.courseCache[courseId] = data;
  renderCourseDetail(courseId);
}

function closeCourse() {
  $('#course-detail').classList.add('hidden');
  $('#course-detail').innerHTML = '';
  $('#courses-list-pane').classList.remove('hidden');
}

function ficheHtml(fiche) {
  if (!fiche) return '';
  const list = (items, render) => (items && items.length ? `<ul>${items.map(render).join('')}</ul>` : '');
  return `<div class="fiche">
    ${fiche.resume ? `<h3>Résumé</h3><p>${esc(fiche.resume)}</p>` : ''}
    ${fiche.plan && fiche.plan.length ? `<h3>Plan</h3>${fiche.plan.map((part) => `
      <p><b>${esc(part.titre)}</b>${part.contenu ? `<br>${esc(part.contenu)}` : ''}</p>`).join('')}` : ''}
    ${list(fiche.points_cles, (point) => `<li>${esc(point)}</li>`) ? `<h3>Points clés</h3>${list(fiche.points_cles, (p) => `<li>${esc(p)}</li>`)}` : ''}
    ${fiche.definitions && fiche.definitions.length ? `<h3>Définitions</h3><div class="defs">${fiche.definitions.map((def) => `
      <div><b>${esc(def.terme)}</b> — ${esc(def.definition)}</div>`).join('')}</div>` : ''}
    ${fiche.pieges && fiche.pieges.length ? `<h3>Pièges à éviter</h3>${list(fiche.pieges, (piege) => `<li>${esc(piege)}</li>`)}` : ''}
  </div>`;
}

function mindmapHtml(mindmap) {
  if (!mindmap || !mindmap.racine) return '';
  const branches = (mindmap.branches || []).map((branch) => `
    <div class="mm-branch">
      <span class="mm-node">${esc(branch.titre)}</span>
      ${branch.enfants && branch.enfants.length ? `<span class="mm-link">→</span>
        <div class="mm-children">${branch.enfants.map((child) => `<span class="mm-leaf">${esc(child.titre)}</span>`).join('')}</div>` : ''}
    </div>`).join('');
  return `<div class="mindmap">
    <div class="mm-root">${esc(mindmap.racine)}</div>
    ${branches ? `<span class="mm-link">→</span><div class="mm-branches">${branches}</div>` : ''}
  </div>`;
}

function renderCourseDetail(courseId) {
  const { course, cards } = APP.courseCache[courseId];
  const pane = $('#course-detail');
  pane.innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <h2 style="margin:0">${esc(course.title)}</h2>
          <div class="course-meta">
            ${course.subject ? `<span class="pill">${esc(course.subject)}</span>` : ''}
            <span>${course.counts.cards} cartes (${course.counts.flashcards} flashcards, ${course.counts.qcm} QCM)</span>
            ${course.counts.due ? `<span class="pill due">${course.counts.due} dues</span>` : ''}
            <span>${course.chars.toLocaleString('fr-FR')} caractères</span>
          </div>
        </div>
        <button class="btn small ghost" id="btn-close-course">Retour</button>
      </div>
      <div class="row wrap">
        <button class="btn primary" id="btn-generate">✨ Générer / compléter le matériel</button>
        <button class="btn" id="btn-review-course" ${course.counts.cards ? '' : 'disabled'}>Réviser ce cours</button>
        <button class="btn" id="btn-exam-course" ${course.counts.cards ? '' : 'disabled'}>Examen blanc</button>
        <button class="btn small ghost" id="btn-edit-course">Renommer / matière / date d'examen</button>
        <button class="btn small danger" id="btn-delete-course">Supprimer</button>
      </div>
      <div class="row wrap" id="gen-options" style="margin-top:.6rem">
        <label>Niveau <select id="gen-level">
          <option value="facile">Facile</option><option value="normal" selected>Standard</option><option value="difficile">Exigeant</option>
        </select></label>
        <label>Flashcards <input type="number" id="gen-flash" min="0" max="60" value="${APP.state.settings.flashcards_per_generation}" style="width:80px"></label>
        <label>QCM <input type="number" id="gen-qcm" min="0" max="40" value="${APP.state.settings.qcm_per_generation}" style="width:80px"></label>
        <label class="grow">Focus (optionnel) <input id="gen-focus" placeholder="ex : chapitre 3, les intégrales…"></label>
      </div>
      <div id="gen-status" class="import-log"></div>
    </div>

    ${course.fiche ? `<div class="card"><h2>Fiche de révision</h2>${ficheHtml(course.fiche)}</div>` : ''}
    ${course.mindmap ? `<div class="card"><h2>Mind map</h2>${mindmapHtml(course.mindmap)}</div>` : ''}

    <div class="card">
      <h2>Tuteur</h2>
      ${APP.state.ai_available ? `
        <div class="chat" id="chat"></div>
        <div class="row"><input id="chat-input" class="grow" placeholder="Explique-moi la partie que je n'ai pas comprise…">
        <button class="btn primary" id="btn-ask">Demander</button></div>`
      : '<p class="muted">Nécessite <code>ANTHROPIC_API_KEY</code> côté serveur.</p>'}
    </div>

    <div class="card">
      <div class="card-head">
        <h2>Cartes (${cards.length})</h2>
        <button class="btn small" id="btn-add-card">+ Ajouter</button>
      </div>
      <div class="cards-table" id="cards-table">${cards.map(cardRowHtml).join('') || '<p class="empty">Aucune carte encore.</p>'}</div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Contenu du cours</h2>
        <button class="btn small ghost" id="btn-toggle-text">Afficher / masquer</button></div>
      <div class="course-text hidden" id="course-text">${esc(course.text)}</div>
    </div>`;

  $('#btn-close-course').onclick = closeCourse;
  $('#btn-generate').onclick = () => generateMaterial(courseId);
  $('#btn-review-course').onclick = () => { go('review'); $('#review-course').value = courseId; $('#review-scope').value = 'due'; runSession(); };
  $('#btn-exam-course').onclick = () => { go('exam'); $('#exam-course').value = courseId; };
  $('#btn-edit-course').onclick = () => editCourse(courseId);
  $('#btn-delete-course').onclick = () => deleteCourse(courseId);
  $('#btn-toggle-text').onclick = () => $('#course-text').classList.toggle('hidden');
  $('#btn-add-card').onclick = () => addCard(courseId);
  if ($('#btn-ask')) {
    $('#btn-ask').onclick = () => ask(courseId);
    $('#chat-input').onkeydown = (event) => { if (event.key === 'Enter') ask(courseId); };
  }
  $('#cards-table').onclick = (event) => {
    const action = event.target.dataset.cardAction;
    if (!action) return;
    const cardId = event.target.closest('.card-row').dataset.card;
    if (action === 'delete') deleteCard(courseId, cardId);
    if (action === 'reset') api(`/api/cards/${cardId}`, { method: 'PATCH', body: { reset: true } })
      .then(() => { toast('Carte remise à zéro', 'ok'); openCourse(courseId); refresh(); })
      .catch((err) => toast(err.message, 'error'));
  };
}

function cardRowHtml(card) {
  const answer = card.type === 'qcm'
    ? `${esc((card.choices || [])[card.correct] || '')} <span class="muted">(QCM)</span>`
    : esc(card.answer);
  return `<div class="card-row" data-card="${card.id}">
    <div class="q">${esc(card.question)}</div>
    <div class="a">${answer}</div>
    <div class="actions">
      <span class="pill">${esc(card.maturity)}</span>
      ${card.tag ? `<span class="pill">${esc(card.tag)}</span>` : ''}
      <button class="btn small ghost" data-card-action="reset">Réinitialiser</button>
      <button class="btn small danger" data-card-action="delete">Supprimer</button>
    </div>
  </div>`;
}

async function generateMaterial(courseId) {
  const status = $('#gen-status');
  const button = $('#btn-generate');
  button.disabled = true;
  status.innerHTML = '<div class="import-line"><span class="spinner"></span> Claude lit ton cours et fabrique le matériel…</div>';
  try {
    const result = await api(`/api/courses/${courseId}/generate`, {
      method: 'POST',
      body: {
        level: $('#gen-level').value,
        n_flashcards: Number($('#gen-flash').value),
        n_qcm: Number($('#gen-qcm').value),
        focus: $('#gen-focus').value,
      },
    });
    status.innerHTML = `<div class="import-line">✅ ${result.created} nouvelle(s) carte(s)${result.offline ? ' — mode hors-ligne, qualité limitée' : ''}</div>`;
    toast(`${result.created} cartes ajoutées`, 'ok');
    await refresh();
    await openCourse(courseId);
  } catch (err) {
    status.innerHTML = `<div class="import-line">❌ ${esc(err.message)}</div>`;
    toast(err.message, 'error');
  } finally {
    if ($('#btn-generate')) $('#btn-generate').disabled = false;
  }
}

async function editCourse(courseId) {
  const { course } = APP.courseCache[courseId];
  const title = prompt('Titre du cours :', course.title);
  if (title === null) return;
  const subject = prompt('Matière :', course.subject || '');
  if (subject === null) return;
  const examDate = prompt('Date d\'examen (AAAA-MM-JJ, vide si aucune) :', course.exam_date || '');
  try {
    await api(`/api/courses/${courseId}`, { method: 'PATCH', body: { title, subject, exam_date: examDate || '' } });
    await refresh();
    await openCourse(courseId);
  } catch (err) { toast(err.message, 'error'); }
}

async function deleteCourse(courseId) {
  const { course } = APP.courseCache[courseId];
  if (!confirm(`Supprimer « ${course.title} » et ses ${course.counts.cards} cartes ?`)) return;
  try {
    await api(`/api/courses/${courseId}`, { method: 'DELETE' });
    toast('Cours supprimé', 'ok');
    closeCourse();
    refresh();
  } catch (err) { toast(err.message, 'error'); }
}

async function deleteCard(courseId, cardId) {
  try {
    await api(`/api/cards/${cardId}`, { method: 'DELETE' });
    await refresh();
    await openCourse(courseId);
  } catch (err) { toast(err.message, 'error'); }
}

async function addCard(courseId) {
  const question = prompt('Question :');
  if (!question) return;
  const answer = prompt('Réponse :');
  if (!answer) return;
  try {
    await api('/api/cards', { method: 'POST', body: { course_id: courseId, type: 'flashcard', question, answer } });
    await refresh();
    await openCourse(courseId);
  } catch (err) { toast(err.message, 'error'); }
}

async function ask(courseId) {
  const input = $('#chat-input');
  const question = input.value.trim();
  if (!question) return;
  const chat = $('#chat');
  const history = $$('.bubble', chat).map((node) => ({
    role: node.classList.contains('user') ? 'user' : 'assistant', content: node.textContent,
  }));
  input.value = '';
  chat.insertAdjacentHTML('beforeend', `<div class="bubble user">${esc(question)}</div>`);
  const pending = document.createElement('div');
  pending.className = 'bubble assistant';
  pending.innerHTML = '<span class="spinner"></span>';
  chat.append(pending);
  chat.scrollTop = chat.scrollHeight;
  try {
    const result = await api(`/api/courses/${courseId}/ask`, { method: 'POST', body: { question, history } });
    pending.textContent = result.answer;
  } catch (err) {
    pending.textContent = `❌ ${err.message}`;
  }
  chat.scrollTop = chat.scrollHeight;
}

/* ----------------------------------------------------------- Import */
function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Lecture du fichier impossible'));
    reader.readAsDataURL(file);
  });
}

async function importFiles(files) {
  const log = $('#import-log');
  for (const file of files) {
    const line = document.createElement('div');
    line.className = 'import-line';
    line.innerHTML = `<span class="spinner"></span> ${esc(file.name)}`;
    log.append(line);
    try {
      const data = await readAsBase64(file);
      const result = await api('/api/courses', {
        method: 'POST',
        body: { filename: file.name, data_b64: data, title: file.name.replace(/\.[^.]+$/, '') },
      });
      line.innerHTML = `✅ ${esc(file.name)} — ${result.course.chars.toLocaleString('fr-FR')} caractères`
        + (result.transcribed ? ' <span class="muted">(transcrit par l\'IA)</span>' : '');
      await refresh();
      if (files.length === 1) openCourse(result.course.id);
    } catch (err) {
      line.innerHTML = `❌ ${esc(file.name)} — ${esc(err.message)}`;
    }
  }
}

/* --------------------------------------------------- Session de révision */
function fillCourseSelects() {
  if (!APP.state) return;
  const options = APP.state.courses.map((course) =>
    `<option value="${course.id}">${esc(course.title)} (${course.counts.due}/${course.counts.cards})</option>`).join('');
  const review = $('#review-course');
  const exam = $('#exam-course');
  const keep = [review.value, exam.value];
  review.innerHTML = `<option value="">Tous les cours</option>${options}`;
  exam.innerHTML = `<option value="all">Tous les cours</option>${options}`;
  if (keep[0]) review.value = keep[0];
  if (keep[1]) exam.value = keep[1];
}

async function runSession(overrides = {}) {
  const params = new URLSearchParams({
    scope: overrides.scope || $('#review-scope').value,
    limit: overrides.limit || $('#review-limit').value,
  });
  const courseId = overrides.course_id ?? $('#review-course').value;
  const type = overrides.type ?? $('#review-type').value;
  if (courseId) params.set('course_id', courseId);
  if (type) params.set('type', type);
  go('review');
  try {
    const data = await api(`/api/session?${params}`);
    if (!data.cards.length) {
      toast('Aucune carte dans cette sélection', 'error');
      return;
    }
    APP.session = {
      queue: data.cards,
      done: 0,
      total: data.cards.length,
      correct: 0,
      startedAt: Date.now(),
      shownAt: Date.now(),
      revealed: false,
      picked: null,
    };
    $('#review-setup').classList.add('hidden');
    $('#review-runner').classList.remove('hidden');
    renderCard();
  } catch (err) { toast(err.message, 'error'); }
}

function endSession() {
  const session = APP.session;
  const minutes = Math.max(1, Math.round((Date.now() - session.startedAt) / 60000));
  const accuracy = session.done ? Math.round(100 * session.correct / session.done) : 0;
  $('#review-runner').innerHTML = `<div class="card session-done">
    <div class="score">${accuracy}%</div>
    <p class="muted">${session.done} cartes en ${minutes} min · ${session.correct} réussies</p>
    <div class="row" style="justify-content:center">
      <button class="btn primary" id="btn-again-session">Nouvelle session</button>
      <button class="btn ghost" data-goto="today">Retour au tableau de bord</button>
    </div></div>`;
  $('#btn-again-session').onclick = () => { $('#review-runner').classList.add('hidden'); $('#review-setup').classList.remove('hidden'); };
  APP.session = null;
  refresh();
}

function renderCard() {
  const session = APP.session;
  if (!session || !session.queue.length) { if (session) endSession(); return; }
  const card = session.queue[0];
  session.revealed = false;
  session.picked = null;
  session.shownAt = Date.now();
  const progress = Math.round(100 * session.done / Math.max(1, session.total));

  $('#review-runner').innerHTML = `
    <div class="runner-head">
      <div class="progress"><i style="width:${progress}%"></i></div>
      <span class="muted small">${session.done}/${session.total}</span>
      <button class="btn small ghost" id="btn-stop-session">Terminer</button>
    </div>
    <div class="qcard">
      <div class="q-meta">
        <span class="pill">${card.type === 'qcm' ? 'QCM' : 'Flashcard'}</span>
        ${card.course_title ? `<span>${esc(card.course_title)}</span>` : ''}
        ${card.tag ? `<span class="pill">${esc(card.tag)}</span>` : ''}
        <span class="muted">${esc(card.maturity)}</span>
      </div>
      <div class="q-text">${esc(card.question)}</div>
      ${card.type === 'qcm'
        ? `<div class="choices">${card.choices.map((choice, index) =>
            `<button class="choice" data-index="${index}"><span class="key">${'ABCDEFGH'[index]}</span><span>${esc(choice)}</span></button>`).join('')}</div>`
        : `<div id="answer-slot"></div>`}
      <div id="grade-slot"></div>
      ${card.type === 'flashcard' ? '<div class="row" style="margin-top:1rem"><button class="btn primary" id="btn-reveal">Voir la réponse <kbd>Espace</kbd></button></div>' : ''}
    </div>`;

  $('#btn-stop-session').onclick = endSession;
  if ($('#btn-reveal')) $('#btn-reveal').onclick = reveal;
  $$('.choice').forEach((button) => { button.onclick = () => pickChoice(Number(button.dataset.index)); });
}

function gradeRowHtml(card, suggestion) {
  const labels = { again: 'À revoir', hard: 'Difficile', good: 'Correct', easy: 'Facile' };
  return `<div class="grade-row">${Object.keys(labels).map((grade, index) => `
    <button class="grade-btn" data-grade="${grade}" ${grade === suggestion ? 'autofocus' : ''}>
      <b>${labels[grade]}</b><small>${esc(card.intervals[grade])} · ${index + 1}</small>
    </button>`).join('')}</div>`;
}

function reveal() {
  const session = APP.session;
  if (!session || session.revealed) return;
  const card = session.queue[0];
  session.revealed = true;
  const slot = $('#answer-slot');
  if (slot) slot.innerHTML = `<div class="a-text">${esc(card.answer)}</div>`;
  if ($('#btn-reveal')) $('#btn-reveal').remove();
  $('#grade-slot').innerHTML = gradeRowHtml(card, 'good');
  $$('.grade-btn').forEach((button) => { button.onclick = () => submitGrade(button.dataset.grade); });
}

function pickChoice(index) {
  const session = APP.session;
  if (!session || session.revealed) return;
  const card = session.queue[0];
  session.revealed = true;
  session.picked = index;
  const correct = index === card.correct;
  $$('.choice').forEach((button, position) => {
    if (position === card.correct) button.classList.add('correct');
    else if (position === index) button.classList.add('wrong');
    button.disabled = true;
  });
  $('#grade-slot').innerHTML =
    `<div class="a-text"><b>${correct ? '✅ Bonne réponse' : '❌ Réponse attendue : ' + esc(card.choices[card.correct])}</b>
      ${card.explanation ? `<br>${esc(card.explanation)}` : ''}</div>
     ${gradeRowHtml(card, correct ? 'good' : 'again')}`;
  $$('.grade-btn').forEach((button) => { button.onclick = () => submitGrade(button.dataset.grade); });
}

async function submitGrade(grade) {
  const session = APP.session;
  if (!session || !session.revealed) return;
  const card = session.queue.shift();
  session.done += 1;
  if (grade === 'good' || grade === 'easy') session.correct += 1;
  const elapsed = Date.now() - session.shownAt;

  // Une carte « à revoir » repasse tout de suite en fin de file.
  let requeued = null;
  if (grade === 'again') {
    requeued = { ...card };
    session.queue.push(requeued);
    session.total += 1;
  }
  renderCard();

  try {
    const result = await api('/api/review', { method: 'POST', body: { card_id: card.id, grade, ms: elapsed } });
    if (requeued) {
      requeued.srs = result.card.srs;
      requeued.intervals = result.card.intervals;
      // La carte repassée est déjà à l'écran : rafraîchir ses délais affichés.
      if (APP.session && APP.session.queue[0] === requeued && !APP.session.revealed) renderCard();
    }
    $('#due-chip').innerHTML = `⏰ <b>${result.due}</b>`;
  } catch (err) { toast(err.message, 'error'); }
}

/* ------------------------------------------------------------- Examen */
async function runExam() {
  const courseId = $('#exam-course').value;
  const count = Number($('#exam-count').value);
  const minutes = Number($('#exam-timer').value);
  try {
    const data = await api('/api/exam', { method: 'POST', body: { course_id: courseId, count } });
    APP.exam = { questions: data.questions, aiGrading: data.ai_grading, startedAt: Date.now(), deadline: minutes ? Date.now() + minutes * 60000 : 0 };
    $('#exam-setup').classList.add('hidden');
    $('#exam-runner').classList.remove('hidden');
    renderExam();
  } catch (err) { toast(err.message, 'error'); }
}

function renderExam() {
  const { questions, deadline } = APP.exam;
  $('#exam-runner').innerHTML = `<div class="card">
    <div class="exam-bar">
      <b>Examen blanc — ${questions.length} questions</b>
      <span class="grow"></span>
      ${deadline ? '<span class="timer" id="exam-timer-display">--:--</span>' : ''}
      <button class="btn small ghost" id="btn-abort-exam">Abandonner</button>
    </div>
    <form id="exam-form">${questions.map((question, index) => `
      <div class="exam-q" data-q="${index}">
        <div class="num">Question ${index + 1} · ${question.type === 'qcm' ? 'QCM' : 'question ouverte'}${question.course_title ? ' · ' + esc(question.course_title) : ''}</div>
        <div class="q-text" style="font-size:1rem">${esc(question.question)}</div>
        ${question.type === 'qcm'
          ? `<div class="choices">${question.choices.map((choice, choiceIndex) => `
              <label class="choice"><input type="radio" name="q${index}" value="${choiceIndex}" style="width:auto">
              <span class="key">${'ABCDEFGH'[choiceIndex]}</span><span>${esc(choice)}</span></label>`).join('')}</div>`
          : `<textarea name="q${index}" rows="3" placeholder="Ta réponse…"></textarea>`}
      </div>`).join('')}
    </form>
    <button class="btn primary" id="btn-submit-exam">Rendre la copie</button>
  </div>`;
  $('#btn-submit-exam').onclick = submitExam;
  $('#btn-abort-exam').onclick = () => {
    if (!confirm('Abandonner l\'examen en cours ?')) return;
    stopTimer();
    APP.exam = null;
    $('#exam-runner').classList.add('hidden');
    $('#exam-setup').classList.remove('hidden');
  };
  if (deadline) startTimer();
}

let timerHandle = null;
function startTimer() {
  stopTimer();
  const tick = () => {
    if (!APP.exam) return stopTimer();
    const left = Math.max(0, APP.exam.deadline - Date.now());
    const display = $('#exam-timer-display');
    if (display) {
      const minutes = String(Math.floor(left / 60000)).padStart(2, '0');
      const seconds = String(Math.floor((left % 60000) / 1000)).padStart(2, '0');
      display.textContent = `${minutes}:${seconds}`;
      display.classList.toggle('low', left < 120000);
    }
    if (left <= 0) { stopTimer(); toast('Temps écoulé — copie rendue', 'error'); submitExam(); }
  };
  tick();
  timerHandle = setInterval(tick, 1000);
}
function stopTimer() { if (timerHandle) clearInterval(timerHandle); timerHandle = null; }

async function submitExam() {
  const exam = APP.exam;
  if (!exam || exam.submitted) return;
  exam.submitted = true;
  stopTimer();
  const form = $('#exam-form');
  const button = $('#btn-submit-exam');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Correction…';

  const results = [];
  const gradings = [];
  exam.questions.forEach((question, index) => {
    const field = form.elements[`q${index}`];
    if (question.type === 'qcm') {
      const chosen = field && field.value !== '' ? Number(form.querySelector(`input[name="q${index}"]:checked`)?.value ?? -1) : -1;
      const correct = chosen === question.correct;
      results[index] = {
        question, given: chosen >= 0 ? question.choices[chosen] : '(sans réponse)',
        expected: question.choices[question.correct],
        note: correct ? 100 : 0, verdict: correct ? 'juste' : 'faux', commentaire: '',
      };
    } else {
      const given = (field?.value || '').trim();
      results[index] = { question, given: given || '(sans réponse)', expected: question.answer, note: null, verdict: null, commentaire: '' };
      if (exam.aiGrading && given) {
        gradings.push(api('/api/grade', { method: 'POST', body: { question: question.question, expected: question.answer, given } })
          .then((grade) => Object.assign(results[index], {
            note: Number(grade.note) || 0,
            verdict: grade.verdict || 'partiel',
            commentaire: grade.commentaire || '',
            manquants: grade.manquants || [],
          }))
          .catch(() => Object.assign(results[index], { note: null, verdict: 'à auto-évaluer', commentaire: 'Correction IA indisponible.' })));
      } else if (!given) {
        Object.assign(results[index], { note: 0, verdict: 'faux' });
      } else {
        Object.assign(results[index], { verdict: 'à auto-évaluer' });
      }
    }
  });
  await Promise.all(gradings);

  const graded = results.filter((result) => typeof result.note === 'number');
  const score = graded.length ? Math.round(graded.reduce((sum, result) => sum + result.note, 0) / graded.length) : 0;

  // Répercussion sur la répétition espacée.
  for (const result of results) {
    if (typeof result.note !== 'number') continue;
    const grade = result.note >= 85 ? 'good' : result.note >= 50 ? 'hard' : 'again';
    api('/api/review', { method: 'POST', body: { card_id: result.question.id, grade } }).catch(() => {});
  }

  $('#exam-runner').innerHTML = `<div class="card session-done">
      <div class="score">${score}<span style="font-size:1rem">/100</span></div>
      <p class="muted">${graded.length} question(s) notée(s) sur ${results.length} · ${Math.round((Date.now() - exam.startedAt) / 60000)} min</p>
      <div class="row" style="justify-content:center">
        <button class="btn primary" id="btn-new-exam">Nouvel examen</button>
        <button class="btn ghost" data-goto="today">Tableau de bord</button>
      </div>
    </div>
    <div class="card"><h2>Correction détaillée</h2>
      ${results.map((result, index) => `
        <div class="exam-q">
          <div class="num">Question ${index + 1}
            ${result.verdict ? `<span class="verdict ${['juste', 'partiel', 'faux'].includes(result.verdict) ? result.verdict : ''}">${esc(String(result.verdict))}${typeof result.note === 'number' ? ` ${result.note}/100` : ''}</span>` : ''}</div>
          <div class="q-text" style="font-size:1rem">${esc(result.question.question)}</div>
          <p class="small"><b>Ta réponse :</b> ${esc(result.given)}</p>
          <p class="small"><b>Attendu :</b> ${esc(result.expected)}</p>
          ${result.commentaire ? `<p class="small muted">${esc(result.commentaire)}</p>` : ''}
          ${result.manquants && result.manquants.length ? `<p class="small muted">Manquant : ${result.manquants.map(esc).join(', ')}</p>` : ''}
        </div>`).join('')}
    </div>`;
  $('#btn-new-exam').onclick = () => {
    APP.exam = null;
    $('#exam-runner').classList.add('hidden');
    $('#exam-setup').classList.remove('hidden');
  };
  refresh();
}

/* -------------------------------------------------------------- Stats */
async function loadStats() {
  try { APP.stats = await api('/api/stats'); } catch (err) { toast(err.message, 'error'); return; }
  const stats = APP.stats;
  $('#stat-tiles').innerHTML = [
    ['Cartes', stats.cards], ['Cours', stats.courses], ['Révisions', stats.reviews],
    ['Réussite', `${stats.accuracy}%`], ['Série', `${stats.streak} j`],
    ['Matures', stats.maturity.mature || 0],
  ].map(([label, value]) => `<div class="tile"><b>${value}</b><small>${label}</small></div>`).join('');

  const max = Math.max(1, ...stats.heatmap.map((day) => day.count));
  $('#heatmap').innerHTML = stats.heatmap.map((day) => {
    const level = day.count === 0 ? 0 : Math.min(4, Math.ceil(4 * day.count / max));
    return `<i class="l${level}" title="${day.date} : ${day.count} révisions"></i>`;
  }).join('');

  const peak = Math.max(1, ...stats.forecast.map((entry) => entry.count));
  $('#forecast').innerHTML = stats.forecast.map((entry) => `
    <div class="bar" style="height:${Math.max(2, Math.round(100 * entry.count / peak))}%" title="${entry.count} cartes">
      ${entry.day % 2 === 0 ? `<span>${entry.day === 0 ? 'auj.' : `+${entry.day}`}</span>` : ''}
    </div>`).join('');

  const subjects = Object.entries(stats.per_subject);
  $('#per-subject').innerHTML = subjects.length ? subjects.map(([name, bucket]) => `
    <div class="subject-row">
      <span class="name" title="${esc(name)}">${esc(name)}</span>
      <span class="track"><i style="width:${bucket.cards ? Math.round(100 * bucket.mature / bucket.cards) : 0}%"></i></span>
      <span class="muted small">${bucket.mature}/${bucket.cards}${bucket.due ? ` · ${bucket.due} dues` : ''}</span>
    </div>`).join('') : '<p class="muted">Pas encore de données.</p>';
}

/* ----------------------------------------------------------- Réglages */
function renderSettings() {
  const settings = APP.state.settings;
  $('#set-model').value = settings.model;
  $('#set-goal').value = settings.daily_goal;
  $('#set-flash').value = settings.flashcards_per_generation;
  $('#set-qcm').value = settings.qcm_per_generation;
  $('#ai-status').textContent = APP.state.ai_available
    ? `✅ Clé détectée — génération, transcription et correction actives (${APP.state.model}).`
    : '⚠️ Aucune clé ANTHROPIC_API_KEY : import de texte et révision fonctionnent, la génération passe en mode heuristique hors-ligne.';
}

async function saveSettings() {
  try {
    await api('/api/settings', {
      method: 'PUT',
      body: {
        model: $('#set-model').value,
        daily_goal: Number($('#set-goal').value),
        flashcards_per_generation: Number($('#set-flash').value),
        qcm_per_generation: Number($('#set-qcm').value),
      },
    });
    toast('Réglages enregistrés', 'ok');
    refresh();
  } catch (err) { toast(err.message, 'error'); }
}

/* -------------------------------------------------------------- Thème */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('revision-theme', theme);
}

/* --------------------------------------------------------------- Init */
function bind() {
  $('#tabs').onclick = (event) => { if (event.target.dataset.view) go(event.target.dataset.view); };
  document.body.addEventListener('click', (event) => {
    const target = event.target.closest('[data-goto]');
    if (target) go(target.dataset.goto);
    const course = event.target.closest('[data-course]');
    if (course && course.dataset.course && !event.target.dataset.cardAction) {
      if (course.classList.contains('mini-course') || course.classList.contains('course-row')) openCourse(course.dataset.course);
    }
  });

  $('#missions').addEventListener('click', (event) => {
    const item = event.target.closest('li');
    if (!item || !item.dataset.action) return;
    if (item.dataset.action === 'review') runSession({ scope: 'due', course_id: item.dataset.course || '' });
    if (item.dataset.action === 'generate' && item.dataset.course) openCourse(item.dataset.course);
    if (item.dataset.action === 'exam') { go('exam'); if (item.dataset.course) $('#exam-course').value = item.dataset.course; }
  });

  $('#btn-start-due').onclick = () => runSession({ scope: 'due', course_id: '' });
  $('#btn-quick-quiz').onclick = () => runSession({ scope: 'all', type: 'qcm', limit: 10, course_id: '' });
  $('#btn-run-session').onclick = () => runSession();
  $('#btn-run-exam').onclick = runExam;
  $('#btn-save-settings').onclick = saveSettings;
  $('#course-search').oninput = renderCourses;
  $('#btn-export').onclick = async () => {
    const data = await api('/api/export');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `revisions-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Import
  const dropzone = $('#dropzone');
  ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (event) => {
    event.preventDefault(); dropzone.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, () => dropzone.classList.remove('over')));
  dropzone.addEventListener('drop', (event) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) importFiles([...event.dataTransfer.files]);
  });
  $('#file-input').onchange = (event) => { if (event.target.files.length) importFiles([...event.target.files]); event.target.value = ''; };
  $('#btn-paste-course').onclick = () => { $('#paste-pane').classList.remove('hidden'); $('#paste-text').focus(); };
  $('#btn-cancel-paste').onclick = () => $('#paste-pane').classList.add('hidden');
  $('#btn-save-paste').onclick = async () => {
    const text = $('#paste-text').value.trim();
    if (!text) return toast('Colle d\'abord le contenu du cours', 'error');
    try {
      const result = await api('/api/courses', {
        method: 'POST',
        body: { text, title: $('#paste-title').value.trim(), subject: $('#paste-subject').value.trim() },
      });
      $('#paste-text').value = ''; $('#paste-title').value = ''; $('#paste-subject').value = '';
      $('#paste-pane').classList.add('hidden');
      await refresh();
      openCourse(result.course.id);
    } catch (err) { toast(err.message, 'error'); }
  };

  // Thème
  applyTheme(localStorage.getItem('revision-theme') || 'auto');
  $('#theme-toggle').onclick = () => {
    const order = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(document.documentElement.dataset.theme) + 1) % order.length];
    applyTheme(next);
    toast(`Thème : ${next}`);
  };

  // Raccourcis clavier de session
  document.addEventListener('keydown', (event) => {
    if (!APP.session || APP.view !== 'review') return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;
    const card = APP.session.queue[0];
    if (!card) return;
    if (event.code === 'Space' || event.key === 'Enter') {
      event.preventDefault();
      if (!APP.session.revealed && card.type === 'flashcard') reveal();
      else if (APP.session.revealed) submitGrade('good');
      return;
    }
    if (!APP.session.revealed && card.type === 'qcm' && /^[a-d]$/i.test(event.key)) {
      const index = event.key.toLowerCase().charCodeAt(0) - 97;
      if (index < card.choices.length) pickChoice(index);
      return;
    }
    if (APP.session.revealed && ['1', '2', '3', '4'].includes(event.key)) {
      submitGrade(['again', 'hard', 'good', 'easy'][Number(event.key) - 1]);
    }
  });
}

bind();
refresh().catch((err) => toast(`Serveur injoignable : ${err.message}`, 'error'));
