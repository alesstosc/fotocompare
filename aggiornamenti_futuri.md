# Aggiornamenti futuri

## EXIF — Lettura DateTimeOriginal (36867) vs DateTime (306)

Attuale `get_exif_date()` usa PIL puro `img.getexif().items()`. Questo trova solo tag IFD0, tra cui `DateTime` (306, data modifica file).

Il tag `DateTimeOriginal` (36867, data scatto originale) sta in Exif sub-IFD (0x8769). Non visibile con `.items()`.

### Impatto
- Foto con solo `DateTimeOriginal` (es. da molte fotocamere) **non vengono rinominate**.
- `DateTime` (306) è spesso assente o diverso dalla data scatto.

### Fix
Opzione A — Aggiungere `exif.get_ifd(0x8769)` per leggere sub-IFD (PIL 8.0+):
```python
exif = img.getexif()
exif_ifd = exif.get_ifd(0x8769)  # ExifIFD
dt = exif_ifd.get(36867)  # DateTimeOriginal
```

Opzione B — Usare `piexif` per lettura affidabile di tutti i tag EXIF:
```python
import piexif
exif_dict = piexif.load(exif_raw)
dt = exif_dict.get('Exif', {}).get(piexif.ExifIFD.DateTimeOriginal)
```

Opzione C — Scrivere sempre `DateTime` (306) oltre a `DateTimeOriginal` nei file generati, così la versione corrente lo legge.

## Pacchettizzazione

- `pyinstaller --onefile --hidden-import piexif` per includere piexif nel binario (altrimenti fallback a PIL puro).
- Su Windows: GitHub Actions produce .exe automaticamente.

## Test data

Ref: `generate_test_photos.py` (non più in uso, tenere come riferimento per debugging).
