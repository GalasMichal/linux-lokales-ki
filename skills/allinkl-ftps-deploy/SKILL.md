---
name: allinkl-ftps-deploy
description: >
  Deploy static sites to All-Inkl via FTPS. Use for Portfolio (michal-galas.de), GitHub Actions
  deploy-allinkl.yml, FTP secrets, or All-Inkl hosting questions.
---

# All-Inkl FTPS Deploy

## Portfolio workflow

- Workflow: `.github/workflows/deploy-allinkl.yml`
- Trigger: push to `main` or `workflow_dispatch`
- Build: `npm run build` → `dist/portfolio/`
- Upload: FTPS to remote dir from secrets

## Required GitHub secrets

- `FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`, `FTP_REMOTE_DIR`

## Optional vars

- `BASE_HREF` (default `/`)
- `SITE_URL` (default `https://michal-galas.de`)

## Agent constraints

- Never commit FTP credentials
- Don't change deploy workflow without user request
- Verify `outputPath` in `angular.json` matches workflow upload path
- SPA: ensure `.htaccess` or server rewrite for Angular routes if needed in `public/`

## Local test before deploy

```bash
npm run build
npx serve dist/portfolio/browser
```

Adjust path if Angular 21 outputs to `dist/portfolio/browser`.
