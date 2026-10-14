# UI · Lika brand — prijedlog 1

Snimke iz `scripts/browser_check.py` (pravi bundle, simulator ormara, Chromium),
pokrenut sa `SCREENSHOT_DIR=docs/ui/prijedlog-1`. Za svaki zaslon: svijetla i tamna
tema, desktop 1280 px i mobitel 360 px.

| Zaslon | Datoteke |
|---|---|
| Prijava | `1-login-*` |
| Prijava, korak 2FA | `2-login-2fa-*` |
| Vezovi | `3-berths-*` |
| Sigurnost (D21) | `4-security-*` |

## Izvor u UI-ju ormara

Repo `Lika-Digital/Cloud_IOT`, commit `e80a4c1e8c24b8d358ee182039f0d0b88bc0f564` (main),
samo čitanje:

| Datoteka ormara | Što je preuzeto |
|---|---|
| `frontend/src/assets/logo.png` | logo (smanjen na 480 px → `frontend/src/assets/lika-logo.png`); boje uzorkovane iz piksela: lime `#C4FF61`, tinta `#2B2A29`; znak (točkice) izmjeren i nacrtan kao SVG → `frontend/public/lika-mark.svg` (favicon) |
| `frontend/src/index.css` | tamna i svijetla tema preko CSS varijabli na `<html>`; kartica `rounded-xl` + 1 px obrub; gumbi `rounded-lg`; sustavski font |
| `frontend/tailwind.config.js` | boje kao `rgb(var(--x) / <alpha-value>)`, da jedna klasa na `<html>` mijenja temu |
| `frontend/src/components/layout/Layout.tsx` | bočna traka `w-56`/`w-60` s logom gore i korisnikom dolje; na mobitelu ladica iza hamburgera; prekidač teme |
| `frontend/index.html` | tema postavljena prije prvog iscrtavanja (kod nas iz vanjske datoteke, ne inline) |

Ormar sam koristi plavu (`brand-600`) za gumbe; ERP umjesto nje nosi boje loga
(lime + tinta), pa je Lika vidljiva i bez loga.
