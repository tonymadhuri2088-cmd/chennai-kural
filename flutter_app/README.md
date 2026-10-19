# Chennai Complaint Portal: Flutter app

One Flutter project for Android, iPhone and the web. It looks like the web pages served by the backend (the light blue banner, the login card, the sign-up forms, the home page) and talks to the Python backend in the project root.

This is an unofficial app. It is not affiliated with CMWSSB or the Government of Tamil Nadu.

## What is in the app

- First screen: the banner and the login card with three tabs of the same size: User Login and Worker Login (mobile number and a code) and Officer Login (username and password). It also has a "How it works" card that changes every few seconds, and English or Tamil for the banner.
- User Sign-up, Worker Sign-up (with "Department of work") and Officer Sign-up, in the style of the reference sign-up screen. The forms suggest the zone from the address.
- "You are new user, please sign up." appears when a mobile number or username has not signed up.
- Home page after a citizen logs in: Register Complaint, Track Complaint, the common services, the citizen's own numbers, how it works, and the citizen's complaints with the "is it fixed?" question. It updates every 5 seconds.
- Register Complaint: the form. A service card on the home page opens it with a matching example. "Your complaints" at the side lists every complaint with its ID and Completed or Not completed. After Submit, the complaint ID is shown with a "Track this complaint" button, and a "From the agents" box is at the side (its content comes later).
- Track Complaint: a search bar for the complaint ID in the banner, or pick one of your complaints. It shows the progress (Registered, Allotted, Work in progress, Resolved), a green Resolved at the side when resolved, the worker, the code for the worker, the "is it fixed?" question and the history. It updates every 5 seconds.
- Worker dashboard: "Complaints registered" (open complaints nobody has taken, with the complaint ID and Accept) and "Allotted tasks" (accepted ones, with Mark as completed). "View complainant details" shows the citizen's sign-up details. Mark as completed sends a code to the citizen; only the right code completes the complaint. It updates every 5 seconds.
- Officer dashboard: the numbers and the complaints, checked every 5 seconds, with new ones marked "New". Tapping a complaint opens it, with Mark resolved, Add note and Escalate. The Notices screen lists complaints that passed their time limit, with the department, the office in charge, the citizen and the worker, and opens by itself when a new notice arrives.
- The round account icon shows the details and the only Log out button.
- Citizens and workers stay logged in until they log out. Officer logins end at midnight India time (set on the backend).

## One-time setup (Windows PowerShell)

1. Install Flutter from https://docs.flutter.dev/get-started/install and check it with `flutter doctor`.
2. Open PowerShell in this `flutter_app` folder.
3. Add the platform folders. First copy `lib`, `test` and `pubspec.yaml` somewhere safe, then run:

       flutter create --platforms=android,ios,web --project-name chennai_complaints .

   Copy `lib`, `test` and `pubspec.yaml` back, replacing the files `flutter create` made.

4. Get the packages, check the code and run the tests:

       flutter pub get
       flutter analyze
       flutter test

## Start the backend first

From the project root (the folder that contains `portal\`), in its own PowerShell window:

    python portal\server.py

For a demo of the notices, give every new complaint a short time limit (2 minutes here):

    python portal\server.py --demo-minutes 2

For a phone on the same Wi-Fi, let other devices reach it:

    $env:HOST="0.0.0.0"; python portal\server.py

Officer accounts must be approved before they can log in:

    python portal\manage.py list-pending
    python portal\manage.py approve-officer --username NAME

## Run the app

### In a browser (easiest)

    flutter build web --base-href /app/

Then open http://127.0.0.1:8000/app/ while the backend is running. The app and the API share one address, so logins work.

Do not use `flutter run -d chrome` for this. The Flutter dev server runs on another address, and the backend does not accept requests from other addresses (it sends no CORS headers, and its login cookies are SameSite=Strict), so every request would fail with "Cannot reach the server".

### Android emulator

    flutter run

The emulator reaches your computer at 10.0.2.2 automatically.

### A real Android phone on the same Wi-Fi

Start the backend with `HOST` set to `0.0.0.0` (see above), find your computer's Wi-Fi address with `ipconfig` (for example 192.168.1.20), then:

    flutter run --dart-define=API_BASE=http://192.168.1.20:8000

Android blocks plain http by default. In `android\app\src\main\AndroidManifest.xml`, add `<uses-permission android:name="android.permission.INTERNET"/>` above `<application>`, and `android:usesCleartextTraffic="true"` inside the `<application>` tag. Use this for the demo only.

### iPhone

Needs a Mac with Xcode. The simulator uses `http://localhost:8000` by default:

    flutter run -d ios

A real iPhone needs `--dart-define=API_BASE=http://<your computer's Wi-Fi address>:8000` and an exception for plain http in `ios/Runner/Info.plist` (for a demo, `NSAppTransportSecurity` with `NSAllowsArbitraryLoads` set to true).

## Things to know

- The Dart code was written where the Flutter SDK could not be installed. It passed a syntax check, an import and argument check, and a separate review, but it has not been compiled. Run `flutter analyze` first and send any errors back.
- The branding is neutral: no government emblem, no official portal name, no photo of a real person, no government footer.
- The Tamil on the first screen should be checked by someone who reads Tamil.
- Codes go by SMS when the server has an SMS provider set up (see `.env.example` and the main README). Otherwise they are shown on screen: the login code on the login card, and the worker's completion code on the citizen's Track Complaint and Home screens.
