# 🐸 Work Hub

Personal to-do board + project tracker tabs + "Brag Book" of what you finished (for standup).
Runs locally. Python 3 standard library only, nothing to install.

## Start it
```
python server.py
```
Opens http://127.0.0.1:8765 in your browser. `Ctrl+C` to stop.
Options: `python server.py 9000 --no-browser` (different port, don't open a browser).

## Files
| File | What |
|---|---|
| `todos.md` | All your to-dos. Safe to hand-edit (the app re-reads it when you switch back to the tab). `todos.md.bak` is the previous version. |
| `trackers/*.html` | Your project trackers. Each one gets its own tab. Click 🔄 next to the tabs after adding a file. |
| `index.html` | The app. |
| `server.py` | Tiny local server (only listens on 127.0.0.1). |

## Using it
- **Add**: type in the notepad, then click a category pill. `Enter` adds to the last-used category. Paste several lines to add several items. Press `/` anywhere to jump to the box.
- **Urgent**: tick "⭐ urgent!" before adding, or click the star on any item. Starred items go to the top and appear in the 🔥 strip.
- **Edit**: double-click an item's text or a category name.
- **Categories**: add with "+ new category". Rename, reorder (↑ ↓) and remove under 🧹 *tidy categories*, or use ✎ / 🗑 on a card. When you remove a category that still has items, you can move them somewhere else or delete them.
- **Brag Book**: everything you ticked, grouped by day. The standup card shows the last working day (Friday on a Monday) plus your starred to-dos. **📋 Copy for standup** puts it on the clipboard.

## Project tabs
Each tracker is shown as the full page, exactly as in a normal browser tab: tables, CSS, and chart scripts (Chart.js, Plotly, etc.) all run.
- Tabs open full width. **Show quick add** brings the sidebar back (remembered).
- **Open ↗** opens the tracker in its own browser tab; **Reload** refreshes it after you edit the file.
- If a tracker uses local files (images, `.js`, `.css`), keep them next to it inside `trackers/` (subfolders are fine) with the same relative paths.
- Charts loaded from a CDN need internet access, same as opening the file directly.

## Pulling to-dos from trackers
On load (and with 🎣) the hub reads every tracker and adds new items. It never changes the tracker files.
Mark to-dos in a tracker in any of these ways (see `trackers/example-project.html`):

```html
<ul class="todo">                      <!-- every <li> in a .todo / .todos list -->
  <li>Draft the kickoff deck</li>
  <li>⭐ Chase sign-off</li>           <!-- leading ⭐ or ! = urgent -->
  <li class="done">Already done</li>   <!-- skipped -->
</ul>

<p data-todo>Book research sessions</p>
<p data-todo="Short text" data-urgent>Long description…</p>
<p data-todo data-category="Admin">Goes into Admin</p>

<label><input type="checkbox"> Update the risk register</label>   <!-- unchecked boxes -->

<tr><td data-todo>Confirm launch date</td><td>Me</td><td>30 Oct</td></tr>   <!-- tables: tag the task cell -->
<tr><td data-todo data-done>Agree metrics</td>…</tr>                         <!-- data-done = skip -->
```
Text inside `<script>` / `<style>` (e.g. chart data) is never pulled.

- Items land in a category named after the tracker file (`project-alpha.html` → "Project Alpha"), unless `data-category` says otherwise.
- Deleting or editing a pulled item stops it being pulled again.
- If you delete a whole category, its pulled items come back on the next pull.

## Moving to another machine
Copy the whole `work-hub` folder. Needs Python 3 (`python --version`).

## Tests
`python -m unittest test_server`
