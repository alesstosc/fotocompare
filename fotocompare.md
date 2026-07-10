# Fotocompare — specifiche

## Obiettivo
App/script che compara foto tra due directory e trova immagini identiche a livello di pixel.

## Approccio
- Hash dei file (SHA256) per identificazione pixel-identiche.
- Opzioni: hash rapido (primi 64KB + metadata) vs hash completo (full file).
- Directory A → hash map, Directory B → match hash.

## Hash rapido — specifica
1. Per ogni file, leggi dimensione. Skip immediato se dimensione diversa.
2. Se dimensione uguale, hash primi 64KB. Stop qui per flag "probabile duplicato".
3. Hash completo solo su richiesta per conferma definitiva.
4. Metadata (data modifica, nome) extra hint, non fonte di verità.

## Post-scan — destinazione duplicati
1. Scan finito, mostra lista duplicati raggruppati.
2. Popup/finestra chiede dove spostare file duplicati.
3. Default: cestino/trash.
4. Utente può cambiare destinazione (picker directory).
5. Conferma → spostamento eseguito.

## Rinomina automatica
1. Rileva nomi generici/sequenziali (es. foto001.jpg, IMG_1234.jpg).
2. EXIF data scatto presente → rinomina in `YYYY-MM-DD_HHmmss.jpg`.
3. EXIF assente → skip, nome originale resta.
4. Rinomina solo source dir, non destinazione.
5. Dry-run opzionale ante applicazione.

## Selezione directory / HD
1. UI o prompt per scegliere source dir e target dir all'avvio.
2. Supporto path assoluti su qualsiasi mount/drive.
3. Path recenti salvati per riuso veloce.
4. Validazione: directory esiste, leggibile, non vuota.

## Stack tecnologico
- **Linguaggio:** Python
- **UI:** Tkinter (built-in, popup/filedialog nativi)
- **EXIF:** Pillow (PIL)
- **Hashing:** hashlib (SHA256)
- **Packaging:** PyInstaller → singolo eseguibile
- **Target:** cross-platform (Win/Mac/Linux)

## Build
- Eseguibile creato: `dist/fotocompare` (19MB, Linux x64)
- Build command: `pyinstaller --onefile --name fotocompare fotocompare.py`
