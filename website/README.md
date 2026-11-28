# zenmetrics.vyaca.com

The ZenMetrics website: one static page, no build step, no tracking. It uses the app's own design
system (palette, Google Sans Flex, cards, buttons) in light and dark.

```
index.html             the page
assets/site.css        styles — the app's palette and components (app/src/styles.css)
assets/site.js         GitHub release + stars, star prompt, live countdown, tabs, theme
assets/img/            screenshots (from docs/images), logo, social card, touch icon
robots.txt, sitemap.xml
```

Typeface: **Google Sans Flex**, loaded from Google Fonts.

## Preview

```bash
python3 -m http.server 4173 --directory website     # from the repo root → http://localhost:4173
```

## Downloads go through GitHub

Every download button opens the **latest release on GitHub** in a new tab — the site never links to
an installer directly — and shows a short prompt that names the right file for the visitor's system
and asks for a ⭐ star (stars help other TeamLogger users find the project). File names and the
version are read live from the GitHub API, so publishing a release updates the site with no edit.
The star count appears next to the star buttons once the repo has at least 5 stars.

## Hosting: GitHub Pages → zenmetrics.vyaca.com

`.github/workflows/pages.yml` publishes this folder (minus this README) on every push to `main`
that touches `website/`, or by hand from the Actions tab.

One-time setup (needs admin on the repo and access to the vyaca.com DNS at Hostinger):

1. **GitHub → Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Hostinger → Domains → vyaca.com → DNS / Nameservers → add a record:**
   `CNAME` · name `zenmetrics` · target `vyaca-corp.github.io` · TTL default.
3. **GitHub → Settings → Pages → Custom domain:** `zenmetrics.vyaca.com` → Save. Wait for the DNS
   check to pass, then tick **Enforce HTTPS** (the certificate can take up to an hour).
4. Recommended: verify `vyaca.com` for the organisation (org Settings → Pages → Add a domain) so no
   one else can claim the subdomain.

## Before launch

- Check the social preview (`assets/img/og.png`) and screenshots still match the current app
  (see `docs/images/`).
