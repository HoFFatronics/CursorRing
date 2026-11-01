# CursorRing

Ett litet Pythonprogram för Windows som visar en färgad ring runt muspekaren. Ringen är inbyggd i den anpassade Windows-muspekaren, inte ett separat överläggsfönster. Avsett för exempelvis skärminspelning av kartor med gröna terrängområden och blå/röda territorier.

## Färgprofiler

Tre färger kan konfigureras i [config.json](config.json):

| Profil | Standardvärde | Syfte |
| --- | --- | --- |
| `yellow` | `#FFE500` | **Standard.** Hög synlighet mot blått och rött, med konturer för grön terräng. |
| `white` | `#FFFFFF` | Alternativ för mörka kartor. |
| `black` | `#111111` | Alternativ för ljusa kartor. |

Alla tre profilerna har **svart och vit kontur** runt ringen. Därmed kräver inte pekaren att betraktaren kan skilja på rött och grönt, och den blir lättare att se på både ljusa och mörka kartområden. Färgerna är rekommenderade utgångsvärden, inte en garanti för alla kartstilar eller synförutsättningar.

Ändra valfria HEX-färger och `default_color` i `config.json`. Det ska finnas **exakt tre** namngivna färgprofiler.

## Snabbtangent för att hitta pekaren

Tryck **Ctrl+Alt+R** när CursorRing körs. Då blinkar ringen och växer/krymper **tre gånger under 2,4 sekunder**. Därefter återgår den till normal storlek. Muspilen syns hela tiden, med oförändrad klickpunkt.

Tryck snabbtangenten igen för att starta om animationen. Tangentkombination och effektlängd ändras i `config.json`:

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

Använd `ctrl`, `alt` och/eller `shift` tillsammans med en bokstav, siffra eller `F1` till `F11`. Minst en modifierare krävs. `animation_seconds` kan vara 0,5 till 10 sekunder.

Programmet använder `RegisterHotKey` för systemövergripande snabbkommando och byter förgenererade muspekare via `SetSystemCursor`. På så sätt behövs inget separat överläggsfönster.
## Installation och körning

Kräver Windows 10 eller 11, Python 3.10+ och Pillow.

```powershell
python -m pip install -r requirements.txt
python cursor_ring.py
```

Programmet väljer automatiskt `default_color` från `config.json`. Välj en annan profil vid start:

```powershell
python cursor_ring.py --color white
python cursor_ring.py --color black
python cursor_ring.py --list-colors
```

Låt terminalen vara öppen och avsluta med `Ctrl+C`. Då återställs Windows vanliga muspekare. Efter oväntad avslutning kan du återställa den manuellt:

```powershell
python cursor_ring.py --restore
```

Du kan även välja en annan konfigurationsfil med `--config sökväg/till/config.json`.

## Inspelning

Välj att spela in **muspekaren** i inspelningsprogrammet. I OBS Studio kan du prova fönsterinspelning med **Capture Cursor** aktiverat. Gör en kort testinspelning eftersom olika metoder kan behandla anpassade pekare olika.

## Teknik och begränsningar

- Programmet skapar en transparent 64 × 64-pixlars `.cur`-fil med en ring och ett svartvitt pilhuvud.
- Klickpunkten (hotspot) är i ringens centrum.
- Det ersätter tillfälligt Windows pilpekare och handpekare (handpekaren får också pilform).
- Andra pekartyper, som textmarkörer eller programunika specialpekare, omfattas inte.
- Ändringen påverkar Windows muspekare i hela sessionen, inte bara ett fönster.
- Funktion och inspelningsresultat måste fortfarande verifieras i Windows.

## Test

```powershell
python -m unittest discover -s tests -v
```
