# Connecting the router to the portal: what changed

The portal already ran the router when a complaint was registered, but it kept only a few numbers and threw away
the router's message and its escalation timeline. Now it keeps both, shows the message as soon as the complaint is
registered, and shows the timeline as the complaint's progress.

| File | Change |
|---|---|
| `complaint_tools/complaintrouter/pipeline.py` | `run_complaint` takes an optional `reference` (the complaint ID) so the router's message names the real complaint. Left out, it behaves exactly as before. |
| `complaint_tools/complaint_portal/router_link.py` | **New.** Keeps the router's timeline (`snapshot`) and turns it into progress steps (`progress`). |
| `complaint_tools/complaint_portal/store.py` | Two new columns, `router_message` and `router_timeline`, added to older databases automatically. |
| `complaint_tools/complaint_portal/workflow.py` | `register` picks the complaint ID first, passes it to the router, and stores the message and timeline. `_public` returns `router_message` and `router_progress`. |
| `portal/assets/portal.js`, `portal.css` | Shared `Portal.routerMessage` and `Portal.routerProgress` and their styles. |
| `portal/register.html` | The empty "From the agents" box now shows the router's message; a "Time limits for your complaint" list is added. |
| `portal/track.html` | A "Time limits from the router" list and a "Message from the complaint router" section. |
| `flutter_app/lib/widgets/router_panels.dart` | **New.** `RouterMessage` and `RouterProgress` widgets. |
| `flutter_app/lib/screens/register_complaint_screen.dart`, `track_complaint_screen.dart` | Use the two widgets in the same places as the web pages. |
| `tests/test_router_link.py`, `tests/js/router_screens.e2e.test.js`, `flutter_app/test/router_panels_test.dart` | **New** tests. |
| `README.md` | Documents the connection; corrects the test count. |

Nothing was removed. No database column was changed or dropped. The router files `intake.py`, `router.py`, `escalation.py`,
`charter_lookup.py`, `reply.py` and `data/charter.json` are untouched.

After pulling these changes, rebuild the Flutter web app (`flutter build web --base-href /app/`) so `/app/` shows them.
