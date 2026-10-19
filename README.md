# Chennai Kural — Your Voice. A Better Chennai. (unofficial demo)

A complaint portal for Chennai water and sewer complaints. Citizens file a complaint and it is sorted into a field (water supply, sewerage, billing, new connections, general). It goes to the owning depot officer. A field worker can accept it and fix it, and closes it only with a code sent to the citizen's mobile. Otherwise the officer marks it resolved, and the citizen confirms whether the problem is gone. If the citizen says it is not fixed, or the charter's time limit at the current level passes, the complaint moves up to the next officer. The last level is the District Head Office.

This project is not affiliated with CMWSSB. Nothing it produces is an official CMWSSB reply, notice or decision.

## Quick start for judges

Submission for the Cognizant AI Lab x IIIT Raichur Agentic AI Hackathon 2026. Unofficial demo, not affiliated with CMWSSB. The project is called Chennai Kural; the demo pages are deliberately branded "Chennai Complaint Portal", with no official-looking name or government footer (a test enforces this).
Read `architecture.md` first (how it works and where the agents are), then `summary.md` (one-page summary and measured results).

You need Python 3.12 or 3.13 (tested on 3.12; the Dockerfile uses 3.13). The portal and the tests need no model and no internet.

```
python -m pip install -r requirements.txt
python -m pytest -q tests
python portal/manage.py seed-demo --password "a-long-password"
python portal/server.py
```

Then open http://127.0.0.1:8000. Use only invented names and numbers in the demo. For a live demo of time limits and escalation, start the portal with `python portal/server.py --demo-minutes 2`.

## Run the Neuro-SAN agent network

The router is also a Neuro-SAN agent network in `registries/complaintrouter.hocon`: a coordinator and five agents (intake, charter lookup, router, escalation, reply). The coordinator calls them in a fixed order.

1. Optional: copy `.env.example` to `.env` and paste your key after `GOOGLE_API_KEY=` if you use Gemini. The default model is the local Ollama llama3.1 (`ollama pull llama3.1`, and keep Ollama running). Keep `.env` private.
2. In the terminal you will use, set two environment variables. On Windows PowerShell: `$env:PYTHONPATH = "<project folder>"` and `$env:AGENT_TOOL_PATH = "complaint_tools"`. On macOS or Linux: `export PYTHONPATH="$PWD"` and `export AGENT_TOOL_PATH=complaint_tools`.
3. From the project folder run `ns validate registries/complaintrouter.hocon`. It should print "Validation passed: No errors found".
4. Run `ns run`. The server starts on port 8080 and the chat interface on port 4173. Open http://localhost:4173 and select `complaintrouter`.
5. Try a sample query, for example "Water is leaking from the pipe near my house for three days, please fix it." The coordinator calls `intake_agent`, `charter_agent`, `router_agent`, `escalation_agent` (only if days elapsed are given) and `reply_agent`, in that order.

Step 3 was run on this project. Step 4 needs a model and was not run in the build environment.

## How a complaint moves

A citizen signs up once with their name, a 10-digit mobile number, their address and their ward. The address narrows the choice to a zone, and the citizen picks their ward from that zone. After that they log in with a code sent to their mobile number, and stay logged in until they log out. Then they file a complaint with a description. A local model may help sort it (see below), and a keyword classifier is always the fallback. The complaint gets an ID such as CMP-20261015-4821 and is recorded under the citizen's ward. It is sent to the depot officer for its field and zone, and the charter timeline for the repair sets the first time limit.

The depot officer sees the complaint on their dashboard and can add notes, mark it resolved with a note, or escalate it. Marking it resolved does not close it. The citizen then sees a question: is the problem fixed? If yes, a six-digit confirmation code is shown to them, and the complaint closes when they enter it. If no, the complaint goes to the ward office straight away, and then to the District Head Office if the ward office does not fix it in time.

Field workers sign up once (the same details as a citizen, plus their department of work) and log in with a code to their mobile number. A worker sees every open complaint that no worker has taken yet, with its complaint ID, and can accept it. The citizen then sees "Allotted" and "Work in progress" on Track Complaint and on the home page. Accepted complaints move to the worker's "Allotted tasks". When the work is done, the worker presses "Mark as completed": a six-digit code goes to the citizen's mobile number, and the complaint closes only if the worker enters that code. The citizen then sees a green "Resolved". A worker can open "View complainant details" on any complaint to see what the citizen gave at sign-up (name, mobile number, address, zone and ward).

If the time limit at a level passes without a resolution, the complaint moves to the next level, and the officers get a notice. The notice shows the complaint ID, the complaint, the department and the office in charge, the citizen's details and, if a worker had accepted it, the worker's details. Notices appear on the officer dashboard by themselves. The time limits come from `data/charter.json`. The first limit is the charter's repair timeline. Each later level uses the days the charter prints for that level. The levels are Depot, Deputy Area Engineer, Area Engineer, Superintendent Engineer, and then the District Head Office. Complaints with no charter escalation go straight from the depot to the District Head Office.

## Districts, zones, and wards

Chennai is one revenue district. Greater Chennai Corporation divides the city into 15 zones, and those zones hold 200 wards numbered 1 to 200. When a citizen logs in, they give their address. The address is matched against the zone names, assembly constituency names, and taluk names in the data, which narrows the choice to a zone. The citizen then picks their ward from that zone. The data has no street or ward-level names, so an address cannot be matched to a ward by itself. The portal records the zone and ward on each complaint and shows them as "Zone, Ward" on the officer screens. Officers can be set up for one zone or for the whole city.

The data is in three files in `data/`:

- `chennai_zones.csv` has the 15 zones, their ward-number ranges, and the assembly and parliamentary constituencies and taluks each covers. The ranges come from the Tamil Nadu Government Gazette of 14 December 2021 (G.O. No. II(2)/MAWS/871(e-1)/2021). The constituency and taluk columns come from the Wikipedia article "Administrative divisions of Chennai".
- `chennai_wards.csv` has one row per ward (200 rows). The `ward_name` column is blank. None of the sources used lists the ward names, so fill them in from the Greater Chennai Corporation's ward list. Once a name is filled in, the portal shows it on the drop-down and on the officer screens.
- `cmwssb_sewer_zones.csv` lists CMWSSB's five wastewater zones and their areas. It is for reference only. The sources do not say which ward belongs to which sewer zone, so the portal does not route by it.

The portal checks the zone and ward files when it starts. It refuses to run if a ward is missing, appears twice, sits under the wrong zone, or if the zone ranges have a gap.

To give a zone its own officer, add the officer with a zone number: `python portal/manage.py add-officer --username water.depot.zone9 --name "Water depot, Teynampet zone" --field water --level depot --zone 9`. For each complaint, the portal uses the officer for that zone when one is set up, and otherwise the city-wide officer for that field and level. Escalation keeps the zone.

## Who sees what

Citizens sign up once and then log in with a code to their mobile number to file complaints and see their own complaints. A mobile number that has not signed up is told "You are new user, please sign up." The account icon at the top right shows the signed-in person's details, and its Log out button is the only one. Anyone can also track or confirm a complaint with its ID and mobile number together, without logging in. A wrong ID or number gives the same message, so nobody can look up someone else's complaint.

Workers sign up at `/worker/signup` and log in from the Worker Login tab on the first screen. A worker stays logged in until they log out. A worker sees open complaints that nobody has taken, and their own allotted tasks. Only the worker who accepted a complaint can complete it.

Officers sign up at `/officer/signup`. The sign-up waits until the District Head Office approves it with `manage.py approve-officer`, so nobody gets complaints by signing up. Officers log in from the Officer login tab on the first screen, and their login ends at midnight every day (India time). An officer sees only the complaints assigned to them. Only the assigned officer can mark a complaint resolved. The District Head Office sees every complaint and can run the time-limit check by hand.

## Pages

All pages share `portal/assets/portal.css`, `portal/assets/portal.js` and the line icons in `portal/assets/icons.svg`. Nothing is loaded from other sites, so the pages work without internet. The look follows the reference screenshots (colours, banner, login card, form layout), with neutral branding: no government emblem, no official portal name, no photo of a real person, and no government footer.

- `/` is the first screen: the banner, and the login card with three tabs of the same size: User Login (mobile number and code), Worker Login (mobile number and code) and Officer Login (username and password). Anyone still logged in goes straight to their own page.
- `/signup` (User Sign-up), `/worker/signup` (Worker Sign-up, with "Department of work") and `/officer/signup` are the sign-up forms. The strip under the banner reads Home, User Sign-up, Worker Sign-up, Officer Sign-up, Log in. The forms suggest the zone from the address; the person then picks the ward.
- `/home` is the citizen's home page: Register Complaint and Track Complaint, the common services, the citizen's own complaint numbers, how it works, and the citizen's complaints with the "is it fixed?" question. It updates every 5 seconds.
- `/register` is the complaint form. Name, mobile number and ward come from the account. The address of the problem starts as the citizen's own address and can be changed, with an optional landmark; officers and workers see both. "Your complaints" at the side lists every complaint the citizen filed, with its complaint ID and a green "Completed" or orange "Not completed", and updates by itself. After Submit, the complaint ID is shown in a green box with a "Track this complaint" button. A "From the agents" box at the side shows the router's message about the complaint, and a "Time limits for your complaint" list shows the router's timeline (see "The router's message and timeline" below).
- `/track` is Track Complaint: a search bar for the complaint ID at the top, or pick one of your complaints. It shows a four-step progress bar (Registered, Allotted, Work in progress, Resolved), a green "Resolved" at the side once the complaint is resolved, the worker, the code for the worker when one was asked for, the "is it fixed?" question, and the history. It updates every 5 seconds.
- `/worker` is the worker dashboard: "Complaints registered" and "Allotted tasks" at the side, Accept, View complainant details, Mark as completed with the citizen's code. It updates every 5 seconds and marks new complaints.
- `/officer` is the officer dashboard. It checks for new complaints and notices every 5 seconds. The Notices screen lists complaints that passed their time limit and opens by itself when a new one arrives.

## The local model step

A local model (llama3.1 through Ollama) may pick a complaint's type and subtype. Charter timelines, owners, escalation days and the reply text never come from the model. Urgency comes from keyword rules, so the model cannot lower it. If Ollama is not running, or the model's answer is not a valid type, the keyword classifier is used and the screen says so. Every model choice has a note for the officer to confirm.

## Run it

1. Install the requirements once: `python -m pip install -r requirements.txt`.
2. Create the demo officer accounts: `python portal/manage.py seed-demo --password "a-long-password"`. This makes one account per field and level, plus `district.head`. Usernames look like `water.depot` and `sewerage.deputy_ae`.
3. Start the portal: `python portal/server.py`, then open http://127.0.0.1:8000. Citizens and officers both log in on that first screen (User Login and Officer Login tabs).
4. Optional, for the model step: install Ollama, run `ollama pull llama3.1`, and keep Ollama running. The portal works without it.

The portal checks time limits every 30 seconds. For a demo, `python portal/server.py --demo-minutes 2` gives every new complaint a 2-minute time limit, so a notice appears on the officer dashboard about two minutes after a complaint is filed. Without `--demo-minutes`, the charter's days are used.

### Sending the codes by SMS

The login codes, the "is it fixed?" code and the worker's completion code can go to the person's mobile by SMS. Copy `.env.example` to `.env` in the project folder and fill in one provider:

- Fast2SMS (Indian numbers): `SMS_PROVIDER=fast2sms`, `FAST2SMS_API_KEY` (Dev API in the dashboard) and `FAST2SMS_OTP_ID` (the ID of an OTP template you create in the dashboard). The portal makes the code itself and sends it through the Fast2SMS OTP API.
- Twilio: `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM` (your Twilio number). Messages go to +91 and the 10-digit number. A trial account only sends to numbers you verify in the Twilio console.

When the server starts, it says whether SMS is on. With no provider set, or if sending fails, the code is shown on screen instead (and the reason is shown), so a demo never gets stuck. SMS needs a paid or verified provider account; it costs money per message and Indian rules (DLT) may require a registered template. Never share or upload the `.env` file.

## Manage officers

These commands run from the project folder. Each one asks for the password, so it is not left in the command history.

```
python portal/manage.py add-officer --username water.depot2 --name "Water supply depot, zone 2" --field water --level depot
python portal/manage.py list-officers
python portal/manage.py check-overdue
```

Officers who sign up pick their own field and level, and the District Head Office approves them with `python portal/manage.py approve-officer --username NAME`. `python portal/manage.py list-pending` shows the sign-ups waiting. Fields are `water`, `sewerage`, `billing`, `new_connection`, `general`, and `all` for the District Head Office. Levels are `depot`, `deputy_ae`, `area_engineer`, `superintendent_engineer`, and `district_head`. A complaint with no officer at its level waits as unassigned, and the District Head Office can see it.

The database is `portal/data/portal.db`. Set `COMPLAINT_PORTAL_DB` to use another file. Delete the file to start again.

## Assumptions and open questions for CMWSSB

The charter does not say whether its escalation days are cumulative from registration or apply to each level separately. This portal uses per level, as the table reads. This is the most important thing to confirm.

The charter says that if a complaint is not solved, a notification goes to the Chief Engineer. This portal sends it to the District Head Office, as the project owner asked. The final level is set in `complaint_tools/complaint_portal/rules.py`, and the account in `seed.py`. Change both if the Chief Engineer should be the final level.

The charter does not mention a ward office. This portal reads the drawing as: a citizen who says the problem is not fixed sends the complaint to the ward office, which is the depot officer for the ward's zone, with the same time to fix it as the depot had. If that time passes, it goes to the District Head Office. The time limits from the charter for the other levels are unchanged.

The portal does not close a complaint when the citizen does not reply. It waits in "Marked resolved" and nothing moves it. Decide whether an automatic close after a set number of days is wanted.

The charter does not name an owner for septic tank clearance. The depot is assumed, as before.

## Security and privacy

Passwords are stored as salted PBKDF2-SHA256 hashes. Citizens stay logged in until they log out (kept for at most a year). Officer logins end at midnight every day (India time). Sessions are kept in memory, so a restart logs everyone out. Citizen login codes and confirmation codes are six digits, last 10 minutes, stop working after five wrong tries, and work only once. They are also kept in memory, so a restart cancels them. In this demo the code is shown on the page, so anyone who can open the page and type a mobile number can log in as that number. A real SMS service is needed before any real use. The server listens on 127.0.0.1 only. API requests must be JSON, which stops a plain web form on another site from sending requests.

This is a demo. Before any real use, it needs HTTPS, proper accounts managed by CMWSSB, a real database server, an audit of the code, and a decision on how long citizens' mobile numbers and complaint text are kept. The demo stores mobile numbers, addresses and complaint text in plain text in the SQLite file. Change the demo officer passwords before use.

Use only invented names and numbers when you try the demo. The hackathon rules do not allow personal data.

## Other ways to use the project

`app/server.py` runs the offline router page at http://127.0.0.1:8000 (see the router section below). `examples/run_pipeline.py` runs the routing steps with no LLM and prints the exact reply text. `registries/complaintrouter.hocon` is the Neuro-SAN agent network (see "Run the Neuro-SAN agent network" above). Its coordinator calls the five router agents in a fixed order, and the portal runs the same five coded tools in-process, so the timelines, owners and escalation days are the same in both. The coordinator is told to return the reply agent's text word for word, but a model can still reword it, so for the exact reply text use the pipeline or the portal. `examples/evaluate_router.py` measures the router on 45 labelled complaints in `data/eval_complaints.csv` (the results are in `summary.md`); add `--llm` to measure the local model too.

### The offline router page

### The router's message and timeline

When a citizen registers a complaint, the portal runs the router (`complaintrouter.pipeline.run_complaint`) and keeps two things with the complaint:

- **The router's message.** The exact text from `reply.build_reply`, with the real complaint ID in it (the portal passes the ID in, so it no longer says "reference to be assigned"). It is shown on the registration screen as soon as the complaint is filed, and again on Track Complaint under "Message from the complaint router". Its first line is the router's own banner (a draft, not an official CMWSSB reply); the screens show that line as a notice and the rest as the message, and change nothing in the text.
- **The router's timeline.** The charter repair time and the escalation days for each officer level, as the router's tools gave them at registration. The screens turn it into progress: each office, its time limit, and a marker for Done, Now, Next or Not needed. The current step shows the live deadline the portal is counting down to. When a time limit passes or the citizen says "not fixed", the marker moves, so the list follows the complaint.

Both come back in the JSON of `POST /api/complaints`, `POST /api/track` and the officer complaint views, as `router_message` (text, or `null` for a complaint filed before this was kept) and `router_progress` (`label`, `repair_time`, `steps`, `after_last_level`, `note`, `kept_at_registration`). Older complaints get a timeline rebuilt by the router's own tools; their message is not invented. Older database files get the two new columns (`router_message`, `router_timeline`) when the portal starts.

The message and the timeline never come from a model: the model only chooses a complaint's type, and the router's tools do the rest. The message is a draft with open items for a reviewer, and it says so. The charter does not say whether its escalation days are cumulative or per level, and the portal treats them as per level (see `rules.py`); the timeline repeats the router's note about this. The router also says that after the last level a notification goes to the Chief Engineer, while the portal's last level is the District Head Office; the timeline shows the router's sentence as written.

The worker page still has its own "From the agents" placeholder under each complaint. It is not connected.

`python app/server.py` opens a page that takes one complaint and shows the model's classification and the exact draft reply in separate boxes. It is a demo tool and does not store complaints.

## Layout

`complaint_tools/complaint_portal/` holds the portal's rules (fields, stages, time limits), storage (SQLite), password and session handling, the workflow, and the demo account seeding. `complaint_tools/complaintrouter/` holds the routing steps, the model step with its fallback, and the pipeline. `portal/` holds the portal's web server, the pages (the first screen with citizen and officer login, the citizen sign-up, the officer sign-up, and the officer dashboard), and `manage.py`. `app/` holds the offline router page. `registries/` holds the agent network. `data/charter.json` holds the timelines, owners, escalation days and helpline numbers. `data/chennai_zones.csv`, `data/chennai_wards.csv`, and `data/cmwssb_sewer_zones.csv` hold the district, zone, and ward data. `tests/` holds the tests.

The folder is named `complaint_tools` rather than `coded_tools` because an installed neuro-san-studio package already uses the name `coded_tools`.

## Tests

`python -m pytest -q tests` runs 303 tests. None needs Ollama or the internet. The account tests cover sign-up and approval, the midnight rule for officer logins, and the account API. The portal tests cover field routing, deadlines, escalation through every level to the District Head Office, citizen confirmation, officer visibility, login and sessions, and the web API. The citizen tests cover address matching, the login codes (wrong, expired, and locked after too many tries), the confirmation code, and the route from a not-fixed complaint through the ward office to the District Head Office. The worker tests cover worker sign-up and login, accepting (and two workers trying to accept the same complaint), the completion code (wrong and right), the citizen's view, and the notices with the citizen's and worker's details. The ward tests check the 15 zones and 200 wards, the loader's refusal of broken data, the zone-specific officer rule, and the upgrade of older database files. The router tests cover the timelines, the reply text, the model's answer handling, and the fallback. The router-link tests (`tests/test_router_link.py`) cover the message at registration (exact text, real complaint ID, kept and returned), the timeline as progress for each kind of complaint, its movement through escalation, the ward office and closure, complaints filed before the link, upgrading an older database, and the HTTP responses. `tests/js/router_screens.e2e.test.js` is an optional check of the real pages in a browser engine (needs Node and `npm install jsdom`, and a running portal), and `flutter_app/test/router_panels_test.dart` covers the app's new widgets (run it with `flutter test`).

## Verified and not verified

Verified here: all 303 tests pass, including the SMS tests (with a fake provider; no real SMS was sent from here). A headless Chromium run of Register Complaint passed 11 checks for the "Your complaints" panel. A headless Chromium run of the worker and notice flow passed 26 checks: three equal login tabs, the complaint ID after Submit with "Track this complaint", the agents box, the Track search bar, worker sign-up and login, a new complaint appearing on the worker's list by itself, complainant details, accepting (the citizen sees Allotted and Work in progress), a wrong completion code refused and the right one accepted, the green Resolved on Track and Home, the officer's notice opening by itself with the citizen's and the worker's details, and phone width. The earlier Track run (14 checks) and whole-flow run (36 checks) were run again and pass. A headless Chromium run of Track Complaint passed 14 checks: the empty state, newest complaint first, picking another complaint, a wrong ID, the page updating by itself after the officer's resolve, closing with the code, the Track link from home, and phone width. Earlier, after the pages were rebuilt in the light blue style, a headless Chromium run went through the whole flow with the browser set to dark mode (the pages stay light): sign-up with the zone suggested from the address, the new-user message, login with a code, the home page, a complaint from a service card, the blank Track page, the officer seeing a new complaint appear by itself within about 5 seconds, the officer's resolve, the citizen's confirmation with a code, log out, officer sign-up, and phone width with no sideways scrolling (36 checks). Before that, A headless Chromium run checked the first screen, both sign-up pages, the new-user message, citizen login and a reload that keeps the login, the account icon with its single Log out control, officer sign-up held for approval, approval and officer login, and the redirect for an officer page opened without a login (25 checks, no script errors). A live server was run through the whole citizen flow: an address matched to Teynampet, a login with a code, a complaint filed under ward 115, the officer's resolve, a "yes" that showed a code, a wrong code that was refused, the right code that closed the complaint, and a "not fixed" that moved the complaint to the ward office. The ward files were checked against the gazette's zone table: 15 zones, 200 wards, and each zone's range matches its ward count. A live run filed complaints under wards 115 and 1, and the zone and ward were recorded and shown. A complaint with no ward is refused. The portal server was run and a complaint was filed, resolved by the depot officer, and reopened by the citizen, which escalated it. The depot officer got a 403 on the district-only check. The pages' scripts pass a syntax check and make no outside requests.

Not verified here: a real midnight rollover (the midnight rule is tested with set times), real SMS delivery through Fast2SMS or Twilio (it needs your account); the model's choices with a running llama3.1 (the sandbox has no Ollama); the official charter values (the PDF copy is from a development mirror); the escalation rule (cumulative or per level); behaviour on Windows, which this sandbox cannot run.

## Suggested demo walkthrough

Run the portal end to end: file a leak complaint, resolve it as the depot officer, reply "not fixed" as the citizen, and check that it moves to the Deputy Area Engineer. Then run the district check as the District Head Office. Check the time limits and the escalation rule against the official charter or the CMWSSB office. Say aloud that this is an unofficial demo and that nothing it produces is an official reply.

Version note: neuro-san 0.7.x fails at server startup with `Cannot instantiate interface 'Startable'` when leaf-common 1.4.5 is installed. The requirements pin `leaf-common==1.4.4`, which fixes it. Keep that pin.

## Flutter app and hosting

The phone and web app is in `flutter_app/`. It is one Flutter project for Android, iPhone and the web. Its own README has the steps to run it.

The app calls the backend's JSON API, so the backend must be running and reachable from the device.

- Same Wi-Fi: `HOST=0.0.0.0 python portal/server.py`, then start the app with `--dart-define=API_BASE=http://<your computer's Wi-Fi address>:8000`.
- Online: the `Dockerfile` runs the server with `HOST=0.0.0.0` and reads `PORT` from the host. Keep the database on a persistent disk mounted at `/data`, or data is lost on restart. Free plans on most hosts sleep when idle, so wake the service a few minutes before a demo.
- Web app from the backend: `cd flutter_app && flutter build web --base-href /app/`, then open `/app/` on the running server.

Status of the Flutter code: the app now follows the web pages, including the Worker Login tab, Worker Sign-up, the worker dashboard, the officer's Notices, the Track search bar and the green Resolved. The Dart files passed a syntax check, a check that every project name is imported and every argument exists, and a separate line-by-line review, but they have not been compiled. `flutter analyze`, `flutter test` and `flutter build` have not been run, because the Flutter SDK could not be downloaded in the environment where it was written. Run `flutter analyze` first and send any errors back.

The backend tests (`python -m pytest`) cover the new `/app/` serving and the citizen sign-up, login and complaint flow over HTTP.
