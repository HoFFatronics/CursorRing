# CursorRing

**CursorRing** är ett litet Pythonprogram för Windows som markerar muspekaren med en tydlig, färgad ring. Programmet är främst avsett för presentatörer som pekar på kartor under **skärminspelning**, även när bara ett enskilt programfönster spelas in.

**Viktigt för vidareutveckling i Codex:** Projektet är en första prototyp. Funktionerna finns i koden men **har inte verifierats praktiskt i Windows eller i en inspelning**. Se [Status, kända problem och nästa steg](#status-kända-problem-och-nästa-steg).

## Mål och designbeslut

- Ringen ska vara lätt att hitta på en karta med **grön terräng**, **blått eget territorium** och **rött motståndarterritorium**.
- Den ska vara användbar för både personer med normalt färgseende och personer med vanlig **röd-grön färgseendevariation** (protan/deutan). Ljushetskontrast och svartvita konturer är därför viktigare än att bara skilja på två kulörer.
- **Standardfärgen är gul** med vit och svart kontur. Tre konfigurerbara färgprofiler ska finnas.
- Muspekaren ska fungera normalt för att klicka, dra och navigera i kartan. Den grafiska markeringens klickpunkt (hotspot) får inte förskjutas.
- **Ctrl+Alt+R** ska tillfälligt få ringen att blinka och pulsera i storlek så att tittaren lätt hittar pekaren. Effekten ska avslutas automatiskt och kunna startas om.
- Ringen ska i första hand vara en del av en **anpassad Windows-muspekare**, inte ett fristående transparent overlay-fönster. Motivet är att en vanlig fönsterinspelning ofta spelar in muspekaren men kan utelämna överlägg från andra fönster. Detta behöver fortfarande testas med faktiska inspelningsprogram.
- Håll implementationen enkel och resurssnål. Det behövs ingen spelmotor, ingen server och ingen muspositionspollning.

## Kom igång i Windows

Krav: **Windows 10 eller 11**, **Python 3.10+** och **Pillow**. Övriga Pythonmoduler är från standardbiblioteket.

```powershell
git clone https://github.com/HoFFatronics/CursorRing.git
cd CursorRing
python -m pip install -r requirements.txt
python cursor_ring.py
```

När programmet körs är ringen synlig. Tryck **Ctrl+Alt+R** för att aktivera hitta-effekten. Håll terminalen öppen och avsluta med **Ctrl+C**. Programmet försöker då återställa Windows systempekare.

Andra kommandon:

```powershell
python cursor_ring.py --color white
python cursor_ring.py --color black
python cursor_ring.py --list-colors
python cursor_ring.py --config .\config.json
python cursor_ring.py --restore
```

`--restore` försöker återställa Windows pekarschema även om den föregående processen har avslutats oväntat. Om Windows inte kan återställa pekaren automatiskt kan pekarschemat även ändras i Windows musinställningar.

**Observera:** Programmet ändrar för närvarande systempekare **i hela Windows-sessionen**, inte enbart i ett specifikt kartfönster. Testa inte för första gången mitt under en viktig presentation.

## Konfiguration

Inställningarna finns i [config.json](config.json):

```json
{
  "default_color": "yellow",
  "colors": {
    "yellow": "#FFE500",
    "white": "#FFFFFF",
    "black": "#111111"
  },
  "hotkey": "ctrl+alt+r",
  "animation_seconds": 2.4
}
```

| Inställning | Nuvarande beteende |
| --- | --- |
| `default_color` | Namnet på profilen som används när `--color` inte anges. |
| `colors` | **Exakt tre** namngivna profiler. Värden är RGB i format `#RRGGBB`. Namnen kan ändras om `default_color` och kommandoradsargument följer med. |
| `hotkey` | Global snabbtangent. En eller flera av `ctrl`, `alt`, `shift`, samt en bokstav, siffra eller `F1` till `F11`. Exempel: `ctrl+alt+r`. |
| `animation_seconds` | Animationens totala längd i sekunder, mellan **0,5 och 10**. Standard **2,4**. |

`--color <profil>` överstyr standardprofilen för den aktuella körningen. `--config <fil>` väljer annan konfigurationsfil. Inställningarna läses vid **uppstart**, inte dynamiskt.

### Färgprofiler och tillgänglighet

| Profil | HEX | Användning |
| --- | --- | --- |
| **Gul (standard)** | `#FFE500` | Föreslagen standard för karta med grön terräng och blå/röda territorier. |
| **Vit** | `#FFFFFF` | Alternativ på övervägande mörka kartor. |
| **Svart** | `#111111` | Alternativ på övervägande ljusa kartor. |

Ringen har **svart ytterkontur och vit mellanliggande kontur** runt profilfärgen. Syftet är synlighet mot varierande ljushet, inte att användaren måste kunna skilja mellan rött och grönt. Valet är en **designhypotes som behöver utvärderas visuellt**, inte en verifierad tillgänglighetsgaranti. Verifiera gärna med representativa kartbilder, både normalt färgseende och simulerad protanopi/deuteranopi.

## Funktionellt beteende

**Normalläge:** En stillastående ring visas runt muspilen. Standardringens basradie är `23` pixlar.

**Hitta-effekt:** När den registrerade globala snabbtangenten trycks startas en tidsbegränsad animation:

1. Ringens radie varierar mellan **18 och 36 pixlar**, med **tre pulser** över den konfigurerade varaktigheten.
2. Ringen blinkar, medan **själva muspilen fortsätter vara synlig**.
3. Efter animationen återgår den vanliga ringen.
4. Om snabbtangenten trycks igen under effekten startar animationen om från början.

Förgenererade muspekarbilder används för olika storlekar och för ett läge utan synlig ring. Bildväxling sker med en målfrekvens på cirka **15 bildrutor per sekund**. Detta är vad koden försöker göra, inte en uppmätt prestandagaranti.

## Projektstruktur

```text
CursorRing/
├── cursor_ring.py             # Program, CUR-generator, Windows-API och animation
├── config.json                # Tre färgprofiler, global snabbtangent och varaktighet
├── requirements.txt           # Pillow
├── tests/
│   └── test_cursor_ring.py    # unittest, konfiguration och bild/animation
├── .gitignore
└── README.md                  # Användning och utvecklaröverlämning
```

### Arkitektur för Codex

All kod ligger idag i [cursor_ring.py](cursor_ring.py):

| Funktion/komponent | Ansvar |
| --- | --- |
| `parse_hex_color()` | Validerar `#RRGGBB` och konverterar till RGBA. |
| `parse_hotkey()` | Tolkar textbaserad snabbtangent till Windows modifierarflaggor och virtual-key-kod. |
| `load_settings()` | Läser/validerar JSON och returnerar standardprofil, profilfärger, snabbtangent och animationstid. |
| `animation_frame()` | Beräknar aktuell radie/synlighet utifrån förfluten animationstid. Oberoende av Windows. |
| `create_cursor()` | Renderar ring och pil med Pillow och skriver en **32-bitars `.cur`-fil**. |
| `prepare_frames()` | Genererar i förväg normalpekare, pil utan ring och flera ringstorlekar i temporär katalog. |
| `windows_api()` | Deklarerar `ctypes`-signaturer för `user32.dll`. |
| `enable()` | Läser in `.cur` och ersätter systempekarna för normal pil och hand. |
| `restore()` | Anropar `SystemParametersInfoW(SPI_SETCURSORS)` för att återläsa systemets pekarschema. |
| `run()` | Registrerar global snabbtangent, hanterar meddelandekö, styr animationen och försöker återställa resurser. |
| `main()` | Kommandoradsgränssnitt, konfiguration, start och avslut. |

Detaljer att bevara eller utvärdera vid refaktorering:

- Pekarbildens canvas är **96 × 96 pixlar**, med **hotspot på (48, 48)**. Bilden ritas först med 4× upplösning för kantutjämning.
- Formatet `.cur` byggs manuellt med CUR-header, DIB/BGRA-data och en transparensmask (AND-mask). Pillow skapar bildinnehållet.
- `SetSystemCursor` används för `OCR_NORMAL=32512` och `OCR_HAND=32649`. **Handpekaren byts också till en pilform**, vilket är en begränsning.
- `RegisterHotKey` registrerar snabbtangenten i trådens meddelandekö. `PeekMessageW` tar emot `WM_HOTKEY`. Det behövs inget externt tangentbordsbibliotek.
- `SetSystemCursor` tar över ägarskapet för ett lyckat överlämnat pekarhandtag. Hantering av handtag och upprepade byten bör Windows-testas och helst granskas särskilt.
- Temporära `.cur`-filer används under körningen. Normalt återskapas pekarschemat och katalogen städas vid avslutning.

## Skärminspelning

Tanken är att spela in en **kartapplikations fönster** och ändå få med ringen som en del av muspekaren, utan att behöva spela in hela bildskärmen.

I OBS Studio: prova en källa av typen **Window Capture/Fönsterinspelning** med **Capture Cursor** aktiverat. Gör sedan en riktig testinspelning.

**Inte verifierat:** Olika OBS-capture-metoder, Windows-versioner och program kan hantera egna systempekare på olika sätt. Program som själva renderar sina pekare kan förbigå den modifierade Windows-pekaren. Om Windows-baserade systempekare inte fångas i målprogrammet måste lösningen omprövas, exempelvis genom ett separat overlay och en annan inspelningsmetod.

## Tester

Från projektets rot:

```powershell
python -m unittest discover -s tests -v
```

Tester ska kunna köras utan att modifiera Windows-systempekare. Testa i synnerhet konfigurationsfel, geometri/format/hotspot, animationsberäkning, snabbtangentsparser och temporära bildfiler. Verklig integration mot `user32.dll` måste testas på Windows.

### Känd testbrist i nuvarande commit

**Kontrollera detta först i Codex.** I [tests/test_cursor_ring.py](tests/test_cursor_ring.py) används `parse_hotkey`, `animation_frame` och `prepare_frames`, men de finns **inte med i filens import från `cursor_ring`**. Det innebär att dessa testmetoder väntas få `NameError` när de körs. Något grönt testresultat för nuvarande kodbas ska därför inte antas. Testnamnet `test_cursor_file_is_64px_with_center_hotspot` är också missvisande, eftersom det nu kontrollerar **96 × 96**.

Fixa testimporter/namngivning, kör hela sviten och lägg sedan till regressionstester för restaurering och felvägar där det går att mocka Windows-API-anrop.

## Status, kända problem och nästa steg

**Implementerat i kod:** tre färgprofiler, konfigurationsfil, Windows-systempekare, återställningskommando, global snabbtangent och blinkande/pulserande animation.

**Inte verifierat:** verklig visning och animering i Windows, hotkey-registrering, långvarig stabilitet, prestanda, originalpekarens återställning eller medverkan i fönsterinspelning.

### Prioriterad fortsättningsplan

1. **Gör testerna gröna.** Åtgärda de kända saknade importerna och namnet för 96-pixeltestet. Kör `unittest` och komplettera tester vid behov.
2. **Kör ett manuellt Windows-smoketest.** Installera krav, starta programmet, kontrollera pil/hand, färgval, snabbkommando, pulsering, återställning med `Ctrl+C` och `--restore`.
3. **Verifiera fönsterinspelning.** Spela in en verklig karta med grön/blå/röd bakgrund. Kontrollera att både normalläge och animation syns i den inspelade filen, inte bara på skärmen.
4. **Granska den globala pekarhanteringen.** Bedöm blinkning/flicker och resursanvändning från frekventa `SetSystemCursor`-anrop, särskilt efter längre körning, vid andra pekartyper och vid avvikande avslutning.
5. **Utvärdera tillgänglighet och UX.** Kontrollera färgkontrast i representativa kartor inklusive färgseendesimulering. Justera storlek, linjebredd, blinkfrekvens och tangentkombination utifrån tester, inte enbart antaganden.

### Manuella acceptanskriterier

- [ ] Skriptet startar på Windows med `python cursor_ring.py`.
- [ ] Standardprofilen är gul. `--color white` och `--color black` fungerar.
- [ ] Normalläge och hitta-effekt syns tydligt mot grönt, blått och rött i kartan.
- [ ] `Ctrl+Alt+R` triggar tre pulser, muspilen förblir synlig och en ny tryckning startar om.
- [ ] Klick och drag i kartan fungerar och klickpunkten ligger kvar på rätt position.
- [ ] Pekaren återställs efter normalt avslut samt med `--restore`.
- [ ] OBS fönsterinspelning inkluderar ring och animation i själva videofilen.
- [ ] Automatiserade tester går igenom på en ren installation.

## Föreslagen första uppgift till Codex

> Läs README.md, cursor_ring.py, config.json och tests/test_cursor_ring.py. Börja med att rätta de dokumenterade testbristerna och köra testsviten. Granska därefter särskilt Win32-anropen, resursägarskap och möjligheten att återställa pekaren vid fel. Bevara målet med en ring som kan fångas som muspekare vid fönsterinspelning, de tre konfigurerbara högkontrastfärgerna och Ctrl+Alt+R-animationen. Beskriv vilka delar du faktiskt kan verifiera på din miljö och vilka som kräver manuellt Windows- och OBS-test. Gör små, tydliga commits och håll README uppdaterad.

---

**Källan till sanningen är alltid den aktuella koden och konfigurationen i detta repo.** Om README avviker från implementationen ska Codex notera avvikelsen, verifiera önskat beteende och uppdatera dokumentationen tillsammans med kodändringen.
