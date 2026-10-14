// Theme before first paint (no flash): the saved choice, else the system preference.
// External file, not inline, so a strict Content-Security-Policy can stay strict.
(function () {
  var t = null
  try { t = localStorage.getItem('erp-theme') } catch (e) { /* private mode */ }
  if (t !== 'light' && t !== 'dark') {
    t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  document.documentElement.classList.add(t)
})()
