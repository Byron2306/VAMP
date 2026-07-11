# VAMP Landing Page

A static, responsive homepage prototype for **VAMP — Virtual Academic Management Partner**.

## What is included

- `index.html` — single-page homepage
- `assets/css/styles.css` — full gothic SaaS styling
- `assets/js/main.js` — mobile menu, demo modal, scroll reveal
- `assets/images/` — VAMP icon and optimized screenshot previews
- `assets/video/vamp-promo-web.mp4` — compressed web-friendly demo video

## How to preview locally

Open `index.html` directly in your browser, or run a simple local server:

```bash
cd vamp-landing-page
python3 -m http.server 8080
```

Then visit:

```text
http://localhost:8080
```

## What to change before public launch

1. Replace the mail link in `index.html` with a form endpoint when you are ready to automate access requests.
2. Replace screenshot previews with public-safe demo screenshots if needed.
3. Confirm which university logos/branding may legally appear on a commercial/public site.
4. Add a proper privacy policy, licence/EULA, and terms page.
5. Wire the Download section to a real gated flow later, e.g. Stripe/Lemon Squeezy + Supabase + private storage.

## Deployment options

This is plain static HTML/CSS/JS, so it can be deployed on:

- GitHub Pages
- Netlify
- Vercel
- Cloudflare Pages
- Any basic web server

## Suggested next build phase

Create these pages next:

- `/features.html`
- `/use-cases.html`
- `/pricing.html`
- `/download.html`
- `/privacy.html`
- `/terms.html`

For the pay-gated installer, avoid putting the installer in a public folder. Use authenticated, expiring signed download links.
