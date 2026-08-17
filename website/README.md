# Website deployment

The MAID Runner website is a dependency-free static site deployed by Vercel.
Its only indexable public URL is `https://maidrunner.dev/`.

## Vercel project settings

Keep the Vercel project connected to this repository with these settings:

- Framework Preset: Other
- Root Directory: repository root (`.`)
- Build Command: empty
- Output Directory: `"website"`, declared in [`../vercel.json`](../vercel.json)
- Primary production domain: `https://maidrunner.dev/`
- Redirect domain: `www.maidrunner.dev` redirects permanently to
  `https://maidrunner.dev/`

Vercel also redirects HTTP requests to HTTPS. The expected public behavior is:

| Request | Expected result |
| --- | --- |
| `https://maidrunner.dev/` | `200` and indexable |
| `http://maidrunner.dev/` | permanent `308` redirect to the canonical URL |
| `https://www.maidrunner.dev/` | permanent `308` redirect to the canonical URL |
| `http://www.maidrunner.dev/` | permanent redirect chain ending at the canonical URL |

Configure the apex and `www` relationship in Vercel's Domains settings. Domain
redirects are deployment settings; do not duplicate them with client-side
redirects or canonicalize the apex URL to a redirecting alias.

## Google Search Console

Google Search Console reports the HTTP and `www` aliases as **Page with redirect**.
That classification is intentional: redirecting URLs are excluded while the
final HTTPS apex page is indexed. Do not request indexing or "Validate fix" for
those aliases.

When investigating a report, confirm that the affected URL redirects to
`https://maidrunner.dev/`, then inspect the final URL instead. The homepage
canonical tag, `robots.txt` sitemap declaration, and every sitemap location
must continue to use the final HTTPS apex URL.

## Retired GitHub Pages automation

The repository no longer declares GitHub Pages as a production or fallback
publisher. Do not restore `.github/workflows/deploy-website.yml`; running
Vercel and GitHub Pages in parallel creates a stale second deployment surface
and obscures which host is canonical.

Deleting the workflow does not disable GitHub Pages at the repository level.
Before release, confirm Pages is disabled under **Settings → Pages**. This
repository configuration can prevent future workflow deployments, but it
cannot enforce that external setting.
