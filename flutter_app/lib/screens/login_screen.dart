import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/skyline.dart';
import 'citizen_signup_screen.dart';
import 'home_screen.dart';
import 'officer_home_screen.dart';
import 'officer_signup_screen.dart';
import 'worker_home_screen.dart';
import 'worker_signup_screen.dart';

const String newUserMessage = 'You are new user, please sign up.';

/// Goes back to the first screen, forgetting every screen opened before, with an optional message.
/// [officerTab] or [workerTab] opens that login tab instead of User Login.
void returnToLogin(
  BuildContext context, {
  String? message,
  bool isError = false,
  bool officerTab = false,
  bool workerTab = false,
}) {
  Navigator.of(context).pushAndRemoveUntil(
    MaterialPageRoute<void>(
      builder: (_) => LoginScreen(
        message: message,
        messageIsError: isError,
        officerTab: officerTab,
        workerTab: workerTab,
      ),
    ),
    (route) => false,
  );
}

/// The three tabs on the login card.
enum LoginTab { user, worker, officer }

/// The mobile-number-and-code login, used by the User Login and Worker Login tabs.
class _PhoneLogin {
  final TextEditingController mobile = TextEditingController();
  final TextEditingController code = TextEditingController();
  bool codeSent = false;
  String codeShown = '';
  String codeNote = '';
  String? error;
  bool showNewUser = false;
  String? verifyError;

  void dispose() {
    mobile.dispose();
    code.dispose();
  }
}

class _Slide {
  const _Slide(this.icon, this.kicker, this.title, this.text);

  final IconData icon;
  final String kicker;
  final String title;
  final String text;
}

/// The words on the first screen, in English and Tamil. The Tamil should be checked by a native speaker.
class _Words {
  const _Words({
    required this.line1,
    required this.before,
    required this.sky,
    required this.after,
    required this.lead,
    required this.chips,
    required this.slides,
  });

  final String line1;
  final String before;
  final String sky;
  final String after;
  final String lead;
  final List<String> chips;
  final List<_Slide> slides;
}

const Map<String, _Words> _words = <String, _Words>{
  'en': _Words(
    line1: 'Clean Water, Clear Drains',
    before: 'for Every Street in ',
    sky: 'Chennai',
    after: '',
    lead: 'Report water and sewer problems, follow their progress, and confirm when they are fixed. '
        'Sign up once, then log in with your mobile number.',
    chips: <String>['Clean water', 'Clear drains', 'Quick response', 'Your voice matters'],
    slides: <_Slide>[
      _Slide(
        Icons.edit_note,
        'How it works',
        'Report a problem in minutes',
        'Describe the problem in your own words. The portal sorts it into water supply, sewerage, billing, '
            'new connections or general, and sends it to the officer for your ward.',
      ),
      _Slide(
        Icons.alt_route,
        'Stay informed',
        'Follow every step',
        'See which office has your complaint and its time limit. If the time passes without a fix, '
            'the complaint moves up to the next officer.',
      ),
      _Slide(
        Icons.check_circle_outline,
        'You decide',
        'Confirm the fix yourself',
        'When the officer marks it resolved, you confirm. If it is still not fixed, it goes to the ward office '
            'and then to the District Head Office.',
      ),
    ],
  ),
  'ta': _Words(
    line1: 'சுத்தமான குடிநீர், தெளிவான வடிகால்',
    before: '',
    sky: 'சென்னையின்',
    after: ' ஒவ்வொரு தெருவுக்கும்',
    lead: 'குடிநீர் மற்றும் கழிவுநீர் பிரச்சனைகளைப் புகார் செய்யுங்கள், முன்னேற்றத்தைப் பின்தொடருங்கள், '
        'சரியானதும் உறுதிப்படுத்துங்கள். ஒருமுறை பதிவு செய்து, உங்கள் மொபைல் எண்ணுடன் உள்நுழையுங்கள்.',
    chips: <String>['சுத்தமான குடிநீர்', 'தெளிவான வடிகால்', 'விரைவான நடவடிக்கை', 'உங்கள் குரல் முக்கியம்'],
    slides: <_Slide>[
      _Slide(
        Icons.edit_note,
        'எப்படி வேலை செய்கிறது',
        'சில நிமிடங்களில் புகார் செய்யுங்கள்',
        'புகாரைப் பதிவு செய்யுங்கள். அது சரியான அலுவலகத்திற்குச் செல்லும்.',
      ),
      _Slide(
        Icons.alt_route,
        'தகவலுடன் இருங்கள்',
        'ஒவ்வொரு படியையும் பின்தொடருங்கள்',
        'உங்கள் புகார் எந்த அலுவலகத்தில் உள்ளது, அதன் கால வரம்பு என்ன என்பதைப் பாருங்கள்.',
      ),
      _Slide(
        Icons.check_circle_outline,
        'உங்கள் முடிவு',
        'சரியானதை நீங்களே உறுதிப்படுத்துங்கள்',
        'பிரச்சனை தீர்ந்ததும் உறுதிப்படுத்துங்கள். தீரவில்லை என்றால், புகார் அடுத்த அலுவலருக்குச் செல்லும்.',
      ),
    ],
  ),
};

/// The first screen: the blue banner and the login card with User Login, Worker Login and Officer Login.
class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.message,
    this.messageIsError = false,
    this.officerTab = false,
    this.workerTab = false,
  });

  /// A message to show on the card, for example after a sign-up.
  final String? message;
  final bool messageIsError;
  final bool officerTab;
  final bool workerTab;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  static const double _cardWidth = 456;

  final _citizen = _PhoneLogin();
  final _worker = _PhoneLogin();
  final _username = TextEditingController();
  final _password = TextEditingController();

  late LoginTab _tab = widget.officerTab
      ? LoginTab.officer
      : (widget.workerTab ? LoginTab.worker : LoginTab.user);
  late String? _notice = widget.message;
  late final bool _noticeIsError = widget.messageIsError;

  bool _busy = false;
  String? _officerError;

  String _lang = 'en';
  int _slide = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 7), (_) {
      if (mounted) setState(() => _slide = (_slide + 1) % 3);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _citizen.dispose();
    _worker.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  void _switchTab(LoginTab tab) {
    setState(() {
      _tab = tab;
      _notice = null;
    });
  }

  Future<void> _sendCode(bool worker) async {
    final login = worker ? _worker : _citizen;
    setState(() {
      _busy = true;
      login.error = null;
      login.showNewUser = false;
    });
    try {
      final mobile = login.mobile.text.trim();
      final sent = worker ? await api.workerStartLogin(mobile) : await api.citizenStartLogin(mobile);
      if (!mounted) return;
      setState(() {
        login.codeSent = true;
        login.codeShown = sent['code']?.toString() ?? '';
        login.codeNote = '${sent['note'] ?? ''} It lasts ${sent['minutes'] ?? 10} minutes.';
        login.code.clear();
        login.verifyError = null;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        login.error = error.message;
        login.showNewUser = error.status == 404;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify(bool worker) async {
    final login = worker ? _worker : _citizen;
    setState(() {
      _busy = true;
      login.verifyError = null;
    });
    try {
      final mobile = login.mobile.text.trim();
      final code = login.code.text.trim();
      final Widget next;
      if (worker) {
        next = WorkerHomeScreen(worker: await api.workerVerify(mobile, code));
      } else {
        next = HomeScreen(profile: await api.citizenVerify(mobile, code));
      }
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute<void>(builder: (_) => next), (route) => false);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => login.verifyError = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _officerLogin() async {
    setState(() {
      _busy = true;
      _officerError = null;
    });
    try {
      final officer = await api.officerLogin(_username.text.trim(), _password.text);
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => OfficerHomeScreen(officer: officer)),
        (route) => false,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _officerError = error.message;
        _password.clear();
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _openSignUp(LoginTab tab) {
    final Widget screen;
    if (tab == LoginTab.officer) {
      screen = const OfficerSignupScreen();
    } else if (tab == LoginTab.worker) {
      screen = const WorkerSignupScreen();
    } else {
      screen = const CitizenSignupScreen();
    }
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
  }

  @override
  Widget build(BuildContext context) {
    final words = _words[_lang] ?? _words['en']!;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(trailing: [_languagePicker()]),
              if (isWideScreen(context)) _wideBody(words) else _narrowBody(words),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  // Wide screens: the login card sits at the right of the banner and hangs below it, like the reference screen.
  Widget _wideBody(_Words words) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final right = math.max(0.0, (screenWidth - maxPageWidth) / 2) + pageGutter(context);
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            HeroBanner(
              skylineShare: 0.48,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: _bannerText(words)),
                  const SizedBox(width: _cardWidth + 32),
                ],
              ),
            ),
            PageWidth(
              child: Padding(
                padding: const EdgeInsets.only(top: 26),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _infoCard(words)),
                    const SizedBox(width: _cardWidth + 32),
                  ],
                ),
              ),
            ),
            _skyband(),
          ],
        ),
        Positioned(top: 72, right: right, width: _cardWidth, child: _loginCard()),
      ],
    );
  }

  Widget _narrowBody(_Words words) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        HeroBanner(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [_bannerText(words), const SizedBox(height: 24), _loginCard()],
          ),
        ),
        PageWidth(
          child: Padding(padding: const EdgeInsets.only(top: 22), child: _infoCard(words)),
        ),
        _skyband(),
      ],
    );
  }

  Widget _bannerText(_Words words) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        HeroHeadline(line1: words.line1, before: words.before, sky: words.sky, after: words.after),
        HeroLead(words.lead),
        FeatureChips(labels: words.chips),
      ],
    );
  }

  Widget _skyband() {
    return const Padding(
      padding: EdgeInsets.only(top: 20),
      child: SizedBox(
        height: 96,
        width: double.infinity,
        child: Skyline(stroke: Palette.skyband, repeat: true),
      ),
    );
  }

  Widget _languagePicker() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(
        color: Palette.white,
        border: Border.all(color: Palette.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.language, size: 18, color: Palette.navy),
          const SizedBox(width: 6),
          DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: _lang,
              isDense: true,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Palette.navy),
              items: const [
                DropdownMenuItem<String>(value: 'en', child: Text('English')),
                DropdownMenuItem<String>(value: 'ta', child: Text('தமிழ்')),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _lang = value);
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _loginCard() {
    final notice = _notice;
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 18),
      decoration: BoxDecoration(
        color: Palette.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFDBE7F4)),
        boxShadow: const [BoxShadow(color: Color(0x29023668), blurRadius: 32, offset: Offset(0, 12))],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Three tabs of the same size: User Login, Worker Login, Officer Login.
          Row(
            children: [
              Expanded(child: _tabButton('User Login', Icons.person_outline, LoginTab.user)),
              const SizedBox(width: 8),
              Expanded(child: _tabButton('Worker Login', Icons.engineering_outlined, LoginTab.worker)),
              const SizedBox(width: 8),
              Expanded(child: _tabButton('Officer Login', Icons.work_outline, LoginTab.officer)),
            ],
          ),
          const SizedBox(height: 16),
          if (notice != null) NoticeBox(text: notice, tone: _noticeIsError ? NoticeTone.error : NoticeTone.ok),
          if (_tab == LoginTab.officer) ..._officerForm() else ..._phoneForm(worker: _tab == LoginTab.worker),
        ],
      ),
    );
  }

  Widget _tabButton(String label, IconData icon, LoginTab tab) {
    final selected = _tab == tab;
    return Semantics(
      selected: selected,
      button: true,
      child: TextButton(
        onPressed: () => _switchTab(tab),
        style: TextButton.styleFrom(
          backgroundColor: selected ? Palette.primary : Palette.white,
          foregroundColor: selected ? Palette.white : Palette.navy,
          minimumSize: const Size(0, 44),
          padding: const EdgeInsets.symmetric(horizontal: 6),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(7),
            side: BorderSide(color: selected ? Palette.primary : Palette.border),
          ),
          textStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600),
        ),
        // Scales the words down on a narrow phone, so all three tabs stay the same size on one line.
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [Icon(icon, size: 16), const SizedBox(width: 6), Text(label, maxLines: 1)],
          ),
        ),
      ),
    );
  }

  Widget _note(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(text, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
    );
  }

  Widget _signUpLine(String lead, String link, VoidCallback onTap) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Wrap(
        alignment: WrapAlignment.center,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(lead, style: const TextStyle(fontSize: TextSizes.small, color: Palette.labelText)),
          TextButton(
            onPressed: onTap,
            style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 4)),
            child: Text(
              link,
              style: const TextStyle(fontSize: TextSizes.small, decoration: TextDecoration.underline),
            ),
          ),
        ],
      ),
    );
  }

  /// The User Login and Worker Login tabs: a mobile number, then the code shown on screen (no SMS in this demo).
  List<Widget> _phoneForm({required bool worker}) {
    final login = worker ? _worker : _citizen;
    final tab = worker ? LoginTab.worker : LoginTab.user;
    final signUpLine = worker
        ? _signUpLine('New worker?', 'Click here to sign up', () => _openSignUp(tab))
        : _signUpLine("Don't have an account?", 'Click here to sign up', () => _openSignUp(tab));
    if (!login.codeSent) {
      final error = login.error;
      return [
        LabeledField(
          label: 'Mobile number',
          required: true,
          child: TextField(
            key: ValueKey<String>(worker ? 'workerMobile' : 'citizenMobile'),
            controller: login.mobile,
            keyboardType: TextInputType.phone,
            inputFormatters: [LengthLimitingTextInputFormatter(16)],
            decoration: fieldDecoration(hint: 'Enter your 10-digit mobile number', icon: Icons.phone_android),
            onSubmitted: (_) => _sendCode(worker),
          ),
        ),
        _note(worker
            ? 'Workers get a 6-digit code by SMS on this number. If SMS is not set up on the server, the code appears here.'
            : 'You get a 6-digit code by SMS on this number. If SMS is not set up on the server, the code appears here.'),
        PortalButton(
          label: 'Send me a code',
          trailingIcon: Icons.arrow_forward,
          busy: _busy,
          expand: true,
          onPressed: () => _sendCode(worker),
        ),
        if (error != null) ErrorText(error),
        if (login.showNewUser)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () => _openSignUp(tab),
              child: Text(worker ? 'Sign up as a worker' : 'Sign up as a citizen'),
            ),
          ),
        signUpLine,
      ];
    }
    final error = login.verifyError;
    return [
      Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: Palette.sectionBg,
          border: Border.all(color: Palette.primaryBright),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Sent by SMS: no code on screen. Otherwise (no SMS set up on the server) the code is shown here.
            Text(login.codeShown.isEmpty ? 'Check your phone' : 'Code for ${login.mobile.text.trim()}',
                style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
            Text(
              login.codeShown.isEmpty ? 'SMS sent' : login.codeShown,
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: Palette.navy, letterSpacing: 8),
            ),
            Text(login.codeNote, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
          ],
        ),
      ),
      LabeledField(
        label: 'Code',
        required: true,
        child: TextField(
          key: ValueKey<String>(worker ? 'workerCode' : 'citizenCode'),
          controller: login.code,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
          decoration: fieldDecoration(hint: 'Enter the 6-digit code', icon: Icons.shield_outlined),
          onSubmitted: (_) => _verify(worker),
        ),
      ),
      PortalButton(label: 'Log in', icon: Icons.login, busy: _busy, expand: true, onPressed: () => _verify(worker)),
      if (error != null) ErrorText(error),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton(
          onPressed: () => setState(() {
            login.codeSent = false;
            login.verifyError = null;
          }),
          child: const Text('Use a different mobile number'),
        ),
      ),
      signUpLine,
    ];
  }

  List<Widget> _officerForm() {
    final error = _officerError;
    return [
      LabeledField(
        label: 'Username',
        required: true,
        child: TextField(
          controller: _username,
          autocorrect: false,
          decoration: fieldDecoration(hint: 'Your officer username', icon: Icons.person_outline),
        ),
      ),
      LabeledField(
        label: 'Password',
        required: true,
        child: TextField(
          controller: _password,
          obscureText: true,
          decoration: fieldDecoration(hint: 'Password', icon: Icons.lock_outline),
          onSubmitted: (_) => _officerLogin(),
        ),
      ),
      _note('Officer logins end at midnight every day (India time).'),
      PortalButton(label: 'Log in', icon: Icons.login, busy: _busy, expand: true, onPressed: _officerLogin),
      if (error != null) ErrorText(error),
      _signUpLine('New officer?', 'Click here to sign up', () => _openSignUp(LoginTab.officer)),
    ];
  }

  Widget _infoCard(_Words words) {
    final phone = isPhone(context);
    final slides = words.slides;
    final index = _slide % slides.length;
    final slide = slides[index];
    final art = Container(
      width: phone ? 84 : 140,
      height: phone ? 84 : 140,
      decoration: const BoxDecoration(
        color: Palette.white,
        shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: Color(0x12023668), blurRadius: 10, offset: Offset(0, 2))],
      ),
      child: Icon(slide.icon, size: phone ? 42 : 70, color: Palette.primary),
    );
    final text = KeyedSubtree(
      key: ValueKey<String>('$_lang-$index'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            slide.kicker.toUpperCase(),
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Palette.navy, letterSpacing: 1),
          ),
          const SizedBox(height: 2),
          Text(
            slide.title,
            style: TextStyle(fontSize: phone ? 22 : 28, fontWeight: FontWeight.w800, color: Palette.navy),
          ),
          const SizedBox(height: 8),
          Text(slide.text, style: const TextStyle(fontSize: 14.5, color: Palette.labelText, height: 1.5)),
        ],
      ),
    );
    final switcher = AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      layoutBuilder: (current, previous) => Stack(
        alignment: Alignment.centerLeft,
        children: [...previous, if (current != null) current],
      ),
      child: text,
    );
    final round = Container(
      width: 64,
      height: 64,
      decoration: const BoxDecoration(color: Palette.primaryBright, shape: BoxShape.circle),
      child: const Icon(Icons.campaign_outlined, color: Palette.white, size: 28),
    );
    final controls = Row(
      children: [
        _arrow(Icons.chevron_left, () => setState(() => _slide = (index + slides.length - 1) % slides.length)),
        const SizedBox(width: 8),
        _arrow(Icons.chevron_right, () => setState(() => _slide = (index + 1) % slides.length)),
        Expanded(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (var i = 0; i < slides.length; i++)
                GestureDetector(
                  onTap: () => setState(() => _slide = i),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: i == index ? 22 : 9,
                    height: 9,
                    decoration: BoxDecoration(
                      color: i == index ? Palette.primary : const Color(0xFFB9CFE6),
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (!phone) const SizedBox(width: 68),
      ],
    );
    return Container(
      padding: EdgeInsets.fromLTRB(phone ? 18 : 26, 22, phone ? 18 : 26, 16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFFDCEFFF), Color(0xFFEEF7FF), Color(0xFFE3F2FF)],
          stops: [0, 0.6, 1],
        ),
        border: Border.all(color: Palette.cardEdge),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (phone)
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [art, const SizedBox(height: 14), switcher])
          else
            Row(
              children: [
                art,
                const SizedBox(width: 22),
                Expanded(child: switcher),
                const SizedBox(width: 22),
                round,
              ],
            ),
          const SizedBox(height: 10),
          controls,
        ],
      ),
    );
  }

  Widget _arrow(IconData icon, VoidCallback onTap) {
    return InkWell(
      customBorder: const CircleBorder(),
      onTap: onTap,
      child: Container(
        width: 30,
        height: 30,
        decoration: BoxDecoration(
          color: Palette.white,
          shape: BoxShape.circle,
          border: Border.all(color: Palette.line),
        ),
        child: Icon(icon, size: 18, color: Palette.navy),
      ),
    );
  }
}
