# Spoty — Yapılacaklar

Uygulama tamamen çalışıyor. Arayüz, mockup'a piksel-mükemmel uyması için **HTML/CSS/JS +
webview**'a taşındı; eski CustomTkinter arayüzü **tamamen kaldırıldı**.

## Tamamlananlar ✅

- [x] **Webview arayüzü** — `spoty/web_app.py` (Api köprüsü), `spoty/webmain.py` (giriş),
  `spoty/web/` (index.html/style.css/app.js/icons.js). pywebview + WebView2. Çekirdek
  (`core/`) aynen; ses yine Python'da (`just_playback`).
- [x] **Tüm işlevler**: arama/indirme, çalma + kontroller (oynat/duraklat/ileri/geri/
  karıştır/tekrar/sar/ses), çalma listeleri (oluştur/sil/ekle/çıkar), yeniden adlandırma,
  şarkı silme, **sürükle-bırak sıralama (HTML5 DnD)**, Şimdi Çalıyor paneli aç/kapat,
  otomatik sonraki şarkı, boş kütüphane ekranı, ses/son-şarkı hatırlama.
- [x] **UX**: arama işlevi büyüteçte; sonuçlar arama çubuğu altında açılır panel; yükleniyor
  durumları CSS spinner; kısa placeholder ("Ne dinlemek istersin?").
- [x] **Eski CTk arayüzü kaldırıldı** (`spoty/ui/`, `spoty/main.py`, `customtkinter` bağımlılığı).

## İleride (opsiyonel fikirler)

- [ ] Şarkı sözü gösterimi
- [ ] İndirme formatı / kalite seçimi (şu an sabit mp3 192k)

> Geçmiş: önce CTk ile yapıldı (kütüphane/çalma/listeler → görsel cila → backlog özellikler →
> Spotify benzeri redesign), sonra piksel-mükemmel uyum için webview'a taşındı.

---

## Notlar (mevcut durum)
- Çalıştırma: `.\.venv\Scripts\python.exe -m spoty.webmain`
- Mimari ve komutlar için: `CLAUDE.md` · tasarım referansı: `design/mockup.html`
- Webview mantığı GUI'siz test edilir: `from spoty.web_app import Api; Api()` + metot çağrıları.
  Frontend için `node --check spoty/web/app.js`.
- Arayüz dosyaları: HTML/CSS/JS → `spoty/web/`; köprü/Api → `spoty/web_app.py`.
