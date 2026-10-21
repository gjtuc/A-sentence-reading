# 436 — The web's reading look on the phone, and more fonts

## Ask

Give the phone the web reader's line spacing, line width and page colour. On
both the web and the phone, offer current fonts that are good for reading papers.

## Change

- Line height is its own setting, 줄 간격: 보통 / 넓게 / 아주 넓게 (web 1.6 / 1.9 /
  2.2; phone keeps the theme's 1.5 for 보통). 글자 간격 now changes only letters
  and words. Until 줄 간격 is chosen, a saved wide 글자 간격 still brings wide
  lines, as before.
- Fonts, bundled (SIL Open Font License, static instances from Google Fonts,
  regular, italic and bold, about 1.6 MB in all; licences in
  `assets/fonts/OFL-*.txt`):
  - 기본 — the platform font;
  - Inter — a clean sans for screens;
  - Atkinson Hyperlegible — made to tell l, I and 1 apart;
  - Source Serif 4 — the earlier 책 글꼴, still saved as `serif`;
  - Literata — the serif made for Google Play Books.

  Korean has no glyphs in these and falls back to the device font.
- Phone settings, 읽기 화면: 문장 글자 크기 (design/435), 줄 간격, 글자 간격, 줄 폭,
  글꼴, 화면 색, with a sample sentence drawn in the chosen look.
  - 줄 폭 on a phone is the side margin inside the sentence card: 좁게 40, 보통
    16 (the old margin), 넓게 6 px.
  - 화면 색: 앱 테마 (follows 테마, the default), 어두운 회색, 종이색, 흰색. A colour
    paints every screen, as on the web (design/420). It is saved apart from the
    web's, whose default is 어두운 회색.
- Web settings gain 줄 간격 and the new fonts.

Files: `state/web_reading_prefs.dart` (`WebLineGap`, `kReadingFontFamily`),
`state/reader_prefs.dart` (`phoneSentenceStyle`, `kPhoneColumnInset`, `page`),
`screens/settings_screen.dart`, `screens/reader_screen.dart`, `app.dart`,
`pubspec.yaml`.

## Not covered

- No Korean font is bundled; a full Korean font adds several MB to the app and
  to the web download.
