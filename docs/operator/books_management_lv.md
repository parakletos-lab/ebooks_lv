# Grāmatu pārvaldība (Operators)

Šī ir vienkāršota ikdienas rokasgrāmata grāmatu pārvaldībai.

Jūs strādāsiet divās vietās:

- **Calibre** (kur glabājas grāmatu faili un metadati)
- **ebooks.lv Admin → Books Sync** (`/admin/ebookslv/books/`) (kur grāmatas tiek sinhronizētas ar Mozello)

---

## 1) Kur klikšķināt

- Books Sync lapa: `/admin/ebookslv/books/`
- Mozello iestatījumi (API atslēga, webhook): `/admin/mozello/`

Pogas, kuras izmantosiet Books Sync lapā:

- **Reload Calibre Books**
- **Export All to Store**
- **Export** (katrai grāmatai atsevišķi)
- **Push Prices to Mozello**
- **Sync Prices from Mozello**
- **Load Mozello Products**
- **Delete** (katram produktam atsevišķi)

Adminiem pieejams arī grāmatas lapā (`/book/<id>`):

- **Sync to Mozello** (eksportē tikai šo vienu grāmatu)

---

## 2) Biežākie uzdevumi

### 2.1 Pievienot jaunu maksas grāmatu

1. Pievienojiet grāmatu **Calibre** un aizpildiet metadatus (nosaukums, vāks, apraksts, valoda).
2. Uzstādiet **cenu** Calibre (izmantojiet lauku `mz_price`).
   - Cenai jābūt **lielākai par 0**.
3. Atveriet `/admin/ebookslv/books/`.
4. Nospiediet **Reload Calibre Books**.
5. Eksportējiet uz Mozello:
   - Vienai grāmatai: rindā nospiediet **Export**.
   - Vairākām jaunām maksas grāmatām: nospiediet **Export All to Store**.
   - Alternatīvi: atveriet `/book/<id>` un nospiediet **Sync to Mozello**.
6. Pārbaudiet, ka viss izdevās:
   - Izmantojiet pogas **LV / RU / EN**, lai atvērtu Mozello produkta lapu.

### 2.2 Mainīt cenu (Calibre → Mozello)

Izmantojiet šo, ja vēlaties, lai gala cena nāk no Calibre.

1. Izmainiet cenu Calibre (`mz_price`).
2. Atveriet `/admin/ebookslv/books/`.
3. Nospiediet **Push Prices to Mozello**.

### 2.3 Mainīt cenu (Mozello → Calibre)

Izmantojiet šo, ja kāds cenu ir izmainījis tieši Mozello.

1. Atveriet `/admin/ebookslv/books/`.
2. Nospiediet **Sync Prices from Mozello**.

### 2.4 Padarīt maksas grāmatu par bezmaksas

1. Calibre iestatiet cenu (`mz_price`) uz **0** (vai notīriet lauku).
2. Izlemiet, vai Mozello produktam vēl jāpaliek veikalā:
   - Ja nevēlaties, lai produktu vairs pārdod: `/admin/ebookslv/books/` rindā nospiediet **Delete**.

### 2.5 Dzēst Mozello produktu

1. Atveriet `/admin/ebookslv/books/`.
2. Produktam nospiediet **Delete**.

---

## 3) “Orphan” produkti (Mozello produkts bez atbilstošas grāmatas)

1. Nospiediet **Load Mozello Products**.
2. Rindas ar atzīmi **ORPHAN** ir produkti, kas eksistē Mozello, bet neatbilst nevienai grāmatai.
3. Parasti drošākais risinājums ir **Delete** “orphan” produktu un tad eksportēt pareizo grāmatu no Calibre.

---

## 4) Ātrā problēmu novēršana

### 4.1 Eksports neizdodas

- Pārbaudiet Mozello iestatījumus `/admin/mozello/`.
- Pamēģiniet eksportēt vienu grāmatu (rindā **Export**), lai redzētu kļūdu.

### 4.2 LV/RU/EN produkta saites nestrādā

- Nospiediet **Load Mozello Products** un mēģiniet vēlreiz.
- Ja joprojām nestrādā, eksportējiet grāmatu atkārtoti.

---

Tehniskai informācijai (kā lauki tiek glabāti, endpointi, shēma un padziļināta atkļūdošana), skatiet: `docs/operator/books_management_technical.md`.
