# CWR-CE build index

Static page listing CI builds of [CWR-CE](https://github.com/ofpisnotdead-com/CWR-CE),
with download links served by [nightly.link](https://nightly.link). Regenerated
hourly by GitHub Actions and published to GitHub Pages.

`generate.py` queries the public Actions API and writes `_site/index.html`.
No secrets; reads only public data.
