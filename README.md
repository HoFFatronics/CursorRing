# CursorRing

Ett litet Pythonprogram för Windows som visar en röd ring runt muspekaren. Ringen är inbyggd i den anpassade Windows-muspekaren, inte ett separat överläggsfönster. Avsett som pekarhjälp vid exempelvis skärminspelning av kartor och presentationer.

## Krav

- Windows 10 eller 11
- Python 3.10 eller senare
- Pillow

## Installation och körning

```powershell
python -m pip install -r requirements.txt
python cursor_ring.py
```

Låt terminalen vara öppen medan ringen används. Stoppa med `Ctrl+C` i terminalen. Då återställs Windows vanliga muspekare.

Om Pythonprocessen avslutas oväntat och muspekaren inte återställs:

```powershell
python cursor_ring.py --restore
```

## Inspelning

Välj alternativet att spela in **muspekaren** i inspelningsprogrammet. För OBS Studio, testa fönsterinspelning med **Capture Cursor** aktiverat. Kontrollera med en kort testinspelning, eftersom olika inspelningsmetoder kan behandla anpassade pekare olika.

## Vad programmet gör

- Skapar en 64 × 64 pixlars `.cur`-fil med genomskinlig bakgrund och en röd ring.
- Sätter klickpunkten (hotspot) i ringens centrum.
- Ersätter Windows vanliga pilpekare och handpekare tillfälligt.
- Återställer standardpekarna vid normal avslutning.

## Begränsningar

- Ändringen påverkar Windows systempekare i hela användarsessionen, inte bara kartfönstret.
- Andra pekartyper, till exempel textmarkören eller specialpekare i enskilda program, omfattas inte av första versionen.
- Windows skärm- och tillgänglighetsinställningar samt inspelningsprogram kan påverka resultatet.
- Skriptet är syntaxkontrollerat, men ska funktionstestas på Windows före användning vid viktig inspelning.
