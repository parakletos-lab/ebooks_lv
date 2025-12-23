# ebooks.lv Admin Hub (Operators)

Šī ir galvenā navigācijas lapa ebooks.lv admin rīkiem.

- Hub lapa: `/admin/ebookslv/`

Šis dokuments īsi paskaidro, ko nozīmē katra kartīte (card) un uz kuru lapu tā ved.

---

## 1) Kartītes uz `/admin/ebookslv/`

### 1.1 Orders
- Atver: `/admin/ebookslv/orders/`
- Ko tas dara: pārvalda klientu piekļuvi, importējot apmaksātus Mozello pasūtījumus, veidojot manuālus pasūtījumus un piesaistot tos Calibre-Web lietotājiem.

### 1.2 Mozello
- Atver: `/admin/mozello/`
- Ko tas dara: Mozello integrācijas konfigurācija un uzraudzība (API/webhook iestatījumi), lai pasūtījumi un produktu saites strādātu korekti.

### 1.3 Books
- Atver: `/admin/ebookslv/books/`
- Ko tas dara: sinhronizē Calibre bibliotēkas grāmatas ar Mozello produktiem (ielādē produktus, eksportē/atjaunina, sinhronizē cenas un veic produktu uzturēšanas darbības).

### 1.4 Email Templates
- Atver: `/admin/ebookslv/email-templates/`
- Ko tas dara: rediģē ebooks.lv izejošo e-pastu šablonus (piemēram, pirkuma/ielogošanās e-pastus) un atļautos tokenus.

---

## 2) Poga uz hub lapas

### 2.1 Set default settings
- Pogas atrašanās vieta: `/admin/ebookslv/`
- Mērķis: uzstāda ieteiktos noklusējuma Calibre-Web iestatījumus (lomas, sānjosla, virsraksts).

Ja pēc šīs pogas nospiešanas kaut kas nestrādā, tehniskā informācija ir: `docs/operator/admin_hub_technical.md`.
