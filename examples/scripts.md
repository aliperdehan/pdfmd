# One document, many scripts

pdfmd sets each script in a font that has it, and finds the document by name too.

| Script | Sample | Notes |
|---|---|---|
| Kazakh | Қазақ тілі: әріптер ә ғ қ ң ө ұ ү һ і | Cyrillic letters STIX Two Text lacks |
| Greek | Τύχη, η φύση της εντροπίας | `pdfmd tyche` finds `Τύχη.md` with `--translit greek` |
| Arabic | اللغة العربية تُكتب من اليمين إلى اليسار | set right to left |
| Hebrew | עברית נכתבת מימין לשמאל | set right to left |
| Chinese | 熵是系统无序程度的度量 | Songti or Noto Serif CJK |
| Japanese | エントロピーは乱雑さの尺度です | kana set in the Japanese flavour |
| Korean | 엔트로피는 무질서의 척도입니다 | `pdfmd unmyeong` finds `운명.md` |
| Hindi | एन्ट्रॉपी अव्यवस्था की माप है | Devanagari |

Emoji are pictures, not boxes: 🚀 ✅ 🧪 🇰🇿 👩‍🔬 👍🏽.

Math and code keep their own fonts: $\Delta S \geq q/T$, and `print("σ → ∞")`.
