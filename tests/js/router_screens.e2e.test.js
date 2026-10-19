// Optional end-to-end test of the REAL web pages against a RUNNING portal (needs Node 18+ and `npm install jsdom`).
//   1) start the portal:   python portal/server.py --port 8000 --db some-test.db     (use a throw-away database)
//   2) node tests/js/router_screens.e2e.test.js            (BASE_URL=http://127.0.0.1:8000 by default)
// It signs a citizen up, then opens /register and /track in a browser engine, files a complaint through the real
// form, and checks the router's message and timeline appear. jsdom is not a real browser (no layout, no CSS paint).
const { JSDOM, CookieJar } = require('jsdom');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const CONTACT = '98765' + String(Math.floor(Math.random() * 90000) + 10000);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let passed = 0;
const must = (cond, msg) => { if (!cond) throw new Error('FAILED: ' + msg); passed++; console.log('  ok  ' + msg); };
async function waitFor(fn, what, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) { /* keep waiting */ } await sleep(100); }
  throw new Error('TIMED OUT waiting for: ' + what);
}
const json = async (path, body, cookie) => {
  const res = await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) }, body: JSON.stringify(body) });
  return { res, data: await res.json().catch(() => ({})) };
};

async function openPage(path, cookie) {
  const jar = new CookieJar();
  jar.setCookieSync(cookie, BASE);
  const dom = await JSDOM.fromURL(BASE + path, {
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, cookieJar: jar,
    beforeParse(w) {
      w.fetch = (u, o = {}) => fetch(new URL(u, BASE), { ...o, headers: { ...(o.headers || {}), Cookie: cookie } });
      w.scrollTo = () => {};
      w.HTMLElement.prototype.scrollIntoView = () => {};
    },
  });
  return dom;
}

(async () => {
  console.log('Real pages, real server: router message + timeline');
  // a citizen with a session
  let r = await json('/api/citizen/signup', { name: 'E2E Citizen', contact: CONTACT, address: '12 Main Road, Teynampet, Chennai', ward_number: 115 });
  must(r.res.status === 201, 'citizen signs up');
  const login = await json('/api/citizen/login', { contact: CONTACT });
  r = await json('/api/citizen/verify', { contact: CONTACT, code: login.data.code });
  const cookie = r.res.headers.get('set-cookie').split(';')[0];
  must(cookie.startsWith('citizen_session='), 'citizen logs in');

  // ---- /register: file an emergency complaint through the real form (emergencies need no photos)
  const reg = await openPage('/register', cookie);
  const w = reg.window, d = w.document, $ = (id) => d.getElementById(id);
  await waitFor(() => d.querySelector('input[name="kind"]'), 'form ready');
  const emergency = d.querySelector('input[name="kind"][value="emergency"]');
  emergency.checked = true; emergency.dispatchEvent(new w.Event('change', { bubbles: true }));
  const category = await waitFor(() => d.querySelector('input[name="category"]'), 'categories');
  category.checked = true; category.dispatchEvent(new w.Event('change', { bubbles: true }));
  await waitFor(() => d.querySelector('input[name="address"]'), 'addresses');
  $('complaint').value = 'Water is leaking from the pipe near my house for three days, please fix it.';
  $('useLlm').checked = false;                                  // keyword classifier: no model needed
  $('complaintForm').dispatchEvent(new w.Event('submit', { cancelable: true, bubbles: true }));
  await waitFor(() => !$('doneBody').hidden, 'registration success panel');
  const id = $('doneId').textContent.trim();
  must(/^CMP-\d{8}-\d{4}$/.test(id), `complaint registered: ${id}`);

  const banner = d.querySelector('#routerMessageBody .router-banner');
  const message = d.querySelector('#routerMessageBody pre.router-message');
  must(banner && banner.textContent.startsWith('DRAFT - NOT SENT'), "the router's banner is shown as a notice");
  must(message && message.textContent.includes(`Complaint reference: ${id}`), 'the router message names the real complaint ID');
  must(!message.textContent.includes('to be assigned'), 'it no longer says "to be assigned"');
  must(!/coming soon/i.test(d.body.textContent), 'the "Coming soon" placeholder is gone');
  const steps = [...d.querySelectorAll('#routerTimeline .router-steps .rs')];
  must(!$('routerTimelineBox').hidden && steps.length === 5, 'the router timeline shows all five levels');
  must(steps[0].classList.contains('current') && steps[0].textContent.includes('Time limit: 3 days'), 'the depot is the current step with its 3-day charter limit');
  must(steps.slice(1).every((s) => s.classList.contains('upcoming')), 'later levels are upcoming');

  // the text on screen is exactly what the server stored
  const tracked = await json('/api/track', { id, contact: CONTACT });
  must(banner.textContent + '\n\n' + message.textContent === tracked.data.router_message, "screen text equals the router's stored message exactly");

  // ---- /track: the same complaint
  const trk = await openPage('/track?id=' + id, cookie);
  const tw = trk.window, td = tw.document;
  await waitFor(() => !td.getElementById('result').hidden && !td.getElementById('routerBox').hidden, 'track page result');
  const tsteps = [...td.querySelectorAll('#routerProgress .rs')];
  must(tsteps.length === 5 && tsteps[0].classList.contains('current'), 'Track Complaint shows the router timeline with the current level marked');
  must(td.querySelector('#routerMessageBox summary').textContent.includes('Message from the complaint router'), 'Track Complaint offers the router message');
  must(td.querySelector('#routerMessageBody pre').textContent.includes(`Complaint reference: ${id}`), 'the message on Track Complaint names the complaint ID');

  // ---- hostile text can never become HTML
  const { renderCheck } = (() => {
    const P = tw.Portal;
    const nodes = P.routerMessage('<img src=x onerror=alert(1)>\n\n<b>body</b>');
    const holder = td.createElement('div'); nodes.filter(Boolean).forEach((n) => holder.append(n));
    return { renderCheck: holder };
  })();
  must(renderCheck.querySelectorAll('img, b').length === 0 && renderCheck.textContent.includes('<img src=x'), 'message text is shown as text, never as HTML');

  console.log(`\n${passed} checks passed`);
  process.exit(0);
})().catch((e) => { console.error('\n' + e.message); process.exit(1); });
