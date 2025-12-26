# Grāmatu pārvaldība

Šī ir vienkāršota ikdienas rokasgrāmata grāmatu pārvaldībai **ebooks.lv**.

Grāmatas pārvaldīsiet divās vietās:

- **Calibre** – šeit glabājas grāmatu faili un metadati.
- **ebooks.lv Admin → Books Sync** ([/admin/ebookslv/books/](/admin/ebookslv/books/)) – šeit grāmatas tiek sinhronizētas ar Mozello.

---

## 1) Kur klikšķināt

- Books Sync lapa: [/admin/ebookslv/books/](/admin/ebookslv/books/)
- Mozello iestatījumi (API atslēga, webhook): [/admin/ebookslv/mozello/](/admin/ebookslv/mozello/)

Books Sync lapā izmantotās pogas:

- **Pārlādēt Calibre grāmatas**
- **Ielādēt Mozello produktus**
- **Sinhronizēt cenas no Mozello**
- **Nosūtīt cenas uz Mozello**
- **Eksportēt visu uz veikalu**
- **Dzēst** (katram produktam atsevišķi)

---

## 2) Biežākie uzdevumi

### 2.1 Pievienot jaunu maksas grāmatu

1. Pievienojiet grāmatu **Calibre** un aizpildiet metadatus (nosaukums, vāks, apraksts, valoda).
2. Uzstādiet **cenu** Calibre (lauku `mz_price`).
   - Cenai jābūt **lielākai par 0**.
3. Atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/).
4. Nospiediet **Pārlādēt Calibre grāmatas**.
5. Eksportējiet uz Mozello:
   - Nospiediet **Eksportēt visu uz veikalu**.
6. Pārbaudiet, ka viss izdevās:
   - Izmantojiet pogas **LV / RU / EN**, lai atvērtu Mozello produkta lapu.

### 2.2 Mainīt cenu (Calibre → Mozello)

Izmantojiet šo, ja vēlaties, lai gala cena nāk no Calibre.

1. Izmainiet cenu Calibre (`mz_price`).
2. Atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/).
3. Nospiediet **Nosūtīt cenas uz Mozello**.

### 2.3 Mainīt cenu (Mozello → Calibre)

Izmantojiet šo, ja kāds ir mainījis cenu tieši Mozello.

1. Atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/).
2. Nospiediet **Sinhronizēt cenas no Mozello**.

### 2.4 Padarīt maksas grāmatu par bezmaksas

1. Calibre iestatiet cenu (`mz_price`) uz **0** vai izdzēsiet lauka vērtību.
2. Izlemiet, vai Mozello produktam vēl jāpaliek veikalā:
   - Ja nevēlaties, lai produktu pārdod: [/admin/ebookslv/books/](/admin/ebookslv/books/) rindā nospiediet **Dzēst**.

### 2.5 Dzēst Mozello produktu

1. Atveriet [/admin/ebookslv/books/](/admin/ebookslv/books/).
2. Produktam nospiediet **Dzēst**.

---

## 3) “Orphan” produkti (Mozello produkts bez atbilstošas grāmatas)

1. Nospiediet **Ielādēt Mozello produktus**.
2. Rindas ar atzīmi **ORPHAN** ir produkti, kas eksistē Mozello, bet neatbilst nevienai grāmatai.
3. Parasti drošākais risinājums: **Dzēst** “orphan” produktu un tad eksportēt pareizo grāmatu no Calibre.

---

## 4) Ātrā problēmu novēršana

### 4.1 Eksports neizdodas

- Pārbaudiet Mozello iestatījumus: [/admin/ebookslv/mozello/](/admin/ebookslv/mozello/).
- Pamēģiniet eksportēt vēlreiz, lai redzētu kļūdu.

### 4.2 LV / RU / EN produkta saites nestrādā

- Nospiediet **Ielādēt Mozello produktus** un mēģiniet vēlreiz.
- Ja joprojām nestrādā, eksportējiet grāmatu atkārtoti.

---