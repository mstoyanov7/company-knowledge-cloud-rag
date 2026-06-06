# OneNote Automotive Software Content Pack

Generated pages: 105

## Strategy

1. Create one OneNote section for each folder name, using the section name after the numeric prefix.
2. Create one OneNote page for each HTML file. Use the H1 title as the OneNote page title.
3. Keep one page focused on one real internal topic. Do not merge unrelated processes into one page.
4. Keep page titles clear and specific because the title is the strongest signal during retrieval.
5. Keep commands in code blocks and do not merge multiple commands into one paragraph.
6. Vary the page layout so sections look maintained by different teams while staying clear.
7. For project inventory, only pages in the Projects Setups section should be considered project setup pages.

## Writing Rules

- Write like normal internal company documentation.
- Use natural headings and process wording that a real team would maintain.
- Mix paragraphs, tables, short lists, and command blocks instead of making every page a checklist.
- Prefer concrete owner teams, systems, artifacts, and completion checks.
- Avoid repeated filler. Each page should contain details that are unique to that page.
- Keep setup commands as separate lines in code blocks. Project setup pages include Linux and Windows paths where useful.

## Copy Into OneNote

Open an HTML file in a browser, select the rendered page content, copy it, and paste it into a new OneNote page.
Do not paste the raw HTML source unless you intentionally want source code visible in OneNote.

After import, run a OneNote bootstrap reindex so the app sees the new pages:

```powershell
docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_bootstrap
```
