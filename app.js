const $ = (selector) => document.querySelector(selector);
const catalogueUrl = new URL("processed/catalogue.json", document.baseURI);
const state = { books: [], activeBook: null, pages: [], chapters: [], pageIndex: 0, matches: [], matchIndex: -1 };

const disciplineNames = { ayurveda: "Ayurveda", homeopathy: "Homeopathy", unani: "Unani", general: "General" };
const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const formatNumber = (value) => new Intl.NumberFormat().format(value || 0);

function renderCatalogue() {
  const query = $("#catalog-search").value.trim().toLocaleLowerCase();
  const discipline = $("#discipline-filter").value;
  const books = state.books.filter((book) => {
    const searchable = [book.title, book.author, book.translator, book.discipline, book.language, book.volume].filter(Boolean).join(" ").toLocaleLowerCase();
    return (discipline === "all" || book.discipline === discipline) && searchable.includes(query);
  });
  $("#result-count").textContent = `${books.length} ${books.length === 1 ? "BOOK" : "BOOKS"}`;
  $("#book-list").innerHTML = books.length ? books.map((book) => `<button class="book-card" type="button" data-book="${escapeHtml(book.id)}">
    <span class="tag-row"><span class="tag">${escapeHtml(disciplineNames[book.discipline] || book.discipline)}</span><span class="language">${escapeHtml(book.language || "")}</span></span>
    <h2>${escapeHtml(book.title)}</h2><span class="author">${escapeHtml([book.author, book.translator && `trans. ${book.translator}`].filter(Boolean).join(" · "))}</span>
    <span class="card-bottom"><span>${book.year ? `${escapeHtml(book.year)} · ` : ""}${formatNumber(book.page_count)} PAGES</span><span class="open-mark">↗</span></span>
  </button>`).join("") : `<div class="empty-state">No books match that search. Try a different title or tradition.</div>`;
}

async function loadBook(id) {
  const book = state.books.find((item) => item.id === id);
  if (!book) return;
  $("#reader").hidden = false;
  $("#reader-title").textContent = book.title;
  $("#reader-kicker").textContent = `${disciplineNames[book.discipline] || book.discipline} · ${book.language || ""}`;
  $("#reader-byline").textContent = [book.author, book.translator && `Translated by ${book.translator}`, book.year, book.volume].filter(Boolean).join(" · ");
  $("#download-link").href = book.processed_epub;
  $("#reader-note").hidden = true;
  $("#page-text").textContent = "Loading book text…";
  $("#chapter-list").hidden = true;
  $("#text-search").value = "";
  $("#search-status").textContent = "";
  $("#library").hidden = true;
  state.activeBook = book;
  history.replaceState(null, "", `#book/${encodeURIComponent(id)}`);
  $("#reader").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const response = await fetch(new URL(book.processed_json, document.baseURI));
    if (!response.ok) throw new Error(`Could not load this book (${response.status}).`);
    const data = await response.json();
    state.pages = data.pages || [];
    state.chapters = data.chapters || [];
    state.pageIndex = 0;
    state.matches = [];
    state.matchIndex = -1;
    $("#page-number").max = state.pages.length;
    $("#page-total").textContent = `of ${formatNumber(state.pages.length)}`;
    const note = data.note || "";
    $("#reader-note").textContent = note;
    $("#reader-note").hidden = !note;
    renderChapters();
    renderPage();
  } catch (error) {
    $("#page-text").textContent = `${error.message} Check that the site is being served over HTTP and the book data is available.`;
  }
}

function renderChapters() {
  const panel = $("#chapter-list");
  panel.hidden = !state.chapters.length;
  $("#chapter-links").innerHTML = state.chapters.map((chapter, index) => `<button class="chapter-link" type="button" data-chapter="${index}">${escapeHtml(chapter.label)}${chapter.title ? ` · ${escapeHtml(chapter.title)}` : ""}</button>`).join("");
}

function renderPage() {
  const page = state.pages[state.pageIndex];
  if (!page) return;
  const displayNumber = page.page_number ?? (state.pageIndex + 1);
  $("#page-number").value = displayNumber;
  $("#page-meta").textContent = [page.label, `PAGE ${displayNumber}`, `TEXT PAGE ${state.pageIndex + 1} OF ${state.pages.length}`].filter(Boolean).join(" · ");
  $("#page-text").textContent = page.text || "[No text was recovered for this page.]";
  $("#page-position").textContent = `${state.pageIndex + 1} / ${state.pages.length}`;
  $("#previous-page").disabled = state.pageIndex <= 0;
  $("#next-page").disabled = state.pageIndex >= state.pages.length - 1;
}

function changePage(index) {
  state.pageIndex = Math.max(0, Math.min(state.pages.length - 1, index));
  renderPage();
}

function searchInBook() {
  const query = $("#text-search").value.trim().toLocaleLowerCase();
  if (!query) {
    state.matches = [];
    state.matchIndex = -1;
    $("#search-status").textContent = "";
    return;
  }
  state.matches = [];
  for (let i = 0; i < state.pages.length; i++) if ((state.pages[i].text || "").toLocaleLowerCase().includes(query)) state.matches.push(i);
  state.matchIndex = state.matches.length ? 0 : -1;
  $("#search-status").textContent = state.matches.length ? `${state.matches.length} matching pages` : "No matches";
  if (state.matchIndex >= 0) changePage(state.matches[0]);
}

async function start() {
  $("#footer-year").textContent = new Date().getFullYear();
  try {
    const response = await fetch(catalogueUrl);
    if (!response.ok) throw new Error("Catalogue unavailable");
    state.books = await response.json();
    const disciplines = [...new Set(state.books.map((book) => book.discipline))].sort();
    $("#discipline-filter").insertAdjacentHTML("beforeend", disciplines.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(disciplineNames[item] || item)}</option>`).join(""));
    const pages = state.books.reduce((total, book) => total + (book.page_count || 0), 0);
    $("#stats").innerHTML = `<span><strong>${state.books.length}</strong> BOOKS</span><span><strong>${formatNumber(pages)}</strong> PAGES</span><span><strong>${disciplines.length}</strong> TRADITIONS</span>`;
    renderCatalogue();
    const hashMatch = location.hash.match(/^#book\/(.+)$/);
    if (hashMatch) loadBook(decodeURIComponent(hashMatch[1]));
  } catch {
    $("#result-count").textContent = "Catalogue unavailable";
    $("#book-list").innerHTML = `<div class="empty-state">The catalogue could not load. Open this page from GitHub Pages or a local web server; browsers block data files when the page is opened directly from disk.</div>`;
  }
}

$("#catalog-search").addEventListener("input", renderCatalogue);
$("#discipline-filter").addEventListener("change", renderCatalogue);
$("#book-list").addEventListener("click", (event) => { const card = event.target.closest("[data-book]"); if (card) loadBook(card.dataset.book); });
$("#back-button").addEventListener("click", () => { $("#reader").hidden = true; $("#library").hidden = false; history.replaceState(null, "", "#library"); window.scrollTo({ top: $("#library").offsetTop - 20, behavior: "smooth" }); });
$("#previous-page").addEventListener("click", () => changePage(state.pageIndex - 1));
$("#next-page").addEventListener("click", () => changePage(state.pageIndex + 1));
$("#page-number").addEventListener("change", (event) => { const wanted = Number(event.target.value); let index = state.pages.findIndex((page, i) => (page.page_number ?? i + 1) === wanted); if (index < 0) index = Math.max(0, Math.min(state.pages.length - 1, wanted - 1)); changePage(index); });
let searchTimer;
$("#text-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(searchInBook, 180); });
$("#chapter-links").addEventListener("click", (event) => { const button = event.target.closest("[data-chapter]"); if (!button) return; const startPage = Number(state.chapters[Number(button.dataset.chapter)].start_page); const index = state.pages.findIndex((page, i) => (page.page_number ?? i + 1) >= startPage); if (index >= 0) changePage(index); });
start();
