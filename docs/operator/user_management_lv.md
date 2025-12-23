# Lietotāju pārvaldība (Operators)

Šī ir vienkāršota ikdienas rokasgrāmata lietotāju atbalstam.

Visbiežāk izmantosiet **Mozello Orders** administrēšanu:

- Orders lapa: `/admin/ebookslv/orders/`

---

## 1) Ko šeit var izdarīt

No Orders lapas var:

- Importēt apmaksātus pasūtījumus no Mozello (lai piešķirtu piekļuvi)
- Pievienot manuālu pasūtījuma ierakstu (lai piešķirtu piekļuvi)
- Izveidot (vai piesaistīt) Calibre lietotāju klientam
- Atsvaidzināt pasūtījuma ierakstu (pārbaudīt grāmatas/lietotāja sasaisti)
- Dzēst pasūtījuma ierakstu (atņem piekļuvi ebooks.lv; Mozello netiek mainīts)

---

## 2) Biežākie uzdevumi

### 2.1 Klients nopirka grāmatu, bet to neredz

1. Atveriet `/admin/ebookslv/orders/`.
2. Nospiediet **Import paid Mozello orders**.
   - Izmantojiet datumu intervālu (pēc noklusējuma ~pēdējās 10 dienas).
3. Atrodiet klienta rindu pēc **Email**.
4. Ja **Calibre book** ir sarkans / nav atrasts, nospiediet **Refresh** šai rindai.
5. Ja **Calibre user** ir “Not linked”, nospiediet **Create User**.
   - Ja lietotājs jau eksistē, sistēma viņu piesaistīs (nevis izveidos jaunu).

Rezultāts:
- Pasūtījuma rindā jābūt zaļam **Calibre book** un zaļam **Calibre user**.

### 2.2 Manuāli piešķirt piekļuvi (izveidot manuālu lietotājs ↔ grāmata sasaisti)

Izmantojiet, ja klients ir samaksājis, bet webhook/imports nav ienācis, vai citos manuāla atbalsta gadījumos.

1. Atveriet `/admin/ebookslv/orders/`.
2. Formā **Add Order**:
   - Ievadiet klienta **Email**.
   - Ievadiet nopirktās grāmatas **Mozello handle**.
     - Parasti handle izskatās kā `book-123`.
3. Nospiediet **Add Order**.
4. Ja rindā zem **Calibre user** ir “Not linked”, nospiediet **Create User**.
5. Ja rindā ir “Calibre book missing”, nospiediet **Refresh**.

Piezīmes:
- Ja nezināt handle, atveriet `/admin/ebookslv/books/` un tabulā atrodiet grāmatu un tās Mozello handle.

### 2.3 Klients nevar ielogoties / aizmirsis paroli

Palūdziet klientam izmantot pogu **Forgot password?** lapā `/login`.

Ja e-pastu sūtīšana ir konfigurēta, viņš saņems paroles atiestatīšanas e-pastu.

Ja joprojām nevar atiestatīt:
- Pārbaudiet, vai pasūtījuma ierakstā e-pasts ir pareizs.
- Ja nepieciešams, nospiediet **Create User** pasūtījuma rindā, lai pārliecinātos, ka konts eksistē.

### 2.4 Atņemt piekļuvi (noņemt nopirktu grāmatu lietotājam)

1. Atveriet `/admin/ebookslv/orders/`.
2. Atrodiet pasūtījuma ieraksta rindu.
3. Nospiediet atkritnes ikonu (**Delete**) un apstipriniet.

Svarīgi:
- Tiek dzēsts tikai **lokālais piekļuves ieraksts**.
- Mozello pusē nekas netiek atmaksāts vai mainīts.

### 2.5 Dublikāti / nepareizs e-pasts

- Ja pasūtījuma rinda izveidota ar nepareizu e-pastu vai handle, **Delete** un izveidojiet pareizu no jauna.
- Ja ir vairāki dublikāti vienam lietotājam un vienam handle, izdzēsiet liekos.

---

## 3) Ātrā problēmu novēršana

### 3.1 “Calibre book missing”

Biežākie iemesli:
- Mozello handle neatbilst nevienai eksportētai grāmatai.
- Grāmata ir Mozello, bet nekad nav eksportēta ar mūsu Books Sync rīku.

Risinājums:
- Aizejiet uz `/admin/ebookslv/books/` un eksportējiet/sinhronizējiet grāmatu, lai handle eksistē.
- Atgriezieties Orders lapā un nospiediet **Refresh**.

### 3.2 “Create User” neizdodas

Biežākais iemesls:
- Calibre runtime nav pieejams.

Risinājums:
- Mēģiniet vēlāk.
- Ja lietotājs jau eksistē, nospiediet **Reload** Orders lapā un tad vēlreiz **Create User** (tas var piesaistīt esošo).

---

Padziļinātai tehniskai informācijai (endpointi, token flow, ko tieši dara “Create User”), skatiet: `docs/operator/user_management_technical.md`.
