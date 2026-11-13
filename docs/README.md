# Heli Controller: telefon jako ovladač vrtulníku

Telefon držený naplocho se naklání a otáčí. Data jdou po Wi-Fi na PC, kde se
mění na virtuální Xbox ovladač. Hra (Arma 3, Wardogs) ho vidí jako běžný gamepad.

```
[Android appka] --UDP JSON 50x/s--> [receiver.py na PC] --vJoy--> [virtuální joystick] --> [hra]
```

## Mapování

| Telefon                          | Ovladač                       |
|----------------------------------|-------------------------------|
| náklon dopředu/dozadu            | levá páka Y (cyklická)        |
| náklon do stran                  | levá páka X (cyklická)        |
| otočení telefonu kolem osy       | pravá páka X (pedály / yaw)   |
| slider Kolektiv nahoru / dolů    | RT / LT (kolektiv)            |
| tlačítka na displeji             | A, B, X, Y, LB, RB, Start, Back |

Tlačítka a jejich popisky se nastavují v profilech. Přiřazení ve hře dělá
uživatel v nastavení ovládání hry.

---

## 1. Část pro PC (Windows)

### Instalace
1. Nainstaluj **Python 3.12+** (zaškrtni „Add python.exe to PATH“).
2. Nainstaluj **vJoy** z https://sourceforge.net/projects/vjoystick/ (výchozí nastavení). Virtuální joystick 1 je nastaven automaticky.
3. Ve složce `pc/` spusť:
   ```
   python -m pip install -r requirements.txt
   ```

### Firewall (jednou, jako správce)
```
netsh advfirewall firewall add rule name="HeliController UDP" dir=in action=allow protocol=UDP localport=47800 profile=private
```
IP adresu PC zjistíš příkazem `ipconfig` (položka IPv4, např. `192.168.0.10`).

### Test bez ovladače
```
python test_receiver.py
python receiver.py --dry-run
```
Druhé okno: `python fake_phone.py --host 127.0.0.1`. Hodnoty by se měly vypisovat.

### Ostré spuštění
```
python receiver.py
```
Pak otevři **Joy.cpl** (Ovladače her) a ověř, že se objevil „Xbox 360 Controller“ a reaguje na pohyb.

### Steam Input
Pokud hra běží přes Steam, vypni pro ni Steam Input (Vlastnosti hry → Ovladač → Přepsat nastavení Steam Input), jinak Steam může ovladač přemapovat.

### Export do .exe
```
build_exe.bat
```
Výsledek je v `dist\receiver\receiver.exe`. vJoy musí být nainstalovaný i u exe.

---

## 2. Část pro telefon (Android)

### Sestavení
1. Otevři složku `android/` v **Android Studiu** (Hedgehog nebo novější).
2. Build → Build APK, nebo Run na připojeném telefonu (USB ladění).
3. APK je v `app/build/outputs/apk/debug/`.

### Použití
1. Spusť appku na telefonu. Telefon a PC musí být ve stejné síti.
2. Do políčka IP napiš adresu PC a stiskni **Připojit**.
3. Polož telefon naplocho, vyber profil a stiskni **Střed** (nastaví nulovou polohu).
4. Ve hře nastav ovládání: levá páka = cyklická, pravá páka X = pedály, RT/LT = kolektiv.

### Profily
Tlačítko **Profily** otevře JSON s profily (tlačítka, popisky, citlivost). Změny se ukládají do telefonu.
Bit tlačítka musí být 0 až 7 a odpovídá klíčům `buttons` v `pc/config.json`.

---

## 3. Ladění citlivosti

- **Telefon (profil):** `pitchScale`, `rollScale`, `yawScale` (1.0 = výchozí, menší = jemnější).
- **PC (`pc/config.json`):**
  - `deadzone`: mrtvé pásmo kolem nuly (0.05 = 5 %).
  - `invert`: převrátí osu (pokud se ovládání chová opačně).
  - `sensitivity`: citlivost osy na PC.
  - `timeout_s`: po jak dlouhé ztrátě spojení se ovladač vrátí do středu.

Pokud se páka ve hře pohybuje opačným směrem, přepni `invert` pro danou osu.

---

## Známé omezení

- Yaw se odvozuje z natočení telefonu. Telefon může po delší době driftovat, proto tlačítko **Střed** před letem.
- Protokol je nezabezpečený (UDP bez šifrování). Určeno pro domácí síť.
- Kolektiv je posuvník, který drží polohu. Vrácení do nuly je ručně.
