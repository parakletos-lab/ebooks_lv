# Lietotāju pārvaldība

Šī ir vienkāršota ikdienas rokasgrāmata lietotāju atbalstam **ebooks.lv**.

Visbiežāk izmantosiet **Mozello Pasūtījumu** administrēšanu:

- **Pasūtījumu lapa**: [/admin/ebookslv/orders/](/admin/ebookslv/orders/)

---

## 1) Ko šeit var izdarīt

No **Pasūtījumu lapas** iespējams:

- Importēt apmaksātus pasūtījumus no Mozello (lai piešķirtu piekļuvi)
- Pievienot manuālu pasūtījuma ierakstu (lai piešķirtu piekļuvi)
- Izveidot vai piesaistīt Calibre lietotāju klientam
- Atsvaidzināt pasūtījuma ierakstu (pārbaudīt grāmatas/lietotāja sasaisti)
- Dzēst pasūtījuma ierakstu (atņem piekļuvi ebooks.lv; Mozello netiek mainīts)

---

## 2) Biežākie uzdevumi

### 2.1 Klients nopirka grāmatu, bet to neredz

1. Atveriet **Pasūtījumu lapu** [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. Nospiediet **Importēt apmaksātos Mozello pasūtījumus**.
   - Izmantojiet datumu intervālu (pēc noklusējuma ~pēdējās 10 dienas).
3. Atrodiet klienta rindu pēc **E-pasts**.
4. Ja **Calibre grāmata nav atrasta** ir sarkans, nospiediet **Atsvaidzināt**.
5. Ja **Calibre lietotājs nav piesaistīts**, nospiediet **Izveidot lietotāju**.
   - Ja lietotājs jau eksistē, sistēma piesaistīs esošo kontu.

Rezultāts:
- Pasūtījuma rindā jābūt zaļam **Calibre grāmata** un zaļam **Calibre lietotājs**.

### 2.2 Manuāli piešķirt piekļuvi (izveidot lietotāju ↔ grāmatu sasaisti)

Izmantojiet, ja klients ir samaksājis, bet webhook/imports nav ienācis, vai citi manuāla atbalsta gadījumi.

1. Atveriet **Pasūtījumu lapu** [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. Formā **Pievienot pasūtījumu**:
   - Ievadiet klienta **E-pasts**.
   - Ievadiet nopirktās grāmatas **Mozello identifikators**, piemēram, `book-123`.
3. Nospiediet **Pievienot pasūtījumu**.
4. Ja rindā zem **Calibre lietotājs** ir “Nav piesaistīts”, nospiediet **Izveidot lietotāju**.
5. Ja rindā ir “Calibre grāmata nav atrasta”, nospiediet **Atsvaidzināt**.

Piezīme:
- Ja nezināt identifikatoru, atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/) un tabulā atrodiet grāmatu un tās Mozello identifikatoru.

### 2.3 Klients nevar ielogoties / aizmirsis paroli

- Lūdziet klientam izmantot pogu **Aizmirsi paroli?** lapā [/login](/login).
- Ja e-pastu sūtīšana ir konfigurēta, tiks nosūtīts paroles atiestatīšanas e-pasts.

Ja joprojām nevar atiestatīt:
- Pārbaudiet, vai pasūtījuma ierakstā e-pasts ir pareizs.
- Ja nepieciešams, nospiediet **Izveidot lietotāju**, lai pārliecinātos, ka konts eksistē.

#### Paroles noteikumi (svarīgi pārlūka ģenerētām parolēm)

Ja pārlūka ieteiktā parole tiek noraidīta, tas notiek Calibre-Web iestatījumu dēļ **Lietotāja paroles politika**.

Kur konfigurēt:
- [/admin/config](/admin/config) → **Rediģēt pamatkonfigurāciju** → sadaļa **Lietotāja paroles politika**.

Iestatījumi, kas kontrolē validāciju:
- **Lietotāja paroles politika** (ON/OFF)
- **Minimālais paroles garums** (`config_password_min_length`)
- **Skaitļu prasība** (`config_password_number`)
- **Mazajiem burtiem prasība** (`config_password_lower`)
- **Lielajiem burtiem prasība** (`config_password_upper`)
- **Speciālo simbolu prasība** (`config_password_special`)

Ieteicamie iestatījumi pārlūka ģenerētām parolēm:
- **Lietotāja paroles politika = ON**
- **Minimālais paroles garums = 12** (vai `10` pēc vajadzības)
- Ieslēgt **Skaitļu / mazo / lielo burtu prasību**
- Izslēgt **Speciālo simbolu prasību** (daudzi pārlūki neiekļauj simbolus ieteiktajās parolēs)

Lai pieņemtu jebkuru pārlūka ieteikto paroli:
- **Lietotāja paroles politika = OFF**

### 2.4 Atņemt piekļuvi (noņemt nopirktu grāmatu lietotājam)

1. Atveriet **Pasūtījumu lapu** [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. Atrodiet pasūtījuma ieraksta rindu.
3. Nospiediet atkritnes ikonu (**Dzēst**) un apstipriniet.

Svarīgi:
- Tiek dzēsts tikai **lokālais piekļuves ieraksts**.
- Mozello pusē nekas netiek mainīts vai atmaksāts.

### 2.5 Dublikāti / nepareizs e-pasts

- Ja pasūtījuma rinda izveidota ar nepareizu e-pastu vai identifikatoru, **Dzēst** un izveidojiet pareizu ierakstu.
- Ja ir vairāki dublikāti vienam lietotājam un identifikatoram, izdzēsiet liekos.

---

## 3) Ātrā problēmu novēršana

### 3.1 Calibre grāmata nav atrasta

Biežākie iemesli:
- Mozello identifikators neatbilst nevienai eksportētai grāmatai.
- Grāmata ir Mozello, bet nekad nav eksportēta ar Books Sync rīku.

Risinājums:
- Atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/) un eksportējiet/sinhronizējiet grāmatu.
- Atgriezieties **Pasūtījumu lapā** un nospiediet **Atsvaidzināt**.

### 3.2 Izveidot lietotāju neizdodas

Biežākais iemesls:
- Calibre izpildlaiks nav pieejams.

Risinājums:
- Mēģiniet vēlāk.
- Ja lietotājs jau eksistē, nospiediet **Pārlādēt** **Pasūtījumu lapā** un tad vēlreiz **Izveidot lietotāju** — tas piesaistīs esošo kontu.

---
